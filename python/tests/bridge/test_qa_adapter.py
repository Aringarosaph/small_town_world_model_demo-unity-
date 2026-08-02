from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from town_core.bridge.qa_adapter import (
    EVIDENCE_FILENAME,
    EVIDENCE_SCHEMA,
    TRANSCRIPT_FILENAME,
    TRANSCRIPT_SCHEMA,
    main,
)

pytestmark = pytest.mark.m2

ROOT = Path(__file__).resolve().parents[3]
PROBE_KEYS = {
    "probe_id",
    "connection_generation",
    "before",
    "after",
    "authority_mutation_count",
    "authority_transaction_count",
    "outcome",
    "error_code",
    "transcript_sequences",
}
TRANSCRIPT_KEYS = {
    "schema",
    "sequence",
    "event_type",
    "probe_id",
    "connection_generation",
    "direction",
    "message_id",
    "message_type",
    "state_version",
    "trigger_sequence",
    "authority_before",
    "authority_after",
    "authority_mutation_count",
    "authority_transaction_count",
    "outcome",
    "error_code",
    "envelope",
}


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_cli_exports_real_cancellation_and_reconnect_authority_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "m2-authority"

    exit_code = main(
        [
            "--config",
            str(ROOT / "config" / "v0"),
            "--output-root",
            str(output_root),
            "--agent",
            "npc_01",
            "--seed",
            "12345",
        ]
    )

    cli_result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cli_result == {
        "evidence": EVIDENCE_FILENAME,
        "final_state_hash": cli_result["final_state_hash"],
        "ok": True,
        "passed": True,
        "schema": EVIDENCE_SCHEMA,
        "transcript": TRANSCRIPT_FILENAME,
    }
    evidence_path = output_root / EVIDENCE_FILENAME
    transcript_path = output_root / TRANSCRIPT_FILENAME
    evidence = _load_json(evidence_path)
    transcript_text = transcript_path.read_text(encoding="utf-8")
    transcript = [cast(dict[str, Any], json.loads(line)) for line in transcript_text.splitlines()]

    assert evidence["schema"] == EVIDENCE_SCHEMA
    assert evidence["project_name"] == "Small Town World Model（STWM）"
    assert evidence["scenario"] == {
        "active_agent_id": "npc_01",
        "name": "m2_cancellation_reconnect",
        "seed": 12345,
    }
    assert evidence["catalog_protocol_version"] == "0.1.0"
    assert evidence["negotiated_protocol_version"] == "0.2.0"
    assert evidence["passed"] is True
    assert evidence["transcript"] == {
        "record_count": len(transcript),
        "relative_path": TRANSCRIPT_FILENAME,
        "schema": TRANSCRIPT_SCHEMA,
        "sha256": hashlib.sha256(transcript_text.encode("utf-8")).hexdigest(),
    }
    assert str(ROOT) not in evidence_path.read_text(encoding="utf-8")
    assert str(ROOT) not in transcript_text

    cancellation = evidence["observations"]["cancellation"]
    assert cancellation["direction"] == "unity_to_python"
    assert cancellation["correlation_id_equals_action_id"] is True
    assert cancellation["python_authority_cancel_transaction_count"] == 1
    assert cancellation["unity_direct_authority_mutation_count"] == 0
    assert cancellation["duplicate_same_message_id_is_idempotent"] is True
    assert cancellation["conflicting_same_message_id_rejected_without_mutation"] is True
    assert cancellation["direction_rejected_without_mutation"] is True
    assert cancellation["future_state_version_rejected_without_mutation"] is True
    assert cancellation["stale_exact_current_action_processed"] is True
    assert cancellation["stale_state_message_authority_mutation_count"] == 0
    assert cancellation["late_terminal_message_authority_mutation_count"] == 0
    assert all(set(probe) == PROBE_KEYS for probe in cancellation["probes"].values())
    assert set(cancellation["evidence_refs"]) == {
        key for key, value in cancellation.items() if not isinstance(value, (dict, list))
    }

    authority_inputs = evidence["runtime_evidence"]["authority_inputs"]
    accepted = [item for item in authority_inputs if item["accepted"]]
    assert len(accepted) == 1
    assert accepted[0]["reported_state_version"] < accepted[0]["before"]["state_version"]
    assert accepted[0]["authority_transaction_count"] == 1
    assert accepted[0]["authority_mutation_count"] == 1
    assert len(accepted[0]["transactions"]) == 1
    transaction = accepted[0]["transactions"][0]
    assert transaction["previous_state_hash"] == accepted[0]["before"]["state_hash"]
    assert transaction["committed_state_hash"] == accepted[0]["after"]["state_hash"]

    reconnect = evidence["observations"]["reconnect"]
    assert reconnect["full_hello_and_registry_repeated"] is True
    assert reconnect["new_message_ids"] is True
    assert reconnect["fresh_snapshot_not_older_than_last_acknowledged_version"] is True
    assert reconnect["new_client_ready_before_resume"] is True
    assert reconnect["obsolete_generation_rejected"] is True
    assert reconnect["late_obsolete_generation_authority_mutation_count"] == 0
    assert reconnect["stale_state_message_authority_mutation_count"] == 0
    assert reconnect["fresh_snapshot"]["state_version"] >= reconnect["old_generation_last_acknowledged_state_version"]
    assert reconnect["old_generation"]["generation"] == 1
    assert reconnect["new_generation"]["generation"] == 2
    assert reconnect["old_generation"]["ready_after_ack"] is True
    assert reconnect["new_generation"]["ready_before_ack"] is False
    assert reconnect["new_generation"]["ready_after_ack"] is True
    assert set(reconnect["evidence_refs"]) == {
        key for key, value in reconnect.items() if not isinstance(value, (dict, list))
    }
    assert set(reconnect["old_generation"]["message_ids"]).isdisjoint(reconnect["new_generation"]["message_ids"])
    sessions = evidence["runtime_evidence"]["sessions"]
    assert [item["generation"] for item in sessions] == [1, 2]
    assert sessions[0]["disconnected"] is True
    assert sessions[1]["ready_acknowledged"] is True

    assert transcript
    assert all(set(record) == TRANSCRIPT_KEYS for record in transcript)
    assert [record["sequence"] for record in transcript] == list(range(1, len(transcript) + 1))
    assert {record["event_type"] for record in transcript} == {
        "unity_message_received",
        "python_message_emitted",
        "authority_probe_evaluated",
    }
    cancellation_transaction_lines = [
        record
        for record in transcript
        if record["message_type"] == "movement_cancelled" and record["authority_transaction_count"] == 1
    ]
    assert len(cancellation_transaction_lines) == 1
    assert any(record["message_type"] == "action_cancelled" for record in transcript)
    registry_inputs = [record for record in transcript if record["message_type"] == "asset_registry"]
    ready_inputs = [record for record in transcript if record["message_type"] == "client_ready"]
    assert [record["envelope"]["correlation_id"] for record in registry_inputs] == [
        "msg_10000001",
        "msg_20000001",
    ]
    assert [record["envelope"]["correlation_id"] for record in ready_inputs] == [
        "msg_10000002",
        "msg_20000002",
    ]


def test_cli_rejects_repository_descendant_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forbidden = ROOT / "forbidden-m2-authority-evidence"

    exit_code = main(
        [
            "--config",
            str(ROOT / "config" / "v0"),
            "--output-root",
            str(forbidden),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["error_type"] == "ValueError"
    assert "outside the repository" in output["error"]
    assert not forbidden.exists()
