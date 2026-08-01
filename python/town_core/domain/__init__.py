"""Versioned domain and wire-contract models."""

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import CONFIG_VERSION, PROTOCOL_VERSION
from town_core.domain.protocol_models import ProtocolMessage

__all__ = [
    "CONFIG_VERSION",
    "PROTOCOL_VERSION",
    "CatalogBundle",
    "ProtocolMessage",
]
