from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from tests.qa.m3_regression_test_support import FakeRegressionRunner, write_json

from tools.diagnostics import check_m2, check_m3
from tools.diagnostics import run_m3_regressions as regressions

pytestmark = [pytest.mark.qa, pytest.mark.m3, pytest.mark.m3_fast]


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _head(root: Path) -> str:
    return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True).strip()


def _inputs(tmp_path: Path, *, source_commit: str | None = None) -> tuple[Path, Path, Path]:
    root = _root()
    commit = source_commit or _head(root)
    report = tmp_path / "m3-readiness.json"
    finding = {
        "check": "m3.evidence",
        "status": "PENDING",
        "code": "M3_ACCEPTANCE_EVIDENCE_PENDING",
        "message": "final evidence has not been assembled",
        "owner": "QA",
        "path": None,
        "remediation": "run the final assembler",
    }
    write_json(
        report,
        {
            "schema": check_m3.READINESS_SCHEMA,
            "project_name": check_m3.PROJECT_NAME,
            "profile": "fast",
            "source_commit": commit,
            "accepted_m2_commit": check_m3.ACCEPTED_M2_COMMIT,
            "m3_entry_commit": check_m3.M3_ENTRY_COMMIT,
            "catalog_protocol_version": check_m3.CATALOG_PROTOCOL_VERSION,
            "negotiated_protocol_version": check_m3.PROTOCOL_VERSION,
            "findings": [finding],
            "summary": {"pass": 0, "pending": 1, "fail": 0},
        },
    )
    registry = tmp_path / "m2-registry.json"
    write_json(registry, {"protocol_version": "0.2.0", "message_type": "asset_registry", "payload": {}})
    evidence = tmp_path / "m2-evidence.json"
    write_json(
        evidence,
        {
            "schema": check_m2.EVIDENCE_SCHEMA,
            "project_name": check_m3.PROJECT_NAME,
            "source_commit": "b" * 40,
        },
    )
    return report, registry, evidence


def test_six_real_command_shapes_produce_bound_pass_finding(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path)
    runner = FakeRegressionRunner()

    result = regressions.run_regression_lane(
        root=_root(),
        repository_report_path=report,
        output_root=tmp_path / "regressions",
        m2_registry_path=registry,
        m2_evidence_path=evidence,
        runner=runner,
    )

    assert result["status"] == "PASS"
    assert tuple(runner.observed_steps) == regressions.STEP_IDS
    repository = json.loads(report.read_text(encoding="utf-8"))
    finding = next(item for item in repository["findings"] if item["code"] == regressions.FINDING_CODE)
    assert finding["status"] == "PASS"
    assert repository["summary"] == {"pass": 1, "pending": 1, "fail": 0}
    regressions.validate_regression_finding_artifact(report, finding, _root())
    manifest = json.loads(Path(cast(str, result["manifest"])).read_text(encoding="utf-8"))
    assert manifest["source_commit"] == _head(_root())
    assert manifest["m1_evidence"]["source_commit"] == manifest["source_commit"]
    assert manifest["m1_evidence"]["produced_by_step"] == "m1_diagnostics"
    rendered = json.dumps(manifest)
    assert str(_root()) not in rendered
    log_text = (tmp_path / "regressions/logs/m0_diagnostics.log").read_text(encoding="utf-8")
    assert "REPOSITORY_ROOT" in log_text
    assert "not-a-real-secret-token" not in log_text


def test_nonzero_step_writes_fail_and_stops_later_commands(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path)
    runner = FakeRegressionRunner(fail_step="m1_tests")

    result = regressions.run_regression_lane(
        root=_root(),
        repository_report_path=report,
        output_root=tmp_path / "failed-regressions",
        m2_registry_path=registry,
        m2_evidence_path=evidence,
        runner=runner,
    )

    assert result["status"] == "FAIL"
    assert tuple(runner.observed_steps) == regressions.STEP_IDS[:4]
    repository = json.loads(report.read_text(encoding="utf-8"))
    finding = next(item for item in repository["findings"] if item["code"] == regressions.FINDING_CODE)
    assert finding["status"] == "FAIL"
    assert repository["summary"] == {"pass": 0, "pending": 1, "fail": 1}
    manifest = json.loads(Path(cast(str, result["manifest"])).read_text(encoding="utf-8"))
    assert [item["status"] for item in manifest["steps"]] == [
        "PASS",
        "PASS",
        "PASS",
        "FAIL",
        "NOT_RUN",
        "NOT_RUN",
    ]


def test_exit_zero_diagnostic_with_pending_is_failure(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path)

    result = regressions.run_regression_lane(
        root=_root(),
        repository_report_path=report,
        output_root=tmp_path / "pending-regressions",
        m2_registry_path=registry,
        m2_evidence_path=evidence,
        runner=FakeRegressionRunner(pending_step="m0_diagnostics"),
    )

    assert result["status"] == "FAIL"
    manifest = json.loads(Path(cast(str, result["manifest"])).read_text(encoding="utf-8"))
    assert manifest["steps"][0]["exit_code"] == 0
    assert manifest["steps"][0]["status"] == "FAIL"


def test_exit_zero_pytest_with_skip_is_failure(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path)

    result = regressions.run_regression_lane(
        root=_root(),
        repository_report_path=report,
        output_root=tmp_path / "skipped-regressions",
        m2_registry_path=registry,
        m2_evidence_path=evidence,
        runner=FakeRegressionRunner(skipped_step="m1_tests"),
    )

    assert result["status"] == "FAIL"
    manifest = json.loads(Path(cast(str, result["manifest"])).read_text(encoding="utf-8"))
    assert manifest["steps"][3]["exit_code"] == 0
    assert manifest["steps"][3]["status"] == "FAIL"


def test_source_mismatch_refuses_to_edit_repository_report(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path, source_commit="c" * 40)
    before = report.read_bytes()

    with pytest.raises(regressions.RegressionError, match="source_commit"):
        regressions.run_regression_lane(
            root=_root(),
            repository_report_path=report,
            output_root=tmp_path / "not-created",
            m2_registry_path=registry,
            m2_evidence_path=evidence,
            runner=FakeRegressionRunner(),
        )

    assert report.read_bytes() == before
    assert not (tmp_path / "not-created").exists()


def test_tampered_manifest_invalidates_pass_finding(tmp_path: Path) -> None:
    report, registry, evidence = _inputs(tmp_path)
    result = regressions.run_regression_lane(
        root=_root(),
        repository_report_path=report,
        output_root=tmp_path / "tamper-regressions",
        m2_registry_path=registry,
        m2_evidence_path=evidence,
        runner=FakeRegressionRunner(),
    )
    manifest_path = Path(cast(str, result["manifest"]))
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    repository = json.loads(report.read_text(encoding="utf-8"))
    finding = next(item for item in repository["findings"] if item["code"] == regressions.FINDING_CODE)

    with pytest.raises(regressions.RegressionError, match="digest/bytes"):
        regressions.validate_regression_finding_artifact(report, finding, _root())


@pytest.mark.parametrize(
    "script",
    ("tools/diagnostics/run_m3_regressions.py", "tools/diagnostics/assemble_m3_acceptance.py"),
)
def test_direct_cli_entrypoint_resolves_repository_imports(script: str) -> None:
    completed = subprocess.run(
        (sys.executable, script, "--help"),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": "python"},
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout
