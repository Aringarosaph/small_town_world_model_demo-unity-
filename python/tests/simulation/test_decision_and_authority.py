from __future__ import annotations

import copy

import pytest
from town_core.decision.candidates import CandidateEnumerator
from town_core.decision.outcomes import HeuristicOutcomeProvider
from town_core.decision.resolver import CentralResolver
from town_core.decision.utility import UtilityScorer
from town_core.domain.config_models import CatalogBundle
from town_core.domain.decision_models import ActionProposal, CandidateAction
from town_core.domain.enums import BehaviorId, EventType, ProposalResult
from town_core.events import EventLedger
from town_core.simulation.initialization import build_initial_world_state, state_hash
from town_core.simulation.run import authority_log_hash


def _proposal(candidate: CandidateAction, state_version: int) -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal_00000001",
        state_version=state_version,
        actor_id=candidate.actor_id,
        candidate_id=candidate.candidate_id,
        behavior_id=candidate.behavior_id,
        target_agent_id=None,
        target_object_ids=candidate.target_object_ids,
        score=0.0,
        model_prediction_id="prediction_00000001",
    )


def test_candidates_are_catalog_backed_and_limited_to_m1(catalog: CatalogBundle) -> None:
    state = build_initial_world_state(catalog)
    candidates = CandidateEnumerator(catalog).enumerate(state, "npc_01", work_window=None)

    assert {item.behavior_id for item in candidates} == {
        BehaviorId.IDLE,
        BehaviorId.SLEEP,
        BehaviorId.EAT_AT_HOME,
    }
    assert candidates[0].behavior_id is BehaviorId.IDLE
    assert all(item.route_planning.value == "DISABLED" for item in candidates)


def test_outcome_and_utility_tie_break_are_repeatable(catalog: CatalogBundle) -> None:
    state = build_initial_world_state(catalog, seed=12345)
    candidates = CandidateEnumerator(catalog).enumerate(state, "npc_01", work_window=None)
    provider = HeuristicOutcomeProvider(catalog)
    predictions = {
        candidate.candidate_id: provider.predict(state, candidate, prediction_sequence=index)
        for index, candidate in enumerate(candidates, start=1)
    }
    scorer = UtilityScorer(catalog)

    first = scorer.score_all(state, candidates, predictions, work_window=None, recent_behavior=None)
    repeat = scorer.score_all(state, candidates, predictions, work_window=None, recent_behavior=None)

    assert first == repeat
    assert all(set(item.utility_terms) >= {"needs", "schedule", "travel_cost", "deterministic_noise"} for item in first)


def test_resolver_rejects_stale_state_without_mutation(catalog: CatalogBundle) -> None:
    state = build_initial_world_state(catalog)
    candidate = CandidateEnumerator(catalog).enumerate(state, "npc_01", work_window=None)[0]
    before = state_hash(state)

    resolution = CentralResolver(catalog).resolve(
        state,
        _proposal(candidate, state.state_version + 1),
        candidate,
        reserved_food_units=0,
        work_window=None,
    )

    assert resolution.result is ProposalResult.STATE_STALE
    assert state_hash(state) == before


def test_eat_resolver_reserves_two_slots_and_one_food_unit(catalog: CatalogBundle) -> None:
    state = build_initial_world_state(catalog)
    candidates = CandidateEnumerator(catalog).enumerate(state, "npc_01", work_window=None)
    candidate = next(item for item in candidates if item.behavior_id is BehaviorId.EAT_AT_HOME)

    resolution = CentralResolver(catalog).resolve(
        state,
        _proposal(candidate, state.state_version),
        candidate,
        reserved_food_units=0,
        work_window=None,
    )

    assert resolution.result is ProposalResult.ACCEPTED
    assert resolution.household_food_units == 1
    assert len(resolution.slot_reservations) == 2
    assert not any(obj.occupied_slots for obj in state.objects.values())


def test_event_ledger_rejects_mutation_like_duplicate_append(catalog: CatalogBundle) -> None:
    ledger = EventLedger(catalog)
    event = ledger.create(
        EventType.MEAL_CONSUMED,
        staged_offset=0,
        game_minute=1,
        location_id="home_a",
        actor_ids=["npc_01"],
        affected_agent_ids=["npc_01"],
        witness_agent_ids=[],
        source_action_id=None,
        payload={"food_units": 1},
    )
    ledger.commit([event])

    with pytest.raises(ValueError, match="order"):
        ledger.commit([event.model_copy(update={"payload": {"food_units": 99}})])

    assert ledger.events == (event,)


@pytest.mark.parametrize("kind", ["decisions", "actions", "transactions", "events"])
def test_authority_log_hash_covers_each_ordered_authority_log(kind: str) -> None:
    records = {name: [{"sequence": 1}] for name in ("decisions", "actions", "transactions", "events")}
    baseline = authority_log_hash(records)
    tampered = copy.deepcopy(records)
    tampered[kind][0]["sequence"] = 2

    assert authority_log_hash(tampered) != baseline
