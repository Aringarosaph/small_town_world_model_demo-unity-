"""Catalog-bounded deterministic outcome previews for the M1 rules baseline."""

from __future__ import annotations

from collections.abc import Mapping

from town_core.domain.config_models import BehaviorConfig, CatalogBundle, DeltaBounds
from town_core.domain.decision_models import CandidateAction, OutcomePrediction
from town_core.domain.enums import BehaviorId, MoodAxis, NeedName, RelationshipDirection
from town_core.domain.state_models import MoodDelta, NeedDelta, WorldState


def _midpoint(bounds: DeltaBounds) -> float:
    return (bounds.minimum + bounds.maximum) / 2.0


def _zero_need_delta() -> dict[NeedName, float]:
    return {axis: 0.0 for axis in NeedName}


class HeuristicOutcomeProvider:
    """Derive exact M1 effects from the frozen catalog, never free constants."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self._behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}
        self._decay = dict(catalog.utility.need_decay_per_game_hour)

    def predict(
        self,
        state: WorldState,
        candidate: CandidateAction,
        *,
        prediction_sequence: int,
    ) -> OutcomePrediction:
        behavior = self._behaviors[candidate.behavior_id]
        need_deltas = self.action_need_deltas(behavior, candidate.estimated_duration_minutes)
        mood = self.completion_mood_deltas(behavior)
        return OutcomePrediction(
            prediction_id=f"prediction_{prediction_sequence:08d}",
            candidate_id=candidate.candidate_id,
            need_delta_preview=NeedDelta(**{axis.value: value for axis, value in need_deltas.items()}),
            actor_mood_delta=MoodDelta(
                valence=mood.get(MoodAxis.VALENCE, 0.0),
                stress=mood.get(MoodAxis.STRESS, 0.0),
            ),
            target_mood_delta=None,
            relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
            relationship_delta_target_to_actor=None,
            acceptance_probability=None,
            event_probabilities={},
        )

    def action_need_deltas(self, behavior: BehaviorConfig, duration_minutes: int) -> Mapping[NeedName, float]:
        """Preview only behavior-authorized axes, including relevant passive decay."""

        values = _zero_need_delta()
        duration_hours = duration_minutes / 60.0
        if behavior.behavior_id is BehaviorId.SLEEP:
            energy_bounds = behavior.output_bounds.need_deltas[NeedName.ENERGY]
            energy_per_minute = _midpoint(energy_bounds) / behavior.duration_minutes.base
            values[NeedName.ENERGY] = min(energy_bounds.maximum, energy_per_minute * duration_minutes)
            for axis in (NeedName.HUNGER, NeedName.SOCIAL):
                bounds = behavior.output_bounds.need_deltas[axis]
                values[axis] = max(bounds.minimum, self._decay[axis] * duration_hours)
        elif behavior.behavior_id is BehaviorId.WORK_SHIFT:
            for axis in (NeedName.ENERGY, NeedName.HYGIENE, NeedName.FUN):
                bounds = behavior.output_bounds.need_deltas[axis]
                active = (_midpoint(bounds) / behavior.duration_minutes.base) * duration_minutes
                combined = active + (self._decay[axis] * duration_hours)
                values[axis] = max(bounds.minimum, min(bounds.maximum, combined))
        elif behavior.behavior_id is BehaviorId.EAT_AT_HOME:
            bounds = behavior.output_bounds.need_deltas[NeedName.HUNGER]
            values[NeedName.HUNGER] = _midpoint(bounds)
        return values

    def continuous_need_delta_per_minute(self, behavior_id: BehaviorId) -> Mapping[NeedName, float]:
        """Return catalog-derived active effects; global decay is applied separately."""

        behavior = self._behaviors[behavior_id]
        values = _zero_need_delta()
        if behavior_id is BehaviorId.SLEEP:
            bounds = behavior.output_bounds.need_deltas[NeedName.ENERGY]
            values[NeedName.ENERGY] = _midpoint(bounds) / behavior.duration_minutes.base
        elif behavior_id is BehaviorId.WORK_SHIFT:
            for axis in (NeedName.ENERGY, NeedName.HYGIENE, NeedName.FUN):
                bounds = behavior.output_bounds.need_deltas[axis]
                values[axis] = _midpoint(bounds) / behavior.duration_minutes.base
        return values

    def completion_need_deltas(self, behavior_id: BehaviorId) -> Mapping[NeedName, float]:
        behavior = self._behaviors[behavior_id]
        values = _zero_need_delta()
        if behavior_id is BehaviorId.EAT_AT_HOME:
            values[NeedName.HUNGER] = _midpoint(behavior.output_bounds.need_deltas[NeedName.HUNGER])
        return values

    def completion_mood_deltas(self, behavior: BehaviorConfig) -> Mapping[MoodAxis, float]:
        if behavior.behavior_id is not BehaviorId.EAT_AT_HOME:
            return {}
        return {axis: _midpoint(bounds) for axis, bounds in behavior.output_bounds.actor_mood_deltas.items()}

    @property
    def passive_decay_per_minute(self) -> Mapping[NeedName, float]:
        return {axis: value / 60.0 for axis, value in self._decay.items()}
