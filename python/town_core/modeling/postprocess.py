"""Catalog masks, bounds, and finite-value enforcement for M4 outputs."""

from __future__ import annotations

import math
from collections import Counter

from town_core.domain.config_models import BehaviorConfig, CatalogBundle, DeltaBounds
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import MoodAxis, NeedName, RelationshipAxis, RelationshipDirection
from town_core.domain.state_models import MoodDelta, NeedDelta, RelationshipDelta
from town_core.modeling.contracts import CandidateFeatureRow


class OutcomePostprocessError(ValueError):
    """One neural batch cannot be made contract-safe and must fall back whole."""


def _bounded(value: float, bounds: DeltaBounds, violations: Counter[str]) -> float:
    if not math.isfinite(value):
        raise OutcomePostprocessError("non-finite neural outcome")
    clamped = max(bounds.minimum, min(bounds.maximum, value))
    if clamped != value:
        violations["out_of_bounds"] += 1
    return round(clamped, 9)


class CatalogOutcomePostprocessor:
    def __init__(self, catalog: CatalogBundle) -> None:
        self._behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}

    def process(
        self,
        row: CandidateFeatureRow,
        prediction: OutcomePrediction,
    ) -> tuple[OutcomePrediction, dict[str, int]]:
        if prediction.candidate_id != row.candidate_id:
            raise OutcomePostprocessError("prediction candidate ID differs from feature row")
        behavior = self._behaviors[row.raw_candidate.behavior_id]
        violations: Counter[str] = Counter()
        need_values = self._masked_needs(behavior, prediction, violations)
        actor_mood_values = self._masked_actor_mood(behavior, prediction, violations)
        target_mood, relationship, acceptance = self._masked_target(row, behavior, prediction, violations)
        allowed_events = set(behavior.emitted_event_types)
        event_probabilities = {}
        for event_type, probability in prediction.event_probabilities.items():
            if not math.isfinite(probability):
                raise OutcomePostprocessError("non-finite event probability")
            if event_type not in allowed_events:
                violations["unknown_or_masked_event"] += 1
                continue
            bounded = max(0.0, min(1.0, float(probability)))
            if bounded != probability:
                violations["out_of_bounds"] += 1
            event_probabilities[event_type] = round(bounded, 9)
        return (
            OutcomePrediction(
                prediction_id=prediction.prediction_id,
                candidate_id=prediction.candidate_id,
                need_delta_preview=NeedDelta(**need_values),
                actor_mood_delta=MoodDelta(**actor_mood_values),
                target_mood_delta=target_mood,
                relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
                relationship_delta_target_to_actor=relationship,
                acceptance_probability=acceptance,
                event_probabilities=event_probabilities,
            ),
            dict(sorted(violations.items())),
        )

    @staticmethod
    def _masked_needs(
        behavior: BehaviorConfig,
        prediction: OutcomePrediction,
        violations: Counter[str],
    ) -> dict[str, float]:
        values: dict[str, float] = {}
        for axis in NeedName:
            value = float(getattr(prediction.need_delta_preview, axis.value))
            bounds = behavior.output_bounds.need_deltas.get(axis)
            if bounds is None:
                if value != 0.0:
                    violations["masked_need"] += 1
                values[axis.value] = 0.0
            else:
                values[axis.value] = _bounded(value, bounds, violations)
        return values

    @staticmethod
    def _masked_actor_mood(
        behavior: BehaviorConfig,
        prediction: OutcomePrediction,
        violations: Counter[str],
    ) -> dict[str, float]:
        values: dict[str, float] = {}
        for axis in MoodAxis:
            value = float(getattr(prediction.actor_mood_delta, axis.value))
            bounds = behavior.output_bounds.actor_mood_deltas.get(axis)
            if bounds is None:
                if value != 0.0:
                    violations["masked_actor_mood"] += 1
                values[axis.value] = 0.0
            else:
                values[axis.value] = _bounded(value, bounds, violations)
        return values

    @staticmethod
    def _masked_target(
        row: CandidateFeatureRow,
        behavior: BehaviorConfig,
        prediction: OutcomePrediction,
        violations: Counter[str],
    ) -> tuple[MoodDelta | None, RelationshipDelta | None, float | None]:
        if row.raw_target is None or not behavior.soft_effect_mask.acceptance:
            if (
                prediction.target_mood_delta is not None
                or prediction.relationship_delta_target_to_actor is not None
                or prediction.acceptance_probability is not None
            ):
                violations["absent_or_masked_target"] += 1
            return None, None, None
        if prediction.acceptance_probability is None:
            raise OutcomePostprocessError("targeted neural outcome omitted acceptance")
        if not math.isfinite(prediction.acceptance_probability):
            raise OutcomePostprocessError("non-finite acceptance probability")
        acceptance = max(0.0, min(1.0, float(prediction.acceptance_probability)))
        if acceptance != prediction.acceptance_probability:
            violations["out_of_bounds"] += 1

        target_source = prediction.target_mood_delta or MoodDelta(valence=0.0, stress=0.0)
        target_values: dict[str, float] = {}
        for axis in MoodAxis:
            value = float(getattr(target_source, axis.value))
            bounds = behavior.output_bounds.target_mood_deltas.get(axis)
            if bounds is None:
                if value != 0.0:
                    violations["masked_target_mood"] += 1
                target_values[axis.value] = 0.0
            else:
                target_values[axis.value] = _bounded(value, bounds, violations)

        relation_source = prediction.relationship_delta_target_to_actor or RelationshipDelta(
            familiarity=0.0, affinity=0.0, trust=0.0, tension=0.0
        )
        relation_values: dict[str, float] = {}
        for relationship_axis in RelationshipAxis:
            value = float(getattr(relation_source, relationship_axis.value))
            bounds = behavior.output_bounds.relationship_target_to_actor.get(relationship_axis)
            if bounds is None:
                if value != 0.0:
                    violations["masked_relationship"] += 1
                relation_values[relationship_axis.value] = 0.0
            else:
                relation_values[relationship_axis.value] = _bounded(value, bounds, violations)
        return MoodDelta(**target_values), RelationshipDelta(**relation_values), round(acceptance, 9)
