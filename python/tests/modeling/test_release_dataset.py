from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from town_core.modeling.features import split_for_scenario_group
from town_core.modeling.release_dataset import (
    DAYS_PER_SEED,
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
