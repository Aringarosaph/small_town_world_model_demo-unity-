"""Pytest marker registration for cross-component tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


MARKERS = (
    "qa: QA-owned validation and regression coverage",
    "m0: milestone M0 acceptance coverage",
    "m1: milestone M1 Headless authority acceptance coverage",
    "integration: crosses a process, package, protocol, or repository boundary",
    "contract_pending: requires an upstream CONTRACTS/Orchestrator M0 artifact",
    "sim_pending: may skip only while the AITOWN-SIM M1 runtime is absent",
    "headless: executes or validates the Headless authority runtime",
    "determinism: validates seed and tick-chunk deterministic equivalence",
    "replay: validates authoritative snapshot and transaction replay",
    "invariant: validates authority-state rejection and safety invariants",
    "slow: intentionally unsuitable for the default fast regression lane",
)


def pytest_configure(config: pytest.Config) -> None:
    """Register project markers without modifying the CONTRACTS-owned pyproject."""
    for marker in MARKERS:
        config.addinivalue_line("markers", marker)
