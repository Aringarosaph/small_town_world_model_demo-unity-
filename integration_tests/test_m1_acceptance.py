"""Executable black-box M1 acceptance gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.diagnostics.check_m0 import find_repository_root
from tools.diagnostics.check_m1 import Status, render_text, run_checks

pytestmark = [
    pytest.mark.qa,
    pytest.mark.m1,
    pytest.mark.integration,
    pytest.mark.sim_pending,
    pytest.mark.headless,
    pytest.mark.determinism,
    pytest.mark.replay,
    pytest.mark.invariant,
]


def test_repository_is_m1_headless_ready(tmp_path: Path) -> None:
    root = find_repository_root(Path(__file__))
    supplied_evidence = os.environ.get("STWM_M1_QA_EVIDENCE")
    evidence_path = Path(supplied_evidence).resolve() if supplied_evidence else None
    findings = run_checks(root, evidence_path=evidence_path, output_root=tmp_path)
    failures = [finding for finding in findings if finding.status is Status.FAIL]
    pending = [finding for finding in findings if finding.status is Status.PENDING]

    assert not failures, "\n" + render_text(findings)
    if pending:
        pytest.skip(
            "SIM M1 authority runtime is not integrated; strict M1 gate remains pending.\n" + render_text(findings)
        )
