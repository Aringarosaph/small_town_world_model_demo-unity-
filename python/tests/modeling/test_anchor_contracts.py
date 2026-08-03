from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError
from town_core.catalogs import load_catalog
from town_core.domain.config_models import MoodValues, NeedValues, PersonalityValues
from town_core.domain.decision_models import HardCostPreview, OutcomePrediction
from town_core.domain.enums import BehaviorId, LocationType, RelationshipDirection, RelationshipRole
from town_core.domain.state_models import MoodDelta, NeedDelta, RelationshipDelta
from town_core.modeling.anchor_review import assemble_producer_judgments
from town_core.modeling.anchors import (
    REPOSITORY_ROOT,
    AnchorSourceCandidate,
    _source_candidate,
    default_coverage_policy,
    select_anchor_tasks,
)
from town_core.modeling.contracts import (
    ArtifactDescriptor,
    CandidateFeatureRow,
    CategoricalFeatures,
    DatasetShard,
    FeatureMasks,
    NumericFeatures,
    OutcomeLabel,
    RawActorFeatures,
    RawCandidateFeatures,
    RawTargetFeatures,
    SocialAnchorApprovalEntry,
    SocialAnchorApprovalManifest,
    SocialAnchorCoveragePolicy,
    SocialAnchorJudgment,
    SocialAnchorTypedAssertion,
    TrainingExample,
)
from town_core.modeling.postprocess import CatalogOutcomePostprocessor

BEHAVIORS = (
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
)
SPLITS = ("train", "validation", "test")


def _digest(value: str, length: int = 64) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def _example(index: int, behavior: BehaviorId, split: str) -> TrainingExample:
    actor_number = index % 10 + 1
    target_number = (actor_number - 1 + (index // 10) % 9 + 1) % 10 + 1
    actor_id = f"npc_{actor_number:02d}"
    target_id = f"npc_{target_number:02d}"
    candidate_id = f"candidate_{index + 1}"
    relation_values = (0.15 + 0.35 * (index % 3), 0.15 + 0.35 * ((index // 3) % 3))
    feature = CandidateFeatureRow(
        row_id=f"row_{_digest(f'row:{index}', 24)}",
        source_commit="a" * 40,
        seed=12345,
        episode_id=f"episode_{index:04d}",
        scenario_group_id=f"scenario_{split}_{index:04d}",
        split=split,  # type: ignore[arg-type]
        decision_group_id=f"decision_group_{index:04d}",
        decision_id=f"decision_{index:04d}",
        candidate_id=candidate_id,
        actor_id=actor_id,
        source_state_version=index,
        game_minute=index,
        candidate_rank=0,
        raw_actor=RawActorFeatures(
            needs=NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.5, social=0.5),
            mood=MoodValues(valence=0.0, stress=0.4),
            personality=PersonalityValues(
                sociability=(0.4, 0.6)[index % 2],
                discipline=0.5,
                frugality=0.5,
                irritability=(0.2, 0.4)[(index // 2) % 2],
            ),
            household_money=100,
            household_food_units=10,
            current_location_id="home_a",
            home_location_id="home_a",
            assigned_work_location_id="cafe_bar",
            local_population=2,
            known_event_count=0,
            decision_overdue_minutes=0,
        ),
        raw_candidate=RawCandidateFeatures(
            behavior_id=behavior,
            destination_location_id=("home_a", "park")[index % 2],
            destination_location_type=(LocationType.HOME, LocationType.PARK)[index % 2],
            target_object_ids=[],
            object_type_values=[],
            capability_values=[],
            estimated_travel_minutes=5,
            estimated_duration_minutes=10,
            schedule_conflict_minutes=0,
            hard_cost_preview=HardCostPreview(),
            repeats_previous_behavior=False,
            crosses_location=False,
            joint_action_candidate=behavior is BehaviorId.INVITE_JOIN,
        ),
        raw_target=RawTargetFeatures(
            agent_id=target_id,
            needs=NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.5, social=0.5),
            mood=MoodValues(valence=0.0, stress=(0.3, 0.7)[(index // 4) % 2]),
            relationship_roles_target_to_actor=[RelationshipRole.ACQUAINTANCE],
            relationship_familiarity=relation_values[0],
            relationship_affinity=relation_values[1],
            relationship_trust=0.15 + 0.35 * ((index // 9) % 3),
            relationship_tension=0.15 + 0.35 * ((index // 27) % 3),
            minutes_since_interaction=index,
            same_household=index % 5 == 0,
            coworker=index % 5 == 1,
            active_conversation=False,
            knows_selected_event=False,
        ),
        raw_events=[],
        numeric=NumericFeatures(
            actor_needs=NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.5, social=0.5),
            actor_mood=MoodValues(valence=0.0, stress=0.4),
            actor_personality=PersonalityValues(sociability=0.6, discipline=0.5, frugality=0.5, irritability=0.2),
            household_money_ratio=1.0,
            household_food_ratio=1.0,
            minute_of_day_sin=0.0,
            minute_of_day_cos=1.0,
            weekday_sin=0.0,
            weekday_cos=1.0,
            local_population_ratio=0.2,
            known_event_count_ratio=0.0,
            decision_overdue_ratio=0.0,
            travel_ratio=0.1,
            duration_ratio=0.1,
            schedule_conflict_ratio=0.0,
            money_cost_ratio=0.0,
            food_cost_ratio=0.0,
            target_needs=NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.5, social=0.5),
            target_mood=MoodValues(valence=0.0, stress=0.3),
            target_relationship=[relation_values[0], relation_values[1], 0.5, 0.5],
            target_interaction_age_ratio=0.1,
            event_importance=[0.0, 0.0, 0.0, 0.0],
            event_age_ratio=[0.0, 0.0, 0.0, 0.0],
        ),
        categorical=CategoricalFeatures(
            behavior_index=0,
            actor_current_location_index=0,
            actor_home_location_index=0,
            actor_work_location_index=1,
            destination_location_type_index=0,
            object_type_indices=[],
            capability_indices=[],
            relationship_role_indices=[0],
            event_type_indices=[-1, -1, -1, -1],
        ),
        masks=FeatureMasks(
            target_present=True,
            relationship_present=True,
            acceptance_present=True,
            target_mood_present=True,
            relationship_delta_present=True,
            event_mask=[False, False, False, False],
        ),
    )
    prediction = OutcomePrediction(
        prediction_id=f"prediction_{index + 1}",
        candidate_id=candidate_id,
        need_delta_preview=NeedDelta(hunger=0.0, energy=0.0, hygiene=0.0, fun=0.0, social=0.1),
        actor_mood_delta=MoodDelta(valence=0.1, stress=-0.1),
        target_mood_delta=MoodDelta(valence=0.1, stress=-0.1),
        relationship_direction=RelationshipDirection.TARGET_TO_ACTOR,
        relationship_delta_target_to_actor=RelationshipDelta(
            familiarity=0.02,
            affinity=0.02,
            trust=0.01,
            tension=-0.01,
        ),
        acceptance_probability=0.7,
        event_probabilities={},
    )
    return TrainingExample(
        feature=feature,
        label=OutcomeLabel(
            row_id=feature.row_id,
            prediction=prediction,
            utility_terms={"social": 1.0},
            total_score=1.0,
            tie_break=0.0,
            selected_by_teacher=True,
            resolver_attempted=True,
            resolver_result="ACCEPTED",
        ),
    )


def _candidate_matrix() -> list[AnchorSourceCandidate]:
    shard = DatasetShard(
        shard_id="shard_00000",
        relative_path="shards/shard_00000.parquet",
        sha256="b" * 64,
        bytes=100,
        row_count=1260,
        decision_group_count=1260,
        split_counts={"train": 420, "validation": 420, "test": 420},
    )
    candidates = []
    index = 0
    for behavior in BEHAVIORS:
        for split in SPLITS:
            for _ in range(60):
                example = _example(index, behavior, split)
                payload = json.dumps(
                    example.model_dump(mode="json", by_alias=True, exclude_none=False),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                candidate = _source_candidate(
                    payload,
                    shard=shard,
                    dataset_manifest_sha256="c" * 64,
                )
                assert candidate is not None
                candidates.append(candidate)
                index += 1
    return candidates


def test_frozen_policy_and_selector_emit_exact_hash_stable_matrix() -> None:
    policy = default_coverage_policy()
    candidates = _candidate_matrix()
    tasks, coverage = select_anchor_tasks(
        candidates,
        dataset_manifest_sha256="c" * 64,
        policy=policy,
    )
    reversed_tasks, reversed_coverage = select_anchor_tasks(
        list(reversed(candidates)),
        dataset_manifest_sha256="c" * 64,
        policy=policy,
    )

    assert [task.task_id for task in tasks] == [task.task_id for task in reversed_tasks]
    assert coverage == reversed_coverage
    assert len(tasks) == len({task.task_id for task in tasks}) == 300
    counts = Counter((task.behavior_id, task.partition) for task in tasks)
    assert counts[(BehaviorId.GREET, "TRAIN")] == 28
    assert counts[(BehaviorId.APOLOGIZE, "TRAIN")] == 35
    assert counts[(BehaviorId.CONFRONT, "ANCHOR_HOLDOUT")] == 10
    assert max(Counter((task.behavior_id, task.partition, task.actor_target_pair_key) for task in tasks).values()) <= 3
    assert (
        max(
            Counter(
                (
                    task.behavior_id,
                    task.partition,
                    json.dumps(task.coverage_signature.model_dump(mode="json"), sort_keys=True),
                )
                for task in tasks
            ).values()
        )
        <= 3
    )


def test_anchor_judgment_and_final_approval_keep_provenance_separate() -> None:
    policy = default_coverage_policy()
    tasks, _ = select_anchor_tasks(
        _candidate_matrix(),
        dataset_manifest_sha256="c" * 64,
        policy=policy,
    )
    first = tasks[0]
    judgment = SocialAnchorJudgment(
        judgment_id=f"anchor_judgment_{'d' * 24}",
        task_id=first.task_id,
        task_sha256="e" * 64,
        anchor_id=first.anchor_id,
        family_id=first.family_id,
        batch_id=first.batch_id,
        behavior_id=first.behavior_id,
        partition=first.partition,
        candidate_id=first.feature.candidate_id,
        producer_id="AITOWN-ANCHOR-PRODUCER",
        produced_at_utc="2026-08-04T00:00:00Z",
        proposed_prediction=first.heuristic_baseline.prediction,
        rationale_tags=["direction_checked"],
        typed_assertions=[
            SocialAnchorTypedAssertion(
                assertion_id=f"assertion_{'f' * 16}",
                assertion_type="DIRECTION",
                statement="Relationship effects remain Target-to-Actor.",
            )
        ],
    )
    assert judgment.provider_id == "stwm.codex.anchor-producer/v1"
    assert first.heuristic_baseline.teacher_provider_id == "stwm.heuristic.m3/v1"

    entries = [
        SocialAnchorApprovalEntry(
            anchor_id=task.anchor_id,
            task_id=task.task_id,
            task_sha256=_digest(f"task:{index}"),
            judgment_id=f"anchor_judgment_{_digest(f'judgment-id:{index}', 24)}",
            judgment_sha256=_digest(f"judgment:{index}"),
            behavior_id=task.behavior_id,
            partition=task.partition,
            decision="APPROVED",
            issue_ids=[],
            blocking_issue_ids=[],
            disputed_issue_ids=[],
            advisory_issue_ids=[],
            acknowledged_advisory_issue_ids=[],
        )
        for index, task in enumerate(tasks)
    ]
    descriptor = ArtifactDescriptor(relative_path="anchors/artifact.jsonl", sha256="1" * 64, bytes=1)
    manifest = SocialAnchorApprovalManifest(
        approval_id=f"anchor_approval_{'2' * 24}",
        status="FINAL",
        created_at_utc="2026-08-04T00:00:00Z",
        producer_id="AITOWN-ANCHOR-PRODUCER",
        reviewer_id="AITOWN-ANCHOR-REVIEWER",
        source_dataset_manifest_sha256="c" * 64,
        coverage_policy=descriptor,
        tasks=descriptor,
        judgments=descriptor,
        issues=descriptor,
        entries=entries,
    )
    assert len([entry for entry in manifest.entries if entry.decision == "APPROVED"]) == 300

    invalid = manifest.model_dump(mode="json", by_alias=True)
    invalid["entries"][0]["decision"] = "REJECTED"
    with pytest.raises(ValidationError, match="frozen 300-entry"):
        SocialAnchorApprovalManifest.model_validate(invalid)


def test_coverage_policy_rejects_threshold_or_quota_drift() -> None:
    policy = default_coverage_policy().model_dump(mode="json", by_alias=True)
    policy["near_neighbor_linf_maximum"] = 0.11
    with pytest.raises(ValidationError, match="thresholds are frozen"):
        SocialAnchorCoveragePolicy.model_validate(policy)

    policy = default_coverage_policy().model_dump(mode="json", by_alias=True)
    policy["quotas"][0]["train"] = 27
    with pytest.raises(ValidationError):
        SocialAnchorCoveragePolicy.model_validate(policy)


def _write_greet_producer_inputs(tmp_path: Path) -> tuple[Path, Path]:
    tasks, _ = select_anchor_tasks(
        _candidate_matrix(),
        dataset_manifest_sha256="c" * 64,
        policy=default_coverage_policy(),
    )
    postprocessor = CatalogOutcomePostprocessor(load_catalog(REPOSITORY_ROOT / "config" / "v0"))
    tasks = [
        task.model_copy(
            update={
                "heuristic_baseline": task.heuristic_baseline.model_copy(
                    update={"prediction": postprocessor.process(task.feature, task.heuristic_baseline.prediction)[0]}
                )
            }
        )
        for task in tasks
    ]
    tasks_path = tmp_path / "anchor-tasks.jsonl"
    task_lines = [
        json.dumps(
            task.model_dump(mode="json", by_alias=True, exclude_none=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for task in tasks
    ]
    tasks_path.write_text("\n".join(task_lines) + "\n", encoding="utf-8")
    responses = []
    for task, line in zip(tasks, task_lines, strict=True):
        if task.behavior_id is not BehaviorId.GREET:
            continue
        prediction, _ = postprocessor.process(task.feature, task.heuristic_baseline.prediction)
        assert prediction.target_mood_delta is not None
        assert prediction.relationship_delta_target_to_actor is not None
        responses.append(
            {
                "task_id": task.task_id,
                "task_sha256": hashlib.sha256(line.encode()).hexdigest(),
                "need_delta_preview": prediction.need_delta_preview.model_dump(mode="json"),
                "actor_mood_delta": prediction.actor_mood_delta.model_dump(mode="json"),
                "target_mood_delta": prediction.target_mood_delta.model_dump(mode="json"),
                "relationship_delta_target_to_actor": prediction.relationship_delta_target_to_actor.model_dump(
                    mode="json"
                ),
                "acceptance_probability": prediction.acceptance_probability,
                "event_probabilities": prediction.event_probabilities,
                "rationale_tags": ["heuristic_baseline_reviewed"],
                "typed_assertions": [
                    {
                        "assertion_type": "DIRECTION",
                        "statement": "Relationship effects remain Target-to-Actor.",
                        "paired_task_id": None,
                        "paired_task_sha256": None,
                        "expected_order": None,
                    }
                ],
            }
        )
    responses_path = tmp_path / "greet-producer-responses.jsonl"
    responses_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for item in responses
        ),
        encoding="utf-8",
    )
    return tasks_path, responses_path


def test_producer_assembler_requires_exact_hashes_masks_and_bounds(tmp_path: Path) -> None:
    tasks_path, responses_path = _write_greet_producer_inputs(tmp_path)
    report = assemble_producer_judgments(
        config_path=REPOSITORY_ROOT / "config" / "v0",
        tasks_path=tasks_path,
        responses_path=responses_path,
        output_root=tmp_path / "valid-output",
        behavior_id=BehaviorId.GREET,
        producer_id="AITOWN-ANCHOR-PRODUCER",
        produced_at_utc="2026-08-04T00:00:00Z",
    )
    assert report["judgment_count"] == 40
    assert report["retained_heuristic_count"] == 40
    assert report["changed_from_heuristic_count"] == 0
    judgments = (tmp_path / "valid-output" / "greet-judgments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(judgments) == 40
    assert all(
        SocialAnchorJudgment.model_validate_json(line).provider_id == "stwm.codex.anchor-producer/v1"
        for line in judgments
    )

    response_rows = [json.loads(line) for line in responses_path.read_text(encoding="utf-8").splitlines()]
    response_rows[0]["actor_mood_delta"]["valence"] = 0.9
    invalid_path = tmp_path / "invalid-responses.jsonl"
    invalid_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for item in response_rows
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden mask/bounds repair"):
        assemble_producer_judgments(
            config_path=REPOSITORY_ROOT / "config" / "v0",
            tasks_path=tasks_path,
            responses_path=invalid_path,
            output_root=tmp_path / "invalid-output",
            behavior_id=BehaviorId.GREET,
            producer_id="AITOWN-ANCHOR-PRODUCER",
            produced_at_utc="2026-08-04T00:00:00Z",
        )
