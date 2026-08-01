"""Deterministic rule enumeration for the four-behavior M1 allowlist."""

from __future__ import annotations

from dataclasses import dataclass

from town_core.domain.config_models import BehaviorConfig, CatalogBundle
from town_core.domain.decision_models import CandidateAction, HardCostPreview
from town_core.domain.enums import BehaviorId, ObjectType, RoutePlanningCapability
from town_core.domain.state_models import AgentState, InteractionObjectState, WorldState

M1_BEHAVIORS = frozenset(
    {
        BehaviorId.IDLE,
        BehaviorId.SLEEP,
        BehaviorId.EAT_AT_HOME,
        BehaviorId.WORK_SHIFT,
    }
)


@dataclass(frozen=True, slots=True)
class WorkWindow:
    """One absolute work occurrence for an agent/day session."""

    session_id: str
    day: int
    start_game_minute: int
    end_game_minute: int
    grace_minutes: int
    effective_work_minutes: int = 0
    finalized: bool = False


class CandidateEnumerator:
    def __init__(self, catalog: CatalogBundle) -> None:
        self._catalog = catalog
        self._behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}
        self._locations = {item.location_id: item for item in catalog.locations.locations}

    def enumerate(
        self,
        state: WorldState,
        agent_id: str,
        *,
        work_window: WorkWindow | None,
        reserved_food_units: int = 0,
    ) -> list[CandidateAction]:
        agent = state.agents[agent_id]
        if agent.current_action_id is not None or agent.current_location_id == "TRAVELING":
            return []

        drafts: list[tuple[BehaviorId, list[str], str | None, int, int, int, HardCostPreview]] = []
        idle = self._behaviors[BehaviorId.IDLE]
        drafts.append(
            (
                BehaviorId.IDLE,
                [],
                agent.current_location_id,
                0,
                idle.duration_minutes.base,
                self._schedule_conflict(
                    state.game_minute,
                    idle.duration_minutes.base,
                    work_window,
                ),
                HardCostPreview(),
            )
        )

        bed = self._assigned_or_first_object(state, agent, ObjectType.BED, agent.home_location_id)
        if bed is not None and agent.needs.energy < 1.0:
            sleep = self._behaviors[BehaviorId.SLEEP]
            travel = self._travel_minutes(agent.current_location_id, agent.home_location_id)
            minimum = sleep.duration_minutes.base - sleep.duration_minutes.variance
            maximum = sleep.duration_minutes.base + sleep.duration_minutes.variance
            duration = max(minimum, min(maximum, sleep.duration_minutes.base))
            if work_window is not None and state.game_minute < work_window.start_game_minute:
                travel_to_work = self._travel_minutes(agent.home_location_id, agent.assigned_work_location_id)
                available = work_window.start_game_minute - state.game_minute - travel - travel_to_work
                if available >= minimum:
                    duration = min(duration, available)
            drafts.append(
                (
                    BehaviorId.SLEEP,
                    [bed.object_id],
                    agent.home_location_id,
                    travel,
                    duration,
                    self._schedule_conflict(state.game_minute + travel, duration, work_window),
                    HardCostPreview(),
                )
            )

        household = state.households[agent.household_id]
        fridge = self._assigned_or_first_object(state, agent, ObjectType.FRIDGE, agent.home_location_id)
        seat = self._assigned_or_first_object(state, agent, ObjectType.DINING_SEAT, agent.home_location_id)
        if household.food_units - reserved_food_units >= 1 and fridge is not None and seat is not None:
            eat = self._behaviors[BehaviorId.EAT_AT_HOME]
            travel = self._travel_minutes(agent.current_location_id, agent.home_location_id)
            drafts.append(
                (
                    BehaviorId.EAT_AT_HOME,
                    [fridge.object_id, seat.object_id],
                    agent.home_location_id,
                    travel,
                    eat.duration_minutes.base,
                    self._schedule_conflict(state.game_minute + travel, eat.duration_minutes.base, work_window),
                    HardCostPreview(household_food_units=-1),
                )
            )

        if (
            work_window is not None
            and not work_window.finalized
            and work_window.start_game_minute - 60 <= state.game_minute < work_window.end_game_minute
        ):
            workstation = self._assigned_workstation(state, agent)
            if workstation is not None:
                work = self._behaviors[BehaviorId.WORK_SHIFT]
                travel = self._travel_minutes(agent.current_location_id, agent.assigned_work_location_id)
                perform_start = max(state.game_minute + travel, work_window.start_game_minute)
                duration = min(work.duration_minutes.base, work_window.end_game_minute - perform_start)
                if duration > 0:
                    drafts.append(
                        (
                            BehaviorId.WORK_SHIFT,
                            [workstation.object_id],
                            agent.assigned_work_location_id,
                            travel,
                            duration,
                            0,
                            HardCostPreview(),
                        )
                    )

        candidates: list[CandidateAction] = []
        for ordinal, (behavior_id, object_ids, destination, travel, duration, conflict, preview) in enumerate(
            drafts[: self._catalog.utility.max_candidates_per_agent],
            start=1,
        ):
            sequence = (state.state_version * 100) + ordinal
            candidates.append(
                CandidateAction(
                    candidate_id=f"candidate_{sequence:08d}",
                    actor_id=agent_id,
                    behavior_id=behavior_id,
                    target_agent_id=None,
                    target_object_ids=object_ids,
                    destination_location_id=destination,
                    estimated_travel_minutes=travel,
                    estimated_duration_minutes=duration,
                    hard_cost_preview=preview,
                    schedule_conflict_minutes=conflict,
                    context_event_ids=[],
                    route_planning=RoutePlanningCapability.DISABLED,
                )
            )
        return candidates

    def behavior(self, behavior_id: BehaviorId) -> BehaviorConfig:
        return self._behaviors[behavior_id]

    def _travel_minutes(self, origin: str, destination: str) -> int:
        if origin == destination:
            return 0
        return self._locations[origin].travel_minutes[destination]

    @staticmethod
    def _schedule_conflict(start: int, duration: int, work_window: WorkWindow | None) -> int:
        if work_window is None:
            return 0
        end = start + duration
        return max(0, min(end, work_window.end_game_minute) - max(start, work_window.start_game_minute))

    @staticmethod
    def _has_free_slot(obj: InteractionObjectState) -> bool:
        return obj.enabled and len(obj.occupied_slots) < obj.slot_count

    def _assigned_or_first_object(
        self,
        state: WorldState,
        agent: AgentState,
        object_type: ObjectType,
        location_id: str,
    ) -> InteractionObjectState | None:
        matching = sorted(
            (
                obj
                for obj in state.objects.values()
                if obj.object_type is object_type and obj.location_id == location_id and self._has_free_slot(obj)
            ),
            key=lambda obj: (
                obj.metadata.get("assigned_agent_id") != agent.agent_id,
                obj.object_id,
            ),
        )
        return matching[0] if matching else None

    def _assigned_workstation(
        self,
        state: WorldState,
        agent: AgentState,
    ) -> InteractionObjectState | None:
        matching = sorted(
            (
                obj
                for obj in state.objects.values()
                if obj.object_type is ObjectType.WORKSTATION
                and obj.location_id == agent.assigned_work_location_id
                and agent.assigned_workstation_tag in obj.capability_tags
                and self._has_free_slot(obj)
            ),
            key=lambda obj: (
                obj.metadata.get("assigned_agent_id") != agent.agent_id,
                obj.object_id,
            ),
        )
        return matching[0] if matching else None
