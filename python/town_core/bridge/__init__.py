"""M2 local WebSocket bridge for Small Town World Model（STWM）."""

from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.server import BridgeWebSocketServer
from town_core.bridge.session import BridgeProtocolError, BridgeSession, SessionPhase

__all__ = [
    "BridgeProtocolError",
    "BridgeRuntime",
    "BridgeSession",
    "BridgeWebSocketServer",
    "SessionPhase",
]
