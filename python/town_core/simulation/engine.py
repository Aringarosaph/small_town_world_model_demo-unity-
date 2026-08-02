"""Deterministic one-NPC M1 authority engine."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from town_core.decision.candidates import CandidateEnumerator, WorkWindow
from town_core.decision.outcomes import HeuristicOutcomeProvider
from town_core.decision.resolver import CentralResolver, Resolution, SlotReservation
from town_core.decision.utility import ScoredCandidate, UtilityScorer
from town_core.domain.config_models import CatalogBundle, MoodValues, NeedValues, ScheduleEntry
from town_core.domain.decision_models import (
    ActionProposal,
    CandidateAction,
    HardEffect,
    ResolvedAction,
    StateTransaction,
)
from town_core.domain.enums import (
    ActionPhase,
    BehaviorId,
    EventType,
    EventWitnessScope,
    KnowledgeAcquisitionType,
    MoodAxis,
    MovementCancellationReason,
    MovementFailureReason,
    NeedName,
    ProposalResult,
)
from town_core.domain.state_models import (
    ActionState,
    KnowledgeRecord,
    WorldEvent,
    WorldState,
)
from town_core.events import EventLedger
from town_core.simulation.clock import RuntimeMode, accept_advanced_game_minute
from town_core.simulation.initialization import catalog_hash
from town_core.simulation.invariants import assert_live_input_transition, assert_transition, assert_world_invariants
from town_core.simulation.transactions import build_transaction_record


@dataclass(slots=True)
class _ActionRuntime:
    action_id: str
    proposal_id: str
    candidate: CandidateAction
    reservations: tuple[SlotReservation, ...]
    reserved_food_units: int
    travel_arrival_minute: int
    perform_start_minute: int
    work_session_id: str | None
    origin_location_id: str


@dataclass(slots=True)
class _WorkSession:
    session_id: str
    day: int
    start_game_minute: int
    end_game_minute: int
    grace_minutes: int
    effective_work_minutes: int = 0
    first_work_minute: int | None = None
    started_event_emitted: bool = False
    late_event_emitted: bool = False
    finalized: bool = False
    paid: bool = False
    proposal_ids: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)

    def as_window(self) -> WorkWindow:
        return WorkWindow(
            session_id=self.session_id,
            day=self.day,
            start_game_minute=self.start_game_minute,
            end_game_minute=self.end_game_minute,
            grace_minutes=self.grace_minutes,
            effective_work_minutes=self.effective_work_minutes,
            finalized=self.finalized,
        )


@dataclass(frozen=True, slots=True)
class AdvanceResult:
    previous_game_minute: int
    target_game_minute: int
    transactions: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    actions: tuple[dict[str, Any], ...]
    events: tuple[WorldEvent, ...]


class _TickContext:
    def __init__(self, engine: SimulationEngine, minute: int) -> None:
        self.source = engine.state
        self.minute = minute
        self.agents = dict(self.source.agents)
        self.households = dict(self.source.households)
        self.locations = dict(self.source.locations)
        self.objects = dict(self.source.objects)
        self.active_actions = dict(self.source.active_actions)
        self.action_runtimes = copy.deepcopy(engine._action_runtimes)
        self.work_sessions = copy.deepcopy(engine._work_sessions)
        self.reserved_food_by_household = dict(engine._reserved_food_by_household)
        self.active_need_crises = set(engine._active_need_crises)
        self.recent_behavior = engine._recent_behavior
        self.knowledge_records = list(engine._knowledge_records)
        self.events: list[WorldEvent] = []
        self.changes: list[str] = []
        self.decisions: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.state_transactions: list[dict[str, Any]] = []

    def provisional_state(self) -> WorldState:
        return WorldState(
            schema_version=self.source.schema_version,
            world_id=self.source.world_id,
            game_minute=self.minute,
            random_seed=self.source.random_seed,
            state_version=self.source.state_version,
            agents=self.agents,
            households=self.households,
            locations=self.locations,
            objects=self.objects,
            relationships=self.source.relationships,
            active_actions=self.active_actions,
            dialogue_session_ids=self.source.dialogue_session_ids,
            event_cursor=self.source.event_cursor + len(self.events),
            model_version=self.source.model_version,
            config_hash=self.source.config_hash,
        )


class SimulationEngine:
    """Advance one enabled M1 agent using absolute game-minute inputs."""

    def __init__(
        self,
        catalog: CatalogBundle,
        state: WorldState,
        *,
        active_agent_id: str = "npc_01",
        runtime_mode: RuntimeMode = RuntimeMode.HEADLESS_FAST,
        movement_timeout_minutes: int = 15,
    ) -> None:
        if state.config_hash != catalog_hash(catalog):
            raise ValueError("initial state/config hash mismatch")
        if state.active_actions:
            raise ValueError("M1 engine starts only from an action-free initial snapshot")
        self.catalog = catalog
        self.state = state
        self.active_agent_id = active_agent_id
        self.runtime_mode = runtime_mode
        if movement_timeout_minutes <= 0:
            raise ValueError("movement timeout must be positive")
        self.movement_timeout_minutes = movement_timeout_minutes
        self.ledger = EventLedger(catalog)
        self._enumerator = CandidateEnumerator(catalog)
        self._outcomes = HeuristicOutcomeProvider(catalog)
        self._scorer = UtilityScorer(catalog)
        self._resolver = CentralResolver(catalog)
        self._event_scopes = {item.event_type: item.witness_scope for item in catalog.events.event_types}
        schedule_id = state.agents[active_agent_id].schedule_id
        schedule = next(item for item in catalog.schedules.schedules if item.schedule_id == schedule_id)
        self._schedule_entry: ScheduleEntry = schedule.entries[0]
        self._action_runtimes: dict[str, _ActionRuntime] = {}
        self._work_sessions: dict[str, _WorkSession] = {}
        self._reserved_food_by_household: dict[str, int] = {}
        self._active_need_crises: set[NeedName] = set()
        self._recent_behavior: BehaviorId | None = None
        self._knowledge_records: list[KnowledgeRecord] = []
        self._action_counter = 0
        self._decision_counter = 0
        self._proposal_counter = 0
        assert_world_invariants(state, active_agent_id=active_agent_id, events=self.ledger.events)

    def report_movement_arrived(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        object_id: str | None,
        slot_index: int | None,
    ) -> AdvanceResult:
        """Commit a validated Unity arrival without advancing ``game_minute``."""

        runtime, action = self._validate_live_movement_report(
            action_id=action_id,
            agent_id=agent_id,
            expected_state_version=expected_state_version,
        )
        expected_slots = {(item.object_id, item.slot_index) for item in runtime.reservations}
        if expected_slots and object_id is None:
            raise ValueError("movement arrival must acknowledge an authoritative interaction slot")
        if object_id is None and slot_index is not None:
            raise ValueError("movement arrival slot requires an object_id")
        if object_id is not None and (object_id, slot_index) not in expected_slots:
            raise ValueError("movement arrival does not match an authoritative reservation")
        context = _TickContext(self, self.state.game_minute)
        perform_start = max(context.minute, runtime.perform_start_minute)
        context.action_runtimes[action_id].perform_start_minute = perform_start
        context.active_actions[action_id] = action.model_copy(
            update={"planned_end_game_minute": perform_start + runtime.candidate.estimated_duration_minutes}
        )
        self._arrive(context, context.action_runtimes[action_id])
        context.changes.append(f"movement_arrived:{action_id}")
        return self._commit_live_input(context)

    def report_movement_failed(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        reason: MovementFailureReason,
    ) -> AdvanceResult:
        """Commit a validated Unity navigation failure as an authority transaction."""

        runtime, _ = self._validate_live_movement_report(
            action_id=action_id,
            agent_id=agent_id,
            expected_state_version=expected_state_version,
        )
        context = _TickContext(self, self.state.game_minute)
        self._fail_traveling_action(context, context.action_runtimes[runtime.action_id], reason)
        return self._commit_live_input(context)

    def report_movement_cancelled(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        reason: MovementCancellationReason,
    ) -> AdvanceResult:
        """Commit one typed Unity cancellation report as a Python authority decision."""

        runtime, _ = self._validate_live_movement_report(
            action_id=action_id,
            agent_id=agent_id,
            expected_state_version=expected_state_version,
            allow_stale_version=True,
        )
        context = _TickContext(self, self.state.game_minute)
        self._cancel_traveling_action(context, context.action_runtimes[runtime.action_id], reason)
        return self._commit_live_input(context)

    def _validate_live_movement_report(
        self,
        *,
        action_id: str,
        agent_id: str,
        expected_state_version: int,
        allow_stale_version: bool = False,
    ) -> tuple[_ActionRuntime, ActionState]:
        if self.runtime_mode is not RuntimeMode.UNITY_LIVE:
            raise ValueError("movement reports are accepted only in UNITY_LIVE mode")
        if expected_state_version > self.state.state_version:
            raise ValueError("movement report state_version is from the future")
        if not allow_stale_version and expected_state_version != self.state.state_version:
            raise ValueError("movement report state_version is stale")
        if agent_id != self.active_agent_id:
            raise ValueError("movement report agent is not the active M2 agent")
        action = self.state.active_actions.get(action_id)
        runtime = self._action_runtimes.get(action_id)
        if action is None or runtime is None:
            raise ValueError("movement report references an unknown or terminal action")
        if action.agent_ids != [agent_id]:
            raise ValueError("movement report action/agent mismatch")
        if action.phase is not ActionPhase.TRAVELING:
            raise ValueError("movement report is valid only during TRAVELING")
        return runtime, action

    def _commit_live_input(self, context: _TickContext) -> AdvanceResult:
        committed = context.provisional_state().model_copy(update={"state_version": self.state.state_version + 1})
        committed = WorldState.model_validate(committed.model_dump(mode="json", exclude_none=False))
        all_events = (*self.ledger.events, *context.events)
        assert_live_input_transition(self.state, committed)
        assert_world_invariants(committed, active_agent_id=self.active_agent_id, events=all_events)
        self.ledger.commit(context.events)

        source = self.state
        self.state = committed
        self._action_runtimes = context.action_runtimes
        self._work_sessions = context.work_sessions
        self._reserved_food_by_household = context.reserved_food_by_household
        self._active_need_crises = context.active_need_crises
        self._recent_behavior = context.recent_behavior
        self._knowledge_records = context.knowledge_records
        transaction = build_transaction_record(
            source,
            committed,
            committed_event_ids=[event.event_id for event in context.events],
            changes=context.changes,
            state_transaction=None,
        )
        for record in context.actions:
            record["state_version"] = committed.state_version
        return AdvanceResult(
            previous_game_minute=source.game_minute,
            target_game_minute=committed.game_minute,
            transactions=(transaction,),
            decisions=(),
            actions=tuple(context.actions),
            events=tuple(context.events),
        )

    @property
    def knowledge_records(self) -> tuple[KnowledgeRecord, ...]:
        return tuple(self._knowledge_records)

    @property
    def work_sessions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "session_id": session.session_id,
                "day": session.day,
                "start_game_minute": session.start_game_minute,
                "end_game_minute": session.end_game_minute,
                "effective_work_minutes": session.effective_work_minutes,
                "first_work_minute": session.first_work_minute,
                "grace_minutes": session.grace_minutes,
                "late": session.late_event_emitted,
                "finalized": session.finalized,
                "paid": session.paid,
                "action_ids": list(session.action_ids),
            }
            for session in sorted(self._work_sessions.values(), key=lambda item: item.session_id)
        )

    def advance_to(self, target_game_minute: int) -> AdvanceResult:
        advance = accept_advanced_game_minute(self.state.game_minute, target_game_minute)
        transactions: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        events: list[WorldEvent] = []
        for minute in advance.minutes():
            result = self._advance_one_minute(minute)
            transactions.extend(result.transactions)
            decisions.extend(result.decisions)
            actions.extend(result.actions)
            events.extend(result.events)
        return AdvanceResult(
            previous_game_minute=advance.previous_game_minute,
            target_game_minute=advance.target_game_minute,
            transactions=tuple(transactions),
            decisions=tuple(decisions),
            actions=tuple(actions),
            events=tuple(events),
        )

    def _advance_one_minute(self, minute: int) -> AdvanceResult:
        context = _TickContext(self, minute)
        self._apply_need_changes(context)
        self._progress_action(context)
        self._finalize_work_session_if_due(context)
        self._update_need_crises(context)
        self._decide_if_available(context)

        committed = context.provisional_state().model_copy(update={"state_version": self.state.state_version + 1})
        committed = WorldState.model_validate(committed.model_dump(mode="json", exclude_none=False))
        all_events = (*self.ledger.events, *context.events)
        assert_transition(self.state, committed)
        assert_world_invariants(committed, active_agent_id=self.active_agent_id, events=all_events)
        self.ledger.commit(context.events)

        source = self.state
        self.state = committed
        self._action_runtimes = context.action_runtimes
        self._work_sessions = context.work_sessions
        self._reserved_food_by_household = context.reserved_food_by_household
        self._active_need_crises = context.active_need_crises
        self._recent_behavior = context.recent_behavior
        self._knowledge_records = context.knowledge_records

        state_transaction: dict[str, Any] | None
        if not context.state_transactions:
            state_transaction = None
        elif len(context.state_transactions) == 1:
            state_transaction = context.state_transactions[0]
        else:
            state_transaction = {"batch": context.state_transactions}
        transaction = build_transaction_record(
            source,
            committed,
            committed_event_ids=[event.event_id for event in context.events],
            changes=context.changes,
            state_transaction=state_transaction,
        )
        for record in context.decisions:
            record["committed_state_version"] = committed.state_version
        for record in context.actions:
            record["state_version"] = committed.state_version
        return AdvanceResult(
            previous_game_minute=source.game_minute,
            target_game_minute=minute,
            transactions=(transaction,),
            decisions=tuple(context.decisions),
            actions=tuple(context.actions),
            events=tuple(context.events),
        )

    def _apply_need_changes(self, context: _TickContext) -> None:
        agent = context.agents[self.active_agent_id]
        active = context.active_actions.get(agent.current_action_id or "")
        sleeping = (
            active is not None and active.phase is ActionPhase.PERFORMING and active.behavior_id is BehaviorId.SLEEP
        )
        values = agent.needs.model_dump()
        for axis, delta in self._outcomes.passive_decay_per_minute.items():
            if axis is NeedName.ENERGY and sleeping:
                continue
            values[axis.value] += delta
        if active is not None and active.phase is ActionPhase.PERFORMING:
            for axis, delta in self._outcomes.continuous_need_delta_per_minute(active.behavior_id).items():
                values[axis.value] += delta
            if active.behavior_id is BehaviorId.WORK_SHIFT:
                runtime = context.action_runtimes[active.action_id]
                if runtime.work_session_id is not None:
                    session = context.work_sessions[runtime.work_session_id]
                    if session.start_game_minute < context.minute <= session.end_game_minute:
                        session.effective_work_minutes += 1
        bounded = {key: round(max(0.0, min(1.0, float(value))), 9) for key, value in values.items()}
        context.agents[self.active_agent_id] = agent.model_copy(update={"needs": NeedValues(**bounded)})
        context.changes.append("active_agent_need_tick")

    def _progress_action(self, context: _TickContext) -> None:
        agent = context.agents[self.active_agent_id]
        if agent.current_action_id is None:
            return
        action = context.active_actions[agent.current_action_id]
        runtime = context.action_runtimes[action.action_id]
        if action.phase is ActionPhase.TRAVELING:
            if self.runtime_mode is RuntimeMode.UNITY_LIVE:
                timeout = runtime.travel_arrival_minute + self.movement_timeout_minutes
                if context.minute >= timeout:
                    self._fail_traveling_action(context, runtime, MovementFailureReason.TIMEOUT)
                return
            if context.minute >= runtime.travel_arrival_minute:
                self._arrive(context, runtime)
                action = context.active_actions[action.action_id]
        if action.phase is ActionPhase.ALIGNING and context.minute >= runtime.perform_start_minute:
            self._start_performing(context, runtime)
            action = context.active_actions[action.action_id]
        if (
            action.phase is ActionPhase.PERFORMING
            and action.planned_end_game_minute is not None
            and context.minute >= action.planned_end_game_minute
        ):
            self._resolve_action(context, runtime)

    def _arrive(self, context: _TickContext, runtime: _ActionRuntime) -> None:
        action = context.active_actions[runtime.action_id]
        destination = action.destination_location_id
        if destination is None:
            raise ValueError("traveling action is missing destination")
        agent = context.agents[self.active_agent_id]
        context.agents[self.active_agent_id] = agent.model_copy(update={"current_location_id": destination})
        location = context.locations[destination]
        context.locations[destination] = location.model_copy(
            update={"current_agent_ids": sorted({*location.current_agent_ids, self.active_agent_id})}
        )
        if context.minute < runtime.perform_start_minute:
            self._set_action_phase(context, runtime.action_id, ActionPhase.ALIGNING)
        else:
            self._start_performing(context, runtime)
        context.changes.append(f"action_arrived:{runtime.action_id}")

    def _fail_traveling_action(
        self,
        context: _TickContext,
        runtime: _ActionRuntime,
        reason: MovementFailureReason,
    ) -> None:
        action = context.active_actions[runtime.action_id]
        if action.phase is not ActionPhase.TRAVELING:
            raise ValueError("only a traveling action can fail movement")
        self._release_reservations(context, runtime)
        self._record_action_phase(context, action, ActionPhase.FAILED, failure_reason=reason.value)
        context.active_actions.pop(runtime.action_id)
        context.action_runtimes.pop(runtime.action_id)
        origin = context.locations[runtime.origin_location_id]
        context.locations[runtime.origin_location_id] = origin.model_copy(
            update={"current_agent_ids": sorted({*origin.current_agent_ids, self.active_agent_id})}
        )
        agent = context.agents[self.active_agent_id]
        context.agents[self.active_agent_id] = agent.model_copy(
            update={
                "current_location_id": runtime.origin_location_id,
                "current_action_id": None,
                "decision_due_at": context.minute,
            }
        )
        context.recent_behavior = action.behavior_id
        context.changes.append(f"movement_failed:{runtime.action_id}:{reason.value}")

    def _cancel_traveling_action(
        self,
        context: _TickContext,
        runtime: _ActionRuntime,
        reason: MovementCancellationReason,
    ) -> None:
        action = context.active_actions[runtime.action_id]
        if action.phase is not ActionPhase.TRAVELING:
            raise ValueError("only a traveling action can be cancelled by a movement report")
        self._release_reservations(context, runtime)
        self._record_action_phase(context, action, ActionPhase.CANCELLED, failure_reason=reason.value)
        context.active_actions.pop(runtime.action_id)
        context.action_runtimes.pop(runtime.action_id)
        origin = context.locations[runtime.origin_location_id]
        context.locations[runtime.origin_location_id] = origin.model_copy(
            update={"current_agent_ids": sorted({*origin.current_agent_ids, self.active_agent_id})}
        )
        agent = context.agents[self.active_agent_id]
        context.agents[self.active_agent_id] = agent.model_copy(
            update={
                "current_location_id": runtime.origin_location_id,
                "current_action_id": None,
                "decision_due_at": context.minute,
            }
        )
        context.recent_behavior = action.behavior_id
        context.changes.append(f"movement_cancelled:{runtime.action_id}:{reason.value}")

    def _start_performing(self, context: _TickContext, runtime: _ActionRuntime) -> None:
        self._set_action_phase(context, runtime.action_id, ActionPhase.PERFORMING)
        action = context.active_actions[runtime.action_id]
        if action.behavior_id is not BehaviorId.WORK_SHIFT or runtime.work_session_id is None:
            return
        session = context.work_sessions[runtime.work_session_id]
        first_start = session.first_work_minute is None
        if first_start:
            session.first_work_minute = context.minute
        if not session.started_event_emitted:
            self._stage_event(
                context,
                EventType.WORK_STARTED,
                location_id=context.agents[self.active_agent_id].assigned_work_location_id,
                source_action_id=runtime.action_id,
                payload={
                    "session_id": session.session_id,
                    "scheduled_start": session.start_game_minute,
                    "actual_start": context.minute,
                },
            )
            session.started_event_emitted = True
        if first_start and context.minute > session.start_game_minute and not session.late_event_emitted:
            self._stage_event(
                context,
                EventType.WORK_LATE,
                location_id=context.agents[self.active_agent_id].assigned_work_location_id,
                source_action_id=runtime.action_id,
                payload={
                    "session_id": session.session_id,
                    "scheduled_start": session.start_game_minute,
                    "arrival_minute": context.minute,
                    "late_minutes": context.minute - session.start_game_minute,
                },
            )
            session.late_event_emitted = True

    def _resolve_action(self, context: _TickContext, runtime: _ActionRuntime) -> None:
        action = context.active_actions[runtime.action_id]
        self._set_action_phase(context, runtime.action_id, ActionPhase.RESOLVING)
        emitted: list[WorldEvent] = []
        hard_effects: list[HardEffect] = []
        terminal = ActionPhase.COMPLETED
        failure_reason: str | None = None
        if action.behavior_id is BehaviorId.EAT_AT_HOME:
            agent = context.agents[self.active_agent_id]
            household = context.households[agent.household_id]
            if household.food_units < runtime.reserved_food_units:
                terminal = ActionPhase.FAILED
                failure_reason = "INSUFFICIENT_RESERVED_FOOD_AT_RESOLUTION"
            else:
                context.households[agent.household_id] = household.model_copy(
                    update={"food_units": household.food_units - runtime.reserved_food_units}
                )
                self._apply_completion_effects(context, BehaviorId.EAT_AT_HOME)
                event = self._stage_event(
                    context,
                    EventType.MEAL_CONSUMED,
                    location_id=agent.home_location_id,
                    source_action_id=runtime.action_id,
                    payload={"food_units": runtime.reserved_food_units},
                )
                emitted.append(event)
                hard_effects.append(
                    HardEffect(
                        field_path=f"households.{agent.household_id}.food_units",
                        delta_integer=-runtime.reserved_food_units,
                    )
                )
        self._release_reservations(context, runtime)
        self._record_action_phase(context, action, terminal, failure_reason=failure_reason)
        context.active_actions.pop(runtime.action_id)
        context.action_runtimes.pop(runtime.action_id)
        agent = context.agents[self.active_agent_id]
        context.agents[self.active_agent_id] = agent.model_copy(
            update={"current_action_id": None, "decision_due_at": context.minute}
        )
        context.recent_behavior = action.behavior_id
        context.changes.append(f"action_terminal:{runtime.action_id}:{terminal.value}")
        if hard_effects or emitted:
            resolved = ResolvedAction(
                action_id=runtime.action_id,
                source_proposal_ids=[runtime.proposal_id],
                result=ProposalResult.ACCEPTED,
                hard_effects=hard_effects,
                soft_effects=[],
                emitted_events=emitted,
            )
            transaction = StateTransaction(
                expected_state_version=context.source.state_version,
                resolved_actions=[resolved],
                committed_event_ids=[event.event_id for event in emitted],
            )
            context.state_transactions.append(transaction.model_dump(mode="json", exclude_none=False))

    def _apply_completion_effects(self, context: _TickContext, behavior_id: BehaviorId) -> None:
        agent = context.agents[self.active_agent_id]
        needs = agent.needs.model_dump()
        for axis, delta in self._outcomes.completion_need_deltas(behavior_id).items():
            needs[axis.value] = round(max(0.0, min(1.0, float(needs[axis.value]) + delta)), 9)
        mood = agent.mood.model_dump()
        behavior = self._enumerator.behavior(behavior_id)
        for mood_axis, delta in self._outcomes.completion_mood_deltas(behavior).items():
            lower = -1.0 if mood_axis is MoodAxis.VALENCE else 0.0
            mood[mood_axis.value] = round(max(lower, min(1.0, float(mood[mood_axis.value]) + delta)), 9)
        context.agents[self.active_agent_id] = agent.model_copy(
            update={"needs": NeedValues(**needs), "mood": MoodValues(**mood)}
        )

    def _finalize_work_session_if_due(self, context: _TickContext) -> None:
        day = context.minute // 1440
        if day % 7 not in self._schedule_entry.weekdays:
            return
        end = (day * 1440) + self._schedule_entry.end_minute_of_day
        if context.minute != end:
            return
        session = self._work_session(context, day)
        if session.finalized:
            return
        scheduled_minutes = session.end_game_minute - session.start_game_minute
        session.finalized = True
        location_id = context.agents[self.active_agent_id].assigned_work_location_id
        source_action_id = session.action_ids[-1] if session.action_ids else None
        minimum_effective_minutes = scheduled_minutes - session.grace_minutes
        arrived_within_grace = (
            session.first_work_minute is not None
            and session.first_work_minute <= session.start_game_minute + session.grace_minutes
        )
        if arrived_within_grace and session.effective_work_minutes >= minimum_effective_minutes:
            agent = context.agents[self.active_agent_id]
            household = context.households[agent.household_id]
            wage = self.catalog.economy.fixed_shift_wage
            context.households[agent.household_id] = household.model_copy(update={"money": household.money + wage})
            session.paid = True
            event = self._stage_event(
                context,
                EventType.WORK_COMPLETED,
                location_id=location_id,
                source_action_id=source_action_id,
                payload={
                    "session_id": session.session_id,
                    "effective_work_minutes": session.effective_work_minutes,
                    "scheduled_work_minutes": scheduled_minutes,
                    "minimum_effective_minutes": minimum_effective_minutes,
                    "grace_minutes": session.grace_minutes,
                    "wage_minor_units": wage,
                },
            )
            context.changes.append(f"work_session_paid:{session.session_id}")
            if source_action_id is not None and session.proposal_ids:
                resolved = ResolvedAction(
                    action_id=source_action_id,
                    source_proposal_ids=session.proposal_ids,
                    result=ProposalResult.ACCEPTED,
                    hard_effects=[
                        HardEffect(
                            field_path=f"households.{agent.household_id}.money",
                            delta_integer=wage,
                        )
                    ],
                    soft_effects=[],
                    emitted_events=[event],
                )
                transaction = StateTransaction(
                    expected_state_version=context.source.state_version,
                    resolved_actions=[resolved],
                    committed_event_ids=[event.event_id],
                )
                context.state_transactions.append(transaction.model_dump(mode="json", exclude_none=False))
        else:
            self._stage_event(
                context,
                EventType.WORK_MISSED,
                location_id=location_id,
                source_action_id=source_action_id,
                payload={
                    "session_id": session.session_id,
                    "effective_work_minutes": session.effective_work_minutes,
                    "scheduled_work_minutes": scheduled_minutes,
                    "minimum_effective_minutes": minimum_effective_minutes,
                    "grace_minutes": session.grace_minutes,
                    "missed_minutes": scheduled_minutes - session.effective_work_minutes,
                },
            )
            context.changes.append(f"work_session_missed:{session.session_id}")

    def _update_need_crises(self, context: _TickContext) -> None:
        agent = context.agents[self.active_agent_id]
        for axis, threshold in self.catalog.utility.need_crisis_thresholds.items():
            value = float(getattr(agent.needs, axis.value))
            if value <= threshold and axis not in context.active_need_crises:
                self._stage_event(
                    context,
                    EventType.NEED_CRISIS,
                    location_id=(
                        agent.home_location_id
                        if agent.current_location_id == "TRAVELING"
                        else agent.current_location_id
                    ),
                    source_action_id=agent.current_action_id,
                    payload={"need": axis.value, "value": value, "threshold": threshold},
                )
                context.active_need_crises.add(axis)
            elif value > threshold and axis in context.active_need_crises:
                context.active_need_crises.remove(axis)

    def _decide_if_available(self, context: _TickContext) -> None:
        if context.agents[self.active_agent_id].current_action_id is not None:
            return
        work_window = self._next_work_window(context)
        state = context.provisional_state()
        agent = state.agents[self.active_agent_id]
        reserved_food = context.reserved_food_by_household.get(agent.household_id, 0)
        candidates = self._enumerator.enumerate(
            state,
            self.active_agent_id,
            work_window=work_window,
            reserved_food_units=reserved_food,
        )
        if not candidates:
            raise ValueError("M1 candidate enumeration lost the idle fallback")
        self._decision_counter += 1
        decision_id = f"decision_{self._decision_counter:08d}"
        predictions = {
            candidate.candidate_id: self._outcomes.predict(
                state,
                candidate,
                prediction_sequence=(self._decision_counter * 100) + ordinal,
            )
            for ordinal, candidate in enumerate(candidates, start=1)
        }
        scored = self._scorer.score_all(
            state,
            candidates,
            predictions,
            work_window=work_window,
            recent_behavior=context.recent_behavior,
        )
        attempts: list[dict[str, str]] = []
        accepted: tuple[ScoredCandidate, Resolution] | None = None
        for scored_candidate in scored[:2]:
            proposal = self._proposal(state, scored_candidate)
            resolution = self._resolver.resolve(
                state,
                proposal,
                scored_candidate.candidate,
                reserved_food_units=reserved_food,
                work_window=work_window,
            )
            attempts.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "candidate_id": proposal.candidate_id,
                    "result": resolution.result.value,
                }
            )
            if resolution.result is ProposalResult.ACCEPTED:
                accepted = (scored_candidate, resolution)
                break
        if accepted is None:
            idle = next(item for item in scored if item.candidate.behavior_id is BehaviorId.IDLE)
            proposal = self._proposal(state, idle)
            resolution = self._resolver.resolve(
                state,
                proposal,
                idle.candidate,
                reserved_food_units=reserved_food,
                work_window=work_window,
            )
            attempts.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "candidate_id": proposal.candidate_id,
                    "result": resolution.result.value,
                }
            )
            if resolution.result is not ProposalResult.ACCEPTED:
                raise ValueError("central Resolver rejected the idle fallback")
            accepted = (idle, resolution)

        selected, resolution = accepted
        self._create_action(context, resolution, work_window)
        context.decisions.append(
            {
                "decision_id": decision_id,
                "source_state_version": state.state_version,
                "game_minute": context.minute,
                "agent_id": self.active_agent_id,
                "trigger": "ACTION_AVAILABLE",
                "candidates": [
                    {
                        "candidate": item.candidate.model_dump(mode="json", exclude_none=False),
                        "prediction": item.prediction.model_dump(mode="json", exclude_none=False),
                        "utility_terms": item.utility_terms,
                        "total_score": item.total_score,
                        "tie_break": item.tie_break,
                    }
                    for item in scored
                ],
                "selected_candidate_id": selected.candidate.candidate_id,
                "selected_behavior_id": selected.candidate.behavior_id.value,
                "resolver_attempts": attempts,
                "selected_action_id": next(reversed(context.active_actions)),
                "outcome_provider": "M1_CATALOG_BOUNDED_HEURISTIC",
            }
        )
        context.changes.append(f"decision_committed:{decision_id}")

    def _proposal(self, state: WorldState, scored: ScoredCandidate) -> ActionProposal:
        self._proposal_counter += 1
        candidate = scored.candidate
        return ActionProposal(
            proposal_id=f"proposal_{self._proposal_counter:08d}",
            state_version=state.state_version,
            actor_id=candidate.actor_id,
            candidate_id=candidate.candidate_id,
            behavior_id=candidate.behavior_id,
            target_agent_id=None,
            target_object_ids=candidate.target_object_ids,
            score=scored.total_score,
            model_prediction_id=scored.prediction.prediction_id,
        )

    def _create_action(
        self,
        context: _TickContext,
        resolution: Resolution,
        work_window: WorkWindow | None,
    ) -> None:
        self._action_counter += 1
        action_id = f"action_{self._action_counter:08d}"
        candidate = resolution.candidate
        arrival = context.minute + candidate.estimated_travel_minutes
        perform_start = arrival
        session_id: str | None = None
        if candidate.behavior_id is BehaviorId.WORK_SHIFT:
            if work_window is None:
                raise ValueError("work action has no work session")
            perform_start = max(arrival, work_window.start_game_minute)
            session_id = work_window.session_id
        planned_end = perform_start + candidate.estimated_duration_minutes
        action = ActionState(
            action_id=action_id,
            behavior_id=candidate.behavior_id,
            agent_ids=[self.active_agent_id],
            phase=ActionPhase.CREATED,
            destination_location_id=candidate.destination_location_id,
            target_object_ids=candidate.target_object_ids,
            started_at_game_minute=context.minute,
            planned_end_game_minute=planned_end,
        )
        context.active_actions[action_id] = action
        self._record_action_phase(context, action, ActionPhase.CREATED)
        self._set_action_phase(context, action_id, ActionPhase.RESERVING)
        for reservation in resolution.slot_reservations:
            obj = context.objects[reservation.object_id]
            occupied = dict(obj.occupied_slots)
            occupied[reservation.slot_index] = action_id
            context.objects[reservation.object_id] = obj.model_copy(update={"occupied_slots": occupied})
        agent = context.agents[self.active_agent_id]
        if resolution.household_food_units:
            context.reserved_food_by_household[agent.household_id] = (
                context.reserved_food_by_household.get(agent.household_id, 0) + resolution.household_food_units
            )
        runtime = _ActionRuntime(
            action_id=action_id,
            proposal_id=resolution.proposal.proposal_id,
            candidate=candidate,
            reservations=resolution.slot_reservations,
            reserved_food_units=resolution.household_food_units,
            travel_arrival_minute=arrival,
            perform_start_minute=perform_start,
            work_session_id=session_id,
            origin_location_id=agent.current_location_id,
        )
        context.action_runtimes[action_id] = runtime
        context.agents[self.active_agent_id] = agent.model_copy(
            update={"current_action_id": action_id, "decision_due_at": planned_end}
        )
        if session_id is not None:
            session = context.work_sessions[session_id]
            session.proposal_ids.append(resolution.proposal.proposal_id)
            session.action_ids.append(action_id)
        if candidate.estimated_travel_minutes:
            origin = agent.current_location_id
            if origin == "TRAVELING":
                raise ValueError("available agent cannot already be traveling")
            location = context.locations[origin]
            context.locations[origin] = location.model_copy(
                update={
                    "current_agent_ids": [item for item in location.current_agent_ids if item != self.active_agent_id]
                }
            )
            context.agents[self.active_agent_id] = context.agents[self.active_agent_id].model_copy(
                update={"current_location_id": "TRAVELING"}
            )
            self._set_action_phase(context, action_id, ActionPhase.TRAVELING)
        elif context.minute < perform_start:
            self._set_action_phase(context, action_id, ActionPhase.ALIGNING)
        else:
            self._start_performing(context, runtime)
        context.changes.append(f"action_created:{action_id}:{candidate.behavior_id.value}")

    def _set_action_phase(self, context: _TickContext, action_id: str, phase: ActionPhase) -> None:
        action = context.active_actions[action_id]
        context.active_actions[action_id] = action.model_copy(update={"phase": phase})
        self._record_action_phase(context, action, phase)

    def _record_action_phase(
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
                "reservations": (
                    [{"object_id": item.object_id, "slot_index": item.slot_index} for item in runtime.reservations]
                    if runtime is not None
                    else []
                ),
                "failure_reason": failure_reason,
            }
        )

    def _release_reservations(self, context: _TickContext, runtime: _ActionRuntime) -> None:
        for reservation in runtime.reservations:
            obj = context.objects[reservation.object_id]
            occupied = dict(obj.occupied_slots)
            if occupied.get(reservation.slot_index) != runtime.action_id:
                raise ValueError("reservation owner changed before resolution")
            occupied.pop(reservation.slot_index)
            context.objects[reservation.object_id] = obj.model_copy(update={"occupied_slots": occupied})
        if runtime.reserved_food_units:
            household_id = context.agents[self.active_agent_id].household_id
            remaining = context.reserved_food_by_household.get(household_id, 0) - runtime.reserved_food_units
            if remaining < 0:
                raise ValueError("reserved household food became negative")
            if remaining:
                context.reserved_food_by_household[household_id] = remaining
            else:
                context.reserved_food_by_household.pop(household_id, None)

    def _stage_event(
        self,
        context: _TickContext,
        event_type: EventType,
        *,
        location_id: str,
        source_action_id: str | None,
        payload: dict[str, Any],
    ) -> WorldEvent:
        direct_ids = [self.active_agent_id]
        witness_ids: list[str] = []
        if self._event_scopes[event_type] is EventWitnessScope.HIGH_LEVEL_LOCATION:
            witness_ids = sorted(
                agent_id
                for agent_id in context.locations[location_id].current_agent_ids
                if agent_id not in direct_ids and context.agents[agent_id].enabled
            )
        event = self.ledger.create(
            event_type,
            staged_offset=len(context.events),
            game_minute=context.minute,
            location_id=location_id,
            actor_ids=direct_ids,
            affected_agent_ids=direct_ids,
            witness_agent_ids=witness_ids,
            source_action_id=source_action_id,
            payload=payload,
        )
        context.events.append(event)
        for agent_id in (*direct_ids, *witness_ids):
            agent = context.agents[agent_id]
            if event.event_id not in agent.known_event_ids:
                context.agents[agent_id] = agent.model_copy(
                    update={"known_event_ids": [*agent.known_event_ids, event.event_id]}
                )
            context.knowledge_records.append(
                KnowledgeRecord(
                    agent_id=agent_id,
                    event_id=event.event_id,
                    source_agent_id=None if agent_id in direct_ids else self.active_agent_id,
                    acquisition_type=(
                        KnowledgeAcquisitionType.DIRECT_PARTICIPANT
                        if agent_id in direct_ids
                        else KnowledgeAcquisitionType.WITNESSED
                    ),
                    confidence=1.0,
                    first_known_minute=context.minute,
                    last_reinforced_minute=context.minute,
                )
            )
        context.changes.append(f"event_appended:{event.event_id}:{event.event_type.value}")
        return event

    def _next_work_window(self, context: _TickContext) -> WorkWindow | None:
        current_day = context.minute // 1440
        for day in range(current_day, current_day + 8):
            if day % 7 not in self._schedule_entry.weekdays:
                continue
            end = (day * 1440) + self._schedule_entry.end_minute_of_day
            if context.minute >= end:
                continue
            start = (day * 1440) + self._schedule_entry.start_minute_of_day
            session_id = f"work_session_{self.active_agent_id}_day_{day:04d}"
            existing = context.work_sessions.get(session_id)
            if existing is not None:
                return existing.as_window()
            if context.minute >= start - 60:
                return self._work_session(context, day).as_window()
            return WorkWindow(
                session_id=session_id,
                day=day,
                start_game_minute=start,
                end_game_minute=end,
                grace_minutes=self._schedule_entry.grace_minutes,
            )
        return None

    def _work_session(self, context: _TickContext, day: int) -> _WorkSession:
        session_id = f"work_session_{self.active_agent_id}_day_{day:04d}"
        session = context.work_sessions.get(session_id)
        if session is None:
            session = _WorkSession(
                session_id=session_id,
                day=day,
                start_game_minute=(day * 1440) + self._schedule_entry.start_minute_of_day,
                end_game_minute=(day * 1440) + self._schedule_entry.end_minute_of_day,
                grace_minutes=self._schedule_entry.grace_minutes,
            )
            context.work_sessions[session_id] = session
        return session
