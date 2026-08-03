from __future__ import annotations

from collections.abc import Mapping

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId, EventType, EventWitnessScope
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.state_models import RelationshipState, WorldEvent, WorldState
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.models import ConversationRecord, ScoredSocietyCandidate, WorkSessionRecord
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
            update={"game_minute": 485, "state_version": 485, "agents": agents, "locations": locations}
        )
        work_session = WorkSessionRecord(
            session_id="work_session_npc_01_day_0000",
            agent_id="npc_01",
            day=0,
            start_game_minute=360,
            end_game_minute=840,
            grace_minutes=15,
            effective_work_minutes=125,
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


def test_completion_safe_break_is_selected_once_without_consuming_wage_grace(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    state, work_session, conversations = _state_for_behavior(catalog, m3_catalogs, BehaviorId.TAKE_BREAK)
    assert work_session is not None
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        "npc_01",
        work_session=work_session,
        conversations=conversations,
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.WORK_SHIFT, BehaviorId.TAKE_BREAK}),
    )
    predictions = {
        item.candidate.candidate_id: rulebook.predict(
            state,
            item,
            prediction_id=f"prediction_{index:08d}",
        )
        for index, item in enumerate(candidates, start=1)
    }
    scored = rulebook.score_candidates(
        state,
        candidates,
        predictions,
        work_session=work_session,
        recent_behavior=None,
        event_importance={},
    )
    selected = scored[0].candidate.candidate
    scheduled = work_session.end_game_minute - work_session.start_game_minute
    projected_effective = work_session.effective_work_minutes + (
        work_session.end_game_minute - state.game_minute - selected.estimated_duration_minutes
    )

    assert selected.behavior_id is BehaviorId.TAKE_BREAK
    assert projected_effective >= scheduled - work_session.grace_minutes
    completed = work_session.model_copy(update={"completed_break_action_ids": ["action_00000001"]})
    assert (
        rulebook.enumerate_candidates(
            state,
            "npc_01",
            work_session=completed,
            conversations=conversations,
            event_importance={},
            reserved_money=0,
            reserved_food=0,
            next_candidate_id=next_id,
            behavior_allowlist=frozenset({BehaviorId.TAKE_BREAK}),
        )
        == []
    )
    with pytest.raises(ValueError, match="at most one completed break"):
        WorkSessionRecord.model_validate(
            {
                **work_session.model_dump(mode="json"),
                "completed_break_action_ids": ["action_00000001", "action_00000002"],
            }
        )


def test_target_related_negative_event_unlocks_and_prioritizes_confront(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    event = WorldEvent(
        event_id="event_00000001",
        event_type=EventType.AWKWARD_INTERACTION,
        game_minute=9,
        location_id="home_a",
        actor_ids=["npc_01"],
        affected_agent_ids=["npc_02"],
        witness_agent_ids=[],
        source_action_id="action_00000001",
        importance=0.45,
        witness_scope=EventWitnessScope.HIGH_LEVEL_LOCATION,
        payload={"accepted": False},
    )
    agents = dict(checkpoint.world.agents)
    agents["npc_01"] = agents["npc_01"].model_copy(update={"known_event_ids": [event.event_id]})
    state = checkpoint.world.model_copy(
        update={"game_minute": 10, "state_version": 10, "event_cursor": 1, "agents": agents}
    )
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        "npc_01",
        work_session=None,
        conversations={},
        event_importance={event.event_id: float(event.importance)},
        events_by_id={event.event_id: event},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.CHAT, BehaviorId.CONFRONT}),
    )
    predictions = {
        item.candidate.candidate_id: rulebook.predict(
            state,
            item,
            prediction_id=f"prediction_{index:08d}",
        )
        for index, item in enumerate(candidates, start=1)
    }
    scored = rulebook.score_candidates(
        state,
        candidates,
        predictions,
        work_session=None,
        recent_behavior=None,
        event_importance={event.event_id: float(event.importance)},
    )
    confront = next(item for item in candidates if item.candidate.behavior_id is BehaviorId.CONFRONT)

    assert confront.selected_context_event_id == event.event_id
    assert scored[0].candidate.candidate.behavior_id is BehaviorId.CONFRONT
    assert scored[0].utility_terms["conflict_response"] > 0.0


def test_low_household_food_supply_outranks_individual_discretionary_actions(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    state, _, conversations = _state_for_behavior(catalog, m3_catalogs, BehaviorId.BUY_GROCERIES)
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        "npc_01",
        work_session=None,
        conversations=conversations,
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.BUY_GROCERIES, BehaviorId.EAT_AT_CAFE}),
    )
    predictions = {
        item.candidate.candidate_id: rulebook.predict(
            state,
            item,
            prediction_id=f"prediction_{index:08d}",
        )
        for index, item in enumerate(candidates, start=1)
    }
    scored = rulebook.score_candidates(
        state,
        candidates,
        predictions,
        work_session=None,
        recent_behavior=None,
        event_importance={},
    )

    assert scored[0].candidate.candidate.behavior_id is BehaviorId.BUY_GROCERIES
    assert scored[0].utility_terms["household_food_supply"] > 0.0


def test_hunger_recovery_activates_before_the_eight_hour_business_closure(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    actor = checkpoint.world.agents["npc_01"]
    agents = dict(checkpoint.world.agents)
    agents[actor.agent_id] = actor.model_copy(update={"needs": actor.needs.model_copy(update={"hunger": 0.39})})
    state = checkpoint.world.model_copy(update={"game_minute": 600, "state_version": 600, "agents": agents})
    rulebook = SocietyRulebook(catalog)
    work_session = WorkSessionRecord(
        session_id="work_session_npc_01_day_0000",
        agent_id="npc_01",
        day=0,
        start_game_minute=360,
        end_game_minute=840,
        grace_minutes=15,
        effective_work_minutes=240,
    )
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        actor.agent_id,
        work_session=work_session,
        conversations={},
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.EAT_AT_CAFE, BehaviorId.SLEEP}),
    )
    predictions = {
        item.candidate.candidate_id: rulebook.predict(
            state,
            item,
            prediction_id=f"prediction_{index:08d}",
        )
        for index, item in enumerate(candidates, start=1)
    }
    scored = rulebook.score_candidates(
        state,
        candidates,
        predictions,
        work_session=work_session,
        recent_behavior=None,
        event_importance={},
    )

    assert scored[0].candidate.candidate.behavior_id is BehaviorId.EAT_AT_CAFE
    assert scored[0].utility_terms["need_crisis_recovery"] > 0.0


def test_low_social_need_bounds_sleep_before_zero(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    actor = checkpoint.world.agents["npc_01"]
    agents = dict(checkpoint.world.agents)
    agents[actor.agent_id] = actor.model_copy(update={"needs": actor.needs.model_copy(update={"social": 0.29})})
    state = checkpoint.world.model_copy(update={"game_minute": 600, "state_version": 600, "agents": agents})
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        actor.agent_id,
        work_session=None,
        conversations={},
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.SLEEP}),
    )

    sleep = next(item for item in candidates if item.candidate.behavior_id is BehaviorId.SLEEP)
    assert sleep.candidate.estimated_duration_minutes <= 120


def test_local_open_bar_opportunity_is_bounded_by_location_and_work(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=24680)
    actor = checkpoint.world.agents["npc_01"]
    agents = dict(checkpoint.world.agents)
    locations = dict(checkpoint.world.locations)
    home = locations[actor.home_location_id]
    bar = locations["cafe_bar"]
    agents[actor.agent_id] = actor.model_copy(
        update={
            "current_location_id": "cafe_bar",
            "needs": actor.needs.model_copy(update={"energy": 0.57, "fun": 0.77}),
        }
    )
    locations[home.location_id] = home.model_copy(
        update={"current_agent_ids": [item for item in home.current_agent_ids if item != actor.agent_id]}
    )
    locations[bar.location_id] = bar.model_copy(
        update={"current_agent_ids": sorted([*bar.current_agent_ids, actor.agent_id])}
    )
    state = checkpoint.world.model_copy(
        update={
            "game_minute": 600,
            "state_version": 600,
            "agents": agents,
            "locations": locations,
        }
    )
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    def score(work_session: WorkSessionRecord | None) -> dict[BehaviorId, ScoredSocietyCandidate]:
        candidates = rulebook.enumerate_candidates(
            state,
            actor.agent_id,
            work_session=work_session,
            conversations={},
            event_importance={},
            reserved_money=0,
            reserved_food=0,
            next_candidate_id=next_id,
            behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.DRINK_AT_BAR, BehaviorId.WATCH_TV}),
        )
        predictions = {
            item.candidate.candidate_id: rulebook.predict(
                state,
                item,
                prediction_id=f"prediction_{index:08d}",
            )
            for index, item in enumerate(candidates, start=1)
        }
        return {
            item.candidate.candidate.behavior_id: item
            for item in rulebook.score_candidates(
                state,
                candidates,
                predictions,
                work_session=work_session,
                recent_behavior=None,
                event_importance={},
            )
        }

    available = score(None)
    assert available[BehaviorId.DRINK_AT_BAR].utility_terms["local_bar_opportunity"] == 0.10
    assert available[BehaviorId.DRINK_AT_BAR].total_score > available[BehaviorId.WATCH_TV].total_score

    due_work = WorkSessionRecord(
        session_id="work_session_npc_01_day_0000",
        agent_id=actor.agent_id,
        day=0,
        start_game_minute=360,
        end_game_minute=840,
        grace_minutes=15,
    )
    during_work = score(due_work)
    assert during_work[BehaviorId.DRINK_AT_BAR].utility_terms["local_bar_opportunity"] == 0.0

    closed_state = state.model_copy(update={"game_minute": 120, "state_version": 120})
    closed_candidate = next(
        item
        for item in rulebook.enumerate_candidates(
            closed_state,
            actor.agent_id,
            work_session=None,
            conversations={},
            event_importance={},
            reserved_money=0,
            reserved_food=0,
            next_candidate_id=next_id,
            behavior_allowlist=frozenset({BehaviorId.DRINK_AT_BAR}),
        )
        if item.candidate.behavior_id is BehaviorId.DRINK_AT_BAR
    )
    closed_prediction = rulebook.predict(closed_state, closed_candidate, prediction_id="prediction_99999999")
    closed_score = rulebook.score_candidates(
        closed_state,
        [closed_candidate],
        {closed_candidate.candidate.candidate_id: closed_prediction},
        work_session=None,
        recent_behavior=None,
        event_importance={},
    )[0]
    assert closed_score.utility_terms["local_bar_opportunity"] == 0.0


def test_zero_need_recovery_blocks_work_and_bounds_discretionary_duration(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    actor = checkpoint.world.agents["npc_01"]
    agents = dict(checkpoint.world.agents)
    agents[actor.agent_id] = actor.model_copy(
        update={
            "needs": actor.needs.model_copy(update={"hunger": 0.0, "social": 0.0}),
        }
    )
    state = checkpoint.world.model_copy(update={"game_minute": 600, "state_version": 600, "agents": agents})
    work_session = WorkSessionRecord(
        session_id="work_session_npc_01_day_0000",
        agent_id="npc_01",
        day=0,
        start_game_minute=360,
        end_game_minute=840,
        grace_minutes=15,
        effective_work_minutes=240,
    )
    rulebook = SocietyRulebook(catalog)
    candidate_number = 0

    def next_id() -> str:
        nonlocal candidate_number
        candidate_number += 1
        return f"candidate_{candidate_number:08d}"

    candidates = rulebook.enumerate_candidates(
        state,
        actor.agent_id,
        work_session=work_session,
        conversations={},
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=next_id,
        behavior_allowlist=frozenset(
            {
                BehaviorId.IDLE,
                BehaviorId.WORK_SHIFT,
                BehaviorId.EAT_AT_CAFE,
                BehaviorId.WATCH_TV,
                BehaviorId.SLEEP,
            }
        ),
    )
    predictions = {
        item.candidate.candidate_id: rulebook.predict(
            state,
            item,
            prediction_id=f"prediction_{index:08d}",
        )
        for index, item in enumerate(candidates, start=1)
    }
    scored = rulebook.score_candidates(
        state,
        candidates,
        predictions,
        work_session=work_session,
        recent_behavior=None,
        event_importance={},
    )

    assert scored[0].candidate.candidate.behavior_id is BehaviorId.EAT_AT_CAFE
    work = next(item for item in scored if item.candidate.candidate.behavior_id is BehaviorId.WORK_SHIFT)
    assert work.utility_terms["critical_need_block"] == -200.0
    watch_score = next(item for item in scored if item.candidate.candidate.behavior_id is BehaviorId.WATCH_TV)
    sleep_score = next(item for item in scored if item.candidate.candidate.behavior_id is BehaviorId.SLEEP)
    assert watch_score.utility_terms["critical_need_block"] == -200.0
    assert sleep_score.utility_terms["critical_need_block"] == -200.0
    watch = next(item for item in candidates if item.candidate.behavior_id is BehaviorId.WATCH_TV)
    assert watch.candidate.estimated_duration_minutes == 30
    sleep = next(item for item in candidates if item.candidate.behavior_id is BehaviorId.SLEEP)
    assert sleep.candidate.estimated_duration_minutes == 30
