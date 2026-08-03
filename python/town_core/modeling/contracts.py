"""Versioned private contracts for the M4 distilled outcome model."""

from __future__ import annotations

from itertools import combinations
from typing import Annotated, Literal, cast

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
ANCHOR_TASK_SCHEMA = "stwm.model.social-anchor-task/v1"
ANCHOR_JUDGMENT_SCHEMA = "stwm.model.social-anchor-judgment/v1"
ANCHOR_REVIEW_ISSUE_SCHEMA = "stwm.model.social-anchor-review-issue/v1"
ANCHOR_APPROVAL_SCHEMA = "stwm.model.social-anchor-approval-manifest/v1"
ANCHOR_COVERAGE_POLICY_SCHEMA = "stwm.model.social-anchor-coverage-policy/v1"
ANCHOR_TRAINING_INPUT_SCHEMA = "stwm.model.social-anchor-training-input-manifest/v1"
DATASET_SCHEMA = "stwm.model.dataset-manifest/v1"
PACKAGE_SCHEMA = "stwm.model.outcome-package/v1"
EVALUATION_SCHEMA = "stwm.model.evaluation-report/v1"
FEATURE_VERSION = "v0.1"
LABEL_VERSION = "v0.1"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
COMMIT_PATTERN = r"^[a-f0-9]{40}$"

DatasetSplit = Literal["train", "validation", "test"]
AnchorPartition = Literal["TRAIN", "VALIDATION", "ANCHOR_HOLDOUT"]
AnchorReviewDecision = Literal["APPROVED", "REJECTED", "DISPUTED"]
ReviewedAnchorOutputPath = Literal[
    "acceptance_probability",
    "actor_mood_delta.valence",
    "actor_mood_delta.stress",
    "target_mood_delta.valence",
    "target_mood_delta.stress",
    "relationship_delta_target_to_actor.familiarity",
    "relationship_delta_target_to_actor.affinity",
    "relationship_delta_target_to_actor.trust",
    "relationship_delta_target_to_actor.tension",
]
HeuristicPassthroughOutputPath = Literal[
    "need_delta_preview.hunger",
    "need_delta_preview.energy",
    "need_delta_preview.hygiene",
    "need_delta_preview.fun",
    "need_delta_preview.social",
    "event_probabilities",
]

REVIEWED_SOCIAL_BEHAVIORS = frozenset(
    {
        BehaviorId.GREET,
        BehaviorId.CHAT,
        BehaviorId.JOKE,
        BehaviorId.COMPLIMENT,
        BehaviorId.INVITE_JOIN,
        BehaviorId.APOLOGIZE,
        BehaviorId.CONFRONT,
    }
)


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


class SocialAnchorCoverageSignature(ContractModel):
    relationship_direction: Literal["TARGET_TO_ACTOR"] = "TARGET_TO_ACTOR"
    familiarity_bin: Literal["LOW", "MIDDLE", "HIGH"]
    affinity_bin: Literal["LOW", "MIDDLE", "HIGH"]
    trust_bin: Literal["LOW", "MIDDLE", "HIGH"]
    tension_bin: Literal["LOW", "MIDDLE", "HIGH"]
    target_stress_bin: Literal["LOW", "HIGH"]
    actor_sociability_bin: Literal["LOW", "HIGH", "GAP"]
    actor_irritability_bin: Literal["LOW", "HIGH", "GAP"]
    privacy_bin: Literal["PRIVATE_HOME", "PUBLIC"]
    event_context_bin: Literal["NONE", "LIGHT", "HEAVY"]
    social_identity_bin: Literal["SAME_HOUSEHOLD", "COWORKER", "ACQUAINTANCE"]


class SocialAnchorTask(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-task/v1"] = Field(
        default="stwm.model.social-anchor-task/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    anchor_id: Annotated[str, Field(pattern=r"^anchor_[a-f0-9]{24}$")]
    family_id: Annotated[str, Field(pattern=r"^anchor_family_[a-f0-9]{24}$")]
    batch_id: Annotated[str, Field(pattern=r"^social_[a-z0-9_]+_v1$")]
    behavior_id: BehaviorId
    partition: AnchorPartition
    source_dataset_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    source_shard_relative_path: Annotated[str, Field(min_length=1)]
    source_shard_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    source_example_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    actor_target_pair_key: Annotated[str, Field(min_length=1)]
    coverage_signature: SocialAnchorCoverageSignature
    feature: CandidateFeatureRow
    heuristic_baseline: OutcomeLabel

    @model_validator(mode="after")
    def validate_task_identity(self) -> SocialAnchorTask:
        if self.behavior_id not in REVIEWED_SOCIAL_BEHAVIORS:
            raise ValueError("anchor task behavior is outside the reviewed social allowlist")
        if self.feature.raw_candidate.behavior_id is not self.behavior_id:
            raise ValueError("anchor task behavior must match its immutable feature")
        if self.feature.row_id != self.heuristic_baseline.row_id:
            raise ValueError("anchor task feature and baseline row IDs must match")
        if self.feature.candidate_id != self.heuristic_baseline.prediction.candidate_id:
            raise ValueError("anchor task feature and baseline candidate IDs must match")
        expected_partition = cast(
            AnchorPartition,
            {"train": "TRAIN", "validation": "VALIDATION", "test": "ANCHOR_HOLDOUT"}[self.feature.split],
        )
        if self.partition != expected_partition:
            raise ValueError("anchor partition must preserve the immutable raw dataset split")
        if self.feature.raw_target is None or not self.feature.masks.acceptance_present:
            raise ValueError("reviewed social anchor tasks require a target and acceptance head")
        if self.batch_id != f"social_{self.behavior_id.value}_v1":
            raise ValueError("anchor batch ID must be behavior-local")
        return self


class SocialAnchorTypedAssertion(ContractModel):
    assertion_id: Annotated[str, Field(pattern=r"^assertion_[a-f0-9]{16}$")]
    assertion_type: Literal[
        "ACCEPTANCE_RATIONALE",
        "DELTA_RATIONALE",
        "DIRECTION",
        "EVENT_RATIONALE",
        "PERSONALITY_MONOTONICITY",
    ]
    statement: Annotated[str, Field(min_length=1)]
    paired_task_id: Annotated[str | None, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")] = None
    paired_task_sha256: Annotated[str | None, Field(pattern=SHA256_PATTERN)] = None
    expected_order: Literal["LOWER", "EQUAL", "HIGHER"] | None = None

    @model_validator(mode="after")
    def validate_pair(self) -> SocialAnchorTypedAssertion:
        paired = (
            self.paired_task_id is not None or self.paired_task_sha256 is not None or self.expected_order is not None
        )
        if self.assertion_type == "PERSONALITY_MONOTONICITY":
            if not paired or None in (self.paired_task_id, self.paired_task_sha256, self.expected_order):
                raise ValueError("personality monotonicity assertions require a complete explicit pair")
        elif paired:
            raise ValueError("only personality monotonicity assertions may reference a paired task")
        return self


class SocialAnchorJudgment(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-judgment/v1"] = Field(
        default="stwm.model.social-anchor-judgment/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    judgment_id: Annotated[str, Field(pattern=r"^anchor_judgment_[a-f0-9]{24}$")]
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    task_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    anchor_id: Annotated[str, Field(pattern=r"^anchor_[a-f0-9]{24}$")]
    family_id: Annotated[str, Field(pattern=r"^anchor_family_[a-f0-9]{24}$")]
    batch_id: Annotated[str, Field(pattern=r"^social_[a-z0-9_]+_v1$")]
    behavior_id: BehaviorId
    partition: AnchorPartition
    candidate_id: CandidateId
    producer_id: Annotated[str, Field(min_length=1)]
    produced_at_utc: Annotated[str, Field(min_length=1)]
    provider_id: Literal["stwm.codex.anchor-producer/v1"] = "stwm.codex.anchor-producer/v1"
    revision_of_judgment_sha256: Annotated[str | None, Field(pattern=SHA256_PATTERN)] = None
    proposed_prediction: OutcomePrediction
    reviewed_output_paths: Annotated[list[ReviewedAnchorOutputPath], Field(min_length=1)]
    heuristic_passthrough_output_paths: Annotated[list[HeuristicPassthroughOutputPath], Field(min_length=1)]
    rationale_tags: Annotated[list[str], Field(min_length=1)]
    typed_assertions: Annotated[list[SocialAnchorTypedAssertion], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_judgment_identity(self) -> SocialAnchorJudgment:
        if self.behavior_id not in REVIEWED_SOCIAL_BEHAVIORS:
            raise ValueError("anchor judgment behavior is outside the reviewed social allowlist")
        if self.proposed_prediction.candidate_id != self.candidate_id:
            raise ValueError("anchor judgment candidate and proposed prediction must match")
        if self.batch_id != f"social_{self.behavior_id.value}_v1":
            raise ValueError("anchor judgment batch ID must be behavior-local")
        if len(self.reviewed_output_paths) != len(set(self.reviewed_output_paths)):
            raise ValueError("anchor reviewed output paths must be unique")
        if len(self.heuristic_passthrough_output_paths) != len(set(self.heuristic_passthrough_output_paths)):
            raise ValueError("anchor heuristic passthrough paths must be unique")
        if len(self.rationale_tags) != len(set(self.rationale_tags)):
            raise ValueError("anchor judgment rationale tags must be unique")
        return self


class SocialAnchorReviewIssue(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-review-issue/v1"] = Field(
        default="stwm.model.social-anchor-review-issue/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    issue_id: Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    task_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    judgment_id: Annotated[str, Field(pattern=r"^anchor_judgment_[a-f0-9]{24}$")]
    judgment_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    reviewer_id: Annotated[str, Field(min_length=1)]
    reviewed_at_utc: Annotated[str, Field(min_length=1)]
    severity: Literal["ADVISORY", "BLOCKING", "DISPUTED"]
    issue_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]
    message: Annotated[str, Field(min_length=1)]
    related_anchor_ids: list[Annotated[str, Field(pattern=r"^anchor_[a-f0-9]{24}$")]] = Field(default_factory=list)


class SocialAnchorApprovalEntry(ContractModel):
    anchor_id: Annotated[str, Field(pattern=r"^anchor_[a-f0-9]{24}$")]
    task_id: Annotated[str, Field(pattern=r"^anchor_task_[a-f0-9]{24}$")]
    task_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    judgment_id: Annotated[str, Field(pattern=r"^anchor_judgment_[a-f0-9]{24}$")]
    judgment_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    behavior_id: BehaviorId
    partition: AnchorPartition
    decision: AnchorReviewDecision
    issue_ids: list[Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]]
    blocking_issue_ids: list[Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]]
    disputed_issue_ids: list[Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]]
    advisory_issue_ids: list[Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]]
    acknowledged_advisory_issue_ids: list[Annotated[str, Field(pattern=r"^anchor_issue_[a-f0-9]{24}$")]]

    @model_validator(mode="after")
    def validate_approval(self) -> SocialAnchorApprovalEntry:
        if self.behavior_id not in REVIEWED_SOCIAL_BEHAVIORS:
            raise ValueError("anchor approval behavior is outside the reviewed social allowlist")
        classified = (
            set(self.blocking_issue_ids),
            set(self.disputed_issue_ids),
            set(self.advisory_issue_ids),
        )
        if any(left & right for left, right in combinations(classified, 2)):
            raise ValueError("anchor approval issue severity sets must be disjoint")
        if set().union(*classified) != set(self.issue_ids):
            raise ValueError("anchor approval must classify every issue by severity")
        if self.decision == "APPROVED" and (self.blocking_issue_ids or self.disputed_issue_ids):
            raise ValueError("approved anchor entries cannot retain blocking or disputed issues")
        if self.decision == "APPROVED" and set(self.advisory_issue_ids) != set(self.acknowledged_advisory_issue_ids):
            raise ValueError("approved anchor entries must acknowledge every advisory issue")
        return self


class SocialAnchorBehaviorQuota(ContractModel):
    behavior_id: BehaviorId
    approved_target: PositiveInt
    train: PositiveInt
    validation: PositiveInt
    anchor_holdout: PositiveInt

    @model_validator(mode="after")
    def validate_total(self) -> SocialAnchorBehaviorQuota:
        if self.approved_target != self.train + self.validation + self.anchor_holdout:
            raise ValueError("anchor behavior quota partitions must sum to the approved target")
        return self


class SocialAnchorCoveragePolicy(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-coverage-policy/v1"] = Field(
        default="stwm.model.social-anchor-coverage-policy/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    policy_id: Literal["stwm.m4.reviewed-social-anchors-300/v1"] = "stwm.m4.reviewed-social-anchors-300/v1"
    selector_id: Literal["stwm.m4.greedy-pairwise-selector/v1"] = "stwm.m4.greedy-pairwise-selector/v1"
    quotas: Annotated[list[SocialAnchorBehaviorQuota], Field(min_length=7, max_length=7)]
    relation_cut_points: tuple[float, float] = (1.0 / 3.0, 2.0 / 3.0)
    target_stress_cut_point: float = 0.5
    sociability_low_maximum: float = 0.5
    sociability_high_minimum: float = 0.55
    irritability_low_maximum: float = 0.25
    irritability_high_minimum: float = 0.3
    event_heavy_minimum: float = 0.6
    near_neighbor_linf_maximum: float = 0.1
    acceptance_dispute_threshold: float = 0.2
    allowed_delta_absolute_floor: float = 0.04
    allowed_delta_bound_span_fraction: float = 0.5
    max_actor_target_pair_repeats_per_behavior_partition: PositiveInt = 3
    max_exact_coverage_signature_repeats_per_behavior_partition: PositiveInt = 3
    orchestrator_sample_minimum: PositiveInt = 3
    orchestrator_sample_fraction: float = 0.1

    @model_validator(mode="after")
    def validate_frozen_quotas(self) -> SocialAnchorCoveragePolicy:
        actual = {
            item.behavior_id: (item.approved_target, item.train, item.validation, item.anchor_holdout)
            for item in self.quotas
        }
        expected = {
            BehaviorId.GREET: (40, 28, 4, 8),
            BehaviorId.CHAT: (40, 28, 4, 8),
            BehaviorId.JOKE: (40, 28, 4, 8),
            BehaviorId.COMPLIMENT: (40, 28, 4, 8),
            BehaviorId.INVITE_JOIN: (40, 28, 4, 8),
            BehaviorId.APOLOGIZE: (50, 35, 5, 10),
            BehaviorId.CONFRONT: (50, 35, 5, 10),
        }
        if actual != expected or len(self.quotas) != len(actual):
            raise ValueError("anchor coverage policy must use the frozen seven-behavior 300 quota")
        frozen_scalars = (
            self.relation_cut_points,
            self.target_stress_cut_point,
            self.sociability_low_maximum,
            self.sociability_high_minimum,
            self.irritability_low_maximum,
            self.irritability_high_minimum,
            self.event_heavy_minimum,
            self.near_neighbor_linf_maximum,
            self.acceptance_dispute_threshold,
            self.allowed_delta_absolute_floor,
            self.allowed_delta_bound_span_fraction,
            self.max_actor_target_pair_repeats_per_behavior_partition,
            self.max_exact_coverage_signature_repeats_per_behavior_partition,
            self.orchestrator_sample_minimum,
            self.orchestrator_sample_fraction,
        )
        expected_scalars = (
            (1.0 / 3.0, 2.0 / 3.0),
            0.5,
            0.5,
            0.55,
            0.25,
            0.3,
            0.6,
            0.1,
            0.2,
            0.04,
            0.5,
            3,
            3,
            3,
            0.1,
        )
        if frozen_scalars != expected_scalars:
            raise ValueError("anchor coverage policy thresholds are frozen by ADR-0013")
        return self


class SocialAnchorApprovalManifest(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-approval-manifest/v1"] = Field(
        default="stwm.model.social-anchor-approval-manifest/v1", alias="schema", serialization_alias="schema"
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    approval_id: Annotated[str, Field(pattern=r"^anchor_approval_[a-f0-9]{24}$")]
    status: Literal["DRAFT", "FINAL"]
    created_at_utc: Annotated[str, Field(min_length=1)]
    producer_id: Annotated[str, Field(min_length=1)]
    reviewer_id: Annotated[str, Field(min_length=1)]
    source_dataset_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    previous_approval_manifest_sha256: Annotated[str | None, Field(pattern=SHA256_PATTERN)] = None
    coverage_policy: ArtifactDescriptor
    tasks: ArtifactDescriptor
    judgments: ArtifactDescriptor
    issues: ArtifactDescriptor
    entries: Annotated[list[SocialAnchorApprovalEntry], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_manifest(self) -> SocialAnchorApprovalManifest:
        if self.producer_id == self.reviewer_id:
            raise ValueError("anchor producer and reviewer identities must differ")
        approved = [item for item in self.entries if item.decision == "APPROVED"]
        if len({item.anchor_id for item in approved}) != len(approved):
            raise ValueError("approved anchor IDs must be unique")
        if len({item.task_sha256 for item in approved}) != len(approved):
            raise ValueError("approved anchor tasks must be unique")
        if len({item.judgment_sha256 for item in approved}) != len(approved):
            raise ValueError("approved anchor judgments must be unique")
        if self.status == "FINAL":
            expected: dict[tuple[BehaviorId, AnchorPartition], int] = {}
            for behavior, train, validation, holdout in (
                (BehaviorId.GREET, 28, 4, 8),
                (BehaviorId.CHAT, 28, 4, 8),
                (BehaviorId.JOKE, 28, 4, 8),
                (BehaviorId.COMPLIMENT, 28, 4, 8),
                (BehaviorId.INVITE_JOIN, 28, 4, 8),
                (BehaviorId.APOLOGIZE, 35, 5, 10),
                (BehaviorId.CONFRONT, 35, 5, 10),
            ):
                expected[(behavior, "TRAIN")] = train
                expected[(behavior, "VALIDATION")] = validation
                expected[(behavior, "ANCHOR_HOLDOUT")] = holdout
            actual = {
                key: sum(item.behavior_id == key[0] and item.partition == key[1] for item in approved)
                for key in expected
            }
            if len(approved) != 300 or actual != expected:
                raise ValueError("final anchor approval must select the frozen 300-entry partition matrix")
        return self


class SocialAnchorReviewedBatchSource(ContractModel):
    behavior_id: BehaviorId
    batch_manifest: ArtifactDescriptor
    draft_approval: ArtifactDescriptor

    @model_validator(mode="after")
    def validate_behavior(self) -> SocialAnchorReviewedBatchSource:
        if self.behavior_id not in REVIEWED_SOCIAL_BEHAVIORS:
            raise ValueError("anchor training source behavior is outside the reviewed social allowlist")
        return self


class SocialAnchorTrainingInputManifest(ContractModel):
    schema_id: Literal["stwm.model.social-anchor-training-input-manifest/v1"] = Field(
        default="stwm.model.social-anchor-training-input-manifest/v1",
        alias="schema",
        serialization_alias="schema",
    )
    project_name: Literal["Small Town World Model（STWM）"] = "Small Town World Model（STWM）"
    source_commit: Annotated[str, Field(pattern=COMMIT_PATTERN)]
    created_at_utc: Annotated[str, Field(min_length=1)]
    source_dataset_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    raw_dataset_manifest: ArtifactDescriptor
    coverage_policy: ArtifactDescriptor
    tasks: ArtifactDescriptor
    final_anchor_approval: ArtifactDescriptor
    fit_judgments: ArtifactDescriptor
    source_batches: Annotated[list[SocialAnchorReviewedBatchSource], Field(min_length=7, max_length=7)]
    train_count: Literal[210] = 210
    validation_count: Literal[30] = 30
    excluded_anchor_holdout_count: Literal[60] = 60
    included_partitions: tuple[Literal["TRAIN"], Literal["VALIDATION"]] = ("TRAIN", "VALIDATION")
    excluded_partition: Literal["ANCHOR_HOLDOUT"] = "ANCHOR_HOLDOUT"
    heuristic_passthrough_output_paths: Annotated[list[HeuristicPassthroughOutputPath], Field(min_length=6)]
    training_eligible: Literal[True] = True

    @model_validator(mode="after")
    def validate_frozen_training_boundary(self) -> SocialAnchorTrainingInputManifest:
        behaviors = [item.behavior_id for item in self.source_batches]
        if len(set(behaviors)) != 7 or set(behaviors) != REVIEWED_SOCIAL_BEHAVIORS:
            raise ValueError("anchor training input must reference exactly one reviewed batch per behavior")
        expected_passthrough = {
            "need_delta_preview.hunger",
            "need_delta_preview.energy",
            "need_delta_preview.hygiene",
            "need_delta_preview.fun",
            "need_delta_preview.social",
            "event_probabilities",
        }
        if (
            len(self.heuristic_passthrough_output_paths) != len(expected_passthrough)
            or set(self.heuristic_passthrough_output_paths) != expected_passthrough
        ):
            raise ValueError("anchor training input must preserve every ADR-0012 heuristic passthrough head")
        return self


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
