from __future__ import annotations

from pathlib import Path

from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import load_checkpoint
from town_core.society.replay import replay_society_run
from town_core.society.run import run_society


def test_one_day_run_replay_and_six_hour_resume_match_full_authority_hash(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    baseline_path = tmp_path / "baseline"
    baseline = run_society(
        catalog,
        m3_catalogs,
        days=1,
        seed=12345,
        run_path=baseline_path,
        chunk_minutes=60,
    )
    replay = replay_society_run(baseline_path, output_root=tmp_path)
    six_hour = load_checkpoint(baseline_path / "checkpoints" / "checkpoint_00000360.json")
    resumed = run_society(
        catalog,
        m3_catalogs,
        days=1,
        seed=12345,
        run_path=tmp_path / "resumed",
        chunk_minutes=7,
        resume_checkpoint=six_hour,
    )

    assert replay["match"] is True
    assert replay["actual_final_state_hash"] == baseline["final_state_hash"]
    assert replay["actual_ledger_hash"] == baseline["ledger_hash"]
    assert replay["checkpoint_mismatch_count"] == 0
    assert replay["checked_checkpoint_count"] == 5
    assert resumed["final_state_hash"] == baseline["final_state_hash"]
    assert resumed["final_checkpoint_hash"] == baseline["final_checkpoint_hash"]
    assert resumed["authority_log_hash"] == baseline["authority_log_hash"]
    assert resumed["authority_record_count"] == baseline["authority_record_count"]
    assert resumed["transaction_chain_hash"] == baseline["transaction_chain_hash"]
    assert resumed["ledger_hash"] == baseline["ledger_hash"]
