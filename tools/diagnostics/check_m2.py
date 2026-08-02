"""Gray-box M2 QA diagnostics for Small Town World Model（STWM）.

The checker validates frozen protocol DTOs, QA fixtures, the scoped semantic
asset registry, repository hygiene, and Unity-produced acceptance evidence. It
does not implement the WebSocket server, Unity client, navigation, authority
state transitions, or reconnect behavior.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final, cast

from pydantic import TypeAdapter, ValidationError

REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_IMPORT_ROOT, REPOSITORY_IMPORT_ROOT / "python"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from town_core.catalogs import CatalogValidationError, load_catalog
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import MessageType, MovementFailureReason, ObjectType
from town_core.domain.protocol_models import (
    AssetRegistryMessage,
    ProtocolMessage,
    PythonToUnityMessage,
    UnityToPythonMessage,
)

from tools.diagnostics.check_m0 import Status as M0Status
from tools.diagnostics.check_m0 import check_sensitive_files, detect_secret_content, find_repository_root


class Status(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    PENDING = "PENDING"
    FAIL = "FAIL"


class Owner(StrEnum):
    QA = "QA"
    CONTRACTS = "CONTRACTS"
    UNITY = "UNITY"
    SIM = "SIM"
    ORCHESTRATOR = "ORCHESTRATOR"


@dataclass(frozen=True)
class Finding:
    check: str
    status: Status
    code: str
    message: str
    owner: Owner
    path: str | None = None
    remediation: str | None = None


@dataclass(frozen=True)
class AssetIssue:
    severity: str
    code: str
    message: str
    entity_id: str | None = None


PROJECT_NAME: Final = "Small Town World Model（STWM）"
ACCEPTED_M1_COMMIT: Final = "d014e709f50d7d59a6181ddb796ae00f11c264b8"
PROTOCOL_VERSION: Final = "0.2.0"
M3_PROTOCOL_VERSION: Final = "0.3.0"
CATALOG_PROTOCOL_VERSION: Final = "0.1.0"
UNITY_EDITOR_VERSION: Final = "6000.4.2f1"
REPORT_SCHEMA: Final = "stwm.qa.m2-diagnostics/v1"
EVIDENCE_SCHEMA: Final = "stwm.qa.m2-acceptance-evidence/v1"
FIXTURE_ROOT: Final = Path("integration_tests/fixtures/m2")
EVIDENCE_TEMPLATE: Final = Path("docs/qa/M2_ACCEPTANCE_EVIDENCE.template.json")
M2_BASELINE: Final = Path("docs/orchestration/M2_EXECUTION_BASELINE.md")
M2_ADR: Final = Path("docs/adr/0009-m2-greybox-and-scoped-asset-validation.md")
M2_PROTOCOL_ADR: Final = Path("docs/adr/0010-m2-movement-cancellation-and-protocol-v020.md")
HANDSHAKE_TYPES: Final = (
    "client_hello",
    "server_hello",
    "asset_registry",
    "asset_registry_result",
    "world_snapshot",
    "client_ready",
)
EXPECTED_FAILURE_REASONS: Final = (
    "NO_PATH",
    "DESTINATION_DISABLED",
    "SLOT_BLOCKED",
    "AGENT_DISABLED",
    "TIMEOUT",
    "UNKNOWN",
)
EVIDENCE_GATES: Final = (
    "asset_registry",
    "authority_boundary",
    "cancellation_authority",
    "handshake",
    "message_id_idempotency",
    "navigation_arrived",
    "navigation_cancelled",
    "navigation_failed",
    "obsolete_generation_rejection",
    "protocol_direction",
    "reconnect_resync",
    "repository_guard",
    "unity_editmode",
    "unity_playmode",
)
EVIDENCE_ARTIFACTS: Final = (
    "batchmode_log",
    "editmode_results",
    "handshake_transcript",
    "playmode_results",
    "registry_report",
)
CANCELLATION_OBSERVATIONS: Final = (
    "conflicting_same_message_id_rejected_without_mutation",
    "correlation_id_equals_action_id",
    "direction",
    "direction_rejected_without_mutation",
    "duplicate_same_message_id_is_idempotent",
    "future_state_version_rejected_without_mutation",
    "python_authority_cancel_transaction_count",
    "stale_exact_current_action_processed",
    "stale_nonmatching_or_terminal_authority_mutation_count",
    "stale_nonmatching_or_terminal_authority_transaction_count",
    "stale_nonmatching_or_terminal_diagnostic_resync",
    "unity_direct_authority_mutation_count",
)
RECONNECT_OBSERVATIONS: Final = (
    "fresh_snapshot_not_older_than_last_acknowledged_version",
    "full_hello_and_registry_repeated",
    "late_obsolete_generation_authority_mutation_count",
    "new_client_ready_before_resume",
    "new_message_ids",
    "obsolete_generation_rejected",
)
UNITY_GENERATED_PARTS: Final = {
    "library",
    "temp",
    "obj",
    "build",
    "builds",
    "logs",
    "usersettings",
    "memorycaptures",
    "recordings",
    "testresults",
}
SOURCE_COMMIT_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
MACHINE_PATH_PATTERN: Final = re.compile(r"(?:/Users/|/home/runner/|[A-Za-z]:\\Users\\)")
MAX_EVIDENCE_ARTIFACT_BYTES: Final = 10 * 1024 * 1024


class DiagnosticError(ValueError):
    """Raised for malformed QA fixtures or acceptance evidence."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DiagnosticError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DiagnosticError(f"{label} must be an array")
    return cast(list[object], value)


def _string(mapping: Mapping[str, object], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise DiagnosticError(f"{label}.{key} must be a non-empty string")
    return value


def _boolean(mapping: Mapping[str, object], key: str, label: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise DiagnosticError(f"{label}.{key} must be boolean")
    return value


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"cannot read {path}: {exc}") from exc
    return _mapping(raw, path.as_posix())


def _finding(
    *,
    check: str,
    code: str,
    ok: bool,
    success: str,
    failure: str,
    owner: Owner,
    path: str | None = None,
    remediation: str | None = None,
) -> Finding:
    return Finding(
        check=check,
        status=Status.PASS if ok else Status.FAIL,
        code=code,
        message=success if ok else failure,
        owner=owner,
        path=path,
        remediation=None if ok else remediation,
    )


def _pending(
    *,
    check: str,
    code: str,
    message: str,
    owner: Owner,
    require_m2: bool,
    remediation: str,
    path: str | None = None,
) -> Finding:
    return Finding(
        check=check,
        status=Status.FAIL if require_m2 else Status.PENDING,
        code=code,
        message=message,
        owner=owner,
        path=path,
        remediation=remediation,
    )


def _git_candidates(root: Path) -> tuple[list[str], str | None]:
    completed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return [], completed.stderr.decode("utf-8", errors="replace").strip()
    decoded = completed.stdout.decode("utf-8", errors="surrogateescape")
    return [value for value in decoded.split("\0") if value], None


def detect_unity_generated_path(relative_path: str) -> str | None:
    """Return the generated Unity directory component for an unsafe candidate."""
    parts = tuple(part.lower() for part in PurePosixPath(relative_path).parts)
    if not parts or parts[0] != "unity":
        return None
    return next((part for part in parts[1:] if part in UNITY_GENERATED_PARTS), None)


def check_repository_guard(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    m0_failures = [finding for finding in check_sensitive_files(root) if finding.status is M0Status.FAIL]
    findings.append(
        _finding(
            check="m2.repository",
            code="M2_SENSITIVE_FILE_GUARD",
            ok=not m0_failures,
            success="no sensitive or generated candidates were detected by the frozen M0 guard",
            failure="; ".join(f"{item.path}: {item.message}" for item in m0_failures),
            owner=Owner.QA,
            remediation="Remove the candidate and rotate any exposed credential before M2 integration.",
        )
    )
    paths, error = _git_candidates(root)
    if error:
        findings.append(
            Finding(
                check="m2.repository",
                status=Status.FAIL,
                code="M2_GIT_CANDIDATE_SCAN_FAILED",
                message=error,
                owner=Owner.QA,
            )
        )
        return findings
    generated = [(path, detect_unity_generated_path(path)) for path in paths]
    generated = [(path, detector) for path, detector in generated if detector is not None]
    findings.append(
        _finding(
            check="m2.repository",
            code="M2_UNITY_CACHE_GUARD",
            ok=not generated,
            success="Unity Library/Logs/TestResults and other generated trees are ignored and untracked",
            failure="; ".join(f"{path}: unity-{detector}" for path, detector in generated),
            owner=Owner.QA,
            remediation="Remove generated Unity output from Git and keep batchmode outputs outside the worktree.",
        )
    )
    return findings


def check_governance(root: Path, require_m2: bool) -> list[Finding]:
    completed = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ACCEPTED_M1_COMMIT, "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    findings = [
        _finding(
            check="m2.governance",
            code="M2_ACCEPTED_M1_BASELINE",
            ok=completed.returncode == 0,
            success=f"HEAD contains accepted M1 baseline {ACCEPTED_M1_COMMIT[:7]}",
            failure=f"HEAD does not contain accepted M1 baseline {ACCEPTED_M1_COMMIT}",
            owner=Owner.ORCHESTRATOR,
            remediation="Recreate the M2 branch from the accepted public main; do not merge the historical M1 QA branch.",
        )
    ]
    for path, code, label in (
        (M2_BASELINE, "M2_EXECUTION_BASELINE_PENDING", "M2 execution baseline"),
        (M2_ADR, "M2_ADR_0009_PENDING", "ADR-0009 functional gray-box decision"),
        (M2_PROTOCOL_ADR, "M2_ADR_0010_PENDING", "ADR-0010 protocol 0.2 cancellation decision"),
    ):
        if (root / path).is_file():
            findings.append(
                Finding(
                    check="m2.governance",
                    status=Status.PASS,
                    code=code.removesuffix("_PENDING") + "_PRESENT",
                    message=f"{label} is present",
                    owner=Owner.ORCHESTRATOR,
                    path=path.as_posix(),
                )
            )
        else:
            findings.append(
                _pending(
                    check="m2.governance",
                    code=code,
                    message=f"{label} is not integrated on this branch yet",
                    owner=Owner.ORCHESTRATOR,
                    require_m2=require_m2,
                    remediation="Integrate the Orchestrator-owned M2 baseline commit before the final strict gate.",
                    path=path.as_posix(),
                )
            )
    return findings


def _validate_handshake_fixture(root: Path) -> tuple[bool, str]:
    document = _read_json(root / FIXTURE_ROOT / "handshake-contract.json")
    if document.get("schema") != "stwm.qa.m2-handshake-contract/v1":
        return False, "handshake fixture schema mismatch"
    if document.get("protocol_version") != PROTOCOL_VERSION:
        return False, f"handshake fixture must target protocol {PROTOCOL_VERSION}"
    steps = _sequence(document.get("happy_path"), "handshake.happy_path")
    observed = [
        _string(_mapping(step, f"handshake.happy_path[{index}]"), "message_type", "step")
        for index, step in enumerate(steps)
    ]
    if observed != list(HANDSHAKE_TYPES):
        return False, f"handshake order is {observed}, expected {list(HANDSHAKE_TYPES)}"
    expected_directions = (
        "unity_to_python",
        "python_to_unity",
        "unity_to_python",
        "python_to_unity",
        "python_to_unity",
        "unity_to_python",
    )
    observed_directions = [
        _string(_mapping(step, f"handshake.happy_path[{index}]"), "direction", "step")
        for index, step in enumerate(steps)
    ]
    if observed_directions != list(expected_directions):
        return False, "handshake message directions violate the frozen client/server permissions"
    known = {item.value for item in MessageType}
    missing = [value for value in observed if value not in known]
    invariants = _mapping(document.get("invariants"), "handshake.invariants")
    if not invariants or not all(value is True for value in invariants.values()):
        return False, "handshake invariants must all be true"
    failure = _mapping(document.get("failure_branch"), "handshake.failure_branch")
    if not _boolean(failure, "simulation_must_not_start", "handshake.failure_branch"):
        return False, "rejected registry must prevent simulation start"
    return not missing, f"unknown handshake message types: {missing}"


def _validate_navigation_fixture(root: Path) -> tuple[bool, str, bool]:
    document = _read_json(root / FIXTURE_ROOT / "navigation-replay-contract.json")
    if document.get("schema") != "stwm.qa.m2-navigation-replay/v1":
        return False, "navigation fixture schema mismatch", False
    if document.get("protocol_version") != PROTOCOL_VERSION:
        return False, f"navigation fixture must target protocol {PROTOCOL_VERSION}", False
    known = {item.value for item in MessageType}
    cases = _sequence(document.get("cases"), "navigation.cases")
    indexed: dict[str, Mapping[str, object]] = {}
    for index, raw_case in enumerate(cases):
        item = _mapping(raw_case, f"navigation.cases[{index}]")
        indexed[_string(item, "name", f"navigation.cases[{index}]")] = item
    if set(indexed) != {"arrived", "failed", "cancelled"}:
        return False, "navigation cases must be arrived, failed, and cancelled", False
    arrived = _string(indexed["arrived"], "required_message_type", "navigation.arrived")
    failed = _string(indexed["failed"], "required_message_type", "navigation.failed")
    cancelled = _string(indexed["cancelled"], "required_message_type", "navigation.cancelled")
    if arrived not in known or failed not in known:
        return False, "arrived/failed message contracts are missing", cancelled in known
    reasons = [
        item for item in _sequence(indexed["failed"].get("allowed_reasons"), "navigation.failed.allowed_reasons")
    ]
    if reasons != list(EXPECTED_FAILURE_REASONS) or reasons != [item.value for item in MovementFailureReason]:
        return False, "movement failure reasons differ from the frozen contract", cancelled in known
    reconnect = _mapping(document.get("reconnect"), "navigation.reconnect")
    if not reconnect or not all(value is True for value in reconnect.values()):
        return False, "frozen reconnect/resync requirements must all be true", cancelled in known
    authority = _mapping(document.get("authority_invariants"), "navigation.authority_invariants")
    if not authority or not all(value is True for value in authority.values()):
        return False, "navigation authority invariants must all be true", cancelled in known
    for name in ("arrived", "failed", "cancelled"):
        if indexed[name].get("direction") != "unity_to_python":
            return False, f"navigation.{name} must be Unity-to-Python", cancelled in known
    cancellation = indexed["cancelled"]
    required_cancellation_observations = (
        "conflicting_same_message_id_rejected",
        "correlation_id_equals_action_id",
        "duplicate_same_message_id_is_idempotent",
    )
    if any(cancellation.get(key) is not True for key in required_cancellation_observations):
        return False, "cancellation correlation/idempotency requirements are incomplete", cancelled in known
    if cancellation.get("unity_direct_authority_mutation_count") != 0:
        return False, "Unity cancellation reports must have zero direct authority mutation", cancelled in known
    if cancellation.get("stale_exact_current_action_processed") is not True:
        return False, "an exact current-action stale cancellation must be processed", cancelled in known
    if cancellation.get("python_authority_cancel_transaction_count") != 1:
        return False, "an exact current-action stale cancellation must commit once", cancelled in known
    if cancellation.get("direction_rejected_without_mutation") is not True:
        return False, "a wrong-direction cancellation must be rejected without mutation", cancelled in known
    if cancellation.get("future_state_version_rejected_without_mutation") is not True:
        return False, "a future-version cancellation must be rejected without mutation", cancelled in known
    if cancellation.get("stale_nonmatching_or_terminal_diagnostic_resync") is not True:
        return False, "a nonmatching or terminal stale cancellation must trigger diagnostic resync", cancelled in known
    if cancellation.get("stale_nonmatching_or_terminal_authority_transaction_count") != 0:
        return False, "a nonmatching or terminal stale cancellation must not commit", cancelled in known
    if cancellation.get("stale_nonmatching_or_terminal_authority_mutation_count") != 0:
        return False, "a nonmatching or terminal stale cancellation must not mutate authority", cancelled in known
    return True, "", cancelled in known


def _validate_movement_cancelled_artifacts(root: Path) -> tuple[bool, str]:
    if "movement_cancelled" not in {item.value for item in MessageType}:
        return False, "MessageType does not contain movement_cancelled"
    example_path = root / "protocol/examples/movement-cancelled.json"
    action_example_path = root / "protocol/examples/action-cancelled.json"
    schema_paths = (
        root / "protocol/jsonschema/protocol-message.schema.json",
        root / "protocol/jsonschema/unity-to-python-message.schema.json",
        root / "protocol/jsonschema/python-to-unity-message.schema.json",
    )
    try:
        example = _read_json(example_path)
        action_example = _read_json(action_example_path)
        payload = _mapping(example.get("payload"), "movement_cancelled.payload")
        if example.get("protocol_version") != PROTOCOL_VERSION:
            return False, f"movement_cancelled example must use protocol {PROTOCOL_VERSION}"
        if example.get("message_type") != "movement_cancelled":
            return False, "movement_cancelled example has the wrong message_type"
        if example.get("correlation_id") != payload.get("action_id"):
            return False, "movement_cancelled correlation_id must equal payload.action_id"
        TypeAdapter(ProtocolMessage).validate_python(example)
        TypeAdapter(UnityToPythonMessage).validate_python(example)
        try:
            TypeAdapter(PythonToUnityMessage).validate_python(example)
        except ValidationError:
            pass
        else:
            return False, "movement_cancelled was accepted in the Python-to-Unity direction"
        TypeAdapter(PythonToUnityMessage).validate_python(action_example)
        try:
            TypeAdapter(UnityToPythonMessage).validate_python(action_example)
        except ValidationError:
            pass
        else:
            return False, "action_cancelled was accepted in the Unity-to-Python direction"
        schema_documents = [_read_json(path) for path in schema_paths]
        generic_text = json.dumps(schema_documents[0])
        if "movement_cancelled" not in generic_text:
            return False, "generated generic protocol JSON Schema omits movement_cancelled"
        unity_mapping = _mapping(
            _mapping(schema_documents[1].get("discriminator"), "unity schema.discriminator").get("mapping"),
            "unity schema.discriminator.mapping",
        )
        python_mapping = _mapping(
            _mapping(schema_documents[2].get("discriminator"), "python schema.discriminator").get("mapping"),
            "python schema.discriminator.mapping",
        )
        if "movement_cancelled" not in unity_mapping or "action_cancelled" in unity_mapping:
            return False, "Unity-to-Python direction schema has invalid cancellation permissions"
        if "action_cancelled" not in python_mapping or "movement_cancelled" in python_mapping:
            return False, "Python-to-Unity direction schema has invalid cancellation permissions"
    except (DiagnosticError, OSError, ValidationError) as exc:
        return False, str(exc)
    return True, ""


def _validate_protocol_version_policy(version: Mapping[str, object]) -> tuple[bool, str]:
    try:
        compatibility = _mapping(version.get("compatibility"), "protocol.version.compatibility")
        frozen = _mapping(version.get("frozen_decisions"), "protocol.version.frozen_decisions")
        bootstrap_versions = compatibility.get("bootstrap_decodable_versions")
        current_protocol = version.get("protocol_version")
        expected_cancellation_versions = (
            [PROTOCOL_VERSION]
            if current_protocol == PROTOCOL_VERSION
            else [M3_PROTOCOL_VERSION, PROTOCOL_VERSION]
            if current_protocol == M3_PROTOCOL_VERSION
            else None
        )
        immutable_m2_ok = (
            compatibility.get("m2_compatibility_artifacts_immutable") is True
            if current_protocol == M3_PROTOCOL_VERSION
            else "m2_compatibility_artifacts_immutable" not in compatibility
            or compatibility.get("m2_compatibility_artifacts_immutable") is True
        )
        compatibility_current_ok = (
            compatibility.get("current") == current_protocol
            if current_protocol == M3_PROTOCOL_VERSION
            else compatibility.get("current") in {None, current_protocol}
        )
        ok = (
            compatibility.get("active_m2_acceptance_versions") == [PROTOCOL_VERSION]
            and isinstance(bootstrap_versions, list)
            and PROTOCOL_VERSION in bootstrap_versions
            and "0.1.0" in bootstrap_versions
            and compatibility.get("legacy_decode_only_versions") == ["0.1.0"]
            and expected_cancellation_versions is not None
            and compatibility.get("movement_cancelled_versions") == expected_cancellation_versions
            and immutable_m2_ok
            and compatibility_current_ok
            and frozen.get("action_cancelled_direction") == "PYTHON_TO_UNITY_AUTHORITATIVE_DECISION"
            and frozen.get("action_correlation") == "CORRELATION_ID_EQUALS_ACTION_ID"
            and frozen.get("movement_cancelled_direction") == "UNITY_TO_PYTHON_NON_AUTHORITATIVE_REPORT"
            and frozen.get("heartbeat") == "WEBSOCKET_PING_PONG"
            and frozen.get("resync") == "FULL_HANDSHAKE_REGISTRY_SNAPSHOT_CLIENT_READY"
        )
    except DiagnosticError as exc:
        return False, str(exc)
    return ok, "protocol/version.json does not retain the accepted ADR-0010 M2 profile and direction policy"


def check_protocol_contract(root: Path, require_m2: bool) -> list[Finding]:
    findings: list[Finding] = []
    try:
        version = _read_json(root / "protocol/version.json")
        current_protocol = version.get("protocol_version")
        catalog_protocol = load_catalog(root / "config/v0").world.protocol_version
        editor_ok = version.get("unity_editor") == UNITY_EDITOR_VERSION
        version_policy_ok, version_policy_error = _validate_protocol_version_policy(version)
        handshake_ok, handshake_error = _validate_handshake_fixture(root)
        navigation_ok, navigation_error, cancellation_present = _validate_navigation_fixture(root)
        cancellation_artifacts_ok, cancellation_artifacts_error = _validate_movement_cancelled_artifacts(root)
    except (CatalogValidationError, DiagnosticError) as exc:
        return [
            Finding(
                check="m2.protocol",
                status=Status.FAIL,
                code="M2_PROTOCOL_FIXTURE_INVALID",
                message=str(exc),
                owner=Owner.QA,
            )
        ]
    findings.append(
        _finding(
            check="m2.protocol",
            code="M2_UNITY_VERSION_CONTRACT",
            ok=editor_ok,
            success=f"protocol metadata retains Unity {UNITY_EDITOR_VERSION}",
            failure="protocol metadata changed the pinned Unity editor",
            owner=Owner.CONTRACTS,
            remediation="Stop and request CONTRACTS/Orchestrator review; QA may not alter the editor pin.",
        )
    )
    findings.append(
        _finding(
            check="m2.protocol",
            code="M2_CATALOG_BRIDGE_VERSION_SEPARATION",
            ok=catalog_protocol == CATALOG_PROTOCOL_VERSION,
            success=(
                f"catalog provenance remains {CATALOG_PROTOCOL_VERSION} while M2 evidence negotiates "
                f"its retained {PROTOCOL_VERSION} compatibility profile"
            ),
            failure=f"catalog_protocol_version={catalog_protocol!r}",
            owner=Owner.CONTRACTS,
            remediation="Do not rewrite the M0 catalog provenance; bridge negotiation comes from protocol/version.json.",
        )
    )
    findings.append(
        _finding(
            check="m2.protocol",
            code="M2_PROTOCOL_VERSION_DIRECTION_POLICY",
            ok=version_policy_ok,
            success="protocol metadata retains the M2 0.2.0 profile, direction authority, correlation, and full resync",
            failure=version_policy_error,
            owner=Owner.CONTRACTS,
            path="protocol/version.json",
            remediation="Restore the generated ADR-0010 protocol metadata; QA may not redefine direction policy.",
        )
    )
    if current_protocol in {PROTOCOL_VERSION, M3_PROTOCOL_VERSION}:
        findings.append(
            _finding(
                check="m2.protocol",
                code="M2_PROTOCOL_0_2_CONTRACT",
                ok=version_policy_ok,
                success=(
                    f"protocol {PROTOCOL_VERSION} artifacts remain the active M2 acceptance profile "
                    f"while repository current is {current_protocol}"
                ),
                failure="repository current is supported, but the active M2 0.2.0 acceptance profile is missing",
                owner=Owner.CONTRACTS,
                remediation="Restore active_m2_acceptance_versions=['0.2.0'] and the retained ADR-0010 artifacts.",
            )
        )
    elif current_protocol == "0.1.0":
        findings.append(
            _pending(
                check="m2.protocol",
                code="M2_PROTOCOL_0_2_PENDING",
                message="accepted M1 protocol 0.1.0 is present; CONTRACTS protocol 0.2.0 integration is pending",
                owner=Owner.CONTRACTS,
                require_m2=require_m2,
                remediation="Integrate ADR-0010 plus regenerated 0.2.0 DTO, Schema, examples, and compatibility tests.",
            )
        )
    else:
        findings.append(
            Finding(
                check="m2.protocol",
                status=Status.FAIL,
                code="M2_PROTOCOL_VERSION_UNEXPECTED",
                message=f"unexpected protocol version: {current_protocol!r}",
                owner=Owner.CONTRACTS,
            )
        )
    findings.append(
        _finding(
            check="m2.handshake",
            code="M2_HANDSHAKE_CONTRACT_FIXTURE",
            ok=handshake_ok,
            success="handshake happy/failure paths use the frozen message union and authority invariants",
            failure=handshake_error,
            owner=Owner.QA,
            path=(FIXTURE_ROOT / "handshake-contract.json").as_posix(),
            remediation="Correct only the QA fixture unless CONTRACTS explicitly changes the protocol.",
        )
    )
    findings.append(
        _finding(
            check="m2.navigation",
            code="M2_NAVIGATION_REPLAY_FIXTURE",
            ok=navigation_ok,
            success="arrived, failed, and frozen reconnect/resync expectations are internally consistent",
            failure=navigation_error,
            owner=Owner.QA,
            path=(FIXTURE_ROOT / "navigation-replay-contract.json").as_posix(),
        )
    )
    if (
        current_protocol in {PROTOCOL_VERSION, M3_PROTOCOL_VERSION}
        and version_policy_ok
        and cancellation_present
        and cancellation_artifacts_ok
    ):
        findings.append(
            Finding(
                check="m2.navigation",
                status=Status.PASS,
                code="M2_MOVEMENT_CANCELLED_CONTRACT_PRESENT",
                message="Unity-to-Python movement cancellation has a versioned protocol message",
                owner=Owner.CONTRACTS,
            )
        )
    elif current_protocol == "0.1.0" and not cancellation_present:
        findings.append(
            _pending(
                check="m2.navigation",
                code="M2_MOVEMENT_CANCELLED_CONTRACT_PENDING",
                message="protocol 0.2.0 movement_cancelled is authorized but not yet present in MessageType/DTO/JSON Schema",
                owner=Owner.CONTRACTS,
                require_m2=require_m2,
                remediation="Integrate CONTRACTS ADR-0010 artifacts; final M2 acceptance cannot retain this pending result.",
            )
        )
    else:
        findings.append(
            Finding(
                check="m2.navigation",
                status=Status.FAIL,
                code="M2_MOVEMENT_CANCELLED_CONTRACT_INVALID",
                message=cancellation_artifacts_error or "movement_cancelled is inconsistent with the message union",
                owner=Owner.CONTRACTS,
                remediation=(
                    "Regenerate the 0.2.0 DTO union, protocol JSON Schema, and "
                    "protocol/examples/movement-cancelled.json from the accepted CONTRACTS source."
                ),
            )
        )
    return findings


def _asset_issue(code: str, message: str, entity_id: str | None = None) -> AssetIssue:
    return AssetIssue(severity="ERROR", code=code, message=message, entity_id=entity_id)


def analyze_asset_registry(document: Mapping[str, object], catalog: CatalogBundle) -> list[AssetIssue]:
    """Inspect one frozen AssetRegistryMessage for the functional M2 slice."""
    if document.get("message_type") != "asset_registry":
        return [_asset_issue("NOT_ASSET_REGISTRY", "fixture is not an asset_registry message")]
    if document.get("protocol_version") != PROTOCOL_VERSION:
        return [_asset_issue("PROTOCOL_VERSION_MISMATCH", f"registry must target protocol {PROTOCOL_VERSION}")]
    try:
        payload = TypeAdapter(AssetRegistryMessage).validate_python(document).payload
    except ValidationError as exc:
        return [_asset_issue("PROTOCOL_SCHEMA_INVALID", str(exc))]

    issues: list[AssetIssue] = []
    locations = payload.locations
    location_ids = [item.location_id for item in locations]
    if len(location_ids) != len(set(location_ids)):
        issues.append(_asset_issue("DUPLICATE_LOCATION_ID", "location IDs must be unique"))
    expected_locations = {item.location_id: item.location_type for item in catalog.locations.locations}
    actual_locations = {item.location_id: item.location_type for item in locations}
    required_m2_locations = {"home_a", "cafe_bar"}
    for location_id in sorted(required_m2_locations - set(actual_locations)):
        issues.append(_asset_issue("MISSING_M2_LOCATION", "blocking M2 semantic location is missing", location_id))
    for location_id in sorted(set(expected_locations) - set(actual_locations)):
        if location_id not in required_m2_locations:
            issues.append(
                AssetIssue(
                    severity="WARNING",
                    code="FULL_V0_LOCATION_MISSING",
                    message="location is deferred diagnostic debt until M3",
                    entity_id=location_id,
                )
            )
    for location_id, expected_type in expected_locations.items():
        if location_id in actual_locations and actual_locations[location_id] != expected_type:
            issues.append(_asset_issue("LOCATION_TYPE_MISMATCH", "location type differs from catalog", location_id))
    for location_id in sorted(set(actual_locations) - set(expected_locations)):
        issues.append(_asset_issue("UNKNOWN_LOCATION_ID", "location is outside the frozen catalog", location_id))

    agent_ids = [item.agent_id for item in payload.npc_views]
    if len(agent_ids) != len(set(agent_ids)):
        issues.append(_asset_issue("DUPLICATE_NPC_VIEW", "NpcView agent IDs must be unique"))
    expected_agents = {item.agent_id for item in catalog.population.npcs}
    if "npc_01" not in agent_ids:
        issues.append(_asset_issue("MISSING_M2_NPC_VIEW", "blocking M2 NpcView npc_01 is missing", "npc_01"))
    for agent_id in sorted(expected_agents - set(agent_ids)):
        if agent_id != "npc_01":
            issues.append(
                AssetIssue(
                    severity="WARNING",
                    code="FULL_V0_NPC_VIEW_MISSING",
                    message="NpcView is deferred diagnostic debt until M3",
                    entity_id=agent_id,
                )
            )
    for agent_id in sorted(set(agent_ids) - expected_agents):
        issues.append(_asset_issue("UNKNOWN_NPC_VIEW", "NpcView ID is outside the frozen catalog", agent_id))

    object_ids = [item.object_id for item in payload.objects]
    if len(object_ids) != len(set(object_ids)):
        issues.append(_asset_issue("DUPLICATE_OBJECT_ID", "semantic object IDs must be unique"))
    object_catalog = {item.object_type: item for item in catalog.objects.object_types}
    required_m2_object_types = {ObjectType.BED, ObjectType.FRIDGE, ObjectType.DINING_SEAT, ObjectType.WORKSTATION}
    actual_object_types = {item.object_type for item in payload.objects}
    for object_type in sorted(set(object_catalog) - actual_object_types, key=lambda item: item.value):
        if object_type not in required_m2_object_types:
            issues.append(
                AssetIssue(
                    severity="WARNING",
                    code="FULL_V0_OBJECT_TYPE_MISSING",
                    message="object type is deferred diagnostic debt until M3",
                    entity_id=object_type.value,
                )
            )
    for item in payload.objects:
        if item.location_id not in actual_locations:
            issues.append(_asset_issue("UNKNOWN_OBJECT_LOCATION", "object location is not registered", item.object_id))
        allowed_capabilities = set(object_catalog[item.object_type].capability_tags)
        if not set(item.capability_tags) <= allowed_capabilities:
            issues.append(
                _asset_issue("ILLEGAL_CAPABILITY_TAG", "object capability is outside its catalog type", item.object_id)
            )
        slot_indices = [slot.slot_index for slot in item.interaction_slots]
        if len(slot_indices) != len(set(slot_indices)):
            issues.append(
                _asset_issue("DUPLICATE_SLOT_INDEX", "slot indices must be unique per object", item.object_id)
            )
        if any(not slot.supported_animation_semantics for slot in item.interaction_slots):
            issues.append(
                _asset_issue("EMPTY_SLOT_ANIMATION_SET", "interaction slot has no animation semantic", item.object_id)
            )

    def matching_objects(*, object_type: ObjectType, location_id: str, capabilities: set[str]) -> list[object]:
        return [
            item
            for item in payload.objects
            if item.enabled
            and item.object_type == object_type
            and item.location_id == location_id
            and capabilities <= {value.value for value in item.capability_tags}
        ]

    if not matching_objects(object_type=ObjectType.BED, location_id="home_a", capabilities={"SLEEP"}):
        issues.append(_asset_issue("MISSING_HOME_BED", "M2 npc_01 requires an enabled SLEEP bed in home_a"))
    if not matching_objects(object_type=ObjectType.FRIDGE, location_id="home_a", capabilities={"FOOD_SOURCE_HOME"}):
        issues.append(_asset_issue("MISSING_HOME_FRIDGE", "M2 requires an enabled home_a food source"))
    if not matching_objects(object_type=ObjectType.DINING_SEAT, location_id="home_a", capabilities={"EAT"}):
        issues.append(_asset_issue("MISSING_HOME_DINING_SLOT", "M2 requires an enabled home_a dining slot"))
    if not matching_objects(
        object_type=ObjectType.WORKSTATION,
        location_id="cafe_bar",
        capabilities={"WORK", "CAFE_MORNING"},
    ):
        issues.append(_asset_issue("MISSING_WORKSTATION", "npc_01 requires a CAFE_MORNING workstation"))

    m2_behaviors = {"idle", "sleep", "eat_at_home", "work_shift"}
    required_animations = {"WALK"}
    for behavior in catalog.behaviors.behaviors:
        if behavior.behavior_id.value in m2_behaviors:
            required_animations.update(item.value for item in behavior.unity.animation_semantics)
    mapped = {item.value for item in payload.mapped_animation_semantics}
    for missing in sorted(required_animations - mapped):
        issues.append(_asset_issue("MISSING_ANIMATION_SEMANTIC", f"M2 animation mapping missing {missing}", missing))
    return issues


def _mutate_registry(document: Mapping[str, object], operation: str) -> Mapping[str, object]:
    mutable = copy.deepcopy(dict(document))
    payload = cast(dict[str, object], mutable["payload"])
    objects = cast(list[object], payload["objects"])
    if operation == "none":
        return mutable
    if operation == "duplicate_first_object":
        objects.append(copy.deepcopy(objects[0]))
    elif operation == "remove_workstations":
        payload["objects"] = [
            item for item in objects if _mapping(item, "asset object").get("object_type") != "WORKSTATION"
        ]
    elif operation == "remove_walk_mapping":
        semantics = cast(list[object], payload["mapped_animation_semantics"])
        payload["mapped_animation_semantics"] = [item for item in semantics if item != "WALK"]
    else:
        raise DiagnosticError(f"unknown asset registry fixture operation: {operation}")
    return mutable


def check_asset_registry_fixtures(root: Path) -> list[Finding]:
    try:
        catalog = load_catalog(root / "config/v0")
        cases_document = _read_json(root / FIXTURE_ROOT / "asset-registry-cases.json")
        if cases_document.get("schema") != "stwm.qa.m2-asset-registry-cases/v1":
            raise DiagnosticError("asset registry case schema mismatch")
        failures: list[str] = []
        for index, raw_case in enumerate(_sequence(cases_document.get("cases"), "asset cases")):
            case = _mapping(raw_case, f"asset cases[{index}]")
            name = _string(case, "name", f"asset cases[{index}]")
            fixture = root / FIXTURE_ROOT / _string(case, "fixture", f"asset cases[{index}]")
            document = _mutate_registry(_read_json(fixture), _string(case, "operation", f"asset cases[{index}]"))
            issues = analyze_asset_registry(document, catalog)
            actual = {issue.code for issue in issues if issue.severity == "ERROR"}
            expected_raw = _sequence(case.get("expected_error_codes"), f"asset cases[{index}].expected_error_codes")
            expected = {str(item) for item in expected_raw}
            if actual != expected:
                failures.append(f"{name}: actual={sorted(actual)} expected={sorted(expected)}")
            if case.get("expected_accepted") is not (not actual):
                failures.append(f"{name}: accepted={not actual} does not match expected_accepted")
            if name == "m2_slice_valid":
                if fixture.name != "m2-slice-valid.json":
                    failures.append("m2_slice_valid: canonical fixture filename mismatch")
                expected_warnings = {
                    str(item)
                    for item in _sequence(
                        case.get("expected_warning_codes"),
                        "asset cases.m2_slice_valid.expected_warning_codes",
                    )
                }
                actual_warnings = {issue.code for issue in issues if issue.severity == "WARNING"}
                if actual_warnings != expected_warnings:
                    failures.append(
                        f"m2_slice_valid: warning_codes={sorted(actual_warnings)} expected={sorted(expected_warnings)}"
                    )
        full_reference = _read_json(root / FIXTURE_ROOT / "full-v0-registry-reference.json")
        full_issues = analyze_asset_registry(full_reference, catalog)
        if full_issues:
            failures.append(
                "full_v0_reference: " + ", ".join(f"{issue.severity}/{issue.code}" for issue in full_issues)
            )
    except (CatalogValidationError, DiagnosticError, KeyError) as exc:
        failures = [str(exc)]
    return [
        _finding(
            check="m2.asset_registry",
            code="M2_ASSET_REGISTRY_FIXTURES",
            ok=not failures,
            success="valid and invalid scoped asset registry fixtures produced the expected reports",
            failure="; ".join(failures),
            owner=Owner.QA,
            path=(FIXTURE_ROOT / "asset-registry-cases.json").as_posix(),
            remediation="Fix the QA fixture/diagnostic only; do not change frozen catalog or protocol DTOs.",
        )
    ]


def check_external_registry(root: Path, registry_path: Path) -> list[Finding]:
    try:
        catalog = load_catalog(root / "config/v0")
        issues = analyze_asset_registry(_read_json(registry_path), catalog)
    except (CatalogValidationError, DiagnosticError) as exc:
        issues = [_asset_issue("REGISTRY_UNREADABLE", str(exc))]
    failures = [issue for issue in issues if issue.severity == "ERROR"]
    findings = [
        Finding(
            check="m2.asset_registry.external",
            status=Status.FAIL if failures else Status.PASS,
            code="M2_EXTERNAL_ASSET_REGISTRY",
            message=(
                "; ".join(f"{item.code}: {item.message}" for item in failures)
                if failures
                else "external asset registry satisfies the scoped M2 gray-box profile"
            ),
            owner=Owner.UNITY,
            path=registry_path.as_posix(),
        )
    ]
    findings.extend(
        Finding(
            check="m2.asset_registry.issue",
            status=Status.FAIL if issue.severity == "ERROR" else Status.WARNING,
            code=issue.code,
            message=issue.message,
            owner=Owner.UNITY,
            path=issue.entity_id,
        )
        for issue in issues
    )
    return findings


def check_evidence_template(root: Path) -> list[Finding]:
    try:
        document = _read_json(root / EVIDENCE_TEMPLATE)
        gates = _mapping(document.get("gates"), "M2 evidence template.gates")
        artifacts = _mapping(document.get("artifacts"), "M2 evidence template.artifacts")
        observations = _mapping(document.get("observations"), "M2 evidence template.observations")
        ok = (
            document.get("schema") == EVIDENCE_SCHEMA
            and document.get("project_name") == PROJECT_NAME
            and document.get("accepted_m1_commit") == ACCEPTED_M1_COMMIT
            and document.get("protocol_version") == PROTOCOL_VERSION
            and document.get("catalog_protocol_version") == CATALOG_PROTOCOL_VERSION
            and document.get("negotiated_protocol_version") == PROTOCOL_VERSION
            and document.get("unity_editor_version") == UNITY_EDITOR_VERSION
            and set(gates) == set(EVIDENCE_GATES)
            and set(artifacts) == set(EVIDENCE_ARTIFACTS)
            and set(observations) == {"cancellation", "reconnect"}
            and set(_mapping(observations["cancellation"], "observations.cancellation"))
            == set(CANCELLATION_OBSERVATIONS)
            and set(_mapping(observations["reconnect"], "observations.reconnect")) == set(RECONNECT_OBSERVATIONS)
            and all(_mapping(value, f"gate.{key}").get("status") == "PENDING" for key, value in gates.items())
        )
        error = "M2 evidence template shape or frozen metadata is incorrect"
    except DiagnosticError as exc:
        ok = False
        error = str(exc)
    return [
        _finding(
            check="m2.evidence_template",
            code="M2_ACCEPTANCE_EVIDENCE_TEMPLATE",
            ok=ok,
            success=f"{EVIDENCE_SCHEMA} template contains all gray-box gates",
            failure=error,
            owner=Owner.QA,
            path=EVIDENCE_TEMPLATE.as_posix(),
        )
    ]


def _resolve_artifact(evidence_path: Path, value: object, label: str, root: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise DiagnosticError(f"{label} must be a relative artifact path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise DiagnosticError(f"{label} must remain below the evidence directory")
    path = (evidence_path.parent / relative).resolve()
    try:
        path.relative_to(evidence_path.parent.resolve())
    except ValueError as exc:
        raise DiagnosticError(f"{label} escapes the evidence directory") from exc
    try:
        path.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise DiagnosticError(f"{label} must remain outside the repository")
    if not path.is_file():
        raise DiagnosticError(f"{label} does not exist: {path}")
    return path


def _validate_evidence_artifact(name: str, path: Path) -> None:
    expected_suffixes = {
        "batchmode_log": {".log", ".txt"},
        "editmode_results": {".xml"},
        "handshake_transcript": {".jsonl"},
        "playmode_results": {".xml"},
        "registry_report": {".json"},
    }
    if path.suffix.lower() not in expected_suffixes[name]:
        raise DiagnosticError(f"M2 evidence.artifacts.{name} has an unexpected file type")
    if path.stat().st_size > MAX_EVIDENCE_ARTIFACT_BYTES:
        raise DiagnosticError(f"M2 evidence.artifacts.{name} exceeds the 10 MiB redacted-artifact limit")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DiagnosticError(f"M2 evidence.artifacts.{name} must be UTF-8 text: {exc}") from exc
    if not text.strip():
        raise DiagnosticError(f"M2 evidence.artifacts.{name} is empty")
    secret_detectors = detect_secret_content(text)
    if secret_detectors:
        raise DiagnosticError(f"M2 evidence.artifacts.{name} contains sensitive content: {', '.join(secret_detectors)}")
    if MACHINE_PATH_PATTERN.search(text):
        raise DiagnosticError(f"M2 evidence.artifacts.{name} contains an unredacted machine-local path")
    try:
        if name in {"editmode_results", "playmode_results"}:
            ET.fromstring(text)
        elif name == "handshake_transcript":
            for line_number, line in enumerate(text.splitlines(), start=1):
                if line.strip():
                    _mapping(json.loads(line), f"M2 handshake transcript line {line_number}")
        elif name == "registry_report":
            _mapping(json.loads(text), "M2 registry report")
    except (ET.ParseError, json.JSONDecodeError, DiagnosticError) as exc:
        raise DiagnosticError(f"M2 evidence.artifacts.{name} is malformed: {exc}") from exc


def validate_acceptance_evidence(evidence_path: Path, root: Path) -> list[Finding]:
    try:
        document = _read_json(evidence_path)
        if document.get("schema") != EVIDENCE_SCHEMA or document.get("project_name") != PROJECT_NAME:
            raise DiagnosticError("M2 evidence schema or project name mismatch")
        if document.get("accepted_m1_commit") != ACCEPTED_M1_COMMIT:
            raise DiagnosticError("M2 evidence does not reference the accepted M1 commit")
        if document.get("protocol_version") != PROTOCOL_VERSION:
            raise DiagnosticError("M2 evidence protocol version mismatch")
        if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
            raise DiagnosticError("M2 evidence catalog protocol provenance mismatch")
        if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
            raise DiagnosticError("M2 evidence negotiated protocol version mismatch")
        if document.get("unity_editor_version") != UNITY_EDITOR_VERSION:
            raise DiagnosticError("M2 evidence Unity editor version mismatch")
        source_commit = document.get("source_commit")
        if not isinstance(source_commit, str) or SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None:
            raise DiagnosticError("M2 evidence source_commit must be a full Git SHA")
        gates = _mapping(document.get("gates"), "M2 evidence.gates")
        if set(gates) != set(EVIDENCE_GATES):
            raise DiagnosticError(f"M2 evidence gates must be exactly {sorted(EVIDENCE_GATES)}")
        failed_gates = []
        for name, raw_gate in gates.items():
            gate = _mapping(raw_gate, f"M2 evidence.gates.{name}")
            if gate.get("status") != "PASS" or not isinstance(gate.get("details"), str) or not gate.get("details"):
                failed_gates.append(name)
        if failed_gates:
            raise DiagnosticError(f"M2 evidence gates are not PASS with details: {sorted(failed_gates)}")
        artifacts = _mapping(document.get("artifacts"), "M2 evidence.artifacts")
        if set(artifacts) != set(EVIDENCE_ARTIFACTS):
            raise DiagnosticError(f"M2 evidence artifacts must be exactly {sorted(EVIDENCE_ARTIFACTS)}")
        for name, value in artifacts.items():
            artifact_path = _resolve_artifact(evidence_path, value, f"M2 evidence.artifacts.{name}", root)
            _validate_evidence_artifact(name, artifact_path)
        observations = _mapping(document.get("observations"), "M2 evidence.observations")
        if set(observations) != {"cancellation", "reconnect"}:
            raise DiagnosticError("M2 evidence observations must contain cancellation and reconnect")
        cancellation = _mapping(observations["cancellation"], "M2 evidence.observations.cancellation")
        if set(cancellation) != set(CANCELLATION_OBSERVATIONS):
            raise DiagnosticError(f"M2 cancellation observations must be exactly {sorted(CANCELLATION_OBSERVATIONS)}")
        required_cancellation_true = (
            "conflicting_same_message_id_rejected_without_mutation",
            "correlation_id_equals_action_id",
            "direction_rejected_without_mutation",
            "duplicate_same_message_id_is_idempotent",
            "future_state_version_rejected_without_mutation",
        )
        if any(cancellation.get(key) is not True for key in required_cancellation_true):
            raise DiagnosticError("cancellation correlation/idempotency observations are not all true")
        if cancellation.get("direction") != "unity_to_python":
            raise DiagnosticError("movement_cancelled direction must be Unity-to-Python")
        if cancellation.get("python_authority_cancel_transaction_count") != 1:
            raise DiagnosticError("cancellation must commit exactly one Python authority transaction")
        if cancellation.get("unity_direct_authority_mutation_count") != 0:
            raise DiagnosticError("Unity cancellation report directly mutated authority")
        if cancellation.get("stale_exact_current_action_processed") is not True:
            raise DiagnosticError(
                "a stale movement_cancelled for the exact current-generation/world/action/agent/TRAVELING "
                "match was not processed"
            )
        if cancellation.get("stale_nonmatching_or_terminal_diagnostic_resync") is not True:
            raise DiagnosticError(
                "a nonmatching or terminal stale movement_cancelled did not trigger diagnostic resync"
            )
        if cancellation.get("stale_nonmatching_or_terminal_authority_transaction_count") != 0:
            raise DiagnosticError("a nonmatching or terminal stale movement_cancelled committed a transaction")
        if cancellation.get("stale_nonmatching_or_terminal_authority_mutation_count") != 0:
            raise DiagnosticError("a nonmatching or terminal stale movement_cancelled mutated authority")
        reconnect = _mapping(observations["reconnect"], "M2 evidence.observations.reconnect")
        if set(reconnect) != set(RECONNECT_OBSERVATIONS):
            raise DiagnosticError(f"M2 reconnect observations must be exactly {sorted(RECONNECT_OBSERVATIONS)}")
        required_reconnect_true = (
            "fresh_snapshot_not_older_than_last_acknowledged_version",
            "full_hello_and_registry_repeated",
            "new_client_ready_before_resume",
            "new_message_ids",
            "obsolete_generation_rejected",
        )
        if any(reconnect.get(key) is not True for key in required_reconnect_true):
            raise DiagnosticError("reconnect/resync observations are not all true")
        if reconnect.get("late_obsolete_generation_authority_mutation_count") != 0:
            raise DiagnosticError("late obsolete-generation message mutated authority")
        if "movement_cancelled" not in {item.value for item in MessageType}:
            raise DiagnosticError("movement_cancelled protocol contract is unresolved; strict M2 evidence cannot pass")
    except DiagnosticError as exc:
        return [
            Finding(
                check="m2.evidence",
                status=Status.FAIL,
                code="M2_ACCEPTANCE_EVIDENCE_INVALID",
                message=str(exc),
                owner=Owner.QA,
                path=evidence_path.as_posix(),
            )
        ]
    return [
        Finding(
            check="m2.evidence",
            status=Status.PASS,
            code="M2_ACCEPTANCE_EVIDENCE_VALID",
            message="Unity gray-box evidence has all PASS gates and external redacted artifacts",
            owner=Owner.QA,
            path=evidence_path.as_posix(),
        )
    ]


def check_unity_integration(root: Path, require_m2: bool) -> list[Finding]:
    unity_root = root / "unity"
    editor_version_path = unity_root / "ProjectSettings/ProjectVersion.txt"
    try:
        editor_text = editor_version_path.read_text(encoding="utf-8")
    except OSError as exc:
        editor_text = str(exc)
    editor_ok = f"m_EditorVersion: {UNITY_EDITOR_VERSION}" in editor_text
    findings = [
        _finding(
            check="m2.unity",
            code="M2_UNITY_EDITOR_PIN",
            ok=editor_ok,
            success=f"Unity editor remains pinned to {UNITY_EDITOR_VERSION}",
            failure=f"Unity ProjectVersion does not pin {UNITY_EDITOR_VERSION}: {editor_text}",
            owner=Owner.UNITY,
            path="unity/ProjectSettings/ProjectVersion.txt",
            remediation="Do not upgrade Unity without the accepted editor-upgrade ADR and user approval.",
        )
    ]
    cs_files = list((unity_root / "Assets/AITown").rglob("*.cs"))
    if not cs_files:
        findings.append(
            _pending(
                check="m2.unity",
                code="M2_UNITY_RUNTIME_NOT_INTEGRATED",
                message="Unity contains only the accepted empty skeleton; gray-box product execution is pending",
                owner=Owner.UNITY,
                require_m2=require_m2,
                remediation="Integrate the AITOWN-UNITY M2 bridge and batchmode tests before strict acceptance.",
            )
        )
        return findings
    requirements: tuple[tuple[str, bool], ...] = (
        ("unity/Packages/manifest.json", (unity_root / "Packages/manifest.json").is_file()),
        ("unity/Packages/packages-lock.json", (unity_root / "Packages/packages-lock.json").is_file()),
        ("Unity asmdef", any((unity_root / "Assets/AITown").rglob("*.asmdef"))),
        ("EditMode tests", any((unity_root / "Assets/AITown/Tests/EditMode").rglob("*.cs"))),
        ("PlayMode tests", any((unity_root / "Assets/AITown/Tests/PlayMode").rglob("*.cs"))),
        ("Bridge scripts", any((unity_root / "Assets/AITown/Scripts/Bridge").rglob("*.cs"))),
        ("Semantic scripts", any((unity_root / "Assets/AITown/Scripts/Semantic").rglob("*.cs"))),
        ("NPC scripts", any((unity_root / "Assets/AITown/Scripts/NPC").rglob("*.cs"))),
    )
    missing = [name for name, present in requirements if not present]
    findings.append(
        _finding(
            check="m2.unity",
            code="M2_UNITY_INTEGRATION_SURFACE",
            ok=not missing,
            success="Unity bridge, semantic/NPC scripts, package lock, assemblies, and both test modes are present",
            failure=f"partial Unity M2 integration is missing: {', '.join(missing)}",
            owner=Owner.UNITY,
            remediation="Complete the scoped Unity M2 surface; partial integration may not be reported as pending.",
        )
    )
    return findings


def run_checks(
    root: Path,
    *,
    require_m2: bool = False,
    registry_path: Path | None = None,
    evidence_path: Path | None = None,
) -> list[Finding]:
    findings = [
        *check_governance(root, require_m2),
        *check_repository_guard(root),
        *check_protocol_contract(root, require_m2),
        *check_asset_registry_fixtures(root),
        *check_evidence_template(root),
        *check_unity_integration(root, require_m2),
    ]
    if registry_path is not None:
        findings.extend(check_external_registry(root, registry_path))
    if evidence_path is not None:
        findings.extend(validate_acceptance_evidence(evidence_path, root))
    else:
        findings.append(
            _pending(
                check="m2.evidence",
                code="M2_ACCEPTANCE_EVIDENCE_PENDING",
                message="no Unity batchmode M2 acceptance evidence was supplied",
                owner=Owner.UNITY,
                require_m2=require_m2,
                remediation="Run EditMode/PlayMode gray-box acceptance and pass --evidence outside the repository.",
            )
        )
    return findings


def render_text(findings: Sequence[Finding]) -> str:
    lines: list[str] = []
    for finding in findings:
        suffix = f" [{finding.path}]" if finding.path else ""
        lines.append(f"{finding.status} {finding.code} ({finding.owner}): {finding.message}{suffix}")
        if finding.remediation:
            lines.append(f"  -> {finding.remediation}")
    counts = {status: sum(item.status is status for item in findings) for status in Status}
    lines.append("summary: " + ", ".join(f"{status.value.lower()}={counts[status]}" for status in Status))
    return "\n".join(lines)


def write_json_report(path: Path, findings: Sequence[Finding]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": REPORT_SCHEMA,
        "project_name": PROJECT_NAME,
        "accepted_m1_commit": ACCEPTED_M1_COMMIT,
        "catalog_protocol_version": CATALOG_PROTOCOL_VERSION,
        "negotiated_protocol_version": PROTOCOL_VERSION,
        "findings": [asdict(finding) for finding in findings],
        "summary": {status.value.lower(): sum(item.status is status for item in findings) for status in Status},
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root; auto-detected by default")
    parser.add_argument("--registry", type=Path, help="validate an exported asset_registry message")
    parser.add_argument("--evidence", type=Path, help="validate Unity batchmode M2 acceptance evidence")
    parser.add_argument("--require-m2", action="store_true", help="convert every unresolved M2 gate to failure")
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve() if args.root else find_repository_root(Path(__file__))
    findings = run_checks(
        root,
        require_m2=args.require_m2,
        registry_path=args.registry.resolve() if args.registry else None,
        evidence_path=args.evidence.resolve() if args.evidence else None,
    )
    print(render_text(findings))
    if args.json_output:
        write_json_report(args.json_output.resolve(), findings)
    return 1 if any(finding.status is Status.FAIL for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
