"""Repository import bootstrap for cross-component tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


M2_MARKERS = {
    "batchmode": "Unity batchmode execution or evidence validation",
    "graybox": "M2 functional gray-box bridge coverage",
    "m2": "M2 Unity bridge acceptance and contract coverage",
    "protocol": "versioned Python/Unity protocol coverage",
    "unity": "Unity-owned runtime or exported evidence coverage",
    "unity_pending": "temporary marker allowed only before the M2 Unity runtime is integrated",
}


def pytest_configure(config: pytest.Config) -> None:
    for name, description in M2_MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {description}")
