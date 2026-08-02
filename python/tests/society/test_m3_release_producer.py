from __future__ import annotations

import json
import platform
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from town_core.domain.enums import BehaviorId
from town_core.society import m3_release_producer as producer

SOURCE_COMMIT = "a" * 40
REFERENCE_MACHINE = "unit-test host"


@pytest.fixture(autouse=True)
def _release_source_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(producer, "_repository_head", lambda: SOURCE_COMMIT)
    monkeypatch.setattr(producer, "_repository_is_clean", lambda: True)


def _fake_summary(run_path: Path, job: Mapping[str, Any]) -> dict[str, Any]:
    run_path.mkdir(parents=True)
    digest = f"{int(job['seed']):064x}"[-64:]
    summary: dict[str, Any] = {
        "run_id": run_path.name,
        "seed": int(job["seed"]),
        "tick_count": int(job["days"]) * 1440,
        "final_state_hash": digest,
        "final_checkpoint_hash": digest,
        "ledger_hash": digest,
        "transaction_chain_hash": digest,
        "authority_log_hash": digest,
        "authority_record_count": 1,
        "invariants": {"passed": True, "violations": []},
    }
    (run_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return summary


def _fake_replay(run_path: Path) -> dict[str, Any]:
    summary = json.loads((run_path / "summary.json").read_text(encoding="utf-8"))
    return {
        "actual_final_state_hash": summary["final_state_hash"],
        "actual_final_checkpoint_hash": summary["final_checkpoint_hash"],
        "actual_ledger_hash": summary["ledger_hash"],
        "actual_authority_log_hash": summary["authority_log_hash"],
        "checkpoint_mismatch_count": 0,
        "checked_checkpoint_count": 1,
        "source_run_mutation_count": 0,
        "match": True,
    }


def _fake_observation(catalog: object, run_path: Path) -> dict[str, Any]:
    del catalog
    return {
        "run_id": run_path.name,
        "behavior_counts": {behavior.value: 1 for behavior in BehaviorId},
        "agent_liveness": [
            {
                "agent_id": f"npc_{index:02d}",
                "enabled": True,
                "scheduled": True,
                "decision_count": 1,
                "settled_action_count": 1,
                "max_idle_with_legal_non_idle_minutes": 0,
                "work_bound_violation_count": 0,
            }
            for index in range(1, 11)
        ],
        "household_economy": [
            {
                "household_id": f"household_{suffix}",
                "initial_money": 100,
                "final_money": 100,
                "unique_wages": 0,
                "grocery_charges": 0,
                "cafe_charges": 0,
                "bar_charges": 0,
                "initial_food": 10,
                "final_food": 10,
                "grocery_purchases": 0,
                "completed_home_meals": 0,
                "failed_or_cancelled_charge_count": 0,
                "duplicate_settlement_count": 0,
                "minimum_money": 100,
                "minimum_food": 10,
                "resource_recovery_within_workweek": True,
            }
            for suffix in "abcd"
        ],
        "relationship": {
            "edge_count": 90,
            "out_of_range_count": 0,
            "wrong_direction_count": 0,
            "untraced_delta_count": 0,
            "boundary_violation_count": 0,
        },
        "knowledge": {"acquisition_counts": {}, "shared_event_count": 1, "shared_without_speaker_knowledge_count": 0},
        "joint": {
            "joint_action_count": 1,
            "invitation_accepted_count": 1,
            "invitation_rejected_count": 1,
            "split_action_count": 0,
            "terminal_phase_counts": {"COMPLETED": 1},
        },
        "pathology": {
            "max_candidates_per_agent": 12,
            "max_decision_batch": 10,
            "reservation_leak_count": 0,
            "slot_conflict_count": 0,
            "permanent_idle_agent_count": 0,
            "work_bound_violation_count": 0,
            "max_recoverable_zero_need_minutes": 0,
            "unrecovered_household_count": 0,
            "max_all_households_money_low_streak_days": 0.0,
            "relationship_boundary_violation_count": 0,
            "max_events_per_game_day": 10,
            "event_growth_linear": True,
            "untyped_event_count": 0,
            "duplicate_semantic_event_count": 0,
        },
        "performance": {
            "wall_seconds": 1.0,
            "tick_p99_ms": 1.0,
            "decision_batch_p95_ms": 1.0,
            "peak_rss_bytes": 1,
            "rss_collection_method": "test",
            "post_warmup_rss_slope_bytes_per_game_day": 0.0,
            "platform": "Darwin-test",
            "python_version": "3.12.0",
        },
    }


def _arguments(tmp_path: Path) -> dict[str, Any]:
    return {
        "config_path": producer.REPOSITORY_ROOT / "config" / "v0",
        "output_root": tmp_path,
        "source_commit": SOURCE_COMMIT,
        "reference_machine": REFERENCE_MACHINE,
    }


def test_release_job_plan_is_exact_fixed_matrix() -> None:
    plan = producer._job_plan()
    soak = [(cast(int, item["days"]), cast(int, item["seed"])) for item in plan if item["role"] == "SOAK"]

    assert soak == [*((7, seed) for seed in producer.SEEDS_7_DAY), *((30, seed) for seed in producer.SEEDS_30_DAY)]
    assert len(plan) == 11
    assert {(cast(int, item["chunk_minutes"]), item["role"]) for item in plan} == {
        (1, "CANONICAL_CHUNK"),
        (7, "CANONICAL_CHUNK"),
        (60, "CANONICAL_REPEAT"),
        (60, "SOAK"),
    }


def test_release_plan_is_external_idempotent_and_recovers_dead_local_lock(tmp_path: Path) -> None:
    first = producer.produce_release_evidence(**_arguments(tmp_path), plan_only=True)
    state_before = (tmp_path / "producer-state.json").read_bytes()
    (tmp_path / "producer.lock").write_text(
        json.dumps({"pid": 999_999_999, "host": platform.node(), "started_at_utc": "2026-08-03T00:00:00Z"}),
        encoding="utf-8",
    )
    second = producer.produce_release_evidence(**_arguments(tmp_path), plan_only=True)

    assert first == second == {"completed": False, "status": "PENDING", "planned_jobs": 11}
    assert (tmp_path / "producer-state.json").read_bytes() == state_before
    assert not (tmp_path / "producer.lock").exists()

    with pytest.raises(ValueError, match="outside the repository"):
        producer.produce_release_evidence(
            **{**_arguments(tmp_path), "output_root": producer.REPOSITORY_ROOT / "forbidden-release-output"},
            plan_only=True,
        )


def test_release_cli_is_machine_readable_for_plan_and_invalid_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "--config",
        str(producer.REPOSITORY_ROOT / "config" / "v0"),
        "--output-root",
        str(tmp_path),
        "--source-commit",
        SOURCE_COMMIT,
        "--reference-machine",
        REFERENCE_MACHINE,
        "--plan-only",
    ]
    assert producer.main(arguments) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["planned_jobs"] == 11
    arguments[arguments.index(SOURCE_COMMIT)] = "deadbeef"
    assert producer.main(arguments) == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["completed"] is False
    assert rejected["error_type"] == "ValueError"


def test_release_producer_resumes_without_repeating_completed_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(config_path: Path, run_path: Path, job: Mapping[str, Any]) -> dict[str, Any]:
        del config_path
        calls.append(str(job["job_id"]))
        return _fake_summary(run_path, job)

    monkeypatch.setattr(producer, "_invoke_production_run", fake_run)
    monkeypatch.setattr(producer, "verify_society_run", _fake_replay)
    first = producer.produce_release_evidence(**_arguments(tmp_path), max_new_runs=2)
    second = producer.produce_release_evidence(**_arguments(tmp_path), max_new_runs=1)
    state = json.loads((tmp_path / "producer-state.json").read_text(encoding="utf-8"))

    assert first["completed"] is False and first["completed_jobs"] == 2
    assert second["completed"] is False and second["completed_jobs"] == 3
    assert calls == [str(item["job_id"]) for item in producer._job_plan()[:3]]
    assert [item["status"] for item in state["jobs"][:3]] == ["COMPLETED"] * 3
    assert all(len(item["attempts"]) == 1 for item in state["jobs"][:3])


def test_release_producer_writes_only_seven_sim_artifacts_and_revalidates_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        producer, "_invoke_production_run", lambda config_path, run_path, job: _fake_summary(run_path, job)
    )
    monkeypatch.setattr(producer, "verify_society_run", _fake_replay)

    monkeypatch.setattr(producer, "_run_observation", _fake_observation)
    first = producer.produce_release_evidence(**_arguments(tmp_path))
    second = producer.produce_release_evidence(**_arguments(tmp_path))
    bundle = json.loads((tmp_path / "bundle-manifest.json").read_text(encoding="utf-8"))

    assert first["completed"] is True and second["completed"] is True
    assert set(bundle["artifacts"]) == set(producer.ARTIFACT_SCHEMAS)
    assert bundle["schema"] == producer.BUNDLE_SCHEMA
    authority = json.loads((tmp_path / bundle["artifacts"]["authority_evidence"]["path"]).read_text(encoding="utf-8"))
    assert len(authority["qa_matrix_projection"]["soak_runs"]) == 8
    assert authority["qa_matrix_projection"]["determinism"]["driver_chunks_minutes"] == [1, 7, 60]
    unsupported = {item["qa_field"] for item in authority["not_produced_qa_fields"]}
    assert "matrices.knowledge_permissions.unknown_share_rejected" in unsupported
    assert "matrices.joint_action.cancel_release|failure_release|timeout_release" in unsupported
    assert "stwm.qa.m3-acceptance-evidence/v1" not in {
        json.loads((tmp_path / descriptor["path"]).read_text(encoding="utf-8"))["schema"]
        for descriptor in bundle["artifacts"].values()
    }
    assert len(list((tmp_path / "runs").glob("*/attempt_0001"))) == 11
    authority_path = tmp_path / bundle["artifacts"]["authority_evidence"]["path"]
    authority_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest differs"):
        producer.produce_release_evidence(**_arguments(tmp_path))
