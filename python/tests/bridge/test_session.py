from __future__ import annotations

from typing import Any, cast

import pytest
from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.session import BridgeProtocolError, SessionPhase
from town_core.domain.enums import PROTOCOL_VERSION, MessageType, MovementFailureReason
from town_core.domain.protocol_models import (
    ActionPhaseChangedMessage,
    MovementArrivedMessage,
    MovementArrivedPayload,
    MovementFailedMessage,
    MovementFailedPayload,
    PresentationCompletedMessage,
    PresentationCompletedPayload,
    ProtocolMessage,
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

    late = report.model_copy(update={"message_id": "msg_20000002", "state_version": before_version})
    resync = session.receive_json(late.model_dump(mode="json"))
    assert len(resync) == 1
    assert resync[0].message_type is MessageType.WORLD_SNAPSHOT
    assert state_hash(runtime.engine.state) == after_first


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
