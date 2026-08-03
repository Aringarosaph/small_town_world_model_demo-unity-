"""Strict external validation for M4 teacher Parquet datasets."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from town_core.domain.enums import BehaviorId
from town_core.modeling.contracts import DatasetManifest, TrainingExample


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dataset(root: Path) -> dict[str, object]:
    manifest_path = root / "dataset-manifest.json"
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.status != "COMPLETED":
        raise ValueError("M4 dataset manifest is not terminal COMPLETED")
    try:
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as exc:
        raise RuntimeError("M4 dataset validation requires pyarrow") from exc

    row_ids: set[str] = set()
    group_shards: dict[str, set[str]] = defaultdict(set)
    group_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    behavior_counts: Counter[BehaviorId] = Counter()
    observed_rows = 0
    for descriptor in manifest.shards:
        path = (root / descriptor.relative_path).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("M4 dataset shard escaped its dataset root")
        if not path.is_file():
            raise FileNotFoundError(f"missing M4 dataset shard: {descriptor.relative_path}")
        if path.stat().st_size != descriptor.bytes or _sha256(path) != descriptor.sha256:
            raise ValueError(f"M4 dataset shard descriptor mismatch: {descriptor.shard_id}")
        table = cast(Any, pq).read_table(path)
        records = table.to_pylist()
        if len(records) != descriptor.row_count:
            raise ValueError(f"M4 Parquet row count mismatch: {descriptor.shard_id}")
        descriptor_splits: Counter[str] = Counter()
        descriptor_groups: set[str] = set()
        for record in records:
            example = TrainingExample.model_validate_json(record["example_json"])
            feature = example.feature
            if (
                record["row_id"] != feature.row_id
                or record["decision_group_id"] != feature.decision_group_id
                or record["scenario_group_id"] != feature.scenario_group_id
                or record["split"] != feature.split
                or record["behavior_id"] != feature.raw_candidate.behavior_id.value
                or record["selected_by_teacher"] != example.label.selected_by_teacher
            ):
                raise ValueError(f"M4 Parquet index projection mismatch: {feature.row_id}")
            if feature.row_id in row_ids:
                raise ValueError(f"duplicate M4 row ID: {feature.row_id}")
            row_ids.add(feature.row_id)
            group_shards[feature.decision_group_id].add(descriptor.shard_id)
            group_splits[feature.decision_group_id].add(feature.split)
            descriptor_groups.add(feature.decision_group_id)
            descriptor_splits[feature.split] += 1
            split_counts[feature.split] += 1
            behavior_counts[feature.raw_candidate.behavior_id] += 1
            observed_rows += 1
        expected_descriptor_splits = {
            "train": descriptor_splits["train"],
            "validation": descriptor_splits["validation"],
            "test": descriptor_splits["test"],
        }
        if expected_descriptor_splits != descriptor.split_counts:
            raise ValueError(f"M4 shard split counts mismatch: {descriptor.shard_id}")
        if len(descriptor_groups) != descriptor.decision_group_count:
            raise ValueError(f"M4 shard decision group count mismatch: {descriptor.shard_id}")

    if any(len(value) != 1 for value in group_shards.values()):
        raise ValueError("an M4 decision group was split across Parquet shards")
    if any(len(value) != 1 for value in group_splits.values()):
        raise ValueError("an M4 decision group crossed dataset splits")
    expected_splits = {
        "train": split_counts["train"],
        "validation": split_counts["validation"],
        "test": split_counts["test"],
    }
    expected_behaviors = {behavior: behavior_counts[behavior] for behavior in BehaviorId}
    if observed_rows != manifest.row_count or len(group_shards) != manifest.decision_group_count:
        raise ValueError("M4 dataset aggregate row/group counts differ from manifest")
    if expected_splits != manifest.split_counts or expected_behaviors != manifest.behavior_counts:
        raise ValueError("M4 dataset aggregate split/behavior counts differ from manifest")
    return {
        "schema": "stwm.model.dataset-validation/v1",
        "dataset_id": manifest.dataset_id,
        "passed": True,
        "manifest_sha256": _sha256(manifest_path),
        "row_count": observed_rows,
        "decision_group_count": len(group_shards),
        "split_counts": expected_splits,
        "behavior_counts": {key.value: value for key, value in expected_behaviors.items()},
        "shard_count": len(manifest.shards),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an external M4 teacher dataset")
    parser.add_argument("--dataset", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(json.dumps(validate_dataset(arguments.dataset), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
