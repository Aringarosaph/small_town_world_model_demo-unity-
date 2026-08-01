"""Pydantic models for the complete V0 configuration catalog."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.enums import (
    AnimationSemantic,
    BehaviorCategory,
    BehaviorId,
    CapabilityTag,
    ConfigVersion,
    EffectTiming,
    EventType,
    EventWitnessScope,
    HardEffectOperation,
    JointActionAuthority,
    KnowledgeAcquisitionType,
    LocationType,
    MoodAxis,
    NeedName,
    ObjectType,
    PerceptionAuthority,
    PersonalityAxis,
    RelationshipAxis,
    RelationshipDirection,
    RelationshipRole,
    ReservationMode,
    RoutePlanningCapability,
    TargetKind,
)
from town_core.domain.identifiers import AgentId, HouseholdId, LocationId, ScheduleId, WorldId

UnitValue = Annotated[float, Field(ge=0.0, le=1.0)]
SignedUnitValue = Annotated[float, Field(ge=-1.0, le=1.0)]


class FrozenDecisions(ContractModel):
    unity_editor: Literal["6000.4.2f1"]
    relationship_prediction: Literal[RelationshipDirection.TARGET_TO_ACTOR]
    joint_action_authority: Literal[JointActionAuthority.CENTRAL_RESOLVER]
    perception_authority: Literal[PerceptionAuthority.HIGH_LEVEL_LOCATION]
    route_planning: Literal[RoutePlanningCapability.DISABLED]


class WorldConfig(ContractModel):
    config_version: Literal[ConfigVersion.V0]
    schema_version: Literal["v0.1"]
    protocol_version: Literal["0.1.0"]
    world_id: WorldId
    random_seed: NonNegativeInt
    initial_game_minute: NonNegativeInt
    fixed_counts: dict[Literal["npcs", "households", "locations", "behaviors", "object_types"], PositiveInt]
    frozen: FrozenDecisions


class NeedValues(ContractModel):
    hunger: UnitValue
    energy: UnitValue
    hygiene: UnitValue
    fun: UnitValue
    social: UnitValue


class PersonalityValues(ContractModel):
    sociability: UnitValue
    discipline: UnitValue
    frugality: UnitValue
    irritability: UnitValue


class MoodValues(ContractModel):
    valence: SignedUnitValue
    stress: UnitValue


class NpcConfig(ContractModel):
    agent_id: AgentId
    display_name_key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    life_stage: Literal["ADULT"]
    household_id: HouseholdId
    home_location_id: LocationId
    assigned_work_location_id: LocationId
    assigned_workstation_tag: CapabilityTag
    schedule_id: ScheduleId
    initial_needs: NeedValues
    personality: PersonalityValues
    initial_mood: MoodValues
    enabled: Literal[True]


class PopulationCatalog(ContractModel):
    npcs: Annotated[list[NpcConfig], Field(min_length=10, max_length=10)]
    relationship_initialization: RelationshipInitializationConfig


class RelationshipRange(ContractModel):
    minimum: UnitValue
    maximum: UnitValue

    @model_validator(mode="after")
    def validate_order(self) -> RelationshipRange:
        if self.minimum > self.maximum:
            raise ValueError("relationship initialization range is reversed")
        return self


class RelationshipRangeSet(ContractModel):
    familiarity: RelationshipRange
    affinity: RelationshipRange
    trust: RelationshipRange
    tension: RelationshipRange


class RelationshipInitializationConfig(ContractModel):
    generation_seed: NonNegativeInt
    role_priority: Annotated[list[RelationshipRole], Field(min_length=3, max_length=3)]
    same_household: RelationshipRangeSet
    coworker: RelationshipRangeSet
    other: RelationshipRangeSet

    @model_validator(mode="after")
    def validate_role_priority(self) -> RelationshipInitializationConfig:
        expected = [RelationshipRole.HOUSEHOLD_MEMBER, RelationshipRole.COWORKER, RelationshipRole.ACQUAINTANCE]
        if self.role_priority != expected:
            raise ValueError(f"role_priority must be ordered as {expected}")
        return self


class HouseholdConfig(ContractModel):
    household_id: HouseholdId
    member_ids: Annotated[list[AgentId], Field(min_length=1)]
    home_location_id: LocationId
    initial_money: NonNegativeInt
    initial_food_units: NonNegativeInt


class HouseholdCatalog(ContractModel):
    households: Annotated[list[HouseholdConfig], Field(min_length=4, max_length=4)]


class OpenInterval(ContractModel):
    start_minute_of_day: Annotated[int, Field(ge=0, lt=1440)]
    end_minute_of_day: Annotated[int, Field(gt=0, le=1440)]

    @model_validator(mode="after")
    def validate_interval(self) -> OpenInterval:
        if self.start_minute_of_day >= self.end_minute_of_day:
            raise ValueError("open interval must not cross midnight in V0")
        return self


class LocationConfig(ContractModel):
    location_id: LocationId
    location_type: LocationType
    display_name_key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    open_intervals: Annotated[list[OpenInterval], Field(min_length=1)]
    capacity: PositiveInt
    travel_minutes: dict[LocationId, PositiveInt]


class LocationCatalog(ContractModel):
    locations: Annotated[list[LocationConfig], Field(min_length=8, max_length=8)]


class ObjectTypeConfig(ContractModel):
    object_type: ObjectType
    capability_tags: Annotated[list[CapabilityTag], Field(min_length=1)]
    default_slot_count: PositiveInt
    persistent_occupancy: bool
    unity_binding_required: Literal[True]


class ObjectCatalog(ContractModel):
    object_types: Annotated[list[ObjectTypeConfig], Field(min_length=15, max_length=15)]


class DurationRange(ContractModel):
    base: PositiveInt
    variance: NonNegativeInt


class ObjectRequirement(ContractModel):
    capability: CapabilityTag
    accepted_object_types: Annotated[list[ObjectType], Field(min_length=1)]
    quantity: PositiveInt = 1
    reservation_mode: ReservationMode


class HardEffectSpec(ContractModel):
    operation: HardEffectOperation
    timing: EffectTiming
    amount: int | None = None
    economy_key: Annotated[str | None, Field(pattern=r"^[a-z][a-z0-9_]*$")] = None

    @model_validator(mode="after")
    def validate_value_source(self) -> HardEffectSpec:
        if self.amount is not None and self.economy_key is not None:
            raise ValueError("hard effect uses either amount or economy_key")
        return self


class SoftEffectMask(ContractModel):
    needs: list[NeedName]
    actor_mood: list[MoodAxis]
    target_mood: list[MoodAxis]
    relationship_target_to_actor: list[RelationshipAxis]
    acceptance: bool
    events: bool


class DeltaBounds(ContractModel):
    minimum: SignedUnitValue
    maximum: SignedUnitValue

    @model_validator(mode="after")
    def validate_order(self) -> DeltaBounds:
        if self.minimum > self.maximum:
            raise ValueError("delta bounds are reversed")
        return self


class BehaviorOutputBounds(ContractModel):
    need_deltas: dict[NeedName, DeltaBounds]
    actor_mood_deltas: dict[MoodAxis, DeltaBounds]
    target_mood_deltas: dict[MoodAxis, DeltaBounds]
    relationship_target_to_actor: dict[RelationshipAxis, DeltaBounds]


class UnityPresentation(ContractModel):
    animation_semantics: Annotated[list[AnimationSemantic], Field(min_length=1)]
    requires_facing: bool
    prop_semantic: str | None = None


class BehaviorConfig(ContractModel):
    behavior_id: BehaviorId
    category: BehaviorCategory
    actor_count: Literal[1]
    target_kind: TargetKind
    allowed_location_types: Annotated[list[LocationType], Field(min_length=1)]
    candidate_conditions: Annotated[list[str], Field(min_length=1)]
    object_requirements: list[ObjectRequirement]
    duration_minutes: DurationRange
    interruptible: bool
    hard_effects: list[HardEffectSpec]
    soft_effect_mask: SoftEffectMask
    output_bounds: BehaviorOutputBounds
    emitted_event_types: list[EventType]
    unity: UnityPresentation
    cooldown_minutes: NonNegativeInt


class BehaviorCatalog(ContractModel):
    behaviors: Annotated[list[BehaviorConfig], Field(min_length=22, max_length=22)]


class ScheduleEntry(ContractModel):
    entry_id: Annotated[str, Field(pattern=r"^npc_[0-9]{2}_work$")]
    kind: Literal["WORK"]
    weekdays: Annotated[list[Annotated[int, Field(ge=0, le=6)]], Field(min_length=1)]
    start_minute_of_day: Annotated[int, Field(ge=0, lt=1440)]
    end_minute_of_day: Annotated[int, Field(gt=0, le=1440)]
    location_id: LocationId
    required_behavior_id: Literal[BehaviorId.WORK_SHIFT]
    grace_minutes: NonNegativeInt
    priority: UnitValue

    @model_validator(mode="after")
    def validate_shift(self) -> ScheduleEntry:
        if self.start_minute_of_day >= self.end_minute_of_day:
            raise ValueError("V0 work shift must end on the same day")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must be unique")
        return self


class ScheduleConfig(ContractModel):
    schedule_id: ScheduleId
    entries: Annotated[list[ScheduleEntry], Field(min_length=1, max_length=1)]


class ScheduleCatalog(ContractModel):
    schedules: Annotated[list[ScheduleConfig], Field(min_length=10, max_length=10)]


class PurchaseConfig(ContractModel):
    price: PositiveInt
    food_units_delta: NonNegativeInt = 0


class EconomyConfig(ContractModel):
    currency: Literal["minor_units"]
    allow_negative_money: Literal[False]
    allow_negative_food: Literal[False]
    fixed_shift_wage: PositiveInt
    groceries: PurchaseConfig
    cafe_meal: PurchaseConfig
    bar_drink: PurchaseConfig
    food_low_threshold: NonNegativeInt
    money_low_threshold: NonNegativeInt


class UtilityWeights(ContractModel):
    needs: float
    mood: float
    schedule: float
    relationship: float
    known_events: float
    money_cost: float
    travel_cost: float
    interrupt_cost: float
    repetition_penalty: float
    idle_penalty: float


class UtilityConfig(ContractModel):
    max_candidates_per_agent: Literal[12]
    need_decay_per_game_hour: dict[NeedName, Annotated[float, Field(ge=-1.0, le=0.0)]]
    need_crisis_thresholds: dict[NeedName, UnitValue]
    weights: UtilityWeights
    personality_axes: Annotated[list[PersonalityAxis], Field(min_length=4, max_length=4)]
    deterministic_noise_amplitude: Annotated[float, Field(ge=0.0, le=0.1)]

    @model_validator(mode="after")
    def validate_personality_axes(self) -> UtilityConfig:
        expected = list(PersonalityAxis)
        if self.personality_axes != expected:
            raise ValueError(f"personality_axes must be ordered as {expected}")
        return self


class EventTypeConfig(ContractModel):
    event_type: EventType
    category: Literal["LIFE_ECONOMY", "WORK", "SOCIAL"]
    default_importance: UnitValue
    witness_scope: EventWitnessScope


class EventConfig(ContractModel):
    append_only: Literal[True]
    event_types: Annotated[list[EventTypeConfig], Field(min_length=23, max_length=23)]
    knowledge_acquisition_types: Annotated[list[KnowledgeAcquisitionType], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def validate_acquisition_types(self) -> EventConfig:
        if self.knowledge_acquisition_types != list(KnowledgeAcquisitionType):
            raise ValueError("knowledge_acquisition_types must contain the complete ordered V0 enum")
        return self


class ModelConfig(ContractModel):
    feature_version: Literal["v0.1"]
    default_outcome_model: Literal["heuristic"]
    neural_model_status: Literal["deferred_to_m4"]
    max_context_events: Literal[4]
    relationship_prediction: Literal[RelationshipDirection.TARGET_TO_ACTOR]
    relationship_axes: Annotated[list[RelationshipAxis], Field(min_length=4, max_length=4)]
    need_axes: Annotated[list[NeedName], Field(min_length=5, max_length=5)]
    mood_axes: Annotated[list[MoodAxis], Field(min_length=2, max_length=2)]
    acceptance_behaviors: list[BehaviorId]

    @model_validator(mode="after")
    def validate_axis_order(self) -> ModelConfig:
        if self.relationship_axes != list(RelationshipAxis):
            raise ValueError("relationship_axes must contain the complete ordered V0 enum")
        if self.need_axes != list(NeedName):
            raise ValueError("need_axes must contain the complete ordered V0 enum")
        if self.mood_axes != list(MoodAxis):
            raise ValueError("mood_axes must contain the complete ordered V0 enum")
        return self


class PromptTemplateConfig(ContractModel):
    prompt_id: Literal["parse_player_utterance", "verbalize_speech_plan"]
    prompt_version: Literal["v0.1"]
    template_file: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*\.md$")]
    model_name: Literal["deepseek-v4-flash"]
    temperature: Annotated[float, Field(ge=0.0, le=2.0)]
    max_tokens: PositiveInt
    schema_version: Literal["v0.1"]
    required_variables: list[str]


class PromptConfig(ContractModel):
    runtime_status: Literal["deferred_to_m5"]
    templates: Annotated[list[PromptTemplateConfig], Field(min_length=2, max_length=2)]


class CatalogBundle(ContractModel):
    world: WorldConfig
    population: PopulationCatalog
    households: HouseholdCatalog
    locations: LocationCatalog
    objects: ObjectCatalog
    behaviors: BehaviorCatalog
    schedules: ScheduleCatalog
    economy: EconomyConfig
    utility: UtilityConfig
    events: EventConfig
    model: ModelConfig
    prompts: PromptConfig
