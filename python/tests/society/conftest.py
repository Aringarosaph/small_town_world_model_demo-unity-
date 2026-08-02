from __future__ import annotations

from pathlib import Path

import pytest
from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.initialization import ManifestSemanticObjectFixture

CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config" / "v0"


@pytest.fixture(scope="session")
def catalog() -> CatalogBundle:
    return load_catalog(CONFIG_ROOT)


@pytest.fixture(scope="session")
def m3_catalogs(catalog: CatalogBundle) -> M3Catalogs:
    return load_m3_catalogs(CONFIG_ROOT, catalog=catalog)


@pytest.fixture(scope="session")
def society_object_fixture(m3_catalogs: M3Catalogs) -> ManifestSemanticObjectFixture:
    return ManifestSemanticObjectFixture(m3_catalogs.semantic_instances)
