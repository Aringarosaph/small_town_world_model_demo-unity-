"""Persistable V0 state DTOs; no state transition behavior lives here."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import MoodValues, NeedValues, PersonalityValues, SignedUnitValue, UnitValue
from town_core.domain.enums import (
    ActionPhase,
    BehaviorId,
    CapabilityTag,
    EventType,
    EventWitnessScope,
    KnowledgeAcquisitionType,
    LocationType,
    ObjectType,
    RelationshipRole,
)
from town_core.domain.identifiers import (
    ActionId,
    AgentId,
    ConversationId,
    EventId,
    HouseholdId,
    LocationId,
    ObjectId,
    ScheduleId,
    WorldId,
)


class AgentState(ContractModel):
    agent_id: AgentId
    household_id: HouseholdId
    display_name_key: str
    home_location_id: LocationId
    current_location_id: LocationId | Literal["TRAVELING"]
    assigned_work_location_id: LocationId
    assigned_workstation_tag: CapabilityTag
    current_action_id: ActionId | None
    needs: NeedValues
    personality: PersonalityValues
    mood: MoodValues
    schedule_id: ScheduleId
    known_event_ids: list[EventId]
    social_cooldowns: dict[str, NonNegativeInt]
    decision_due_at: NonNegativeInt
    enabled: bool


class HouseholdState(ContractModel):
    household_id: HouseholdId
    member_ids: Annotated[list[AgentId], Field(min_length=1)]
    home_location_id: LocationId
    money: NonNegativeInt
    food_units: NonNegativeInt


class RelationshipState(ContractModel):
    source_agent_id: AgentId
    target_agent_id: AgentId
    roles: list[RelationshipRole]
    familiarity: UnitValue
    affinity: UnitValue
    trust: UnitValue
    tension: UnitValue
    last_interaction_minute: NonNegativeInt | None

    @model_validator(mode="after")
    def validate_direction(self) -> RelationshipState:
        if self.source_agent_id == self.target_agent_id:
            raise ValueError("relationship endpoints must be distinct")
        return self


class LocationState(ContractModel):
    location_id: LocationId
    location_type: LocationType
    current_agent_ids: list[AgentId]
    object_ids: list[ObjectId]


class InteractionObjectState(ContractModel):
    object_id: ObjectId
    object_type: ObjectType
    location_id: LocationId
    capability_tags: Annotated[list[CapabilityTag], Field(min_length=1)]
    slot_count: Annotated[int, Field(gt=0)]
    occupied_slots: dict[Annotated[int, Field(ge=0)], ActionId]
    enabled: bool
    unity_binding_required: bool
    metadata: dict[str, str]


class ActionState(ContractModel):
    action_id: ActionId
    behavior_id: BehaviorId
    agent_ids: Annotated[list[AgentId], Field(min_length=1)]
    phase: ActionPhase
    destination_location_id: LocationId | None
    target_object_ids: list[ObjectId]
    started_at_game_minute: NonNegativeInt
    planned_end_game_minute: NonNegativeInt | None


EventPayloadValue = str | int | float | bool | None


class WorldEvent(ContractModel):
    event_id: EventId
    event_type: EventType
    game_minute: NonNegativeInt
    location_id: LocationId
    actor_ids: Annotated[list[AgentId], Field(min_length=1)]
    affected_agent_ids: list[AgentId]
    witness_agent_ids: list[AgentId]
    source_action_id: ActionId | None
    importance: UnitValue
    witness_scope: EventWitnessScope
    payload: dict[str, EventPayloadValue]
    supersedes_event_id: EventId | None = None


class KnowledgeRecord(ContractModel):
    agent_id: AgentId
    event_id: EventId
    source_agent_id: AgentId | None
    acquisition_type: KnowledgeAcquisitionType
    confidence: UnitValue
    first_known_minute: NonNegativeInt
    last_reinforced_minute: NonNegativeInt


class WorldState(ContractModel):
    schema_version: Literal["v0.1"]
    world_id: WorldId
    game_minute: NonNegativeInt
    random_seed: NonNegativeInt
    state_version: NonNegativeInt
    agents: dict[AgentId, AgentState]
    households: dict[HouseholdId, HouseholdState]
    locations: dict[LocationId, LocationState]
    objects: dict[ObjectId, InteractionObjectState]
    relationships: list[RelationshipState]
    active_actions: dict[ActionId, ActionState]
    dialogue_session_ids: list[ConversationId]
    event_cursor: NonNegativeInt
    model_version: str | None
    config_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class RelationshipDelta(ContractModel):
    familiarity: SignedUnitValue
    affinity: SignedUnitValue
    trust: SignedUnitValue
    tension: SignedUnitValue


class MoodDelta(ContractModel):
    valence: SignedUnitValue
    stress: SignedUnitValue


class NeedDelta(ContractModel):
    hunger: SignedUnitValue
    energy: SignedUnitValue
    hygiene: SignedUnitValue
    fun: SignedUnitValue
    social: SignedUnitValue
