"""Deterministic task selection for independently reviewed M4 social anchors."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from town_core.domain.enums import BehaviorId, LocationType
from town_core.modeling.contracts import (
    REVIEWED_SOCIAL_BEHAVIORS,
    AnchorPartition,
    DatasetManifest,
    DatasetShard,
    SocialAnchorBehaviorQuota,
    SocialAnchorCoveragePolicy,
    SocialAnchorCoverageSignature,
    SocialAnchorTask,
    TrainingExample,
)
from town_core.modeling.validate_dataset import validate_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BEHAVIOR_ORDER = (
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
)
PARTITION_ORDER: tuple[AnchorPartition, ...] = ("TRAIN", "VALIDATION", "ANCHOR_HOLDOUT")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *values: str) -> str:
    digest = _sha256_bytes("\x1f".join(values).encode("utf-8"))[:24]
    return f"{prefix}_{digest}"


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 reviewed-anchor artifacts must remain outside the repository")


def default_coverage_policy() -> SocialAnchorCoveragePolicy:
    return SocialAnchorCoveragePolicy(
        quotas=[
            SocialAnchorBehaviorQuota(
                behavior_id=behavior,
                approved_target=target,
                train=train,
                validation=validation,
                anchor_holdout=holdout,
            )
            for behavior, target, train, validation, holdout in (
                (BehaviorId.GREET, 40, 28, 4, 8),
                (BehaviorId.CHAT, 40, 28, 4, 8),
                (BehaviorId.JOKE, 40, 28, 4, 8),
                (BehaviorId.COMPLIMENT, 40, 28, 4, 8),
                (BehaviorId.INVITE_JOIN, 40, 28, 4, 8),
                (BehaviorId.APOLOGIZE, 50, 35, 5, 10),
                (BehaviorId.CONFRONT, 50, 35, 5, 10),
            )
        ]
    )


def _relation_bin(value: float) -> str:
    if value < 1.0 / 3.0:
        return "LOW"
    if value < 2.0 / 3.0:
        return "MIDDLE"
    return "HIGH"


def _personality_bin(value: float, *, low_maximum: float, high_minimum: float) -> str:
    if value <= low_maximum:
        return "LOW"
    if value >= high_minimum:
        return "HIGH"
    return "GAP"


def coverage_signature(example: TrainingExample) -> SocialAnchorCoverageSignature:
    feature = example.feature
    target = feature.raw_target
    if target is None or not feature.masks.acceptance_present:
        raise ValueError("reviewed social anchor candidate requires target and acceptance features")
    event_importance = max((event.importance for event in feature.raw_events), default=None)
    if event_importance is None:
        event_bin = "NONE"
    elif event_importance < 0.6:
        event_bin = "LIGHT"
    else:
        event_bin = "HEAVY"
    if target.same_household:
        identity_bin = "SAME_HOUSEHOLD"
    elif target.coworker:
        identity_bin = "COWORKER"
    else:
        identity_bin = "ACQUAINTANCE"
    relationship = target.relationship_familiarity, target.relationship_affinity, target.relationship_trust
    return SocialAnchorCoverageSignature.model_validate(
        {
            "familiarity_bin": _relation_bin(relationship[0]),
            "affinity_bin": _relation_bin(relationship[1]),
            "trust_bin": _relation_bin(relationship[2]),
            "tension_bin": _relation_bin(target.relationship_tension),
            "target_stress_bin": "LOW" if target.mood.stress < 0.5 else "HIGH",
            "actor_sociability_bin": _personality_bin(
                feature.raw_actor.personality.sociability,
                low_maximum=0.5,
                high_minimum=0.55,
            ),
            "actor_irritability_bin": _personality_bin(
                feature.raw_actor.personality.irritability,
                low_maximum=0.25,
                high_minimum=0.3,
            ),
            "privacy_bin": (
                "PRIVATE_HOME" if feature.raw_candidate.destination_location_type is LocationType.HOME else "PUBLIC"
            ),
            "event_context_bin": event_bin,
            "social_identity_bin": identity_bin,
        }
    )


def _signature_tokens(signature: SocialAnchorCoverageSignature) -> tuple[str, ...]:
    values = signature.model_dump(mode="json")
    return tuple(f"{key}={values[key]}" for key in sorted(values) if key != "relationship_direction")


def _coverage_pairs(signature: SocialAnchorCoverageSignature) -> frozenset[str]:
    return frozenset("|".join(pair) for pair in combinations(_signature_tokens(signature), 2))


@dataclass(frozen=True)
class AnchorSourceCandidate:
    example: TrainingExample
    shard: DatasetShard
    source_example_sha256: str
    signature: SocialAnchorCoverageSignature
    signature_key: str
    actor_target_pair_key: str
    tie_break: str

    @property
    def behavior_id(self) -> BehaviorId:
        return self.example.feature.raw_candidate.behavior_id

    @property
    def partition(self) -> AnchorPartition:
        return cast(
            AnchorPartition,
            {"train": "TRAIN", "validation": "VALIDATION", "test": "ANCHOR_HOLDOUT"}[self.example.feature.split],
        )


def _source_candidate(
    example_json: str,
    *,
    shard: DatasetShard,
    dataset_manifest_sha256: str,
) -> AnchorSourceCandidate | None:
    example = TrainingExample.model_validate_json(example_json)
    feature = example.feature
    behavior = feature.raw_candidate.behavior_id
    if behavior not in REVIEWED_SOCIAL_BEHAVIORS or feature.raw_target is None or not feature.masks.acceptance_present:
        return None
    signature = coverage_signature(example)
    signature_key = _canonical(signature.model_dump(mode="json"))
    pair_key = f"{feature.actor_id}->{feature.raw_target.agent_id}"
    return AnchorSourceCandidate(
        example=example,
        shard=shard,
        source_example_sha256=_sha256_bytes(example_json.encode("utf-8")),
        signature=signature,
        signature_key=signature_key,
        actor_target_pair_key=pair_key,
        tie_break=_sha256_bytes(f"{dataset_manifest_sha256}:{feature.row_id}".encode()),
    )


def _compact_candidates(candidates: Iterable[AnchorSourceCandidate]) -> list[AnchorSourceCandidate]:
    best: dict[tuple[BehaviorId, AnchorPartition, str, str], AnchorSourceCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.behavior_id,
            candidate.partition,
            candidate.signature_key,
            candidate.actor_target_pair_key,
        )
        current = best.get(key)
        if current is None or candidate.tie_break < current.tie_break:
            best[key] = candidate
    return sorted(best.values(), key=lambda item: item.tie_break)


def _select_partition(
    candidates: Sequence[AnchorSourceCandidate],
    *,
    count: int,
    policy: SocialAnchorCoveragePolicy,
) -> tuple[list[AnchorSourceCandidate], int, int]:
    remaining = list(candidates)
    feasible_pairs = set().union(*(_coverage_pairs(item.signature) for item in remaining)) if remaining else set()
    covered_pairs: set[str] = set()
    pair_counts: Counter[str] = Counter()
    signature_counts: Counter[str] = Counter()
    selected: list[AnchorSourceCandidate] = []
    while len(selected) < count:
        eligible = [
            item
            for item in remaining
            if pair_counts[item.actor_target_pair_key] < policy.max_actor_target_pair_repeats_per_behavior_partition
            and signature_counts[item.signature_key]
            < policy.max_exact_coverage_signature_repeats_per_behavior_partition
        ]
        if not eligible:
            raise ValueError("validated raw dataset cannot fill the frozen anchor quota under repetition caps")
        chosen = min(
            eligible,
            key=lambda item: (
                -len(_coverage_pairs(item.signature) - covered_pairs),
                pair_counts[item.actor_target_pair_key],
                signature_counts[item.signature_key],
                item.tie_break,
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)
        covered_pairs.update(_coverage_pairs(chosen.signature))
        pair_counts[chosen.actor_target_pair_key] += 1
        signature_counts[chosen.signature_key] += 1
    return selected, len(covered_pairs), len(feasible_pairs)


def select_anchor_tasks(
    candidates: Sequence[AnchorSourceCandidate],
    *,
    dataset_manifest_sha256: str,
    policy: SocialAnchorCoveragePolicy,
) -> tuple[list[SocialAnchorTask], list[dict[str, object]]]:
    compact = _compact_candidates(candidates)
    by_cell: dict[tuple[BehaviorId, AnchorPartition], list[AnchorSourceCandidate]] = {}
    for item in compact:
        by_cell.setdefault((item.behavior_id, item.partition), []).append(item)
    quotas = {item.behavior_id: item for item in policy.quotas}
    selected_sources: list[AnchorSourceCandidate] = []
    coverage_rows: list[dict[str, object]] = []
    for behavior in BEHAVIOR_ORDER:
        quota = quotas[behavior]
        counts = {
            "TRAIN": quota.train,
            "VALIDATION": quota.validation,
            "ANCHOR_HOLDOUT": quota.anchor_holdout,
        }
        for partition in PARTITION_ORDER:
            chosen, covered_count, feasible_count = _select_partition(
                by_cell.get((behavior, partition), []),
                count=counts[partition],
                policy=policy,
            )
            selected_sources.extend(chosen)
            coverage_rows.append(
                {
                    "behavior_id": behavior.value,
                    "partition": partition,
                    "selected_count": len(chosen),
                    "covered_pair_count": covered_count,
                    "feasible_pair_count": feasible_count,
                }
            )
    tasks: list[SocialAnchorTask] = []
    for item in selected_sources:
        feature = item.example.feature
        identity_values = (dataset_manifest_sha256, feature.row_id)
        tasks.append(
            SocialAnchorTask(
                task_id=_stable_id("anchor_task", *identity_values),
                anchor_id=_stable_id("anchor", *identity_values),
                family_id=_stable_id("anchor_family", dataset_manifest_sha256, feature.scenario_group_id),
                batch_id=f"social_{item.behavior_id.value}_v1",
                behavior_id=item.behavior_id,
                partition=item.partition,
                source_dataset_manifest_sha256=dataset_manifest_sha256,
                source_shard_relative_path=item.shard.relative_path,
                source_shard_sha256=item.shard.sha256,
                source_example_sha256=item.source_example_sha256,
                actor_target_pair_key=item.actor_target_pair_key,
                coverage_signature=item.signature,
                feature=feature,
                heuristic_baseline=item.example.label,
            )
        )
    if len(tasks) != 300 or len({task.task_id for task in tasks}) != 300:
        raise RuntimeError("frozen anchor task selector did not emit exactly 300 unique tasks")
    return tasks, coverage_rows


def _load_candidates(root: Path, manifest: DatasetManifest, manifest_sha256: str) -> list[AnchorSourceCandidate]:
    try:
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as exc:
        raise RuntimeError("M4 reviewed-anchor selection requires pyarrow") from exc
    candidates: list[AnchorSourceCandidate] = []
    for shard in manifest.shards:
        table = cast(Any, pq).read_table(root / shard.relative_path, columns=["example_json"])
        for record in table.to_pylist():
            candidate = _source_candidate(
                cast(str, record["example_json"]),
                shard=shard,
                dataset_manifest_sha256=manifest_sha256,
            )
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def generate_anchor_tasks(*, dataset_root: Path, output_root: Path) -> dict[str, object]:
    _ensure_external(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("M4 reviewed-anchor output root must be absent or empty")
    validation = validate_dataset(dataset_root)
    manifest_path = dataset_root / "dataset-manifest.json"
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    manifest_sha256 = cast(str, validation["manifest_sha256"])
    policy = default_coverage_policy()
    candidates = _load_candidates(dataset_root, manifest, manifest_sha256)
    tasks, coverage = select_anchor_tasks(
        candidates,
        dataset_manifest_sha256=manifest_sha256,
        policy=policy,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    policy_path = output_root / "coverage-policy.json"
    tasks_path = output_root / "anchor-tasks.jsonl"
    coverage_path = output_root / "coverage-report.json"
    policy_path.write_text(
        json.dumps(policy.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tasks_path.write_text(
        "".join(_canonical(task.model_dump(mode="json", by_alias=True, exclude_none=False)) + "\n" for task in tasks),
        encoding="utf-8",
    )
    coverage_document = {
        "format": "stwm.model.social-anchor-selection-report/v1",
        "project_name": "Small Town World Model（STWM）",
        "policy_id": policy.policy_id,
        "dataset_manifest_sha256": manifest_sha256,
        "task_count": len(tasks),
        "coverage": coverage,
    }
    coverage_path.write_text(
        json.dumps(coverage_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "format": "stwm.model.social-anchor-task-generation-result/v1",
        "task_count": len(tasks),
        "dataset_manifest_sha256": manifest_sha256,
        "policy_sha256": _sha256_file(policy_path),
        "tasks_sha256": _sha256_file(tasks_path),
        "coverage_sha256": _sha256_file(coverage_path),
        "output_root": str(output_root.resolve()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select immutable M4 reviewed social-anchor tasks")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(
        json.dumps(
            generate_anchor_tasks(dataset_root=arguments.dataset, output_root=arguments.output_root),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
