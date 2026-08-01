from __future__ import annotations

from pathlib import Path

import pytest
from town_core.catalogs import load_catalog
from town_core.domain.config_models import CatalogBundle

CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config" / "v0"


@pytest.fixture(scope="session")
def catalog() -> CatalogBundle:
    return load_catalog(CONFIG_ROOT)
