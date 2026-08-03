from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society import m3_release_producer as producer
from town_core.society.m3_targeted_evidence import execute_invitation_acceptance_probe

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
        "knowledge": {
            "acquisition_counts": {"DIRECT_PARTICIPANT": 1, "WITNESSED": 1, "TOLD": 1},
            "shared_event_count": 1,
            "shared_without_speaker_knowledge_count": 0,
            "player_told_record_count": 0,
            "epistemic_graph_count": 0,
        },
        "joint": {
            "joint_action_count": 0,
            "invitation_accepted_count": 0,
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


def test_acceptance_projection_requires_transactional_observation_not_only_pass_record(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    assertion_count, observation = execute_invitation_acceptance_probe(catalog, m3_catalogs)
    result: dict[str, object] = {
        "status": "PASS",
        "test_ids": [
            "python/tests/society/test_m3_targeted_evidence.py::test_sim_targeted_invitation_acceptance_probe"
        ],
        "assertion_count": assertion_count,
    }

    assert producer._targeted_invitation_acceptance_covered(result, observation)
    for key, invalid in (
        ("invitation_accepted_event_count", 0),
        ("joint_authority", "UNKNOWN"),
        ("joint_terminal_phase", "FAILED"),
        ("reservation_remnant_count", 1),
        ("replay_match", False),
        ("deterministic_draw", 1.0),
    ):
        assert not producer._targeted_invitation_acceptance_covered(result, {**observation, key: invalid})


def test_semantic_event_occurrences_distinguish_rearmed_threshold_episodes() -> None:
    threshold_event: dict[str, Any] = {
        "event_id": "event_00000001",
        "event_type": "NEED_CRISIS",
        "game_minute": 100,
        "source_action_id": None,
        "actor_ids": ["npc_03"],
        "affected_agent_ids": ["npc_03"],
        "payload": {"need": "hunger", "value": 0.1, "threshold": 0.1},
    }
    later_emission = {**threshold_event, "event_id": "event_00000002", "game_minute": 200}
    action_event = {**threshold_event, "source_action_id": "action_00000001"}
    delayed_action_duplicate = {**action_event, "event_id": "event_00000004", "game_minute": 101}
    tracker = producer._SemanticEventEpisodeTracker(
        active_need_crises={"npc_03": []},
        low_resource_flags={},
    )

    first_key = tracker.observe(threshold_event)
    assert tracker.observe(later_emission) == first_key
    tracker.apply_patch({"active_need_crises": {"npc_03": []}})
    assert tracker.observe(later_emission) != first_key
    food_event = {
        **threshold_event,
        "event_type": "HOUSEHOLD_FOOD_LOW",
        "actor_ids": ["npc_01", "npc_02"],
        "affected_agent_ids": ["npc_01", "npc_02"],
        "payload": {"household_id": "household_a", "food_units": 0, "money": 50000},
    }
    first_food_key = tracker.observe(food_event)
    assert tracker.observe({**food_event, "game_minute": 300}) == first_food_key
    tracker.apply_patch({"low_resource_flags": {"household_a": []}})
    assert tracker.observe({**food_event, "game_minute": 300}) != first_food_key
    assert producer._semantic_event_occurrence_key(action_event) == producer._semantic_event_occurrence_key(
        delayed_action_duplicate
    )


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


def test_production_child_failure_preserves_machine_readable_error_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=json.dumps(
                {
                    "completed": False,
                    "error_type": "ValueError",
                    "error": "M3 central Resolver rejected idle fallback: npc_07",
                }
            ),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="production run-society failed: ValueError: M3 central Resolver rejected idle fallback: npc_07",
    ):
        producer._invoke_production_run(
            producer.REPOSITORY_ROOT / "config" / "v0",
            tmp_path / "run",
            producer._job_plan()[0],
        )


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
    assert authority["qa_matrix_projection"]["knowledge_permissions"] == {
        "direct_participant_covered": True,
        "witnessed_covered": True,
        "told_covered": True,
        "unknown_share_rejected": True,
        "speaker_known_event_only": True,
        "player_told_record_count": 0,
        "epistemic_graph_count": 0,
    }
    assert authority["qa_matrix_projection"]["joint_action"] == {
        "invited_activity_ids": ["watch_tv", "eat_at_cafe", "drink_at_bar", "walk_in_park", "sit_in_park"],
        "central_resolver": True,
        "acceptance_covered": True,
        "rejection_covered": True,
        "participant_exclusivity": True,
        "atomic_reservations": True,
        "cancel_release": True,
        "failure_release": True,
        "timeout_release": True,
        "split_action_count": 0,
        "replay_match": True,
    }
    assert set(authority["qa_probe_evidence"]) == {
        "knowledge_unknown_share_rejected",
        "joint_action_cancel_release",
        "joint_action_failure_release",
        "joint_action_timeout_release",
    }
    assert all(
        set(record) == {"status", "test_ids", "assertion_count"}
        and record["status"] == "PASS"
        and record["test_ids"]
        and record["assertion_count"] > 0
        for record in authority["qa_probe_evidence"].values()
    )
    assert set(authority["sim_targeted_probe_evidence"]) == {"joint_action_invitation_acceptance"}
    acceptance_record = authority["sim_targeted_probe_evidence"]["joint_action_invitation_acceptance"]
    assert set(acceptance_record) == {"status", "test_ids", "assertion_count"}
    assert acceptance_record["status"] == "PASS"
    assert acceptance_record["test_ids"] == [
        "python/tests/society/test_m3_targeted_evidence.py::test_sim_targeted_invitation_acceptance_probe"
    ]
    assert acceptance_record["assertion_count"] > 0
    acceptance_observation = authority["targeted_probe_observations"]["joint_action_invitation_acceptance"]
    assert acceptance_observation["invitation_accepted_event_count"] == 1
    assert acceptance_observation["joint_authority"] == "CENTRAL_RESOLVER"
    assert acceptance_observation["joint_terminal_phase"] == "COMPLETED"
    assert acceptance_observation["reservation_remnant_count"] == 0
    assert acceptance_observation["replay_match"] is True
    assert authority["joint_action_observation"]["invitation_accepted_count"] == 0
    unsupported = {item["qa_field"] for item in authority["not_produced_qa_fields"]}
    assert "matrices.knowledge_permissions.unknown_share_rejected" not in unsupported
    assert "matrices.joint_action.cancel_release|failure_release|timeout_release" not in unsupported
    behavior_path = tmp_path / bundle["artifacts"]["behavior_matrix_report"]["path"]
    behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    assert len(behavior["cases"]) == 22
    assert [item["behavior_id"] for item in behavior["cases"]] == [item.value for item in BehaviorId]
    expected_probe_keys = {
        "legal_candidate",
        "illegal_candidate",
        "hard_cost_preview",
        "resolver_accept",
        "resolver_reject",
        "reservation_and_lifecycle",
        "allowed_effects",
        "authoritative_replay",
    }
    assert all(set(item["sim_targeted_probe_results"]) == expected_probe_keys for item in behavior["cases"])
    assert all(
        set(record) == {"status", "test_ids", "assertion_count"}
        and record["status"] == "PASS"
        and record["test_ids"]
        and record["assertion_count"] > 0
        for item in behavior["cases"]
        for record in item["sim_targeted_probe_results"].values()
    )
    assert all(item["unity_presentation"] is None for item in behavior["cases"])
    assert "stwm.qa.m3-acceptance-evidence/v1" not in {
        json.loads((tmp_path / descriptor["path"]).read_text(encoding="utf-8"))["schema"]
        for descriptor in bundle["artifacts"].values()
    }
    assert len(list((tmp_path / "runs").glob("*/attempt_0001"))) == 11
    authority_path = tmp_path / bundle["artifacts"]["authority_evidence"]["path"]
    authority_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest differs"):
        producer.produce_release_evidence(**_arguments(tmp_path))
