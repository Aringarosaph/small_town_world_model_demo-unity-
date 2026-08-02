from __future__ import annotations

import asyncio
import json

from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.server import BridgeWebSocketServer
from websockets.asyncio.client import connect

from .conftest import asset_registry, client_hello, ready_message


def test_real_local_websocket_handshake_and_readiness(runtime: BridgeRuntime) -> None:
    async def scenario() -> None:
        server = BridgeWebSocketServer(runtime, port=0, auto_advance=False)
        async with server.running():
            assert server.bound_port is not None
            uri = f"ws://127.0.0.1:{server.bound_port}/town"
            async with connect(uri) as websocket:
                await websocket.send(client_hello(runtime).model_dump_json())
                hello_response = json.loads(await websocket.recv())
                assert hello_response["message_type"] == "server_hello"

                await websocket.send(asset_registry(runtime).model_dump_json())
                registry_response = json.loads(await websocket.recv())
                snapshot = json.loads(await websocket.recv())
                assert registry_response["payload"]["accepted"] is True
                assert snapshot["message_type"] == "world_snapshot"
                assert not runtime.ready

                await websocket.send(ready_message(runtime, snapshot["state_version"]).model_dump_json())
                clock = json.loads(await websocket.recv())
                assert clock["message_type"] == "simulation_clock_updated"
                assert runtime.ready

    asyncio.run(scenario())
