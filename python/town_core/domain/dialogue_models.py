"""M5-facing language schemas frozen early; no LLM runtime is implemented."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import SignedUnitValue, UnitValue
from town_core.domain.enums import BehaviorId, SpeechAct
from town_core.domain.identifiers import AgentId, ConversationId, EventId


class SpeechTone(ContractModel):
    warmth: UnitValue
    hostility: UnitValue
    urgency: UnitValue


class PlayerSpeechParse(ContractModel):
    speech_act: SpeechAct
    target_agent_id: AgentId
    referenced_agent_ids: list[AgentId]
    referenced_event_ids: list[EventId]
    invite_activity: BehaviorId | None
    tone: SpeechTone
    claims: Annotated[list[str], Field(max_length=0)]
    confidence: UnitValue
    requires_clarification: bool

    @model_validator(mode="after")
    def validate_invite_activity(self) -> PlayerSpeechParse:
        allowed = {
            BehaviorId.WATCH_TV,
            BehaviorId.EAT_AT_CAFE,
            BehaviorId.DRINK_AT_BAR,
            BehaviorId.WALK_IN_PARK,
            BehaviorId.SIT_IN_PARK,
        }
        if self.invite_activity is not None and self.invite_activity not in allowed:
            raise ValueError("invite_activity must use the V0 joint-activity allowlist")
        return self


class SpeechStance(ContractModel):
    certainty: UnitValue
    approval: SignedUnitValue


class SpeechStyle(ContractModel):
    directness: UnitValue
    warmth: UnitValue
    verbosity: UnitValue


class SpeechPlan(ContractModel):
    speech_plan_id: Annotated[str, Field(pattern=r"^speech_plan_[0-9]+$")]
    conversation_id: ConversationId
    speaker_agent_id: AgentId
    listener_ids: Annotated[list[str], Field(min_length=1)]
    speech_act: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]
    communicative_goal: str
    allowed_event_ids: list[EventId]
    allowed_agent_ids: list[AgentId]
    fact_payload: dict[str, str | int | float | bool | None]
    stance: SpeechStance
    emotion_valence: SignedUnitValue
    emotion_stress: UnitValue
    style: SpeechStyle
    forbidden_topics: list[str]
    state_version: Annotated[int, Field(ge=0)]
