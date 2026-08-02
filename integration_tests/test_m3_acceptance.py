"""Executable M3 integration-aware acceptance adapter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m3 import Status, render_text, run_checks

pytestmark = [
    pytest.mark.qa,
    pytest.mark.m3,
    pytest.mark.m3_fast,
    pytest.mark.integration,
    pytest.mark.protocol,
    pytest.mark.society,
    pytest.mark.full_registry,
    pytest.mark.joint_action,
]


def _external_path(variable: str) -> Path | None:
    value = os.environ.get(variable)
    return Path(value).resolve() if value else None


def test_repository_is_m3_integration_ready() -> None:
    """Consume real upstream evidence; complete absence is the only skip state."""
    root = find_repository_root(Path(__file__))
    findings = run_checks(
        root,
        registry_path=_external_path("STWM_M3_FULL_REGISTRY"),
        evidence_path=_external_path("STWM_M3_QA_EVIDENCE"),
    )
    failures = [finding for finding in findings if finding.status is Status.FAIL]
    pending = [finding for finding in findings if finding.status is Status.PENDING]

    assert not failures, "\n" + render_text(findings)
    if pending:
        pytest.skip(
            "M3 CONTRACTS/SIM/UNITY evidence is not fully integrated; --require-m3 remains blocking.\n"
            + render_text(findings)
        )
