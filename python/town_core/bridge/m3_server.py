"""Loopback RFC 6455 server for the protocol 0.3 M3_FULL bridge."""

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

from town_core.bridge.m3_runtime import M3BridgeRuntime
from town_core.bridge.session import BridgeProtocolError
from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.domain.enums import M3_PROTOCOL_VERSION
from town_core.domain.protocol_models import (
    AgentStateDeltaV030Message,
    HouseholdStateDeltaV030Message,
    PythonToUnityMessageV030,
)
from town_core.simulation.clock import RuntimeMode
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint

_PYTHON_TO_UNITY_ADAPTER: TypeAdapter[PythonToUnityMessageV030] = TypeAdapter(PythonToUnityMessageV030)


def serialize_outbound_message(message: PythonToUnityMessageV030) -> str:
    """Serialize a 0.3 envelope while preserving delta field-mask presence."""

    outbound = _PYTHON_TO_UNITY_ADAPTER.validate_python(message)
    document = outbound.model_dump(mode="json", exclude_none=False)
    if isinstance(outbound, (AgentStateDeltaV030Message, HouseholdStateDeltaV030Message)):
        document["payload"] = outbound.payload.model_dump(mode="json", exclude_unset=True)
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


class M3BridgeWebSocketServer:
    """One-active-generation M3_FULL server with a client-ready clock gate."""

    def __init__(
        self,
        runtime: M3BridgeRuntime,
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
            raise ValueError("M3 bridge may bind only to a loopback interface")
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
    async def running(self) -> AsyncIterator[M3BridgeWebSocketServer]:
        async with serve(
            self._handle_connection,
            self.host,
            self.port,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_size=8 * 1024 * 1024,
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
        messages: Sequence[PythonToUnityMessageV030],
    ) -> None:
        if not self.runtime.is_current_generation(generation):
            return
        async with self._send_lock:
            for message in messages:
                await connection.send(serialize_outbound_message(message))

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
                await self._send_messages(connection, generation, self.runtime.advance_one_minute())
            except (ConnectionClosed, ValueError) as exc:
                self.runtime.diagnostics.append(
                    {
                        "code": "M3_CLOCK_LOOP_PAUSED",
                        "detail": str(exc),
                        "generation": generation,
                        "state_version": self.runtime.engine.state.state_version,
                    }
                )

    @staticmethod
    def _bound_port(server: Server) -> int:
        sockets = tuple(server.sockets)
        if not sockets:
            raise RuntimeError("M3 WebSocket server did not bind a socket")
        return int(sockets[0].getsockname()[1])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small Town World Model（STWM） M3_FULL local Unity Bridge")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--path", default="/town")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--wall-seconds-per-game-minute", type=float, default=1.0)
    return parser


async def _run(args: argparse.Namespace) -> None:
    catalog = load_catalog(args.config)
    m3_catalogs = load_m3_catalogs(args.config, catalog=catalog)
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=args.seed)
    engine = SocietyEngine(catalog, m3_catalogs, checkpoint, runtime_mode=RuntimeMode.UNITY_LIVE)
    runtime = M3BridgeRuntime(catalog, m3_catalogs, engine)
    server = M3BridgeWebSocketServer(
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
                    "semantic_profile": "M3_FULL",
                    "host": server.host,
                    "port": server.bound_port,
                    "path": server.path,
                    "enabled_agent_ids": sorted(
                        agent.agent_id for agent in engine.state.agents.values() if agent.enabled
                    ),
                    "catalog_protocol_version": catalog.world.protocol_version,
                    "active_m3_protocol_version": M3_PROTOCOL_VERSION,
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
