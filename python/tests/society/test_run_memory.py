from __future__ import annotations

import json
import os
import platform
import signal
from pathlib import Path

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import (
    checkpoint_hash,
    write_checkpoint,
    write_checkpoint_isolated,
)
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.run import (
    DARWIN_CURRENT_RSS_METHOD,
    LINUX_CURRENT_RSS_METHOD,
    PEAK_RSS_METHOD,
    RSS_SAMPLE_POINT,
    _combined_peak_rss_bytes,
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
    assert f"; daily_sample_point={RSS_SAMPLE_POINT};" in method
    assert method.endswith("atomic sibling replace, parent waitpid before authority resumes")
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
    isolated_path = tmp_path / "isolated-checkpoint.json"

    write_checkpoint(path, checkpoint)
    isolated_result = write_checkpoint_isolated(
        isolated_path,
        checkpoint,
        include_checkpoint_hash=True,
    )

    assert path.read_bytes() == expected
    assert isolated_path.read_bytes() == expected
    assert isolated_result.checkpoint_hash == checkpoint_hash(checkpoint)
    assert isolated_result.peak_rss_bytes > 0


def test_isolated_checkpoint_failure_preserves_target_and_cleans_temporary(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    path = tmp_path / "checkpoint.json"
    temporary = tmp_path / ".checkpoint.json.tmp"
    path.write_text("already committed\n", encoding="utf-8")

    def fail_in_child(
        target: Path,
        value: object,
        *,
        include_checkpoint_hash: bool,
    ) -> str | None:
        del value, include_checkpoint_hash
        target.with_name(f".{target.name}.tmp").write_text("partial", encoding="utf-8")
        raise OSError("targeted checkpoint failure")

    monkeypatch.setattr(
        "town_core.society.checkpoint._write_checkpoint_in_process",
        fail_in_child,
    )

    with pytest.raises(RuntimeError, match="OSError: targeted checkpoint failure"):
        write_checkpoint_isolated(path, checkpoint)

    assert path.read_text(encoding="utf-8") == "already committed\n"
    assert not temporary.exists()


def test_isolated_checkpoint_signal_is_propagated_and_cleans_temporary(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    path = tmp_path / "checkpoint.json"
    temporary = tmp_path / ".checkpoint.json.tmp"

    def terminate_in_child(
        target: Path,
        value: object,
        *,
        include_checkpoint_hash: bool,
    ) -> str | None:
        del value, include_checkpoint_hash
        target.with_name(f".{target.name}.tmp").write_text("partial", encoding="utf-8")
        os.kill(os.getpid(), signal.SIGKILL)
        raise AssertionError("SIGKILL returned unexpectedly")

    monkeypatch.setattr(
        "town_core.society.checkpoint._write_checkpoint_in_process",
        terminate_in_child,
    )

    with pytest.raises(RuntimeError, match=f"terminated by signal {signal.SIGKILL}"):
        write_checkpoint_isolated(path, checkpoint)

    assert not path.exists()
    assert not temporary.exists()


def test_isolated_checkpoint_base_exception_cannot_unwind_into_authority_parent(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    path = tmp_path / "checkpoint.json"

    def interrupt_child(
        target: Path,
        value: object,
        *,
        include_checkpoint_hash: bool,
    ) -> str | None:
        del target, value, include_checkpoint_hash
        raise KeyboardInterrupt("targeted child interrupt")

    monkeypatch.setattr(
        "town_core.society.checkpoint._write_checkpoint_in_process",
        interrupt_child,
    )

    with pytest.raises(RuntimeError, match="KeyboardInterrupt: targeted child interrupt"):
        write_checkpoint_isolated(path, checkpoint)

    assert not path.exists()


def test_isolated_checkpoint_rejects_multithreaded_parent_before_fork(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    monkeypatch.setattr("town_core.society.checkpoint.threading.active_count", lambda: 2)

    with pytest.raises(RuntimeError, match="requires a single-threaded process"):
        write_checkpoint_isolated(tmp_path / "checkpoint.json", checkpoint)


def test_combined_peak_includes_checkpoint_writer_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("town_core.society.run._peak_rss_bytes", lambda: 50_000_000)

    assert _combined_peak_rss_bytes(80_000_000) == 80_000_000
    assert _combined_peak_rss_bytes(40_000_000) == 50_000_000
