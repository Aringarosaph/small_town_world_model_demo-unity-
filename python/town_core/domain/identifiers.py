"""Lexical ID contracts; runtime uniqueness is validated by owning services."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

AgentId = Annotated[str, Field(pattern=r"^npc_[0-9]{2}$")]
HouseholdId = Annotated[str, Field(pattern=r"^household_[a-z]$")]
LocationId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
ObjectId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*_[0-9]{2}$")]
ActionId = Annotated[str, Field(pattern=r"^action_[0-9]+$")]
CandidateId = Annotated[str, Field(pattern=r"^candidate_[0-9]+$")]
ProposalId = Annotated[str, Field(pattern=r"^proposal_[0-9]+$")]
PredictionId = Annotated[str, Field(pattern=r"^prediction_[0-9]+$")]
EventId = Annotated[str, Field(pattern=r"^event_[0-9]+$")]
ConversationId = Annotated[str, Field(pattern=r"^conversation_[0-9]+$")]
MessageId = Annotated[str, Field(pattern=r"^msg_[0-9]+$")]
ScheduleId = Annotated[str, Field(pattern=r"^schedule_npc_[0-9]{2}$")]
WorldId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
