"""Repository import bootstrap for QA-owned tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


M3_MARKERS = (
    "m3: M3 complete heuristic society acceptance",
    "m3_fast: M3 fast readiness gate; no release soak",
    "m3_slow: M3 fixed-seed release soak or reference performance gate",
    "society: ten-agent authority and liveness coverage",
    "full_registry: complete M3 semantic manifest and registry coverage",
    "joint_action: central JointAction atomicity coverage",
    "soak7: fixed seven-game-day M3 soak evidence",
    "soak30: fixed thirty-game-day M3 soak evidence",
    "performance: M3 reference-machine performance evidence",
)


def pytest_configure(config: pytest.Config) -> None:
    """Register additive M3 markers without editing shared project config."""
    for marker in M3_MARKERS:
        config.addinivalue_line("markers", marker)
