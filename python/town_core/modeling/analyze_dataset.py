"""Reproducible quality analysis for validated M4 teacher datasets."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from town_core.catalogs import load_catalog
from town_core.domain.enums import BehaviorId
from town_core.modeling.contracts import DatasetManifest
from town_core.modeling.dataset import REPOSITORY_ROOT, collector_state_config_hash
from town_core.modeling.validate_dataset import validate_dataset

PROJECT_NAME = "Small Town World Model（STWM）"
QUALITY_SCHEMA = "stwm.model.dataset-quality-report/v1"
SPLITS = ("train", "validation", "test")
MASK_NAMES = (
    "target_present",
    "relationship_present",
    "acceptance_present",
    "target_mood_present",
    "relationship_delta_present",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _ensure_external(path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    resolved = path.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("M4 dataset quality output must remain outside the repository")


def _sign(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("M4 quality analysis encountered a non-finite label")
    if value < 0:
        return "negative"
    if value > 0:
        return "positive"
    return "zero"


def _distribution(counter: Mapping[str, int]) -> dict[str, int]:
    return {
        "negative": counter.get("negative", 0),
        "zero": counter.get("zero", 0),
        "positive": counter.get("positive", 0),
    }


def _percentile(sorted_values: Sequence[int], percentile: float) -> int:
    if not sorted_values:
        return 0
    return sorted_values[round((len(sorted_values) - 1) * percentile)]


def _summarize_records(
    records: Iterable[Mapping[str, object]],
    *,
    behavior_ids: Sequence[str],
    acceptance_behavior_ids: Sequence[str],
    splits: Sequence[str] = SPLITS,
    minimum_rows: int = 300_000,
    minimum_groups: int = 50_000,
) -> dict[str, object]:
    candidate_counts: dict[str, Counter[str]] = defaultdict(Counter)
    selected_counts: dict[str, Counter[str]] = defaultdict(Counter)
    group_sizes: Counter[str] = Counter()
    group_selected: Counter[str] = Counter()
    scenario_splits: dict[str, set[str]] = defaultdict(set)
    mask_counts: dict[str, Counter[str]] = {name: Counter() for name in MASK_NAMES}
    event_context_counts: Counter[str] = Counter()
    event_token_counts: Counter[int] = Counter()
    axis_counts: dict[str, Counter[str]] = defaultdict(Counter)
    resolver_counts: Counter[str] = Counter()
    row_count = 0

    for record in records:
        split = str(record["split"])
        behavior_id = str(record["behavior_id"])
        decision_group_id = str(record["decision_group_id"])
        scenario_group_id = str(record["scenario_group_id"])
        selected = bool(record["selected_by_teacher"])
        example = json.loads(str(record["example_json"]))
        feature = cast(dict[str, Any], example["feature"])
        label = cast(dict[str, Any], example["label"])
        masks = cast(dict[str, Any], feature["masks"])
        prediction = cast(dict[str, Any], label["prediction"])

        candidate_counts[behavior_id][split] += 1
        if selected:
            selected_counts[behavior_id][split] += 1
            group_selected[decision_group_id] += 1
        group_sizes[decision_group_id] += 1
        scenario_splits[scenario_group_id].add(split)
        for name in MASK_NAMES:
            mask_counts[name][str(bool(masks[name])).lower()] += 1
        event_mask = cast(list[bool], masks["event_mask"])
        token_count = sum(event_mask)
        event_token_counts[token_count] += 1
        event_context_counts["present" if token_count else "absent"] += 1

        for axis, value in cast(dict[str, float], prediction["need_delta_preview"]).items():
            axis_counts[f"need.{axis}"][_sign(float(value))] += 1
        for axis, value in cast(dict[str, float], prediction["actor_mood_delta"]).items():
            axis_counts[f"actor_mood.{axis}"][_sign(float(value))] += 1
        target_mood = cast(dict[str, float] | None, prediction["target_mood_delta"])
        if target_mood is not None:
            for axis, value in target_mood.items():
                axis_counts[f"target_mood.{axis}"][_sign(float(value))] += 1
        relationship = cast(dict[str, float] | None, prediction["relationship_delta_target_to_actor"])
        if relationship is not None:
            for axis, value in relationship.items():
                axis_counts[f"relationship.{axis}"][_sign(float(value))] += 1
        resolver_counts["attempted" if label["resolver_attempted"] else "not_attempted"] += 1
        resolver_result = label["resolver_result"]
        resolver_counts[f"result:{resolver_result if resolver_result is not None else 'NONE'}"] += 1
        row_count += 1

    behavior_candidate_counts = {
        behavior: {split: candidate_counts[behavior][split] for split in splits} for behavior in behavior_ids
    }
    behavior_selected_counts = {
        behavior: {split: selected_counts[behavior][split] for split in splits} for behavior in behavior_ids
    }
    missing_candidate_cells = [
        f"{behavior}:{split}" for behavior in behavior_ids for split in splits if candidate_counts[behavior][split] == 0
    ]
    missing_acceptance_cells = [
        f"{behavior}:{split}"
        for behavior in acceptance_behavior_ids
        for split in splits
        if candidate_counts[behavior][split] == 0
    ]
    missing_selected_behaviors = [behavior for behavior in behavior_ids if not sum(selected_counts[behavior].values())]
    selected_split_warnings = [
        f"{behavior}:{split}" for behavior in behavior_ids for split in splits if selected_counts[behavior][split] == 0
    ]
    low_selected_cells = [
        f"{behavior}:{split}={selected_counts[behavior][split]}"
        for behavior in behavior_ids
        for split in splits
        if 0 < selected_counts[behavior][split] < 50
    ]
    selected_anomalies = sum(value != 1 for value in group_selected.values()) + sum(
        group_id not in group_selected for group_id in group_sizes
    )
    scenario_leakage_count = sum(len(value) != 1 for value in scenario_splits.values())
    sorted_group_sizes = sorted(group_sizes.values())
    mask_dual_state = all(mask_counts[name]["true"] > 0 and mask_counts[name]["false"] > 0 for name in MASK_NAMES)
    gates = {
        "minimum_candidate_rows": row_count >= minimum_rows,
        "minimum_decision_groups": len(group_sizes) >= minimum_groups,
        "all_behaviors_in_every_split": not missing_candidate_cells,
        "acceptance_behaviors_in_every_split": not missing_acceptance_cells,
        "all_behaviors_selected_at_least_once": not missing_selected_behaviors,
        "exactly_one_teacher_selection_per_group": selected_anomalies == 0,
        "scenario_groups_do_not_cross_splits": scenario_leakage_count == 0,
        "all_feature_masks_have_true_and_false_rows": mask_dual_state,
        "event_context_has_present_and_absent_rows": event_context_counts["present"] > 0
        and event_context_counts["absent"] > 0,
    }
    selected_total = sum(sum(values.values()) for values in selected_counts.values())
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "row_count": row_count,
        "decision_group_count": len(group_sizes),
        "scenario_group_count": len(scenario_splits),
        "selection": {
            "selected_row_count": selected_total,
            "positive_rate": round(selected_total / row_count, 9) if row_count else 0.0,
            "group_anomaly_count": selected_anomalies,
            "missing_behavior_splits": selected_split_warnings,
            "low_count_behavior_splits": low_selected_cells,
        },
        "group_size": {
            "minimum": min(sorted_group_sizes, default=0),
            "maximum": max(sorted_group_sizes, default=0),
            "mean": round(row_count / len(group_sizes), 9) if group_sizes else 0.0,
            "p50": _percentile(sorted_group_sizes, 0.50),
            "p95": _percentile(sorted_group_sizes, 0.95),
        },
        "behavior_candidate_counts": behavior_candidate_counts,
        "behavior_selected_counts": behavior_selected_counts,
        "missing_candidate_cells": missing_candidate_cells,
        "missing_acceptance_candidate_cells": missing_acceptance_cells,
        "missing_selected_behaviors": missing_selected_behaviors,
        "mask_counts": {
            name: {"false": values["false"], "true": values["true"]} for name, values in mask_counts.items()
        },
        "event_context": {
            "absent_rows": event_context_counts["absent"],
            "present_rows": event_context_counts["present"],
            "token_count_distribution": {str(key): value for key, value in sorted(event_token_counts.items())},
        },
        "label_axis_sign_counts": {axis: _distribution(values) for axis, values in sorted(axis_counts.items())},
        "resolver_counts": dict(sorted(resolver_counts.items())),
        "scenario_group_leakage_count": scenario_leakage_count,
    }


def analyze_dataset(*, config_path: Path, dataset_root: Path) -> dict[str, object]:
    validation = validate_dataset(dataset_root)
    manifest_path = dataset_root / "dataset-manifest.json"
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    catalog = load_catalog(config_path)
    if collector_state_config_hash(catalog) != manifest.config_hash:
        raise ValueError("M4 quality config hash differs from the dataset manifest")
    acceptance_behaviors = [
        behavior.behavior_id.value for behavior in catalog.behaviors.behaviors if behavior.soft_effect_mask.acceptance
    ]
    try:
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as exc:
        raise RuntimeError("M4 dataset quality analysis requires pyarrow") from exc

    def records() -> Iterable[Mapping[str, object]]:
        columns = [
            "decision_group_id",
            "scenario_group_id",
            "split",
            "behavior_id",
            "selected_by_teacher",
            "example_json",
        ]
        for descriptor in manifest.shards:
            table = cast(Any, pq).read_table(dataset_root / descriptor.relative_path, columns=columns)
            for batch in table.to_batches(max_chunksize=8192):
                yield from cast(list[Mapping[str, object]], batch.to_pylist())

    summary = _summarize_records(
        records(),
        behavior_ids=[behavior.value for behavior in BehaviorId],
        acceptance_behavior_ids=acceptance_behaviors,
    )
    return {
        "schema": QUALITY_SCHEMA,
        "project_name": PROJECT_NAME,
        "generated_at_utc": _utc_now(),
        "dataset_source_commit": manifest.source_commit,
        "analysis_source_commit": _repository_head(),
        "dataset_id": manifest.dataset_id,
        "dataset_manifest_sha256": _sha256(manifest_path),
        "config_hash": manifest.config_hash,
        "m3_catalog_hash": manifest.m3_catalog_hash,
        "strict_validation": validation,
        "acceptance_behavior_ids": acceptance_behaviors,
        **summary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a validated external M4 teacher dataset")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    _ensure_external(arguments.output)
    report = analyze_dataset(config_path=arguments.config, dataset_root=arguments.dataset)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(arguments.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
