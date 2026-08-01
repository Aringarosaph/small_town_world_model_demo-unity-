"""Executable full-repository M0 acceptance gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.diagnostics.check_m0 import (
    Status,
    find_repository_root,
    render_text,
    run_checks,
)

pytestmark = [
    pytest.mark.qa,
    pytest.mark.m0,
    pytest.mark.integration,
]


def test_repository_is_strictly_m0_ready() -> None:
    root = find_repository_root(Path(__file__))
    findings = run_checks(root, ("all",), allow_pending_m0_inputs=False)
    failures = [finding for finding in findings if finding.status is Status.FAIL]

    assert not failures, "\n" + render_text(findings)
