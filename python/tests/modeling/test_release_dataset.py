from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from town_core.modeling import release_dataset
from town_core.modeling.features import split_for_scenario_group
from town_core.modeling.release_dataset import (
    DAYS_PER_SEED,
    MAX_PARALLEL_SEED_JOBS,
    MAXIMUM_ROWS_PER_SEED,
    REPOSITORY_ROOT,
    ROWS_PER_SHARD,
    SEEDS,
    _plan,
    produce_release_dataset,
)


def test_release_teacher_matrix_and_group_split_are_frozen() -> None:
    assert _plan() == [
        {
            "job_id": f"teacher_seed_{seed}_60d",
            "seed": seed,
            "days": 60,
            "maximum_rows": 100_000,
            "rows_per_shard": 25_000,
        }
        for seed in (12345, 24680, 97531, 314159, 271828)
    ]
    assert DAYS_PER_SEED == 60
    assert MAXIMUM_ROWS_PER_SEED == 100_000
    assert MAX_PARALLEL_SEED_JOBS == 5
    assert ROWS_PER_SHARD == 25_000
    assert SEEDS == (12345, 24680, 97531, 314159, 271828)
    distribution = Counter(
        split_for_scenario_group(f"m3_seed_{seed}_episode_{episode:03d}") for seed in SEEDS for episode in range(9)
    )
    assert distribution == {"train": 37, "validation": 3, "test": 5}


def test_release_producer_plan_is_external_and_idempotent(tmp_path: Path) -> None:
    first = produce_release_dataset(
        config_path=REPOSITORY_ROOT / "config" / "v0",
        output_root=tmp_path,
        source_commit="a" * 40,
        plan_only=True,
    )
    state_before = (tmp_path / "producer-state.json").read_bytes()
    second = produce_release_dataset(
        config_path=REPOSITORY_ROOT / "config" / "v0",
        output_root=tmp_path,
        source_commit="a" * 40,
        plan_only=True,
    )

    assert first == second == {"completed": False, "planned_jobs": 5, "days_per_seed": 60}
    assert (tmp_path / "producer-state.json").read_bytes() == state_before
    assert not (tmp_path / "producer.lock").exists()

    with pytest.raises(ValueError, match="outside the repository"):
        produce_release_dataset(
            config_path=REPOSITORY_ROOT / "config" / "v0",
            output_root=REPOSITORY_ROOT / "forbidden-m4-dataset",
            source_commit="a" * 40,
            plan_only=True,
        )


def test_parallel_pool_startup_failure_is_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_dataset, "SEEDS", (12345, 24680))
    monkeypatch.setattr(release_dataset, "DAYS_PER_SEED", 1)
    monkeypatch.setattr(release_dataset, "MAXIMUM_ROWS_PER_SEED", 100)
    monkeypatch.setattr(release_dataset, "ROWS_PER_SHARD", 100)

    class UnavailablePool:
        def __init__(self, *, max_workers: int) -> None:
            assert max_workers == 2
            raise PermissionError("process semaphores unavailable")

    monkeypatch.setattr(release_dataset, "ProcessPoolExecutor", UnavailablePool)
    with pytest.raises(PermissionError, match="process semaphores unavailable"):
        produce_release_dataset(
            config_path=REPOSITORY_ROOT / "config" / "v0",
            output_root=tmp_path,
            source_commit="b" * 40,
            max_workers=2,
        )

    state = json.loads((tmp_path / "producer-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "FAILED"
    assert [job["status"] for job in state["jobs"]] == ["FAILED", "FAILED"]
    assert all("PermissionError" in job["attempts"][0]["error"] for job in state["jobs"])
    assert not (tmp_path / "producer.lock").exists()

    with pytest.raises(ValueError, match="max_workers must be in 1..5"):
        produce_release_dataset(
            config_path=REPOSITORY_ROOT / "config" / "v0",
            output_root=tmp_path / "invalid-workers",
            source_commit="a" * 40,
            plan_only=True,
            max_workers=6,
        )
