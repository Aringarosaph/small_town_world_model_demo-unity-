"""Versioned domain and wire-contract models."""

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import CONFIG_VERSION, LEGACY_PROTOCOL_VERSION, PROTOCOL_VERSION
from town_core.domain.protocol_models import (
    ProtocolMessage,
    ProtocolMessageV010,
    PythonToUnityMessage,
    UnityToPythonMessage,
)

__all__ = [
    "CONFIG_VERSION",
    "LEGACY_PROTOCOL_VERSION",
    "PROTOCOL_VERSION",
    "CatalogBundle",
    "ProtocolMessage",
    "ProtocolMessageV010",
    "PythonToUnityMessage",
    "UnityToPythonMessage",
]
