from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from town_core.bridge.m3_registry import M3FullAssetRegistryValidator
from town_core.bridge.m3_runtime import M3BridgeRuntime
from town_core.bridge.m3_server import M3BridgeWebSocketServer, serialize_outbound_message
from town_core.bridge.session import BridgeProtocolError, SessionPhase
from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.domain.config_models import NeedValues
from town_core.domain.enums import (
    M3_PROTOCOL_VERSION,
    ActionPhase,
    AgentDeltaField,
    BehaviorId,
    MessageType,
    MovementCancellationReason,
    MovementFailureReason,
)
from town_core.domain.protocol_models import (
    AgentStateDeltaV030Message,
    AgentStateDeltaV030Payload,
    AssetRegistryPayload,
    AssetRegistryV030Message,
    ClientHelloV030Message,
    ClientHelloV030Payload,
    ClientReadyPayload,
    ClientReadyV030Message,
    MovementArrivedPayload,
    MovementArrivedV030Message,
    MovementCancelledPayload,
    MovementCancelledV030Message,
    MovementFailedPayload,
    MovementFailedV030Message,
    RegisteredInteractionSlot,
    RegisteredLocation,
    RegisteredNpcView,
    RegisteredObject,
    WorldSnapshotV030Message,
)
from town_core.simulation.clock import RuntimeMode
from town_core.society.checkpoint import checkpoint_hash, initial_transaction_chain_hash
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _runtime(*, social_fixture: bool = False) -> M3BridgeRuntime:
    catalog = load_catalog(ROOT / "config" / "v0")
    m3_catalogs = load_m3_catalogs(ROOT / "config" / "v0", catalog=catalog)
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    allowlist = None
    if social_fixture:
        fixture_agents = {"npc_01", "npc_03"}
        agents = {
            agent_id: agent.model_copy(
                update={
                    "needs": NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.0, social=0.0),
                    "current_location_id": "shop" if agent_id in fixture_agents else agent.current_location_id,
                    "decision_due_at": 600 if agent_id == "npc_03" else 1600,
                }
            )
            for agent_id, agent in checkpoint.world.agents.items()
        }
        locations = {
            location_id: location.model_copy(
                update={
                    "current_agent_ids": sorted(
                        ({*location.current_agent_ids} - fixture_agents)
                        | (fixture_agents if location_id == "shop" else set())
                    )
                }
            )
            for location_id, location in checkpoint.world.locations.items()
        }
        world = checkpoint.world.model_copy(update={"game_minute": 600, "agents": agents, "locations": locations})
        checkpoint = checkpoint.model_copy(
            update={"world": world, "transaction_chain_hash": initial_transaction_chain_hash(world)}
        )
        allowlist = frozenset({BehaviorId.IDLE, BehaviorId.INVITE_JOIN})
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=allowlist,
        runtime_mode=RuntimeMode.UNITY_LIVE,
    )
    return M3BridgeRuntime(catalog, m3_catalogs, engine, now=lambda: NOW)


def _scoped_runtime(behaviors: frozenset[BehaviorId], needs: NeedValues) -> M3BridgeRuntime:
    catalog = load_catalog(ROOT / "config" / "v0")
    m3_catalogs = load_m3_catalogs(ROOT / "config" / "v0", catalog=catalog)
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = {
        agent_id: agent.model_copy(
            update={
                "needs": needs,
                "decision_due_at": 0 if agent_id == "npc_01" else 1000,
            }
        )
        for agent_id, agent in checkpoint.world.agents.items()
    }
    checkpoint = checkpoint.model_copy(update={"world": checkpoint.world.model_copy(update={"agents": agents})})
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=behaviors,
        runtime_mode=RuntimeMode.UNITY_LIVE,
    )
    return M3BridgeRuntime(catalog, m3_catalogs, engine, now=lambda: NOW)


def _registry(runtime: M3BridgeRuntime) -> AssetRegistryPayload:
    manifest = runtime.m3_catalogs.semantic_instances
    return AssetRegistryPayload(
        locations=[
            RegisteredLocation(location_id=item.location_id, location_type=item.location_type)
            for item in runtime.catalog.locations.locations
        ],
        objects=[
            RegisteredObject(
                object_id=item.object_id,
                object_type=item.object_type,
                location_id=item.location_id,
                capability_tags=item.capability_tags,
                enabled=True,
                interaction_slots=[
                    RegisteredInteractionSlot(
                        slot_index=slot,
                        supported_animation_semantics=item.supported_animation_semantics,
                    )
                    for slot in range(item.slot_count)
                ],
            )
            for item in manifest.objects
        ],
        npc_views=[RegisteredNpcView(agent_id=agent_id) for agent_id in manifest.npc_view_ids],
        mapped_animation_semantics=manifest.required_animation_semantics,
    )


def _envelope(runtime: M3BridgeRuntime, message_id: str) -> dict[str, object]:
    return {
        "protocol_version": M3_PROTOCOL_VERSION,
        "message_id": message_id,
        "sent_at_utc": NOW,
        "world_id": runtime.world_id,
        "state_version": runtime.engine.state.state_version,
        "correlation_id": None,
    }


def _handshake(runtime: M3BridgeRuntime) -> Any:
    session = runtime.open_session()
    hello = ClientHelloV030Message.model_validate(
        {
            **_envelope(runtime, "msg_70000001"),
            "message_type": MessageType.CLIENT_HELLO,
            "payload": ClientHelloV030Payload(
                client_name="unity",
                unity_editor_version="6000.4.2f1",
                supported_protocol_versions=[cast(Any, M3_PROTOCOL_VERSION)],
            ),
        }
    )
    hello_outputs = session.receive_json(hello.model_dump(mode="json"))
    assert hello_outputs[0].message_type is MessageType.SERVER_HELLO
    registry = AssetRegistryV030Message.model_validate(
        {
            **_envelope(runtime, "msg_70000002"),
            "message_type": MessageType.ASSET_REGISTRY,
            "payload": _registry(runtime),
        }
    )
    registry_outputs = session.receive_json(registry.model_dump(mode="json"))
    snapshot = registry_outputs[1]
    assert isinstance(snapshot, WorldSnapshotV030Message)
    ready = ClientReadyV030Message.model_validate(
        {
            **_envelope(runtime, "msg_70000003"),
            "state_version": snapshot.state_version,
            "message_type": MessageType.CLIENT_READY,
            "payload": ClientReadyPayload(registry_message_id=registry.message_id),
        }
    )
    session.receive_json(ready.model_dump(mode="json"))
    return session


def _traveling_joint(runtime: M3BridgeRuntime) -> str:
    for _ in range(120):
        runtime.advance_one_minute()
        traveling = [
            item
            for item in runtime.engine.checkpoint.joint_actions
            if runtime.engine.state.active_actions[item].phase is ActionPhase.TRAVELING
        ]
        if traveling:
            return min(traveling)
    raise AssertionError("targeted M3 fixture did not produce a traveling JointAction")


def test_m3_full_registry_is_exact_and_blocking() -> None:
    runtime = _runtime()
    validator = M3FullAssetRegistryValidator(runtime.catalog, runtime.m3_catalogs, runtime.engine.state)

    accepted = validator.validate(_registry(runtime))
    assert accepted.accepted
    assert any(item.code == "M3_NPC_VIEW_LOCAL_ATTESTATION" for item in accepted.issues)

    raw = _registry(runtime).model_dump(mode="json")
    raw["objects"] = raw["objects"][1:]
    rejected = validator.validate(AssetRegistryPayload.model_validate(raw))
    assert not rejected.accepted
    assert any(item.code == "M3_OBJECT_MISSING" for item in rejected.issues)


def test_m3_handshake_ready_gate_top_k_and_all_agent_deltas() -> None:
    runtime = _runtime()
    session = runtime.open_session()
    with pytest.raises(ValueError, match="client_ready"):
        runtime.advance_one_minute()
    session.disconnect()

    session = _handshake(runtime)
    assert runtime.ready and session.phase is SessionPhase.READY
    output = runtime.advance_one_minute()
    counts = {kind: sum(item.message_type is kind for item in output) for kind in MessageType}
    assert counts[MessageType.ACTION_STARTED] == 10
    assert counts[MessageType.DEBUG_DECISION_TRACE] == 10
    assert counts[MessageType.AGENT_STATE_DELTA] == 10
    for item in output:
        if item.message_type is MessageType.DEBUG_DECISION_TRACE:
            assert len(item.payload.candidates) <= 12
            assert sum(row.resolver_result is not None for row in item.payload.candidates) <= 2
    evidence = runtime.evidence()["sessions"][-1]
    assert evidence["semantic_profile"] == "M3_FULL"
    assert evidence["catalog_protocol_version"] == "0.1.0"
    assert evidence["negotiated_protocol_version"] == "0.3.0"
    assert evidence["snapshot_checkpoint_hash"]
    assert evidence["ready_acknowledged"] is True


def test_m3_reconnect_invalidates_old_generation_and_sends_fresh_full_snapshot() -> None:
    runtime = _runtime()
    old_session = _handshake(runtime)
    runtime.advance_one_minute()
    expected_hash = checkpoint_hash(runtime.engine.export_checkpoint())
    old_version = runtime.engine.state.state_version

    new_session = runtime.open_session()
    with pytest.raises(BridgeProtocolError, match="OBSOLETE_CONNECTION_GENERATION"):
        old_session.receive_json({})
    assert checkpoint_hash(runtime.engine.export_checkpoint()) == expected_hash

    hello = ClientHelloV030Message.model_validate(
        {
            **_envelope(runtime, "msg_71000001"),
            "message_type": MessageType.CLIENT_HELLO,
            "payload": ClientHelloV030Payload(
                client_name="unity",
                unity_editor_version="6000.4.2f1",
                supported_protocol_versions=[cast(Any, M3_PROTOCOL_VERSION)],
            ),
        }
    )
    new_session.receive_json(hello.model_dump(mode="json"))
    registry = AssetRegistryV030Message.model_validate(
        {
            **_envelope(runtime, "msg_71000002"),
            "message_type": MessageType.ASSET_REGISTRY,
            "payload": _registry(runtime),
        }
    )
    outputs = new_session.receive_json(registry.model_dump(mode="json"))
    snapshot = outputs[1]
    assert isinstance(snapshot, WorldSnapshotV030Message)
    assert snapshot.state_version == old_version
    assert {item.action_id for item in snapshot.payload.active_presentations} == set(
        snapshot.payload.world.active_actions
    )
    assert not runtime.ready


def test_m3_joint_cancellation_is_one_transaction_and_releases_everything() -> None:
    runtime = _runtime(social_fixture=True)
    session = _handshake(runtime)
    action_id = _traveling_joint(runtime)
    active = runtime.engine.export_checkpoint()
    participants = list(active.action_runtimes[action_id].participant_ids)
    reservation_ids = set(active.action_runtimes[action_id].reservation_ids)
    report = MovementCancelledV030Message.model_validate(
        {
            **_envelope(runtime, "msg_72000001"),
            "correlation_id": action_id,
            "message_type": MessageType.MOVEMENT_CANCELLED,
            "payload": MovementCancelledPayload(
                action_id=action_id,
                agent_id=participants[0],
                reason=MovementCancellationReason.NAVIGATION_STOPPED,
            ),
        }
    )
    before_version = runtime.engine.state.state_version
    outputs = session.receive_json(report.model_dump(mode="json"))
    after_hash = checkpoint_hash(runtime.engine.export_checkpoint())

    assert runtime.engine.state.state_version == before_version + 1
    assert action_id not in runtime.engine.state.active_actions
    assert all(runtime.engine.state.agents[item].current_action_id is None for item in participants)
    assert not reservation_ids.intersection(runtime.engine.checkpoint.reservations)
    assert any(item.message_type is MessageType.ACTION_CANCELLED for item in outputs)
    cleared_agents = {
        item.payload.agent_id
        for item in outputs
        if item.message_type is MessageType.AGENT_STATE_DELTA
        and "current_action_id" in item.payload.model_fields_set
        and item.payload.current_action_id is None
    }
    assert cleared_agents == set(participants)
    assert session.receive_json(report.model_dump(mode="json")) == ()
    assert checkpoint_hash(runtime.engine.export_checkpoint()) == after_hash
    evidence = runtime.authority_input_evidence[-1]
    assert evidence["authority_mutation_count"] == 1
    assert evidence["authority_transaction_count"] == 1


def test_m3_joint_arrival_waits_for_every_participant() -> None:
    runtime = _runtime(social_fixture=True)
    session = _handshake(runtime)
    action_id = _traveling_joint(runtime)
    runtime_record = runtime.engine.checkpoint.action_runtimes[action_id]
    participants = list(runtime_record.participant_ids)

    for index, agent_id in enumerate(participants):
        binding = next(
            (
                item
                for item in runtime.engine.checkpoint.reservations.values()
                if item.owner_action_id == action_id
                and item.kind == "OBJECT_SLOT"
                and item.participant_agent_id == agent_id
            ),
            None,
        )
        report = MovementArrivedV030Message.model_validate(
            {
                **_envelope(runtime, f"msg_7300000{index + 1}"),
                "correlation_id": action_id,
                "message_type": MessageType.MOVEMENT_ARRIVED,
                "payload": MovementArrivedPayload(
                    action_id=action_id,
                    agent_id=agent_id,
                    object_id=None if binding is None else binding.object_id,
                    slot_index=None if binding is None else binding.slot_index,
                ),
            }
        )
        session.receive_json(report.model_dump(mode="json"))
        phase = runtime.engine.state.active_actions[action_id].phase
        if index < len(participants) - 1:
            assert phase is ActionPhase.TRAVELING
        else:
            assert phase in {ActionPhase.ALIGNING, ActionPhase.PERFORMING}


def test_m3_joint_failure_is_atomic_and_duplicate_is_noop() -> None:
    runtime = _runtime(social_fixture=True)
    session = _handshake(runtime)
    action_id = _traveling_joint(runtime)
    participants = list(runtime.engine.checkpoint.action_runtimes[action_id].participant_ids)
    report = MovementFailedV030Message.model_validate(
        {
            **_envelope(runtime, "msg_74000001"),
            "correlation_id": action_id,
            "message_type": MessageType.MOVEMENT_FAILED,
            "payload": MovementFailedPayload(
                action_id=action_id,
                agent_id=participants[-1],
                reason=MovementFailureReason.NO_PATH,
            ),
        }
    )
    outputs = session.receive_json(report.model_dump(mode="json"))
    after = checkpoint_hash(runtime.engine.export_checkpoint())
    assert action_id not in runtime.engine.state.active_actions
    assert all(runtime.engine.state.agents[item].current_action_id is None for item in participants)
    assert any(
        item.message_type is MessageType.ACTION_PHASE_CHANGED and item.payload.phase is ActionPhase.FAILED
        for item in outputs
    )
    assert session.receive_json(report.model_dump(mode="json")) == ()
    assert checkpoint_hash(runtime.engine.export_checkpoint()) == after


def test_m3_household_delta_is_emitted_from_real_home_meal_settlement() -> None:
    runtime = _scoped_runtime(
        frozenset({BehaviorId.IDLE, BehaviorId.EAT_AT_HOME}),
        NeedValues(hunger=0.0, energy=0.8, hygiene=0.8, fun=0.8, social=0.8),
    )
    _handshake(runtime)
    initial_food = runtime.engine.state.households["household_a"].food_units
    household_delta = None
    for _ in range(60):
        output = runtime.advance_one_minute()
        household_delta = next(
            (item for item in output if item.message_type is MessageType.HOUSEHOLD_STATE_DELTA),
            None,
        )
        if household_delta is not None:
            break
    assert household_delta is not None
    assert household_delta.payload.household_id == "household_a"
    assert household_delta.payload.food_units == initial_food - 1
    assert household_delta.payload.field_mask == ["food_units"]
    household_wire = json.loads(serialize_outbound_message(household_delta))
    assert set(household_wire["payload"]) == {"household_id", "field_mask", "food_units"}
    assert "money" not in household_wire["payload"]


def test_m3_agent_delta_wire_keys_exactly_follow_field_mask_and_preserve_explicit_null() -> None:
    runtime = _runtime()
    ordinary = AgentStateDeltaV030Message(
        protocol_version=cast(Any, M3_PROTOCOL_VERSION),
        message_id="msg_76000001",
        message_type=MessageType.AGENT_STATE_DELTA,
        sent_at_utc=NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=None,
        payload=AgentStateDeltaV030Payload(
            agent_id="npc_01",
            field_mask=[AgentDeltaField.CURRENT_LOCATION_ID],
            current_location_id="home_a",
        ),
    )
    ordinary_wire = json.loads(serialize_outbound_message(ordinary))
    assert set(ordinary_wire["payload"]) == {"agent_id", "field_mask", "current_location_id"}
    assert set(ordinary_wire["payload"]) - {"agent_id", "field_mask"} == set(ordinary_wire["payload"]["field_mask"])

    explicit_clear = AgentStateDeltaV030Message(
        protocol_version=cast(Any, M3_PROTOCOL_VERSION),
        message_id="msg_76000002",
        message_type=MessageType.AGENT_STATE_DELTA,
        sent_at_utc=NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=None,
        payload=AgentStateDeltaV030Payload(
            agent_id="npc_01",
            field_mask=[AgentDeltaField.CURRENT_ACTION_ID],
            current_action_id=None,
        ),
    )
    clear_wire = json.loads(serialize_outbound_message(explicit_clear))
    assert set(clear_wire["payload"]) == {"agent_id", "field_mask", "current_action_id"}
    assert clear_wire["payload"]["current_action_id"] is None


def test_m3_outbound_serializer_keeps_full_non_delta_envelope_and_snapshot_defaults() -> None:
    runtime = _runtime()
    snapshot = runtime.snapshot_message()
    wire = json.loads(serialize_outbound_message(snapshot))

    assert set(wire) == {
        "protocol_version",
        "message_id",
        "message_type",
        "sent_at_utc",
        "world_id",
        "state_version",
        "correlation_id",
        "payload",
    }
    assert set(wire["payload"]) == {"world", "active_presentations"}
    assert set(wire["payload"]["world"]) == set(snapshot.payload.world.model_dump(mode="json", exclude_none=False))
    assert "active_actions" in wire["payload"]["world"]
    assert wire["payload"]["active_presentations"] == []


def test_m3_social_resolution_emits_directed_relationship_and_dialogue_deltas() -> None:
    runtime = _scoped_runtime(
        frozenset({BehaviorId.IDLE, BehaviorId.COMPLIMENT}),
        NeedValues(hunger=0.5, energy=0.7, hygiene=0.7, fun=0.0, social=0.0),
    )
    _handshake(runtime)
    message_types: set[MessageType] = set()
    relationship_sources: set[tuple[str, str]] = set()
    for _ in range(30):
        output = runtime.advance_one_minute()
        message_types.update(item.message_type for item in output)
        relationship_sources.update(
            (item.payload.source_agent_id, item.payload.target_agent_id)
            for item in output
            if item.message_type is MessageType.RELATIONSHIP_DELTA
        )
        if MessageType.DIALOGUE_LINE_READY in message_types:
            break
    assert MessageType.RELATIONSHIP_DELTA in message_types
    assert MessageType.DIALOGUE_LINE_READY in message_types
    assert relationship_sources == {("npc_02", "npc_01")}


def test_real_m3_loopback_websocket_handshake() -> None:
    async def scenario() -> None:
        runtime = _runtime()
        server = M3BridgeWebSocketServer(runtime, port=0, auto_advance=False)
        async with server.running():
            assert server.bound_port is not None
            async with connect(f"ws://127.0.0.1:{server.bound_port}/town") as websocket:
                hello = ClientHelloV030Message.model_validate(
                    {
                        **_envelope(runtime, "msg_75000001"),
                        "message_type": MessageType.CLIENT_HELLO,
                        "payload": ClientHelloV030Payload(
                            client_name="unity",
                            unity_editor_version="6000.4.2f1",
                            supported_protocol_versions=[cast(Any, M3_PROTOCOL_VERSION)],
                        ),
                    }
                )
                await websocket.send(hello.model_dump_json())
                assert json.loads(await websocket.recv())["message_type"] == "server_hello"
                registry = AssetRegistryV030Message.model_validate(
                    {
                        **_envelope(runtime, "msg_75000002"),
                        "message_type": MessageType.ASSET_REGISTRY,
                        "payload": _registry(runtime),
                    }
                )
                await websocket.send(registry.model_dump_json())
                assert json.loads(await websocket.recv())["payload"]["accepted"] is True
                snapshot = json.loads(await websocket.recv())
                assert snapshot["payload"]["active_presentations"] == []
                ready = ClientReadyV030Message.model_validate(
                    {
                        **_envelope(runtime, "msg_75000003"),
                        "state_version": snapshot["state_version"],
                        "message_type": MessageType.CLIENT_READY,
                        "payload": ClientReadyPayload(registry_message_id=registry.message_id),
                    }
                )
                await websocket.send(ready.model_dump_json())
                assert json.loads(await websocket.recv())["message_type"] == "simulation_clock_updated"
                assert runtime.ready

    asyncio.run(scenario())
