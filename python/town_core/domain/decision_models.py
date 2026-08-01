"""Candidate, prediction, proposal, and transaction contracts for V0."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import UnitValue
from town_core.domain.enums import (
    BehaviorId,
    EventType,
    JointActionAuthority,
    ProposalResult,
    RelationshipDirection,
    RoutePlanningCapability,
)
from town_core.domain.identifiers import (
    ActionId,
    AgentId,
    CandidateId,
    EventId,
    LocationId,
    ObjectId,
    PredictionId,
    ProposalId,
)
from town_core.domain.state_models import MoodDelta, NeedDelta, RelationshipDelta, WorldEvent


class HardCostPreview(ContractModel):
    household_money: int = 0
    household_food_units: int = 0


class CandidateAction(ContractModel):
    candidate_id: CandidateId
    actor_id: AgentId
    behavior_id: BehaviorId
    target_agent_id: AgentId | None
    target_object_ids: list[ObjectId]
    destination_location_id: LocationId | None
    estimated_travel_minutes: NonNegativeInt
    estimated_duration_minutes: NonNegativeInt
    hard_cost_preview: HardCostPreview
    schedule_conflict_minutes: NonNegativeInt
    context_event_ids: list[EventId]
    route_planning: Literal[RoutePlanningCapability.DISABLED]


class OutcomePrediction(ContractModel):
    prediction_id: PredictionId
    candidate_id: CandidateId
    need_delta_preview: NeedDelta
    actor_mood_delta: MoodDelta
    target_mood_delta: MoodDelta | None
    relationship_direction: Literal[RelationshipDirection.TARGET_TO_ACTOR]
    relationship_delta_target_to_actor: RelationshipDelta | None
    acceptance_probability: UnitValue | None
    event_probabilities: dict[EventType, UnitValue]

    @model_validator(mode="after")
    def validate_target_outputs(self) -> OutcomePrediction:
        has_target_output = self.target_mood_delta is not None or self.relationship_delta_target_to_actor is not None
        if has_target_output and self.acceptance_probability is None:
            raise ValueError("targeted social output requires acceptance probability")
        return self


class ActionProposal(ContractModel):
    proposal_id: ProposalId
    state_version: NonNegativeInt
    actor_id: AgentId
    candidate_id: CandidateId
    behavior_id: BehaviorId
    target_agent_id: AgentId | None
    target_object_ids: list[ObjectId]
    score: float
    model_prediction_id: PredictionId


class JointActionParticipant(ContractModel):
    agent_id: AgentId
    proposal_id: ProposalId


class JointAction(ContractModel):
    action_id: ActionId
    behavior_id: BehaviorId
    authority: Literal[JointActionAuthority.CENTRAL_RESOLVER]
    state_version: NonNegativeInt
    location_id: LocationId
    participants: Annotated[list[JointActionParticipant], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def validate_central_order(self) -> JointAction:
        agent_ids = [participant.agent_id for participant in self.participants]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("joint action agents must be unique")
        if agent_ids != sorted(agent_ids):
            raise ValueError("central resolver emits participants in agent ID order")
        return self


class HardEffect(ContractModel):
    field_path: Annotated[str, Field(min_length=1)]
    delta_integer: int | None = None
    set_string: str | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> HardEffect:
        if (self.delta_integer is None) == (self.set_string is None):
            raise ValueError("hard effect must declare exactly one operation")
        return self


class SoftEffect(ContractModel):
    actor_id: AgentId
    target_id: AgentId | None
    actor_mood_delta: MoodDelta
    target_mood_delta: MoodDelta | None
    relationship_direction: Literal[RelationshipDirection.TARGET_TO_ACTOR]
    relationship_delta_target_to_actor: RelationshipDelta | None


class ResolvedAction(ContractModel):
    action_id: ActionId
    source_proposal_ids: Annotated[list[ProposalId], Field(min_length=1)]
    result: ProposalResult
    hard_effects: list[HardEffect]
    soft_effects: list[SoftEffect]
    emitted_events: list[WorldEvent]


class StateTransaction(ContractModel):
    expected_state_version: NonNegativeInt
    resolved_actions: Annotated[list[ResolvedAction], Field(min_length=1)]
    committed_event_ids: list[EventId]
