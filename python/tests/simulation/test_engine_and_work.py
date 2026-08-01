from __future__ import annotations

from collections import Counter

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import EventType
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state, state_hash
from town_core.simulation.invariants import assert_world_invariants
from town_core.simulation.qa_adapter import _negative_probes, _work_probe


def _advance_by_chunks(catalog: CatalogBundle, chunk: int) -> tuple[str, Counter[str]]:
    engine = SimulationEngine(catalog, build_initial_world_state(catalog), active_agent_id="npc_01")
    events: Counter[str] = Counter()
    while engine.state.game_minute < 1440:
        target = min(1440, engine.state.game_minute + chunk)
        result = engine.advance_to(target)
        events.update(event.event_type.value for event in result.events)
    assert_world_invariants(engine.state, active_agent_id="npc_01", events=engine.ledger.events)
    return state_hash(engine.state), events


@pytest.mark.parametrize("chunk", [1, 7, 60])
def test_driver_chunk_size_does_not_change_one_day_authority(catalog: CatalogBundle, chunk: int) -> None:
    baseline_hash, baseline_events = _advance_by_chunks(catalog, 1)
    actual_hash, actual_events = _advance_by_chunks(catalog, chunk)

    assert actual_hash == baseline_hash
    assert actual_events == baseline_events


def test_only_active_agent_decays_or_acts(catalog: CatalogBundle) -> None:
    initial = build_initial_world_state(catalog)
    engine = SimulationEngine(catalog, initial, active_agent_id="npc_01")
    engine.advance_to(120)

    assert engine.state.agents["npc_01"] != initial.agents["npc_01"]
    assert all(engine.state.agents[f"npc_{index:02d}"] == initial.agents[f"npc_{index:02d}"] for index in range(2, 11))


def test_work_completed_late_and_missed_are_real_three_state_probes(catalog: CatalogBundle) -> None:
    completed = _work_probe(catalog, "npc_01", "completed")
    late = _work_probe(catalog, "npc_01", "late")
    missed = _work_probe(catalog, "npc_01", "missed")

    assert completed["event_type"] == EventType.WORK_COMPLETED.value
    assert completed["completed"] is True
    assert completed["wage_settlement_count"] == 1
    assert completed["wage_amount"] == catalog.economy.fixed_shift_wage
    assert late["event_type"] == EventType.WORK_LATE.value
    assert late["scheduled_start"] < late["actual_start"] <= late["scheduled_start"] + late["grace_minutes"]
    assert late["completed"] is True
    assert late["wage_settlement_count"] == 1
    assert missed["event_type"] == EventType.WORK_MISSED.value
    assert missed["completed"] is False
    assert missed["wage_settlement_count"] == 0
    assert missed["wage_amount"] == 0


def test_exact_six_negative_probes_reject_without_mutation(catalog: CatalogBundle) -> None:
    probes = _negative_probes(catalog, "npc_01")

    assert {probe["name"] for probe in probes} == {
        "stale_state_version",
        "negative_money",
        "negative_food",
        "needs_out_of_range",
        "overlapping_primary_action",
        "event_mutation",
    }
    assert all(probe["accepted"] is False for probe in probes)
    assert all(probe["state_hash_before"] == probe["state_hash_after"] for probe in probes)
    event_probe = next(probe for probe in probes if probe["name"] == "event_mutation")
    assert event_probe["ledger_hash_before"] == event_probe["ledger_hash_after"]
