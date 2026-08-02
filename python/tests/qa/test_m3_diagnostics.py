"""Regression coverage for the QA-owned M3 readiness and release gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

import tools.diagnostics.check_m3 as m3_diagnostics
from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m3 import (
    AGENT_IDS,
    ARTIFACT_SCHEMAS,
    BEHAVIOR_IDS,
    BEHAVIOR_PROBES,
    EVIDENCE_TEMPLATE,
    HOUSEHOLD_IDS,
    INVITED_ACTIVITY_IDS,
    SEEDS_7_DAY,
    SEEDS_30_DAY,
    Status,
    _validate_m3_protocol_version_policy,
    readiness_document,
    run_checks,
    validate_acceptance_evidence,
    validate_readiness_document,
)
from tools.diagnostics.check_m3 import DiagnosticError as M3DiagnosticError

pytestmark = [pytest.mark.qa, pytest.mark.m3, pytest.mark.m3_fast]


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _artifact_content(name: str, suffix: str, schema: str | None) -> bytes:
    if suffix == ".xml":
        return b'<test-run result="Passed" total="1" passed="1" skipped="0" />\n'
    if suffix == ".jsonl":
        return (json.dumps({"schema": schema, "result": "PASS"}) + "\n").encode()
    if suffix == ".json":
        if name == "full_registry":
            document = {"protocol_version": "0.3.0", "message_type": "asset_registry", "payload": {}}
        else:
            document = {"schema": schema, "result": "PASS"} if schema else {"result": "PASS"}
        return (json.dumps(document) + "\n").encode()
    return f"{name} completed with sanitized PASS result\n".encode()


def _passing_evidence(root: Path, output: Path) -> Path:
    document = _read_json(root / EVIDENCE_TEMPLATE)
    document["source_commit"] = "a" * 40
    gates = cast(dict[str, object], document["gates"])
    for name in gates:
        gates[name] = {"status": "PASS", "details": f"verified real {name} evidence"}

    matrices = cast(dict[str, object], document["matrices"])
    matrices["catalog_surface"] = {
        "npcs": 10,
        "households": 4,
        "locations": 8,
        "behaviors": 22,
        "object_types": 15,
        "relationship_edges": 90,
        "needs": 5,
        "personality_axes": 4,
        "mood_axes": 2,
        "relationship_axes": 4,
    }
    matrices["behavior_coverage"] = [
        {
            "behavior_id": behavior_id,
            "fixture_id": f"m3_behavior_{behavior_id}",
            **dict.fromkeys(BEHAVIOR_PROBES, True),
            "release_soak_occurrence_count": 1,
        }
        for behavior_id in BEHAVIOR_IDS
    ]
    matrices["agent_liveness"] = [
        {
            "agent_id": agent_id,
            "enabled": True,
            "scheduled": True,
            "decision_count": 10,
            "settled_action_count": 8,
            "max_idle_with_legal_non_idle_minutes": 120,
            "work_bound_violation_count": 0,
        }
        for agent_id in AGENT_IDS
    ]
    matrices["household_economy"] = [
        {
            "household_id": household_id,
            "initial_money": 100,
            "final_money": 101,
            "unique_wages": 10,
            "grocery_charges": 2,
            "cafe_charges": 3,
            "bar_charges": 4,
            "initial_food": 10,
            "final_food": 16,
            "grocery_purchases": 1,
            "completed_home_meals": 2,
            "failed_or_cancelled_charge_count": 0,
            "duplicate_settlement_count": 0,
            "minimum_money": 50,
            "minimum_food": 1,
            "resource_recovery_within_workweek": True,
        }
        for household_id in HOUSEHOLD_IDS
    ]
    matrices["relationship_summary"] = {
        "edge_count": 90,
        "out_of_range_count": 0,
        "wrong_direction_count": 0,
        "untraced_delta_count": 0,
        "boundary_epsilon": 0.01,
        "boundary_fraction_limit": 0.8,
        "boundary_streak_days": 7,
        "boundary_violation_count": 0,
    }
    matrices["knowledge_permissions"] = {
        "direct_participant_covered": True,
        "witnessed_covered": True,
        "told_covered": True,
        "unknown_share_rejected": True,
        "speaker_known_event_only": True,
        "player_told_record_count": 0,
        "epistemic_graph_count": 0,
    }
    matrices["joint_action"] = {
        "invited_activity_ids": list(INVITED_ACTIVITY_IDS),
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
    matrices["determinism"] = {
        "canonical_seed": 12345,
        "driver_chunks_minutes": [1, 7, 60],
        "checkpoint_interval_minutes": 360,
        "repeat_final_state_hash_match": True,
        "repeat_ledger_hash_match": True,
        "repeat_authority_log_hash_match": True,
        "chunk_final_state_hash_match": True,
        "chunk_ledger_hash_match": True,
        "chunk_authority_log_hash_match": True,
        "checkpoint_resume_final_state_hash_match": True,
        "checkpoint_resume_ledger_hash_match": True,
        "checkpoint_resume_authority_log_hash_match": True,
        "authoritative_replay_final_state_hash_match": True,
        "authoritative_replay_ledger_hash_match": True,
        "authoritative_replay_authority_log_hash_match": True,
        "checkpoint_resume_mismatch_count": 0,
        "replay_mismatch_count": 0,
        "source_run_mutation_count": 0,
    }
    soak_runs: list[dict[str, object]] = []
    for days, seeds in ((7, SEEDS_7_DAY), (30, SEEDS_30_DAY)):
        for seed in seeds:
            state_hash = hashlib.sha256(f"{days}:{seed}:state".encode()).hexdigest()
            ledger_hash = hashlib.sha256(f"{days}:{seed}:ledger".encode()).hexdigest()
            log_hash = hashlib.sha256(f"{days}:{seed}:authority".encode()).hexdigest()
            soak_runs.append(
                {
                    "days": days,
                    "seed": seed,
                    "status": "PASS",
                    "final_state_hash": state_hash,
                    "ledger_hash": ledger_hash,
                    "authority_log_hash": log_hash,
                    "replay_final_state_hash": state_hash,
                    "replay_ledger_hash": ledger_hash,
                    "replay_authority_log_hash": log_hash,
                    "invariant_violation_count": 0,
                    "artifact": "soak_7_day_report" if days == 7 else "soak_30_day_report",
                }
            )
    matrices["soak_runs"] = soak_runs
    matrices["pathology"] = {
        "max_candidates_per_agent": 12,
        "max_decision_batch": 120,
        "reservation_leak_count": 0,
        "slot_conflict_count": 0,
        "permanent_idle_agent_count": 0,
        "work_bound_violation_count": 0,
        "max_recoverable_zero_need_minutes": 360,
        "unrecovered_household_count": 0,
        "max_all_households_money_low_streak_days": 6.5,
        "relationship_boundary_violation_count": 0,
        "max_events_per_game_day": 1000,
        "event_growth_linear": True,
        "untyped_event_count": 0,
        "duplicate_semantic_event_count": 0,
    }
    matrices["performance"] = {
        "reference_machine": "producer Apple-silicon MacBook Air",
        "os": "macOS",
        "python_version": "3.12.7",
        "rss_collection_method": "resource.getrusage plus sampled process RSS",
        "wall_time_seconds_30_day": 899.0,
        "peak_rss_bytes": 1073741823,
        "post_warmup_rss_slope_bytes_per_game_day": 1048576,
        "decision_batch_p95_ms": 49.9,
        "tick_p99_ms": 99.9,
    }
    matrices["unity"] = {
        "npc_views": 10,
        "locations": 8,
        "object_types": 15,
        "all_animation_semantics_mapped": True,
        "all_props_mapped": True,
        "all_facing_behaviors_supported": True,
        "all_required_slots_navmesh_reachable": True,
        "complete_snapshot_replacement": True,
        "explicit_null_clearing": True,
        "active_action_rebind": True,
        "stale_version_rejection": True,
        "duplicate_slot_claim_count": 0,
        "joint_start_phase_cancel_fail_reconnect": True,
        "debug_ui_read_only": True,
        "debug_ui_complete_trace": True,
        "live_smoke_protocol_version": "0.3.0",
        "editmode_skipped": 0,
        "playmode_skipped": 0,
    }

    descriptors = cast(dict[str, object], document["artifacts"])
    for name, (suffixes, schema) in ARTIFACT_SCHEMAS.items():
        suffix = min(suffixes)
        content = _artifact_content(name, suffix, schema)
        artifact = output / f"{name}{suffix}"
        artifact.write_bytes(content)
        descriptors[name] = {
            "path": artifact.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "redacted": True,
            "schema": schema,
        }
    evidence = output / "m3-acceptance-evidence.json"
    evidence.write_text(json.dumps(document), encoding="utf-8")
    return evidence


def test_default_readiness_reports_only_precise_upstream_pending() -> None:
    root = find_repository_root(Path(__file__))

    findings = run_checks(root)

    assert not [finding for finding in findings if finding.status is Status.FAIL]
    assert {finding.code for finding in findings if finding.status is Status.PENDING} == {
        "M3_PROTOCOL_0_3_PENDING",
        "M3_SHARED_SEMANTIC_MANIFEST_PENDING",
        "M3_SIM_QA_ADAPTER_PENDING",
        "M3_UNITY_EVIDENCE_EXPORTER_PENDING",
        "M3_UNITY_FULL_TOWN_FIXTURE_PENDING",
        "M3_FULL_REGISTRY_EVIDENCE_PENDING",
        "M3_ACCEPTANCE_EVIDENCE_PENDING",
    }


def test_strict_mode_converts_every_pending_to_failure() -> None:
    root = find_repository_root(Path(__file__))

    findings = run_checks(root, require_m3=True)

    assert not [finding for finding in findings if finding.status is Status.PENDING]
    assert len([finding for finding in findings if finding.status is Status.FAIL]) == 7


def test_readiness_document_has_exact_counted_shape() -> None:
    root = find_repository_root(Path(__file__))
    document = readiness_document(root, run_checks(root))

    validate_readiness_document(document)

    summary = cast(dict[str, int], document["summary"])
    assert summary["pending"] == 7
    assert summary["fail"] == 0


def test_m3_protocol_policy_requires_additive_m2_and_m3_profiles() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/version.json")
    compatibility = cast(dict[str, object], document["compatibility"])
    document["protocol_version"] = "0.3.0"
    compatibility["active_m3_acceptance_versions"] = ["0.3.0"]
    compatibility["bootstrap_decodable_versions"] = ["0.3.0", "0.2.0", "0.1.0"]

    _validate_m3_protocol_version_policy(document)
    compatibility["active_m2_acceptance_versions"] = []
    with pytest.raises(M3DiagnosticError, match="active_m2_acceptance_versions"):
        _validate_m3_protocol_version_policy(document)


def test_complete_external_release_evidence_passes(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))

    findings = validate_acceptance_evidence(_passing_evidence(root, tmp_path), root)

    assert [(finding.status, finding.code) for finding in findings] == [(Status.PASS, "M3_ACCEPTANCE_EVIDENCE_VALID")]


@pytest.mark.parametrize(
    ("matrix_name", "field", "invalid_value", "error"),
    [
        ("relationship_summary", "wrong_direction_count", 1, "relationship direction"),
        ("knowledge_permissions", "unknown_share_rejected", False, "knowledge permission"),
        ("joint_action", "split_action_count", 1, "JointAction atomicity"),
        ("determinism", "replay_mismatch_count", 1, "replay_mismatch_count must be zero"),
        ("pathology", "max_events_per_game_day", 1001, "event count exceeded"),
        ("performance", "decision_batch_p95_ms", 50, "p95 was not below"),
        ("unity", "playmode_skipped", 1, "may not contain skipped"),
    ],
)
def test_release_threshold_or_skip_regression_fails(
    tmp_path: Path,
    matrix_name: str,
    field: str,
    invalid_value: object,
    error: str,
) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    matrices = cast(dict[str, object], document["matrices"])
    matrix = cast(dict[str, object], matrices[matrix_name])
    matrix[field] = invalid_value
    evidence.write_text(json.dumps(document), encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert error in findings[0].message


def test_missing_behavior_occurrence_or_economy_conservation_fails(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    matrices = cast(dict[str, object], document["matrices"])
    behaviors = cast(list[dict[str, object]], matrices["behavior_coverage"])
    behaviors[0]["release_soak_occurrence_count"] = 0
    evidence.write_text(json.dumps(document), encoding="utf-8")
    findings = validate_acceptance_evidence(evidence, root)
    assert findings[0].status is Status.FAIL
    assert "never occurred" in findings[0].message

    document = _read_json(_passing_evidence(root, tmp_path))
    matrices = cast(dict[str, object], document["matrices"])
    households = cast(list[dict[str, object]], matrices["household_economy"])
    households[0]["final_money"] = 102
    evidence.write_text(json.dumps(document), encoding="utf-8")
    findings = validate_acceptance_evidence(evidence, root)
    assert findings[0].status is Status.FAIL
    assert "money conservation failed" in findings[0].message


def test_replay_hash_mismatch_fails(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    matrices = cast(dict[str, object], document["matrices"])
    soak_runs = cast(list[dict[str, object]], matrices["soak_runs"])
    soak_runs[0]["replay_final_state_hash"] = "f" * 64
    evidence.write_text(json.dumps(document), encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert "replay final-state hash differs" in findings[0].message


def test_artifact_hash_mismatch_fails(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    artifacts = cast(dict[str, dict[str, object]], document["artifacts"])
    authority_path = tmp_path / cast(str, artifacts["authority_evidence"]["path"])
    authority_path.write_text('{"schema":"tampered"}\n', encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert "bytes/hash do not match" in findings[0].message


def test_repository_guard_rejects_committed_release_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "m3-evidence.json"
    artifact.write_text('{"schema":"stwm.qa.m3-acceptance-evidence/v1"}\n', encoding="utf-8")

    monkeypatch.setattr(m3_diagnostics, "check_sensitive_files", lambda _: [])
    monkeypatch.setattr(m3_diagnostics, "_git_candidates", lambda _: ([artifact.name], None))

    findings = m3_diagnostics.check_repository_guard(tmp_path)

    assert [finding.code for finding in findings if finding.status is Status.FAIL] == [
        "M3_EXTERNAL_ARTIFACT_REPOSITORY_GUARD"
    ]
