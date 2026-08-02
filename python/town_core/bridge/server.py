"""Local RFC 6455 server for the M2 Unity Bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from pydantic import TypeAdapter
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.session import BridgeProtocolError
from town_core.catalogs import load_catalog
from town_core.domain.enums import PROTOCOL_VERSION
from town_core.domain.protocol_models import ProtocolMessage, PythonToUnityMessage
from town_core.simulation.clock import RuntimeMode
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state

_PYTHON_TO_UNITY_ADAPTER: TypeAdapter[PythonToUnityMessage] = TypeAdapter(PythonToUnityMessage)


class BridgeWebSocketServer:
    """One-active-generation localhost server with transport liveness pings."""

    def __init__(
        self,
        runtime: BridgeRuntime,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/town",
        ping_interval: float = 10.0,
        ping_timeout: float = 10.0,
        wall_seconds_per_game_minute: float = 1.0,
        auto_advance: bool = True,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("M2 bridge may bind only to a loopback interface")
        if port < 0 or port > 65535:
            raise ValueError("port is outside the TCP range")
        if not path.startswith("/"):
            raise ValueError("WebSocket path must be absolute")
        if wall_seconds_per_game_minute <= 0:
            raise ValueError("wall/game clock adapter interval must be positive")
        self.runtime = runtime
        self.host = host
        self.port = port
        self.path = path
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.wall_seconds_per_game_minute = wall_seconds_per_game_minute
        self.auto_advance = auto_advance
        self.bound_port: int | None = None
        self._active_connection: ServerConnection | None = None
        self._active_generation: int | None = None
        self._send_lock = asyncio.Lock()

    @asynccontextmanager
    async def running(self) -> AsyncIterator[BridgeWebSocketServer]:
        async with serve(
            self._handle_connection,
            self.host,
            self.port,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_size=2 * 1024 * 1024,
            compression=None,
        ) as websocket_server:
            self.bound_port = self._bound_port(websocket_server)
            clock_task = asyncio.create_task(self._clock_loop()) if self.auto_advance else None
            try:
                yield self
            finally:
                if clock_task is not None:
                    clock_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await clock_task
                self._active_connection = None
                self._active_generation = None

    async def serve_forever(self) -> None:
        async with self.running():
            await asyncio.Future()

    async def _handle_connection(self, connection: ServerConnection) -> None:
        if connection.request is None or connection.request.path != self.path:
            await connection.close(1008, "INVALID_BRIDGE_PATH")
            return
        session = self.runtime.open_session()
        self._active_connection = connection
        self._active_generation = session.generation
        try:
            async for raw in connection:
                if not isinstance(raw, str):
                    raise BridgeProtocolError("BINARY_MESSAGE_REJECTED", "bridge accepts JSON text frames only")
                outputs = session.receive_json(raw)
                await self._send_messages(connection, session.generation, outputs)
        except BridgeProtocolError as exc:
            self.runtime.diagnostics.append(
                {
                    "code": exc.code,
                    "detail": exc.message,
                    "generation": session.generation,
                    "state_version": self.runtime.engine.state.state_version,
                    "resync_required": exc.resync_required,
                }
            )
            await connection.close(1002, str(exc)[:120])
        except ConnectionClosed:
            pass
        finally:
            session.disconnect()
            if self._active_generation == session.generation:
                self._active_connection = None
                self._active_generation = None

    async def _send_messages(
        self,
        connection: ServerConnection,
        generation: int,
        messages: Sequence[ProtocolMessage],
    ) -> None:
        if not self.runtime.is_current_generation(generation):
            return
        async with self._send_lock:
            for message in messages:
                outbound = _PYTHON_TO_UNITY_ADAPTER.validate_python(message)
                await connection.send(outbound.model_dump_json(exclude_none=False))

    async def _clock_loop(self) -> None:
        while True:
            scale = self.runtime.time_scale
            interval = self.wall_seconds_per_game_minute if scale <= 0 else self.wall_seconds_per_game_minute / scale
            await asyncio.sleep(interval)
            connection = self._active_connection
            generation = self._active_generation
            if connection is None or generation is None or not self.runtime.ready:
                continue
            try:
                messages = self.runtime.advance_one_minute()
                await self._send_messages(connection, generation, messages)
            except (ConnectionClosed, ValueError) as exc:
                self.runtime.diagnostics.append(
                    {
                        "code": "CLOCK_LOOP_PAUSED",
                        "detail": str(exc),
                        "generation": generation,
                        "state_version": self.runtime.engine.state.state_version,
                    }
                )

    @staticmethod
    def _bound_port(server: Server) -> int:
        sockets = tuple(server.sockets)
        if not sockets:
            raise RuntimeError("WebSocket server did not bind a socket")
        return int(sockets[0].getsockname()[1])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small Town World Model（STWM） M2 local Unity Bridge")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--path", default="/town")
    parser.add_argument("--agent", default="npc_01")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--wall-seconds-per-game-minute", type=float, default=1.0)
    return parser


async def _run(args: argparse.Namespace) -> None:
    catalog = load_catalog(args.config)
    state = build_initial_world_state(catalog, seed=args.seed, active_agent_id=args.agent)
    engine = SimulationEngine(
        catalog,
        state,
        active_agent_id=args.agent,
        runtime_mode=RuntimeMode.UNITY_LIVE,
    )
    runtime = BridgeRuntime(catalog, engine)
    server = BridgeWebSocketServer(
        runtime,
        host=args.host,
        port=args.port,
        path=args.path,
        wall_seconds_per_game_minute=args.wall_seconds_per_game_minute,
    )
    async with server.running():
        print(
            json.dumps(
                {
                    "ready": True,
                    "project_name": "Small Town World Model（STWM）",
                    "host": server.host,
                    "port": server.bound_port,
                    "path": server.path,
                    "agent": args.agent,
                    "catalog_protocol_version": catalog.world.protocol_version,
                    "active_m2_protocol_version": PROTOCOL_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        await asyncio.Future()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        asyncio.run(_run(args))
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"ready": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
