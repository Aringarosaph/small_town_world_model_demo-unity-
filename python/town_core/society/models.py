"""SIM-owned M3 authority checkpoint records.

These records deliberately live outside ``town_core.domain`` and the wire
contract. ADR-0011 keeps the accepted public ``WorldState`` at v0.1 while the
society runtime persists the additional authority required to resume safely.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.decision_models import JointAction, OutcomePrediction
from town_core.domain.enums import BehaviorId, NeedName
from town_core.domain.identifiers import ActionId, AgentId, ConversationId, EventId, HouseholdId, LocationId, ObjectId
from town_core.domain.m3_models import M3CandidateAction
from town_core.domain.state_models import KnowledgeRecord, WorldEvent, WorldState

M3_CHECKPOINT_SCHEMA: Literal["stwm.simulation.m3-authority-checkpoint/v1"] = (
    "stwm.simulation.m3-authority-checkpoint/v1"
)
M3_TRANSACTION_SCHEMA: Literal["stwm.simulation.m3-authority-transaction/v1"] = (
    "stwm.simulation.m3-authority-transaction/v1"
)
M3_RUN_SCHEMA: Literal["stwm.simulation.m3-run/v1"] = "stwm.simulation.m3-run/v1"


class SocietyCandidate(ContractModel):
    """Existing v0.1 candidate plus ADR-0011 society context."""

    candidate: M3CandidateAction

    @property
    def selected_context_event_id(self) -> EventId | None:
        return self.candidate.selected_context_event_id

    @property
    def target_conversation_id(self) -> ConversationId | None:
        return self.candidate.target_conversation_id

    @property
    def invited_activity_id(self) -> BehaviorId | None:
        return self.candidate.invited_activity_id


class ScoredSocietyCandidate(ContractModel):
    candidate: SocietyCandidate
    prediction: OutcomePrediction
    utility_terms: dict[str, float]
    total_score: float
    tie_break: float


class WorkSessionRecord(ContractModel):
    session_id: str
    agent_id: AgentId
    day: NonNegativeInt
    start_game_minute: NonNegativeInt
    end_game_minute: NonNegativeInt
    grace_minutes: NonNegativeInt
    effective_work_minutes: NonNegativeInt = 0
    first_work_minute: NonNegativeInt | None = None
    started_event_emitted: bool = False
    late_event_emitted: bool = False
    finalized: bool = False
    paid: bool = False
    proposal_ids: list[str] = Field(default_factory=list)
    action_ids: list[ActionId] = Field(default_factory=list)
    completed_break_action_ids: list[ActionId] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completed_break(self) -> WorkSessionRecord:
        if len(self.completed_break_action_ids) > 1:
            raise ValueError("work occurrence permits at most one completed break")
        if set(self.completed_break_action_ids) & set(self.action_ids):
            raise ValueError("break action cannot be recorded as effective work")
        return self


ReservationKind = Literal["OBJECT_SLOT", "HOUSEHOLD_RESOURCE", "LOCATION", "PARTICIPANT"]


class ReservationRecord(ContractModel):
    reservation_id: str
    owner_action_id: ActionId
    kind: ReservationKind
    object_id: ObjectId | None = None
    slot_index: NonNegativeInt | None = None
    household_id: HouseholdId | None = None
    money_units: NonNegativeInt = 0
    food_units: NonNegativeInt = 0
    location_id: LocationId | None = None
    participant_agent_id: AgentId | None = None
    valid_from_game_minute: NonNegativeInt
    expires_at_game_minute: NonNegativeInt

    @model_validator(mode="after")
    def validate_kind_fields(self) -> ReservationRecord:
        populated = {
            "OBJECT_SLOT": (
                self.object_id is not None and self.slot_index is not None and self.participant_agent_id is not None
            ),
            "HOUSEHOLD_RESOURCE": self.household_id is not None and (self.money_units > 0 or self.food_units > 0),
            "LOCATION": self.location_id is not None and self.participant_agent_id is not None,
            "PARTICIPANT": self.participant_agent_id is not None,
        }
        if not populated[self.kind]:
            raise ValueError(f"reservation fields do not match kind {self.kind}")
        return self


class DialogueLineRecord(ContractModel):
    line_id: str
    game_minute: NonNegativeInt
    speaker_agent_id: AgentId
    listener_ids: Annotated[list[AgentId], Field(min_length=1)]
    template_id: str
    text: Annotated[str, Field(min_length=1, max_length=1000)]
    referenced_event_ids: list[EventId] = Field(default_factory=list)


class ConversationRecord(ContractModel):
    conversation_id: ConversationId
    participant_ids: Annotated[list[AgentId], Field(min_length=2, max_length=10)]
    started_at_game_minute: NonNegativeInt
    last_activity_game_minute: NonNegativeInt
    active: bool = True
    source_action_ids: list[ActionId] = Field(default_factory=list)
    lines: list[DialogueLineRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_participants(self) -> ConversationRecord:
        if self.participant_ids != sorted(set(self.participant_ids)):
            raise ValueError("conversation participants must be unique and sorted")
        return self


class JointActionRecord(ContractModel):
    joint_action: JointAction
    source_invite_action_id: ActionId
    arrived_agent_ids: list[AgentId] = Field(default_factory=list)
    status: Literal["RESERVED", "TRAVELING", "PERFORMING"] = "RESERVED"


class ActionRuntimeRecord(ContractModel):
    action_id: ActionId
    actor_id: AgentId
    proposal_id: str
    candidate: SocietyCandidate
    prediction: OutcomePrediction
    participant_ids: Annotated[list[AgentId], Field(min_length=1, max_length=10)]
    reservation_ids: list[str]
    origin_location_ids: dict[AgentId, LocationId]
    travel_arrival_minutes: dict[AgentId, NonNegativeInt]
    arrived_agent_ids: list[AgentId] = Field(default_factory=list)
    perform_start_minute: NonNegativeInt
    work_session_id: str | None = None
    joint: bool = False


class SocietyCounters(ContractModel):
    candidate: NonNegativeInt = 0
    prediction: NonNegativeInt = 0
    proposal: NonNegativeInt = 0
    decision: NonNegativeInt = 0
    action: NonNegativeInt = 0
    conversation: NonNegativeInt = 0
    reservation: NonNegativeInt = 0
    transaction: NonNegativeInt = 0
    dialogue_line: NonNegativeInt = 0


class AuthorityCheckpoint(ContractModel):
    schema_id: Literal["stwm.simulation.m3-authority-checkpoint/v1"] = Field(
        default=M3_CHECKPOINT_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    m3_catalog_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    world: WorldState
    events: list[WorldEvent] = Field(default_factory=list)
    knowledge_records: dict[str, KnowledgeRecord] = Field(default_factory=dict)
    work_sessions: dict[str, WorkSessionRecord] = Field(default_factory=dict)
    reservations: dict[str, ReservationRecord] = Field(default_factory=dict)
    conversations: dict[ConversationId, ConversationRecord] = Field(default_factory=dict)
    joint_actions: dict[ActionId, JointActionRecord] = Field(default_factory=dict)
    action_runtimes: dict[ActionId, ActionRuntimeRecord] = Field(default_factory=dict)
    recent_behaviors: dict[AgentId, BehaviorId | None] = Field(default_factory=dict)
    active_need_crises: dict[AgentId, list[NeedName]] = Field(default_factory=dict)
    low_resource_flags: dict[HouseholdId, list[Literal["FOOD", "MONEY"]]] = Field(default_factory=dict)
    settlement_keys: list[str] = Field(default_factory=list)
    counters: SocietyCounters = Field(default_factory=SocietyCounters)
    authority_record_count: NonNegativeInt = 0
    authority_log_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    transaction_chain_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class SocietyAdvanceResult(ContractModel):
    previous_game_minute: NonNegativeInt
    target_game_minute: NonNegativeInt
    transactions: list[dict[str, object]] = Field(default_factory=list)
    decisions: list[dict[str, object]] = Field(default_factory=list)
    actions: list[dict[str, object]] = Field(default_factory=list)
    events: list[WorldEvent] = Field(default_factory=list)
    dialogues: list[DialogueLineRecord] = Field(default_factory=list)
    authority_records: list[dict[str, object]] = Field(default_factory=list)
    authority_record_count: NonNegativeInt
    authority_log_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
