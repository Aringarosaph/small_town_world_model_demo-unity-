"""Deterministic M4 feature extraction from an exact M3 decision snapshot."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, cast

from town_core.domain.config_models import CatalogBundle
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import (
    BehaviorId,
    CapabilityTag,
    EventType,
    LocationType,
    RelationshipRole,
)
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.state_models import KnowledgeRecord, RelationshipState, WorldEvent, WorldState
from town_core.modeling.contracts import (
    CandidateFeatureRow,
    CategoricalFeatures,
    DatasetSplit,
    FeatureMasks,
    NumericFeatures,
    OutcomeLabel,
    RawActorFeatures,
    RawCandidateFeatures,
    RawEventFeatures,
    RawTargetFeatures,
    TrainingExample,
)
from town_core.society.checkpoint import knowledge_key
from town_core.society.models import ConversationRecord, SocietyCandidate

MAX_CONTEXT_EVENTS = 4
MAX_MINUTES_NORMALIZATION = 1440.0


def feature_vocabulary(catalog: CatalogBundle) -> dict[str, list[str]]:
    return {
        "behavior": [item.behavior_id.value for item in catalog.behaviors.behaviors],
        "location": sorted(item.location_id for item in catalog.locations.locations),
        "location_type": [item.value for item in LocationType],
        "object_type": [item.object_type.value for item in catalog.objects.object_types],
        "capability": [item.value for item in CapabilityTag],
        "relationship_role": [item.value for item in RelationshipRole],
        "event_type": [item.event_type.value for item in catalog.events.event_types],
    }


def split_for_scenario_group(scenario_group_id: str) -> DatasetSplit:
    bucket = int(hashlib.sha256(scenario_group_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "validation"
    return "test"


def _index(vocabulary: Mapping[str, list[str]], group: str, value: object) -> int:
    raw = getattr(value, "value", value)
    return vocabulary[group].index(str(raw))


def _row_id(source_commit: str, seed: int, decision_id: str, candidate_id: str) -> str:
    material = json.dumps(
        [source_commit, seed, decision_id, candidate_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"row_{hashlib.sha256(material).hexdigest()[:24]}"


def _ratio(value: float, denominator: float, *, maximum: float = 1.0) -> float:
    return round(max(0.0, min(maximum, value / max(denominator, 1e-9))), 9)


class CandidateFeatureEncoder:
    def __init__(self, catalog: CatalogBundle, m3_catalogs: M3Catalogs, *, source_commit: str) -> None:
        del m3_catalogs
        self.catalog = catalog
        self.source_commit = source_commit
        self.vocabulary = feature_vocabulary(catalog)
        self.behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}

    def encode_decision(
        self,
        *,
        seed: int,
        state: WorldState,
        decision: Mapping[str, object],
        events: Mapping[str, WorldEvent],
        knowledge_records: Mapping[str, KnowledgeRecord],
        conversations: Mapping[str, ConversationRecord],
        recent_behavior: BehaviorId | None,
    ) -> list[TrainingExample]:
        decision_id = str(decision["decision_id"])
        selected_candidate_id = str(decision["selected_candidate_id"])
        candidates = decision.get("candidates")
        if not isinstance(candidates, list):
            raise TypeError("M3 decision candidate rows must be a list")
        attempts = decision.get("resolver_attempts", [])
        if not isinstance(attempts, list):
            raise TypeError("M3 decision resolver attempts must be a list")
        resolver_by_candidate = {
            str(item["candidate_id"]): str(item["result"])
            for item in attempts
            if isinstance(item, dict) and "candidate_id" in item and "result" in item
        }
        episode_id = f"m3_seed_{seed}_day_{state.game_minute // 1440:03d}"
        scenario_group_id = episode_id
        split = split_for_scenario_group(scenario_group_id)
        result: list[TrainingExample] = []
        for rank, item in enumerate(candidates):
            if not isinstance(item, dict):
                raise TypeError("M3 decision candidate entry must be an object")
            society_candidate = SocietyCandidate.model_validate(item["candidate"])
            prediction = OutcomePrediction.model_validate(item["prediction"])
            utility_terms = item.get("utility_terms")
            if not isinstance(utility_terms, dict):
                raise TypeError("M3 utility terms must be an object")
            candidate_id = str(society_candidate.candidate.candidate_id)
            row_id = _row_id(self.source_commit, seed, decision_id, candidate_id)
            feature = self._encode_feature(
                row_id=row_id,
                seed=seed,
                episode_id=episode_id,
                scenario_group_id=scenario_group_id,
                split=split,
                decision_id=decision_id,
                rank=rank,
                state=state,
                item=society_candidate,
                prediction=prediction,
                events=events,
                knowledge_records=knowledge_records,
                conversations=conversations,
                recent_behavior=recent_behavior,
            )
            label = OutcomeLabel(
                row_id=row_id,
                prediction=prediction,
                utility_terms={str(key): float(value) for key, value in utility_terms.items()},
                total_score=float(item["total_score"]),
                tie_break=float(item["tie_break"]),
                selected_by_teacher=candidate_id == selected_candidate_id,
                resolver_attempted=candidate_id in resolver_by_candidate,
                resolver_result=resolver_by_candidate.get(candidate_id),
            )
            result.append(TrainingExample(feature=feature, label=label))
        return result

    def _encode_feature(
        self,
        *,
        row_id: str,
        seed: int,
        episode_id: str,
        scenario_group_id: str,
        split: DatasetSplit,
        decision_id: str,
        rank: int,
        state: WorldState,
        item: SocietyCandidate,
        prediction: OutcomePrediction,
        events: Mapping[str, WorldEvent],
        knowledge_records: Mapping[str, KnowledgeRecord],
        conversations: Mapping[str, ConversationRecord],
        recent_behavior: BehaviorId | None,
    ) -> CandidateFeatureRow:
        candidate = item.candidate
        actor = state.agents[candidate.actor_id]
        if actor.current_location_id == "TRAVELING":
            raise ValueError("a traveling actor cannot enter an M4 decision row")
        household = state.households[actor.household_id]
        behavior = self.behaviors[candidate.behavior_id]
        objects = [state.objects[object_id] for object_id in candidate.target_object_ids]
        object_types = sorted({obj.object_type.value for obj in objects})
        capabilities = sorted({capability.value for obj in objects for capability in obj.capability_tags})
        destination_type = (
            state.locations[candidate.destination_location_id].location_type
            if candidate.destination_location_id is not None
            else None
        )
        local_population = len(state.locations[actor.current_location_id].current_agent_ids)
        selected_events = sorted(
            (events[event_id] for event_id in candidate.context_event_ids if event_id in events),
            key=lambda event: (-event.importance, -event.game_minute, event.event_id),
        )[:MAX_CONTEXT_EVENTS]
        raw_events = [
            self._event_features(state, actor.agent_id, candidate.target_agent_id, event) for event in selected_events
        ]
        target, relationship = self._target_features(
            state,
            actor.agent_id,
            candidate.target_agent_id,
            candidate.selected_context_event_id,
            knowledge_records,
            conversations,
        )
        event_importance = [float(event.importance) for event in selected_events]
        event_age = [
            _ratio(state.game_minute - event.game_minute, MAX_MINUTES_NORMALIZATION) for event in selected_events
        ]
        event_mask = [True] * len(selected_events)
        while len(event_importance) < MAX_CONTEXT_EVENTS:
            event_importance.append(0.0)
            event_age.append(0.0)
            event_mask.append(False)
        minute_of_day = state.game_minute % 1440
        weekday = (state.game_minute // 1440) % 7
        target_relationship = (
            [relationship.familiarity, relationship.affinity, relationship.trust, relationship.tension]
            if relationship is not None
            else None
        )
        target_age = (
            _ratio(state.game_minute - relationship.last_interaction_minute, MAX_MINUTES_NORMALIZATION)
            if relationship is not None and relationship.last_interaction_minute is not None
            else None
        )
        location_vocabulary = self.vocabulary["location"]
        event_indices = [_index(self.vocabulary, "event_type", event.event_type) for event in selected_events]
        event_indices.extend([-1] * (MAX_CONTEXT_EVENTS - len(event_indices)))
        acceptance_present = target is not None and behavior.soft_effect_mask.acceptance
        return CandidateFeatureRow(
            row_id=row_id,
            source_commit=self.source_commit,
            seed=seed,
            episode_id=episode_id,
            scenario_group_id=scenario_group_id,
            split=split,
            decision_group_id=f"{scenario_group_id}:{decision_id}",
            decision_id=decision_id,
            candidate_id=candidate.candidate_id,
            actor_id=candidate.actor_id,
            source_state_version=state.state_version,
            game_minute=state.game_minute,
            candidate_rank=rank,
            raw_actor=RawActorFeatures(
                needs=actor.needs,
                mood=actor.mood,
                personality=actor.personality,
                household_money=household.money,
                household_food_units=household.food_units,
                current_location_id=actor.current_location_id,
                home_location_id=actor.home_location_id,
                assigned_work_location_id=actor.assigned_work_location_id,
                local_population=local_population,
                known_event_count=len(actor.known_event_ids),
                decision_overdue_minutes=max(0, state.game_minute - actor.decision_due_at),
            ),
            raw_candidate=RawCandidateFeatures(
                behavior_id=candidate.behavior_id,
                destination_location_id=candidate.destination_location_id,
                destination_location_type=destination_type,
                target_object_ids=candidate.target_object_ids,
                object_type_values=object_types,
                capability_values=capabilities,
                estimated_travel_minutes=candidate.estimated_travel_minutes,
                estimated_duration_minutes=candidate.estimated_duration_minutes,
                schedule_conflict_minutes=candidate.schedule_conflict_minutes,
                hard_cost_preview=candidate.hard_cost_preview,
                repeats_previous_behavior=recent_behavior is candidate.behavior_id,
                crosses_location=(
                    candidate.destination_location_id is not None
                    and candidate.destination_location_id != actor.current_location_id
                ),
                joint_action_candidate=candidate.invited_activity_id is not None,
            ),
            raw_target=target,
            raw_events=raw_events,
            numeric=NumericFeatures(
                actor_needs=actor.needs,
                actor_mood=actor.mood,
                actor_personality=actor.personality,
                household_money_ratio=_ratio(
                    household.money, self.catalog.economy.money_low_threshold or 1, maximum=20.0
                ),
                household_food_ratio=_ratio(
                    household.food_units, self.catalog.economy.food_low_threshold or 1, maximum=20.0
                ),
                minute_of_day_sin=round(math.sin(2 * math.pi * minute_of_day / 1440), 9),
                minute_of_day_cos=round(math.cos(2 * math.pi * minute_of_day / 1440), 9),
                weekday_sin=round(math.sin(2 * math.pi * weekday / 7), 9),
                weekday_cos=round(math.cos(2 * math.pi * weekday / 7), 9),
                local_population_ratio=_ratio(local_population, 10),
                known_event_count_ratio=_ratio(len(actor.known_event_ids), len(EventType)),
                decision_overdue_ratio=_ratio(max(0, state.game_minute - actor.decision_due_at), 60),
                travel_ratio=_ratio(candidate.estimated_travel_minutes, MAX_MINUTES_NORMALIZATION),
                duration_ratio=_ratio(candidate.estimated_duration_minutes, MAX_MINUTES_NORMALIZATION),
                schedule_conflict_ratio=_ratio(candidate.schedule_conflict_minutes, MAX_MINUTES_NORMALIZATION),
                money_cost_ratio=_ratio(abs(candidate.hard_cost_preview.household_money), household.money or 1),
                food_cost_ratio=_ratio(
                    abs(candidate.hard_cost_preview.household_food_units), household.food_units or 1
                ),
                target_needs=(state.agents[candidate.target_agent_id].needs if candidate.target_agent_id else None),
                target_mood=(state.agents[candidate.target_agent_id].mood if candidate.target_agent_id else None),
                target_relationship=cast(Any, target_relationship),
                target_interaction_age_ratio=target_age,
                event_importance=cast(Any, event_importance),
                event_age_ratio=cast(Any, event_age),
            ),
            categorical=CategoricalFeatures(
                behavior_index=_index(self.vocabulary, "behavior", candidate.behavior_id),
                actor_current_location_index=location_vocabulary.index(actor.current_location_id),
                actor_home_location_index=location_vocabulary.index(actor.home_location_id),
                actor_work_location_index=location_vocabulary.index(actor.assigned_work_location_id),
                destination_location_type_index=(
                    _index(self.vocabulary, "location_type", destination_type) if destination_type is not None else -1
                ),
                object_type_indices=[_index(self.vocabulary, "object_type", value) for value in object_types],
                capability_indices=[_index(self.vocabulary, "capability", value) for value in capabilities],
                relationship_role_indices=(
                    [_index(self.vocabulary, "relationship_role", role) for role in relationship.roles]
                    if relationship is not None
                    else []
                ),
                event_type_indices=cast(Any, event_indices),
            ),
            masks=FeatureMasks(
                target_present=target is not None,
                relationship_present=relationship is not None,
                acceptance_present=acceptance_present,
                target_mood_present=acceptance_present and bool(behavior.soft_effect_mask.target_mood),
                relationship_delta_present=acceptance_present
                and bool(behavior.soft_effect_mask.relationship_target_to_actor),
                event_mask=cast(Any, event_mask),
            ),
        )

    @staticmethod
    def _event_features(
        state: WorldState,
        actor_id: str,
        target_id: str | None,
        event: WorldEvent,
    ) -> RawEventFeatures:
        participants = {*event.actor_ids, *event.affected_agent_ids}
        return RawEventFeatures(
            event_id=event.event_id,
            event_type=event.event_type,
            importance=event.importance,
            age_minutes=max(0, state.game_minute - event.game_minute),
            actor_is_participant=actor_id in participants,
            target_is_participant=target_id in participants if target_id is not None else False,
            same_location=event.location_id == state.agents[actor_id].current_location_id,
        )

    @staticmethod
    def _target_features(
        state: WorldState,
        actor_id: str,
        target_id: str | None,
        selected_event_id: str | None,
        knowledge_records: Mapping[str, KnowledgeRecord],
        conversations: Mapping[str, ConversationRecord],
    ) -> tuple[RawTargetFeatures | None, RelationshipState | None]:
        if target_id is None:
            return None, None
        target = state.agents[target_id]
        relation = next(
            edge
            for edge in state.relationships
            if edge.source_agent_id == target_id and edge.target_agent_id == actor_id
        )
        active_conversation = any(
            item.active and actor_id in item.participant_ids and target_id in item.participant_ids
            for item in conversations.values()
        )
        knows_event = selected_event_id is not None and knowledge_key(target_id, selected_event_id) in knowledge_records
        return (
            RawTargetFeatures(
                agent_id=target.agent_id,
                needs=target.needs,
                mood=target.mood,
                relationship_roles_target_to_actor=relation.roles,
                relationship_familiarity=relation.familiarity,
                relationship_affinity=relation.affinity,
                relationship_trust=relation.trust,
                relationship_tension=relation.tension,
                minutes_since_interaction=(
                    state.game_minute - relation.last_interaction_minute
                    if relation.last_interaction_minute is not None
                    else None
                ),
                same_household=target.household_id == state.agents[actor_id].household_id,
                coworker=target.assigned_work_location_id == state.agents[actor_id].assigned_work_location_id,
                active_conversation=active_conversation,
                knows_selected_event=knows_event,
            ),
            relation,
        )
