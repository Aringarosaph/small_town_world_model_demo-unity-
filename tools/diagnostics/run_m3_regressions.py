"""Run the frozen M0/M1/M2 strict lane and attest it in M3 readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_IMPORT_ROOT, REPOSITORY_IMPORT_ROOT / "python"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from tools.diagnostics import check_m1, check_m2, check_m3

SCHEMA = "stwm.qa.m3-regression-run/v1"
FINDING_CODE = "M3_M0_M2_REGRESSIONS"
FINDING_CHECK = "m3.regression"
STEP_IDS = (
    "m0_diagnostics",
    "m0_tests",
    "m1_diagnostics",
    "m1_tests",
    "m2_diagnostics",
    "m2_tests",
)
DESCRIPTOR_KEYS = ("path", "sha256", "bytes", "redacted", "schema")
INPUT_BINDING_KEYS = ("input_id", "sha256", "bytes", "schema", "source_commit")
STEP_KEYS = ("step_id", "command", "exit_code", "status", "report", "junit", "log")
MANIFEST_KEYS = (
    "schema",
    "project_name",
    "source_commit",
    "python_version",
    "status",
    "ordered_step_ids",
    "steps",
    "m1_evidence",
    "m2_input_bindings",
)
FINDING_MESSAGE_PATTERN = re.compile(
    r"^frozen M0/M1/M2 strict lane (passed|failed); manifest_sha256=([0-9a-f]{64}); manifest_bytes=([1-9][0-9]*)$"
)
USER_PATH_PATTERN = re.compile(r"(?:/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:\\Users\\[^\s\"']+)")
MAX_LOG_CHARS = 1_000_000


class RegressionError(ValueError):
    """Raised for an invalid lane input, output, or attestation."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


ProcessRunner = Callable[[Sequence[str], Path, Mapping[str, str], int], ProcessResult]


@dataclass(frozen=True)
class CommandSpec:
    step_id: str
    argv: tuple[str, ...]
    report_path: Path | None
    report_schema: str | None
    junit_path: Path | None
    environment: Mapping[str, str]


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegressionError(f"{label} is unreadable or malformed: {exc}") from exc
    if not isinstance(value, dict):
        raise RegressionError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: Sequence[str], label: str) -> None:
    if set(value) != set(expected):
        raise RegressionError(
            f"{label} keys differ; missing={sorted(set(expected) - set(value))}, "
            f"extra={sorted(set(value) - set(expected))}"
        )


def _repository_head(root: Path) -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(value) is None:
        raise RegressionError("could not resolve the repository source commit")
    return value


def _external_file(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise RegressionError(f"{label} does not exist: {resolved}")
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return resolved
    raise RegressionError(f"{label} must remain outside the repository")


def _preflight_report(path: Path, root: Path, source_commit: str) -> dict[str, object]:
    report_path = _external_file(path, root, "M3 repository report")
    report = _read_json(report_path, "M3 repository report")
    try:
        check_m3.validate_readiness_document(report)
    except check_m3.DiagnosticError as exc:
        raise RegressionError(str(exc)) from exc
    if report.get("source_commit") != source_commit:
        raise RegressionError("repository report source_commit must equal the checked-out repository HEAD")
    findings = cast(Sequence[object], report["findings"])
    blockers = [
        cast(Mapping[str, object], raw)
        for raw in findings
        if cast(Mapping[str, object], raw).get("status") == "FAIL"
        or (
            cast(Mapping[str, object], raw).get("status") == "PENDING"
            and cast(Mapping[str, object], raw).get("code") != "M3_ACCEPTANCE_EVIDENCE_PENDING"
        )
    ]
    if blockers:
        codes = [str(item.get("code")) for item in blockers]
        raise RegressionError(f"repository report has pre-existing blocking findings: {codes}")
    return report


def _preflight_output_root(output_root: Path, report_path: Path, root: Path) -> Path:
    resolved = output_root.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise RegressionError("regression output_root must remain outside the repository")
    try:
        resolved.relative_to(report_path.resolve().parent)
    except ValueError as exc:
        raise RegressionError("regression output_root must be below the repository report directory") from exc
    if resolved.exists():
        raise RegressionError(f"regression output_root already exists: {resolved}")
    return resolved


def _default_runner(argv: Sequence[str], cwd: Path, environment: Mapping[str, str], timeout: int) -> ProcessResult:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=dict(environment),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ProcessResult(124, stdout, f"{stderr}\ncommand timed out after {timeout} seconds")
    except OSError as exc:
        return ProcessResult(126, "", f"could not execute command: {exc}")
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _sanitize_text(text: str, replacements: Mapping[str, str]) -> str:
    sanitized = text
    for source, replacement in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if source:
            sanitized = sanitized.replace(source, replacement)
    sanitized = check_m3.SECRET_PATTERN.sub("[REDACTED_SECRET]", sanitized)
    sanitized = USER_PATH_PATTERN.sub("USER_PATH", sanitized)
    if len(sanitized) > MAX_LOG_CHARS:
        sanitized = "[TRUNCATED]\n" + sanitized[-MAX_LOG_CHARS:]
    return sanitized


def _sanitize_file(path: Path, replacements: Mapping[str, str], label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RegressionError(f"{label} must be UTF-8 text: {exc}") from exc
    sanitized = _sanitize_text(text, replacements)
    path.write_text(sanitized, encoding="utf-8")


def _descriptor(path: Path, manifest_root: Path, schema: str | None) -> dict[str, object]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(manifest_root.resolve())
    except ValueError as exc:
        raise RegressionError(f"artifact escaped regression output root: {path}") from exc
    raw = resolved.read_bytes()
    if not raw:
        raise RegressionError(f"artifact is empty: {path.name}")
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "redacted": True,
        "schema": schema,
    }


def _validate_diagnostic_report(path: Path, expected_schema: str) -> None:
    document = _read_json(path, path.name)
    if document.get("schema") != expected_schema:
        raise RegressionError(f"{path.name} schema must be {expected_schema}")
    summary = document.get("summary")
    if not isinstance(summary, dict):
        raise RegressionError(f"{path.name}.summary must be an object")
    if summary.get("fail") != 0 or summary.get("pending") != 0:
        raise RegressionError(f"{path.name} must contain zero FAIL and zero PENDING findings")
    passed = summary.get("pass")
    if not isinstance(passed, int) or isinstance(passed, bool) or passed <= 0:
        raise RegressionError(f"{path.name} must contain at least one PASS finding")


def _validate_junit(path: Path) -> None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RegressionError(f"{path.name} is not well-formed JUnit XML: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("./testsuite"))
    if not suites:
        raise RegressionError(f"{path.name} contains no testsuite")
    totals = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals["tests"] <= 0:
        raise RegressionError(f"{path.name} contains no executed tests")
    if any(totals[key] != 0 for key in ("failures", "errors", "skipped")):
        raise RegressionError(f"{path.name} must contain zero failures/errors/skips: {totals}")


def _normalized_command(argv: Sequence[str], replacements: Mapping[str, str]) -> list[str]:
    return [_sanitize_text(value, replacements) for value in argv]


def _validate_command_shape(step_id: str, command: Sequence[object]) -> None:
    expected: dict[str, tuple[str, ...]] = {
        "m0_diagnostics": (
            "PYTHON_3_12",
            "tools/diagnostics/check_m0.py",
            "--json-output",
            "OUTPUT_ROOT/reports/m0-diagnostics.json",
        ),
        "m0_tests": (
            "PYTHON_3_12",
            "-m",
            "pytest",
            "--strict-config",
            "--strict-markers",
            "-m",
            "m0",
            "python/tests",
            "integration_tests",
            "--junitxml",
            "OUTPUT_ROOT/junit/m0-tests.xml",
        ),
        "m1_tests": (
            "PYTHON_3_12",
            "-m",
            "pytest",
            "--strict-config",
            "--strict-markers",
            "-m",
            "m1",
            "integration_tests",
            "--junitxml",
            "OUTPUT_ROOT/junit/m1-tests.xml",
        ),
        "m2_diagnostics": (
            "PYTHON_3_12",
            "tools/diagnostics/check_m2.py",
            "--require-m2",
            "--registry",
            "M2_REGISTRY",
            "--evidence",
            "M2_EVIDENCE",
            "--json-output",
            "OUTPUT_ROOT/reports/m2-diagnostics.json",
        ),
        "m2_tests": (
            "PYTHON_3_12",
            "-m",
            "pytest",
            "--strict-config",
            "--strict-markers",
            "-m",
            "m2",
            "integration_tests",
            "--junitxml",
            "OUTPUT_ROOT/junit/m2-tests.xml",
        ),
    }
    observed = tuple(command)
    if step_id == "m1_diagnostics":
        if len(observed) != 9:
            raise RegressionError("m1_diagnostics command shape differs")
        timeout = observed[4]
        if not isinstance(timeout, str) or not timeout.isdigit() or int(timeout) <= 0:
            raise RegressionError("m1_diagnostics timeout must be a positive integer")
        expected_m1: tuple[object, ...] = (
            "PYTHON_3_12",
            "tools/diagnostics/check_m1.py",
            "--require-sim",
            "--timeout-seconds",
            timeout,
            "--output-root",
            "OUTPUT_ROOT/m1",
            "--json-output",
            "OUTPUT_ROOT/reports/m1-diagnostics.json",
        )
        if observed != expected_m1:
            raise RegressionError("m1_diagnostics command shape differs")
        return
    if step_id not in expected or observed != expected[step_id]:
        raise RegressionError(f"{step_id} command differs from the frozen regression lane")


def _command_specs(
    *,
    root: Path,
    work_root: Path,
    m2_registry: Path,
    m2_evidence: Path,
    m1_timeout_seconds: int,
) -> tuple[CommandSpec, ...]:
    reports = work_root / "reports"
    junit = work_root / "junit"
    m1_root = work_root / "m1"
    base_environment = os.environ.copy()
    base_environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(root / "python"), base_environment.get("PYTHONPATH", "")))
    )
    m1_evidence = m1_root / "m1_qa_evidence.json"
    return (
        CommandSpec(
            "m0_diagnostics",
            (
                sys.executable,
                "tools/diagnostics/check_m0.py",
                "--json-output",
                str(reports / "m0-diagnostics.json"),
            ),
            reports / "m0-diagnostics.json",
            "aitown.qa.m0-diagnostics/v1",
            None,
            base_environment,
        ),
        CommandSpec(
            "m0_tests",
            (
                sys.executable,
                "-m",
                "pytest",
                "--strict-config",
                "--strict-markers",
                "-m",
                "m0",
                "python/tests",
                "integration_tests",
                "--junitxml",
                str(junit / "m0-tests.xml"),
            ),
            None,
            None,
            junit / "m0-tests.xml",
            base_environment,
        ),
        CommandSpec(
            "m1_diagnostics",
            (
                sys.executable,
                "tools/diagnostics/check_m1.py",
                "--require-sim",
                "--timeout-seconds",
                str(m1_timeout_seconds),
                "--output-root",
                str(m1_root),
                "--json-output",
                str(reports / "m1-diagnostics.json"),
            ),
            reports / "m1-diagnostics.json",
            check_m1.REPORT_SCHEMA,
            None,
            base_environment,
        ),
        CommandSpec(
            "m1_tests",
            (
                sys.executable,
                "-m",
                "pytest",
                "--strict-config",
                "--strict-markers",
                "-m",
                "m1",
                "integration_tests",
                "--junitxml",
                str(junit / "m1-tests.xml"),
            ),
            None,
            None,
            junit / "m1-tests.xml",
            {**base_environment, "STWM_M1_QA_EVIDENCE": str(m1_evidence)},
        ),
        CommandSpec(
            "m2_diagnostics",
            (
                sys.executable,
                "tools/diagnostics/check_m2.py",
                "--require-m2",
                "--registry",
                str(m2_registry),
                "--evidence",
                str(m2_evidence),
                "--json-output",
                str(reports / "m2-diagnostics.json"),
            ),
            reports / "m2-diagnostics.json",
            check_m2.REPORT_SCHEMA,
            None,
            base_environment,
        ),
        CommandSpec(
            "m2_tests",
            (
                sys.executable,
                "-m",
                "pytest",
                "--strict-config",
                "--strict-markers",
                "-m",
                "m2",
                "integration_tests",
                "--junitxml",
                str(junit / "m2-tests.xml"),
            ),
            None,
            None,
            junit / "m2-tests.xml",
            {**base_environment, "STWM_M2_QA_EVIDENCE": str(m2_evidence)},
        ),
    )


def _input_binding(path: Path, input_id: str, schema: str | None, source_commit: str | None) -> Mapping[str, object]:
    raw = path.read_bytes()
    return {
        "input_id": input_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "schema": schema,
        "source_commit": source_commit,
    }


def _run_steps(
    *,
    root: Path,
    work_root: Path,
    specs: Sequence[CommandSpec],
    runner: ProcessRunner,
    command_timeout_seconds: int,
    replacements: Mapping[str, str],
) -> tuple[str, list[Mapping[str, object]], Path | None]:
    steps: list[Mapping[str, object]] = []
    failure_seen = False
    m1_evidence = work_root / "m1" / "m1_qa_evidence.json"
    for spec in specs:
        if failure_seen:
            steps.append(
                {
                    "step_id": spec.step_id,
                    "command": _normalized_command(spec.argv, replacements),
                    "exit_code": None,
                    "status": "NOT_RUN",
                    "report": None,
                    "junit": None,
                    "log": None,
                }
            )
            continue
        if spec.report_path is not None:
            spec.report_path.parent.mkdir(parents=True, exist_ok=True)
        if spec.junit_path is not None:
            spec.junit_path.parent.mkdir(parents=True, exist_ok=True)
        result = runner(spec.argv, root, spec.environment, command_timeout_seconds)
        log_path = work_root / "logs" / f"{spec.step_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_text = _sanitize_text(
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}\n",
            replacements,
        )
        validation_error: str | None = None
        report_descriptor: Mapping[str, object] | None = None
        junit_descriptor: Mapping[str, object] | None = None
        if result.returncode == 0:
            try:
                if spec.report_path is not None and spec.report_schema is not None:
                    _sanitize_file(spec.report_path, replacements, f"{spec.step_id} diagnostic report")
                    _validate_diagnostic_report(spec.report_path, spec.report_schema)
                    report_descriptor = _descriptor(spec.report_path, work_root, spec.report_schema)
                if spec.junit_path is not None:
                    _sanitize_file(spec.junit_path, replacements, f"{spec.step_id} JUnit report")
                    _validate_junit(spec.junit_path)
                    junit_descriptor = _descriptor(spec.junit_path, work_root, None)
                if spec.step_id == "m1_diagnostics" and not m1_evidence.is_file():
                    raise RegressionError("M1 diagnostics passed without producing m1_qa_evidence.json")
            except RegressionError as exc:
                validation_error = str(exc)
        else:
            validation_error = f"command exited {result.returncode}"
        if validation_error is not None:
            log_text += f"\nvalidation_error:\n{_sanitize_text(validation_error, replacements)}\n"
        log_path.write_text(log_text, encoding="utf-8")
        status = "PASS" if result.returncode == 0 and validation_error is None else "FAIL"
        steps.append(
            {
                "step_id": spec.step_id,
                "command": _normalized_command(spec.argv, replacements),
                "exit_code": result.returncode,
                "status": status,
                "report": report_descriptor,
                "junit": junit_descriptor,
                "log": _descriptor(log_path, work_root, None),
            }
        )
        failure_seen = status == "FAIL"
    return ("FAIL" if failure_seen else "PASS"), steps, m1_evidence if m1_evidence.is_file() else None


def _atomic_write_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _update_repository_report(
    *,
    report_path: Path,
    original: Mapping[str, object],
    finding: Mapping[str, object],
) -> None:
    updated = dict(original)
    findings = [
        cast(Mapping[str, object], raw)
        for raw in cast(Sequence[object], original["findings"])
        if cast(Mapping[str, object], raw).get("code") != FINDING_CODE
    ]
    acceptance_index = next(
        (index for index, item in enumerate(findings) if item.get("code") == "M3_ACCEPTANCE_EVIDENCE_PENDING"),
        len(findings),
    )
    findings.insert(acceptance_index, finding)
    updated["findings"] = findings
    updated["summary"] = {
        status.value.lower(): sum(item.get("status") == status.value for item in findings) for status in check_m3.Status
    }
    try:
        check_m3.validate_readiness_document(updated)
    except check_m3.DiagnosticError as exc:
        raise RegressionError(f"updated repository report is invalid: {exc}") from exc
    _atomic_write_json(report_path, updated)


def run_regression_lane(
    *,
    root: Path,
    repository_report_path: Path,
    output_root: Path,
    m2_registry_path: Path,
    m2_evidence_path: Path,
    command_timeout_seconds: int = 900,
    m1_timeout_seconds: int = 300,
    runner: ProcessRunner = _default_runner,
) -> Mapping[str, object]:
    """Run the six frozen steps, publish a manifest, and atomically update readiness."""

    root = root.resolve()
    source_commit = _repository_head(root)
    report_path = _external_file(repository_report_path, root, "M3 repository report")
    report = _preflight_report(report_path, root, source_commit)
    final_output_root = _preflight_output_root(output_root, report_path, root)
    m2_registry = _external_file(m2_registry_path, root, "M2 registry")
    m2_evidence = _external_file(m2_evidence_path, root, "M2 evidence")
    m2_document = _read_json(m2_evidence, "M2 evidence")
    if m2_document.get("schema") != check_m2.EVIDENCE_SCHEMA:
        raise RegressionError(f"M2 evidence schema must be {check_m2.EVIDENCE_SCHEMA}")
    m2_source = m2_document.get("source_commit")
    if not isinstance(m2_source, str) or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(m2_source) is None:
        raise RegressionError("M2 evidence source_commit must be a full lowercase Git SHA")

    final_output_root.parent.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix=f".{final_output_root.name}.", dir=final_output_root.parent))
    replacements = {
        str(root): "REPOSITORY_ROOT",
        str(work_root): "OUTPUT_ROOT",
        str(final_output_root): "OUTPUT_ROOT",
        str(m2_registry): "M2_REGISTRY",
        str(m2_evidence): "M2_EVIDENCE",
        sys.executable: "PYTHON_3_12",
    }
    try:
        specs = _command_specs(
            root=root,
            work_root=work_root,
            m2_registry=m2_registry,
            m2_evidence=m2_evidence,
            m1_timeout_seconds=m1_timeout_seconds,
        )
        status, steps, m1_evidence = _run_steps(
            root=root,
            work_root=work_root,
            specs=specs,
            runner=runner,
            command_timeout_seconds=command_timeout_seconds,
            replacements=replacements,
        )
        m1_descriptor: Mapping[str, object] | None = None
        if m1_evidence is not None:
            m1_descriptor = {
                **_descriptor(m1_evidence, work_root, check_m1.EVIDENCE_SCHEMA),
                "produced_by_step": "m1_diagnostics",
                "source_commit": source_commit,
            }
        if status == "PASS" and m1_descriptor is None:
            status = "FAIL"
        registry_document = _read_json(m2_registry, "M2 registry")
        registry_source = registry_document.get("source_commit")
        if registry_source is not None and (
            not isinstance(registry_source, str) or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(registry_source) is None
        ):
            raise RegressionError("M2 registry source_commit must be null or a full lowercase Git SHA")
        manifest: Mapping[str, object] = {
            "schema": SCHEMA,
            "project_name": check_m3.PROJECT_NAME,
            "source_commit": source_commit,
            "python_version": platform.python_version(),
            "status": status,
            "ordered_step_ids": list(STEP_IDS),
            "steps": steps,
            "m1_evidence": m1_descriptor,
            "m2_input_bindings": {
                "registry": _input_binding(
                    m2_registry,
                    "M2_REGISTRY",
                    None,
                    registry_source,
                ),
                "evidence": _input_binding(m2_evidence, "M2_EVIDENCE", check_m2.EVIDENCE_SCHEMA, m2_source),
            },
        }
        manifest_path = work_root / "m0-m2-regression-manifest.json"
        _atomic_write_json(manifest_path, manifest)
        validate_regression_manifest(manifest_path, root, require_pass=status == "PASS")
        work_root.replace(final_output_root)
    except Exception:
        shutil.rmtree(work_root, ignore_errors=True)
        raise

    final_manifest = final_output_root / "m0-m2-regression-manifest.json"
    raw_manifest = final_manifest.read_bytes()
    relative_manifest = final_manifest.relative_to(report_path.parent).as_posix()
    outcome_word = "passed" if status == "PASS" else "failed"
    finding: Mapping[str, object] = {
        "check": FINDING_CHECK,
        "status": status,
        "code": FINDING_CODE,
        "message": (
            f"frozen M0/M1/M2 strict lane {outcome_word}; "
            f"manifest_sha256={hashlib.sha256(raw_manifest).hexdigest()}; manifest_bytes={len(raw_manifest)}"
        ),
        "owner": "QA",
        "path": relative_manifest,
        "remediation": None if status == "PASS" else "Inspect the external regression manifest and rerun a new lane.",
    }
    _update_repository_report(report_path=report_path, original=report, finding=finding)
    return {
        "schema": SCHEMA,
        "status": status,
        "source_commit": source_commit,
        "manifest": final_manifest.as_posix(),
        "repository_report": report_path.as_posix(),
    }


def _descriptor_path(
    manifest_path: Path,
    descriptor: Mapping[str, object],
    root: Path,
    label: str,
) -> Path:
    _exact_keys(descriptor, DESCRIPTOR_KEYS, label)
    relative_value = descriptor.get("path")
    if not isinstance(relative_value, str) or not relative_value:
        raise RegressionError(f"{label}.path must be non-empty relative path")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise RegressionError(f"{label}.path escapes the manifest directory")
    path = (manifest_path.parent / relative).resolve()
    try:
        path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise RegressionError(f"{label}.path escapes the manifest directory") from exc
    try:
        path.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise RegressionError(f"{label}.path must remain outside the repository")
    if not path.is_file():
        raise RegressionError(f"{label}.path does not exist")
    return path


def _validate_descriptor(
    manifest_path: Path,
    raw_descriptor: object,
    root: Path,
    label: str,
    expected_schema: str | None,
) -> None:
    if not isinstance(raw_descriptor, dict):
        raise RegressionError(f"{label} must be an artifact descriptor")
    descriptor = cast(dict[str, object], raw_descriptor)
    path = _descriptor_path(manifest_path, descriptor, root, label)
    if descriptor.get("redacted") is not True or descriptor.get("schema") != expected_schema:
        raise RegressionError(f"{label} redaction/schema mismatch")
    raw = path.read_bytes()
    if descriptor.get("bytes") != len(raw) or descriptor.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise RegressionError(f"{label} bytes/hash mismatch")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RegressionError(f"{label} must be UTF-8") from exc
    if not text.strip() or check_m3.SECRET_PATTERN.search(text) or USER_PATH_PATTERN.search(text):
        raise RegressionError(f"{label} is empty or contains unredacted content")
    if path.suffix == ".json":
        document = _read_json(path, label)
        if expected_schema is not None and document.get("schema") != expected_schema:
            raise RegressionError(f"{label} content schema mismatch")
    elif path.suffix == ".xml":
        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            raise RegressionError(f"{label} is malformed XML: {exc}") from exc


def validate_regression_manifest(manifest_path: Path, root: Path, *, require_pass: bool = True) -> None:
    """Validate one external regression-run manifest and all its owned artifacts."""

    manifest = _read_json(_external_file(manifest_path, root, "regression manifest"), "regression manifest")
    _exact_keys(manifest, MANIFEST_KEYS, "regression manifest")
    if manifest.get("schema") != SCHEMA or manifest.get("project_name") != check_m3.PROJECT_NAME:
        raise RegressionError("regression manifest schema/project mismatch")
    source_commit = manifest.get("source_commit")
    if not isinstance(source_commit, str) or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise RegressionError("regression manifest source_commit must be a full SHA")
    if manifest.get("status") not in {"PASS", "FAIL"}:
        raise RegressionError("regression manifest status must be PASS or FAIL")
    if require_pass and manifest.get("status") != "PASS":
        raise RegressionError("regression manifest is not PASS")
    ordered_step_ids = manifest.get("ordered_step_ids")
    if not isinstance(ordered_step_ids, list) or tuple(ordered_step_ids) != STEP_IDS:
        raise RegressionError("regression manifest ordered_step_ids differ")
    python_version = manifest.get("python_version")
    if not isinstance(python_version, str) or check_m3.PYTHON_312_PATTERN.fullmatch(python_version) is None:
        raise RegressionError("regression manifest must use Python 3.12")
    raw_steps = manifest.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) != len(STEP_IDS):
        raise RegressionError("regression manifest must contain the exact six steps")
    observed_ids: list[str] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise RegressionError(f"regression step {index} must be an object")
        step = cast(dict[str, object], raw_step)
        _exact_keys(step, STEP_KEYS, f"regression step {index}")
        step_id = step.get("step_id")
        if not isinstance(step_id, str):
            raise RegressionError(f"regression step {index}.step_id must be a string")
        observed_ids.append(step_id)
        command = step.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
            raise RegressionError(f"regression step {step_id}.command must be a non-empty string array")
        _validate_command_shape(step_id, command)
        status = step.get("status")
        if status not in {"PASS", "FAIL", "NOT_RUN"}:
            raise RegressionError(f"regression step {step_id} has invalid status")
        if status == "NOT_RUN":
            if any(step.get(key) is not None for key in ("exit_code", "report", "junit", "log")):
                raise RegressionError(f"NOT_RUN regression step {step_id} may not claim execution artifacts")
            continue
        if manifest.get("status") == "PASS" and (status != "PASS" or step.get("exit_code") != 0):
            raise RegressionError(f"regression PASS manifest has incomplete step {step_id}")
        _validate_descriptor(manifest_path, step.get("log"), root, f"step {step_id} log", None)
        expected_report = {
            "m0_diagnostics": "aitown.qa.m0-diagnostics/v1",
            "m1_diagnostics": check_m1.REPORT_SCHEMA,
            "m2_diagnostics": check_m2.REPORT_SCHEMA,
        }.get(step_id)
        if expected_report is not None:
            if step.get("report") is not None:
                _validate_descriptor(
                    manifest_path,
                    step.get("report"),
                    root,
                    f"step {step_id} report",
                    expected_report,
                )
            elif status == "PASS":
                raise RegressionError(f"PASS diagnostic step {step_id} requires its report")
        elif step.get("report") is not None:
            raise RegressionError(f"test step {step_id} may not declare a diagnostic report")
        if step_id.endswith("_tests"):
            if step.get("junit") is not None:
                _validate_descriptor(manifest_path, step.get("junit"), root, f"step {step_id} junit", None)
            elif status == "PASS":
                raise RegressionError(f"PASS test step {step_id} requires JUnit")
        elif step.get("junit") is not None:
            raise RegressionError(f"diagnostic step {step_id} may not declare JUnit")
    if tuple(observed_ids) != STEP_IDS:
        raise RegressionError("regression manifest steps are not in frozen order")
    raw_m1 = manifest.get("m1_evidence")
    if manifest.get("status") == "PASS":
        if not isinstance(raw_m1, dict):
            raise RegressionError("PASS manifest requires bound M1 evidence")
        m1_descriptor = cast(dict[str, object], raw_m1)
        _exact_keys(
            m1_descriptor,
            (*DESCRIPTOR_KEYS, "produced_by_step", "source_commit"),
            "m1_evidence",
        )
        if m1_descriptor.get("produced_by_step") != "m1_diagnostics":
            raise RegressionError("M1 evidence producer step mismatch")
        if m1_descriptor.get("source_commit") != source_commit:
            raise RegressionError("M1 evidence source binding differs from manifest")
        base_descriptor = {key: m1_descriptor[key] for key in DESCRIPTOR_KEYS}
        _validate_descriptor(manifest_path, base_descriptor, root, "m1_evidence", check_m1.EVIDENCE_SCHEMA)
    bindings = manifest.get("m2_input_bindings")
    if not isinstance(bindings, dict) or set(bindings) != {"registry", "evidence"}:
        raise RegressionError("m2_input_bindings must contain exact registry/evidence entries")
    for name, expected_id, expected_schema in (
        ("registry", "M2_REGISTRY", None),
        ("evidence", "M2_EVIDENCE", check_m2.EVIDENCE_SCHEMA),
    ):
        raw_binding = bindings[name]
        if not isinstance(raw_binding, dict):
            raise RegressionError(f"m2_input_bindings.{name} must be an object")
        binding = cast(dict[str, object], raw_binding)
        _exact_keys(binding, INPUT_BINDING_KEYS, f"m2_input_bindings.{name}")
        if binding.get("input_id") != expected_id or binding.get("schema") != expected_schema:
            raise RegressionError(f"m2_input_bindings.{name} identity/schema mismatch")
        digest = binding.get("sha256")
        size = binding.get("bytes")
        source = binding.get("source_commit")
        if not isinstance(digest, str) or check_m3.SHA256_PATTERN.fullmatch(digest) is None:
            raise RegressionError(f"m2_input_bindings.{name}.sha256 is invalid")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise RegressionError(f"m2_input_bindings.{name}.bytes must be positive")
        if source is not None and (
            not isinstance(source, str) or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(source) is None
        ):
            raise RegressionError(f"m2_input_bindings.{name}.source_commit is invalid")


def validate_regression_finding_artifact(
    repository_report_path: Path,
    finding: Mapping[str, object],
    root: Path,
) -> None:
    """Bind a PASS repository finding to its external immutable manifest."""

    if finding.get("status") != "PASS" or finding.get("code") != FINDING_CODE:
        raise RegressionError("M3 regression finding must be PASS with the exact code")
    message = finding.get("message")
    if not isinstance(message, str):
        raise RegressionError("M3 regression finding message must be a string")
    match = FINDING_MESSAGE_PATTERN.fullmatch(message)
    if match is None or match.group(1) != "passed":
        raise RegressionError("M3 regression finding message/digest shape differs")
    path_value = finding.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise RegressionError("M3 regression finding path must reference the external manifest")
    relative = PurePosixPath(path_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise RegressionError("M3 regression finding path escapes the report directory")
    manifest_path = (repository_report_path.parent / relative).resolve()
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != match.group(2) or len(raw) != int(match.group(3)):
        raise RegressionError("M3 regression finding manifest digest/bytes mismatch")
    validate_regression_manifest(manifest_path, root, require_pass=True)
    manifest = _read_json(manifest_path, "regression manifest")
    if manifest.get("source_commit") != finding_source_commit(repository_report_path):
        raise RegressionError("regression manifest source_commit differs from repository report")


def copy_regression_attestation(
    *,
    repository_report_path: Path,
    finding: Mapping[str, object],
    destination_report_path: Path,
    root: Path,
) -> None:
    """Copy the verified manifest and its owned descriptors beside a report copy."""

    validate_regression_finding_artifact(repository_report_path, finding, root)
    path_value = cast(str, finding["path"])
    source_manifest = (repository_report_path.parent / PurePosixPath(path_value)).resolve()
    destination_manifest = (destination_report_path.parent / PurePosixPath(path_value)).resolve()
    manifest = _read_json(source_manifest, "regression manifest")
    raw_steps = cast(Sequence[object], manifest["steps"])
    descriptors: list[Mapping[str, object]] = []
    for raw_step in raw_steps:
        step = cast(Mapping[str, object], raw_step)
        for key in ("report", "junit", "log"):
            raw_descriptor = step.get(key)
            if isinstance(raw_descriptor, dict):
                descriptors.append(cast(dict[str, object], raw_descriptor))
    raw_m1 = manifest.get("m1_evidence")
    if isinstance(raw_m1, dict):
        descriptors.append({key: raw_m1[key] for key in DESCRIPTOR_KEYS})
    for descriptor in descriptors:
        relative = PurePosixPath(cast(str, descriptor["path"]))
        source = (source_manifest.parent / relative).resolve()
        destination = (destination_manifest.parent / relative).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise RegressionError(f"duplicate regression attestation destination: {relative}")
        shutil.copyfile(source, destination)
    destination_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_manifest, destination_manifest)
    validate_regression_finding_artifact(destination_report_path, finding, root)


def finding_source_commit(repository_report_path: Path) -> str:
    report = _read_json(repository_report_path, "M3 repository report")
    value = report.get("source_commit")
    if not isinstance(value, str) or check_m3.SOURCE_COMMIT_PATTERN.fullmatch(value) is None:
        raise RegressionError("repository report source_commit is invalid")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-report", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--m2-registry", required=True, type=Path)
    parser.add_argument("--m2-evidence", required=True, type=Path)
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    parser.add_argument("--m1-timeout-seconds", type=int, default=300)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        result = run_regression_lane(
            root=root,
            repository_report_path=args.repository_report,
            output_root=args.output_root,
            m2_registry_path=args.m2_registry,
            m2_evidence_path=args.m2_evidence,
            command_timeout_seconds=args.command_timeout_seconds,
            m1_timeout_seconds=args.m1_timeout_seconds,
        )
    except (RegressionError, OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
