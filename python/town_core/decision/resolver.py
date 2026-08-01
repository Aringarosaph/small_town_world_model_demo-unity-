"""One-snapshot central Resolver for M1 proposals and reservations."""

from __future__ import annotations

from dataclasses import dataclass

from town_core.decision.candidates import WorkWindow
from town_core.domain.config_models import CatalogBundle
from town_core.domain.decision_models import ActionProposal, CandidateAction
from town_core.domain.enums import BehaviorId, ProposalResult
from town_core.domain.state_models import WorldState


@dataclass(frozen=True, slots=True)
class SlotReservation:
    object_id: str
    slot_index: int


@dataclass(frozen=True, slots=True)
class Resolution:
    result: ProposalResult
    proposal: ActionProposal
    candidate: CandidateAction
    slot_reservations: tuple[SlotReservation, ...]
    household_food_units: int


class CentralResolver:
    """Validate a proposal without mutating its read-only source version."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self._locations = {item.location_id: item for item in catalog.locations.locations}

    def resolve(
        self,
        state: WorldState,
        proposal: ActionProposal,
        candidate: CandidateAction,
        *,
        reserved_food_units: int,
        work_window: WorkWindow | None,
    ) -> Resolution:
        if proposal.state_version != state.state_version:
            return self._rejected(ProposalResult.STATE_STALE, proposal, candidate)
        agent = state.agents[proposal.actor_id]
        if agent.current_action_id is not None:
            return self._rejected(ProposalResult.TARGET_UNAVAILABLE, proposal, candidate)
        if proposal.behavior_id is not candidate.behavior_id or proposal.candidate_id != candidate.candidate_id:
            return self._rejected(ProposalResult.STATE_STALE, proposal, candidate)

        food_units = max(0, -candidate.hard_cost_preview.household_food_units)
        household = state.households[agent.household_id]
        if household.food_units - reserved_food_units < food_units:
            return self._rejected(ProposalResult.INSUFFICIENT_FUNDS, proposal, candidate)

        if candidate.destination_location_id is not None:
            arrival = state.game_minute + candidate.estimated_travel_minutes
            if candidate.behavior_id is BehaviorId.WORK_SHIFT and work_window is not None:
                arrival = max(arrival, work_window.start_game_minute)
            if not self._is_open(candidate.destination_location_id, arrival):
                return self._rejected(ProposalResult.LOCATION_CLOSED, proposal, candidate)

        reservations: list[SlotReservation] = []
        for object_id in candidate.target_object_ids:
            obj = state.objects[object_id]
            free_slots = [slot for slot in range(obj.slot_count) if slot not in obj.occupied_slots]
            if not obj.enabled or not free_slots:
                return self._rejected(ProposalResult.OBJECT_SLOT_CONFLICT, proposal, candidate)
            reservations.append(SlotReservation(object_id, free_slots[0]))
        return Resolution(ProposalResult.ACCEPTED, proposal, candidate, tuple(reservations), food_units)

    def _is_open(self, location_id: str, game_minute: int) -> bool:
        minute_of_day = game_minute % 1440
        return any(
            interval.start_minute_of_day <= minute_of_day < interval.end_minute_of_day
            for interval in self._locations[location_id].open_intervals
        )

    @staticmethod
    def _rejected(
        result: ProposalResult,
        proposal: ActionProposal,
        candidate: CandidateAction,
    ) -> Resolution:
        return Resolution(result, proposal, candidate, (), 0)
