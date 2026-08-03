"""Versioned private contracts for the M4 distilled outcome model."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import MoodValues, NeedValues, PersonalityValues, UnitValue
from town_core.domain.decision_models import HardCostPreview, OutcomePrediction
from town_core.domain.enums import BehaviorId, EventType, LocationType, RelationshipRole
from town_core.domain.identifiers import AgentId, CandidateId, EventId, LocationId, ObjectId

PROJECT_NAME = "Small Town World Model（STWM）"
FEATURE_SCHEMA = "stwm.model.candidate-feature-row/v1"
LABEL_SCHEMA = "stwm.model.outcome-label/v1"
TRAINING_EXAMPLE_SCHEMA = "stwm.model.training-example/v1"
ANCHOR_SCHEMA = "stwm.model.social-anchor/v1"
DATASET_SCHEMA = "stwm.model.dataset-manifest/v1"
PACKAGE_SCHEMA = "stwm.model.outcome-package/v1"
EVALUATION_SCHEMA = "stwm.model.evaluation-report/v1"
FEATURE_VERSION = "v0.1"
LABEL_VERSION = "v0.1"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
COMMIT_PATTERN = r"^[a-f0-9]{40}$"

DatasetSplit = Literal["train", "validation", "test"]


class RawActorFeatures(ContractModel):
    needs: NeedValues
    mood: MoodValues
    personality: PersonalityValues
    household_money: NonNegativeInt
    household_food_units: NonNegativeInt
    current_location_id: LocationId
    home_location_id: LocationId
    assigned_work_location_id: LocationId
    local_population: NonNegativeInt
    known_event_count: NonNegativeInt
    decision_overdue_minutes: NonNegativeInt


class RawCandidateFeatures(ContractModel):
    behavior_id: BehaviorId
    destination_location_id: LocationId | None
    destination_location_type: LocationType | None
    target_object_ids: list[ObjectId]
    object_type_values: list[str]
    capability_values: list[str]
    estimated_travel_minutes: NonNegativeInt
    estimated_duration_minutes: NonNegativeInt
    schedule_conflict_minutes: NonNegativeInt
    hard_cost_preview: HardCostPreview
    repeats_previous_behavior: bool
    crosses_location: bool
    joint_action_candidate: bool


class RawTargetFeatures(ContractModel):
    agent_id: AgentId
    needs: NeedValues
    mood: MoodValues
    relationship_roles_target_to_actor: list[RelationshipRole]
    relationship_familiarity: UnitValue
    relationship_affinity: UnitValue
    relationship_trust: UnitValue
    relationship_tension: UnitValue
    minutes_since_interaction: NonNegativeInt | None
    same_household: bool
    coworker: bool
    active_conversation: bool
    knows_selected_event: bool


class RawEventFeatures(ContractModel):
    event_id: EventId
    event_type: EventType
    importance: UnitValue
    age_minutes: NonNegativeInt
    actor_is_participant: bool
    target_is_participant: bool
    same_location: bool


class NumericFeatures(ContractModel):
    actor_needs: NeedValues
    actor_mood: MoodValues
    actor_personality: PersonalityValues
    household_money_ratio: Annotated[float, Field(ge=0.0, le=20.0)]
    household_food_ratio: Annotated[float, Field(ge=0.0, le=20.0)]
    minute_of_day_sin: Annotated[float, Field(ge=-1.0, le=1.0)]
    minute_of_day_cos: Annotated[float, Field(ge=-1.0, le=1.0)]
    weekday_sin: Annotated[float, Field(ge=-1.0, le=1.0)]
    weekday_cos: Annotated[float, Field(ge=-1.0, le=1.0)]
    local_population_ratio: UnitValue
    known_event_count_ratio: UnitValue
    decision_overdue_ratio: UnitValue
    travel_ratio: UnitValue
    duration_ratio: UnitValue
    schedule_conflict_ratio: UnitValue
    money_cost_ratio: UnitValue
    food_cost_ratio: UnitValue
    target_needs: NeedValues | None
    target_mood: MoodValues | None
    target_relationship: Annotated[list[UnitValue], Field(min_length=4, max_length=4)] | None
    target_interaction_age_ratio: UnitValue | None
    event_importance: Annotated[list[UnitValue], Field(min_length=4, max_length=4)]
    event_age_ratio: Annotated[list[UnitValue], Field(min_length=4, max_length=4)]


class CategoricalFeatures(ContractModel):
    behavior_index: NonNegativeInt
    actor_current_location_index: NonNegativeInt
    actor_home_location_index: NonNegativeInt
    actor_work_location_index: NonNegativeInt
    destination_location_type_index: int
    object_type_indices: list[NonNegativeInt]
    capability_indices: list[NonNegativeInt]
    relationship_role_indices: list[NonNegativeInt]
    event_type_indices: Annotated[list[int], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def validate_sentinels(self) -> CategoricalFeatures:
        if self.destination_location_type_index < -1:
            raise ValueError("destination location type index may only use -1 as the missing sentinel")
        if any(value < -1 for value in self.event_type_indices):
            raise ValueError("event type indices may only use -1 as the missing sentinel")
        return self


class FeatureMasks(ContractModel):
    target_present: bool
    relationship_present: bool
    acceptance_present: bool
    target_mood_present: bool
    relationship_delta_present: bool
    event_mask: Annotated[list[bool], Field(min_length=4, max_length=4)]


class CandidateFeatureRow(ContractModel):
    schema_id: Literal["stwm.model.candidate-feature-row/v1"] = Field(
        default="stwm.model.candidate-feature-row/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    feature_version: Literal["v0.1"] = "v0.1"
    row_id: Annotated[str, Field(pattern=r"^row_[a-f0-9]{24}$")]
    source_commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    seed: NonNegativeInt
    episode_id: Annotated[str, Field(min_length=1)]
    scenario_group_id: Annotated[str, Field(min_length=1)]
    split: DatasetSplit
    decision_group_id: Annotated[str, Field(min_length=1)]
    decision_id: Annotated[str, Field(min_length=1)]
    candidate_id: CandidateId
    actor_id: AgentId
    source_state_version: NonNegativeInt
    game_minute: NonNegativeInt
    candidate_rank: NonNegativeInt
    raw_actor: RawActorFeatures
    raw_candidate: RawCandidateFeatures
    raw_target: RawTargetFeatures | None
    raw_events: Annotated[list[RawEventFeatures], Field(max_length=4)]
    numeric: NumericFeatures
    categorical: CategoricalFeatures
    masks: FeatureMasks


class OutcomeLabel(ContractModel):
    schema_id: Literal["stwm.model.outcome-label/v1"] = Field(
        default="stwm.model.outcome-label/v1", alias="schema", serialization_alias="schema"
    )
    label_version: Literal["v0.1"] = "v0.1"
    row_id: Annotated[str, Field(pattern=r"^row_[a-f0-9]{24}$")]
    teacher_provider_id: Literal["stwm.heuristic.m3/v1"] = "stwm.heuristic.m3/v1"
    prediction: OutcomePrediction
    utility_terms: dict[str, float]
    total_score: float
    tie_break: float
    selected_by_teacher: bool
    resolver_attempted: bool
    resolver_result: str | None


class TrainingExample(ContractModel):
    schema_id: Literal["stwm.model.training-example/v1"] = Field(
        default="stwm.model.training-example/v1", alias="schema", serialization_alias="schema"
    )
    feature: CandidateFeatureRow
    label: OutcomeLabel

    @model_validator(mode="after")
    def validate_identity(self) -> TrainingExample:
        if self.feature.row_id != self.label.row_id:
            raise ValueError("feature and label row IDs must match")
        if self.feature.candidate_id != self.label.prediction.candidate_id:
            raise ValueError("feature candidate and teacher prediction must match")
        return self


class SocialAnchorReview(ContractModel):
    reviewer_id: Annotated[str, Field(min_length=1)]
    reviewed_at_utc: Annotated[str, Field(min_length=1)]
    decision: Literal["APPROVED", "REJECTED", "DISPUTED"]
    issue_codes: list[str]
    notes: str = ""


class SocialAnchor(ContractModel):
    schema_id: Literal["stwm.model.social-anchor/v1"] = Field(
        default="stwm.model.social-anchor/v1", alias="schema", serialization_alias="schema"
    )
    anchor_id: Annotated[str, Field(pattern=r"^anchor_[a-z0-9_]+$")]
    family_id: Annotated[str, Field(min_length=1)]
    behavior_id: BehaviorId
    producer_id: Annotated[str, Field(min_length=1)]
    producer_recorded_at_utc: Annotated[str, Field(min_length=1)]
    feature: CandidateFeatureRow
    expected_label: OutcomeLabel
    assertions: Annotated[list[str], Field(min_length=1)]
    review: SocialAnchorReview | None = None


class ArtifactDescriptor(ContractModel):
    relative_path: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    bytes: NonNegativeInt


class DatasetShard(ArtifactDescriptor):
    shard_id: Annotated[str, Field(pattern=r"^shard_[0-9]{5}$")]
    row_count: PositiveInt
    decision_group_count: PositiveInt
    split_counts: dict[DatasetSplit, NonNegativeInt]


class DatasetManifest(ContractModel):
    schema_id: Literal["stwm.model.dataset-manifest/v1"] = Field(
        default="stwm.model.dataset-manifest/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    dataset_id: Annotated[str, Field(min_length=1)]
    status: Literal["IN_PROGRESS", "COMPLETED", "FAILED"]
    source_commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    feature_version: Literal["v0.1"] = "v0.1"
    label_version: Literal["v0.1"] = "v0.1"
    config_hash: Annotated[str, Field(pattern=SHA256_PATTERN)]
    m3_catalog_hash: Annotated[str, Field(pattern=SHA256_PATTERN)]
    generator_version: Literal["v1"] = "v1"
    parquet_encoding: Literal["canonical_training_example_json/v1"] = "canonical_training_example_json/v1"
    seeds: Annotated[list[NonNegativeInt], Field(min_length=1)]
    max_rows_per_shard: Annotated[int, Field(gt=0, le=25_000)]
    decision_group_count: NonNegativeInt
    row_count: NonNegativeInt
    split_counts: dict[DatasetSplit, NonNegativeInt]
    behavior_counts: dict[BehaviorId, NonNegativeInt]
    shards: list[DatasetShard]
    vocabulary: dict[str, list[str]]
    started_at_utc: Annotated[str, Field(min_length=1)]
    completed_at_utc: str | None = None
    failure: str | None = None


class OutcomePackage(ContractModel):
    schema_id: Literal["stwm.model.outcome-package/v1"] = Field(
        default="stwm.model.outcome-package/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    model_version: Annotated[str, Field(min_length=1)]
    source_commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    feature_version: Literal["v0.1"] = "v0.1"
    label_version: Literal["v0.1"] = "v0.1"
    python_version: Annotated[str, Field(min_length=1)]
    pytorch_version: Annotated[str, Field(min_length=1)]
    architecture: dict[str, object]
    vocabulary: dict[str, list[str]]
    normalization: dict[str, float]
    config_hash: Annotated[str, Field(pattern=SHA256_PATTERN)]
    dataset_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    checkpoint: ArtifactDescriptor
    evaluation: ArtifactDescriptor


class EvaluationMetric(ContractModel):
    name: Annotated[str, Field(min_length=1)]
    value: float
    threshold: float | None = None
    passed: bool | None = None


class EvaluationReport(ContractModel):
    schema_id: Literal["stwm.model.evaluation-report/v1"] = Field(
        default="stwm.model.evaluation-report/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    model_version: Annotated[str, Field(min_length=1)]
    source_commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    dataset_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    metrics: Annotated[list[EvaluationMetric], Field(min_length=1)]
    passed: bool
