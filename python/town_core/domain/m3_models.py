"""Additive cross-component M3 candidate and JointAction metadata contracts.

The authority checkpoint and its private ledgers are SIM-owned in
``town_core.society.models``. CONTRACTS deliberately does not duplicate them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.decision_models import CandidateAction
from town_core.domain.enums import ActionParticipantRole, ActionPhase, BehaviorId, JointActionAuthority
from town_core.domain.identifiers import (
    ActionId,
    AgentId,
    ConversationId,
    EventId,
    LocationId,
    ObjectId,
    ProposalId,
)

INVITED_ACTIVITY_ALLOWLIST = (
    BehaviorId.WATCH_TV,
    BehaviorId.EAT_AT_CAFE,
    BehaviorId.DRINK_AT_BAR,
    BehaviorId.WALK_IN_PARK,
    BehaviorId.SIT_IN_PARK,
)


class M3CandidateAction(CandidateAction):
    """M3-only candidate additions; the accepted M1 candidate stays unchanged."""

    selected_context_event_id: EventId | None = None
    target_conversation_id: ConversationId | None = None
    invited_activity_id: BehaviorId | None = None

    @model_validator(mode="after")
    def validate_typed_targets(self) -> M3CandidateAction:
        if self.selected_context_event_id is not None and self.selected_context_event_id not in self.context_event_ids:
            raise ValueError("selected_context_event_id must appear in context_event_ids")
        if self.behavior_id is BehaviorId.SHARE_EVENT and self.selected_context_event_id is None:
            raise ValueError("share_event requires selected_context_event_id")
        if self.behavior_id is BehaviorId.END_CONVERSATION:
            if self.target_conversation_id is None:
                raise ValueError("end_conversation requires target_conversation_id")
        elif self.target_conversation_id is not None:
            raise ValueError("target_conversation_id is only valid for end_conversation")
        if self.behavior_id is BehaviorId.INVITE_JOIN:
            if self.invited_activity_id not in INVITED_ACTIVITY_ALLOWLIST:
                raise ValueError("invite_join requires an invited activity from the frozen M3 allowlist")
        elif self.invited_activity_id is not None:
            raise ValueError("invited_activity_id is only valid for invite_join")
        return self


class PresentationObjectBinding(ContractModel):
    object_id: ObjectId
    slot_index: NonNegativeInt


class JointParticipantMetadata(ContractModel):
    agent_id: AgentId
    proposal_id: ProposalId
    role: ActionParticipantRole
    object_bindings: list[PresentationObjectBinding]


class JointActionPresentationMetadata(ContractModel):
    """Cross-line presentation projection, not the SIM-owned authority aggregate."""

    action_id: ActionId
    behavior_id: BehaviorId
    invited_activity_id: BehaviorId | None
    authority: Literal[JointActionAuthority.CENTRAL_RESOLVER]
    source_state_version: NonNegativeInt
    location_id: LocationId
    conversation_id: ConversationId | None
    phase: ActionPhase
    participants: Annotated[list[JointParticipantMetadata], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def validate_joint_metadata(self) -> JointActionPresentationMetadata:
        agent_ids = [item.agent_id for item in self.participants]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("JointAction participant agents must be unique")
        if agent_ids != sorted(agent_ids):
            raise ValueError("JointAction participants must use stable agent ID order")
        if sum(item.role is ActionParticipantRole.ACTOR for item in self.participants) != 1:
            raise ValueError("JointAction requires exactly one ACTOR")
        if self.invited_activity_id is not None and self.invited_activity_id not in INVITED_ACTIVITY_ALLOWLIST:
            raise ValueError("JointAction invited activity is outside the frozen M3 allowlist")
        return self
