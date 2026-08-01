"""Unit coverage for the QA-owned M0 diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.diagnostics.check_m0 import (
    FREEZE_CHECKLIST_KEYS,
    Status,
    check_config_freeze,
    detect_secret_content,
    detect_sensitive_path,
    extract_catalog_ids,
)
from tools.diagnostics.prepare_m0_freeze import build_candidate

pytestmark = [pytest.mark.qa, pytest.mark.m0]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".env", "environment-file"),
        ("config/.env.production", "environment-file"),
        (".env.example", None),
        ("runs/demo/events.jsonl", "runtime-output"),
        ("data/generated/train.parquet", "generated-dataset"),
        ("models/checkpoints/latest.pt", "model-artifact"),
        ("unity/Library/ArtifactDB", "unity-generated"),
        ("docs/qa/LOG_FORMAT.md", None),
    ],
)
def test_sensitive_path_detection(path: str, expected: str | None) -> None:
    assert detect_sensitive_path(path) == expected


def test_secret_detector_hides_values_at_api_boundary() -> None:
    fake_value = "sk-" + "a" * 32
    detectors = detect_secret_content(f"OPENAI_API_KEY={fake_value}\n")

    assert "openai-style-key" in detectors
    assert "assigned-secret" in detectors
    assert fake_value not in repr(detectors)


def test_environment_placeholders_are_allowed() -> None:
    assert detect_secret_content("DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}\n") == ()


def test_catalog_extractor_reads_explicit_fields() -> None:
    text = """
    - behavior_id: idle
    - behavior_id: "sleep"
    unrelated_id: ignored
    """

    assert extract_catalog_ids(text, ("behavior_id",)) == ["idle", "sleep"]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_valid_freeze_manifest(root: Path) -> Path:
    files = (
        root / "config/v0/world.yaml",
        root / "protocol/version.json",
        root / "python/town_core/domain/schema.py",
    )
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture: {path.name}\n", encoding="utf-8")

    manifest_path = root / "tools/diagnostics/m0_config_freeze.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "aitown.qa.m0-freeze/v1",
        "source_commit": "deadbee",
        "approved_by": "test-orchestrator",
        "approved_at_utc": "2026-01-01T00:00:00Z",
        "checklist": {key: True for key in FREEZE_CHECKLIST_KEYS},
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _digest(path),
            }
            for path in files
        ],
    }
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    return manifest_path


def test_freeze_manifest_accepts_complete_reviewed_snapshot(tmp_path: Path) -> None:
    _write_valid_freeze_manifest(tmp_path)

    findings = check_config_freeze(tmp_path)

    assert [(finding.status, finding.code) for finding in findings] == [
        (Status.PASS, "CONFIG_FREEZE_VERIFIED")
    ]


def test_freeze_manifest_reports_content_drift(tmp_path: Path) -> None:
    _write_valid_freeze_manifest(tmp_path)
    (tmp_path / "config/v0/world.yaml").write_text(
        "fixture: changed\n", encoding="utf-8"
    )

    findings = check_config_freeze(tmp_path)

    assert any(finding.code == "FROZEN_FILE_CHANGED" for finding in findings)


def test_freeze_candidate_is_actionable_but_unsigned(tmp_path: Path) -> None:
    config = tmp_path / "config/v0/world.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("world_id: demo_world\n", encoding="utf-8")

    candidate = build_candidate(tmp_path, "deadbee")

    assert candidate["approved_by"] == ""
    assert candidate["approved_at_utc"] is None
    checklist = candidate["checklist"]
    assert isinstance(checklist, dict)
    assert checklist and not any(checklist.values())
    assert candidate["files"] == [
        {"path": "config/v0/world.yaml", "sha256": _digest(config)}
    ]
