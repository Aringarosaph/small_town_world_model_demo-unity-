"""Protocol 0.3 M3_FULL adapter around the SIM-owned society authority."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING, Any, cast

from town_core.domain.config_models import BehaviorConfig, CatalogBundle
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import (
    M3_PROTOCOL_VERSION,
    ActionParticipantRole,
    ActionPhase,
    AgentDeltaField,
    AnimationSemantic,
    BehaviorId,
    CapabilityTag,
    DecisionTrigger,
    HouseholdDeltaField,
    MessageType,
    MovementCancellationReason,
    MovementFailureReason,
    ProposalResult,
)
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.protocol_models import (
    ActionCancelledPayload,
    ActionCancelledV030Message,
    ActionParticipantV030,
    ActionPhaseChangedPayload,
    ActionPhaseChangedV030Message,
    ActionStartedV030Message,
    ActionStartedV030Payload,
    ActiveActionPresentationV030,
    AgentStateDeltaV030Message,
    AgentStateDeltaV030Payload,
    DebugCandidateTraceV030,
    DebugDecisionTraceV030Message,
    DebugDecisionTraceV030Payload,
    DialogueLineReadyPayload,
    DialogueLineReadyV030Message,
    FacingTargetV030,
    HardPreviewV030,
    HouseholdStateDeltaV030Message,
    HouseholdStateDeltaV030Payload,
    ParticipantObjectBindingV030,
    PythonToUnityMessageV030,
    RelationshipDeltaPayload,
    RelationshipDeltaV030Message,
    SimulationClockPayload,
    SimulationClockUpdatedV030Message,
    WorldEventCreatedPayload,
    WorldEventCreatedV030Message,
    WorldSnapshotV030Message,
    WorldSnapshotV030Payload,
)
from town_core.domain.state_models import RelationshipDelta, RelationshipState
from town_core.simulation.clock import RuntimeMode, approve_time_scale
from town_core.society.checkpoint import checkpoint_hash
from town_core.society.engine import SocietyEngine
from town_core.society.models import ActionRuntimeRecord, AuthorityCheckpoint, SocietyAdvanceResult

if TYPE_CHECKING:
    from town_core.bridge.m3_session import M3BridgeSession

_V030: Any = M3_PROTOCOL_VERSION


class M3BridgeRuntime:
    """Expose M3 authority without copying or weakening society rules."""

    def __init__(
        self,
        catalog: CatalogBundle,
        m3_catalogs: M3Catalogs,
        engine: SocietyEngine,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if engine.runtime_mode is not RuntimeMode.UNITY_LIVE:
            raise ValueError("M3BridgeRuntime requires a UNITY_LIVE SocietyEngine")
        self.catalog = catalog
        self.m3_catalogs = m3_catalogs
        self.engine = engine
        self._now = now or (lambda: datetime.now(UTC))
        self._message_counter = 0
        self._generation = 0
        self._ready_generation: int | None = None
        self._lock = RLock()
        self.time_scale = 1.0
        self.paused = False
        self.diagnostics: list[dict[str, Any]] = []
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

    def open_session(self) -> M3BridgeSession:
        from town_core.bridge.m3_session import M3BridgeSession

        with self._lock:
            self._generation += 1
            self._ready_generation = None
            self.session_evidence[self._generation] = {
                "generation": self._generation,
                "semantic_profile": self.m3_catalogs.semantic_instances.profile,
                "catalog_protocol_version": self.catalog.world.protocol_version,
                "negotiated_protocol_version": None,
                "registry_message_id": None,
                "snapshot_state_version": None,
                "snapshot_checkpoint_hash": None,
                "client_ready_state_version": None,
                "ready_acknowledged": False,
                "disconnected": False,
            }
            return M3BridgeSession(self, generation=self._generation)

    def is_current_generation(self, generation: int) -> bool:
        return generation == self._generation

    def mark_ready(self, generation: int) -> None:
        if not self.is_current_generation(generation):
            raise ValueError("obsolete M3 connection generation cannot become ready")
        self._ready_generation = generation
        evidence = self.session_evidence[generation]
        evidence["ready_acknowledged"] = True
        evidence["client_ready_state_version"] = self.engine.state.state_version

    def disconnect(self, generation: int) -> None:
        if self.is_current_generation(generation):
            self._ready_generation = None
        if generation in self.session_evidence:
            self.session_evidence[generation]["disconnected"] = True

    def record_negotiated_protocol(self, generation: int, version: str) -> None:
        self.session_evidence[generation]["negotiated_protocol_version"] = version

    def record_snapshot_evidence(self, generation: int, registry_message_id: str) -> None:
        evidence = self.session_evidence[generation]
        evidence["registry_message_id"] = registry_message_id
        evidence["snapshot_state_version"] = self.engine.state.state_version
        evidence["snapshot_checkpoint_hash"] = checkpoint_hash(self.engine.export_checkpoint())

    def evidence(self) -> dict[str, Any]:
        return {
            "schema": "stwm.bridge.m3-session-evidence/v1",
            "project_name": "Small Town World Model（STWM）",
            "active_generation": self._generation,
            "sessions": [dict(self.session_evidence[key]) for key in sorted(self.session_evidence)],
            "authority_inputs": [dict(item) for item in self.authority_input_evidence],
        }

    def next_message_id(self) -> str:
        with self._lock:
            self._message_counter += 1
            return f"msg_{self._message_counter:08d}"

    def snapshot_message(self, *, correlation_id: str | None = None) -> WorldSnapshotV030Message:
        state = self.engine.state
        return WorldSnapshotV030Message(
            protocol_version=_V030,
            message_id=self.next_message_id(),
            message_type=MessageType.WORLD_SNAPSHOT,
            sent_at_utc=self._now(),
            world_id=state.world_id,
            state_version=state.state_version,
            correlation_id=correlation_id,
            payload=WorldSnapshotV030Payload(
                world=state,
                active_presentations=[
                    self._active_presentation(action_id) for action_id in sorted(self.engine.state.active_actions)
                ],
            ),
        )

    def clock_message(self, *, correlation_id: str | None = None) -> SimulationClockUpdatedV030Message:
        state = self.engine.state
        return SimulationClockUpdatedV030Message(
            protocol_version=_V030,
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

    def set_time_scale(self, requested: float) -> SimulationClockUpdatedV030Message:
        self._require_ready()
        self.time_scale = approve_time_scale(requested, RuntimeMode.UNITY_LIVE)
        self.paused = self.time_scale == 0.0
        return self.clock_message()

    def set_paused(self, paused: bool) -> SimulationClockUpdatedV030Message:
        self._require_ready()
        self.paused = paused
        return self.clock_message()

    def advance_one_minute(self) -> tuple[PythonToUnityMessageV030, ...]:
        with self._lock:
            self._require_ready()
            if self.paused or self.time_scale == 0.0:
                return ()
            before = self.engine.export_checkpoint()
            result = self.engine.advance_to(self.engine.state.game_minute + 1)
            return self._messages_for_result(before, result, include_clock=True)

    def movement_arrived(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        object_id: str | None,
        slot_index: int | None,
    ) -> tuple[PythonToUnityMessageV030, ...]:
        return self._movement_input(
            generation=generation,
            kind=MessageType.MOVEMENT_ARRIVED,
            action_id=action_id,
            agent_id=agent_id,
            state_version=state_version,
            apply=lambda: self.engine.report_movement_arrived(
                action_id=action_id,
                agent_id=agent_id,
                expected_state_version=state_version,
                object_id=object_id,
                slot_index=slot_index,
            ),
        )

    def movement_failed(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        reason: MovementFailureReason,
    ) -> tuple[PythonToUnityMessageV030, ...]:
        return self._movement_input(
            generation=generation,
            kind=MessageType.MOVEMENT_FAILED,
            action_id=action_id,
            agent_id=agent_id,
            state_version=state_version,
            apply=lambda: self.engine.report_movement_failed(
                action_id=action_id,
                agent_id=agent_id,
                expected_state_version=state_version,
                reason=reason,
            ),
        )

    def movement_cancelled(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
        reason: MovementCancellationReason,
    ) -> tuple[PythonToUnityMessageV030, ...]:
        return self._movement_input(
            generation=generation,
            kind=MessageType.MOVEMENT_CANCELLED,
            action_id=action_id,
            agent_id=agent_id,
            state_version=state_version,
            apply=lambda: self.engine.report_movement_cancelled(
                action_id=action_id,
                agent_id=agent_id,
                expected_state_version=state_version,
                reason=reason,
            ),
        )

    def _movement_input(
        self,
        *,
        generation: int,
        kind: MessageType,
        action_id: str,
        agent_id: str,
        state_version: int,
        apply: Callable[[], SocietyAdvanceResult],
    ) -> tuple[PythonToUnityMessageV030, ...]:
        with self._lock:
            self._require_current_ready(generation)
            before = self.engine.export_checkpoint()
            try:
                result = apply()
            except ValueError as exc:
                self._record_authority_input(
                    kind, generation, action_id, agent_id, state_version, before, None, str(exc)
                )
                return self._diagnose_and_resync(f"{kind.value.upper()}_REJECTED", str(exc), action_id)
            self._record_authority_input(kind, generation, action_id, agent_id, state_version, before, result, None)
            return self._messages_for_result(before, result, include_clock=False)

    def presentation_completed(
        self,
        *,
        generation: int,
        action_id: str,
        agent_id: str,
        state_version: int,
    ) -> tuple[PythonToUnityMessageV030, ...]:
        with self._lock:
            self._require_current_ready(generation)
            runtime = self.engine.checkpoint.action_runtimes.get(action_id)
            if (
                state_version > self.engine.state.state_version
                or runtime is None
                or agent_id not in runtime.participant_ids
            ):
                return self._diagnose_and_resync(
                    "PRESENTATION_COMPLETED_REJECTED", "presentation context is not authoritative", action_id
                )
            self.diagnostics.append(
                {
                    "code": "PRESENTATION_COMPLETED",
                    "generation": generation,
                    "action_id": action_id,
                    "agent_id": agent_id,
                    "state_version": self.engine.state.state_version,
                }
            )
            return ()

    def _record_authority_input(
        self,
        kind: MessageType,
        generation: int,
        action_id: str,
        agent_id: str,
        reported_state_version: int,
        before: AuthorityCheckpoint,
        result: SocietyAdvanceResult | None,
        diagnostic: str | None,
    ) -> None:
        after = self.engine.export_checkpoint()
        self.authority_input_evidence.append(
            {
                "input_kind": kind.value,
                "generation": generation,
                "action_id": action_id,
                "agent_id": agent_id,
                "reported_state_version": reported_state_version,
                "accepted": result is not None,
                "diagnostic": diagnostic,
                "before": self._authority_point(before),
                "after": self._authority_point(after),
                "authority_mutation_count": int(checkpoint_hash(before) != checkpoint_hash(after)),
                "authority_transaction_count": 0 if result is None else len(result.transactions),
            }
        )

    @staticmethod
    def _authority_point(checkpoint: AuthorityCheckpoint) -> dict[str, object]:
        return {
            "checkpoint_hash": checkpoint_hash(checkpoint),
            "state_version": checkpoint.world.state_version,
            "game_minute": checkpoint.world.game_minute,
            "transaction_chain_hash": checkpoint.transaction_chain_hash,
        }

    def _diagnose_and_resync(self, code: str, detail: str, action_id: str) -> tuple[PythonToUnityMessageV030, ...]:
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

    def _messages_for_result(
        self,
        before: AuthorityCheckpoint,
        result: SocietyAdvanceResult,
        *,
        include_clock: bool,
    ) -> tuple[PythonToUnityMessageV030, ...]:
        messages: list[PythonToUnityMessageV030] = []
        if include_clock:
            messages.append(self.clock_message())
        for raw in result.actions:
            action_id = str(raw["action_id"])
            phase = ActionPhase(str(raw["phase"]))
            raw_version = raw["state_version"]
            if not isinstance(raw_version, int):
                raise TypeError("M3 action authority state_version must be an integer")
            version = raw_version
            if phase is ActionPhase.CREATED and action_id in self.engine.state.active_actions:
                messages.append(self._action_started(action_id, version))
            elif phase is ActionPhase.CANCELLED:
                reason = raw.get("failure_reason")
                if not isinstance(reason, str) or not reason:
                    raise ValueError("M3 authority cancellation is missing its typed reason")
                messages.append(
                    ActionCancelledV030Message(
                        protocol_version=_V030,
                        message_id=self.next_message_id(),
                        message_type=MessageType.ACTION_CANCELLED,
                        sent_at_utc=self._now(),
                        world_id=self.world_id,
                        state_version=version,
                        correlation_id=action_id,
                        payload=ActionCancelledPayload(action_id=action_id, reason=reason),
                    )
                )
            elif phase is not ActionPhase.CREATED:
                messages.append(
                    ActionPhaseChangedV030Message(
                        protocol_version=_V030,
                        message_id=self.next_message_id(),
                        message_type=MessageType.ACTION_PHASE_CHANGED,
                        sent_at_utc=self._now(),
                        world_id=self.world_id,
                        state_version=version,
                        correlation_id=action_id,
                        payload=ActionPhaseChangedPayload(action_id=action_id, phase=phase),
                    )
                )
        messages.extend(self._state_deltas(before, self.engine.export_checkpoint()))
        for event in result.events:
            messages.append(
                WorldEventCreatedV030Message(
                    protocol_version=_V030,
                    message_id=self.next_message_id(),
                    message_type=MessageType.WORLD_EVENT_CREATED,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=self.engine.state.state_version,
                    correlation_id=event.source_action_id,
                    payload=WorldEventCreatedPayload(event=event),
                )
            )
        for line in result.dialogues:
            conversation_id = self._conversation_id_for_line(line.line_id)
            messages.append(
                DialogueLineReadyV030Message(
                    protocol_version=_V030,
                    message_id=self.next_message_id(),
                    message_type=MessageType.DIALOGUE_LINE_READY,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=self.engine.state.state_version,
                    correlation_id=conversation_id,
                    payload=DialogueLineReadyPayload(
                        conversation_id=conversation_id,
                        speaker_agent_id=line.speaker_agent_id,
                        text=line.text,
                    ),
                )
            )
        messages.extend(self._decision_messages(result.decisions, before))
        return tuple(messages)

    def _state_deltas(self, before: AuthorityCheckpoint, after: AuthorityCheckpoint) -> list[PythonToUnityMessageV030]:
        messages: list[PythonToUnityMessageV030] = []
        for agent_id in sorted(after.world.agents):
            old = before.world.agents[agent_id]
            new = after.world.agents[agent_id]
            values: dict[str, object] = {"agent_id": agent_id, "field_mask": []}
            for field, member in (
                (AgentDeltaField.CURRENT_LOCATION_ID, "current_location_id"),
                (AgentDeltaField.CURRENT_ACTION_ID, "current_action_id"),
                (AgentDeltaField.NEEDS, "needs"),
                (AgentDeltaField.MOOD, "mood"),
                (AgentDeltaField.KNOWN_EVENT_IDS, "known_event_ids"),
            ):
                if getattr(old, member) != getattr(new, member):
                    cast(list[AgentDeltaField], values["field_mask"]).append(field)
                    values[member] = getattr(new, member)
            if not values["field_mask"]:
                continue
            payload = AgentStateDeltaV030Payload.model_validate(values)
            messages.append(
                AgentStateDeltaV030Message(
                    protocol_version=_V030,
                    message_id=self.next_message_id(),
                    message_type=MessageType.AGENT_STATE_DELTA,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=after.world.state_version,
                    correlation_id=new.current_action_id,
                    payload=payload,
                )
            )
        for household_id in sorted(after.world.households):
            old_household = before.world.households[household_id]
            new_household = after.world.households[household_id]
            values = {"household_id": household_id, "field_mask": []}
            if old_household.money != new_household.money:
                cast(list[HouseholdDeltaField], values["field_mask"]).append(HouseholdDeltaField.MONEY)
                values["money"] = new_household.money
            if old_household.food_units != new_household.food_units:
                cast(list[HouseholdDeltaField], values["field_mask"]).append(HouseholdDeltaField.FOOD_UNITS)
                values["food_units"] = new_household.food_units
            if not values["field_mask"]:
                continue
            messages.append(
                HouseholdStateDeltaV030Message(
                    protocol_version=_V030,
                    message_id=self.next_message_id(),
                    message_type=MessageType.HOUSEHOLD_STATE_DELTA,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=after.world.state_version,
                    correlation_id=None,
                    payload=HouseholdStateDeltaV030Payload.model_validate(values),
                )
            )
        old_relations = {(item.source_agent_id, item.target_agent_id): item for item in before.world.relationships}
        new_relations = {(item.source_agent_id, item.target_agent_id): item for item in after.world.relationships}
        for key in sorted(new_relations):
            old_relation = old_relations[key]
            new_relation = new_relations[key]
            delta = self._relationship_delta(old_relation, new_relation)
            if any(float(getattr(delta, axis)) != 0.0 for axis in ("familiarity", "affinity", "trust", "tension")):
                messages.append(
                    RelationshipDeltaV030Message(
                        protocol_version=_V030,
                        message_id=self.next_message_id(),
                        message_type=MessageType.RELATIONSHIP_DELTA,
                        sent_at_utc=self._now(),
                        world_id=self.world_id,
                        state_version=after.world.state_version,
                        correlation_id=None,
                        payload=RelationshipDeltaPayload(
                            source_agent_id=key[0],
                            target_agent_id=key[1],
                            delta=delta,
                        ),
                    )
                )
        return messages

    @staticmethod
    def _relationship_delta(old: RelationshipState, new: RelationshipState) -> RelationshipDelta:
        return RelationshipDelta(
            familiarity=float(new.familiarity) - float(old.familiarity),
            affinity=float(new.affinity) - float(old.affinity),
            trust=float(new.trust) - float(old.trust),
            tension=float(new.tension) - float(old.tension),
        )

    def _decision_messages(
        self, decisions: list[dict[str, object]], before: AuthorityCheckpoint
    ) -> list[DebugDecisionTraceV030Message]:
        messages: list[DebugDecisionTraceV030Message] = []
        for raw in decisions:
            decision = cast(dict[str, Any], raw)
            attempts_raw = cast(list[dict[str, Any]], decision["resolver_attempts"])
            # A same-snapshot due agent can become a participant in an earlier
            # globally ordered social proposal. Its diagnostic decision has no
            # independent accepted proposal, so it cannot truthfully inhabit
            # DebugDecisionTraceV030's selected-proposal shape.
            if not all("candidate_id" in item and "proposal_id" in item for item in attempts_raw):
                continue
            attempts = {str(item["candidate_id"]): item for item in attempts_raw}
            rows: list[DebugCandidateTraceV030] = []
            for rank, item in enumerate(decision["candidates"], start=1):
                candidate = item["candidate"]["candidate"]
                candidate_id = str(candidate["candidate_id"])
                attempt = attempts.get(candidate_id)
                result = None if attempt is None else ProposalResult(str(attempt["result"]))
                conflict_code = result.value if result is not None and result is not ProposalResult.ACCEPTED else None
                rows.append(
                    DebugCandidateTraceV030(
                        rank=rank,
                        candidate_id=candidate_id,
                        proposal_id=None if attempt is None else str(attempt["proposal_id"]),
                        behavior_id=BehaviorId(str(candidate["behavior_id"])),
                        actor_id=str(candidate["actor_id"]),
                        target_agent_id=candidate.get("target_agent_id"),
                        selected_context_event_id=candidate.get("selected_context_event_id"),
                        target_conversation_id=candidate.get("target_conversation_id"),
                        invited_activity_id=candidate.get("invited_activity_id"),
                        destination_location_id=candidate.get("destination_location_id"),
                        hard_preview=self._hard_preview(candidate, before),
                        prediction=OutcomePrediction.model_validate(item["prediction"]),
                        utility_terms={key: float(value) for key, value in item["utility_terms"].items()},
                        total_score=float(item["total_score"]),
                        resolver_result=result,
                        conflict_code=conflict_code,
                    )
                )
            selected_id = str(decision["selected_candidate_id"])
            selected_attempt = attempts[selected_id]
            messages.append(
                DebugDecisionTraceV030Message(
                    protocol_version=_V030,
                    message_id=self.next_message_id(),
                    message_type=MessageType.DEBUG_DECISION_TRACE,
                    sent_at_utc=self._now(),
                    world_id=self.world_id,
                    state_version=int(decision["committed_state_version"]),
                    correlation_id=str(decision["decision_id"]),
                    payload=DebugDecisionTraceV030Payload(
                        decision_id=str(decision["decision_id"]),
                        agent_id=str(decision["agent_id"]),
                        trigger=DecisionTrigger.DECISION_DUE,
                        source_state_version=int(decision["source_state_version"]),
                        candidates=rows,
                        selected_candidate_id=selected_id,
                        selected_proposal_id=str(selected_attempt["proposal_id"]),
                    ),
                )
            )
        return messages

    def _hard_preview(self, candidate: dict[str, Any], before: AuthorityCheckpoint) -> HardPreviewV030:
        bindings: list[ParticipantObjectBindingV030] = []
        for object_id in candidate["target_object_ids"]:
            obj = before.world.objects[str(object_id)]
            free = next((slot for slot in range(obj.slot_count) if slot not in obj.occupied_slots), 0)
            bindings.append(ParticipantObjectBindingV030(object_id=str(object_id), slot_index=free))
        cost = candidate["hard_cost_preview"]
        return HardPreviewV030(
            household_money_delta=int(cost["household_money"]),
            household_food_units_delta=int(cost["household_food_units"]),
            object_bindings=bindings,
            reservation_keys=[f"object:{item.object_id}:{item.slot_index}" for item in bindings],
            settlement_keys=[f"candidate:{candidate['candidate_id']}"],
        )

    def _action_started(self, action_id: str, state_version: int) -> ActionStartedV030Message:
        action = self.engine.state.active_actions[action_id]
        runtime = self.engine.checkpoint.action_runtimes[action_id]
        destination = action.destination_location_id
        if destination is None:
            raise ValueError("M3 action presentation requires a semantic destination")
        return ActionStartedV030Message(
            protocol_version=_V030,
            message_id=self.next_message_id(),
            message_type=MessageType.ACTION_STARTED,
            sent_at_utc=self._now(),
            world_id=self.world_id,
            state_version=state_version,
            correlation_id=action_id,
            payload=ActionStartedV030Payload(
                action_id=action_id,
                behavior_id=action.behavior_id,
                destination_location_id=destination,
                participants=self._participants(runtime),
                is_joint=len(runtime.participant_ids) >= 2,
                conversation_id=self._conversation_id_for_action(runtime),
                planned_duration_minutes=runtime.candidate.candidate.estimated_duration_minutes,
            ),
        )

    def _active_presentation(self, action_id: str) -> ActiveActionPresentationV030:
        action = self.engine.state.active_actions[action_id]
        runtime = self.engine.checkpoint.action_runtimes[action_id]
        if action.destination_location_id is None:
            raise ValueError("M3 active presentation requires a destination")
        return ActiveActionPresentationV030(
            action_id=action_id,
            behavior_id=action.behavior_id,
            phase=action.phase,
            destination_location_id=action.destination_location_id,
            participants=self._participants(runtime),
            is_joint=len(runtime.participant_ids) >= 2,
            conversation_id=self._conversation_id_for_action(runtime),
            planned_end_game_minute=action.planned_end_game_minute,
        )

    def _participants(self, runtime: ActionRuntimeRecord) -> list[ActionParticipantV030]:
        target = runtime.candidate.candidate.target_agent_id
        behavior = self._behavior(runtime.candidate.candidate.behavior_id)
        result: list[ActionParticipantV030] = []
        for agent_id in sorted(runtime.participant_ids):
            role = ActionParticipantRole.PARTICIPANT
            if agent_id == runtime.actor_id:
                role = ActionParticipantRole.ACTOR
            elif agent_id == target:
                role = ActionParticipantRole.TARGET
            bindings = [
                ParticipantObjectBindingV030(object_id=str(item.object_id), slot_index=cast(int, item.slot_index))
                for item in self.engine.checkpoint.reservations.values()
                if item.owner_action_id == runtime.action_id
                and item.kind == "OBJECT_SLOT"
                and item.participant_agent_id == agent_id
            ]
            bindings.sort(key=lambda item: (item.object_id, item.slot_index))
            facing = None
            if behavior.unity.requires_facing and target is not None:
                facing_agent = target if agent_id == runtime.actor_id else runtime.actor_id
                facing = FacingTargetV030(target_agent_id=facing_agent)
            result.append(
                ActionParticipantV030(
                    agent_id=agent_id,
                    role=role,
                    object_bindings=bindings,
                    facing_target=facing,
                    animation_semantic=self._animation_semantic(runtime, agent_id),
                    prop_semantic=behavior.unity.prop_semantic,
                )
            )
        return result

    def _animation_semantic(self, runtime: ActionRuntimeRecord, agent_id: str) -> AnimationSemantic:
        behavior = self._behavior(runtime.candidate.candidate.behavior_id)
        if behavior.behavior_id is BehaviorId.WORK_SHIFT:
            tag = self.engine.state.agents[agent_id].assigned_workstation_tag
            if tag in {CapabilityTag.CAFE_MORNING, CapabilityTag.CAFE_EVENING}:
                return AnimationSemantic.WORK_STANDING
            if tag is CapabilityTag.WORKSHOP:
                return AnimationSemantic.WORK_WORKSHOP
            return AnimationSemantic.WORK_DESK
        return behavior.unity.animation_semantics[0]

    def _conversation_id_for_action(self, runtime: ActionRuntimeRecord) -> str | None:
        target_id = runtime.candidate.target_conversation_id
        if target_id is not None:
            return target_id
        participants = set(runtime.participant_ids)
        matches = [
            item.conversation_id
            for item in self.engine.checkpoint.conversations.values()
            if item.active and set(item.participant_ids) == participants
        ]
        return min(matches) if matches else None

    def _conversation_id_for_line(self, line_id: str) -> str:
        for conversation in self.engine.checkpoint.conversations.values():
            if any(line.line_id == line_id for line in conversation.lines):
                return conversation.conversation_id
        raise ValueError("M3 dialogue line has no authoritative conversation")

    def _behavior(self, behavior_id: BehaviorId) -> BehaviorConfig:
        return next(item for item in self.catalog.behaviors.behaviors if item.behavior_id is behavior_id)

    def _require_ready(self) -> None:
        if not self.ready:
            raise ValueError("M3 simulation is gated until the current connection sends client_ready")

    def _require_current_ready(self, generation: int) -> None:
        if not self.is_current_generation(generation):
            raise ValueError("obsolete M3 connection generation")
        self._require_ready()
