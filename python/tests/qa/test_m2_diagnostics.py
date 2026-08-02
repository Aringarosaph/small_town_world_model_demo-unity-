"""Regression coverage for QA-owned M2 gray-box diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter, ValidationError
from town_core.catalogs import load_catalog
from town_core.domain.enums import MessageType, MovementCancellationReason
from town_core.domain.protocol_models import (
    MovementCancelledMessage,
    PythonToUnityMessage,
    UnityToPythonMessage,
)

import tools.diagnostics.check_m2 as m2_diagnostics
from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m2 import (
    EVIDENCE_TEMPLATE,
    FIXTURE_ROOT,
    Status,
    _validate_protocol_version_policy,
    analyze_asset_registry,
    check_asset_registry_fixtures,
    check_evidence_template,
    check_external_registry,
    check_protocol_contract,
    detect_unity_generated_path,
    validate_acceptance_evidence,
)

pytestmark = [pytest.mark.qa, pytest.mark.m2, pytest.mark.graybox]


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _passing_evidence(root: Path, output: Path) -> Path:
    document = _read_json(root / EVIDENCE_TEMPLATE)
    document["source_commit"] = "a" * 40
    gates = cast(dict[str, dict[str, object]], document["gates"])
    for name in gates:
        gates[name] = {"details": f"verified {name}", "status": "PASS"}
    artifacts = {
        "batchmode_log": "batchmode.log",
        "editmode_results": "editmode-results.xml",
        "handshake_transcript": "handshake-transcript.jsonl",
        "playmode_results": "playmode-results.xml",
        "registry_report": "registry-report.json",
    }
    document["artifacts"] = artifacts
    (output / "batchmode.log").write_text("M2 batchmode completed\n", encoding="utf-8")
    (output / "editmode-results.xml").write_text('<test-run result="Passed" />\n', encoding="utf-8")
    (output / "playmode-results.xml").write_text('<test-run result="Passed" />\n', encoding="utf-8")
    (output / "handshake-transcript.jsonl").write_text(
        '{"message_id":"msg_000001","message_type":"client_hello"}\n', encoding="utf-8"
    )
    (output / "registry-report.json").write_text('{"accepted":true,"issues":[]}\n', encoding="utf-8")
    observations = cast(dict[str, dict[str, object]], document["observations"])
    observations["cancellation"] = {
        "conflicting_same_message_id_rejected_without_mutation": True,
        "correlation_id_equals_action_id": True,
        "direction": "unity_to_python",
        "direction_rejected_without_mutation": True,
        "duplicate_same_message_id_is_idempotent": True,
        "future_state_version_rejected_without_mutation": True,
        "python_authority_cancel_transaction_count": 1,
        "stale_exact_current_action_processed": True,
        "stale_nonmatching_or_terminal_authority_mutation_count": 0,
        "stale_nonmatching_or_terminal_authority_transaction_count": 0,
        "stale_nonmatching_or_terminal_diagnostic_resync": True,
        "unity_direct_authority_mutation_count": 0,
    }
    observations["reconnect"] = {
        "fresh_snapshot_not_older_than_last_acknowledged_version": True,
        "full_hello_and_registry_repeated": True,
        "late_obsolete_generation_authority_mutation_count": 0,
        "new_client_ready_before_resume": True,
        "new_message_ids": True,
        "obsolete_generation_rejected": True,
    }
    evidence = output / "m2-evidence.json"
    evidence.write_text(json.dumps(document), encoding="utf-8")
    return evidence


@pytest.mark.parametrize(
    ("path", "detected"),
    [
        ("unity/Library/ArtifactDB", "library"),
        ("unity/Logs/Editor.log", "logs"),
        ("unity/TestResults/editmode.xml", "testresults"),
        ("unity/Assets/AITown/Tests/EditMode/BridgeTests.cs", None),
        ("docs/qa/TestResults.md", None),
    ],
)
def test_unity_generated_path_guard(path: str, detected: str | None) -> None:
    assert detect_unity_generated_path(path) == detected


def test_m2_slice_is_accepted_with_only_full_v0_warnings() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / FIXTURE_ROOT / "m2-slice-valid.json")
    cases = _read_json(root / FIXTURE_ROOT / "asset-registry-cases.json")
    payload = cast(dict[str, object], document["payload"])
    issues = analyze_asset_registry(document, load_catalog(root / "config/v0"))

    valid_case = cast(list[dict[str, object]], cases["cases"])[0]
    assert valid_case["name"] == "m2_slice_valid"
    assert valid_case["expected_accepted"] is True
    assert [item["location_id"] for item in cast(list[dict[str, object]], payload["locations"])] == [
        "home_a",
        "cafe_bar",
    ]
    assert [item["agent_id"] for item in cast(list[dict[str, object]], payload["npc_views"])] == ["npc_01"]
    assert {item["object_type"] for item in cast(list[dict[str, object]], payload["objects"])} == {
        "BED",
        "DINING_SEAT",
        "FRIDGE",
        "WORKSTATION",
    }
    assert not [issue for issue in issues if issue.severity == "ERROR"]
    assert {issue.code for issue in issues if issue.severity == "WARNING"} == {
        "FULL_V0_LOCATION_MISSING",
        "FULL_V0_NPC_VIEW_MISSING",
        "FULL_V0_OBJECT_TYPE_MISSING",
    }

    findings = check_external_registry(root, root / FIXTURE_ROOT / "m2-slice-valid.json")
    assert findings[0].status is Status.PASS
    assert {finding.status for finding in findings[1:]} == {Status.WARNING}


def test_full_v0_reference_has_no_scoped_validation_debt() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / FIXTURE_ROOT / "full-v0-registry-reference.json")
    issues = analyze_asset_registry(document, load_catalog(root / "config/v0"))

    assert issues == []


def test_asset_registry_case_matrix_matches_expected_acceptance() -> None:
    root = find_repository_root(Path(__file__))

    findings = check_asset_registry_fixtures(root)

    assert [(finding.status, finding.code) for finding in findings] == [(Status.PASS, "M2_ASSET_REGISTRY_FIXTURES")]


@pytest.mark.protocol
def test_integrated_protocol_and_target_fixtures_have_no_contract_pending() -> None:
    root = find_repository_root(Path(__file__))

    findings = check_protocol_contract(root, require_m2=False)

    required_codes = {
        "M2_HANDSHAKE_CONTRACT_FIXTURE",
        "M2_MOVEMENT_CANCELLED_CONTRACT_PRESENT",
        "M2_NAVIGATION_REPLAY_FIXTURE",
        "M2_PROTOCOL_0_2_CONTRACT",
        "M2_PROTOCOL_VERSION_DIRECTION_POLICY",
    }
    assert {finding.code for finding in findings if finding.status is Status.PASS} >= required_codes
    assert not [finding for finding in findings if finding.status is Status.FAIL]
    assert not [finding for finding in findings if finding.status is Status.PENDING]


def test_m2_protocol_policy_survives_additive_m3_current_version(monkeypatch: pytest.MonkeyPatch) -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/version.json")
    compatibility = cast(dict[str, object], document["compatibility"])
    document["protocol_version"] = "0.3.0"
    compatibility["active_m3_acceptance_versions"] = ["0.3.0"]
    compatibility["bootstrap_decodable_versions"] = ["0.3.0", "0.2.0", "0.1.0"]
    compatibility["current"] = "0.3.0"
    compatibility["m2_compatibility_artifacts_immutable"] = True
    compatibility["movement_cancelled_versions"] = ["0.3.0", "0.2.0"]

    ok, error = _validate_protocol_version_policy(document)

    assert ok, error

    real_read_json = m2_diagnostics._read_json

    def read_with_m3_current(path: Path) -> Mapping[str, object]:
        return document if path == root / "protocol/version.json" else real_read_json(path)

    monkeypatch.setattr(m2_diagnostics, "_read_json", read_with_m3_current)
    findings = check_protocol_contract(root, require_m2=False)
    assert not [finding for finding in findings if finding.status is not Status.PASS]
    assert {finding.code for finding in findings} >= {
        "M2_PROTOCOL_0_2_CONTRACT",
        "M2_MOVEMENT_CANCELLED_CONTRACT_PRESENT",
        "M2_PROTOCOL_VERSION_DIRECTION_POLICY",
    }

    compatibility["active_m2_acceptance_versions"] = []
    ok, _ = _validate_protocol_version_policy(document)
    assert not ok


def test_repository_version_document_matches_current_m2_compatibility_policy() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/version.json")
    compatibility = cast(dict[str, object], document["compatibility"])

    ok, error = _validate_protocol_version_policy(document)

    assert ok, error
    if document["protocol_version"] == "0.3.0":
        assert compatibility["current"] == "0.3.0"
        assert compatibility["movement_cancelled_versions"] == ["0.3.0", "0.2.0"]
        assert compatibility["m2_compatibility_artifacts_immutable"] is True
    else:
        assert document["protocol_version"] == "0.2.0"
        assert compatibility["movement_cancelled_versions"] == ["0.2.0"]


@pytest.mark.protocol
def test_movement_cancelled_is_typed_unity_input_and_not_python_output() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/examples/movement-cancelled.json")

    TypeAdapter(UnityToPythonMessage).validate_python(document)
    message = TypeAdapter(MovementCancelledMessage).validate_python(document)

    assert message.message_type is MessageType.MOVEMENT_CANCELLED
    assert message.payload.reason is MovementCancellationReason.NAVIGATION_STOPPED
    assert message.correlation_id == message.payload.action_id
    with pytest.raises(ValidationError):
        TypeAdapter(PythonToUnityMessage).validate_python(document)


@pytest.mark.protocol
def test_action_cancelled_is_typed_python_output_and_not_unity_input() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/examples/action-cancelled.json")

    TypeAdapter(PythonToUnityMessage).validate_python(document)

    with pytest.raises(ValidationError):
        TypeAdapter(UnityToPythonMessage).validate_python(document)


@pytest.mark.protocol
def test_movement_cancelled_rejects_wrong_action_correlation() -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / "protocol/examples/movement-cancelled.json")
    document["correlation_id"] = "action_0000099"

    with pytest.raises(ValidationError, match="correlation_id"):
        TypeAdapter(UnityToPythonMessage).validate_python(document)


def test_evidence_template_contains_every_strict_gate() -> None:
    root = find_repository_root(Path(__file__))

    findings = check_evidence_template(root)

    assert [(finding.status, finding.code) for finding in findings] == [
        (Status.PASS, "M2_ACCEPTANCE_EVIDENCE_TEMPLATE")
    ]


def test_pending_evidence_cannot_be_reported_as_final(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    document = _read_json(root / EVIDENCE_TEMPLATE)
    document["source_commit"] = "a" * 40
    evidence = tmp_path / "m2-evidence.json"
    evidence.write_text(json.dumps(document), encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert [(finding.status, finding.code) for finding in findings] == [(Status.FAIL, "M2_ACCEPTANCE_EVIDENCE_INVALID")]
    assert "not PASS" in findings[0].message


def test_complete_external_evidence_passes_with_processable_stale_branch(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))

    findings = validate_acceptance_evidence(_passing_evidence(root, tmp_path), root)

    assert [(finding.status, finding.code) for finding in findings] == [(Status.PASS, "M2_ACCEPTANCE_EVIDENCE_VALID")]


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("cancellation", "stale_exact_current_action_transaction_count"),
        ("cancellation", "stale_state_message_authority_mutation_count"),
        ("reconnect", "stale_state_message_authority_mutation_count"),
    ],
)
def test_ambiguous_or_duplicate_stale_observation_is_rejected(
    tmp_path: Path,
    section: str,
    field: str,
) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    observations = cast(dict[str, dict[str, object]], document["observations"])
    observations[section][field] = 0
    evidence.write_text(json.dumps(document), encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert f"{section} observations must be exactly" in findings[0].message


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("stale_exact_current_action_processed", False, "match was not processed"),
        ("python_authority_cancel_transaction_count", 0, "must commit exactly one Python authority transaction"),
        ("direction_rejected_without_mutation", False, "not all true"),
        ("future_state_version_rejected_without_mutation", False, "not all true"),
        (
            "stale_nonmatching_or_terminal_diagnostic_resync",
            False,
            "did not trigger diagnostic resync",
        ),
        ("stale_nonmatching_or_terminal_authority_transaction_count", 1, "committed a transaction"),
        ("stale_nonmatching_or_terminal_authority_mutation_count", 1, "mutated authority"),
    ],
)
def test_stale_cancellation_branches_are_not_conflated(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    document = _read_json(evidence)
    observations = cast(dict[str, dict[str, object]], document["observations"])
    observations["cancellation"][field] = value
    evidence.write_text(json.dumps(document), encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert message in findings[0].message


def test_external_evidence_rejects_sensitive_artifact_content(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    evidence = _passing_evidence(root, tmp_path)
    synthetic_secret = "token=" + "sk" + "-" + ("a" * 32) + "\n"
    (tmp_path / "batchmode.log").write_text(synthetic_secret, encoding="utf-8")

    findings = validate_acceptance_evidence(evidence, root)

    assert findings[0].status is Status.FAIL
    assert "sensitive content" in findings[0].message
