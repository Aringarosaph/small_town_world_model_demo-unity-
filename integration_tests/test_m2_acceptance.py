"""Executable M2 gray-box acceptance adapter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m2 import Status, render_text, run_checks

pytestmark = [
    pytest.mark.qa,
    pytest.mark.m2,
    pytest.mark.integration,
    pytest.mark.graybox,
    pytest.mark.protocol,
    pytest.mark.unity,
    pytest.mark.unity_pending,
    pytest.mark.batchmode,
]


def test_repository_is_m2_graybox_ready() -> None:
    root = find_repository_root(Path(__file__))
    supplied_evidence = os.environ.get("STWM_M2_QA_EVIDENCE")
    evidence_path = Path(supplied_evidence).resolve() if supplied_evidence else None
    findings = run_checks(root, evidence_path=evidence_path)
    failures = [finding for finding in findings if finding.status is Status.FAIL]
    pending = [finding for finding in findings if finding.status is Status.PENDING]

    assert not failures, "\n" + render_text(findings)
    if pending:
        pytest.skip(
            "M2 CONTRACTS/Unity evidence is not fully integrated; strict M2 gate remains pending.\n"
            + render_text(findings)
        )
