from __future__ import annotations

from collections.abc import Mapping

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.state_models import RelationshipState, WorldState
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.models import ConversationRecord, WorkSessionRecord
from town_core.society.rules import SocietyRulebook


def _state_for_behavior(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
) -> tuple[WorldState, WorkSessionRecord | None, Mapping[str, ConversationRecord]]:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    state = checkpoint.world
    work_session: WorkSessionRecord | None = None
    conversations: Mapping[str, ConversationRecord] = {}
    agent = state.agents["npc_01"]

    if behavior_id is BehaviorId.WORK_SHIFT:
        state = state.model_copy(update={"game_minute": 300, "state_version": 300})
        work_session = WorkSessionRecord(
            session_id="work_session_npc_01_day_0000",
            agent_id="npc_01",
            day=0,
            start_game_minute=360,
            end_game_minute=840,
            grace_minutes=15,
        )
    elif behavior_id is BehaviorId.TAKE_BREAK:
        locations = dict(state.locations)
        home = locations[agent.home_location_id]
        work = locations[agent.assigned_work_location_id]
        locations[home.location_id] = home.model_copy(
            update={"current_agent_ids": [item for item in home.current_agent_ids if item != agent.agent_id]}
        )
        locations[work.location_id] = work.model_copy(
            update={"current_agent_ids": sorted([*work.current_agent_ids, agent.agent_id])}
        )
        agents = dict(state.agents)
        agents[agent.agent_id] = agent.model_copy(update={"current_location_id": agent.assigned_work_location_id})
        state = state.model_copy(
            update={"game_minute": 600, "state_version": 600, "agents": agents, "locations": locations}
        )
        work_session = WorkSessionRecord(
            session_id="work_session_npc_01_day_0000",
            agent_id="npc_01",
            day=0,
            start_game_minute=360,
            end_game_minute=840,
            grace_minutes=15,
            effective_work_minutes=120,
        )
    elif behavior_id is BehaviorId.BUY_GROCERIES:
        households = dict(state.households)
        household = households[agent.household_id]
        households[agent.household_id] = household.model_copy(update={"food_units": 0})
        state = state.model_copy(update={"game_minute": 600, "state_version": 600, "households": households})
    elif behavior_id in {
        BehaviorId.EAT_AT_CAFE,
        BehaviorId.DRINK_AT_BAR,
        BehaviorId.WALK_IN_PARK,
        BehaviorId.SIT_IN_PARK,
    }:
        state = state.model_copy(update={"game_minute": 600, "state_version": 600})
    elif behavior_id is BehaviorId.SHARE_EVENT:
        agents = dict(state.agents)
        agents[agent.agent_id] = agent.model_copy(update={"known_event_ids": ["event_00000001"]})
        state = state.model_copy(update={"agents": agents})
    elif behavior_id in {BehaviorId.APOLOGIZE, BehaviorId.CONFRONT}:
        relationships: list[RelationshipState] = []
        for edge in state.relationships:
            if edge.source_agent_id == "npc_02" and edge.target_agent_id == "npc_01":
                edge = edge.model_copy(update={"tension": 0.8})
            relationships.append(edge)
        state = state.model_copy(update={"relationships": relationships})
    elif behavior_id is BehaviorId.END_CONVERSATION:
        conversations = {
            "conversation_00000001": ConversationRecord(
                conversation_id="conversation_00000001",
                participant_ids=["npc_01", "npc_02"],
                started_at_game_minute=0,
                last_activity_game_minute=0,
            )
        }
    return state, work_session, conversations


@pytest.mark.parametrize("behavior_id", list(BehaviorId))
def test_each_catalog_behavior_has_a_targeted_legal_candidate(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
) -> None:
    state, work_session, conversations = _state_for_behavior(catalog, m3_catalogs, behavior_id)
    rulebook = SocietyRulebook(catalog)
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"candidate_{counter:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        "npc_01",
        work_session=work_session,
        conversations=conversations,
        event_importance={"event_00000001": 1.0},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({behavior_id}),
    )

    assert candidates
    assert {item.candidate.behavior_id for item in candidates} == {behavior_id}
    candidate = candidates[0].candidate
    if behavior_id is BehaviorId.EAT_AT_HOME:
        assert candidate.hard_cost_preview.household_food_units == -1
    elif behavior_id is BehaviorId.BUY_GROCERIES:
        assert candidate.hard_cost_preview.household_money == -catalog.economy.groceries.price
        assert candidate.hard_cost_preview.household_food_units == catalog.economy.groceries.food_units_delta
    elif behavior_id is BehaviorId.EAT_AT_CAFE:
        assert candidate.hard_cost_preview.household_money == -catalog.economy.cafe_meal.price
    elif behavior_id is BehaviorId.DRINK_AT_BAR:
        assert candidate.hard_cost_preview.household_money == -catalog.economy.bar_drink.price


def test_unknown_share_event_and_low_tension_social_candidates_are_rejected(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    rulebook = SocietyRulebook(catalog)
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"candidate_{counter:08d}"

    for behavior_id in (BehaviorId.SHARE_EVENT, BehaviorId.APOLOGIZE, BehaviorId.CONFRONT):
        assert (
            rulebook.enumerate_candidates(
                checkpoint.world,
                "npc_01",
                work_session=None,
                conversations={},
                event_importance={},
                reserved_money=0,
                reserved_food=0,
                next_candidate_id=next_id,
                behavior_allowlist=frozenset({behavior_id}),
            )
            == []
        )
