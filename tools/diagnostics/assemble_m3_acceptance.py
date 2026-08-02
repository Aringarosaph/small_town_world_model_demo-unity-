"""Assemble strict M3 acceptance evidence from real external owner bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_IMPORT_ROOT, REPOSITORY_IMPORT_ROOT / "python"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from tools.diagnostics import check_m3 as m3
from tools.diagnostics.run_m3_regressions import (
    RegressionError,
    copy_regression_attestation,
    validate_regression_finding_artifact,
)

ASSEMBLY_SCHEMA = "stwm.qa.m3-acceptance-assembly/v1"
SIM_BUNDLE_SCHEMA = "stwm.simulation.m3-release-bundle/v1"
UNITY_BUNDLE_SCHEMA = "stwm.unity.m3-partial-acceptance-evidence/v1"

SIM_ARTIFACTS = (
    "authority_evidence",
    "behavior_matrix_report",
    "soak_7_day_report",
    "soak_30_day_report",
    "replay_report",
    "pathology_report",
    "performance_report",
)
UNITY_ARTIFACTS = (
    "full_registry",
    "registry_report",
    "unity_semantic_report",
    "debug_trace",
    "editmode_results",
    "playmode_results",
    "batchmode_log",
)
SIM_MATRIX_KEYS = (
    "catalog_surface",
    "agent_liveness",
    "household_economy",
    "relationship_summary",
    "knowledge_permissions",
    "joint_action",
    "determinism",
    "soak_runs",
    "pathology",
    "performance",
)
SIM_BEHAVIOR_PROBES = m3.BEHAVIOR_PROBES[:-1]
PROBE_RESULT_KEYS = ("status", "test_ids", "assertion_count")
SIM_AUTHORITY_PROBES = (
    "knowledge_unknown_share_rejected",
    "joint_action_cancel_release",
    "joint_action_failure_release",
    "joint_action_timeout_release",
)
UNITY_PROJECTION_KEYS = ("unity", "behavior_presentation")
UNITY_PRESENTATION_KEYS = ("behavior_id", "fixture_id", "unity_presentation")

REPOSITORY_PASS_CODES = frozenset(
    {
        "M3_ACCEPTED_M2_BASELINE",
        "M3_EXECUTION_BASELINE",
        "M3_ADR_0011",
        "M3_SENSITIVE_FILE_GUARD",
        "M3_UNITY_CACHE_GUARD",
        "M3_EXTERNAL_ARTIFACT_REPOSITORY_GUARD",
        "M3_CATALOG_SURFACE",
        "M3_RELEASE_PROFILE",
        "M3_TARGETED_BEHAVIOR_MATRIX",
        "M3_FULL_REGISTRY_PROFILE",
        "M3_QA_SCHEMA_TEMPLATE",
        "M3_PROTOCOL_0_3",
        "M3_SHARED_SEMANTIC_MANIFEST",
        "M3_SIM_QA_ADAPTER",
        "M3_UNITY_EVIDENCE_EXPORTER",
        "M3_UNITY_FUNCTIONAL_GRAYBOX",
        "M3_FULL_REGISTRY_VALID",
        "M3_M0_M2_REGRESSIONS",
    }
)
ALLOWED_REPOSITORY_PENDING_CODES = frozenset({"M3_ACCEPTANCE_EVIDENCE_PENDING"})

SIM_BUNDLE_KEYS = (
    "schema",
    "project_name",
    "source_commit",
    "generated_at_utc",
    "profile",
    "complete",
    "artifacts",
    "explicitly_not_generated",
)
UNITY_BUNDLE_BASE_KEYS = (
    "schema",
    "project_name",
    "source_commit",
    "generated_at_utc",
    "accepted_m2_commit",
    "catalog_protocol_version",
    "negotiated_protocol_version",
    "unity_editor_version",
    "status",
    "acceptance_eligible",
    "pending_reasons",
    "gates",
    "unity_test_summary",
    "artifacts",
)


@dataclass
class Assessment:
    """Mutable audit state used while validating independently-owned inputs."""

    missing_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def missing(self, message: str) -> None:
        if message not in self.missing_fields:
            self.missing_fields.append(message)

    def error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)


@dataclass(frozen=True)
class OwnerBundle:
    source_commit: str
    artifact_paths: Mapping[str, Path]
    artifact_descriptors: Mapping[str, Mapping[str, object]]
    matrices: Mapping[str, object]
    behavior_rows: Sequence[Mapping[str, object]] = ()


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise m3.DiagnosticError(f"{label} is unreadable or malformed: {exc}") from exc
    if not isinstance(value, dict):
        raise m3.DiagnosticError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _exact_keys(value: Mapping[str, object], keys: Sequence[str], label: str) -> None:
    expected = set(keys)
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise m3.DiagnosticError(f"{label} keys differ; missing={missing}, extra={extra}")


def _external_file(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise m3.DiagnosticError(f"{label} does not exist: {resolved}")
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return resolved
    raise m3.DiagnosticError(f"{label} must remain outside the repository")


def _external_output(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise m3.DiagnosticError("output_root must remain outside the repository")
    if resolved.exists():
        raise m3.DiagnosticError(f"output_root already exists: {resolved}")
    return resolved


def _source_commit(value: object, label: str) -> str:
    if not isinstance(value, str) or m3.SOURCE_COMMIT_PATTERN.fullmatch(value) is None:
        raise m3.DiagnosticError(f"{label} must be a full lowercase Git SHA")
    return value


def _artifact_inputs(
    *,
    bundle_path: Path,
    root: Path,
    raw_artifacts: object,
    required_names: Sequence[str],
    exact: bool,
    assessment: Assessment | None = None,
) -> tuple[dict[str, Path], dict[str, Mapping[str, object]]]:
    artifacts = m3._mapping(raw_artifacts, f"{bundle_path.name}.artifacts")
    required = set(required_names)
    if exact and set(artifacts) != required:
        raise m3.DiagnosticError(
            f"{bundle_path.name}.artifacts must be exact {sorted(required)}; observed={sorted(artifacts)}"
        )
    missing = required - set(artifacts)
    if missing:
        raise m3.DiagnosticError(f"{bundle_path.name}.artifacts missing {sorted(missing)}")
    paths: dict[str, Path] = {}
    descriptors: dict[str, Mapping[str, object]] = {}
    for name in required_names:
        raw_descriptor = artifacts[name]
        try:
            m3._validate_artifact(name, raw_descriptor, bundle_path, root)
            descriptor = m3._mapping(raw_descriptor, f"artifact {name}")
            paths[name] = m3._artifact_path(bundle_path, descriptor, f"artifact {name}", root)
            descriptors[name] = descriptor
        except (m3.DiagnosticError, OSError) as exc:
            if assessment is None:
                raise
            assessment.error(str(exc))
    return paths, descriptors


def _probe_passed(raw: object, label: str, assessment: Assessment) -> bool:
    if raw is None:
        assessment.missing(label)
        return False
    if not isinstance(raw, dict):
        assessment.error(f"{label} must be a probe-result object")
        return False
    value = cast(dict[str, object], raw)
    try:
        _exact_keys(value, PROBE_RESULT_KEYS, label)
    except m3.DiagnosticError as exc:
        assessment.error(str(exc))
        return False
    status = value.get("status")
    if status == "FAIL":
        assessment.error(f"{label} reports FAIL")
        return False
    if status != "PASS":
        assessment.missing(f"{label} has status {status!r}; PASS is required")
        return False
    test_ids = value.get("test_ids")
    if (
        not isinstance(test_ids, list)
        or not test_ids
        or any(not isinstance(item, str) or not item.strip() for item in test_ids)
    ):
        assessment.error(f"{label}.test_ids must be a non-empty string array")
        return False
    assertion_count = value.get("assertion_count")
    if not isinstance(assertion_count, int) or isinstance(assertion_count, bool) or assertion_count <= 0:
        assessment.error(f"{label}.assertion_count must be a positive integer")
        return False
    return True


def _validate_sim_projection(matrices: Mapping[str, object], assessment: Assessment) -> None:
    validations: list[tuple[str, Callable[[], None]]] = []
    if "catalog_surface" in matrices:
        validations.append(
            (
                "catalog_surface",
                lambda: m3._validate_catalog_matrix(m3._mapping(matrices["catalog_surface"], "catalog_surface")),
            )
        )
    if "agent_liveness" in matrices:
        validations.append(
            (
                "agent_liveness",
                lambda: m3._validate_agent_liveness(m3._sequence(matrices["agent_liveness"], "agent_liveness")),
            )
        )
    if "household_economy" in matrices:
        validations.append(
            (
                "household_economy",
                lambda: m3._validate_household_economy(
                    m3._sequence(matrices["household_economy"], "household_economy")
                ),
            )
        )
    if {"relationship_summary", "knowledge_permissions", "joint_action"} <= set(matrices):
        validations.append(("social matrices", lambda: m3._validate_social_matrices(matrices)))
    if {"determinism", "soak_runs"} <= set(matrices):
        validations.append(("determinism/soak", lambda: m3._validate_determinism(matrices)))
    if "pathology" in matrices:
        validations.append(
            ("pathology", lambda: m3._validate_pathology(m3._mapping(matrices["pathology"], "pathology")))
        )
    if "performance" in matrices:
        validations.append(
            ("performance", lambda: m3._validate_performance(m3._mapping(matrices["performance"], "performance")))
        )
    for label, action in validations:
        try:
            action()
        except (m3.DiagnosticError, KeyError) as exc:
            assessment.error(f"SIM {label} projection invalid: {exc}")


def _load_sim_bundle(path: Path, root: Path, assessment: Assessment) -> OwnerBundle | None:
    try:
        bundle_path = _external_file(path, root, "SIM bundle")
        bundle = _read_json(bundle_path, "SIM bundle")
        _exact_keys(bundle, SIM_BUNDLE_KEYS, "SIM bundle")
        if bundle.get("schema") != SIM_BUNDLE_SCHEMA or bundle.get("project_name") != m3.PROJECT_NAME:
            raise m3.DiagnosticError("SIM bundle schema/project mismatch")
        if bundle.get("profile") != "M3_RELEASE_SOCIETY":
            raise m3.DiagnosticError("SIM bundle profile must be M3_RELEASE_SOCIETY")
        source_commit = _source_commit(bundle.get("source_commit"), "SIM bundle source_commit")
        if bundle.get("complete") is not True:
            assessment.missing("SIM release bundle complete=true")
        paths, descriptors = _artifact_inputs(
            bundle_path=bundle_path,
            root=root,
            raw_artifacts=bundle.get("artifacts"),
            required_names=SIM_ARTIFACTS,
            exact=True,
        )
        authority = _read_json(paths["authority_evidence"], "SIM authority evidence")
        behavior_report = _read_json(paths["behavior_matrix_report"], "SIM behavior report")
        if authority.get("source_commit") != source_commit or behavior_report.get("source_commit") != source_commit:
            raise m3.DiagnosticError("SIM artifact source_commit differs from its bundle")
    except (m3.DiagnosticError, OSError) as exc:
        assessment.error(str(exc))
        return None

    matrices: dict[str, object] = {}
    raw_projection = authority.get("qa_matrix_projection")
    if raw_projection is None:
        assessment.missing("SIM authority_evidence.qa_matrix_projection")
        projection: Mapping[str, object] = {}
    elif not isinstance(raw_projection, dict):
        assessment.error("SIM authority_evidence.qa_matrix_projection must be an object")
        projection = {}
    else:
        projection = cast(dict[str, object], raw_projection)
        extra_projection_keys = set(projection) - set(SIM_MATRIX_KEYS)
        if extra_projection_keys:
            assessment.error(f"SIM qa_matrix_projection has unexpected keys {sorted(extra_projection_keys)}")
    for name in SIM_MATRIX_KEYS:
        if name not in projection or projection[name] is None:
            assessment.missing(f"SIM authority_evidence.qa_matrix_projection.{name}")
        else:
            matrices[name] = projection[name]

    raw_probe_evidence = authority.get("qa_probe_evidence")
    if raw_probe_evidence is None:
        for name in SIM_AUTHORITY_PROBES:
            assessment.missing(f"SIM authority_evidence.qa_probe_evidence.{name}")
        probe_evidence: Mapping[str, object] = {}
    elif not isinstance(raw_probe_evidence, dict):
        assessment.error("SIM authority_evidence.qa_probe_evidence must be an object")
        probe_evidence = {}
    else:
        probe_evidence = cast(dict[str, object], raw_probe_evidence)
        try:
            _exact_keys(probe_evidence, SIM_AUTHORITY_PROBES, "SIM authority_evidence.qa_probe_evidence")
        except m3.DiagnosticError as exc:
            assessment.error(str(exc))
    authority_probe_pass = {
        name: _probe_passed(
            probe_evidence.get(name),
            f"SIM authority_evidence.qa_probe_evidence.{name}",
            assessment,
        )
        for name in SIM_AUTHORITY_PROBES
    }
    knowledge = matrices.get("knowledge_permissions")
    if (
        isinstance(knowledge, dict)
        and authority_probe_pass["knowledge_unknown_share_rejected"]
        and knowledge.get("unknown_share_rejected") is not True
    ):
        assessment.error("SIM knowledge unknown-share probe PASS disagrees with qa_matrix_projection")
    joint = matrices.get("joint_action")
    joint_fields = {
        "joint_action_cancel_release": "cancel_release",
        "joint_action_failure_release": "failure_release",
        "joint_action_timeout_release": "timeout_release",
    }
    if isinstance(joint, dict):
        for probe_name, matrix_name in joint_fields.items():
            if authority_probe_pass[probe_name] and joint.get(matrix_name) is not True:
                assessment.error(f"SIM {probe_name} PASS disagrees with joint_action.{matrix_name}")

    raw_cases = behavior_report.get("cases")
    if not isinstance(raw_cases, list):
        assessment.error("SIM behavior_matrix_report.cases must be an array")
        cases: Sequence[object] = ()
    else:
        cases = raw_cases
    behavior_rows: list[Mapping[str, object]] = []
    observed_ids: list[str] = []
    case_keys = (
        "behavior_id",
        "fixture_id",
        "sim_targeted_probe_owner",
        "sim_targeted_probe_results",
        "release_soak_occurrence_count",
        "unity_presentation",
        "unity_presentation_owner",
        "run_refs",
    )
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            assessment.error(f"SIM behavior case {index} must be an object")
            continue
        case = cast(dict[str, object], raw_case)
        try:
            _exact_keys(case, case_keys, f"SIM behavior case {index}")
        except m3.DiagnosticError as exc:
            assessment.error(str(exc))
            continue
        behavior_id = case.get("behavior_id")
        if not isinstance(behavior_id, str):
            assessment.error(f"SIM behavior case {index}.behavior_id must be a string")
            continue
        observed_ids.append(behavior_id)
        if case.get("fixture_id") != f"m3_behavior_{behavior_id}":
            assessment.error(f"SIM behavior {behavior_id} fixture_id mismatch")
        if case.get("sim_targeted_probe_owner") != "SIM_FAST_TARGETED_FIXTURES":
            assessment.error(f"SIM behavior {behavior_id} targeted probe owner mismatch")
        if case.get("unity_presentation") is not None or case.get("unity_presentation_owner") != "UNITY":
            assessment.error(f"SIM behavior {behavior_id} may not assert the Unity presentation fact")
        count = case.get("release_soak_occurrence_count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            assessment.error(f"SIM behavior {behavior_id} has no positive release-soak occurrence")
            count = 0
        raw_results = case.get("sim_targeted_probe_results")
        if raw_results is None:
            assessment.missing(f"SIM behavior {behavior_id} targeted probe results")
            results: Mapping[str, object] = {}
        elif not isinstance(raw_results, dict):
            assessment.error(f"SIM behavior {behavior_id} targeted probe results must be an object")
            results = {}
        else:
            results = cast(dict[str, object], raw_results)
            try:
                _exact_keys(results, SIM_BEHAVIOR_PROBES, f"SIM behavior {behavior_id} targeted probe results")
            except m3.DiagnosticError as exc:
                assessment.error(str(exc))
        probe_values = {
            probe: _probe_passed(
                results.get(probe),
                f"SIM behavior {behavior_id} targeted probe {probe}",
                assessment,
            )
            for probe in SIM_BEHAVIOR_PROBES
        }
        behavior_rows.append(
            {
                "behavior_id": behavior_id,
                "fixture_id": f"m3_behavior_{behavior_id}",
                **probe_values,
                "release_soak_occurrence_count": count,
            }
        )
    if tuple(observed_ids) != m3.BEHAVIOR_IDS:
        assessment.error("SIM behavior cases must contain the exact ordered 22 behavior IDs")
    _validate_sim_projection(matrices, assessment)
    return OwnerBundle(source_commit, paths, descriptors, matrices, behavior_rows)


def _load_unity_bundle(path: Path, root: Path, assessment: Assessment) -> OwnerBundle | None:
    try:
        bundle_path = _external_file(path, root, "Unity bundle")
        bundle = _read_json(bundle_path, "Unity bundle")
        allowed_keys = set(UNITY_BUNDLE_BASE_KEYS) | {"qa_matrix_projection"}
        if set(bundle) not in (set(UNITY_BUNDLE_BASE_KEYS), allowed_keys):
            missing = sorted(set(UNITY_BUNDLE_BASE_KEYS) - set(bundle))
            extra = sorted(set(bundle) - allowed_keys)
            raise m3.DiagnosticError(f"Unity bundle keys differ; missing={missing}, extra={extra}")
        if bundle.get("schema") != UNITY_BUNDLE_SCHEMA or bundle.get("project_name") != m3.PROJECT_NAME:
            raise m3.DiagnosticError("Unity bundle schema/project mismatch")
        source_commit = _source_commit(bundle.get("source_commit"), "Unity bundle source_commit")
        expected_provenance = (
            bundle.get("accepted_m2_commit"),
            bundle.get("catalog_protocol_version"),
            bundle.get("negotiated_protocol_version"),
            bundle.get("unity_editor_version"),
        )
        if expected_provenance != (
            m3.ACCEPTED_M2_COMMIT,
            m3.CATALOG_PROTOCOL_VERSION,
            m3.PROTOCOL_VERSION,
            m3.UNITY_EDITOR_VERSION,
        ):
            raise m3.DiagnosticError("Unity bundle protocol/catalog/editor provenance mismatch")
        if bundle.get("status") == "FAIL":
            raise m3.DiagnosticError("Unity bundle reports FAIL")
        if bundle.get("status") not in {"PASS", "PENDING"}:
            raise m3.DiagnosticError("Unity bundle status must be PASS or PENDING")
    except (m3.DiagnosticError, OSError) as exc:
        assessment.error(str(exc))
        return None
    try:
        paths, descriptors = _artifact_inputs(
            bundle_path=bundle_path,
            root=root,
            raw_artifacts=bundle.get("artifacts"),
            required_names=UNITY_ARTIFACTS,
            exact=False,
            assessment=assessment,
        )
    except (m3.DiagnosticError, OSError) as exc:
        assessment.error(str(exc))
        paths = {}
        descriptors = {}

    gates = bundle.get("gates")
    required_unity_gates = (
        "protocol_0_3_live",
        "full_registry",
        "structured_presentation",
        "unity_semantics",
        "editmode",
        "playmode_live",
    )
    if not isinstance(gates, dict):
        assessment.error("Unity bundle.gates must be an object")
    else:
        for name in required_unity_gates:
            gate = gates.get(name)
            if not isinstance(gate, dict):
                assessment.missing(f"Unity bundle.gates.{name}")
            elif gate.get("status") == "FAIL":
                assessment.error(f"Unity bundle.gates.{name} reports FAIL")
            elif gate.get("status") != "PASS":
                assessment.missing(f"Unity bundle.gates.{name} PASS")

    raw_projection = bundle.get("qa_matrix_projection")
    if raw_projection is None:
        assessment.missing("Unity bundle.qa_matrix_projection.unity")
        assessment.missing("Unity bundle.qa_matrix_projection.behavior_presentation")
        projection: Mapping[str, object] = {}
    elif not isinstance(raw_projection, dict):
        assessment.error("Unity bundle.qa_matrix_projection must be an object")
        projection = {}
    else:
        projection = cast(dict[str, object], raw_projection)
        try:
            _exact_keys(projection, UNITY_PROJECTION_KEYS, "Unity bundle.qa_matrix_projection")
        except m3.DiagnosticError as exc:
            assessment.error(str(exc))
    matrices: dict[str, object] = {}
    if projection.get("unity") is None:
        assessment.missing("Unity bundle.qa_matrix_projection.unity")
    else:
        matrices["unity"] = projection["unity"]
        try:
            m3._validate_unity(m3._mapping(projection["unity"], "Unity qa_matrix_projection.unity"))
        except m3.DiagnosticError as exc:
            assessment.error(f"Unity matrix projection invalid: {exc}")

    summary = bundle.get("unity_test_summary")
    if not isinstance(summary, dict):
        assessment.error("Unity bundle.unity_test_summary must be an object")
    else:
        for mode in ("editmode", "playmode"):
            raw_mode = summary.get(mode)
            if not isinstance(raw_mode, dict):
                assessment.error(f"Unity bundle.unity_test_summary.{mode} must be an object")
                continue
            total = raw_mode.get("total")
            passed = raw_mode.get("passed")
            if (
                not isinstance(total, int)
                or isinstance(total, bool)
                or total <= 0
                or passed != total
                or any(raw_mode.get(key) != 0 for key in ("failed", "skipped", "inconclusive"))
            ):
                assessment.error(f"Unity bundle.unity_test_summary.{mode} is not a zero-skip PASS run")
        unity_matrix = matrices.get("unity")
        if isinstance(unity_matrix, dict):
            editmode = summary.get("editmode")
            playmode = summary.get("playmode")
            if isinstance(editmode, dict) and unity_matrix.get("editmode_skipped") != editmode.get("skipped"):
                assessment.error("Unity matrix editmode_skipped disagrees with unity_test_summary")
            if isinstance(playmode, dict) and unity_matrix.get("playmode_skipped") != playmode.get("skipped"):
                assessment.error("Unity matrix playmode_skipped disagrees with unity_test_summary")

    raw_presentations = projection.get("behavior_presentation")
    if raw_presentations is None:
        assessment.missing("Unity bundle.qa_matrix_projection.behavior_presentation")
        presentations: Sequence[object] = ()
    elif not isinstance(raw_presentations, list):
        assessment.error("Unity behavior_presentation must be an array")
        presentations = ()
    else:
        presentations = raw_presentations
    behavior_rows: list[Mapping[str, object]] = []
    observed_ids: list[str] = []
    for index, raw_item in enumerate(presentations):
        if not isinstance(raw_item, dict):
            assessment.error(f"Unity behavior presentation {index} must be an object")
            continue
        item = cast(dict[str, object], raw_item)
        try:
            _exact_keys(item, UNITY_PRESENTATION_KEYS, f"Unity behavior presentation {index}")
        except m3.DiagnosticError as exc:
            assessment.error(str(exc))
            continue
        behavior_id = item.get("behavior_id")
        if not isinstance(behavior_id, str):
            assessment.error(f"Unity behavior presentation {index}.behavior_id must be a string")
            continue
        observed_ids.append(behavior_id)
        if item.get("fixture_id") != f"m3_behavior_{behavior_id}":
            assessment.error(f"Unity behavior {behavior_id} fixture_id mismatch")
        passed = _probe_passed(
            item.get("unity_presentation"),
            f"Unity behavior {behavior_id} presentation probe",
            assessment,
        )
        behavior_rows.append({"behavior_id": behavior_id, "unity_presentation": passed})
    if presentations and tuple(observed_ids) != m3.BEHAVIOR_IDS:
        assessment.error("Unity behavior presentation must contain the exact ordered 22 behavior IDs")
    return OwnerBundle(source_commit, paths, descriptors, matrices, behavior_rows)


def _load_repository_report(
    path: Path,
    root: Path,
    assessment: Assessment,
) -> tuple[str, Path, Mapping[str, object]] | None:
    try:
        report_path = _external_file(path, root, "repository report")
        report = _read_json(report_path, "repository report")
        m3.validate_readiness_document(report)
        source_commit = _source_commit(report.get("source_commit"), "repository report source_commit")
    except (m3.DiagnosticError, OSError) as exc:
        assessment.error(str(exc))
        return None
    findings = cast(Sequence[object], report["findings"])
    status_by_code: dict[str, str] = {}
    for raw in findings:
        finding = cast(Mapping[str, object], raw)
        code = cast(str, finding["code"])
        status = cast(str, finding["status"])
        status_by_code[code] = status
        if status == "FAIL":
            assessment.error(f"repository report {code} reports FAIL")
        elif status == "PENDING" and code not in ALLOWED_REPOSITORY_PENDING_CODES:
            assessment.missing(f"repository report {code} PASS")
        if code == "M3_M0_M2_REGRESSIONS" and status == "PASS":
            try:
                validate_regression_finding_artifact(report_path, finding, root)
            except (RegressionError, OSError) as exc:
                assessment.error(f"repository regression finding is not executable evidence: {exc}")
    for code in sorted(REPOSITORY_PASS_CODES):
        observed_status = status_by_code.get(code)
        if observed_status == "FAIL":
            continue
        if observed_status != "PASS":
            assessment.missing(f"repository report finding {code}=PASS")
    raw = report_path.read_bytes()
    descriptor: Mapping[str, object] = {
        "path": report_path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "redacted": True,
        "schema": m3.READINESS_SCHEMA,
    }
    m3._validate_artifact("repository_report", descriptor, report_path, root)
    return source_commit, report_path, descriptor


def _merge_behavior_rows(
    sim_rows: Sequence[Mapping[str, object]],
    unity_rows: Sequence[Mapping[str, object]],
    assessment: Assessment,
) -> list[Mapping[str, object]]:
    if len(sim_rows) != len(m3.BEHAVIOR_IDS) or len(unity_rows) != len(m3.BEHAVIOR_IDS):
        return []
    merged: list[Mapping[str, object]] = []
    for sim_row, unity_row, expected_id in zip(sim_rows, unity_rows, m3.BEHAVIOR_IDS, strict=True):
        if sim_row.get("behavior_id") != expected_id or unity_row.get("behavior_id") != expected_id:
            assessment.error(f"SIM/Unity behavior projection order differs at {expected_id}")
            continue
        merged.append({**sim_row, "unity_presentation": unity_row.get("unity_presentation")})
    return merged


def _gate_document() -> dict[str, Mapping[str, str]]:
    return {
        name: {
            "status": "PASS",
            "details": "verified by exact assembly of hashed external SIM, Unity, and repository evidence",
        }
        for name in m3.EVIDENCE_GATES
    }


def _write_complete_bundle(
    *,
    root: Path,
    output_root: Path,
    source_commit: str,
    matrices: Mapping[str, object],
    artifact_sources: Mapping[str, Path],
) -> Path:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        artifact_root = temporary_root / "artifacts"
        artifact_root.mkdir()
        document = _read_json(root / m3.EVIDENCE_TEMPLATE, "M3 acceptance evidence template")
        document["source_commit"] = source_commit
        document["gates"] = _gate_document()
        document["matrices"] = dict(matrices)
        descriptors: dict[str, Mapping[str, object]] = {}
        for name, (suffixes, schema) in m3.ARTIFACT_SCHEMAS.items():
            source = artifact_sources[name]
            suffix = source.suffix.lower()
            if suffix not in suffixes:
                raise m3.DiagnosticError(f"artifact {name} suffix changed during assembly")
            destination = artifact_root / f"{name}{suffix}"
            shutil.copyfile(source, destination)
            if name == "repository_report":
                repository_document = _read_json(source, "M3 repository report")
                regression_finding = next(
                    (
                        cast(Mapping[str, object], raw)
                        for raw in m3._sequence(repository_document["findings"], "repository findings")
                        if cast(Mapping[str, object], raw).get("code") == "M3_M0_M2_REGRESSIONS"
                    ),
                    None,
                )
                if regression_finding is None:
                    raise m3.DiagnosticError("repository report lacks the bound M0/M1/M2 regression finding")
                copy_regression_attestation(
                    repository_report_path=source,
                    finding=regression_finding,
                    destination_report_path=destination,
                    root=root,
                )
            raw = destination.read_bytes()
            descriptors[name] = {
                "path": destination.relative_to(temporary_root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "redacted": True,
                "schema": schema,
            }
        document["artifacts"] = descriptors
        evidence_path = temporary_root / "m3-acceptance-evidence.json"
        evidence_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        findings = m3.validate_acceptance_evidence(evidence_path, root)
        if len(findings) != 1 or findings[0].status is not m3.Status.PASS:
            message = findings[0].message if findings else "validator returned no finding"
            raise m3.DiagnosticError(f"assembled evidence failed the exact validator: {message}")
        temporary_root.replace(output_root)
        return output_root / evidence_path.name
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def assemble_acceptance(
    *,
    root: Path,
    sim_bundle_path: Path,
    unity_bundle_path: Path,
    repository_report_path: Path,
    output_root: Path,
    require_complete: bool = False,
) -> Mapping[str, object]:
    """Audit inputs and atomically write final evidence only when they are complete."""

    assessment = Assessment()
    try:
        final_output_root = _external_output(output_root, root)
    except m3.DiagnosticError as exc:
        assessment.error(str(exc))
        final_output_root = output_root.resolve()
    sim = _load_sim_bundle(sim_bundle_path, root, assessment)
    unity = _load_unity_bundle(unity_bundle_path, root, assessment)
    repository = _load_repository_report(repository_report_path, root, assessment)

    repository_source: str | None = None
    repository_path: Path | None = None
    repository_descriptor: Mapping[str, object] | None = None
    if repository is not None:
        repository_source, repository_path, repository_descriptor = repository
    if sim is not None and repository_source is not None and sim.source_commit != repository_source:
        assessment.error("SIM bundle source_commit differs from repository report source_commit")
    if unity is not None and repository_source is not None and unity.source_commit != repository_source:
        assessment.error("Unity bundle source_commit differs from repository report source_commit")

    matrices: dict[str, object] = {}
    artifact_sources: dict[str, Path] = {}
    if sim is not None:
        matrices.update(sim.matrices)
        artifact_sources.update(sim.artifact_paths)
    if unity is not None:
        matrices.update(unity.matrices)
        artifact_sources.update(unity.artifact_paths)
    if sim is not None and unity is not None:
        behavior_rows = _merge_behavior_rows(sim.behavior_rows, unity.behavior_rows, assessment)
        if behavior_rows:
            matrices["behavior_coverage"] = behavior_rows
    if repository_path is not None and repository_descriptor is not None:
        artifact_sources["repository_report"] = repository_path

    expected_matrices = set(m3.MATRIX_KEYS)
    for name in sorted(expected_matrices - set(matrices)):
        assessment.missing(f"final matrices.{name}")
    expected_artifacts = set(m3.ARTIFACT_SCHEMAS)
    for name in sorted(expected_artifacts - set(artifact_sources)):
        assessment.missing(f"final artifacts.{name}")

    evidence_path: Path | None = None
    if not assessment.errors and not assessment.missing_fields and repository_source is not None:
        try:
            evidence_path = _write_complete_bundle(
                root=root,
                output_root=final_output_root,
                source_commit=repository_source,
                matrices=matrices,
                artifact_sources=artifact_sources,
            )
        except (m3.DiagnosticError, OSError) as exc:
            assessment.error(str(exc))

    if assessment.errors or (require_complete and assessment.missing_fields):
        status = "FAIL"
    elif assessment.missing_fields:
        status = "PENDING"
    else:
        status = "PASS"
    return {
        "schema": ASSEMBLY_SCHEMA,
        "status": status,
        "require_complete": require_complete,
        "source_commit": repository_source,
        "inputs": {
            "sim_bundle": sim_bundle_path.resolve().as_posix(),
            "unity_bundle": unity_bundle_path.resolve().as_posix(),
            "repository_report": repository_report_path.resolve().as_posix(),
        },
        "missing_fields": sorted(assessment.missing_fields),
        "errors": sorted(assessment.errors),
        "output": evidence_path.as_posix() if evidence_path is not None else None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit and assemble real external SIM, Unity, and repository M3 release evidence"
    )
    parser.add_argument("--sim-bundle", required=True, type=Path)
    parser.add_argument("--unity-bundle", required=True, type=Path)
    parser.add_argument("--repository-report", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    result = assemble_acceptance(
        root=root,
        sim_bundle_path=args.sim_bundle,
        unity_bundle_path=args.unity_bundle,
        repository_report_path=args.repository_report,
        output_root=args.output_root,
        require_complete=args.require_complete,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
