from __future__ import annotations

import json
from pathlib import Path

import pytest
from town_core.catalogs import load_catalog
from town_core.cli import main
from town_core.replay import replay_run
from town_core.simulation.run import run_headless

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "config" / "v0"

pytestmark = [pytest.mark.integration]


def test_three_day_headless_run_and_replay(tmp_path: Path) -> None:
    catalog = load_catalog(CONFIG_ROOT)
    source = tmp_path / "source-run"
    summary = run_headless(
        catalog,
        active_agent_id="npc_01",
        days=3,
        seed=12345,
        run_path=source,
        chunk_minutes=60,
    )

    assert summary["tick_count"] == 4320
    assert summary["transaction_count"] == 4320
    assert set(summary["selected_behavior_counts"]) == {"idle", "sleep", "eat_at_home", "work_shift"}
    assert all(count > 0 for count in summary["selected_behavior_counts"].values())
    assert len(summary["work_sessions"]) == 3
    assert all(session["finalized"] and session["paid"] for session in summary["work_sessions"])
    assert all(session["effective_work_minutes"] == 480 for session in summary["work_sessions"])
    assert {item.name for item in source.iterdir()} >= {
        "metadata.json",
        "config_snapshot",
        "initial_snapshot.json",
        "decisions.jsonl",
        "actions.jsonl",
        "transactions.jsonl",
        "events.jsonl",
        "final_snapshot.json",
        "summary.json",
    }

    replay = replay_run(source, output_root=tmp_path / "replays")

    assert replay["match"] is True
    assert replay["expected_final_hash"] == summary["final_state_hash"] == replay["actual_final_hash"]
    assert replay["expected_authority_log_hash"] == summary["authority_log_hash"]
    assert replay["actual_authority_log_hash"] == summary["authority_log_hash"]


def test_replay_rejects_descendant_output(tmp_path: Path) -> None:
    source = tmp_path / "source-run"
    run_headless(
        load_catalog(CONFIG_ROOT),
        active_agent_id="npc_01",
        days=1,
        seed=12345,
        run_path=source,
        chunk_minutes=60,
    )

    with pytest.raises(ValueError, match="sibling"):
        replay_run(source, output_root=source / "descendant")


@pytest.mark.parametrize("error", [KeyError("authority_projection"), RuntimeError("source mutated")])
def test_replay_cli_errors_are_nonzero_machine_readable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def fail_replay(_source: Path, *, output_root: Path | None = None) -> dict[str, object]:
        del output_root
        raise error

    monkeypatch.setattr("town_core.cli.replay_run", fail_replay)

    assert main(["replay", "--run", "damaged-run"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["completed"] is False
    assert output["error_type"] == type(error).__name__
