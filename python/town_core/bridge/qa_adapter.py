"""Produce external M2 authority evidence through the production Bridge runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from town_core.bridge.runtime import BridgeRuntime
from town_core.bridge.session import BridgeProtocolError, BridgeSession
from town_core.catalogs import load_catalog
from town_core.domain.enums import (
    PROTOCOL_VERSION,
    ActionPhase,
    AnimationSemantic,
    MessageType,
    MovementCancellationReason,
    ObjectType,
)
from town_core.domain.protocol_models import (
    ActionCancelledMessage,
    ActionCancelledPayload,
    AssetRegistryMessage,
    AssetRegistryPayload,
    ClientHelloMessage,
    ClientHelloPayload,
    ClientReadyMessage,
    ClientReadyPayload,
    MovementCancelledMessage,
    MovementCancelledPayload,
    ProtocolMessage,
    RegisteredInteractionSlot,
    RegisteredLocation,
    RegisteredNpcView,
    RegisteredObject,
    WorldSnapshotMessage,
)
from town_core.simulation.clock import RuntimeMode
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state, state_hash

EVIDENCE_SCHEMA = "stwm.bridge.m2-authority-evidence/v1"
TRANSCRIPT_SCHEMA = "stwm.bridge.m2-authority-transcript/v1"
PROJECT_NAME = "Small Town World Model（STWM）"
EVIDENCE_FILENAME = "m2-authority-evidence.json"
TRANSCRIPT_FILENAME = "bridge-authority-transcript.jsonl"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXED_SENT_AT_UTC = datetime(2026, 8, 2, tzinfo=UTC)
_MACHINE_PATH_MARKERS = ("/Users/", "/home/", ":\\Users\\")
_SECRET_MARKERS = ("authorization:", "bearer ", "api_key", "api-key", "sk-")


def _authority_point(runtime: BridgeRuntime) -> dict[str, Any]:
    state = runtime.engine.state
    return {
        "state_hash": state_hash(state),
        "state_version": state.state_version,
        "game_minute": state.game_minute,
    }


def _mutation_count(before: Mapping[str, Any], after: Mapping[str, Any]) -> int:
    return int(before["state_hash"] != after["state_hash"])


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    connection_generation: int
    before: dict[str, Any]
    after: dict[str, Any]
    authority_transaction_count: int
    outcome: str
    error_code: str | None
    transcript_sequences: tuple[int, ...]
    output_message_types: tuple[str, ...]

    @property
    def authority_mutation_count(self) -> int:
        return _mutation_count(self.before, self.after)

    def as_document(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "connection_generation": self.connection_generation,
            "before": self.before,
            "after": self.after,
            "authority_mutation_count": self.authority_mutation_count,
            "authority_transaction_count": self.authority_transaction_count,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "transcript_sequences": list(self.transcript_sequences),
        }


class AuthorityTranscript:
    """Append-only in-memory transcript written once outside the repository."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(
        self,
        *,
        event_type: str,
        probe_id: str,
        connection_generation: int,
        direction: str,
        message_id: str | None,
        message_type: str | None,
        state_version: int,
        trigger_sequence: int | None,
        authority_before: Mapping[str, Any],
        authority_after: Mapping[str, Any],
        authority_mutation_count: int,
        authority_transaction_count: int,
        outcome: str,
        error_code: str | None,
        envelope: Mapping[str, Any] | None,
    ) -> int:
        sequence = len(self.records) + 1
        self.records.append(
            {
                "schema": TRANSCRIPT_SCHEMA,
                "sequence": sequence,
                "event_type": event_type,
                "probe_id": probe_id,
                "connection_generation": connection_generation,
                "direction": direction,
                "message_id": message_id,
                "message_type": message_type,
                "state_version": state_version,
                "trigger_sequence": trigger_sequence,
                "authority_before": dict(authority_before),
                "authority_after": dict(authority_after),
                "authority_mutation_count": authority_mutation_count,
                "authority_transaction_count": authority_transaction_count,
                "outcome": outcome,
                "error_code": error_code,
                "envelope": dict(envelope) if envelope is not None else None,
            }
        )
        return sequence

    def render(self) -> str:
        return "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
            for record in self.records
        )


def _message_document(message: ProtocolMessage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(message, Mapping):
        return dict(message)
    return cast(dict[str, Any], message.model_dump(mode="json", exclude_none=False))


def _message_type(document: Mapping[str, Any]) -> str | None:
    value = document.get("message_type")
    return value if isinstance(value, str) else None


def _message_id(document: Mapping[str, Any]) -> str | None:
    value = document.get("message_id")
    return value if isinstance(value, str) else None


def _message_state_version(document: Mapping[str, Any], fallback: int) -> int:
    value = document.get("state_version")
    return value if isinstance(value, int) and value >= 0 else fallback


def _exchange(
    runtime: BridgeRuntime,
    session: BridgeSession,
    transcript: AuthorityTranscript,
    message: ProtocolMessage | Mapping[str, Any],
    *,
    probe_id: str,
) -> ProbeResult:
    document = _message_document(message)
    before = _authority_point(runtime)
    authority_input_cursor = len(runtime.authority_input_evidence)
    outputs: tuple[ProtocolMessage, ...] = ()
    error_code: str | None = None
    try:
        outputs = session.receive_json(document)
    except BridgeProtocolError as exc:
        error_code = exc.code
    after = _authority_point(runtime)
    new_authority_inputs = runtime.authority_input_evidence[authority_input_cursor:]
    transaction_count = sum(int(item["authority_transaction_count"]) for item in new_authority_inputs)
    if error_code is not None:
        outcome = "REJECTED"
    elif new_authority_inputs and any(not bool(item["accepted"]) for item in new_authority_inputs):
        outcome = "DIAGNOSTIC_RESYNC"
    elif not outputs and before == after:
        outcome = "IDEMPOTENT_NOOP"
    else:
        outcome = "ACCEPTED"
    input_sequence = transcript.append(
        event_type="unity_message_received",
        probe_id=probe_id,
        connection_generation=session.generation,
        direction="unity_to_python",
        message_id=_message_id(document),
        message_type=_message_type(document),
        state_version=_message_state_version(document, int(before["state_version"])),
        trigger_sequence=None,
        authority_before=before,
        authority_after=after,
        authority_mutation_count=_mutation_count(before, after),
        authority_transaction_count=transaction_count,
        outcome=outcome,
        error_code=error_code,
        envelope=document,
    )
    sequences = [input_sequence]
    output_types: list[str] = []
    for output in outputs:
        output_document = _message_document(output)
        output_type = _message_type(output_document)
        if output_type is not None:
            output_types.append(output_type)
        sequences.append(
            transcript.append(
                event_type="python_message_emitted",
                probe_id=probe_id,
                connection_generation=session.generation,
                direction="python_to_unity",
                message_id=_message_id(output_document),
                message_type=output_type,
                state_version=_message_state_version(output_document, int(after["state_version"])),
                trigger_sequence=input_sequence,
                authority_before=after,
                authority_after=after,
                authority_mutation_count=0,
                authority_transaction_count=0,
                outcome="EMITTED",
                error_code=None,
                envelope=output_document,
            )
        )
    return ProbeResult(
        probe_id=probe_id,
        connection_generation=session.generation,
        before=before,
        after=after,
        authority_transaction_count=transaction_count,
        outcome=outcome,
        error_code=error_code,
        transcript_sequences=tuple(sequences),
        output_message_types=tuple(output_types),
    )


def _advance_probe(
    runtime: BridgeRuntime,
    transcript: AuthorityTranscript,
    *,
    probe_id: str,
) -> ProbeResult:
    before = _authority_point(runtime)
    outputs: tuple[ProtocolMessage, ...] = ()
    error_code: str | None = None
    try:
        outputs = runtime.advance_one_minute()
    except ValueError as exc:
        error_code = "CLIENT_READY_GATE" if "client_ready" in str(exc) else type(exc).__name__
    after = _authority_point(runtime)
    transaction_count = max(0, int(after["state_version"]) - int(before["state_version"]))
    outcome = "GATED" if error_code is not None else "COMMITTED"
    probe_sequence = transcript.append(
        event_type="authority_probe_evaluated",
        probe_id=probe_id,
        connection_generation=runtime.generation,
        direction="adapter_to_authority",
        message_id=None,
        message_type=None,
        state_version=int(before["state_version"]),
        trigger_sequence=None,
        authority_before=before,
        authority_after=after,
        authority_mutation_count=_mutation_count(before, after),
        authority_transaction_count=transaction_count,
        outcome=outcome,
        error_code=error_code,
        envelope=None,
    )
    sequences = [probe_sequence]
    output_types: list[str] = []
    for output in outputs:
        output_document = _message_document(output)
        output_type = _message_type(output_document)
        if output_type is not None:
            output_types.append(output_type)
        sequences.append(
            transcript.append(
                event_type="python_message_emitted",
                probe_id=probe_id,
                connection_generation=runtime.generation,
                direction="python_to_unity",
                message_id=_message_id(output_document),
                message_type=output_type,
                state_version=_message_state_version(output_document, int(after["state_version"])),
                trigger_sequence=probe_sequence,
                authority_before=after,
                authority_after=after,
                authority_mutation_count=0,
                authority_transaction_count=0,
                outcome="EMITTED",
                error_code=None,
                envelope=output_document,
            )
        )
    return ProbeResult(
        probe_id=probe_id,
        connection_generation=runtime.generation,
        before=before,
        after=after,
        authority_transaction_count=transaction_count,
        outcome=outcome,
        error_code=error_code,
        transcript_sequences=tuple(sequences),
        output_message_types=tuple(output_types),
    )


def _client_hello(runtime: BridgeRuntime, message_id: str) -> ClientHelloMessage:
    return ClientHelloMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.CLIENT_HELLO,
        sent_at_utc=FIXED_SENT_AT_UTC,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=None,
        payload=ClientHelloPayload(
            client_name="unity",
            unity_editor_version="6000.4.2f1",
            supported_protocol_versions=[cast(Any, PROTOCOL_VERSION), "0.1.0"],
        ),
    )


def _registry_probe_payload(runtime: BridgeRuntime) -> AssetRegistryPayload:
    state = runtime.engine.state
    agent = state.agents[runtime.engine.active_agent_id]
    animation_by_type = {
        ObjectType.BED: AnimationSemantic.SLEEP,
        ObjectType.FRIDGE: AnimationSemantic.EAT,
        ObjectType.DINING_SEAT: AnimationSemantic.EAT,
        ObjectType.WORKSTATION: AnimationSemantic.WORK_STANDING,
    }
    required_objects = [
        obj
        for obj in state.objects.values()
        if (
            obj.metadata.get("assigned_agent_id") == agent.agent_id
            and obj.object_type in {ObjectType.BED, ObjectType.DINING_SEAT, ObjectType.WORKSTATION}
        )
        or (obj.object_type is ObjectType.FRIDGE and obj.location_id == agent.home_location_id)
    ]
    if {obj.object_type for obj in required_objects} != set(animation_by_type):
        raise RuntimeError("authority state does not expose the complete ADR-0009 M2 registry probe profile")
    registered_objects = [
        RegisteredObject(
            object_id=obj.object_id,
            object_type=obj.object_type,
            location_id=obj.location_id,
            capability_tags=obj.capability_tags,
            enabled=obj.enabled,
            interaction_slots=[
                RegisteredInteractionSlot(
                    slot_index=slot_index,
                    supported_animation_semantics=[animation_by_type[obj.object_type]],
                )
                for slot_index in range(obj.slot_count)
            ],
        )
        for obj in sorted(required_objects, key=lambda item: item.object_id)
    ]
    location_ids = (agent.home_location_id, agent.assigned_work_location_id)
    return AssetRegistryPayload(
        locations=[
            RegisteredLocation(location_id=location_id, location_type=state.locations[location_id].location_type)
            for location_id in location_ids
        ],
        objects=registered_objects,
        npc_views=[RegisteredNpcView(agent_id=agent.agent_id)],
        mapped_animation_semantics=[
            AnimationSemantic.IDLE,
            AnimationSemantic.SLEEP,
            AnimationSemantic.EAT,
            AnimationSemantic.WORK_STANDING,
        ],
    )


def _asset_registry(runtime: BridgeRuntime, message_id: str, correlation_id: str) -> AssetRegistryMessage:
    return AssetRegistryMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.ASSET_REGISTRY,
        sent_at_utc=FIXED_SENT_AT_UTC,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=correlation_id,
        payload=_registry_probe_payload(runtime),
    )


def _client_ready(
    runtime: BridgeRuntime,
    *,
    message_id: str,
    registry_message_id: str,
    snapshot_state_version: int,
) -> ClientReadyMessage:
    return ClientReadyMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.CLIENT_READY,
        sent_at_utc=FIXED_SENT_AT_UTC,
        world_id=runtime.world_id,
        state_version=snapshot_state_version,
        correlation_id=registry_message_id,
        payload=ClientReadyPayload(registry_message_id=registry_message_id),
    )


def _begin_handshake(
    runtime: BridgeRuntime,
    session: BridgeSession,
    transcript: AuthorityTranscript,
    *,
    message_prefix: int,
) -> tuple[dict[str, Any], WorldSnapshotMessage]:
    hello_id = f"msg_{message_prefix + 1}"
    registry_id = f"msg_{message_prefix + 2}"
    hello = _exchange(
        runtime, session, transcript, _client_hello(runtime, hello_id), probe_id=f"g{session.generation}_hello"
    )
    registry = _exchange(
        runtime,
        session,
        transcript,
        _asset_registry(runtime, registry_id, hello_id),
        probe_id=f"g{session.generation}_registry",
    )
    hello_outputs = _protocol_outputs_for_sequences(transcript, hello.transcript_sequences)
    server_hello_id = next(
        record.message_id for record in hello_outputs if record.message_type is MessageType.SERVER_HELLO
    )
    registry_outputs = _protocol_outputs_for_sequences(transcript, registry.transcript_sequences)
    snapshot_record = next(record for record in registry_outputs if isinstance(record, WorldSnapshotMessage))
    registry_result_id = next(
        record.message_id for record in registry_outputs if record.message_type is MessageType.ASSET_REGISTRY_RESULT
    )
    snapshot_point = {
        "state_hash": state_hash(snapshot_record.payload.world),
        "state_version": snapshot_record.state_version,
        "game_minute": snapshot_record.payload.world.game_minute,
    }
    observation = {
        "generation": session.generation,
        "catalog_protocol_version": runtime.catalog.world.protocol_version,
        "negotiated_protocol_version": session.negotiated_protocol_version,
        "hello_message_id": hello_id,
        "server_hello_message_id": server_hello_id,
        "registry_message_id": registry_id,
        "registry_result_message_id": registry_result_id,
        "snapshot_message_id": snapshot_record.message_id,
        "snapshot": snapshot_point,
        "ready_message_id": None,
        "ready_before_ack": runtime.ready,
        "ready_after_ack": False,
        "last_client_applied_state_version": session.last_client_state_version,
        "handshake_message_types": [
            MessageType.CLIENT_HELLO.value,
            MessageType.SERVER_HELLO.value,
            MessageType.ASSET_REGISTRY.value,
            MessageType.ASSET_REGISTRY_RESULT.value,
            MessageType.WORLD_SNAPSHOT.value,
        ],
        "message_ids": sorted(
            {
                hello_id,
                registry_id,
                *(item.message_id for item in registry_outputs),
                *(item.message_id for item in hello_outputs),
            }
        ),
    }
    return observation, snapshot_record


def _protocol_outputs_for_sequences(
    transcript: AuthorityTranscript,
    sequences: Sequence[int],
) -> tuple[ProtocolMessage, ...]:
    from pydantic import TypeAdapter

    from town_core.domain.protocol_models import ProtocolMessage as ProtocolMessageUnion

    adapter: TypeAdapter[ProtocolMessageUnion] = TypeAdapter(ProtocolMessageUnion)
    outputs: list[ProtocolMessage] = []
    for sequence in sequences:
        record = transcript.records[sequence - 1]
        if record["event_type"] != "python_message_emitted":
            continue
        outputs.append(adapter.validate_python(record["envelope"]))
    return tuple(outputs)


def _finish_handshake(
    runtime: BridgeRuntime,
    session: BridgeSession,
    transcript: AuthorityTranscript,
    observation: dict[str, Any],
    snapshot: WorldSnapshotMessage,
    *,
    message_prefix: int,
) -> ProbeResult:
    ready_id = f"msg_{message_prefix + 3}"
    ready = _exchange(
        runtime,
        session,
        transcript,
        _client_ready(
            runtime,
            message_id=ready_id,
            registry_message_id=cast(str, observation["registry_message_id"]),
            snapshot_state_version=snapshot.state_version,
        ),
        probe_id=f"g{session.generation}_ready",
    )
    observation["ready_message_id"] = ready_id
    observation["ready_after_ack"] = runtime.ready
    observation["last_client_applied_state_version"] = session.last_client_state_version
    cast(list[str], observation["handshake_message_types"]).append(MessageType.CLIENT_READY.value)
    cast(list[str], observation["message_ids"]).append(ready_id)
    cast(list[str], observation["message_ids"]).sort()
    return ready


def _advance_until_traveling(
    runtime: BridgeRuntime,
    transcript: AuthorityTranscript,
    *,
    max_minutes: int = 720,
) -> tuple[str, int]:
    for elapsed in range(1, max_minutes + 1):
        _advance_probe(runtime, transcript, probe_id=f"advance_until_traveling_{elapsed:04d}")
        agent = runtime.engine.state.agents[runtime.engine.active_agent_id]
        if agent.current_action_id is None:
            continue
        action = runtime.engine.state.active_actions[agent.current_action_id]
        if action.phase is ActionPhase.TRAVELING:
            return action.action_id, elapsed
    raise RuntimeError(f"no traveling M2 action was created within {max_minutes} game minutes")


def _cancel_message(
    runtime: BridgeRuntime,
    *,
    action_id: str,
    message_id: str,
    state_version: int,
    reason: MovementCancellationReason = MovementCancellationReason.NAVIGATION_STOPPED,
) -> MovementCancelledMessage:
    return MovementCancelledMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.MOVEMENT_CANCELLED,
        sent_at_utc=FIXED_SENT_AT_UTC,
        world_id=runtime.world_id,
        state_version=state_version,
        correlation_id=action_id,
        payload=MovementCancelledPayload(action_id=action_id, agent_id=runtime.engine.active_agent_id, reason=reason),
    )


def _require_probe(probe: ProbeResult, *, outcome: str, mutation_count: int, transaction_count: int) -> None:
    if (
        probe.outcome != outcome
        or probe.authority_mutation_count != mutation_count
        or probe.authority_transaction_count != transaction_count
    ):
        raise RuntimeError(
            f"probe {probe.probe_id} expected outcome={outcome}/mutation={mutation_count}/txn={transaction_count}, "
            f"observed {probe.outcome}/{probe.authority_mutation_count}/{probe.authority_transaction_count}"
        )


def _redaction_check(text: str, label: str) -> None:
    lowered = text.lower()
    for marker in _MACHINE_PATH_MARKERS:
        if marker.lower() in lowered:
            raise ValueError(f"{label} contains an unredacted machine-local path")
    for marker in _SECRET_MARKERS:
        if marker in lowered:
            raise ValueError(f"{label} contains a sensitive marker")


def _write_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def _prepare_output_root(output_root: Path) -> Path:
    resolved = output_root.resolve()
    if resolved == resolved.parent:
        raise ValueError("output root must be a dedicated directory, not a filesystem root")
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("M2 authority evidence output must remain outside the repository")
    if resolved.exists() and any(resolved.iterdir()):
        raise FileExistsError(f"M2 authority evidence output directory is not empty: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def run_authority_evidence(
    *,
    config_root: Path,
    output_root: Path,
    active_agent_id: str = "npc_01",
    seed: int = 12345,
) -> dict[str, Any]:
    """Run deterministic real Bridge sessions and write external authority evidence."""

    destination = _prepare_output_root(output_root)
    catalog = load_catalog(config_root)
    initial_state = build_initial_world_state(catalog, seed=seed, active_agent_id=active_agent_id)
    engine = SimulationEngine(
        catalog,
        initial_state,
        active_agent_id=active_agent_id,
        runtime_mode=RuntimeMode.UNITY_LIVE,
    )
    runtime = BridgeRuntime(catalog, engine, now=lambda: FIXED_SENT_AT_UTC)
    transcript = AuthorityTranscript()
    initial_authority = _authority_point(runtime)

    old_session = runtime.open_session()
    old_generation, old_snapshot = _begin_handshake(runtime, old_session, transcript, message_prefix=10_000_000)
    _finish_handshake(
        runtime,
        old_session,
        transcript,
        old_generation,
        old_snapshot,
        message_prefix=10_000_000,
    )
    if not runtime.ready:
        raise RuntimeError("generation 1 did not become ready after the production handshake")

    action_id, _ = _advance_until_traveling(runtime, transcript)
    stale_exact_reported_version = runtime.engine.state.state_version
    make_stale = _advance_probe(runtime, transcript, probe_id="make_cancel_report_stale")
    _require_probe(make_stale, outcome="COMMITTED", mutation_count=1, transaction_count=1)
    action = runtime.engine.state.active_actions.get(action_id)
    if action is None or action.phase is not ActionPhase.TRAVELING:
        raise RuntimeError("stale-exact cancellation probe lost the current TRAVELING action")

    wrong_direction = ActionCancelledMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id="msg_10000010",
        message_type=MessageType.ACTION_CANCELLED,
        sent_at_utc=FIXED_SENT_AT_UTC,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=action_id,
        payload=ActionCancelledPayload(action_id=action_id, reason=MovementCancellationReason.NAVIGATION_STOPPED.value),
    )
    direction_reject = _exchange(runtime, old_session, transcript, wrong_direction, probe_id="direction_reject")
    _require_probe(direction_reject, outcome="REJECTED", mutation_count=0, transaction_count=0)

    future_version = _exchange(
        runtime,
        old_session,
        transcript,
        _cancel_message(
            runtime,
            action_id=action_id,
            message_id="msg_10000011",
            state_version=runtime.engine.state.state_version + 1,
        ),
        probe_id="future_version",
    )
    _require_probe(future_version, outcome="REJECTED", mutation_count=0, transaction_count=0)

    cancel_message = _cancel_message(
        runtime,
        action_id=action_id,
        message_id="msg_10000012",
        state_version=stale_exact_reported_version,
    )
    cancel_once = _exchange(
        runtime,
        old_session,
        transcript,
        cancel_message,
        probe_id="stale_exact_current_action",
    )
    _require_probe(cancel_once, outcome="ACCEPTED", mutation_count=1, transaction_count=1)
    if MessageType.ACTION_CANCELLED.value not in cancel_once.output_message_types:
        raise RuntimeError("accepted cancellation did not emit authoritative action_cancelled")

    duplicate = _exchange(
        runtime,
        old_session,
        transcript,
        cancel_message,
        probe_id="duplicate_same_id",
    )
    _require_probe(duplicate, outcome="IDEMPOTENT_NOOP", mutation_count=0, transaction_count=0)

    conflict_message = cancel_message.model_copy(
        update={
            "payload": cancel_message.payload.model_copy(update={"reason": MovementCancellationReason.CLIENT_SHUTDOWN})
        }
    )
    conflict = _exchange(
        runtime,
        old_session,
        transcript,
        conflict_message,
        probe_id="conflicting_same_id",
    )
    _require_probe(conflict, outcome="REJECTED", mutation_count=0, transaction_count=0)

    late_terminal = _exchange(
        runtime,
        old_session,
        transcript,
        _cancel_message(
            runtime,
            action_id=action_id,
            message_id="msg_10000013",
            state_version=runtime.engine.state.state_version,
        ),
        probe_id="late_terminal",
    )
    _require_probe(late_terminal, outcome="DIAGNOSTIC_RESYNC", mutation_count=0, transaction_count=0)
    old_generation["last_client_applied_state_version"] = old_session.last_client_state_version

    new_session = runtime.open_session()
    obsolete_generation = _exchange(
        runtime,
        old_session,
        transcript,
        _cancel_message(
            runtime,
            action_id=action_id,
            message_id="msg_10000014",
            state_version=runtime.engine.state.state_version,
        ),
        probe_id="obsolete_generation",
    )
    _require_probe(obsolete_generation, outcome="REJECTED", mutation_count=0, transaction_count=0)
    old_session.disconnect()

    new_generation, new_snapshot = _begin_handshake(runtime, new_session, transcript, message_prefix=20_000_000)
    pre_ready_advance = _advance_probe(runtime, transcript, probe_id="pre_ready_advance")
    _require_probe(pre_ready_advance, outcome="GATED", mutation_count=0, transaction_count=0)
    _finish_handshake(
        runtime,
        new_session,
        transcript,
        new_generation,
        new_snapshot,
        message_prefix=20_000_000,
    )
    if not runtime.ready:
        raise RuntimeError("generation 2 did not become ready after the fresh snapshot acknowledgement")

    stale_nonmatching = _exchange(
        runtime,
        new_session,
        transcript,
        _cancel_message(
            runtime,
            action_id=action_id,
            message_id="msg_20000010",
            state_version=stale_exact_reported_version,
        ),
        probe_id="stale_nonmatching_or_terminal",
    )
    _require_probe(stale_nonmatching, outcome="DIAGNOSTIC_RESYNC", mutation_count=0, transaction_count=0)
    post_ready_advance = _advance_probe(runtime, transcript, probe_id="post_ready_advance")
    _require_probe(post_ready_advance, outcome="COMMITTED", mutation_count=1, transaction_count=1)
    new_generation["last_client_applied_state_version"] = new_session.last_client_state_version

    old_types = cast(list[str], old_generation["handshake_message_types"])
    new_types = cast(list[str], new_generation["handshake_message_types"])
    expected_handshake = [
        MessageType.CLIENT_HELLO.value,
        MessageType.SERVER_HELLO.value,
        MessageType.ASSET_REGISTRY.value,
        MessageType.ASSET_REGISTRY_RESULT.value,
        MessageType.WORLD_SNAPSHOT.value,
        MessageType.CLIENT_READY.value,
    ]
    old_message_ids = set(cast(list[str], old_generation["message_ids"]))
    new_message_ids = set(cast(list[str], new_generation["message_ids"]))
    runtime_evidence = runtime.evidence()
    accepted_cancel_inputs = [
        item
        for item in cast(list[dict[str, Any]], runtime_evidence["authority_inputs"])
        if item["action_id"] == action_id and item["accepted"]
    ]
    cancel_transaction_count = sum(int(item["authority_transaction_count"]) for item in accepted_cancel_inputs)
    unity_direct_mutation_count = max(0, cancel_once.authority_mutation_count - cancel_transaction_count)
    full_handshake_repeated = old_types == expected_handshake and new_types == expected_handshake
    fresh_snapshot = cast(dict[str, Any], new_generation["snapshot"])
    last_acknowledged = int(old_generation["last_client_applied_state_version"])
    fresh_snapshot_ok = int(fresh_snapshot["state_version"]) >= last_acknowledged
    new_ids = not old_message_ids.intersection(new_message_ids)
    ready_before_resume = (
        new_generation["ready_before_ack"] is False
        and pre_ready_advance.outcome == "GATED"
        and new_generation["ready_after_ack"] is True
        and post_ready_advance.outcome == "COMMITTED"
    )

    cancellation_observation = {
        "direction": "unity_to_python",
        "correlation_id_equals_action_id": cancel_message.correlation_id == cancel_message.payload.action_id,
        "python_authority_cancel_transaction_count": cancel_transaction_count,
        "unity_direct_authority_mutation_count": unity_direct_mutation_count,
        "duplicate_same_message_id_is_idempotent": duplicate.outcome == "IDEMPOTENT_NOOP",
        "conflicting_same_message_id_rejected_without_mutation": (
            conflict.error_code == "MESSAGE_ID_CONTENT_MISMATCH" and conflict.authority_mutation_count == 0
        ),
        "direction_rejected_without_mutation": (
            direction_reject.error_code == "INVALID_UNITY_TO_PYTHON_ENVELOPE"
            and direction_reject.authority_mutation_count == 0
        ),
        "future_state_version_rejected_without_mutation": (
            future_version.error_code == "FUTURE_STATE_VERSION" and future_version.authority_mutation_count == 0
        ),
        "stale_exact_current_action_processed": (
            stale_exact_reported_version < int(cancel_once.before["state_version"])
            and cancel_once.authority_transaction_count == 1
        ),
        "stale_state_message_authority_mutation_count": stale_nonmatching.authority_mutation_count,
        "late_terminal_message_authority_mutation_count": late_terminal.authority_mutation_count,
        "probes": {
            "direction_reject": direction_reject.as_document(),
            "future_version": future_version.as_document(),
            "stale_exact_current_action": cancel_once.as_document(),
            "duplicate_same_id": duplicate.as_document(),
            "conflicting_same_id": conflict.as_document(),
            "stale_nonmatching_or_terminal": stale_nonmatching.as_document(),
            "late_terminal": late_terminal.as_document(),
        },
        "evidence_refs": {
            "direction": "stale_exact_current_action",
            "correlation_id_equals_action_id": "stale_exact_current_action",
            "python_authority_cancel_transaction_count": "runtime_evidence.authority_inputs",
            "unity_direct_authority_mutation_count": "stale_exact_current_action",
            "duplicate_same_message_id_is_idempotent": "duplicate_same_id",
            "conflicting_same_message_id_rejected_without_mutation": "conflicting_same_id",
            "direction_rejected_without_mutation": "direction_reject",
            "future_state_version_rejected_without_mutation": "future_version",
            "stale_exact_current_action_processed": "stale_exact_current_action",
            "stale_state_message_authority_mutation_count": "stale_nonmatching_or_terminal",
            "late_terminal_message_authority_mutation_count": "late_terminal",
        },
    }
    reconnect_observation = {
        "full_hello_and_registry_repeated": full_handshake_repeated,
        "new_message_ids": new_ids,
        "fresh_snapshot_not_older_than_last_acknowledged_version": fresh_snapshot_ok,
        "new_client_ready_before_resume": ready_before_resume,
        "obsolete_generation_rejected": obsolete_generation.error_code == "OBSOLETE_CONNECTION_GENERATION",
        "late_obsolete_generation_authority_mutation_count": obsolete_generation.authority_mutation_count,
        "stale_state_message_authority_mutation_count": stale_nonmatching.authority_mutation_count,
        "old_generation_last_acknowledged_state_version": last_acknowledged,
        "fresh_snapshot": fresh_snapshot,
        "old_generation": old_generation,
        "new_generation": new_generation,
        "probes": {
            "obsolete_generation": obsolete_generation.as_document(),
            "pre_ready_advance": pre_ready_advance.as_document(),
            "post_ready_advance": post_ready_advance.as_document(),
            "stale_nonmatching_or_terminal": stale_nonmatching.as_document(),
        },
        "evidence_refs": {
            "full_hello_and_registry_repeated": "old_generation,new_generation",
            "new_message_ids": "old_generation.message_ids,new_generation.message_ids",
            "fresh_snapshot_not_older_than_last_acknowledged_version": (
                "old_generation_last_acknowledged_state_version,fresh_snapshot.state_version"
            ),
            "new_client_ready_before_resume": "pre_ready_advance,new_generation,post_ready_advance",
            "obsolete_generation_rejected": "obsolete_generation",
            "late_obsolete_generation_authority_mutation_count": "obsolete_generation",
            "stale_state_message_authority_mutation_count": "stale_nonmatching_or_terminal",
            "old_generation_last_acknowledged_state_version": "old_generation",
        },
    }
    required_cancellation_values = (
        cancellation_observation["correlation_id_equals_action_id"] is True,
        cancellation_observation["python_authority_cancel_transaction_count"] == 1,
        cancellation_observation["unity_direct_authority_mutation_count"] == 0,
        cancellation_observation["duplicate_same_message_id_is_idempotent"] is True,
        cancellation_observation["conflicting_same_message_id_rejected_without_mutation"] is True,
        cancellation_observation["direction_rejected_without_mutation"] is True,
        cancellation_observation["future_state_version_rejected_without_mutation"] is True,
        cancellation_observation["stale_exact_current_action_processed"] is True,
        cancellation_observation["stale_state_message_authority_mutation_count"] == 0,
        cancellation_observation["late_terminal_message_authority_mutation_count"] == 0,
    )
    required_reconnect_values = (
        reconnect_observation["full_hello_and_registry_repeated"] is True,
        reconnect_observation["new_message_ids"] is True,
        reconnect_observation["fresh_snapshot_not_older_than_last_acknowledged_version"] is True,
        reconnect_observation["new_client_ready_before_resume"] is True,
        reconnect_observation["obsolete_generation_rejected"] is True,
        reconnect_observation["late_obsolete_generation_authority_mutation_count"] == 0,
        reconnect_observation["stale_state_message_authority_mutation_count"] == 0,
    )

    transcript_text = transcript.render()
    _redaction_check(transcript_text, TRANSCRIPT_FILENAME)
    transcript_digest = hashlib.sha256(transcript_text.encode("utf-8")).hexdigest()
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "project_name": PROJECT_NAME,
        "scenario": {
            "name": "m2_cancellation_reconnect",
            "active_agent_id": active_agent_id,
            "seed": seed,
        },
        "catalog_protocol_version": catalog.world.protocol_version,
        "negotiated_protocol_version": PROTOCOL_VERSION,
        "passed": all((*required_cancellation_values, *required_reconnect_values)),
        "initial_authority": initial_authority,
        "final_authority": _authority_point(runtime),
        "transcript": {
            "schema": TRANSCRIPT_SCHEMA,
            "relative_path": TRANSCRIPT_FILENAME,
            "record_count": len(transcript.records),
            "sha256": transcript_digest,
        },
        "observations": {
            "cancellation": cancellation_observation,
            "reconnect": reconnect_observation,
        },
        "runtime_evidence": runtime_evidence,
    }
    evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _redaction_check(evidence_text, EVIDENCE_FILENAME)
    if evidence["passed"] is not True:
        raise RuntimeError("M2 authority evidence probes did not all pass")
    _write_exclusive(destination / TRANSCRIPT_FILENAME, transcript_text)
    _write_exclusive(destination / EVIDENCE_FILENAME, evidence_text)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--agent", default="npc_01")
    parser.add_argument("--seed", type=int, default=12345)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = run_authority_evidence(
            config_root=args.config.resolve(),
            output_root=args.output_root,
            active_agent_id=args.agent,
            seed=args.seed,
        )
    except (FileExistsError, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": evidence["schema"],
                "passed": evidence["passed"],
                "evidence": EVIDENCE_FILENAME,
                "transcript": TRANSCRIPT_FILENAME,
                "final_state_hash": evidence["final_authority"]["state_hash"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
