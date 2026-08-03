"""M4 batch provider boundary and deterministic non-neural implementations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from town_core.domain.config_models import BehaviorConfig, CatalogBundle
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import BehaviorId, MoodAxis, NeedName, RelationshipDirection
from town_core.domain.state_models import MoodDelta, NeedDelta, RelationshipDelta
from town_core.modeling.contracts import CandidateFeatureRow
from town_core.society.rules import HEURISTIC_PROVIDER_ID, midpoint


class OutcomeModel(Protocol):
    provider_id: str
    model_version: str | None

    def predict_batch(self, rows: Sequence[CandidateFeatureRow]) -> Sequence[OutcomePrediction]: ...


def _prediction_id(row: CandidateFeatureRow) -> str:
    return f"prediction_{int(row.row_id.removeprefix('row_'), 16)}"


class HeuristicOutcomeModel:
    """Candidate-row adapter reproducing the frozen M3 heuristic formulas."""

    provider_id = HEURISTIC_PROVIDER_ID
    model_version: str | None = None

    def __init__(self, catalog: CatalogBundle) -> None:
        self._behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}

    def predict_batch(self, rows: Sequence[CandidateFeatureRow]) -> Sequence[OutcomePrediction]:
        return [self._predict(row, self._behaviors[row.raw_candidate.behavior_id]) for row in rows]

    @staticmethod
    def _predict(row: CandidateFeatureRow, behavior: BehaviorConfig) -> OutcomePrediction:
        need_values = {axis.value: 0.0 for axis in NeedName}
        for need_axis, bounds in behavior.output_bounds.need_deltas.items():
            need_values[need_axis.value] = midpoint(bounds)
        actor_mood_values = {axis.value: 0.0 for axis in MoodAxis}
        for actor_mood_axis, bounds in behavior.output_bounds.actor_mood_deltas.items():
            actor_mood_values[actor_mood_axis.value] = midpoint(bounds)

        target_mood: MoodDelta | None = None
        relationship: RelationshipDelta | None = None
        acceptance: float | None = None
        target = row.raw_target
        if target is not None and behavior.soft_effect_mask.acceptance:
            target_mood_values = {axis.value: 0.0 for axis in MoodAxis}
            for target_mood_axis, bounds in behavior.output_bounds.target_mood_deltas.items():
                target_mood_values[target_mood_axis.value] = midpoint(bounds)
            relationship_values = {axis: 0.0 for axis in ("familiarity", "affinity", "trust", "tension")}
            for relationship_axis, bounds in behavior.output_bounds.relationship_target_to_actor.items():
                relationship_values[relationship_axis.value] = midpoint(bounds)
            target_mood = MoodDelta(**target_mood_values)
            relationship = RelationshipDelta(**relationship_values)
            behavior_bias = {
                BehaviorId.GREET: 0.18,
                BehaviorId.CHAT: 0.12,
                BehaviorId.JOKE: 0.0,
                BehaviorId.COMPLIMENT: 0.05,
                BehaviorId.INVITE_JOIN: -0.02,
                BehaviorId.APOLOGIZE: -0.05,
                BehaviorId.CONFRONT: -0.20,
            }.get(row.raw_candidate.behavior_id, 0.0)
            raw = (
                0.38
                + behavior_bias
                + (0.20 * target.relationship_affinity)
                + (0.18 * target.relationship_trust)
                + (0.08 * target.relationship_familiarity)
                - (0.28 * target.relationship_tension)
                + (0.08 * row.raw_actor.personality.sociability)
                - (0.08 * target.mood.stress)
            )
            acceptance = round(max(0.05, min(0.95, raw)), 6)

        return OutcomePrediction(
            prediction_id=_prediction_id(row),
            candidate_id=row.candidate_id,
            need_delta_preview=NeedDelta(**need_values),
            actor_mood_delta=MoodDelta(**actor_mood_values),
            target_mood_delta=target_mood,
            relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
            relationship_delta_target_to_actor=relationship,
            acceptance_probability=acceptance,
            event_probabilities={event_type: 1.0 for event_type in behavior.emitted_event_types},
        )


class RecordedOutcomeModel:
    provider_id = "stwm.recorded-outcome/v1"

    def __init__(self, predictions: Mapping[str, OutcomePrediction], *, model_version: str | None = None) -> None:
        self._predictions = dict(predictions)
        self.model_version = model_version

    def predict_batch(self, rows: Sequence[CandidateFeatureRow]) -> Sequence[OutcomePrediction]:
        missing = [row.row_id for row in rows if row.row_id not in self._predictions]
        if missing:
            raise KeyError(f"recorded outcome batch is incomplete: {missing[:3]}")
        return [self._predictions[row.row_id].model_copy(update={"candidate_id": row.candidate_id}) for row in rows]
