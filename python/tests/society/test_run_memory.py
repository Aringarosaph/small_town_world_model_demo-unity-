from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import write_checkpoint
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.run import (
    DARWIN_CURRENT_RSS_METHOD,
    LINUX_CURRENT_RSS_METHOD,
    PEAK_RSS_METHOD,
    RSS_SAMPLE_POINT,
    _current_rss_bytes,
    _linear_slope,
    _linux_current_rss_bytes,
    _peak_rss_bytes,
    _rss_collection_method,
    _rss_sample,
    run_society,
)


def test_daily_slope_uses_current_rss_not_peak_high_water() -> None:
    samples = [
        {
            "game_day": day,
            "game_minute": day * 1440,
            "current_rss_bytes": 50_000_000,
            "peak_rss_bytes": 50_000_000 + day * 5_000_000,
        }
        for day in range(4)
    ]

    assert _linear_slope(samples) == 0.0


def test_daily_slope_retains_frozen_post_warmup_boundary() -> None:
    samples = [
        {"game_day": 0, "game_minute": 0, "current_rss_bytes": 1, "peak_rss_bytes": 1},
        {"game_day": 1, "game_minute": 1440, "current_rss_bytes": 10, "peak_rss_bytes": 100},
        {"game_day": 2, "game_minute": 2880, "current_rss_bytes": 30, "peak_rss_bytes": 100},
        {"game_day": 3, "game_minute": 4320, "current_rss_bytes": 50, "peak_rss_bytes": 100},
    ]

    assert _linear_slope(samples) == 20.0


def test_linux_statm_sampler_uses_resident_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statm = tmp_path / "statm"
    statm.write_text("100 7 3 2 1 0 0\n", encoding="ascii")
    monkeypatch.setattr("town_core.society.run.os.sysconf", lambda name: 4096)

    assert _linux_current_rss_bytes(statm) == 7 * 4096


def test_collection_method_names_peak_and_current_sources() -> None:
    method = _rss_collection_method()

    assert method.startswith(f"peak={PEAK_RSS_METHOD}; daily_current=")
    assert method.endswith(f"; daily_sample_point={RSS_SAMPLE_POINT}")
    if platform.system() == "Darwin":
        assert f"daily_current={DARWIN_CURRENT_RSS_METHOD};" in method
    elif platform.system() == "Linux":
        assert f"daily_current={LINUX_CURRENT_RSS_METHOD};" in method


def test_current_rss_sample_is_truthful_and_bounded_by_peak() -> None:
    current = _current_rss_bytes()
    peak = _peak_rss_bytes()
    sample = _rss_sample(2880)

    assert 0 < current <= peak
    assert sample["game_day"] == 2
    assert sample["game_minute"] == 2880
    assert 0 < sample["current_rss_bytes"] <= sample["peak_rss_bytes"]


def test_external_checkpoint_export_remains_detached(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    exported = engine.export_checkpoint()

    exported.world.agents.pop("npc_01")

    assert "npc_01" in engine.state.agents


def test_headless_persistence_avoids_external_deep_export(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_external_export(engine: SocietyEngine) -> object:
        raise AssertionError("headless persistence created an external checkpoint copy")

    monkeypatch.setattr(SocietyEngine, "export_checkpoint", reject_external_export)

    summary = run_society(
        catalog,
        m3_catalogs,
        days=1,
        seed=12345,
        run_path=tmp_path / "headless-persistence",
        chunk_minutes=60,
    )

    assert summary["invariants"] == {"passed": True, "violations": []}


def test_streamed_checkpoint_bytes_match_frozen_json_format(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    expected = (
        json.dumps(
            checkpoint.model_dump(mode="json", exclude_none=False, by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    path = tmp_path / "checkpoint.json"

    write_checkpoint(path, checkpoint)

    assert path.read_bytes() == expected
