"""Independent regeneration and integrity validation for M4 anchor task packets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from town_core.modeling.anchors import (
    REPOSITORY_ROOT,
    _canonical,
    _load_candidates,
    default_coverage_policy,
    select_anchor_tasks,
)
from town_core.modeling.contracts import DatasetManifest, SocialAnchorCoveragePolicy, SocialAnchorTask
from town_core.modeling.validate_dataset import validate_dataset


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 anchor validation report must remain outside the repository")


def _load_canonical_tasks(path: Path) -> list[SocialAnchorTask]:
    payload = path.read_text(encoding="utf-8")
    if not payload.endswith("\n") or "\n\n" in payload:
        raise ValueError("anchor task JSONL must be newline-terminated without blank records")
    tasks: list[SocialAnchorTask] = []
    for line in payload.splitlines():
        task = SocialAnchorTask.model_validate_json(line)
        canonical = _canonical(task.model_dump(mode="json", by_alias=True, exclude_none=False))
        if line != canonical:
            raise ValueError(f"anchor task is not canonical JSON: {task.task_id}")
        tasks.append(task)
    return tasks


def validate_anchor_tasks(*, dataset_root: Path, tasks_root: Path) -> dict[str, object]:
    validation = validate_dataset(dataset_root)
    manifest_path = dataset_root / "dataset-manifest.json"
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    manifest_sha256 = cast(str, validation["manifest_sha256"])

    policy_path = tasks_root / "coverage-policy.json"
    tasks_path = tasks_root / "anchor-tasks.jsonl"
    coverage_path = tasks_root / "coverage-report.json"
    policy = SocialAnchorCoveragePolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    if policy != default_coverage_policy():
        raise ValueError("anchor task packet coverage policy differs from the ADR-0013 frozen policy")
    tasks = _load_canonical_tasks(tasks_path)
    if len(tasks) != 300 or len({task.task_id for task in tasks}) != 300:
        raise ValueError("anchor task packet must contain exactly 300 unique tasks")
    if any(task.source_dataset_manifest_sha256 != manifest_sha256 for task in tasks):
        raise ValueError("anchor task packet references a different dataset manifest")

    candidates = _load_candidates(dataset_root, manifest, manifest_sha256)
    regenerated_tasks, regenerated_coverage = select_anchor_tasks(
        candidates,
        dataset_manifest_sha256=manifest_sha256,
        policy=policy,
    )
    serialized = [task.model_dump(mode="json", by_alias=True, exclude_none=False) for task in tasks]
    regenerated = [task.model_dump(mode="json", by_alias=True, exclude_none=False) for task in regenerated_tasks]
    if serialized != regenerated:
        raise ValueError("anchor task packet is not the deterministic selection from its source dataset")
    expected_coverage = {
        "format": "stwm.model.social-anchor-selection-report/v1",
        "project_name": "Small Town World Model（STWM）",
        "policy_id": policy.policy_id,
        "dataset_manifest_sha256": manifest_sha256,
        "task_count": 300,
        "coverage": regenerated_coverage,
    }
    coverage_document = json.loads(coverage_path.read_text(encoding="utf-8"))
    if coverage_document != expected_coverage:
        raise ValueError("anchor coverage report differs from independent deterministic regeneration")

    matrix = Counter((task.behavior_id.value, task.partition) for task in tasks)
    pair_repeats = Counter((task.behavior_id.value, task.partition, task.actor_target_pair_key) for task in tasks)
    signature_repeats = Counter(
        (
            task.behavior_id.value,
            task.partition,
            _canonical(task.coverage_signature.model_dump(mode="json")),
        )
        for task in tasks
    )
    return {
        "schema": "stwm.model.social-anchor-task-validation/v1",
        "project_name": "Small Town World Model（STWM）",
        "passed": True,
        "dataset_manifest_sha256": manifest_sha256,
        "task_count": len(tasks),
        "policy_sha256": _sha256_file(policy_path),
        "tasks_sha256": _sha256_file(tasks_path),
        "coverage_sha256": _sha256_file(coverage_path),
        "deterministic_regeneration_equal": True,
        "maximum_actor_target_pair_repeats": max(pair_repeats.values()),
        "maximum_exact_coverage_signature_repeats": max(signature_repeats.values()),
        "matrix": {f"{behavior}:{partition}": matrix[(behavior, partition)] for behavior, partition in sorted(matrix)},
        "coverage": regenerated_coverage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and regenerate an M4 social-anchor task packet")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    _ensure_external(arguments.output)
    report = validate_anchor_tasks(dataset_root=arguments.dataset, tasks_root=arguments.tasks_root)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_name(f".{arguments.output.name}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(arguments.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
