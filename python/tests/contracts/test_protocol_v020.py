from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from town_core.catalogs import load_catalog
from town_core.domain.enums import (
    LEGACY_PROTOCOL_VERSION,
    M2_ACCEPTED_PROTOCOL_VERSIONS,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    MessageType,
    MovementCancellationReason,
)
from town_core.domain.protocol_models import (
    ClientHelloMessage,
    ClientHelloV010Message,
    ProtocolMessage,
    ProtocolMessageV010,
    PythonToUnityMessage,
    ServerHelloMessage,
    UnityToPythonMessage,
    select_m2_protocol_version,
    select_protocol_version,
)

PROTOCOL_ADAPTER: TypeAdapter[ProtocolMessage] = TypeAdapter(ProtocolMessage)
PROTOCOL_V010_ADAPTER: TypeAdapter[ProtocolMessageV010] = TypeAdapter(ProtocolMessageV010)
PYTHON_TO_UNITY_ADAPTER: TypeAdapter[PythonToUnityMessage] = TypeAdapter(PythonToUnityMessage)
UNITY_TO_PYTHON_ADAPTER: TypeAdapter[UnityToPythonMessage] = TypeAdapter(UnityToPythonMessage)
CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config" / "v0"


def _envelope(
    message_type: str,
    payload: dict[str, Any],
    *,
    version: str = "0.2.0",
    correlation_id: str | None = None,
    state_version: int = 17,
) -> dict[str, Any]:
    return {
        "protocol_version": version,
        "message_id": "msg_000100",
        "message_type": message_type,
        "sent_at_utc": "2026-08-02T12:00:00Z",
        "world_id": "demo_world",
        "state_version": state_version,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def _client_hello(version: str, supported: list[str]) -> dict[str, Any]:
    return _envelope(
        "client_hello",
        {
            "client_name": "unity",
            "unity_editor_version": "6000.4.2f1",
            "supported_protocol_versions": supported,
        },
        version=version,
        state_version=0,
    )


def _movement_cancelled(*, version: str = "0.2.0", correlation_id: str = "action_00000001") -> dict[str, Any]:
    return _envelope(
        "movement_cancelled",
        {
            "action_id": "action_00000001",
            "agent_id": "npc_01",
            "reason": "NAVIGATION_STOPPED",
        },
        version=version,
        correlation_id=correlation_id,
    )


def test_protocol_version_policy_is_explicit() -> None:
    assert PROTOCOL_VERSION == "0.2.0"
    assert LEGACY_PROTOCOL_VERSION == "0.1.0"
    assert SUPPORTED_PROTOCOL_VERSIONS == ("0.2.0", "0.1.0")
    assert M2_ACCEPTED_PROTOCOL_VERSIONS == ("0.2.0",)


def test_catalog_protocol_version_is_provenance_not_bridge_negotiation() -> None:
    assert load_catalog(CONFIG_ROOT).world.protocol_version == "0.1.0"
    assert PROTOCOL_VERSION == "0.2.0"


def test_client_hello_bootstrap_preserves_preference_order() -> None:
    hello = TypeAdapter(ClientHelloMessage).validate_python(
        _client_hello("0.2.0", ["0.2.0", "0.1.0"])
    )

    assert hello.payload.supported_protocol_versions == ["0.2.0", "0.1.0"]
    assert select_protocol_version(hello.payload.supported_protocol_versions) == "0.2.0"
    assert select_m2_protocol_version(hello.payload.supported_protocol_versions) == "0.2.0"


def test_legacy_client_hello_remains_decodable_but_cannot_enter_m2() -> None:
    hello = TypeAdapter(ClientHelloV010Message).validate_python(_client_hello("0.1.0", ["0.1.0"]))

    assert select_protocol_version(hello.payload.supported_protocol_versions) == "0.1.0"
    with pytest.raises(ValueError, match="requires protocol 0.2.0"):
        select_m2_protocol_version(hello.payload.supported_protocol_versions)

    with pytest.raises(ValueError, match="first client preference"):
        select_m2_protocol_version(["0.1.0", "0.2.0"])


def test_legacy_non_cancellation_message_retains_v010_decoder_shape() -> None:
    raw = _envelope(
        "action_phase_changed",
        {"action_id": "action_00000001", "phase": "TRAVELING"},
        version="0.1.0",
        correlation_id=None,
    )

    message = PROTOCOL_V010_ADAPTER.validate_python(raw)
    assert message.protocol_version == "0.1.0"
    with pytest.raises(ValidationError):
        PROTOCOL_ADAPTER.validate_python(raw)


def test_client_hello_rejects_duplicate_or_mismatched_bootstrap_versions() -> None:
    adapter = TypeAdapter(ClientHelloMessage)
    with pytest.raises(ValidationError, match="unique"):
        adapter.validate_python(_client_hello("0.2.0", ["0.2.0", "0.2.0"]))
    with pytest.raises(ValidationError, match="envelope version"):
        adapter.validate_python(_client_hello("0.1.0", ["0.2.0"]))


def test_server_hello_envelope_uses_selected_version() -> None:
    raw = _envelope(
        "server_hello",
        {
            "server_name": "python_town_core",
            "accepted_protocol_version": "0.2.0",
            "config_version": "v0",
            "schema_version": "v0.1",
        },
        version="0.2.0",
        correlation_id="msg_000001",
        state_version=0,
    )
    assert TypeAdapter(ServerHelloMessage).validate_python(raw).protocol_version == "0.2.0"

    raw["protocol_version"] = "0.1.0"
    with pytest.raises(ValidationError, match="selected protocol version"):
        TypeAdapter(ServerHelloMessage).validate_python(raw)


def test_movement_cancelled_is_v020_unity_report_only() -> None:
    message = UNITY_TO_PYTHON_ADAPTER.validate_python(_movement_cancelled())

    assert message.message_type is MessageType.MOVEMENT_CANCELLED
    assert message.payload.reason is MovementCancellationReason.NAVIGATION_STOPPED
    assert PROTOCOL_ADAPTER.validate_python(_movement_cancelled()).protocol_version == "0.2.0"
    with pytest.raises(ValidationError):
        PYTHON_TO_UNITY_ADAPTER.validate_python(_movement_cancelled())


def test_action_cancelled_is_python_authority_output_only() -> None:
    raw = _envelope(
        "action_cancelled",
        {"action_id": "action_00000001", "reason": "MOVEMENT_CANCELLED"},
        correlation_id="action_00000001",
    )

    assert PYTHON_TO_UNITY_ADAPTER.validate_python(raw).message_type is MessageType.ACTION_CANCELLED
    with pytest.raises(ValidationError):
        UNITY_TO_PYTHON_ADAPTER.validate_python(raw)


def test_protocol_v010_cannot_encode_movement_cancelled() -> None:
    with pytest.raises(ValidationError):
        PROTOCOL_ADAPTER.validate_python(_movement_cancelled(version="0.1.0"))


@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        (
            "action_started",
            {
                "action_id": "action_00000001",
                "agent_ids": ["npc_01"],
                "behavior_id": "work_shift",
                "destination_location_id": "cafe_bar",
                "target_object_ids": ["cafe_bar_workstation_01"],
                "animation_semantic": "WORK_STANDING",
                "prop_semantic": None,
                "planned_duration_minutes": 480,
            },
        ),
        ("action_phase_changed", {"action_id": "action_00000001", "phase": "TRAVELING"}),
        ("action_cancelled", {"action_id": "action_00000001", "reason": "MOVEMENT_CANCELLED"}),
        (
            "movement_arrived",
            {"action_id": "action_00000001", "agent_id": "npc_01", "object_id": None, "slot_index": None},
        ),
        (
            "movement_failed",
            {"action_id": "action_00000001", "agent_id": "npc_01", "reason": "NO_PATH"},
        ),
        (
            "movement_cancelled",
            {"action_id": "action_00000001", "agent_id": "npc_01", "reason": "NAVIGATION_STOPPED"},
        ),
        ("presentation_completed", {"action_id": "action_00000001", "agent_id": "npc_01"}),
    ],
)
def test_all_action_messages_require_exact_action_correlation(
    message_type: str,
    payload: dict[str, Any],
) -> None:
    assert PROTOCOL_ADAPTER.validate_python(
        _envelope(message_type, payload, correlation_id="action_00000001")
    )

    with pytest.raises(ValidationError, match="correlation_id"):
        PROTOCOL_ADAPTER.validate_python(_envelope(message_type, payload, correlation_id="action_00000002"))


def test_reported_state_version_remains_non_negative() -> None:
    with pytest.raises(ValidationError):
        UNITY_TO_PYTHON_ADAPTER.validate_python(_movement_cancelled() | {"state_version": -1})
