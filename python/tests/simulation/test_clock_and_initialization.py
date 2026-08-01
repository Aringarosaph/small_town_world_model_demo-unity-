from __future__ import annotations

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.simulation.clock import RuntimeMode, accept_advanced_game_minute, approve_time_scale
from town_core.simulation.initialization import build_initial_world_state, state_hash


def test_clock_accepts_only_absolute_forward_game_minutes() -> None:
    advance = accept_advanced_game_minute(10, 14)

    assert list(advance.minutes()) == [11, 12, 13, 14]
    assert advance.elapsed_game_minutes == 4
    with pytest.raises(ValueError, match="advance"):
        accept_advanced_game_minute(10, 10)
    with pytest.raises(ValueError, match="non-negative"):
        accept_advanced_game_minute(-1, 0)


@pytest.mark.parametrize("scale", [0.0, 1.0, 2.0, 4.0])
def test_live_time_scale_allowlist(scale: float) -> None:
    assert approve_time_scale(scale, RuntimeMode.UNITY_LIVE) == scale


def test_headless_scale_is_driver_metadata_not_authority_time() -> None:
    assert approve_time_scale(256.0, RuntimeMode.HEADLESS_FAST) == 256.0
    with pytest.raises(ValueError, match="one of"):
        approve_time_scale(3.0, RuntimeMode.UNITY_LIVE)


def test_initial_world_has_one_active_agent_and_complete_deterministic_edges(catalog: CatalogBundle) -> None:
    first = build_initial_world_state(catalog, seed=12345, active_agent_id="npc_01")
    repeat = build_initial_world_state(catalog, seed=12345, active_agent_id="npc_01")
    other_seed = build_initial_world_state(catalog, seed=12346, active_agent_id="npc_01")

    assert [agent.agent_id for agent in first.agents.values() if agent.enabled] == ["npc_01"]
    assert all(not first.agents[f"npc_{index:02d}"].enabled for index in range(2, 11))
    assert len(first.relationships) == 90
    assert len({(edge.source_agent_id, edge.target_agent_id) for edge in first.relationships}) == 90
    assert state_hash(first) == state_hash(repeat)
    assert first.relationships != other_seed.relationships
    assert len(first.objects) == 34
    assert all(item.metadata["fixture_id"] == "stwm.m1.headless-semantic-objects/v1" for item in first.objects.values())


def test_initialization_preserves_all_household_memberships(catalog: CatalogBundle) -> None:
    state = build_initial_world_state(catalog, active_agent_id="npc_01")
    configured = {item.household_id: item.member_ids for item in catalog.households.households}

    assert {household_id: household.member_ids for household_id, household in state.households.items()} == configured
