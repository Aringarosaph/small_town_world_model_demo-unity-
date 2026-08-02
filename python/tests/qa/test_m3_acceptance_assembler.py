from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from tests.qa.m3_regression_test_support import FakeRegressionRunner
from tests.qa.test_m3_diagnostics import _passing_evidence

from tools.diagnostics import assemble_m3_acceptance as assembler
from tools.diagnostics import check_m3 as m3
from tools.diagnostics import run_m3_regressions as regressions

pytestmark = [pytest.mark.qa, pytest.mark.m3, pytest.mark.m3_fast]


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _descriptor(path: Path, base: Path, schema: str | None) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(base).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "redacted": True,
        "schema": schema,
    }


def _probe(test_id: str) -> dict[str, object]:
    return {"status": "PASS", "test_ids": [test_id], "assertion_count": 1}


def _complete_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = _root()
    source = tmp_path / "owners"
    source.mkdir()
    evidence_path = _passing_evidence(root, source)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    matrices = cast(dict[str, object], evidence["matrices"])
    source_commit = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True).strip()

    sim_projection = {name: matrices[name] for name in assembler.SIM_MATRIX_KEYS}
    authority_path = source / "authority_evidence.json"
    _write_json(
        authority_path,
        {
            "schema": m3.ARTIFACT_SCHEMAS["authority_evidence"][1],
            "project_name": m3.PROJECT_NAME,
            "source_commit": source_commit,
            "qa_matrix_projection": sim_projection,
            "qa_probe_evidence": {
                name: _probe(f"python/tests/society/test_m3_targeted.py::test_{name}")
                for name in assembler.SIM_AUTHORITY_PROBES
            },
        },
    )
    behavior_rows = cast(list[Mapping[str, object]], matrices["behavior_coverage"])
    behavior_path = source / "behavior_matrix_report.json"
    _write_json(
        behavior_path,
        {
            "schema": m3.ARTIFACT_SCHEMAS["behavior_matrix_report"][1],
            "project_name": m3.PROJECT_NAME,
            "source_commit": source_commit,
            "cases": [
                {
                    "behavior_id": row["behavior_id"],
                    "fixture_id": row["fixture_id"],
                    "sim_targeted_probe_owner": "SIM_FAST_TARGETED_FIXTURES",
                    "sim_targeted_probe_results": {
                        probe: _probe(f"python/tests/society/test_m3_targeted.py::test_{row['behavior_id']}_{probe}")
                        for probe in assembler.SIM_BEHAVIOR_PROBES
                    },
                    "release_soak_occurrence_count": row["release_soak_occurrence_count"],
                    "unity_presentation": None,
                    "unity_presentation_owner": "UNITY",
                    "run_refs": [f"runs/{row['behavior_id']}/actions.jsonl"],
                }
                for row in behavior_rows
            ],
        },
    )
    sim_artifacts: dict[str, Mapping[str, object]] = {}
    for name in assembler.SIM_ARTIFACTS:
        suffix = min(m3.ARTIFACT_SCHEMAS[name][0])
        path = source / f"{name}{suffix}"
        sim_artifacts[name] = _descriptor(path, source, m3.ARTIFACT_SCHEMAS[name][1])
    sim_bundle_path = source / "bundle-manifest.json"
    _write_json(
        sim_bundle_path,
        {
            "schema": assembler.SIM_BUNDLE_SCHEMA,
            "project_name": m3.PROJECT_NAME,
            "source_commit": source_commit,
            "generated_at_utc": "2026-08-03T00:00:00Z",
            "profile": "M3_RELEASE_SOCIETY",
            "complete": True,
            "artifacts": sim_artifacts,
            "explicitly_not_generated": [
                m3.EVIDENCE_SCHEMA,
                "Unity registry/semantic/debug/EditMode/PlayMode/batchmode artifacts",
            ],
        },
    )

    final_descriptors = cast(dict[str, Mapping[str, object]], evidence["artifacts"])
    unity_artifacts = {name: final_descriptors[name] for name in assembler.UNITY_ARTIFACTS}
    unity_bundle_path = source / "m3-unity-partial-acceptance-evidence.json"
    unity_gates = {
        name: {"status": "PASS", "evidence_source": "test", "details": "real external fixture"}
        for name in (
            "protocol_0_3_live",
            "full_registry",
            "structured_presentation",
            "unity_semantics",
            "editmode",
            "playmode_live",
        )
    }
    _write_json(
        unity_bundle_path,
        {
            "schema": assembler.UNITY_BUNDLE_SCHEMA,
            "project_name": m3.PROJECT_NAME,
            "source_commit": source_commit,
            "generated_at_utc": "2026-08-03T00:00:00Z",
            "accepted_m2_commit": m3.ACCEPTED_M2_COMMIT,
            "catalog_protocol_version": m3.CATALOG_PROTOCOL_VERSION,
            "negotiated_protocol_version": m3.PROTOCOL_VERSION,
            "unity_editor_version": m3.UNITY_EDITOR_VERSION,
            "status": "PENDING",
            "acceptance_eligible": False,
            "pending_reasons": ["FINAL_RELEASE_ASSEMBLER_OWNS_COMPOSITION"],
            "gates": unity_gates,
            "unity_test_summary": {
                "editmode": {"total": 46, "passed": 46, "failed": 0, "skipped": 0, "inconclusive": 0},
                "playmode": {"total": 4, "passed": 4, "failed": 0, "skipped": 0, "inconclusive": 0},
            },
            "artifacts": unity_artifacts,
            "qa_matrix_projection": {
                "unity": matrices["unity"],
                "behavior_presentation": [
                    {
                        "behavior_id": behavior_id,
                        "fixture_id": f"m3_behavior_{behavior_id}",
                        "unity_presentation": _probe(
                            f"unity/Assets/Tests/PlayMode/M3BehaviorPresentationTests.cs::{behavior_id}"
                        ),
                    }
                    for behavior_id in m3.BEHAVIOR_IDS
                ],
            },
        },
    )

    findings = [
        {
            "check": "m3.final-assembly-input",
            "status": "PASS",
            "code": code,
            "message": f"real external evidence for {code}",
            "owner": "QA",
            "path": None,
            "remediation": None,
        }
        for code in sorted(assembler.REPOSITORY_PASS_CODES - {regressions.FINDING_CODE})
    ]
    findings.append(
        {
            "check": "m3.evidence",
            "status": "PENDING",
            "code": "M3_ACCEPTANCE_EVIDENCE_PENDING",
            "message": "final assembler has not run yet",
            "owner": "QA",
            "path": None,
            "remediation": "run the final assembler",
        }
    )
    repository_report_path = source / "m3-readiness.json"
    _write_json(
        repository_report_path,
        {
            "schema": m3.READINESS_SCHEMA,
            "project_name": m3.PROJECT_NAME,
            "profile": "fast",
            "source_commit": source_commit,
            "accepted_m2_commit": m3.ACCEPTED_M2_COMMIT,
            "m3_entry_commit": m3.M3_ENTRY_COMMIT,
            "catalog_protocol_version": m3.CATALOG_PROTOCOL_VERSION,
            "negotiated_protocol_version": m3.PROTOCOL_VERSION,
            "findings": findings,
            "summary": {"pass": len(findings) - 1, "pending": 1, "fail": 0},
        },
    )
    m2_registry = source / "m2-registry-input.json"
    _write_json(m2_registry, {"protocol_version": "0.2.0", "message_type": "asset_registry", "payload": {}})
    m2_evidence = source / "m2-evidence-input.json"
    _write_json(
        m2_evidence,
        {
            "schema": "stwm.qa.m2-acceptance-evidence/v1",
            "project_name": m3.PROJECT_NAME,
            "source_commit": "b" * 40,
        },
    )
    result = regressions.run_regression_lane(
        root=root,
        repository_report_path=repository_report_path,
        output_root=source / "m0-m2-regressions",
        m2_registry_path=m2_registry,
        m2_evidence_path=m2_evidence,
        runner=FakeRegressionRunner(),
    )
    assert result["status"] == "PASS"
    return sim_bundle_path, unity_bundle_path, repository_report_path


def _refresh_descriptor(bundle_path: Path, artifact_name: str) -> None:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    descriptor = bundle["artifacts"][artifact_name]
    artifact = bundle_path.parent / descriptor["path"]
    bundle["artifacts"][artifact_name] = _descriptor(artifact, bundle_path.parent, descriptor["schema"])
    _write_json(bundle_path, bundle)


def test_complete_real_owner_projections_assemble_exact_acceptance(tmp_path: Path) -> None:
    sim, unity, repository = _complete_inputs(tmp_path)
    output_root = tmp_path / "final"

    result = assembler.assemble_acceptance(
        root=_root(),
        sim_bundle_path=sim,
        unity_bundle_path=unity,
        repository_report_path=repository,
        output_root=output_root,
        require_complete=True,
    )

    assert result["status"] == "PASS"
    assert result["missing_fields"] == []
    assert result["errors"] == []
    evidence_path = Path(cast(str, result["output"]))
    findings = m3.validate_acceptance_evidence(evidence_path, _root())
    assert [(item.status, item.code) for item in findings] == [(m3.Status.PASS, "M3_ACCEPTANCE_EVIDENCE_VALID")]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["artifacts"]["repository_report"]["schema"] == m3.READINESS_SCHEMA
    copied_report = evidence_path.parent / evidence["artifacts"]["repository_report"]["path"]
    copied_document = json.loads(copied_report.read_text(encoding="utf-8"))
    copied_finding = next(item for item in copied_document["findings"] if item["code"] == regressions.FINDING_CODE)
    regressions.validate_regression_finding_artifact(copied_report, copied_finding, _root())


def test_missing_owner_probes_are_pending_and_strict_failure_without_output(tmp_path: Path) -> None:
    sim, unity, repository = _complete_inputs(tmp_path)
    behavior_bundle = json.loads(sim.read_text(encoding="utf-8"))
    behavior_path = sim.parent / behavior_bundle["artifacts"]["behavior_matrix_report"]["path"]
    behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    behavior["cases"][0]["sim_targeted_probe_results"] = None
    _write_json(behavior_path, behavior)
    _refresh_descriptor(sim, "behavior_matrix_report")
    unity_document = json.loads(unity.read_text(encoding="utf-8"))
    unity_document.pop("qa_matrix_projection")
    _write_json(unity, unity_document)
    repository_document = json.loads(repository.read_text(encoding="utf-8"))
    repository_document["findings"] = [
        item for item in repository_document["findings"] if item["code"] != "M3_M0_M2_REGRESSIONS"
    ]
    repository_document["summary"]["pass"] -= 1
    _write_json(repository, repository_document)

    pending = assembler.assemble_acceptance(
        root=_root(),
        sim_bundle_path=sim,
        unity_bundle_path=unity,
        repository_report_path=repository,
        output_root=tmp_path / "pending-output",
    )
    strict = assembler.assemble_acceptance(
        root=_root(),
        sim_bundle_path=sim,
        unity_bundle_path=unity,
        repository_report_path=repository,
        output_root=tmp_path / "strict-output",
        require_complete=True,
    )

    assert pending["status"] == "PENDING"
    assert strict["status"] == "FAIL"
    missing = cast(list[str], pending["missing_fields"])
    assert "SIM behavior idle targeted probe results" in missing
    assert "Unity bundle.qa_matrix_projection.unity" in missing
    assert "Unity bundle.qa_matrix_projection.behavior_presentation" in missing
    assert "repository report finding M3_M0_M2_REGRESSIONS=PASS" in missing
    assert pending["output"] is None
    assert not (tmp_path / "pending-output").exists()
    assert not (tmp_path / "strict-output").exists()


def test_owner_artifact_hash_tamper_is_failure(tmp_path: Path) -> None:
    sim, unity, repository = _complete_inputs(tmp_path)
    bundle = json.loads(sim.read_text(encoding="utf-8"))
    artifact = sim.parent / bundle["artifacts"]["pathology_report"]["path"]
    artifact.write_text("{}\n", encoding="utf-8")

    result = assembler.assemble_acceptance(
        root=_root(),
        sim_bundle_path=sim,
        unity_bundle_path=unity,
        repository_report_path=repository,
        output_root=tmp_path / "tampered-output",
    )

    assert result["status"] == "FAIL"
    assert any("bytes/hash" in item for item in cast(list[str], result["errors"]))
    assert result["output"] is None


def test_redacted_unity_xml_must_remain_well_formed(tmp_path: Path) -> None:
    sim, unity, repository = _complete_inputs(tmp_path)
    bundle = json.loads(unity.read_text(encoding="utf-8"))
    artifact = unity.parent / bundle["artifacts"]["editmode_results"]["path"]
    artifact.write_text(
        '<?xml version="1.0"?><test-run fullname="<REPOSITORY_ROOT>/unity/Library" />\n',
        encoding="utf-8",
    )
    _refresh_descriptor(unity, "editmode_results")

    result = assembler.assemble_acceptance(
        root=_root(),
        sim_bundle_path=sim,
        unity_bundle_path=unity,
        repository_report_path=repository,
        output_root=tmp_path / "malformed-xml-output",
    )

    assert result["status"] == "FAIL"
    assert any("artifact editmode_results is malformed" in item for item in cast(list[str], result["errors"]))
    assert result["output"] is None


def test_cli_returns_zero_for_readable_pending_and_one_for_strict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sim, unity, repository = _complete_inputs(tmp_path)
    unity_document = json.loads(unity.read_text(encoding="utf-8"))
    unity_document.pop("qa_matrix_projection")
    _write_json(unity, unity_document)
    arguments = [
        "--sim-bundle",
        str(sim),
        "--unity-bundle",
        str(unity),
        "--repository-report",
        str(repository),
        "--output-root",
        str(tmp_path / "cli-output"),
    ]

    assert assembler.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PENDING"
    assert assembler.main([*arguments[:-1], str(tmp_path / "cli-strict"), "--require-complete"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
