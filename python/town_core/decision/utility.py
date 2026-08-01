"""Decomposed configured Utility scoring with deterministic tie noise."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from town_core.decision.candidates import WorkWindow
from town_core.domain.config_models import CatalogBundle
from town_core.domain.decision_models import CandidateAction, OutcomePrediction
from town_core.domain.enums import BehaviorId, NeedName
from town_core.domain.state_models import WorldState


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: CandidateAction
    prediction: OutcomePrediction
    utility_terms: dict[str, float]
    total_score: float
    tie_break: float


class UtilityScorer:
    def __init__(self, catalog: CatalogBundle) -> None:
        self._weights = catalog.utility.weights
        self._noise_amplitude = catalog.utility.deterministic_noise_amplitude

    def score_all(
        self,
        state: WorldState,
        candidates: list[CandidateAction],
        predictions: dict[str, OutcomePrediction],
        *,
        work_window: WorkWindow | None,
        recent_behavior: BehaviorId | None,
    ) -> list[ScoredCandidate]:
        preliminary = [
            self._score_one(
                state,
                candidate,
                predictions[candidate.candidate_id],
                work_window=work_window,
                recent_behavior=recent_behavior,
                idle_penalty=0.0,
            )
            for candidate in candidates
        ]
        best_non_idle = max(
            (item.total_score for item in preliminary if item.candidate.behavior_id is not BehaviorId.IDLE),
            default=float("-inf"),
        )
        apply_idle_penalty = best_non_idle > self._weights.idle_penalty
        scored = [
            self._score_one(
                state,
                candidate,
                predictions[candidate.candidate_id],
                work_window=work_window,
                recent_behavior=recent_behavior,
                idle_penalty=self._weights.idle_penalty if apply_idle_penalty else 0.0,
            )
            for candidate in candidates
        ]
        return sorted(
            scored,
            key=lambda item: (-item.total_score, -item.tie_break, item.candidate.candidate_id),
        )

    def _score_one(
        self,
        state: WorldState,
        candidate: CandidateAction,
        prediction: OutcomePrediction,
        *,
        work_window: WorkWindow | None,
        recent_behavior: BehaviorId | None,
        idle_penalty: float,
    ) -> ScoredCandidate:
        agent = state.agents[candidate.actor_id]
        need_preview = prediction.need_delta_preview.model_dump()
        need_utility = 0.0
        for axis in NeedName:
            delta = float(need_preview[axis.value])
            current = float(getattr(agent.needs, axis.value))
            if delta >= 0:
                need_utility += delta * ((1.0 - current) ** 2) * 4.0
            else:
                need_utility += delta * max(0.25, current)

        schedule_utility = 0.0
        if work_window is not None:
            if candidate.behavior_id is BehaviorId.WORK_SHIFT:
                urgency = 1.0 if state.game_minute < work_window.start_game_minute else 2.0
                schedule_utility = urgency * (1.0 + agent.personality.discipline)
            elif candidate.schedule_conflict_minutes:
                schedule_utility = -(candidate.schedule_conflict_minutes / 60.0) * (1.0 + agent.personality.discipline)

        household = state.households[agent.household_id]
        resource_cost_ratio = 0.0
        if candidate.hard_cost_preview.household_money < 0 and household.money > 0:
            resource_cost_ratio += abs(candidate.hard_cost_preview.household_money) / household.money
        if candidate.hard_cost_preview.household_food_units < 0 and household.food_units > 0:
            resource_cost_ratio += abs(candidate.hard_cost_preview.household_food_units) / household.food_units
        repetition = 1.0 if recent_behavior is candidate.behavior_id else 0.0
        tie_break = self._stable_tie_break(state, candidate)
        terms = {
            "needs": self._weights.needs * need_utility,
            "mood": 0.0,
            "schedule": self._weights.schedule * schedule_utility,
            "relationship": 0.0,
            "known_events": 0.0,
            "money_cost": -self._weights.money_cost * resource_cost_ratio * (1.0 + agent.personality.frugality),
            "travel_cost": -self._weights.travel_cost * (candidate.estimated_travel_minutes / 60.0),
            "interrupt_cost": 0.0,
            "repetition_penalty": -self._weights.repetition_penalty * repetition,
            "idle_penalty": -idle_penalty if candidate.behavior_id is BehaviorId.IDLE else 0.0,
            "deterministic_noise": tie_break * self._noise_amplitude,
        }
        total = round(sum(terms.values()), 12)
        return ScoredCandidate(candidate, prediction, terms, total, tie_break)

    @staticmethod
    def _stable_tie_break(state: WorldState, candidate: CandidateAction) -> float:
        material = (
            f"stwm-m1|tie-v1|{state.random_seed}|{state.state_version}|"
            f"{candidate.actor_id}|{candidate.behavior_id.value}|{candidate.candidate_id}"
        ).encode()
        integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
        unit = integer / float((1 << 64) - 1)
        return (unit * 2.0) - 1.0
