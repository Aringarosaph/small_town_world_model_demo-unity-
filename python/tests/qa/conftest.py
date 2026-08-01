"""Pytest marker registration for QA-owned tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


MARKERS = (
    "qa: QA-owned validation and regression coverage",
    "m0: milestone M0 acceptance coverage",
    "integration: crosses a process, package, protocol, or repository boundary",
    "contract_pending: requires an upstream CONTRACTS/Orchestrator M0 artifact",
    "slow: intentionally unsuitable for the default fast regression lane",
)


def pytest_configure(config: pytest.Config) -> None:
    """Register project markers without modifying the CONTRACTS-owned pyproject."""
    for marker in MARKERS:
        config.addinivalue_line("markers", marker)
