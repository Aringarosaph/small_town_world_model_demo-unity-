"""Unit coverage for the QA-owned M1 evidence validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m1 import (
    BEHAVIOR_IDS,
    EVIDENCE_SCHEMA,
    INVARIANT_KEYS,
    NEED_NAMES,
    NEGATIVE_PROBES,
    PROJECT_NAME,
    REQUIRED_RUN_DIRECTORIES,
    REQUIRED_RUN_FILES,
    RUN_MATRIX,
    Status,
    _pending_or_missing_sim,
    validate_evidence,
)

pytestmark = [pytest.mark.qa, pytest.mark.m1]

HASH_A = "a" * 64
HASH_B = "b" * 64


def _create_run_tree(root: Path, name: str) -> str:
    run = root / name
    run.mkdir()
    for filename in REQUIRED_RUN_FILES:
        (run / filename).write_text("{}\n", encoding="utf-8")
    for dirname in REQUIRED_RUN_DIRECTORIES:
        (run / dirname).mkdir()
    return name


def _run_document(root: Path, label: str, chunk_minutes: int) -> dict[str, object]:
    run_directory = _create_run_tree(root, f"run-{label}")
    document: dict[str, object] = {
        "label": label,
        "run_directory": run_directory,
        "seed": 12345,
        "chunk_minutes": chunk_minutes,
        "start_minute": 0,
        "end_minute": 4320,
        "tick_count": 4320,
        "skipped_tick_count": 0,
        "duplicated_tick_count": 0,
        "active_agent_ids": ["npc_01"],
        "inactive_actor_activity_count": 0,
        "action_count": 12,
        "decision_count": 12,
        "event_count": 8,
        "committed_transaction_count": 12,
        "state_version_start": 0,
        "state_version_end": 12,
        "illegal_state_count": 0,
        "initial_state_hash": HASH_B,
        "final_state_hash": HASH_A,
        "authority_log_hash": HASH_B,
        "invariants": {key: True for key in INVARIANT_KEYS},
        "need_extrema": {need: {"min": 0.2, "max": 0.9} for need in NEED_NAMES},
        "need_decay_observations": {
            need: {
                "before": 0.8,
                "after": 0.79,
                "elapsed_minutes": 1,
                "behavior_effect_applied": False,
            }
            for need in NEED_NAMES
        },
        "behavior_counts": {behavior_id: 3 for behavior_id in BEHAVIOR_IDS},
    }
    if label == "baseline":
        document["replay"] = {
            "output_directory": _create_run_tree(root, "run-replay"),
            "transaction_count": 12,
            "expected_final_state_hash": HASH_A,
            "actual_final_state_hash": HASH_A,
            "match": True,
            "source_tree_hash_before": HASH_B,
            "source_tree_hash_after": HASH_B,
        }
    return document


def _valid_document(root: Path) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA,
        "project_name": PROJECT_NAME,
        "scenario": {
            "agent_id": "npc_01",
            "seed": 12345,
            "days": 3,
            "start_minute": 0,
            "end_minute": 4320,
            "allowed_behavior_ids": list(BEHAVIOR_IDS),
            "chunk_minutes": [1, 7, 60],
        },
        "runs": [_run_document(root, label, chunk) for label, chunk in RUN_MATRIX.items()],
        "work_probes": {
            "completed": {
                "event_type": "WORK_COMPLETED",
                "completed": True,
                "wage_settlement_count": 1,
                "wage_amount": 12000,
                "wage_after_completion": True,
            },
            "late": {
                "event_type": "WORK_LATE",
                "completed": True,
                "wage_settlement_count": 1,
                "wage_amount": 12000,
                "wage_after_completion": True,
            },
            "missed": {
                "event_type": "WORK_MISSED",
                "completed": False,
                "wage_settlement_count": 0,
                "wage_amount": 0,
                "wage_after_completion": False,
            },
        },
        "negative_probes": [
            {
                "name": name,
                "accepted": False,
                "rejection_code": f"REJECTED_{name.upper()}",
                "state_hash_before": HASH_A,
                "state_hash_after": HASH_A,
                **({"ledger_hash_before": HASH_B, "ledger_hash_after": HASH_B} if name == "event_mutation" else {}),
            }
            for name in NEGATIVE_PROBES
        ],
        "cli_contract": {
            "run_headless_exit_code": 0,
            "replay_exit_code": 0,
            "run_headless_summary_machine_readable": True,
            "replay_summary_machine_readable": True,
            "invalid_input_nonzero": True,
        },
    }


def _write_evidence(root: Path, document: dict[str, object]) -> Path:
    path = root / "m1_qa_evidence.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_valid_m1_evidence_passes_all_checks(tmp_path: Path) -> None:
    repository_root = find_repository_root(Path(__file__))
    findings = validate_evidence(_write_evidence(tmp_path, _valid_document(tmp_path)), repository_root)

    assert findings
    assert all(finding.status is Status.PASS for finding in findings)


def test_determinism_failure_names_the_run_matrix(tmp_path: Path) -> None:
    repository_root = find_repository_root(Path(__file__))
    document = _valid_document(tmp_path)
    runs = cast(list[dict[str, object]], document["runs"])
    runs[-1]["final_state_hash"] = "c" * 64

    findings = validate_evidence(_write_evidence(tmp_path, document), repository_root)

    determinism = next(finding for finding in findings if finding.code == "M1_DETERMINISM")
    assert determinism.status is Status.FAIL
    assert "different initial/final state or ordered-log hashes" in determinism.message


def test_negative_probe_must_reject_without_mutation(tmp_path: Path) -> None:
    repository_root = find_repository_root(Path(__file__))
    document = _valid_document(tmp_path)
    probes = cast(list[dict[str, object]], document["negative_probes"])
    probes[0]["accepted"] = True
    probes[1]["state_hash_after"] = "c" * 64

    findings = validate_evidence(_write_evidence(tmp_path, document), repository_root)

    rejection = next(finding for finding in findings if finding.code == "M1_INVALID_STATE_REJECTIONS")
    assert rejection.status is Status.FAIL
    assert "was accepted" in rejection.message
    assert "mutated authority state" in rejection.message


def test_replay_must_not_mutate_source_run(tmp_path: Path) -> None:
    repository_root = find_repository_root(Path(__file__))
    document = _valid_document(tmp_path)
    runs = cast(list[dict[str, object]], document["runs"])
    baseline = runs[0]
    replay = cast(dict[str, object], baseline["replay"])
    replay["source_tree_hash_after"] = "c" * 64

    findings = validate_evidence(_write_evidence(tmp_path, document), repository_root)

    result = next(finding for finding in findings if finding.code == "M1_REPLAY")
    assert result.status is Status.FAIL
    assert "mutated the source run" in result.message


def test_run_artifacts_must_stay_outside_repository(tmp_path: Path) -> None:
    repository_root = find_repository_root(Path(__file__))
    document = _valid_document(tmp_path)
    runs = cast(list[dict[str, object]], document["runs"])
    runs[-1]["run_directory"] = repository_root.as_posix()

    findings = validate_evidence(_write_evidence(tmp_path, document), repository_root)

    artifacts = next(finding for finding in findings if finding.code == "M1_RUN_ARTIFACTS")
    assert artifacts.status is Status.FAIL
    assert "must be relative" in artifacts.message


def test_absent_sim_is_readable_pending(tmp_path: Path) -> None:
    findings = _pending_or_missing_sim(tmp_path, require_sim=False)

    assert findings is not None
    assert [(finding.status, finding.code) for finding in findings] == [(Status.PENDING, "M1_SIM_NOT_INTEGRATED")]


def test_final_gate_converts_absent_sim_to_failure(tmp_path: Path) -> None:
    findings = _pending_or_missing_sim(tmp_path, require_sim=True)

    assert findings is not None
    assert findings[0].status is Status.FAIL


def test_partial_sim_integration_is_never_pending(tmp_path: Path) -> None:
    (tmp_path / "python/town_core/simulation").mkdir(parents=True)

    findings = _pending_or_missing_sim(tmp_path, require_sim=False)

    assert findings is not None
    assert [(finding.status, finding.code) for finding in findings] == [(Status.FAIL, "M1_SIM_ADAPTER_INCOMPLETE")]
