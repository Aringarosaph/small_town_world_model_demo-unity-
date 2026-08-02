"""Deterministic ten-NPC M3 society authority engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

from town_core.domain.config_models import BehaviorConfig, CatalogBundle, MoodValues, NeedValues, ScheduleEntry
from town_core.domain.decision_models import ActionProposal, HardCostPreview, JointAction, JointActionParticipant
from town_core.domain.enums import (
    ActionPhase,
    BehaviorId,
    EventType,
    EventWitnessScope,
    JointActionAuthority,
    KnowledgeAcquisitionType,
    LocationType,
    MoodAxis,
    MovementCancellationReason,
    MovementFailureReason,
    NeedName,
    ObjectType,
    ProposalResult,
)
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.m3_models import M3CandidateAction
from town_core.domain.state_models import (
    ActionState,
    InteractionObjectState,
    KnowledgeRecord,
    RelationshipState,
    WorldEvent,
    WorldState,
)
from town_core.simulation.clock import RuntimeMode, accept_advanced_game_minute
from town_core.society.checkpoint import advance_authority_log_hash, knowledge_key
from town_core.society.invariants import assert_society_invariants, assert_society_transition
from town_core.society.models import (
    ActionRuntimeRecord,
    AuthorityCheckpoint,
    ConversationRecord,
    DialogueLineRecord,
    JointActionRecord,
    ReservationRecord,
    ScoredSocietyCandidate,
    SocietyAdvanceResult,
    SocietyCandidate,
    WorkSessionRecord,
)
from town_core.society.rules import HEURISTIC_PROVIDER_ID, SocietyRulebook, midpoint, stable_unit
from town_core.society.templates import BackgroundTemplateProvider
from town_core.society.transactions import build_transaction_record


@dataclass(frozen=True, slots=True)
class _PreparedDecision:
    decision_id: str
    actor_id: str
    candidates: tuple[ScoredSocietyCandidate, ...]


class _TickContext:
    def __init__(self, checkpoint: AuthorityCheckpoint, minute: int) -> None:
        self.source = checkpoint
        self.minute = minute
        world = checkpoint.world
        self.agents = dict(world.agents)
        self.households = dict(world.households)
        self.locations = dict(world.locations)
        self.objects = dict(world.objects)
        self.relationships = list(world.relationships)
        self.active_actions = dict(world.active_actions)
        self.dialogue_session_ids = list(world.dialogue_session_ids)
        self.events = list(checkpoint.events)
        self.staged_events: list[WorldEvent] = []
        self.knowledge_records = dict(checkpoint.knowledge_records)
        self.work_sessions = dict(checkpoint.work_sessions)
        self.reservations = dict(checkpoint.reservations)
        self.conversations = dict(checkpoint.conversations)
        self.joint_actions = dict(checkpoint.joint_actions)
        self.action_runtimes = dict(checkpoint.action_runtimes)
        self.recent_behaviors = dict(checkpoint.recent_behaviors)
        self.active_need_crises = {key: list(value) for key, value in checkpoint.active_need_crises.items()}
        self.low_resource_flags = {key: list(value) for key, value in checkpoint.low_resource_flags.items()}
        self.settlement_keys = list(checkpoint.settlement_keys)
        self.counters = checkpoint.counters
        self.changes: list[str] = []
        self.decisions: list[dict[str, object]] = []
        self.actions: list[dict[str, object]] = []
        self.dialogues: list[DialogueLineRecord] = []

    def bump(self, field: str) -> int:
        value = int(getattr(self.counters, field)) + 1
        self.counters = self.counters.model_copy(update={field: value})
        return value

    def provisional_world(self, *, state_version: int) -> WorldState:
        return self.source.world.model_copy(
            update={
                "game_minute": self.minute,
                "state_version": state_version,
                "agents": self.agents,
                "households": self.households,
                "locations": self.locations,
                "objects": self.objects,
                "relationships": self.relationships,
                "active_actions": self.active_actions,
                "dialogue_session_ids": sorted(self.dialogue_session_ids),
                "event_cursor": len(self.events) + len(self.staged_events),
            }
        )

    def checkpoint_without_chain(self, *, state_version: int) -> AuthorityCheckpoint:
        return self.source.model_copy(
            update={
                "world": self.provisional_world(state_version=state_version),
                "events": [*self.events, *self.staged_events],
                "knowledge_records": self.knowledge_records,
                "work_sessions": self.work_sessions,
                "reservations": self.reservations,
                "conversations": self.conversations,
                "joint_actions": self.joint_actions,
                "action_runtimes": self.action_runtimes,
                "recent_behaviors": self.recent_behaviors,
                "active_need_crises": self.active_need_crises,
                "low_resource_flags": self.low_resource_flags,
                "settlement_keys": self.settlement_keys,
                "counters": self.counters,
            }
        )


class SocietyEngine:
    """M3 authority runtime; it does not alter the accepted M1 engine."""

    def __init__(
        self,
        catalog: CatalogBundle,
        m3_catalogs: M3Catalogs,
        checkpoint: AuthorityCheckpoint,
        *,
        behavior_allowlist: frozenset[BehaviorId] | None = None,
        runtime_mode: RuntimeMode = RuntimeMode.HEADLESS_FAST,
        movement_timeout_minutes: int = 15,
    ) -> None:
        if behavior_allowlist is not None and BehaviorId.IDLE not in behavior_allowlist:
            raise ValueError("a scoped society behavior profile must retain idle fallback")
        self.catalog = catalog
        self.m3_catalogs = m3_catalogs
        self.checkpoint = checkpoint
        self.rulebook = SocietyRulebook(catalog)
        self.behavior_allowlist = behavior_allowlist
        self.runtime_mode = runtime_mode
        if movement_timeout_minutes <= 0:
            raise ValueError("M3 movement timeout must be positive")
        self.movement_timeout_minutes = movement_timeout_minutes
        self.templates = BackgroundTemplateProvider(m3_catalogs.background_dialogue)
        self._event_config = {item.event_type: item for item in catalog.events.event_types}
        self._npc_config = {item.agent_id: item for item in catalog.population.npcs}
        self._schedules: dict[str, ScheduleEntry] = {}
        schedule_by_id = {item.schedule_id: item for item in catalog.schedules.schedules}
        for agent_id, agent in checkpoint.world.agents.items():
            self._schedules[agent_id] = schedule_by_id[agent.schedule_id].entries[0]
        assert_society_invariants(checkpoint, catalog, m3_catalogs)
        self.tick_durations_ms: list[float] = []
        self.decision_batch_durations_ms: list[float] = []

    @property
    def state(self) -> WorldState:
        return self.checkpoint.world

    def export_checkpoint(self) -> AuthorityCheckpoint:
        return AuthorityCheckpoint.model_validate(self.checkpoint.model_dump(mode="json", exclude_none=False))

    def advance_to(self, target_game_minute: int) -> SocietyAdvanceResult:
        advance = accept_advanced_game_minute(self.state.game_minute, target_game_minute)
        transactions: list[dict[str, object]] = []
        decisions: list[dict[str, object]] = []
        actions: list[dict[str, object]] = []
        events: list[WorldEvent] = []
        dialogues: list[DialogueLineRecord] = []
        authority_records: list[dict[str, object]] = []
        for minute in advance.minutes():
            result = self._advance_one_minute(minute)
            transactions.extend(result.transactions)
            decisions.extend(result.decisions)
            actions.extend(result.actions)
            events.extend(result.events)
            dialogues.extend(result.dialogues)
            authority_records.extend(result.authority_records)
        return SocietyAdvanceResult(
            previous_game_minute=advance.previous_game_minute,
            target_game_minute=advance.target_game_minute,
            transactions=transactions,
            decisions=decisions,
            actions=actions,
            events=events,
            dialogues=dialogues,
            authority_records=authority_records,
            authority_record_count=self.checkpoint.authority_record_count,
            authority_log_hash=self.checkpoint.authority_log_hash,
        )

    def cancel_action(self, action_id: str, *, reason: str = "AUTHORITY_CANCELLED") -> SocietyAdvanceResult:
        """Cancel one whole action/JointAction and release its complete reservation set."""

        if action_id not in self.state.active_actions:
            raise ValueError("cannot cancel an unknown or terminal M3 action")
        context = _TickContext(self.checkpoint, self.state.game_minute)
        self._terminate_action(context, action_id, ActionPhase.CANCELLED, reason)
        return self._commit(context, advances_time=False)

    def fail_action(self, action_id: str, *, reason: str = "AUTHORITY_FAILED") -> SocietyAdvanceResult:
        if action_id not in self.state.active_actions:
            raise ValueError("cannot fail an unknown or terminal M3 action")
        context = _TickContext(self.checkpoint, self.state.game_minute)
        self._terminate_action(context, action_id, ActionPhase.FAILED, reason)
        return self._commit(context, advances_time=False)

    def report_movement_arrived(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        object_id: str | None,
        slot_index: int | None,
    ) -> SocietyAdvanceResult:
        """Commit one Unity arrival; a shared action advances after every traveler arrives."""

        self._validate_live_movement(action_id, agent_id, expected_state_version, allow_stale=False)
        context = _TickContext(self.checkpoint, self.state.game_minute)
        runtime = context.action_runtimes[action_id]
        if agent_id in runtime.arrived_agent_ids:
            raise ValueError("M3 movement arrival was already committed for this participant")
        bindings = [
            item
            for item in context.reservations.values()
            if item.owner_action_id == action_id
            and item.kind == "OBJECT_SLOT"
            and item.participant_agent_id == agent_id
        ]
        supplied = (object_id, slot_index)
        valid_bindings = {
            (str(item.object_id), item.slot_index)
            for item in bindings
            if item.object_id is not None and item.slot_index is not None
        }
        if valid_bindings and supplied not in valid_bindings:
            raise ValueError("M3 arrival does not match an authoritative participant slot binding")
        if not valid_bindings and supplied != (None, None):
            raise ValueError("M3 slot-less participant arrival cannot claim an object binding")
        self._arrive_participant(context, runtime, agent_id)
        updated = context.action_runtimes[action_id]
        if set(updated.arrived_agent_ids) == set(updated.participant_ids):
            self._finish_arrival_barrier(context, updated)
        return self._commit(context, advances_time=False)

    def report_movement_failed(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        reason: MovementFailureReason,
    ) -> SocietyAdvanceResult:
        self._validate_live_movement(action_id, agent_id, expected_state_version, allow_stale=False)
        context = _TickContext(self.checkpoint, self.state.game_minute)
        self._terminate_action(context, action_id, ActionPhase.FAILED, reason.value)
        return self._commit(context, advances_time=False)

    def report_movement_cancelled(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        reason: MovementCancellationReason,
    ) -> SocietyAdvanceResult:
        self._validate_live_movement(action_id, agent_id, expected_state_version, allow_stale=True)
        context = _TickContext(self.checkpoint, self.state.game_minute)
        self._terminate_action(context, action_id, ActionPhase.CANCELLED, reason.value)
        return self._commit(context, advances_time=False)

    def _validate_live_movement(
        self,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        *,
        allow_stale: bool,
    ) -> None:
        if self.runtime_mode is not RuntimeMode.UNITY_LIVE:
            raise ValueError("M3 movement reports require UNITY_LIVE mode")
        if expected_state_version > self.state.state_version:
            raise ValueError("future M3 authority state version")
        if not allow_stale and expected_state_version != self.state.state_version:
            raise ValueError("stale M3 authority state version")
        action = self.state.active_actions.get(action_id)
        runtime = self.checkpoint.action_runtimes.get(action_id)
        if action is None or runtime is None:
            raise ValueError("unknown or terminal M3 action")
        if action.phase is not ActionPhase.TRAVELING:
            raise ValueError("M3 movement report requires a TRAVELING action")
        if agent_id not in runtime.participant_ids:
            raise ValueError("M3 movement report agent is not an action participant")
        if self.state.agents[agent_id].current_action_id != action_id:
            raise ValueError("M3 movement report does not match the agent current action")

    def _advance_one_minute(self, minute: int) -> SocietyAdvanceResult:
        tick_started = perf_counter()
        context = _TickContext(self.checkpoint, minute)
        self._apply_need_changes(context)
        self._progress_actions(context)
        self._finalize_work_sessions(context)
        self._update_need_crises(context)
        self._update_low_resources(context)
        decision_started = perf_counter()
        self._decide_due_agents(context)
        self.decision_batch_durations_ms.append((perf_counter() - decision_started) * 1000.0)
        result = self._commit(context, advances_time=True)
        self.tick_durations_ms.append((perf_counter() - tick_started) * 1000.0)
        return result

    def _commit(self, context: _TickContext, *, advances_time: bool) -> SocietyAdvanceResult:
        previous = self.checkpoint
        context.bump("transaction")
        state_version = previous.world.state_version + 1
        committed_without_chain = context.checkpoint_without_chain(state_version=state_version)
        record, committed = build_transaction_record(
            previous=previous,
            committed_without_chain=committed_without_chain,
            changes=context.changes,
        )
        committed = AuthorityCheckpoint.model_validate(committed.model_dump(mode="json", exclude_none=False))
        if advances_time:
            assert_society_transition(previous, committed)
        else:
            if committed.world.game_minute != previous.world.game_minute:
                raise ValueError("external M3 action input cannot advance game time")
            if committed.world.state_version != previous.world.state_version + 1:
                raise ValueError("external M3 action input must increment state version once")
        assert_society_invariants(committed, self.catalog, self.m3_catalogs)
        for decision in context.decisions:
            decision["committed_state_version"] = committed.world.state_version
        for action in context.actions:
            action["state_version"] = committed.world.state_version
        authority_records: list[dict[str, object]] = []
        authority_records.extend({"kind": "decision", "payload": item} for item in context.decisions)
        authority_records.extend({"kind": "action", "payload": item} for item in context.actions)
        authority_records.extend(
            {
                "kind": "event",
                "payload": item.model_dump(mode="json", exclude_none=False),
            }
            for item in context.staged_events
        )
        authority_records.extend(
            {
                "kind": "dialogue",
                "payload": item.model_dump(mode="json", exclude_none=False),
            }
            for item in context.dialogues
        )
        authority_records.append({"kind": "transaction", "payload": record})
        authority_record_count = previous.authority_record_count
        authority_log_hash = previous.authority_log_hash
        for raw_record in authority_records:
            authority_record_count += 1
            envelope = {
                "schema": "stwm.simulation.m3-authority-record/v1",
                "sequence": authority_record_count,
                "kind": raw_record["kind"],
                "payload": raw_record["payload"],
            }
            authority_log_hash = advance_authority_log_hash(authority_log_hash, envelope)
        committed = committed.model_copy(
            update={
                "authority_record_count": authority_record_count,
                "authority_log_hash": authority_log_hash,
            }
        )
        committed = AuthorityCheckpoint.model_validate(committed.model_dump(mode="json", exclude_none=False))
        assert_society_invariants(committed, self.catalog, self.m3_catalogs)
        self.checkpoint = committed
        return SocietyAdvanceResult(
            previous_game_minute=previous.world.game_minute,
            target_game_minute=committed.world.game_minute,
            transactions=[record],
            decisions=context.decisions,
            actions=context.actions,
            events=context.staged_events,
            dialogues=context.dialogues,
            authority_records=authority_records,
            authority_record_count=authority_record_count,
            authority_log_hash=authority_log_hash,
        )

    def _apply_need_changes(self, context: _TickContext) -> None:
        passive = {axis: value / 60.0 for axis, value in self.catalog.utility.need_decay_per_game_hour.items()}
        for agent_id in sorted(context.agents):
            agent = context.agents[agent_id]
            if not agent.enabled:
                continue
            action = context.active_actions.get(agent.current_action_id or "")
            values = agent.needs.model_dump()
            sleeping = (
                action is not None and action.phase is ActionPhase.PERFORMING and action.behavior_id is BehaviorId.SLEEP
            )
            for axis, delta in passive.items():
                if sleeping and axis is NeedName.ENERGY:
                    continue
                values[axis.value] += delta
            if action is not None and action.phase is ActionPhase.PERFORMING:
                behavior = self.rulebook.behaviors[action.behavior_id]
                if action.behavior_id is BehaviorId.SLEEP:
                    bounds = behavior.output_bounds.need_deltas[NeedName.ENERGY]
                    values[NeedName.ENERGY.value] += midpoint(bounds) / behavior.duration_minutes.base
                elif action.behavior_id is BehaviorId.WORK_SHIFT:
                    for axis in (NeedName.ENERGY, NeedName.HYGIENE, NeedName.FUN):
                        bounds = behavior.output_bounds.need_deltas[axis]
                        values[axis.value] += midpoint(bounds) / behavior.duration_minutes.base
                    runtime = context.action_runtimes[action.action_id]
                    if runtime.work_session_id is not None and runtime.actor_id == agent_id:
                        session = context.work_sessions[runtime.work_session_id]
                        if session.start_game_minute < context.minute <= session.end_game_minute:
                            context.work_sessions[session.session_id] = session.model_copy(
                                update={"effective_work_minutes": session.effective_work_minutes + 1}
                            )
            bounded = {key: round(max(0.0, min(1.0, float(value))), 9) for key, value in values.items()}
            context.agents[agent_id] = agent.model_copy(update={"needs": NeedValues(**bounded)})
        context.changes.append("all_enabled_agent_need_tick")

    def _progress_actions(self, context: _TickContext) -> None:
        for action_id in sorted(context.active_actions, key=self._numeric_id):
            action = context.active_actions.get(action_id)
            if action is None:
                continue
            runtime = context.action_runtimes[action_id]
            if action.phase is ActionPhase.TRAVELING:
                expected_arrival = max(runtime.travel_arrival_minutes.values(), default=context.minute)
                if self.runtime_mode is RuntimeMode.HEADLESS_FAST and context.minute >= expected_arrival:
                    self._arrive(context, runtime)
                    action = context.active_actions[action_id]
                elif (
                    self.runtime_mode is RuntimeMode.UNITY_LIVE
                    and context.minute > expected_arrival + self.movement_timeout_minutes
                ):
                    self._terminate_action(context, action_id, ActionPhase.FAILED, MovementFailureReason.TIMEOUT.value)
                    continue
            if action.phase is ActionPhase.ALIGNING and context.minute >= runtime.perform_start_minute:
                self._start_performing(context, runtime)
                action = context.active_actions[action_id]
            if (
                action.phase is ActionPhase.PERFORMING
                and action.planned_end_game_minute is not None
                and context.minute >= action.planned_end_game_minute
            ):
                self._resolve_action(context, runtime)

    def _arrive(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        for agent_id in runtime.participant_ids:
            if agent_id not in context.action_runtimes[runtime.action_id].arrived_agent_ids:
                self._arrive_participant(context, context.action_runtimes[runtime.action_id], agent_id)
        self._finish_arrival_barrier(context, context.action_runtimes[runtime.action_id])

    def _arrive_participant(
        self,
        context: _TickContext,
        runtime: ActionRuntimeRecord,
        agent_id: str,
    ) -> None:
        action = context.active_actions[runtime.action_id]
        destination = action.destination_location_id
        if destination is None:
            raise ValueError("traveling action has no destination")
        agent = context.agents[agent_id]
        if agent.current_location_id == "TRAVELING":
            context.agents[agent_id] = agent.model_copy(update={"current_location_id": destination})
            location = context.locations[destination]
            context.locations[destination] = location.model_copy(
                update={"current_agent_ids": sorted({*location.current_agent_ids, agent_id})}
            )
        arrived = sorted({*runtime.arrived_agent_ids, agent_id})
        reservation_ids = list(runtime.reservation_ids)
        for reservation_id in list(reservation_ids):
            reservation = context.reservations[reservation_id]
            if reservation.kind == "LOCATION" and reservation.participant_agent_id == agent_id:
                context.reservations.pop(reservation_id)
                reservation_ids.remove(reservation_id)
        context.action_runtimes[runtime.action_id] = runtime.model_copy(
            update={"arrived_agent_ids": arrived, "reservation_ids": reservation_ids}
        )
        if runtime.action_id in context.joint_actions:
            context.joint_actions[runtime.action_id] = context.joint_actions[runtime.action_id].model_copy(
                update={"arrived_agent_ids": arrived}
            )
        context.changes.append(f"participant_arrived:{runtime.action_id}:{agent_id}")

    def _finish_arrival_barrier(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        location_reservations = [
            reservation_id
            for reservation_id in runtime.reservation_ids
            if context.reservations[reservation_id].kind == "LOCATION"
        ]
        for reservation_id in location_reservations:
            context.reservations.pop(reservation_id)
        remaining = [item for item in runtime.reservation_ids if item not in location_reservations]
        updated = runtime.model_copy(update={"reservation_ids": remaining})
        context.action_runtimes[runtime.action_id] = updated
        self._set_phase(context, runtime.action_id, ActionPhase.ALIGNING)
        if context.minute >= updated.perform_start_minute:
            self._start_performing(context, updated)
        context.changes.append(f"action_arrived:{runtime.action_id}")

    def _start_performing(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        self._set_phase(context, runtime.action_id, ActionPhase.PERFORMING)
        action = context.active_actions[runtime.action_id]
        if action.behavior_id is not BehaviorId.WORK_SHIFT or runtime.work_session_id is None:
            return
        session = context.work_sessions[runtime.work_session_id]
        updates: dict[str, object] = {}
        first_start = session.first_work_minute is None
        if first_start:
            updates["first_work_minute"] = context.minute
        if not session.started_event_emitted:
            self._stage_event(
                context,
                EventType.WORK_STARTED,
                location_id=str(action.destination_location_id),
                actor_ids=[runtime.actor_id],
                affected_agent_ids=[runtime.actor_id],
                source_action_id=runtime.action_id,
                payload={
                    "session_id": session.session_id,
                    "scheduled_start": session.start_game_minute,
                    "actual_start": context.minute,
                },
            )
            updates["started_event_emitted"] = True
        if first_start and context.minute > session.start_game_minute and not session.late_event_emitted:
            self._stage_event(
                context,
                EventType.WORK_LATE,
                location_id=str(action.destination_location_id),
                actor_ids=[runtime.actor_id],
                affected_agent_ids=[runtime.actor_id],
                source_action_id=runtime.action_id,
                payload={
                    "session_id": session.session_id,
                    "scheduled_start": session.start_game_minute,
                    "arrival_minute": context.minute,
                    "late_minutes": context.minute - session.start_game_minute,
                },
            )
            updates["late_event_emitted"] = True
        context.work_sessions[session.session_id] = session.model_copy(update=updates)

    def _decide_due_agents(self, context: _TickContext) -> None:
        source_state = context.provisional_world(state_version=context.source.world.state_version)
        event_importance = {
            event.event_id: float(event.importance) for event in [*context.events, *context.staged_events]
        }
        prepared: list[_PreparedDecision] = []
        for agent_id in sorted(source_state.agents):
            agent = source_state.agents[agent_id]
            if (
                not agent.enabled
                or agent.current_action_id is not None
                or agent.current_location_id == "TRAVELING"
                or agent.decision_due_at > context.minute
            ):
                continue
            session = self._decision_work_session(context, agent_id)
            reserved_money, reserved_food = self._reserved_household(context, agent.household_id)
            candidates = self.rulebook.enumerate_candidates(
                source_state,
                agent_id,
                work_session=session,
                conversations=context.conversations,
                event_importance=event_importance,
                reserved_money=reserved_money,
                reserved_food=reserved_food,
                next_candidate_id=lambda: f"candidate_{context.bump('candidate'):08d}",
                behavior_allowlist=self.behavior_allowlist,
            )
            if not candidates:
                raise ValueError(f"M3 candidate enumeration lost idle fallback: {agent_id}")
            predictions = {
                item.candidate.candidate_id: self.rulebook.predict(
                    source_state,
                    item,
                    prediction_id=f"prediction_{context.bump('prediction'):08d}",
                )
                for item in candidates
            }
            scored_candidates = self.rulebook.score_candidates(
                source_state,
                candidates,
                predictions,
                work_session=session,
                recent_behavior=context.recent_behaviors.get(agent_id),
                event_importance=event_importance,
            )
            prepared.append(
                _PreparedDecision(
                    decision_id=f"decision_{context.bump('decision'):08d}",
                    actor_id=agent_id,
                    candidates=tuple(scored_candidates),
                )
            )

        queue = sorted(
            prepared,
            key=lambda item: self._resolver_priority(item.candidates[0]),
        )
        by_actor = {item.actor_id: item for item in prepared}
        outcomes: dict[str, dict[str, object]] = {}
        for prepared_decision in queue:
            actor_id = prepared_decision.actor_id
            if context.agents[actor_id].current_action_id is not None:
                outcomes[actor_id] = {
                    "selected_candidate_id": prepared_decision.candidates[0].candidate.candidate.candidate_id,
                    "selected_behavior_id": prepared_decision.candidates[0].candidate.candidate.behavior_id.value,
                    "selected_action_id": context.agents[actor_id].current_action_id,
                    "resolver_attempts": [{"result": ProposalResult.SOCIAL_TARGET_COMMITTED.value}],
                }
                continue
            attempts: list[dict[str, object]] = []
            accepted: tuple[ScoredSocietyCandidate, str] | None = None
            candidate_attempts = [prepared_decision.candidates[0]]
            idle = next(
                item for item in prepared_decision.candidates if item.candidate.candidate.behavior_id is BehaviorId.IDLE
            )
            if idle not in candidate_attempts:
                candidate_attempts.append(idle)
            for attempt_index, candidate_score in enumerate(candidate_attempts):
                proposal_id = f"proposal_{context.bump('proposal'):08d}"
                proposal = self._proposal(source_state, candidate_score, proposal_id)
                result, action_id = self._resolve_and_create(context, source_state, proposal, candidate_score)
                attempts.append(
                    {
                        "proposal_id": proposal_id,
                        "candidate_id": candidate_score.candidate.candidate.candidate_id,
                        "result": result.value,
                    }
                )
                if result is ProposalResult.ACCEPTED and action_id is not None:
                    accepted = (candidate_score, action_id)
                    break
            if accepted is None:
                raise ValueError(f"M3 central Resolver rejected idle fallback: {actor_id}")
            selected, action_id = accepted
            outcomes[actor_id] = {
                "selected_candidate_id": selected.candidate.candidate.candidate_id,
                "selected_behavior_id": selected.candidate.candidate.behavior_id.value,
                "selected_action_id": action_id,
                "resolver_attempts": attempts,
            }

        for agent_id in sorted(by_actor):
            prepared_decision = by_actor[agent_id]
            outcome = outcomes[agent_id]
            context.decisions.append(
                {
                    "decision_id": prepared_decision.decision_id,
                    "source_state_version": source_state.state_version,
                    "game_minute": context.minute,
                    "agent_id": agent_id,
                    "trigger": "DECISION_DUE",
                    "candidates": [
                        {
                            "candidate": item.candidate.model_dump(mode="json", exclude_none=False),
                            "prediction": item.prediction.model_dump(mode="json", exclude_none=False),
                            "utility_terms": item.utility_terms,
                            "total_score": item.total_score,
                            "tie_break": item.tie_break,
                        }
                        for item in prepared_decision.candidates
                    ],
                    **outcome,
                    "outcome_provider": HEURISTIC_PROVIDER_ID,
                }
            )
            context.changes.append(f"decision_committed:{prepared_decision.decision_id}:{agent_id}")

    def _proposal(
        self,
        source_state: WorldState,
        scored: ScoredSocietyCandidate,
        proposal_id: str,
    ) -> ActionProposal:
        candidate = scored.candidate.candidate
        return ActionProposal(
            proposal_id=proposal_id,
            state_version=source_state.state_version,
            actor_id=candidate.actor_id,
            candidate_id=candidate.candidate_id,
            behavior_id=candidate.behavior_id,
            target_agent_id=candidate.target_agent_id,
            target_object_ids=candidate.target_object_ids,
            score=scored.total_score,
            model_prediction_id=scored.prediction.prediction_id,
        )

    def _resolve_and_create(
        self,
        context: _TickContext,
        source_state: WorldState,
        proposal: ActionProposal,
        scored: ScoredSocietyCandidate,
        *,
        force_joint: bool = False,
        source_invite_action_id: str | None = None,
        participant_proposal_ids: Mapping[str, str] | None = None,
    ) -> tuple[ProposalResult, str | None]:
        candidate = scored.candidate.candidate
        if proposal.state_version != source_state.state_version:
            return ProposalResult.STATE_STALE, None
        actor = context.agents[proposal.actor_id]
        if actor.current_action_id is not None:
            return ProposalResult.TARGET_UNAVAILABLE, None
        participants = [proposal.actor_id]
        if proposal.target_agent_id is not None:
            target = context.agents[proposal.target_agent_id]
            if target.current_action_id is not None:
                return ProposalResult.SOCIAL_TARGET_COMMITTED, None
            if target.current_location_id != actor.current_location_id:
                return ProposalResult.TARGET_UNAVAILABLE, None
            participants.append(proposal.target_agent_id)
        participants = sorted(set(participants))

        if (
            scored.candidate.selected_context_event_id is not None
            and knowledge_key(proposal.actor_id, scored.candidate.selected_context_event_id)
            not in context.knowledge_records
        ):
            return ProposalResult.TARGET_UNAVAILABLE, None
        destination = candidate.destination_location_id
        arrival = context.minute + candidate.estimated_travel_minutes
        if destination is not None and not self.rulebook.location_open(destination, arrival):
            return ProposalResult.LOCATION_CLOSED, None
        if destination is not None:
            incoming = sum(
                1
                for item in context.reservations.values()
                if item.kind == "LOCATION" and item.location_id == destination
            )
            traveling_count = sum(
                1 for agent_id in participants if context.agents[agent_id].current_location_id != destination
            )
            capacity = self.rulebook.locations[destination].capacity
            if len(context.locations[destination].current_agent_ids) + incoming + traveling_count > capacity:
                return ProposalResult.TARGET_UNAVAILABLE, None

        costs = self._resource_costs(context, scored.candidate, participants, force_joint)
        for household_id, (money, food) in costs.items():
            reserved_money, reserved_food = self._reserved_household(context, household_id)
            household = context.households[household_id]
            if household.money - reserved_money < money or household.food_units - reserved_food < food:
                return ProposalResult.INSUFFICIENT_FUNDS, None

        slot_claims: list[tuple[str, int]] = []
        for object_id in candidate.target_object_ids:
            obj = context.objects.get(object_id)
            if obj is None or not obj.enabled:
                return ProposalResult.TARGET_UNAVAILABLE, None
            quantity = self._slot_quantity(obj, candidate.behavior_id, participants, force_joint)
            free = [slot for slot in range(obj.slot_count) if slot not in obj.occupied_slots]
            if len(free) < quantity:
                return ProposalResult.OBJECT_SLOT_CONFLICT, None
            slot_claims.extend((object_id, slot) for slot in free[:quantity])

        action_id = self._create_action(
            context,
            scored,
            proposal,
            participants,
            slot_claims,
            costs,
            force_joint=force_joint,
            source_invite_action_id=source_invite_action_id,
            participant_proposal_ids=participant_proposal_ids,
        )
        return ProposalResult.ACCEPTED, action_id

    def _create_action(
        self,
        context: _TickContext,
        scored: ScoredSocietyCandidate,
        proposal: ActionProposal,
        participants: list[str],
        slot_claims: Sequence[tuple[str, int]],
        costs: Mapping[str, tuple[int, int]],
        *,
        force_joint: bool,
        source_invite_action_id: str | None,
        participant_proposal_ids: Mapping[str, str] | None,
    ) -> str:
        candidate = scored.candidate.candidate
        action_id = f"action_{context.bump('action'):08d}"
        arrivals: dict[str, int] = {}
        origins: dict[str, str] = {}
        destination = candidate.destination_location_id
        for agent_id in participants:
            origin = context.agents[agent_id].current_location_id
            if origin == "TRAVELING":
                raise ValueError("available society participant cannot already be traveling")
            origins[agent_id] = origin
            travel = (
                0
                if destination is None or origin == destination
                else self.rulebook.locations[origin].travel_minutes[destination]
            )
            arrivals[agent_id] = context.minute + travel
        perform_start = max(arrivals.values(), default=context.minute)
        work_session_id: str | None = None
        if candidate.behavior_id is BehaviorId.WORK_SHIFT:
            work_session = self._decision_work_session(context, proposal.actor_id)
            if work_session is None:
                raise ValueError("accepted work action has no work occurrence")
            perform_start = max(perform_start, work_session.start_game_minute)
            work_session_id = work_session.session_id
        planned_end = perform_start + candidate.estimated_duration_minutes
        action = ActionState(
            action_id=action_id,
            behavior_id=candidate.behavior_id,
            agent_ids=participants,
            phase=ActionPhase.CREATED,
            destination_location_id=destination,
            target_object_ids=candidate.target_object_ids,
            started_at_game_minute=context.minute,
            planned_end_game_minute=planned_end,
        )
        context.active_actions[action_id] = action
        self._record_phase(context, action, ActionPhase.CREATED)
        self._set_phase(context, action_id, ActionPhase.RESERVING)

        reservation_ids: list[str] = []
        expires = planned_end + 60
        for agent_id in participants:
            reservation_ids.append(
                self._add_reservation(
                    context,
                    owner_action_id=action_id,
                    kind="PARTICIPANT",
                    participant_agent_id=agent_id,
                    expires_at=expires,
                )
            )
        claims_by_object: dict[str, list[int]] = {}
        for object_id, slot in slot_claims:
            claims_by_object.setdefault(object_id, []).append(slot)
        for object_id, slot in slot_claims:
            object_claims = claims_by_object[object_id]
            participant_index = object_claims.index(slot)
            binding_agent_id = (
                participants[participant_index] if len(object_claims) == len(participants) else proposal.actor_id
            )
            reservation_ids.append(
                self._add_reservation(
                    context,
                    owner_action_id=action_id,
                    kind="OBJECT_SLOT",
                    object_id=object_id,
                    slot_index=slot,
                    participant_agent_id=binding_agent_id,
                    expires_at=expires,
                )
            )
            obj = context.objects[object_id]
            occupied = dict(obj.occupied_slots)
            occupied[slot] = action_id
            context.objects[object_id] = obj.model_copy(update={"occupied_slots": occupied})
        for household_id, (money, food) in sorted(costs.items()):
            if money or food:
                reservation_ids.append(
                    self._add_reservation(
                        context,
                        owner_action_id=action_id,
                        kind="HOUSEHOLD_RESOURCE",
                        household_id=household_id,
                        money_units=money,
                        food_units=food,
                        expires_at=expires,
                    )
                )
        for agent_id in participants:
            if destination is not None and origins[agent_id] != destination:
                reservation_ids.append(
                    self._add_reservation(
                        context,
                        owner_action_id=action_id,
                        kind="LOCATION",
                        location_id=destination,
                        participant_agent_id=agent_id,
                        expires_at=expires,
                    )
                )

        runtime = ActionRuntimeRecord(
            action_id=action_id,
            actor_id=proposal.actor_id,
            proposal_id=proposal.proposal_id,
            candidate=scored.candidate,
            prediction=scored.prediction,
            participant_ids=participants,
            reservation_ids=reservation_ids,
            origin_location_ids=origins,
            travel_arrival_minutes=arrivals,
            arrived_agent_ids=sorted(
                agent_id for agent_id in participants if destination is None or origins[agent_id] == destination
            ),
            perform_start_minute=perform_start,
            work_session_id=work_session_id,
            joint=force_joint,
        )
        context.action_runtimes[action_id] = runtime
        for agent_id in participants:
            agent = context.agents[agent_id]
            context.agents[agent_id] = agent.model_copy(
                update={"current_action_id": action_id, "decision_due_at": planned_end}
            )
        if work_session_id is not None:
            session = context.work_sessions[work_session_id]
            context.work_sessions[work_session_id] = session.model_copy(
                update={
                    "proposal_ids": [*session.proposal_ids, proposal.proposal_id],
                    "action_ids": [*session.action_ids, action_id],
                }
            )
        if force_joint:
            proposal_ids = dict(participant_proposal_ids or {proposal.actor_id: proposal.proposal_id})
            participants_model = [
                JointActionParticipant(agent_id=agent_id, proposal_id=proposal_ids[agent_id])
                for agent_id in sorted(participants)
            ]
            joint = JointAction(
                action_id=action_id,
                behavior_id=candidate.behavior_id,
                authority=JointActionAuthority.CENTRAL_RESOLVER,
                state_version=context.source.world.state_version,
                location_id=cast(str, destination),
                participants=participants_model,
            )
            context.joint_actions[action_id] = JointActionRecord(
                joint_action=joint,
                source_invite_action_id=cast(str, source_invite_action_id),
                status="RESERVED",
            )

        traveling = False
        for agent_id in participants:
            if destination is None or origins[agent_id] == destination:
                continue
            traveling = True
            origin_state = context.locations[origins[agent_id]]
            context.locations[origins[agent_id]] = origin_state.model_copy(
                update={"current_agent_ids": [item for item in origin_state.current_agent_ids if item != agent_id]}
            )
            context.agents[agent_id] = context.agents[agent_id].model_copy(update={"current_location_id": "TRAVELING"})
        if traveling:
            self._set_phase(context, action_id, ActionPhase.TRAVELING)
            if force_joint:
                context.joint_actions[action_id] = context.joint_actions[action_id].model_copy(
                    update={"status": "TRAVELING"}
                )
        elif context.minute < perform_start:
            self._set_phase(context, action_id, ActionPhase.ALIGNING)
        else:
            self._start_performing(context, runtime)
        context.changes.append(f"action_created:{action_id}:{candidate.behavior_id.value}")
        return action_id

    def _resolve_action(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        action = context.active_actions[runtime.action_id]
        self._set_phase(context, runtime.action_id, ActionPhase.RESOLVING)
        accepted = self._social_acceptance(context, runtime)
        if action.behavior_id is BehaviorId.INVITE_JOIN and accepted:
            invite_location_id = str(context.agents[runtime.actor_id].current_location_id)
            self._terminate_action(context, action.action_id, ActionPhase.COMPLETED, None, release_only=True)
            accepted = self._create_invited_joint(context, runtime)
            self._complete_social_effects(context, runtime, accepted, location_id=invite_location_id)
            context.changes.append(f"action_terminal:{runtime.action_id}:COMPLETED")
            return

        self._commit_reserved_resources(context, runtime)
        self._apply_behavior_effects(context, runtime, accepted)
        if action.behavior_id in self._social_behaviors:
            self._complete_social_effects(context, runtime, accepted)
        else:
            self._emit_non_social_events(context, runtime)
        self._terminate_action(context, action.action_id, ActionPhase.COMPLETED, None)

    def _social_acceptance(self, context: _TickContext, runtime: ActionRuntimeRecord) -> bool:
        behavior = runtime.candidate.candidate.behavior_id
        if behavior not in self._social_behaviors or behavior in {BehaviorId.SHARE_EVENT, BehaviorId.END_CONVERSATION}:
            return True
        probability = runtime.prediction.acceptance_probability
        if probability is None:
            return True
        draw = stable_unit(
            "m3-social-outcome-v1",
            context.source.world.random_seed,
            runtime.action_id,
            behavior.value,
            runtime.actor_id,
            runtime.candidate.candidate.target_agent_id,
        )
        return draw <= probability

    def _commit_reserved_resources(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        resource_reservations = [
            context.reservations[item]
            for item in runtime.reservation_ids
            if context.reservations[item].kind == "HOUSEHOLD_RESOURCE"
        ]
        if not resource_reservations:
            return
        settlement_key = f"action_resource:{runtime.action_id}"
        if settlement_key in context.settlement_keys:
            raise ValueError("M3 action resources attempted to settle twice")
        behavior_id = runtime.candidate.candidate.behavior_id
        for reservation in resource_reservations:
            household_id = cast(str, reservation.household_id)
            household = context.households[household_id]
            if household.money < reservation.money_units or household.food_units < reservation.food_units:
                raise ValueError("reserved household resource disappeared before atomic settlement")
            food_delta = -reservation.food_units
            if behavior_id is BehaviorId.BUY_GROCERIES:
                food_delta += self.catalog.economy.groceries.food_units_delta
            context.households[household_id] = household.model_copy(
                update={
                    "money": household.money - reservation.money_units,
                    "food_units": household.food_units + food_delta,
                }
            )
        context.settlement_keys.append(settlement_key)
        context.changes.append(f"resource_settled:{settlement_key}")

    def _apply_behavior_effects(
        self,
        context: _TickContext,
        runtime: ActionRuntimeRecord,
        accepted: bool,
    ) -> None:
        behavior = self.rulebook.behaviors[runtime.candidate.candidate.behavior_id]
        participants = runtime.participant_ids if runtime.joint else [runtime.actor_id]
        for agent_id in participants:
            agent = context.agents[agent_id]
            needs = agent.needs.model_dump()
            for need_axis, bounds in behavior.output_bounds.need_deltas.items():
                if behavior.behavior_id in {BehaviorId.SLEEP, BehaviorId.WORK_SHIFT}:
                    continue
                delta = midpoint(bounds)
                needs[need_axis.value] = round(max(0.0, min(1.0, float(needs[need_axis.value]) + delta)), 9)
            mood = agent.mood.model_dump()
            mood_bounds = behavior.output_bounds.actor_mood_deltas
            for mood_axis, bounds in mood_bounds.items():
                delta = midpoint(bounds)
                lower = -1.0 if mood_axis is MoodAxis.VALENCE else 0.0
                mood[mood_axis.value] = round(max(lower, min(1.0, float(mood[mood_axis.value]) + delta)), 9)
            context.agents[agent_id] = agent.model_copy(
                update={"needs": NeedValues(**needs), "mood": MoodValues(**mood)}
            )
        target_id = runtime.candidate.candidate.target_agent_id
        if target_id is not None and not runtime.joint:
            target = context.agents[target_id]
            mood = target.mood.model_dump()
            for mood_axis, bounds in behavior.output_bounds.target_mood_deltas.items():
                delta = midpoint(bounds) if accepted else bounds.minimum
                lower = -1.0 if mood_axis is MoodAxis.VALENCE else 0.0
                mood[mood_axis.value] = round(max(lower, min(1.0, float(mood[mood_axis.value]) + delta)), 9)
            context.agents[target_id] = target.model_copy(update={"mood": MoodValues(**mood)})

    def _complete_social_effects(
        self,
        context: _TickContext,
        runtime: ActionRuntimeRecord,
        accepted: bool,
        *,
        location_id: str | None = None,
    ) -> None:
        candidate = runtime.candidate.candidate
        target_id = candidate.target_agent_id
        if target_id is None:
            return
        behavior = self.rulebook.behaviors[candidate.behavior_id]
        if behavior.output_bounds.relationship_target_to_actor:
            self._apply_target_to_actor_relationship(
                context,
                source_id=target_id,
                target_id=runtime.actor_id,
                behavior=behavior,
                accepted=accepted,
            )
        if candidate.behavior_id is BehaviorId.SHARE_EVENT and accepted:
            event_id = runtime.candidate.selected_context_event_id
            if event_id is None or knowledge_key(runtime.actor_id, event_id) not in context.knowledge_records:
                raise ValueError("share_event resolved without speaker knowledge permission")
            self._add_knowledge(
                context,
                agent_id=target_id,
                event_id=event_id,
                source_agent_id=runtime.actor_id,
                acquisition_type=KnowledgeAcquisitionType.TOLD,
                confidence=0.75,
            )
        conversation = self._conversation_for_social(context, runtime)
        event_types = self._social_event_types(context, runtime, accepted, conversation)
        for event_type in event_types:
            self._stage_event(
                context,
                event_type,
                location_id=location_id or str(context.agents[runtime.actor_id].current_location_id),
                actor_ids=[runtime.actor_id],
                affected_agent_ids=[target_id],
                source_action_id=runtime.action_id,
                payload={
                    "accepted": accepted,
                    "conversation_id": conversation.conversation_id if conversation is not None else None,
                    "shared_event_id": runtime.candidate.selected_context_event_id,
                    "invited_activity_id": (
                        runtime.candidate.invited_activity_id.value
                        if runtime.candidate.invited_activity_id is not None
                        else None
                    ),
                },
            )
        if conversation is not None:
            line = self.templates.render(
                line_id=f"dialogue_line_{context.bump('dialogue_line'):08d}",
                game_minute=context.minute,
                world_seed=context.source.world.random_seed,
                action_id=runtime.action_id,
                behavior_id=candidate.behavior_id,
                accepted=accepted,
                speaker_agent_id=runtime.actor_id,
                listener_ids=[target_id],
                referenced_event_id=runtime.candidate.selected_context_event_id,
                speaker_known_event_ids=context.agents[runtime.actor_id].known_event_ids,
            )
            current = context.conversations[conversation.conversation_id]
            context.conversations[conversation.conversation_id] = current.model_copy(
                update={
                    "last_activity_game_minute": context.minute,
                    "source_action_ids": [*current.source_action_ids, runtime.action_id],
                    "lines": [*current.lines, line],
                }
            )
            context.dialogues.append(line)
        cooldown_key = f"{candidate.behavior_id.value}:{target_id}"
        actor = context.agents[runtime.actor_id]
        cooldowns = dict(actor.social_cooldowns)
        cooldowns[cooldown_key] = context.minute + behavior.cooldown_minutes
        context.agents[runtime.actor_id] = actor.model_copy(update={"social_cooldowns": cooldowns})

    def _conversation_for_social(
        self,
        context: _TickContext,
        runtime: ActionRuntimeRecord,
    ) -> ConversationRecord | None:
        behavior_id = runtime.candidate.candidate.behavior_id
        target_id = runtime.candidate.candidate.target_agent_id
        if target_id is None:
            return None
        if behavior_id is BehaviorId.END_CONVERSATION:
            conversation_id = runtime.candidate.target_conversation_id
            if conversation_id is None or conversation_id not in context.conversations:
                raise ValueError("end_conversation references no active conversation")
            conversation = context.conversations[conversation_id]
            context.conversations[conversation_id] = conversation.model_copy(
                update={"active": False, "last_activity_game_minute": context.minute}
            )
            if conversation_id in context.dialogue_session_ids:
                context.dialogue_session_ids.remove(conversation_id)
            return context.conversations[conversation_id]
        participants = sorted([runtime.actor_id, target_id])
        existing = next(
            (item for item in context.conversations.values() if item.active and item.participant_ids == participants),
            None,
        )
        if existing is not None:
            return existing
        conversation_id = f"conversation_{context.bump('conversation'):08d}"
        conversation = ConversationRecord(
            conversation_id=conversation_id,
            participant_ids=participants,
            started_at_game_minute=context.minute,
            last_activity_game_minute=context.minute,
        )
        context.conversations[conversation_id] = conversation
        context.dialogue_session_ids.append(conversation_id)
        context.changes.append(f"conversation_started:{conversation_id}")
        return conversation

    def _social_event_types(
        self,
        context: _TickContext,
        runtime: ActionRuntimeRecord,
        accepted: bool,
        conversation: ConversationRecord | None,
    ) -> list[EventType]:
        behavior_id = runtime.candidate.candidate.behavior_id
        if behavior_id is BehaviorId.GREET:
            target_id = runtime.candidate.candidate.target_agent_id or ""
            prior_greeting = any(
                event.event_type is EventType.FIRST_GREETING
                and runtime.actor_id in event.actor_ids
                and target_id in event.affected_agent_ids
                for event in [*context.events, *context.staged_events]
            )
            result = []
            if conversation is not None and not conversation.source_action_ids:
                result.append(EventType.CONVERSATION_STARTED)
            if not prior_greeting:
                result.insert(0, EventType.FIRST_GREETING)
            return result
        if behavior_id is BehaviorId.CHAT:
            result = [EventType.POSITIVE_INTERACTION if accepted else EventType.AWKWARD_INTERACTION]
            if conversation is not None and not conversation.source_action_ids:
                result.append(EventType.CONVERSATION_STARTED)
            return result
        if behavior_id in {BehaviorId.JOKE, BehaviorId.COMPLIMENT}:
            return [EventType.POSITIVE_INTERACTION if accepted else EventType.AWKWARD_INTERACTION]
        if behavior_id is BehaviorId.SHARE_EVENT:
            return [EventType.EVENT_SHARED]
        if behavior_id is BehaviorId.INVITE_JOIN:
            return [EventType.INVITATION_ACCEPTED if accepted else EventType.INVITATION_REJECTED]
        if behavior_id is BehaviorId.APOLOGIZE:
            return (
                [EventType.APOLOGY_ACCEPTED, EventType.CONFLICT_REDUCED] if accepted else [EventType.APOLOGY_REJECTED]
            )
        if behavior_id is BehaviorId.CONFRONT:
            return [EventType.CONFLICT_REDUCED if accepted else EventType.CONFLICT_ESCALATED]
        if behavior_id is BehaviorId.END_CONVERSATION:
            return [EventType.CONVERSATION_ENDED]
        return []

    def _emit_non_social_events(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        behavior_id = runtime.candidate.candidate.behavior_id
        event_type: EventType | None = None
        if behavior_id in {BehaviorId.EAT_AT_HOME, BehaviorId.EAT_AT_CAFE}:
            event_type = EventType.MEAL_CONSUMED
        elif behavior_id is BehaviorId.BUY_GROCERIES:
            event_type = EventType.GROCERIES_PURCHASED
        if event_type is None:
            return
        self._stage_event(
            context,
            event_type,
            location_id=str(context.agents[runtime.actor_id].current_location_id),
            actor_ids=[runtime.actor_id],
            affected_agent_ids=runtime.participant_ids,
            source_action_id=runtime.action_id,
            payload={"behavior_id": behavior_id.value, "participant_count": len(runtime.participant_ids)},
        )

    def _create_invited_joint(self, context: _TickContext, invite_runtime: ActionRuntimeRecord) -> bool:
        activity_id = invite_runtime.candidate.invited_activity_id
        target_id = invite_runtime.candidate.candidate.target_agent_id
        if activity_id is None or target_id is None:
            return False
        actor_id = invite_runtime.actor_id
        state = context.provisional_world(state_version=context.source.world.state_version)
        behavior = self.rulebook.behaviors[activity_id]
        destination = self._destination_for_behavior(state, actor_id, activity_id)
        object_ids = self.rulebook._object_bundle(state, actor_id, behavior, destination)
        if object_ids is None:
            return False
        hard_cost = self._hard_cost_preview(activity_id)
        draft = self.rulebook._draft(
            state,
            actor_id,
            behavior,
            destination=destination,
            target_agent_id=target_id,
            target_object_ids=object_ids,
            hard_cost=hard_cost,
        )
        candidate = SocietyCandidate(candidate=self._candidate_from_draft(context, actor_id, draft))
        prediction = self.rulebook.predict(
            state,
            candidate,
            prediction_id=f"prediction_{context.bump('prediction'):08d}",
        )
        scored = ScoredSocietyCandidate(
            candidate=candidate,
            prediction=prediction,
            utility_terms={"joint_invitation": 1.0},
            total_score=1.0,
            tie_break=0.0,
        )
        actor_proposal_id = f"proposal_{context.bump('proposal'):08d}"
        target_proposal_id = f"proposal_{context.bump('proposal'):08d}"
        proposal = self._proposal(state, scored, actor_proposal_id)
        result, _ = self._resolve_and_create(
            context,
            state,
            proposal,
            scored,
            force_joint=True,
            source_invite_action_id=invite_runtime.action_id,
            participant_proposal_ids={actor_id: actor_proposal_id, target_id: target_proposal_id},
        )
        return result is ProposalResult.ACCEPTED

    def _candidate_from_draft(self, context: _TickContext, actor_id: str, draft: Any) -> M3CandidateAction:
        from town_core.domain.enums import RoutePlanningCapability

        return M3CandidateAction(
            candidate_id=f"candidate_{context.bump('candidate'):08d}",
            actor_id=actor_id,
            behavior_id=draft.behavior_id,
            target_agent_id=draft.target_agent_id,
            target_object_ids=list(draft.target_object_ids),
            destination_location_id=draft.destination_location_id,
            estimated_travel_minutes=draft.travel_minutes,
            estimated_duration_minutes=draft.duration_minutes,
            hard_cost_preview=draft.hard_cost,
            schedule_conflict_minutes=draft.schedule_conflict_minutes,
            context_event_ids=[],
            route_planning=RoutePlanningCapability.DISABLED,
            selected_context_event_id=None,
            target_conversation_id=None,
            invited_activity_id=None,
        )

    def _terminate_action(
        self,
        context: _TickContext,
        action_id: str,
        terminal_phase: ActionPhase,
        reason: str | None,
        *,
        release_only: bool = False,
    ) -> None:
        action = context.active_actions[action_id]
        runtime = context.action_runtimes[action_id]
        self._release_reservations(context, runtime)
        if not release_only:
            self._record_phase(context, action, terminal_phase, failure_reason=reason)
        else:
            self._record_phase(context, action, terminal_phase)
        context.active_actions.pop(action_id)
        context.action_runtimes.pop(action_id)
        context.joint_actions.pop(action_id, None)
        for agent_id in runtime.participant_ids:
            agent = context.agents[agent_id]
            if terminal_phase in {ActionPhase.CANCELLED, ActionPhase.FAILED, ActionPhase.INTERRUPTED}:
                origin = runtime.origin_location_ids[agent_id]
                if agent.current_location_id != "TRAVELING" and agent.current_location_id != origin:
                    current_location = context.locations[agent.current_location_id]
                    context.locations[agent.current_location_id] = current_location.model_copy(
                        update={
                            "current_agent_ids": [
                                item for item in current_location.current_agent_ids if item != agent_id
                            ]
                        }
                    )
                if agent.current_location_id != origin:
                    location = context.locations[origin]
                    context.locations[origin] = location.model_copy(
                        update={"current_agent_ids": sorted({*location.current_agent_ids, agent_id})}
                    )
                    agent = agent.model_copy(update={"current_location_id": origin})
            current_action_id = None if agent.current_action_id == action_id else agent.current_action_id
            context.agents[agent_id] = agent.model_copy(
                update={"current_action_id": current_action_id, "decision_due_at": context.minute}
            )
            context.recent_behaviors[agent_id] = action.behavior_id
        context.changes.append(f"action_terminal:{action_id}:{terminal_phase.value}:{reason or ''}")

    def _release_reservations(self, context: _TickContext, runtime: ActionRuntimeRecord) -> None:
        for reservation_id in runtime.reservation_ids:
            reservation = context.reservations.pop(reservation_id, None)
            if reservation is None:
                raise ValueError(f"action reservation disappeared before release: {reservation_id}")
            if reservation.kind == "OBJECT_SLOT":
                object_id = cast(str, reservation.object_id)
                slot = cast(int, reservation.slot_index)
                obj = context.objects[object_id]
                occupied = dict(obj.occupied_slots)
                if occupied.get(slot) != runtime.action_id:
                    raise ValueError("object slot owner changed before release")
                occupied.pop(slot)
                context.objects[object_id] = obj.model_copy(update={"occupied_slots": occupied})

    def _finalize_work_sessions(self, context: _TickContext) -> None:
        day = context.minute // 1440
        for agent_id in sorted(context.agents):
            schedule = self._schedules[agent_id]
            if day % 7 not in schedule.weekdays:
                continue
            end = (day * 1440) + schedule.end_minute_of_day
            if context.minute != end:
                continue
            session = self._work_session(context, agent_id, day)
            if session.finalized:
                continue
            scheduled_minutes = session.end_game_minute - session.start_game_minute
            minimum = scheduled_minutes - session.grace_minutes
            eligible = session.first_work_minute is not None and session.first_work_minute <= (
                session.start_game_minute + session.grace_minutes
            )
            paid = eligible and session.effective_work_minutes >= minimum
            updates: dict[str, object] = {"finalized": True, "paid": paid}
            context.work_sessions[session.session_id] = session.model_copy(update=updates)
            source_action_id = session.action_ids[-1] if session.action_ids else None
            agent = context.agents[agent_id]
            if paid:
                settlement_key = f"wage:{session.session_id}"
                if settlement_key in context.settlement_keys:
                    raise ValueError("work session wage attempted to settle twice")
                household = context.households[agent.household_id]
                context.households[agent.household_id] = household.model_copy(
                    update={"money": household.money + self.catalog.economy.fixed_shift_wage}
                )
                context.settlement_keys.append(settlement_key)
                self._stage_event(
                    context,
                    EventType.WORK_COMPLETED,
                    location_id=agent.assigned_work_location_id,
                    actor_ids=[agent_id],
                    affected_agent_ids=[agent_id],
                    source_action_id=source_action_id,
                    payload={
                        "session_id": session.session_id,
                        "effective_work_minutes": session.effective_work_minutes,
                        "scheduled_work_minutes": scheduled_minutes,
                        "minimum_effective_minutes": minimum,
                        "grace_minutes": session.grace_minutes,
                        "wage_minor_units": self.catalog.economy.fixed_shift_wage,
                    },
                )
                context.changes.append(f"work_session_paid:{session.session_id}")
            else:
                coworkers = sorted(
                    other_id
                    for other_id, other in context.agents.items()
                    if other_id != agent_id
                    and other.enabled
                    and other.assigned_work_location_id == agent.assigned_work_location_id
                )
                self._stage_event(
                    context,
                    EventType.WORK_MISSED,
                    location_id=agent.assigned_work_location_id,
                    actor_ids=[agent_id],
                    affected_agent_ids=[agent_id],
                    source_action_id=source_action_id,
                    payload={
                        "session_id": session.session_id,
                        "effective_work_minutes": session.effective_work_minutes,
                        "scheduled_work_minutes": scheduled_minutes,
                        "minimum_effective_minutes": minimum,
                        "grace_minutes": session.grace_minutes,
                        "missed_minutes": scheduled_minutes - session.effective_work_minutes,
                    },
                )
                if coworkers:
                    self._stage_event(
                        context,
                        EventType.COWORKER_EXTRA_LOAD,
                        location_id=agent.assigned_work_location_id,
                        actor_ids=[agent_id],
                        affected_agent_ids=coworkers,
                        source_action_id=source_action_id,
                        payload={"session_id": session.session_id, "coworker_ids": ",".join(coworkers)},
                    )
                    for coworker_id in coworkers:
                        self._apply_relationship_delta(
                            context,
                            source_id=coworker_id,
                            target_id=agent_id,
                            deltas={"familiarity": 0.01, "affinity": -0.03, "trust": -0.04, "tension": 0.05},
                        )
                context.changes.append(f"work_session_missed:{session.session_id}")

    def _update_need_crises(self, context: _TickContext) -> None:
        for agent_id in sorted(context.agents):
            agent = context.agents[agent_id]
            active = set(context.active_need_crises.get(agent_id, []))
            for axis, threshold in self.catalog.utility.need_crisis_thresholds.items():
                value = float(getattr(agent.needs, axis.value))
                if value <= threshold and axis not in active:
                    location_id = (
                        agent.home_location_id
                        if agent.current_location_id == "TRAVELING"
                        else agent.current_location_id
                    )
                    self._stage_event(
                        context,
                        EventType.NEED_CRISIS,
                        location_id=location_id,
                        actor_ids=[agent_id],
                        affected_agent_ids=[agent_id],
                        source_action_id=agent.current_action_id,
                        payload={"need": axis.value, "value": value, "threshold": threshold},
                    )
                    active.add(axis)
                elif value > threshold and axis in active:
                    active.remove(axis)
            context.active_need_crises[agent_id] = sorted(active, key=lambda item: item.value)

    def _update_low_resources(self, context: _TickContext) -> None:
        for household_id in sorted(context.households):
            household = context.households[household_id]
            flags = set(context.low_resource_flags.get(household_id, []))
            checks = (
                ("FOOD", household.food_units <= self.catalog.economy.food_low_threshold, EventType.HOUSEHOLD_FOOD_LOW),
                ("MONEY", household.money <= self.catalog.economy.money_low_threshold, EventType.HOUSEHOLD_MONEY_LOW),
            )
            for name, below, event_type in checks:
                if below and name not in flags:
                    self._stage_event(
                        context,
                        event_type,
                        location_id=household.home_location_id,
                        actor_ids=list(household.member_ids),
                        affected_agent_ids=list(household.member_ids),
                        source_action_id=None,
                        payload={
                            "household_id": household_id,
                            "money": household.money,
                            "food_units": household.food_units,
                        },
                    )
                    cast(set[str], flags).add(name)
                elif not below and name in flags:
                    flags.remove(name)
            context.low_resource_flags[household_id] = cast(Any, sorted(flags))

    def _stage_event(
        self,
        context: _TickContext,
        event_type: EventType,
        *,
        location_id: str,
        actor_ids: list[str],
        affected_agent_ids: list[str],
        source_action_id: str | None,
        payload: dict[str, Any],
    ) -> WorldEvent:
        game_day_events = sum(
            1
            for item in [*context.events, *context.staged_events]
            if item.game_minute // 1440 == context.minute // 1440
        )
        if game_day_events >= 1000:
            raise ValueError("M3 event cap exceeded 1,000 events per game day")
        direct = sorted({*actor_ids, *affected_agent_ids})
        config = self._event_config[event_type]
        witnesses: list[str] = []
        if config.witness_scope is EventWitnessScope.HIGH_LEVEL_LOCATION:
            witnesses = sorted(
                agent_id
                for agent_id in context.locations[location_id].current_agent_ids
                if agent_id not in direct and context.agents[agent_id].enabled
            )
        sequence = len(context.events) + len(context.staged_events) + 1
        event = WorldEvent(
            event_id=f"event_{sequence:08d}",
            event_type=event_type,
            game_minute=context.minute,
            location_id=location_id,
            actor_ids=sorted(set(actor_ids)),
            affected_agent_ids=sorted(set(affected_agent_ids)),
            witness_agent_ids=witnesses,
            source_action_id=source_action_id,
            importance=config.default_importance,
            witness_scope=config.witness_scope,
            payload=payload,
            supersedes_event_id=None,
        )
        context.staged_events.append(event)
        for agent_id in direct:
            self._add_knowledge(
                context,
                agent_id=agent_id,
                event_id=event.event_id,
                source_agent_id=None,
                acquisition_type=KnowledgeAcquisitionType.DIRECT_PARTICIPANT,
                confidence=1.0,
            )
        for agent_id in witnesses:
            self._add_knowledge(
                context,
                agent_id=agent_id,
                event_id=event.event_id,
                source_agent_id=actor_ids[0],
                acquisition_type=KnowledgeAcquisitionType.WITNESSED,
                confidence=1.0,
            )
        context.changes.append(f"event_appended:{event.event_id}:{event.event_type.value}")
        return event

    def _add_knowledge(
        self,
        context: _TickContext,
        *,
        agent_id: str,
        event_id: str,
        source_agent_id: str | None,
        acquisition_type: KnowledgeAcquisitionType,
        confidence: float,
    ) -> None:
        key = knowledge_key(agent_id, event_id)
        existing = context.knowledge_records.get(key)
        if existing is None:
            record = KnowledgeRecord(
                agent_id=agent_id,
                event_id=event_id,
                source_agent_id=source_agent_id,
                acquisition_type=acquisition_type,
                confidence=confidence,
                first_known_minute=context.minute,
                last_reinforced_minute=context.minute,
            )
            context.knowledge_records[key] = record
            agent = context.agents[agent_id]
            context.agents[agent_id] = agent.model_copy(update={"known_event_ids": [*agent.known_event_ids, event_id]})
        else:
            context.knowledge_records[key] = existing.model_copy(
                update={
                    "last_reinforced_minute": context.minute,
                    "confidence": max(existing.confidence, confidence),
                }
            )

    def _apply_target_to_actor_relationship(
        self,
        context: _TickContext,
        *,
        source_id: str,
        target_id: str,
        behavior: BehaviorConfig,
        accepted: bool,
    ) -> None:
        deltas = {
            axis.value: midpoint(bounds) if accepted else bounds.minimum
            for axis, bounds in behavior.output_bounds.relationship_target_to_actor.items()
        }
        self._apply_relationship_delta(context, source_id=source_id, target_id=target_id, deltas=deltas)

    def _apply_relationship_delta(
        self,
        context: _TickContext,
        *,
        source_id: str,
        target_id: str,
        deltas: Mapping[str, float],
    ) -> None:
        updated: list[RelationshipState] = []
        found = False
        for edge in context.relationships:
            if edge.source_agent_id == source_id and edge.target_agent_id == target_id:
                values = {
                    axis: round(max(0.0, min(1.0, float(getattr(edge, axis)) + float(deltas.get(axis, 0.0)))), 9)
                    for axis in ("familiarity", "affinity", "trust", "tension")
                }
                edge = edge.model_copy(update={**values, "last_interaction_minute": context.minute})
                found = True
            updated.append(edge)
        if not found:
            raise ValueError("directed relationship edge is missing")
        context.relationships = updated
        context.changes.append(f"relationship_updated:{source_id}:{target_id}")

    def _relationship(self, context: _TickContext, source_id: str, target_id: str) -> RelationshipState:
        return next(
            edge
            for edge in context.relationships
            if edge.source_agent_id == source_id and edge.target_agent_id == target_id
        )

    def _decision_work_session(self, context: _TickContext, agent_id: str) -> WorkSessionRecord | None:
        schedule = self._schedules[agent_id]
        current_day = context.minute // 1440
        for day in range(current_day, current_day + 8):
            if day % 7 not in schedule.weekdays:
                continue
            start = (day * 1440) + schedule.start_minute_of_day
            end = (day * 1440) + schedule.end_minute_of_day
            if context.minute >= end:
                continue
            session_id = f"work_session_{agent_id}_day_{day:04d}"
            existing = context.work_sessions.get(session_id)
            if existing is not None:
                return existing
            if context.minute >= start - 60:
                return self._work_session(context, agent_id, day)
            return WorkSessionRecord(
                session_id=session_id,
                agent_id=agent_id,
                day=day,
                start_game_minute=start,
                end_game_minute=end,
                grace_minutes=schedule.grace_minutes,
            )
        return None

    def _work_session(self, context: _TickContext, agent_id: str, day: int) -> WorkSessionRecord:
        session_id = f"work_session_{agent_id}_day_{day:04d}"
        existing = context.work_sessions.get(session_id)
        if existing is not None:
            return existing
        schedule = self._schedules[agent_id]
        session = WorkSessionRecord(
            session_id=session_id,
            agent_id=agent_id,
            day=day,
            start_game_minute=(day * 1440) + schedule.start_minute_of_day,
            end_game_minute=(day * 1440) + schedule.end_minute_of_day,
            grace_minutes=schedule.grace_minutes,
        )
        context.work_sessions[session_id] = session
        return session

    def _reserved_household(self, context: _TickContext, household_id: str) -> tuple[int, int]:
        money = 0
        food = 0
        for reservation in context.reservations.values():
            if reservation.kind == "HOUSEHOLD_RESOURCE" and reservation.household_id == household_id:
                money += reservation.money_units
                food += reservation.food_units
        return money, food

    def _resource_costs(
        self,
        context: _TickContext,
        candidate: SocietyCandidate,
        participants: Sequence[str],
        force_joint: bool,
    ) -> dict[str, tuple[int, int]]:
        base = candidate.candidate
        actor = context.agents[base.actor_id]
        money = max(0, -base.hard_cost_preview.household_money)
        food = max(0, -base.hard_cost_preview.household_food_units)
        costs: dict[str, tuple[int, int]] = {actor.household_id: (money, food)} if money or food else {}
        if force_joint and base.behavior_id in {BehaviorId.EAT_AT_CAFE, BehaviorId.DRINK_AT_BAR}:
            for participant_id in participants:
                household_id = context.agents[participant_id].household_id
                current_money, current_food = costs.get(household_id, (0, 0))
                price = (
                    self.catalog.economy.cafe_meal.price
                    if base.behavior_id is BehaviorId.EAT_AT_CAFE
                    else self.catalog.economy.bar_drink.price
                )
                if participant_id == base.actor_id:
                    continue
                costs[household_id] = (current_money + price, current_food)
        return costs

    @staticmethod
    def _slot_quantity(
        obj: InteractionObjectState,
        behavior_id: BehaviorId,
        participants: Sequence[str],
        force_joint: bool,
    ) -> int:
        if (
            behavior_id
            in {
                BehaviorId.GREET,
                BehaviorId.CHAT,
                BehaviorId.JOKE,
                BehaviorId.COMPLIMENT,
                BehaviorId.SHARE_EVENT,
                BehaviorId.INVITE_JOIN,
                BehaviorId.APOLOGIZE,
                BehaviorId.CONFRONT,
                BehaviorId.END_CONVERSATION,
            }
            and obj.object_type is ObjectType.CONVERSATION_ANCHOR
        ):
            return len(participants)
        if force_joint and obj.object_type in {
            ObjectType.DINING_SEAT,
            ObjectType.PUBLIC_SEAT,
            ObjectType.SOFA,
            ObjectType.LEISURE_SPOT,
        }:
            return len(participants)
        return 1

    def _add_reservation(
        self,
        context: _TickContext,
        *,
        owner_action_id: str,
        kind: str,
        expires_at: int,
        object_id: str | None = None,
        slot_index: int | None = None,
        household_id: str | None = None,
        money_units: int = 0,
        food_units: int = 0,
        location_id: str | None = None,
        participant_agent_id: str | None = None,
    ) -> str:
        reservation_id = f"reservation_{context.bump('reservation'):08d}"
        context.reservations[reservation_id] = ReservationRecord(
            reservation_id=reservation_id,
            owner_action_id=owner_action_id,
            kind=cast(Any, kind),
            object_id=object_id,
            slot_index=slot_index,
            household_id=household_id,
            money_units=money_units,
            food_units=food_units,
            location_id=location_id,
            participant_agent_id=participant_agent_id,
            valid_from_game_minute=context.minute,
            expires_at_game_minute=expires_at,
        )
        return reservation_id

    def _set_phase(self, context: _TickContext, action_id: str, phase: ActionPhase) -> None:
        action = context.active_actions[action_id]
        updated = action.model_copy(update={"phase": phase})
        context.active_actions[action_id] = updated
        if action_id in context.joint_actions and phase is ActionPhase.PERFORMING:
            context.joint_actions[action_id] = context.joint_actions[action_id].model_copy(
                update={"status": "PERFORMING"}
            )
        self._record_phase(context, updated, phase)

    def _record_phase(
        self,
        context: _TickContext,
        action: ActionState,
        phase: ActionPhase,
        *,
        failure_reason: str | None = None,
    ) -> None:
        runtime = context.action_runtimes.get(action.action_id)
        context.actions.append(
            {
                "action_id": action.action_id,
                "game_minute": context.minute,
                "agent_ids": list(action.agent_ids),
                "behavior_id": action.behavior_id.value,
                "phase": phase.value,
                "target_object_ids": list(action.target_object_ids),
                "reservation_ids": list(runtime.reservation_ids) if runtime is not None else [],
                "joint": runtime.joint if runtime is not None else False,
                "failure_reason": failure_reason,
            }
        )

    def _destination_for_behavior(self, state: WorldState, actor_id: str, behavior_id: BehaviorId) -> str:
        agent = state.agents[actor_id]
        if behavior_id is BehaviorId.WATCH_TV:
            return agent.home_location_id
        if behavior_id in {BehaviorId.EAT_AT_CAFE, BehaviorId.DRINK_AT_BAR}:
            return self.rulebook.location_by_type[LocationType.CAFE_BAR]
        if behavior_id in {BehaviorId.WALK_IN_PARK, BehaviorId.SIT_IN_PARK}:
            return self.rulebook.location_by_type[LocationType.PARK]
        raise ValueError(f"unsupported invited joint activity: {behavior_id.value}")

    def _hard_cost_preview(self, behavior_id: BehaviorId) -> HardCostPreview:
        if behavior_id is BehaviorId.EAT_AT_CAFE:
            return HardCostPreview(household_money=-self.catalog.economy.cafe_meal.price)
        if behavior_id is BehaviorId.DRINK_AT_BAR:
            return HardCostPreview(household_money=-self.catalog.economy.bar_drink.price)
        return HardCostPreview()

    @staticmethod
    def _resolver_priority(scored: ScoredSocietyCandidate) -> tuple[object, ...]:
        candidate = scored.candidate.candidate
        return (
            0 if candidate.behavior_id is BehaviorId.WORK_SHIFT else 1,
            -scored.total_score,
            -scored.tie_break,
            candidate.actor_id,
            candidate.candidate_id,
        )

    @staticmethod
    def _numeric_id(value: str) -> int:
        return int(value.rsplit("_", 1)[1])

    _social_behaviors = frozenset(
        {
            BehaviorId.GREET,
            BehaviorId.CHAT,
            BehaviorId.JOKE,
            BehaviorId.COMPLIMENT,
            BehaviorId.SHARE_EVENT,
            BehaviorId.INVITE_JOIN,
            BehaviorId.APOLOGIZE,
            BehaviorId.CONFRONT,
            BehaviorId.END_CONVERSATION,
        }
    )
