"""Deterministic catalog-backed candidate and heuristic rules for M3."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from town_core.domain.config_models import BehaviorConfig, CatalogBundle, DeltaBounds
from town_core.domain.decision_models import HardCostPreview, OutcomePrediction
from town_core.domain.enums import (
    BehaviorId,
    EventType,
    LocationType,
    MoodAxis,
    NeedName,
    RelationshipDirection,
    RoutePlanningCapability,
)
from town_core.domain.m3_models import M3CandidateAction
from town_core.domain.state_models import (
    MoodDelta,
    NeedDelta,
    RelationshipDelta,
    RelationshipState,
    WorldEvent,
    WorldState,
)
from town_core.society.models import (
    ConversationRecord,
    ScoredSocietyCandidate,
    SocietyCandidate,
    WorkSessionRecord,
)

HEURISTIC_PROVIDER_ID = "M3_CATALOG_BOUNDED_HEURISTIC_V1"
NEED_CRISIS_RECOVERY_BONUS = 5.0
HOUSEHOLD_FOOD_SUPPLY_BONUS = 30.0
CONFLICT_RESPONSE_BONUS = 1.0

_NEED_CRISIS_RECOVERY_PRIORITY = {
    NeedName.HUNGER: 5.0,
    NeedName.ENERGY: 4.0,
    NeedName.SOCIAL: 3.0,
    NeedName.HYGIENE: 2.0,
    NeedName.FUN: 1.0,
}
_NEED_LIVENESS_FLOOR = {NeedName.SOCIAL: 0.30}

_CONFRONT_TRIGGER_EVENTS = frozenset(
    {
        EventType.AWKWARD_INTERACTION,
        EventType.INVITATION_REJECTED,
        EventType.APOLOGY_REJECTED,
        EventType.COWORKER_EXTRA_LOAD,
        EventType.CONFLICT_STARTED,
        EventType.CONFLICT_ESCALATED,
    }
)


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    behavior_id: BehaviorId
    target_agent_id: str | None
    target_object_ids: tuple[str, ...]
    destination_location_id: str | None
    travel_minutes: int
    duration_minutes: int
    hard_cost: HardCostPreview
    schedule_conflict_minutes: int
    selected_context_event_id: str | None = None
    target_conversation_id: str | None = None
    invited_activity_id: BehaviorId | None = None


def stable_unit(*parts: object) -> float:
    material = "|".join(str(item) for item in parts).encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return integer / float((1 << 64) - 1)


def midpoint(bounds: DeltaBounds) -> float:
    return (bounds.minimum + bounds.maximum) / 2.0


class SocietyRulebook:
    """Complete V0 rule registry; catalogs remain the only behavior source."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self.catalog = catalog
        self.behaviors = {item.behavior_id: item for item in catalog.behaviors.behaviors}
        if set(self.behaviors) != set(BehaviorId):
            raise ValueError("M3 rulebook requires the complete frozen 22-behavior catalog")
        self.locations = {item.location_id: item for item in catalog.locations.locations}
        self.location_by_type = {
            location_type: min(
                item.location_id for item in catalog.locations.locations if item.location_type is location_type
            )
            for location_type in LocationType
        }
        self.events_by_id: dict[str, object] = {}
        self._behavior_order = {
            behavior.behavior_id: index for index, behavior in enumerate(catalog.behaviors.behaviors)
        }

    def enumerate_candidates(
        self,
        state: WorldState,
        agent_id: str,
        *,
        work_session: WorkSessionRecord | None,
        conversations: Mapping[str, ConversationRecord],
        event_importance: Mapping[str, float],
        events_by_id: Mapping[str, WorldEvent] | None = None,
        reserved_money: int,
        reserved_food: int,
        next_candidate_id: Callable[[], str],
        behavior_allowlist: frozenset[BehaviorId] | None = None,
    ) -> list[SocietyCandidate]:
        agent = state.agents[agent_id]
        if not agent.enabled or agent.current_action_id is not None or agent.current_location_id == "TRAVELING":
            return []

        household = state.households[agent.household_id]
        available_money = household.money - reserved_money
        available_food = household.food_units - reserved_food
        relationship_by_target = {
            edge.target_agent_id: edge for edge in state.relationships if edge.source_agent_id == agent_id
        }
        incoming_relationship = {
            edge.source_agent_id: edge for edge in state.relationships if edge.target_agent_id == agent_id
        }
        active_conversations = [
            item for item in conversations.values() if item.active and agent_id in item.participant_ids
        ]
        social_targets = self._social_targets(state, agent_id, relationship_by_target)
        drafts: list[CandidateDraft] = []

        for behavior_id in BehaviorId:
            if behavior_allowlist is not None and behavior_id not in behavior_allowlist:
                continue
            behavior = self.behaviors[behavior_id]
            if behavior_id is BehaviorId.IDLE:
                drafts.append(self._draft(state, agent_id, behavior, destination=agent.current_location_id))
                continue
            if behavior_id is BehaviorId.SLEEP and agent.needs.energy < 0.98:
                self._append_object_draft(drafts, state, agent_id, behavior, agent.home_location_id, work_session)
            elif behavior_id is BehaviorId.EAT_AT_HOME and available_food >= 1:
                self._append_object_draft(
                    drafts,
                    state,
                    agent_id,
                    behavior,
                    agent.home_location_id,
                    work_session,
                    hard_cost=HardCostPreview(household_food_units=-1),
                )
            elif (
                behavior_id is BehaviorId.SHOWER
                and agent.needs.hygiene < 0.95
                or behavior_id in {BehaviorId.WATCH_TV, BehaviorId.RELAX_AT_HOME}
                and agent.needs.fun < 0.92
            ):
                self._append_object_draft(drafts, state, agent_id, behavior, agent.home_location_id, work_session)
            elif (
                behavior_id is BehaviorId.WORK_SHIFT
                and self._work_candidate_due(state, work_session)
                or behavior_id is BehaviorId.TAKE_BREAK
                and self._break_legal(state, agent_id, work_session)
            ):
                draft_count = len(drafts)
                self._append_object_draft(
                    drafts,
                    state,
                    agent_id,
                    behavior,
                    agent.assigned_work_location_id,
                    work_session,
                )
                if (
                    behavior_id is BehaviorId.TAKE_BREAK
                    and len(drafts) > draft_count
                    and work_session is not None
                    and not self._break_preserves_completion(
                        state.game_minute + drafts[-1].travel_minutes,
                        drafts[-1].duration_minutes,
                        work_session,
                    )
                ):
                    drafts.pop()
            elif behavior_id is BehaviorId.BUY_GROCERIES:
                price = self.catalog.economy.groceries.price
                if household.food_units <= self.catalog.economy.food_low_threshold and available_money >= price:
                    self._append_object_draft(
                        drafts,
                        state,
                        agent_id,
                        behavior,
                        self.location_by_type[LocationType.SHOP],
                        work_session,
                        hard_cost=HardCostPreview(
                            household_money=-price,
                            household_food_units=self.catalog.economy.groceries.food_units_delta,
                        ),
                    )
            elif behavior_id is BehaviorId.EAT_AT_CAFE:
                price = self.catalog.economy.cafe_meal.price
                if agent.needs.hunger < 0.80 and available_money >= price:
                    self._append_object_draft(
                        drafts,
                        state,
                        agent_id,
                        behavior,
                        self.location_by_type[LocationType.CAFE_BAR],
                        work_session,
                        hard_cost=HardCostPreview(household_money=-price),
                    )
            elif behavior_id is BehaviorId.DRINK_AT_BAR:
                price = self.catalog.economy.bar_drink.price
                if agent.needs.fun < 0.82 and available_money >= price:
                    self._append_object_draft(
                        drafts,
                        state,
                        agent_id,
                        behavior,
                        self.location_by_type[LocationType.CAFE_BAR],
                        work_session,
                        hard_cost=HardCostPreview(household_money=-price),
                    )
            elif behavior_id in {BehaviorId.WALK_IN_PARK, BehaviorId.SIT_IN_PARK} and agent.needs.fun < 0.92:
                self._append_object_draft(
                    drafts,
                    state,
                    agent_id,
                    behavior,
                    self.location_by_type[LocationType.PARK],
                    work_session,
                )
            elif behavior_id in {
                BehaviorId.GREET,
                BehaviorId.CHAT,
                BehaviorId.JOKE,
                BehaviorId.COMPLIMENT,
                BehaviorId.SHARE_EVENT,
                BehaviorId.INVITE_JOIN,
                BehaviorId.APOLOGIZE,
                BehaviorId.CONFRONT,
            }:
                self._append_social_drafts(
                    drafts,
                    state,
                    agent_id,
                    behavior,
                    social_targets,
                    incoming_relationship,
                    event_importance,
                    events_by_id or {},
                )
            elif behavior_id is BehaviorId.END_CONVERSATION:
                for conversation in sorted(active_conversations, key=lambda item: item.conversation_id)[:1]:
                    target_ids = [item for item in conversation.participant_ids if item != agent_id]
                    if target_ids:
                        drafts.append(
                            self._draft(
                                state,
                                agent_id,
                                behavior,
                                destination=agent.current_location_id,
                                target_agent_id=target_ids[0],
                                target_conversation_id=conversation.conversation_id,
                            )
                        )

        drafts = self._cap_drafts(drafts)
        candidates: list[SocietyCandidate] = []
        for draft in drafts:
            candidate = M3CandidateAction(
                candidate_id=next_candidate_id(),
                actor_id=agent_id,
                behavior_id=draft.behavior_id,
                target_agent_id=draft.target_agent_id,
                target_object_ids=list(draft.target_object_ids),
                destination_location_id=draft.destination_location_id,
                estimated_travel_minutes=draft.travel_minutes,
                estimated_duration_minutes=draft.duration_minutes,
                hard_cost_preview=draft.hard_cost,
                schedule_conflict_minutes=draft.schedule_conflict_minutes,
                context_event_ids=(
                    [draft.selected_context_event_id] if draft.selected_context_event_id is not None else []
                ),
                route_planning=RoutePlanningCapability.DISABLED,
                selected_context_event_id=draft.selected_context_event_id,
                target_conversation_id=draft.target_conversation_id,
                invited_activity_id=draft.invited_activity_id,
            )
            candidates.append(SocietyCandidate(candidate=candidate))
        return candidates

    def predict(
        self,
        state: WorldState,
        candidate: SocietyCandidate,
        *,
        prediction_id: str,
    ) -> OutcomePrediction:
        base = candidate.candidate
        behavior = self.behaviors[base.behavior_id]
        need_values = {axis.value: 0.0 for axis in NeedName}
        for need_axis, bounds in behavior.output_bounds.need_deltas.items():
            need_values[need_axis.value] = midpoint(bounds)
        actor_mood_values = {axis.value: 0.0 for axis in MoodAxis}
        for mood_axis, bounds in behavior.output_bounds.actor_mood_deltas.items():
            actor_mood_values[mood_axis.value] = midpoint(bounds)

        target_mood: MoodDelta | None = None
        relationship_delta: RelationshipDelta | None = None
        acceptance: float | None = None
        if base.target_agent_id is not None and behavior.soft_effect_mask.acceptance:
            target_mood_values = {axis.value: 0.0 for axis in MoodAxis}
            for mood_axis, bounds in behavior.output_bounds.target_mood_deltas.items():
                target_mood_values[mood_axis.value] = midpoint(bounds)
            target_mood = MoodDelta(**target_mood_values)
            relationship_values = {
                "familiarity": 0.0,
                "affinity": 0.0,
                "trust": 0.0,
                "tension": 0.0,
            }
            for relationship_axis, bounds in behavior.output_bounds.relationship_target_to_actor.items():
                relationship_values[relationship_axis.value] = midpoint(bounds)
            relationship_delta = RelationshipDelta(**relationship_values)
            acceptance = self.acceptance_probability(state, base.actor_id, base.target_agent_id, base.behavior_id)

        return OutcomePrediction(
            prediction_id=prediction_id,
            candidate_id=base.candidate_id,
            need_delta_preview=NeedDelta(**need_values),
            actor_mood_delta=MoodDelta(**actor_mood_values),
            target_mood_delta=target_mood,
            relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
            relationship_delta_target_to_actor=relationship_delta,
            acceptance_probability=acceptance,
            event_probabilities={event_type: 1.0 for event_type in behavior.emitted_event_types},
        )

    def score_candidates(
        self,
        state: WorldState,
        candidates: Sequence[SocietyCandidate],
        predictions: Mapping[str, OutcomePrediction],
        *,
        work_session: WorkSessionRecord | None,
        recent_behavior: BehaviorId | None,
        event_importance: Mapping[str, float],
    ) -> list[ScoredSocietyCandidate]:
        scored = [
            self._score_one(
                state,
                item,
                predictions[item.candidate.candidate_id],
                work_session=work_session,
                recent_behavior=recent_behavior,
                event_importance=event_importance,
            )
            for item in candidates
        ]
        best_non_idle = max(
            (item.total_score for item in scored if item.candidate.candidate.behavior_id is not BehaviorId.IDLE),
            default=float("-inf"),
        )
        if best_non_idle > self.catalog.utility.weights.idle_penalty:
            rescored: list[ScoredSocietyCandidate] = []
            for item in scored:
                if item.candidate.candidate.behavior_id is BehaviorId.IDLE:
                    terms = dict(item.utility_terms)
                    terms["idle_penalty"] = -self.catalog.utility.weights.idle_penalty
                    total = round(sum(terms.values()), 12)
                    item = item.model_copy(update={"utility_terms": terms, "total_score": total})
                rescored.append(item)
            scored = rescored
        return sorted(
            scored,
            key=lambda item: (-item.total_score, -item.tie_break, item.candidate.candidate.candidate_id),
        )

    def acceptance_probability(
        self,
        state: WorldState,
        actor_id: str,
        target_id: str,
        behavior_id: BehaviorId,
    ) -> float:
        target_to_actor = self.relationship(state, target_id, actor_id)
        actor = state.agents[actor_id]
        target = state.agents[target_id]
        bias = {
            BehaviorId.GREET: 0.18,
            BehaviorId.CHAT: 0.12,
            BehaviorId.JOKE: 0.0,
            BehaviorId.COMPLIMENT: 0.05,
            BehaviorId.INVITE_JOIN: -0.02,
            BehaviorId.APOLOGIZE: -0.05,
            BehaviorId.CONFRONT: -0.20,
        }.get(behavior_id, 0.0)
        raw = (
            0.38
            + bias
            + (0.20 * target_to_actor.affinity)
            + (0.18 * target_to_actor.trust)
            + (0.08 * target_to_actor.familiarity)
            - (0.28 * target_to_actor.tension)
            + (0.08 * actor.personality.sociability)
            - (0.08 * target.mood.stress)
        )
        return round(max(0.05, min(0.95, raw)), 6)

    @staticmethod
    def relationship(state: WorldState, source_id: str, target_id: str) -> RelationshipState:
        return next(
            edge
            for edge in state.relationships
            if edge.source_agent_id == source_id and edge.target_agent_id == target_id
        )

    def _score_one(
        self,
        state: WorldState,
        item: SocietyCandidate,
        prediction: OutcomePrediction,
        *,
        work_session: WorkSessionRecord | None,
        recent_behavior: BehaviorId | None,
        event_importance: Mapping[str, float],
    ) -> ScoredSocietyCandidate:
        candidate = item.candidate
        actor = state.agents[candidate.actor_id]
        weights = self.catalog.utility.weights
        need_utility = 0.0
        for axis in NeedName:
            delta = float(getattr(prediction.need_delta_preview, axis.value))
            current = float(getattr(actor.needs, axis.value))
            need_utility += delta * (((1.0 - current) ** 2) * 4.0 if delta >= 0 else max(0.25, current))
        mood_utility = float(prediction.actor_mood_delta.valence) - float(prediction.actor_mood_delta.stress)
        schedule = 0.0
        if work_session is not None:
            if candidate.behavior_id is BehaviorId.WORK_SHIFT:
                schedule = (2.0 if state.game_minute >= work_session.start_game_minute else 1.0) * (
                    1.0 + actor.personality.discipline
                )
            elif candidate.behavior_id is BehaviorId.TAKE_BREAK:
                # A completion-safe scheduled break is part of the shift rather
                # than an arbitrary conflict with it. The hard legality check
                # guarantees the frozen M1 grace/minimum-work settlement still
                # succeeds if the remaining shift is worked.
                schedule = 2.0 * (1.0 + actor.personality.discipline)
            elif candidate.schedule_conflict_minutes:
                schedule = -(candidate.schedule_conflict_minutes / 60.0) * (1.0 + actor.personality.discipline)
        relationship_utility = 0.0
        if prediction.relationship_delta_target_to_actor is not None:
            relationship_prediction = prediction.relationship_delta_target_to_actor
            relationship_utility = (
                relationship_prediction.affinity
                + relationship_prediction.trust
                + (0.5 * relationship_prediction.familiarity)
                - relationship_prediction.tension
            )
            relationship_utility *= 0.5 + actor.personality.sociability
        known_event_utility = event_importance.get(item.selected_context_event_id or "", 0.0)
        household = state.households[actor.household_id]
        cost_ratio = 0.0
        if candidate.hard_cost_preview.household_money < 0:
            cost_ratio = abs(candidate.hard_cost_preview.household_money) / max(1, household.money)
        repetition = 1.0 if recent_behavior is candidate.behavior_id else 0.0
        work_due = self._work_candidate_due(state, work_session)
        available_at_arrival = candidate.destination_location_id is None or self.location_open(
            candidate.destination_location_id,
            state.game_minute + candidate.estimated_travel_minutes,
        )
        need_crisis_recovery = 0.0
        for axis, threshold in self.catalog.utility.need_crisis_thresholds.items():
            recovery_threshold = max(float(threshold), _NEED_LIVENESS_FLOOR.get(axis, 0.0))
            current = float(getattr(actor.needs, axis.value))
            delta = float(getattr(prediction.need_delta_preview, axis.value))
            if (
                current <= recovery_threshold
                and delta > 0.0
                and available_at_arrival
                and (not work_due or candidate.behavior_id is BehaviorId.TAKE_BREAK or current <= 0.0)
            ):
                severity = (recovery_threshold - current) / max(recovery_threshold, 1e-9)
                need_crisis_recovery += (
                    NEED_CRISIS_RECOVERY_BONUS * _NEED_CRISIS_RECOVERY_PRIORITY[axis] * (1.0 + severity)
                )
        household_food_supply = 0.0
        if candidate.behavior_id is BehaviorId.BUY_GROCERIES and not work_due and available_at_arrival:
            shortage = max(0, (self.catalog.economy.food_low_threshold + 1) - household.food_units)
            household_food_supply = HOUSEHOLD_FOOD_SUPPLY_BONUS * (
                shortage / max(1, self.catalog.economy.food_low_threshold + 1)
            )
        conflict_response = 0.0
        if (
            candidate.behavior_id is BehaviorId.CONFRONT
            and item.selected_context_event_id is not None
            and available_at_arrival
        ):
            conflict_response = CONFLICT_RESPONSE_BONUS + event_importance.get(item.selected_context_event_id, 0.0)
        critical_need_block = 0.0
        if candidate.behavior_id is BehaviorId.WORK_SHIFT:
            critical_need_block = -100.0 * sum(float(getattr(actor.needs, axis.value)) <= 0.0 for axis in NeedName)
        tie = (
            stable_unit(
                "stwm-m3",
                state.random_seed,
                state.state_version,
                candidate.actor_id,
                candidate.behavior_id.value,
                candidate.target_agent_id,
                item.selected_context_event_id,
                item.invited_activity_id,
            )
            * 2.0
        ) - 1.0
        terms = {
            "needs": weights.needs * need_utility,
            "mood": weights.mood * mood_utility,
            "schedule": weights.schedule * schedule,
            "relationship": weights.relationship * relationship_utility,
            "known_events": weights.known_events * known_event_utility,
            "money_cost": -weights.money_cost * cost_ratio * (1.0 + actor.personality.frugality),
            "travel_cost": -weights.travel_cost * (candidate.estimated_travel_minutes / 60.0),
            "interrupt_cost": 0.0,
            "repetition_penalty": -weights.repetition_penalty * repetition,
            "need_crisis_recovery": need_crisis_recovery,
            "household_food_supply": household_food_supply,
            "conflict_response": conflict_response,
            "critical_need_block": critical_need_block,
            "idle_penalty": 0.0,
            "deterministic_noise": tie * self.catalog.utility.deterministic_noise_amplitude,
        }
        return ScoredSocietyCandidate(
            candidate=item,
            prediction=prediction,
            utility_terms=terms,
            total_score=round(sum(terms.values()), 12),
            tie_break=tie,
        )

    def _draft(
        self,
        state: WorldState,
        agent_id: str,
        behavior: BehaviorConfig,
        *,
        destination: str | None,
        target_agent_id: str | None = None,
        target_object_ids: Sequence[str] = (),
        hard_cost: HardCostPreview | None = None,
        work_session: WorkSessionRecord | None = None,
        selected_context_event_id: str | None = None,
        target_conversation_id: str | None = None,
        invited_activity_id: BehaviorId | None = None,
    ) -> CandidateDraft:
        agent = state.agents[agent_id]
        travel = (
            0
            if destination is None or destination == agent.current_location_id
            else self.locations[agent.current_location_id].travel_minutes[destination]
        )
        unit = stable_unit(
            "duration-v1",
            state.random_seed,
            state.state_version,
            agent_id,
            behavior.behavior_id.value,
            target_agent_id,
            selected_context_event_id,
            invited_activity_id,
        )
        minimum = max(1, behavior.duration_minutes.base - behavior.duration_minutes.variance)
        maximum = behavior.duration_minutes.base + behavior.duration_minutes.variance
        duration = minimum + int(unit * ((maximum - minimum) + 1))
        if behavior.behavior_id is BehaviorId.SLEEP and any(
            axis is not NeedName.ENERGY
            and float(getattr(agent.needs, axis.value)) <= self.catalog.utility.need_crisis_thresholds[axis]
            for axis in NeedName
        ):
            duration = min(duration, 120)
        if behavior.behavior_id is BehaviorId.WATCH_TV and agent.needs.social <= 0.0:
            # Choose the shortest catalog-legal local recovery episode once
            # social reaches zero. Travel plus a randomized long TV session
            # otherwise consumes most of the frozen 360-minute recovery bound.
            duration = minimum
        if behavior.behavior_id is BehaviorId.WORK_SHIFT and work_session is not None:
            perform_start = max(state.game_minute + travel, work_session.start_game_minute)
            duration = max(1, min(behavior.duration_minutes.base, work_session.end_game_minute - perform_start))
        conflict = self._schedule_conflict(state.game_minute + travel, duration, work_session)
        return CandidateDraft(
            behavior_id=behavior.behavior_id,
            target_agent_id=target_agent_id,
            target_object_ids=tuple(target_object_ids),
            destination_location_id=destination,
            travel_minutes=travel,
            duration_minutes=duration,
            hard_cost=hard_cost or HardCostPreview(),
            schedule_conflict_minutes=conflict,
            selected_context_event_id=selected_context_event_id,
            target_conversation_id=target_conversation_id,
            invited_activity_id=invited_activity_id,
        )

    def _append_object_draft(
        self,
        drafts: list[CandidateDraft],
        state: WorldState,
        agent_id: str,
        behavior: BehaviorConfig,
        destination: str,
        work_session: WorkSessionRecord | None,
        *,
        hard_cost: HardCostPreview | None = None,
    ) -> None:
        object_ids = self._object_bundle(state, agent_id, behavior, destination)
        if object_ids is None:
            return
        drafts.append(
            self._draft(
                state,
                agent_id,
                behavior,
                destination=destination,
                target_object_ids=object_ids,
                hard_cost=hard_cost,
                work_session=work_session,
            )
        )

    def _append_social_drafts(
        self,
        drafts: list[CandidateDraft],
        state: WorldState,
        agent_id: str,
        behavior: BehaviorConfig,
        targets: Sequence[str],
        incoming_relationship: Mapping[str, RelationshipState],
        event_importance: Mapping[str, float],
        events_by_id: Mapping[str, WorldEvent],
    ) -> None:
        agent = state.agents[agent_id]
        for target_id in targets[:2]:
            edge = incoming_relationship[target_id]
            cooldown_key = f"{behavior.behavior_id.value}:{target_id}"
            if agent.social_cooldowns.get(cooldown_key, 0) > state.game_minute:
                continue
            if (
                behavior.behavior_id is BehaviorId.GREET
                and edge.last_interaction_minute is not None
                and state.game_minute - edge.last_interaction_minute < 1440
            ):
                continue
            if behavior.behavior_id is BehaviorId.APOLOGIZE and edge.tension < 0.30:
                continue
            confront_event_id: str | None = None
            if behavior.behavior_id is BehaviorId.CONFRONT and edge.tension < 0.50:
                confront_event_id = self._target_related_negative_event(
                    state,
                    actor_id=agent_id,
                    target_id=target_id,
                    relationship=edge,
                    events_by_id=events_by_id,
                )
                if confront_event_id is None:
                    continue
            anchor_ids = self._social_anchor(state, str(agent.current_location_id))
            if behavior.behavior_id is BehaviorId.SHARE_EVENT:
                known = sorted(
                    agent.known_event_ids,
                    key=lambda event_id: (-event_importance.get(event_id, 0.0), event_id),
                )[:2]
                for event_id in known:
                    drafts.append(
                        self._draft(
                            state,
                            agent_id,
                            behavior,
                            destination=str(agent.current_location_id),
                            target_agent_id=target_id,
                            target_object_ids=anchor_ids,
                            selected_context_event_id=event_id,
                        )
                    )
            elif behavior.behavior_id is BehaviorId.INVITE_JOIN:
                activities = self._invite_activities(state, agent_id)[:2]
                for activity in activities:
                    drafts.append(
                        self._draft(
                            state,
                            agent_id,
                            behavior,
                            destination=str(agent.current_location_id),
                            target_agent_id=target_id,
                            target_object_ids=anchor_ids,
                            invited_activity_id=activity,
                        )
                    )
            else:
                drafts.append(
                    self._draft(
                        state,
                        agent_id,
                        behavior,
                        destination=str(agent.current_location_id),
                        target_agent_id=target_id,
                        target_object_ids=anchor_ids,
                        selected_context_event_id=confront_event_id,
                    )
                )

    def _object_bundle(
        self,
        state: WorldState,
        agent_id: str,
        behavior: BehaviorConfig,
        destination: str,
    ) -> list[str] | None:
        selected: list[str] = []
        for requirement in behavior.object_requirements:
            matching = sorted(
                (
                    obj
                    for obj in state.objects.values()
                    if obj.enabled
                    and obj.location_id == destination
                    and obj.object_type in requirement.accepted_object_types
                    and requirement.capability in obj.capability_tags
                    and len(obj.occupied_slots) < obj.slot_count
                ),
                key=lambda obj: (
                    obj.metadata.get("assigned_agent_id") != agent_id,
                    obj.object_id,
                ),
            )
            available = [item for item in matching if item.object_id not in selected]
            if len(available) < requirement.quantity:
                return None
            selected.extend(item.object_id for item in available[: requirement.quantity])
        return selected

    @staticmethod
    def _social_targets(
        state: WorldState,
        agent_id: str,
        relationship_by_target: Mapping[str, RelationshipState],
    ) -> list[str]:
        actor = state.agents[agent_id]
        if actor.current_location_id == "TRAVELING":
            return []
        targets = [
            target_id
            for target_id in state.locations[actor.current_location_id].current_agent_ids
            if target_id != agent_id
            and state.agents[target_id].enabled
            and state.agents[target_id].current_action_id is None
        ]
        return sorted(
            targets,
            key=lambda target_id: (
                -relationship_by_target[target_id].familiarity,
                -relationship_by_target[target_id].affinity,
                target_id,
            ),
        )

    @staticmethod
    def _target_related_negative_event(
        state: WorldState,
        *,
        actor_id: str,
        target_id: str,
        relationship: RelationshipState,
        events_by_id: Mapping[str, WorldEvent],
    ) -> str | None:
        candidates: list[WorldEvent] = []
        for event_id in state.agents[actor_id].known_event_ids:
            event = events_by_id.get(event_id)
            if event is None or event.event_type not in _CONFRONT_TRIGGER_EVENTS:
                continue
            participants = {*event.actor_ids, *event.affected_agent_ids}
            if actor_id not in participants or target_id not in participants:
                continue
            if state.game_minute - event.game_minute > 360:
                continue
            if (
                relationship.last_interaction_minute is not None
                and event.game_minute < relationship.last_interaction_minute
            ):
                continue
            candidates.append(event)
        if not candidates:
            return None
        return min(candidates, key=lambda event: (-event.game_minute, event.event_id)).event_id

    @staticmethod
    def _social_anchor(state: WorldState, location_id: str) -> list[str]:
        anchors = sorted(
            obj.object_id
            for obj in state.objects.values()
            if obj.location_id == location_id
            and "SOCIAL_POSITION" in {str(tag) for tag in obj.capability_tags}
            and len(obj.occupied_slots) < obj.slot_count
        )
        return anchors[:1]

    def _invite_activities(self, state: WorldState, agent_id: str) -> list[BehaviorId]:
        actor = state.agents[agent_id]
        preferred = [
            BehaviorId.WATCH_TV,
            BehaviorId.SIT_IN_PARK,
            BehaviorId.WALK_IN_PARK,
            BehaviorId.EAT_AT_CAFE,
            BehaviorId.DRINK_AT_BAR,
        ]
        if actor.needs.hunger < actor.needs.fun:
            preferred = [BehaviorId.EAT_AT_CAFE, *[item for item in preferred if item is not BehaviorId.EAT_AT_CAFE]]
        return preferred

    def _cap_drafts(self, drafts: Sequence[CandidateDraft]) -> list[CandidateDraft]:
        idle = next((item for item in drafts if item.behavior_id is BehaviorId.IDLE), None)
        non_idle = [item for item in drafts if item.behavior_id is not BehaviorId.IDLE]
        non_idle.sort(
            key=lambda item: (
                0 if item.behavior_id is BehaviorId.WORK_SHIFT else 1,
                0 if item.behavior_id is BehaviorId.CONFRONT and item.selected_context_event_id is not None else 1,
                self._behavior_order[item.behavior_id],
                item.target_agent_id or "",
                item.selected_context_event_id or "",
                item.invited_activity_id.value if item.invited_activity_id is not None else "",
                item.target_object_ids,
            )
        )
        if idle is None:
            return non_idle[: self.catalog.utility.max_candidates_per_agent]
        return [*non_idle[: self.catalog.utility.max_candidates_per_agent - 1], idle]

    def _travel_minutes(self, state: WorldState, agent_id: str, destination: str) -> int:
        origin = state.agents[agent_id].current_location_id
        if origin == destination:
            return 0
        if origin == "TRAVELING":
            raise ValueError("traveling agent cannot enumerate a new candidate")
        return self.locations[origin].travel_minutes[destination]

    @staticmethod
    def _schedule_conflict(start: int, duration: int, work_session: WorkSessionRecord | None) -> int:
        if work_session is None or work_session.finalized:
            return 0
        end = start + duration
        return max(
            0,
            min(end, work_session.end_game_minute) - max(start, work_session.start_game_minute),
        )

    @staticmethod
    def _work_candidate_due(state: WorldState, work_session: WorkSessionRecord | None) -> bool:
        return (
            work_session is not None
            and not work_session.finalized
            and work_session.start_game_minute - 60 <= state.game_minute < work_session.end_game_minute
        )

    @staticmethod
    def _break_legal(state: WorldState, agent_id: str, work_session: WorkSessionRecord | None) -> bool:
        if work_session is None or work_session.finalized:
            return False
        agent = state.agents[agent_id]
        return (
            agent.current_location_id == agent.assigned_work_location_id
            and work_session.start_game_minute + 120 <= state.game_minute < work_session.end_game_minute - 30
            and work_session.effective_work_minutes > 0
            and not work_session.completed_break_action_ids
        )

    @staticmethod
    def _break_preserves_completion(
        break_start: int,
        duration_minutes: int,
        work_session: WorkSessionRecord,
    ) -> bool:
        break_end = break_start + duration_minutes
        possible_effective = work_session.effective_work_minutes + max(
            0,
            work_session.end_game_minute - break_end,
        )
        scheduled = work_session.end_game_minute - work_session.start_game_minute
        return possible_effective >= scheduled - work_session.grace_minutes

    def location_open(self, location_id: str, game_minute: int) -> bool:
        minute_of_day = game_minute % 1440
        return any(
            interval.start_minute_of_day <= minute_of_day < interval.end_minute_of_day
            for interval in self.locations[location_id].open_intervals
        )
