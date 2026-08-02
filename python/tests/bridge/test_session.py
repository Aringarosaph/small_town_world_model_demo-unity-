from __future__ import annotations

from typing import Any, cast

import pytest
from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.session import BridgeProtocolError, SessionPhase
from town_core.domain.enums import (
    PROTOCOL_VERSION,
    MessageType,
    MovementCancellationReason,
    MovementFailureReason,
)
from town_core.domain.protocol_models import (
    ActionCancelledMessage,
    ActionCancelledPayload,
    ActionPhaseChangedMessage,
    MovementArrivedMessage,
    MovementArrivedPayload,
    MovementCancelledMessage,
    MovementCancelledPayload,
    MovementFailedMessage,
    MovementFailedPayload,
    PresentationCompletedMessage,
    PresentationCompletedPayload,
    ProtocolMessage,
    ServerHelloMessage,
    WorldSnapshotMessage,
)
from town_core.simulation.initialization import state_hash

from .conftest import (
    FIXED_NOW,
    asset_registry,
    client_hello,
    complete_handshake,
    ready_message,
)


def _traveling_action(runtime: BridgeRuntime) -> tuple[str, tuple[ProtocolMessage, ...]]:
    for _ in range(500):
        messages = runtime.advance_one_minute()
        agent = runtime.engine.state.agents["npc_01"]
        if agent.current_action_id is not None:
            action = runtime.engine.state.active_actions[agent.current_action_id]
            if action.phase.value == "TRAVELING":
                return action.action_id, messages
    raise AssertionError("M2 work travel was not created")


def _reserved_slot(runtime: BridgeRuntime, action_id: str) -> tuple[str, int]:
    for object_id, obj in runtime.engine.state.objects.items():
        for slot, owner in obj.occupied_slots.items():
            if owner == action_id:
                return object_id, slot
    raise AssertionError("traveling action has no slot")


def test_handshake_registry_snapshot_and_client_ready_gate(runtime: BridgeRuntime) -> None:
    session = runtime.open_session()
    hello = client_hello(runtime)
    hello_outputs = session.receive_json(hello.model_dump(mode="json"))
    duplicate_outputs = session.receive_json(hello.model_dump(mode="json"))
    assert duplicate_outputs == hello_outputs
    assert session.phase is SessionPhase.AWAITING_ASSET_REGISTRY

    with pytest.raises(ValueError, match="client_ready"):
        runtime.advance_one_minute()

    registry_outputs = session.receive_json(asset_registry(runtime).model_dump(mode="json"))
    assert [item.message_type for item in registry_outputs] == [
        MessageType.ASSET_REGISTRY_RESULT,
        MessageType.WORLD_SNAPSHOT,
    ]
    snapshot = registry_outputs[1]
    assert snapshot.state_version == runtime.engine.state.state_version
    assert not runtime.ready

    ready_outputs = session.receive_json(ready_message(runtime, snapshot.state_version).model_dump(mode="json"))
    assert ready_outputs[0].message_type is MessageType.SIMULATION_CLOCK_UPDATED
    assert runtime.ready
    assert session.phase is SessionPhase.READY
    evidence = runtime.evidence()["sessions"][0]
    assert evidence["catalog_protocol_version"] == "0.1.0"
    assert evidence["negotiated_protocol_version"] == "0.2.0"
    assert evidence["snapshot_state_version"] == snapshot.state_version
    assert evidence["ready_acknowledged"] is True


def test_bootstrap_decodes_legacy_envelope_but_m2_negotiates_v020(runtime: BridgeRuntime) -> None:
    session = runtime.open_session()
    hello = client_hello(runtime).model_dump(mode="json")
    hello["protocol_version"] = "0.1.0"
    hello["payload"]["supported_protocol_versions"] = ["0.2.0", "0.1.0"]

    outputs = session.receive_json(hello)

    response = outputs[0]
    assert isinstance(response, ServerHelloMessage)
    assert response.protocol_version == "0.2.0"
    assert response.payload.accepted_protocol_version == "0.2.0"


def test_legacy_only_client_cannot_enter_active_m2_session(runtime: BridgeRuntime) -> None:
    session = runtime.open_session()
    hello = client_hello(runtime).model_dump(mode="json")
    hello["protocol_version"] = "0.1.0"
    hello["payload"]["supported_protocol_versions"] = ["0.1.0"]

    with pytest.raises(BridgeProtocolError, match="M2_PROTOCOL_NEGOTIATION_FAILED"):
        session.receive_json(hello)


def test_message_id_content_mismatch_is_protocol_error(runtime: BridgeRuntime) -> None:
    session = runtime.open_session()
    hello = client_hello(runtime).model_dump(mode="json")
    session.receive_json(hello)
    changed = dict(hello)
    changed["sent_at_utc"] = "2026-08-02T00:00:01Z"

    with pytest.raises(BridgeProtocolError, match="MESSAGE_ID_CONTENT_MISMATCH"):
        session.receive_json(changed)


def test_arrival_is_exactly_once_and_invalid_late_report_resyncs(runtime: BridgeRuntime) -> None:
    session = complete_handshake(runtime)
    action_id, presentation = _traveling_action(runtime)
    assert any(getattr(item, "message_type", None) is MessageType.ACTION_STARTED for item in presentation)
    object_id, slot = _reserved_slot(runtime, action_id)
    report = MovementArrivedMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_20000001",
        message_type=MessageType.MOVEMENT_ARRIVED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=action_id,
        payload=MovementArrivedPayload(
            action_id=action_id,
            agent_id="npc_01",
            object_id=object_id,
            slot_index=slot,
        ),
    )
    before_version = runtime.engine.state.state_version

    outputs = session.receive_json(report.model_dump(mode="json"))
    after_first = state_hash(runtime.engine.state)
    assert runtime.engine.state.state_version == before_version + 1
    assert any(item.message_type is MessageType.ACTION_PHASE_CHANGED for item in outputs)

    assert session.receive_json(report.model_dump(mode="json")) == ()
    assert state_hash(runtime.engine.state) == after_first

    late = report.model_copy(update={"message_id": "msg_20000002", "state_version": before_version})
    resync = session.receive_json(late.model_dump(mode="json"))
    assert len(resync) == 1
    assert resync[0].message_type is MessageType.WORLD_SNAPSHOT
    assert state_hash(runtime.engine.state) == after_first


def test_failure_report_is_authoritative_and_duplicate_is_noop(runtime: BridgeRuntime) -> None:
    session = complete_handshake(runtime)
    action_id, _ = _traveling_action(runtime)
    report = MovementFailedMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_21000001",
        message_type=MessageType.MOVEMENT_FAILED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=action_id,
        payload=MovementFailedPayload(
            action_id=action_id,
            agent_id="npc_01",
            reason=MovementFailureReason.SLOT_BLOCKED,
        ),
    )
    before_version = runtime.engine.state.state_version

    outputs = session.receive_json(report.model_dump(mode="json"))
    after_first = state_hash(runtime.engine.state)
    assert runtime.engine.state.state_version == before_version + 1
    assert action_id not in runtime.engine.state.active_actions
    assert any(isinstance(item, ActionPhaseChangedMessage) and item.payload.phase.value == "FAILED" for item in outputs)
    assert session.receive_json(report.model_dump(mode="json")) == ()
    assert state_hash(runtime.engine.state) == after_first


def test_typed_cancellation_is_exactly_once_and_emits_authority_outcome(runtime: BridgeRuntime) -> None:
    session = complete_handshake(runtime)
    action_id, _ = _traveling_action(runtime)
    reported_version = runtime.engine.state.state_version
    runtime.advance_one_minute()
    before_version = runtime.engine.state.state_version
    before_minute = runtime.engine.state.game_minute
    before_resources = runtime.engine.state.households["household_a"]
    report = MovementCancelledMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_22000001",
        message_type=MessageType.MOVEMENT_CANCELLED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=reported_version,
        correlation_id=action_id,
        payload=MovementCancelledPayload(
            action_id=action_id,
            agent_id="npc_01",
            reason=MovementCancellationReason.NAVIGATION_STOPPED,
        ),
    )

    future = report.model_copy(
        update={"message_id": "msg_22000009", "state_version": runtime.engine.state.state_version + 1}
    )
    before_future = state_hash(runtime.engine.state)
    with pytest.raises(BridgeProtocolError, match="FUTURE_STATE_VERSION"):
        session.receive_json(future.model_dump(mode="json"))
    assert state_hash(runtime.engine.state) == before_future

    outputs = session.receive_json(report.model_dump(mode="json"))
    committed_hash = state_hash(runtime.engine.state)
    assert runtime.engine.state.game_minute == before_minute
    assert runtime.engine.state.state_version == before_version + 1
    assert runtime.engine.state.households["household_a"] == before_resources
    assert runtime.engine.state.agents["npc_01"].current_action_id is None
    cancellation = next(item for item in outputs if isinstance(item, ActionCancelledMessage))
    assert cancellation.correlation_id == action_id
    assert cancellation.payload.reason == MovementCancellationReason.NAVIGATION_STOPPED.value

    assert session.receive_json(report.model_dump(mode="json")) == ()
    assert state_hash(runtime.engine.state) == committed_hash

    conflicting = report.model_copy(
        update={"payload": report.payload.model_copy(update={"reason": MovementCancellationReason.CLIENT_SHUTDOWN})}
    )
    with pytest.raises(BridgeProtocolError, match="MESSAGE_ID_CONTENT_MISMATCH"):
        session.receive_json(conflicting.model_dump(mode="json"))
    assert state_hash(runtime.engine.state) == committed_hash

    late = report.model_copy(update={"message_id": "msg_22000002"})
    resync = session.receive_json(late.model_dump(mode="json"))
    assert resync[0].message_type is MessageType.WORLD_SNAPSHOT
    assert state_hash(runtime.engine.state) == committed_hash


def test_python_authority_message_is_rejected_on_unity_ingress(runtime: BridgeRuntime) -> None:
    session = complete_handshake(runtime)
    action_id, _ = _traveling_action(runtime)
    before = state_hash(runtime.engine.state)
    wrong_direction = ActionCancelledMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_23000001",
        message_type=MessageType.ACTION_CANCELLED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=action_id,
        payload=ActionCancelledPayload(action_id=action_id, reason="NAVIGATION_STOPPED"),
    )

    with pytest.raises(BridgeProtocolError, match="INVALID_UNITY_TO_PYTHON_ENVELOPE"):
        session.receive_json(wrong_direction.model_dump(mode="json"))
    assert state_hash(runtime.engine.state) == before


def test_obsolete_generation_cancellation_cannot_mutate_authority(runtime: BridgeRuntime) -> None:
    old_session = complete_handshake(runtime)
    action_id, _ = _traveling_action(runtime)
    report = MovementCancelledMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_24000001",
        message_type=MessageType.MOVEMENT_CANCELLED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=action_id,
        payload=MovementCancelledPayload(
            action_id=action_id,
            agent_id="npc_01",
            reason=MovementCancellationReason.SCENE_UNLOADED,
        ),
    )
    before = state_hash(runtime.engine.state)
    runtime.open_session()

    with pytest.raises(BridgeProtocolError, match="OBSOLETE_CONNECTION_GENERATION") as caught:
        old_session.receive_json(report.model_dump(mode="json"))
    assert caught.value.resync_required is True
    assert state_hash(runtime.engine.state) == before


def test_reconnect_invalidates_old_generation_and_sends_fresh_snapshot(runtime: BridgeRuntime) -> None:
    old_session = complete_handshake(runtime)
    runtime.advance_one_minute()
    last_version = runtime.engine.state.state_version
    old_server_ids: set[str] = set()

    new_session = runtime.open_session()
    hello_outputs = new_session.receive_json(client_hello(runtime, "msg_30000001").model_dump(mode="json"))
    old_server_ids.update(item.message_id for item in hello_outputs)
    registry_outputs = new_session.receive_json(
        asset_registry(runtime, message_id="msg_30000002").model_dump(mode="json")
    )
    snapshot = registry_outputs[1]
    assert isinstance(snapshot, WorldSnapshotMessage)
    assert snapshot.state_version >= last_version
    assert snapshot.payload.world == runtime.engine.state
    assert not old_server_ids.intersection(item.message_id for item in registry_outputs)
    assert not runtime.ready

    before = state_hash(runtime.engine.state)
    stale_transport_report = PresentationCompletedMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_30000009",
        message_type=MessageType.PRESENTATION_COMPLETED,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=last_version,
        correlation_id="action_00000001",
        payload=PresentationCompletedPayload(action_id="action_00000001", agent_id="npc_01"),
    )
    with pytest.raises(BridgeProtocolError, match="OBSOLETE_CONNECTION_GENERATION"):
        old_session.receive_json(stale_transport_report.model_dump(mode="json"))
    assert state_hash(runtime.engine.state) == before

    new_session.receive_json(
        ready_message(
            runtime,
            snapshot.state_version,
            message_id="msg_30000003",
            registry_message_id="msg_30000002",
        ).model_dump(mode="json")
    )
    assert runtime.ready


def test_incompatible_protocol_is_rejected_readably(runtime: BridgeRuntime) -> None:
    session = runtime.open_session()
    raw = client_hello(runtime).model_dump(mode="json")
    raw["protocol_version"] = "9.9.9"

    with pytest.raises(BridgeProtocolError, match="INCOMPATIBLE_PROTOCOL_VERSION"):
        session.receive_json(raw)
