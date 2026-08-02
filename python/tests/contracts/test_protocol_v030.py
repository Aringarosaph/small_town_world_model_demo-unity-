from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError
from town_core.domain.enums import (
    M2_ACCEPTED_PROTOCOL_VERSIONS,
    M3_ACCEPTED_PROTOCOL_VERSIONS,
    M3_PROTOCOL_VERSION,
    M3_SUPPORTED_PROTOCOL_VERSIONS,
    PROTOCOL_VERSION,
)
from town_core.domain.m3_models import M3CandidateAction
from town_core.domain.protocol_models import (
    ActionStartedV030Message,
    AgentStateDeltaV030Message,
    ClientHelloBootstrapMessage,
    DebugDecisionTraceV030Message,
    HouseholdStateDeltaV030Message,
    ProtocolMessage,
    ProtocolMessageV030,
    PythonToUnityMessageV030,
    UnityToPythonMessageV030,
    WorldSnapshotV030Message,
    select_m3_protocol_version,
    select_protocol_version,
)
from town_core.domain.schema_artifacts import VERSION_DOCUMENT

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_ROOT = REPO_ROOT / "protocol" / "examples"
V020_ADAPTER: TypeAdapter[ProtocolMessage] = TypeAdapter(ProtocolMessage)
V030_ADAPTER: TypeAdapter[ProtocolMessageV030] = TypeAdapter(ProtocolMessageV030)
V030_PYTHON_ADAPTER: TypeAdapter[PythonToUnityMessageV030] = TypeAdapter(PythonToUnityMessageV030)
V030_UNITY_ADAPTER: TypeAdapter[UnityToPythonMessageV030] = TypeAdapter(UnityToPythonMessageV030)
BOOTSTRAP_ADAPTER: TypeAdapter[ClientHelloBootstrapMessage] = TypeAdapter(ClientHelloBootstrapMessage)


def _example(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((EXAMPLE_ROOT / f"{name}.json").read_text(encoding="utf-8")))


def _v030(message_type: str, payload: dict[str, Any], *, correlation_id: str | None = None) -> dict[str, Any]:
    return {
        "protocol_version": "0.3.0",
        "message_id": "msg_009999",
        "message_type": message_type,
        "sent_at_utc": "2026-08-02T12:30:00Z",
        "world_id": "demo_world",
        "state_version": 55,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def _upgrade_example(name: str) -> dict[str, Any]:
    value = _example(name)
    value["protocol_version"] = "0.3.0"
    return value


def test_m3_version_policy_preserves_m2_compatibility_surface() -> None:
    assert PROTOCOL_VERSION == "0.2.0"
    assert M3_PROTOCOL_VERSION == "0.3.0"
    assert M2_ACCEPTED_PROTOCOL_VERSIONS == ("0.2.0",)
    assert M3_ACCEPTED_PROTOCOL_VERSIONS == ("0.3.0",)
    assert M3_SUPPORTED_PROTOCOL_VERSIONS == ("0.3.0", "0.2.0", "0.1.0")
    assert VERSION_DOCUMENT["protocol_version"] == "0.3.0"
    assert VERSION_DOCUMENT["schema_version"] == "v0.1"
    compatibility = cast(dict[str, Any], VERSION_DOCUMENT["compatibility"])
    assert compatibility["current"] == "0.3.0"
    assert compatibility["active_m2_acceptance_versions"] == ["0.2.0"]
    assert compatibility["active_m3_acceptance_versions"] == ["0.3.0"]


def test_m3_negotiation_requires_v030_first_without_silent_fallback() -> None:
    assert select_protocol_version(["0.3.0", "0.2.0"]) == "0.3.0"
    assert select_m3_protocol_version(["0.3.0", "0.2.0"]) == "0.3.0"
    with pytest.raises(ValueError, match="first client preference"):
        select_m3_protocol_version(["0.2.0", "0.3.0"])
    with pytest.raises(ValueError, match="requires protocol 0.3.0"):
        select_m3_protocol_version(["0.2.0"])


@pytest.mark.parametrize(
    ("name", "version"),
    [("client-hello-v030", "0.3.0"), ("client-hello", "0.2.0"), ("client-hello-v010-compat", "0.1.0")],
)
def test_bootstrap_decoder_is_version_aware(name: str, version: str) -> None:
    assert BOOTSTRAP_ADAPTER.validate_python(_example(name)).protocol_version == version


def test_v030_and_v020_session_shapes_are_not_overloaded() -> None:
    v030 = _example("action-started-v030")
    v020 = _example("action-started")

    assert V030_ADAPTER.validate_python(v030).protocol_version == "0.3.0"
    assert V020_ADAPTER.validate_python(v020).protocol_version == "0.2.0"
    with pytest.raises(ValidationError):
        V020_ADAPTER.validate_python(v030)
    with pytest.raises(ValidationError):
        V030_ADAPTER.validate_python(v020)


def test_every_v030_unity_input_is_rejected_by_python_output_union() -> None:
    documents = [
        _example("client-hello-v030"),
        _upgrade_example("asset-registry"),
        _upgrade_example("client-ready"),
        _upgrade_example("movement-arrived"),
        _upgrade_example("movement-failed"),
        _upgrade_example("movement-cancelled"),
        _upgrade_example("presentation-completed"),
        _upgrade_example("player-utterance"),
        _v030(
            "player_end_conversation",
            {"conversation_id": "conversation_0001", "target_agent_id": "npc_01"},
            correlation_id="conversation_0001",
        ),
        _v030("set_time_scale_request", {"requested_time_scale": 2.0}),
        _v030("pause_request", {"paused": True}),
    ]
    for document in documents:
        V030_UNITY_ADAPTER.validate_python(document)
        with pytest.raises(ValidationError):
            V030_PYTHON_ADAPTER.validate_python(document)


def test_every_v030_python_output_is_rejected_by_unity_input_union() -> None:
    action_id = "action_00000999"
    event = {
        "event_id": "event_00000999",
        "event_type": "POSITIVE_INTERACTION",
        "game_minute": 55,
        "location_id": "park",
        "actor_ids": ["npc_01"],
        "affected_agent_ids": ["npc_02"],
        "witness_agent_ids": [],
        "source_action_id": action_id,
        "importance": 0.4,
        "witness_scope": "PARTICIPANTS_ONLY",
        "payload": {},
        "supersedes_event_id": None,
    }
    documents = [
        _example("server-hello-v030"),
        _v030("asset_registry_result", {"accepted": True, "issues": []}),
        _example("reconnect-world-snapshot-v030"),
        _v030("simulation_clock_updated", {"game_minute": 55, "time_scale": 2.0, "paused": False}),
        _example("action-started-v030"),
        _v030("action_phase_changed", {"action_id": action_id, "phase": "PERFORMING"}, correlation_id=action_id),
        _v030("action_cancelled", {"action_id": action_id, "reason": "INTERRUPTED"}, correlation_id=action_id),
        _example("agent-state-delta-clear-v030"),
        _example("household-state-delta-v030"),
        _v030(
            "relationship_delta",
            {
                "source_agent_id": "npc_02",
                "target_agent_id": "npc_01",
                "delta": {"familiarity": 0.01, "affinity": 0.02, "trust": 0.0, "tension": -0.01},
            },
        ),
        _v030("world_event_created", {"event": event}, correlation_id="event_00000999"),
        _v030(
            "dialogue_line_ready",
            {"conversation_id": "conversation_0001", "speaker_agent_id": "npc_01", "text": "你好呀。"},
            correlation_id="conversation_0001",
        ),
        _example("debug-decision-trace-v030"),
    ]
    for document in documents:
        V030_PYTHON_ADAPTER.validate_python(document)
        with pytest.raises(ValidationError):
            V030_UNITY_ADAPTER.validate_python(document)


def test_structured_action_participants_are_stable_and_action_correlated() -> None:
    raw = _example("action-started-v030")
    message = ActionStartedV030Message.model_validate(raw)
    assert [item.agent_id for item in message.payload.participants] == ["npc_01", "npc_02"]
    assert message.payload.participants[0].object_bindings[0].slot_index == 0

    duplicate = copy.deepcopy(raw)
    duplicate["payload"]["participants"][1]["agent_id"] = "npc_01"
    with pytest.raises(ValidationError, match="unique"):
        V030_ADAPTER.validate_python(duplicate)

    wrong_correlation = copy.deepcopy(raw)
    wrong_correlation["correlation_id"] = "action_999999"
    with pytest.raises(ValidationError, match="correlation_id"):
        V030_ADAPTER.validate_python(wrong_correlation)


def test_snapshot_restores_exact_active_presentations_and_keeps_world_v01() -> None:
    raw = _example("reconnect-world-snapshot-v030")
    message = WorldSnapshotV030Message.model_validate(raw)
    assert message.payload.world.schema_version == "v0.1"
    assert message.payload.active_presentations[0].conversation_id == "conversation_000301"

    missing = copy.deepcopy(raw)
    missing["payload"]["active_presentations"] = []
    with pytest.raises(ValidationError, match="exactly cover"):
        V030_ADAPTER.validate_python(missing)


def test_agent_delta_field_mask_distinguishes_clear_from_unchanged() -> None:
    raw = _example("agent-state-delta-clear-v030")
    message = AgentStateDeltaV030Message.model_validate(raw)
    assert message.payload.current_action_id is None
    assert "current_action_id" in message.payload.model_fields_set

    absent = copy.deepcopy(raw)
    absent["payload"].pop("current_action_id")
    with pytest.raises(ValidationError, match="exactly match field_mask"):
        V030_ADAPTER.validate_python(absent)

    unmasked = copy.deepcopy(raw)
    unmasked["payload"]["known_event_ids"] = []
    with pytest.raises(ValidationError, match="exactly match field_mask"):
        V030_ADAPTER.validate_python(unmasked)


def test_household_delta_is_python_only_and_resources_cannot_clear() -> None:
    raw = _example("household-state-delta-v030")
    assert HouseholdStateDeltaV030Message.model_validate(raw).payload.money == 145
    with pytest.raises(ValidationError):
        V030_UNITY_ADAPTER.validate_python(raw)

    cleared = copy.deepcopy(raw)
    cleared["payload"]["money"] = None
    with pytest.raises(ValidationError, match="cannot be cleared"):
        V030_ADAPTER.validate_python(cleared)


def test_top_k_trace_represents_attempted_rejected_and_unattempted_rows() -> None:
    raw = _example("debug-decision-trace-v030")
    message = DebugDecisionTraceV030Message.model_validate(raw)
    selected, rejected, unattempted = message.payload.candidates
    assert selected.resolver_result == "ACCEPTED"
    assert selected.proposal_id == message.payload.selected_proposal_id
    assert selected.hard_preview.object_bindings
    assert selected.hard_preview.reservation_keys
    assert selected.hard_preview.settlement_keys
    assert rejected.conflict_code == "WORKSTATION_RESERVED"
    assert unattempted.proposal_id is None and unattempted.resolver_result is None and unattempted.conflict_code is None
    with pytest.raises(ValidationError):
        V030_UNITY_ADAPTER.validate_python(raw)

    false_result = copy.deepcopy(raw)
    false_result["payload"]["candidates"][2]["conflict_code"] = "NOT_ACTUALLY_ATTEMPTED"
    with pytest.raises(ValidationError, match="unattempted"):
        V030_ADAPTER.validate_python(false_result)

    false_proposal = copy.deepcopy(raw)
    false_proposal["payload"]["candidates"][2]["proposal_id"] = "proposal_000399"
    with pytest.raises(ValidationError, match="unattempted"):
        V030_ADAPTER.validate_python(false_proposal)

    missing_conflict = copy.deepcopy(raw)
    missing_conflict["payload"]["candidates"][1]["conflict_code"] = None
    with pytest.raises(ValidationError, match="requires a conflict_code"):
        V030_ADAPTER.validate_python(missing_conflict)

    attempted_without_proposal = copy.deepcopy(raw)
    attempted_without_proposal["payload"]["candidates"][1]["proposal_id"] = None
    with pytest.raises(ValidationError, match="requires a proposal_id"):
        V030_ADAPTER.validate_python(attempted_without_proposal)

    selected_not_accepted = copy.deepcopy(raw)
    selected_not_accepted["payload"]["candidates"][0]["resolver_result"] = "OBJECT_SLOT_CONFLICT"
    selected_not_accepted["payload"]["candidates"][0]["conflict_code"] = "SELECTED_ROW_REJECTED"
    with pytest.raises(ValidationError, match="selected candidate row"):
        V030_ADAPTER.validate_python(selected_not_accepted)

    missing_selected_proposal = copy.deepcopy(raw)
    missing_selected_proposal["payload"]["selected_proposal_id"] = None
    with pytest.raises(ValidationError):
        V030_ADAPTER.validate_python(missing_selected_proposal)

    mismatched_selected_proposal = copy.deepcopy(raw)
    mismatched_selected_proposal["payload"]["selected_proposal_id"] = "proposal_000399"
    with pytest.raises(ValidationError, match="must match the selected candidate row"):
        V030_ADAPTER.validate_python(mismatched_selected_proposal)

    third_attempt = copy.deepcopy(raw)
    third_attempt["payload"]["candidates"][2].update(
        {"proposal_id": "proposal_000303", "resolver_result": "STATE_STALE", "conflict_code": "STATE_STALE"}
    )
    with pytest.raises(ValidationError, match="at most two"):
        V030_ADAPTER.validate_python(third_attempt)


def test_m3_candidate_typed_targets_and_invitation_allowlist() -> None:
    raw = _example("m3-candidate-action")
    candidate = M3CandidateAction.model_validate(raw)
    assert candidate.invited_activity_id == "walk_in_park"

    invalid = copy.deepcopy(raw)
    invalid["invited_activity_id"] = "work_shift"
    with pytest.raises(ValidationError, match="allowlist"):
        M3CandidateAction.model_validate(invalid)

    share = copy.deepcopy(raw)
    share.update(
        {
            "behavior_id": "share_event",
            "invited_activity_id": None,
            "context_event_ids": ["event_0001"],
            "selected_context_event_id": "event_0001",
        }
    )
    assert M3CandidateAction.model_validate(share).selected_context_event_id == "event_0001"

    end = copy.deepcopy(raw)
    end.update(
        {
            "behavior_id": "end_conversation",
            "target_agent_id": None,
            "invited_activity_id": None,
            "target_conversation_id": "conversation_0001",
        }
    )
    assert M3CandidateAction.model_validate(end).target_conversation_id == "conversation_0001"
