"""Resumable serial producer for the frozen M4 raw teacher dataset matrix."""

from __future__ import annotations

import argparse
import json
import os
import platform
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from town_core.domain.enums import BehaviorId
from town_core.modeling.contracts import DatasetManifest, DatasetShard
from town_core.modeling.dataset import generate_dataset
from town_core.modeling.validate_dataset import validate_dataset

PROJECT_NAME = "Small Town World Model（STWM）"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STATE_SCHEMA = "stwm.model.release-dataset-producer-state/v1"
SUMMARY_SCHEMA = "stwm.model.release-dataset-summary/v1"
SEEDS = (12345, 24680, 97531, 314159, 271828)
DAYS_PER_SEED = 60
MAXIMUM_ROWS_PER_SEED = 100_000
ROWS_PER_SHARD = 25_000


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _plan() -> list[dict[str, object]]:
    return [
        {
            "job_id": f"teacher_seed_{seed}_60d",
            "seed": seed,
            "days": DAYS_PER_SEED,
            "maximum_rows": MAXIMUM_ROWS_PER_SEED,
            "rows_per_shard": ROWS_PER_SHARD,
        }
        for seed in SEEDS
    ]


def _new_state(source_commit: str) -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema": STATE_SCHEMA,
        "project_name": PROJECT_NAME,
        "source_commit": source_commit,
        "created_at_utc": now,
        "updated_at_utc": now,
        "status": "PENDING",
        "jobs": [{**job, "status": "PENDING", "attempts": []} for job in _plan()],
    }


def _validate_state(state: Mapping[str, Any], source_commit: str) -> None:
    if state.get("schema") != STATE_SCHEMA or state.get("source_commit") != source_commit:
        raise ValueError("M4 release dataset producer state provenance differs")
    observed = [
        {key: item[key] for key in ("job_id", "seed", "days", "maximum_rows", "rows_per_shard")}
        for item in state.get("jobs", [])
    ]
    if observed != _plan():
        raise ValueError("M4 release dataset producer plan differs from the frozen matrix")


def _acquire_lock(path: Path) -> None:
    document = {"pid": os.getpid(), "host": platform.node(), "started_at_utc": _utc_now()}
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            same_host = existing.get("host") == platform.node()
            pid = int(existing["pid"])
            os.kill(pid, 0)
        except ProcessLookupError:
            if same_host:
                path.unlink()
                return _acquire_lock(path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
        raise RuntimeError("another M4 release dataset producer owns this output root") from exc
    try:
        os.write(descriptor, json.dumps(document, sort_keys=True).encode("utf-8"))
    finally:
        os.close(descriptor)


def _load_or_create_state(root: Path, source_commit: str) -> dict[str, Any]:
    state_path = root / "producer-state.json"
    if state_path.exists():
        value = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("M4 release dataset producer state must be an object")
        _validate_state(value, source_commit)
        return value
    state = _new_state(source_commit)
    _atomic_json(state_path, state)
    return state


def _aggregate(root: Path, state: Mapping[str, Any]) -> DatasetManifest:
    manifests: list[tuple[str, DatasetManifest]] = []
    for job in state["jobs"]:
        if not isinstance(job, dict) or job.get("status") != "COMPLETED":
            raise ValueError("M4 release aggregation requires every seed job to be complete")
        dataset_id = str(job["dataset_id"])
        child_root = root / "runs" / dataset_id
        validate_dataset(child_root)
        child = DatasetManifest.model_validate_json((child_root / "dataset-manifest.json").read_text(encoding="utf-8"))
        manifests.append((dataset_id, child))
    first = manifests[0][1]
    if any(
        (item.source_commit, item.config_hash, item.m3_catalog_hash, item.vocabulary)
        != (first.source_commit, first.config_hash, first.m3_catalog_hash, first.vocabulary)
        for _, item in manifests[1:]
    ):
        raise ValueError("M4 seed dataset provenance or vocabulary differs")
    shards: list[DatasetShard] = []
    split_counts: Counter[str] = Counter()
    behavior_counts: Counter[BehaviorId] = Counter()
    row_count = 0
    decision_group_count = 0
    for dataset_id, manifest in manifests:
        row_count += manifest.row_count
        decision_group_count += manifest.decision_group_count
        split_counts.update(manifest.split_counts)
        behavior_counts.update(manifest.behavior_counts)
        for descriptor in manifest.shards:
            shards.append(
                descriptor.model_copy(
                    update={
                        "shard_id": f"shard_{len(shards):05d}",
                        "relative_path": f"runs/{dataset_id}/{descriptor.relative_path}",
                    }
                )
            )
    return DatasetManifest(
        dataset_id="m4_teacher_release_raw_v1",
        status="COMPLETED",
        source_commit=first.source_commit,
        config_hash=first.config_hash,
        m3_catalog_hash=first.m3_catalog_hash,
        seeds=list(SEEDS),
        max_rows_per_shard=ROWS_PER_SHARD,
        decision_group_count=decision_group_count,
        row_count=row_count,
        split_counts={
            "train": split_counts["train"],
            "validation": split_counts["validation"],
            "test": split_counts["test"],
        },
        behavior_counts={behavior: behavior_counts[behavior] for behavior in BehaviorId},
        shards=shards,
        vocabulary=first.vocabulary,
        started_at_utc=str(state["created_at_utc"]),
        completed_at_utc=_utc_now(),
    )


def produce_release_dataset(
    *,
    config_path: Path,
    output_root: Path,
    source_commit: str,
    plan_only: bool = False,
) -> dict[str, object]:
    root = output_root.resolve()
    repository = REPOSITORY_ROOT.resolve()
    if root == repository or repository in root.parents:
        raise ValueError("M4 release dataset output must remain outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "producer.lock"
    _acquire_lock(lock_path)
    try:
        state = _load_or_create_state(root, source_commit)
        if plan_only:
            return {"completed": False, "planned_jobs": len(_plan()), "days_per_seed": DAYS_PER_SEED}
        state["status"] = "RUNNING"
        state["updated_at_utc"] = _utc_now()
        _atomic_json(root / "producer-state.json", state)
        runs_root = root / "runs"
        runs_root.mkdir(exist_ok=True)
        jobs = cast(list[dict[str, Any]], state["jobs"])
        for job in jobs:
            if job["status"] == "COMPLETED":
                validate_dataset(runs_root / str(job["dataset_id"]))
                continue
            attempt_number = len(job["attempts"]) + 1
            dataset_id = f"{job['job_id']}_attempt_{attempt_number:02d}"
            attempt = {"attempt": attempt_number, "dataset_id": dataset_id, "started_at_utc": _utc_now()}
            job["attempts"].append(attempt)
            job["status"] = "RUNNING"
            state["updated_at_utc"] = _utc_now()
            _atomic_json(root / "producer-state.json", state)
            try:
                manifest = generate_dataset(
                    config_path=config_path,
                    output_root=runs_root,
                    dataset_id=dataset_id,
                    seed=int(job["seed"]),
                    maximum_rows=int(job["maximum_rows"]),
                    maximum_minutes=int(job["days"]) * 1440,
                    rows_per_shard=int(job["rows_per_shard"]),
                    source_commit=source_commit,
                )
                validation = validate_dataset(runs_root / dataset_id)
            except Exception as exc:
                attempt.update(
                    {"status": "FAILED", "completed_at_utc": _utc_now(), "error": f"{type(exc).__name__}: {exc}"}
                )
                job["status"] = "FAILED"
                state["status"] = "FAILED"
                state["updated_at_utc"] = _utc_now()
                _atomic_json(root / "producer-state.json", state)
                raise
            attempt.update(
                {
                    "status": "COMPLETED",
                    "completed_at_utc": _utc_now(),
                    "row_count": manifest.row_count,
                    "decision_group_count": manifest.decision_group_count,
                    "manifest_sha256": validation["manifest_sha256"],
                }
            )
            job["status"] = "COMPLETED"
            job["dataset_id"] = dataset_id
            state["updated_at_utc"] = _utc_now()
            _atomic_json(root / "producer-state.json", state)
        aggregate = _aggregate(root, state)
        _atomic_json(
            root / "dataset-manifest.json", aggregate.model_dump(mode="json", exclude_none=False, by_alias=True)
        )
        validation = validate_dataset(root)
        summary = {
            "schema": SUMMARY_SCHEMA,
            "project_name": PROJECT_NAME,
            "source_commit": source_commit,
            "passed": True,
            "matrix": _plan(),
            "validation": validation,
        }
        _atomic_json(root / "release-summary.json", summary)
        state["status"] = "COMPLETED"
        state["updated_at_utc"] = _utc_now()
        state["aggregate_manifest_sha256"] = validation["manifest_sha256"]
        _atomic_json(root / "producer-state.json", state)
        return summary
    finally:
        lock_path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce the resumable M4 raw teacher dataset matrix")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--plan-only", action="store_true")
    arguments = parser.parse_args(argv)
    result = produce_release_dataset(
        config_path=arguments.config,
        output_root=arguments.output_root,
        source_commit=arguments.source_commit,
        plan_only=arguments.plan_only,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
