"""Authoritative M2 runtime adapter around the accepted M1 engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING, Any, cast

from town_core.domain.config_models import BehaviorConfig, CatalogBundle
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import (
    PROTOCOL_VERSION,
    ActionPhase,
    AnimationSemantic,
    BehaviorId,
    CapabilityTag,
    MessageType,
    MovementCancellationReason,
    MovementFailureReason,
)
from town_core.domain.protocol_models import (
    ActionCancelledMessage,
    ActionCancelledPayload,
    ActionPhaseChangedMessage,
    ActionPhaseChangedPayload,
    ActionStartedMessage,
    ActionStartedPayload,
    AgentStateDeltaMessage,
    AgentStateDeltaPayload,
    DebugDecisionTraceMessage,
    DebugDecisionTracePayload,
    ProtocolMessage,
    SimulationClockPayload,
    SimulationClockUpdatedMessage,
    WorldEventCreatedMessage,
    WorldEventCreatedPayload,
    WorldSnapshotMessage,
    WorldSnapshotPayload,
)
from town_core.simulation.clock import RuntimeMode, approve_time_scale
from town_core.simulation.engine import AdvanceResult, SimulationEngine
from town_core.simulation.initialization import state_hash

if TYPE_CHECKING:
    from town_core.bridge.session import BridgeSession


class BridgeRuntime:
    """Coordinate connection generations without becoming a second simulator."""

    def __init__(
        self,
        catalog: CatalogBundle,
        engine: SimulationEngine,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if engine.runtime_mode is not RuntimeMode.UNITY_LIVE:
            raise ValueError("BridgeRuntime requires a UNITY_LIVE SimulationEngine")
        self.catalog = catalog
        self.engine = engine
        self._now = now or (lambda: datetime.now(UTC))
        self._message_counter = 0
        self._generation = 0
        self._ready_generation: int | None = None
        self._lock = RLock()
        self.time_scale = 1.0
        self.paused = False
        self.diagnostics: list[dict[str, Any]] = []
        self._presented_action_ids: set[str] = set()
        self.session_evidence: dict[int, dict[str, Any]] = {}
        self.authority_input_evidence: list[dict[str, Any]] = []

    @property
    def world_id(self) -> str:
        return self.engine.state.world_id

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def ready(self) -> bool:
        return self._ready_generation == self._generation

    def open_session(self) -> BridgeSession:
        from town_core.bridge.session import BridgeSession

        with self._lock:
            self._generation += 1
            self._ready_generation = None
            self.session_evidence[self._generation] = {
                "generation": self._generation,
                "catalog_protocol_version": self.catalog.world.protocol_version,
                "negotiated_protocol_version": None,
                "registry_message_id": None,
                "snapshot_state_version": None,
                "client_ready_state_version": None,
                "ready_acknowledged": False,
                "disconnected": False,
            }
            return BridgeSession(self, generation=self._generation)

    def is_current_generation(self, generation: int) -> bool:
        return generation == self._generation

    def mark_ready(self, generation: int) -> None:
        if not self.is_current_generation(generation):
            raise ValueError("obsolete connection generation cannot become ready")
        self._ready_generation = generation
        self.session_evidence[generation]["ready_acknowledged"] = True
        self.session_evidence[generation]["client_ready_state_version"] = self.engine.state.state_version

    def disconnect(self, generation: int) -> None:
        if self.is_current_generation(generation):
            self._ready_generation = None
        if generation in self.session_evidence:
            self.session_evidence[generation]["disconnected"] = True

    def record_negotiated_protocol(self, generation: int, version: str) -> None:
        self.session_evidence[generation]["negotiated_protocol_version"] = version

    def record_snapshot_evidence(self, generation: int, registry_message_id: str, state_version: int) -> None:
        evidence = self.session_evidence[generation]
        evidence["registry_message_id"] = registry_message_id
        evidence["snapshot_state_version"] = state_version

    def evidence(self) -> dict[str, Any]:
        return {
            "schema": "stwm.bridge.m2-session-evidence/v1",
            "project_name": "Small Town World Model（STWM）",
            "active_generation": self._generation,
            "sessions": [dict(self.session_evidence[key]) for key in sorted(self.session_evidence)],
            "authority_inputs": [dict(item) for item in self.authority_input_evidence],
        }

    def next_message_id(self) -> str:
        with self._lock:
            self._message_counter += 1
            return f"msg_{self._message_counter:08d}"

    def snapshot_message(self, *, correlation_id: str | None = None) -> WorldSnapshotMessage:
        state = self.engine.state
        return WorldSnapshotMessage(
            protocol_version=cast(Any, PROTOCOL_VERSION),
            message_id=self.next_message_id(),
            message_type=MessageType.WORLD_SNAPSHOT,
            sent_at_utc=self._now(),
            world_id=state.world_id,
            state_version=state.state_version,
            correlation_id=correlation_id,
            payload=WorldSnapshotPayload(world=state),
        )

    def clock_message(self, *, correlation_id: str | None = None) -> SimulationClockUpdatedMessage:
        state = self.engine.state
        return SimulationClockUpdatedMessage(
            protocol_version=cast(Any, PROTOCOL_VERSION),
            message_id=self.next_message_id(),
            message_type=MessageType.SIMULATION_CLOCK_UPDATED,
            sent_at_utc=self._now(),
            world_id=state.world_id,
            state_version=state.state_version,
            correlation_id=correlation_id,
            payload=SimulationClockPayload(
                game_minute=state.game_minute,
                time_scale=self.time_scale,
                paused=self.paused,
            ),
        )

    def set_time_scale(self, requested: float) -> SimulationClockUpdatedMessage:
        self._require_ready()
        self.time_scale = approve_time_scale(requested, RuntimeMode.UNITY_LIVE)
        self.paused = self.time_scale == 0.0
        return self.clock_message()

    def set_paused(self, paused: bool) -> SimulationClockUpdatedMessage:
        self._require_ready()
        self.paused = paused
        return self.clock_message()

    def advance_one_minute(self) -> tuple[ProtocolMessage, ...]:
        with self._lock:
            self._require_ready()
            if self.paused or self.time_scale == 0.0:
                return ()
            result = self.engine.advance_to(self.engine.state.game_minute + 1)
            return self._messages_for_result(result, include_clock=True)

    def movement_arrived(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        object_id: str | None,
        slot_index: int | None,
    ) -> tuple[ProtocolMessage, ...]:
        with self._lock:
            self._require_current_ready(generation)
            try:
                result = self.engine.report_movement_arrived(
                    action_id=action_id,
                    agent_id=agent_id,
                    expected_state_version=state_version,
                    object_id=object_id,
                    slot_index=slot_index,
                )
            except ValueError as exc:
                return self._diagnose_and_resync("MOVEMENT_ARRIVED_REJECTED", str(exc), action_id)
            return self._messages_for_result(result, include_clock=False)

    def movement_failed(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        reason: MovementFailureReason,
    ) -> tuple[ProtocolMessage, ...]:
        with self._lock:
            self._require_current_ready(generation)
            try:
                result = self.engine.report_movement_failed(
                    action_id=action_id,
                    agent_id=agent_id,
                    expected_state_version=state_version,
                    reason=reason,
                )
            except ValueError as exc:
                return self._diagnose_and_resync("MOVEMENT_FAILED_REJECTED", str(exc), action_id)
            return self._messages_for_result(result, include_clock=False)

    def movement_cancelled(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        reason: MovementCancellationReason,
    ) -> tuple[ProtocolMessage, ...]:
        with self._lock:
            self._require_current_ready(generation)
            before = self._authority_point()
            try:
                result = self.engine.report_movement_cancelled(
                    action_id=action_id,
                    agent_id=agent_id,
                    expected_state_version=state_version,
                    reason=reason,
                )
            except ValueError as exc:
                self._record_cancellation_authority_input(
                    generation=generation,
                    action_id=action_id,
                    agent_id=agent_id,
                    reported_state_version=state_version,
                    reason=reason,
                    accepted=False,
                    before=before,
                    result=None,
                    diagnostic_code="MOVEMENT_CANCELLED_REJECTED",
                )
                return self._diagnose_and_resync("MOVEMENT_CANCELLED_REJECTED", str(exc), action_id)
            self._record_cancellation_authority_input(
                generation=generation,
                action_id=action_id,
                agent_id=agent_id,
                reported_state_version=state_version,
                reason=reason,
                accepted=True,
                before=before,
                result=result,
                diagnostic_code=None,
            )
            return self._messages_for_result(result, include_clock=False)

    def _authority_point(self) -> dict[str, Any]:
        state = self.engine.state
        return {
            "state_hash": state_hash(state),
            "state_version": state.state_version,
            "game_minute": state.game_minute,
        }

    def _record_cancellation_authority_input(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        reported_state_version: int,
        reason: MovementCancellationReason,
        accepted: bool,
        before: dict[str, Any],
        result: AdvanceResult | None,
        diagnostic_code: str | None,
    ) -> None:
        after = self._authority_point()
        transaction_projection = [
            {
                "transaction_id": transaction["transaction_id"],
                "expected_state_version": transaction["expected_state_version"],
                "committed_state_version": transaction["committed_state_version"],
                "input_game_minute": transaction["input_game_minute"],
                "previous_state_hash": transaction["previous_state_hash"],
                "committed_state_hash": transaction["committed_state_hash"],
                "transaction_hash": transaction["transaction_hash"],
                "changes": list(transaction["changes"]),
            }
            for transaction in (() if result is None else result.transactions)
        ]
        self.authority_input_evidence.append(
            {
                "input_kind": MessageType.MOVEMENT_CANCELLED.value,
                "generation": generation,
                "action_id": action_id,
                "agent_id": agent_id,
                "reason": reason.value,
                "reported_state_version": reported_state_version,
                "accepted": accepted,
                "diagnostic_code": diagnostic_code,
                "before": before,
                "after": after,
                "authority_mutation_count": int(before["state_hash"] != after["state_hash"]),
                "authority_transaction_count": len(transaction_projection),
                "transactions": transaction_projection,
            }
        )

    def presentation_completed(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
    ) -> tuple[ProtocolMessage, ...]:
        with self._lock:
            self._require_current_ready(generation)
            if (
                agent_id != self.engine.active_agent_id
                or state_version > self.engine.state.state_version
                or action_id not in self._presented_action_ids
            ):
                return self._diagnose_and_resync(
                    "PRESENTATION_COMPLETED_REJECTED", "presentation context is not authoritative", action_id
                )
            self.diagnostics.append(
                {
                    "code": "PRESENTATION_COMPLETED",
                    "generation": generation,
                    "action_id": action_id,
                    "state_version": self.engine.state.state_version,
                }
            )
            return ()

    def _diagnose_and_resync(self, code: str, detail: str, action_id: str) -> tuple[ProtocolMessage, ...]:
        self.diagnostics.append(
            {
                "code": code,
                "detail": detail,
                "generation": self._generation,
                "action_id": action_id,
                "state_version": self.engine.state.state_version,
            }
        )
        return (self.snapshot_message(correlation_id=action_id),)

    def _messages_for_result(self, result: AdvanceResult, *, include_clock: bool) -> tuple[ProtocolMessage, ...]:
        messages: list[ProtocolMessage] = []
        if include_clock:
            messages.append(self.clock_message())
        for record in result.actions:
            action_id = str(record["action_id"])
            phase = ActionPhase(str(record["phase"]))
            state_version = int(record["state_version"])
            if phase is ActionPhase.CREATED:
                action = self.engine.state.active_actions.get(action_id)
                if action is not None:
                    self._presented_action_ids.add(action_id)
                    behavior = self._behavior(action.behavior_id)
                    destination = action.destination_location_id
                    if destination is None:
                        raise ValueError("M2 action presentation requires a semantic destination")
                    messages.append(
                        ActionStartedMessage(
                            protocol_version=cast(Any, PROTOCOL_VERSION),
                            message_id=self.next_message_id(),
                            message_type=MessageType.ACTION_STARTED,
                            sent_at_utc=self._now(),
                            world_id=self.world_id,
                            state_version=state_version,
                            correlation_id=action_id,
                            payload=ActionStartedPayload(
                                action_id=action_id,
                                agent_ids=action.agent_ids,
                                behavior_id=action.behavior_id,
                                destination_location_id=destination,
                                target_object_ids=action.target_object_ids,
                                animation_semantic=self._animation_semantic(action.behavior_id),
                                prop_semantic=behavior.unity.prop_semantic,
                                planned_duration_minutes=behavior.duration_minutes.base,
                            ),
                        )
                    )
                continue
            if phase is ActionPhase.CANCELLED:
                reason = record.get("failure_reason")
                if not isinstance(reason, str) or not reason:
                    raise ValueError("authority cancellation is missing its typed reason")
                messages.append(
                    ActionCancelledMessage(
                        protocol_version=cast(Any, PROTOCOL_VERSION),
                        message_id=self.next_message_id(),
                        message_type=MessageType.ACTION_CANCELLED,
                        sent_at_utc=self._now(),
                        world_id=self.world_id,
                        state_version=state_version,
                        correlation_id=action_id,
                        payload=ActionCancelledPayload(action_id=action_id, reason=reason),
                    )
                )
                continue
            messages.append(
                ActionPhaseChangedMessage(
                    protocol_version=cast(Any, PROTOCOL_VERSION),
                    message_id=self.next_message_id(),
                    message_type=MessageType.ACTION_PHASE_CHANGED,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=state_version,
                    correlation_id=action_id,
                    payload=ActionPhaseChangedPayload(action_id=action_id, phase=phase),
                )
            )
        agent = self.engine.state.agents[self.engine.active_agent_id]
        messages.append(
            AgentStateDeltaMessage(
                protocol_version=cast(Any, PROTOCOL_VERSION),
                message_id=self.next_message_id(),
                message_type=MessageType.AGENT_STATE_DELTA,
                sent_at_utc=self._now(),
                world_id=self.world_id,
                state_version=self.engine.state.state_version,
                correlation_id=agent.current_action_id,
                payload=AgentStateDeltaPayload(
                    agent_id=agent.agent_id,
                    current_location_id=agent.current_location_id,
                    current_action_id=agent.current_action_id,
                    needs=agent.needs,
                ),
            )
        )
        for event in result.events:
            messages.append(
                WorldEventCreatedMessage(
                    protocol_version=cast(Any, PROTOCOL_VERSION),
                    message_id=self.next_message_id(),
                    message_type=MessageType.WORLD_EVENT_CREATED,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=self.engine.state.state_version,
                    correlation_id=event.source_action_id,
                    payload=WorldEventCreatedPayload(event=event),
                )
            )
        for decision in result.decisions:
            selected = next(
                item
                for item in decision["candidates"]
                if item["candidate"]["candidate_id"] == decision["selected_candidate_id"]
            )
            messages.append(
                DebugDecisionTraceMessage(
                    protocol_version=cast(Any, PROTOCOL_VERSION),
                    message_id=self.next_message_id(),
                    message_type=MessageType.DEBUG_DECISION_TRACE,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=int(decision["committed_state_version"]),
                    correlation_id=str(decision["decision_id"]),
                    payload=DebugDecisionTracePayload(
                        agent_id=str(decision["agent_id"]),
                        selected_candidate_id=str(decision["selected_candidate_id"]),
                        prediction=OutcomePrediction.model_validate(selected["prediction"]),
                        utility_terms={key: float(value) for key, value in selected["utility_terms"].items()},
                    ),
                )
            )
        return tuple(messages)

    def _behavior(self, behavior_id: BehaviorId) -> BehaviorConfig:
        return next(item for item in self.catalog.behaviors.behaviors if item.behavior_id is behavior_id)

    def _animation_semantic(self, behavior_id: BehaviorId) -> AnimationSemantic:
        if behavior_id is BehaviorId.WORK_SHIFT:
            tag = self.engine.state.agents[self.engine.active_agent_id].assigned_workstation_tag
            if tag is CapabilityTag.CAFE_MORNING or tag is CapabilityTag.CAFE_EVENING:
                return AnimationSemantic.WORK_STANDING
            if tag is CapabilityTag.WORKSHOP:
                return AnimationSemantic.WORK_WORKSHOP
            return AnimationSemantic.WORK_DESK
        return self._behavior(behavior_id).unity.animation_semantics[0]

    def _require_ready(self) -> None:
        if not self.ready:
            raise ValueError("simulation is gated until the current connection sends client_ready")

    def _require_current_ready(self, generation: int) -> None:
        if not self.is_current_generation(generation):
            raise ValueError("obsolete connection generation")
        self._require_ready()
