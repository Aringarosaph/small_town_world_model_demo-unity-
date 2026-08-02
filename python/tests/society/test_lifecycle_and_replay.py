from __future__ import annotations

from collections import Counter
from typing import Any, cast

import pytest
from town_core.domain.config_models import CatalogBundle, NeedValues
from town_core.domain.enums import BehaviorId, EventType, KnowledgeAcquisitionType, ProposalResult
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import advance_authority_log_hash, checkpoint_hash, knowledge_key
from town_core.society.engine import SocietyEngine, _TickContext
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.invariants import (
    SocietyInvariantViolation,
    assert_society_invariants,
    assert_society_transition,
)
from town_core.society.models import AuthorityCheckpoint
from town_core.society.transactions import apply_transaction_record


def _decision_fixture(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    *,
    minute: int,
    locations_by_agent: dict[str, str],
    due_agent_ids: set[str] | frozenset[str],
    hungry_agent_ids: set[str] | frozenset[str] = frozenset(),
    empty_food_agent_id: str | None = None,
) -> AuthorityCheckpoint:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = dict(checkpoint.world.agents)
    locations = dict(checkpoint.world.locations)
    moved = set(locations_by_agent)
    for location_id, location in locations.items():
        locations[location_id] = location.model_copy(
            update={"current_agent_ids": [item for item in location.current_agent_ids if item not in moved]}
        )
    for agent_id, location_id in locations_by_agent.items():
        location = locations[location_id]
        locations[location_id] = location.model_copy(
            update={"current_agent_ids": sorted([*location.current_agent_ids, agent_id])}
        )
    for agent_id, agent in agents.items():
        needs = agent.needs
        if agent_id in hungry_agent_ids:
            needs = NeedValues(hunger=0.0, energy=1.0, hygiene=1.0, fun=1.0, social=1.0)
        agents[agent_id] = agent.model_copy(
            update={
                "current_location_id": locations_by_agent.get(agent_id, agent.current_location_id),
                "decision_due_at": minute if agent_id in due_agent_ids else minute + 10_000,
                "needs": needs,
            }
        )
    households = dict(checkpoint.world.households)
    if empty_food_agent_id is not None:
        household_id = agents[empty_food_agent_id].household_id
        households[household_id] = households[household_id].model_copy(update={"food_units": 0})
    world = checkpoint.world.model_copy(
        update={
            "game_minute": minute - 1,
            "state_version": minute - 1,
            "agents": agents,
            "households": households,
            "locations": locations,
        }
    )
    recent = {**checkpoint.recent_behaviors, **dict.fromkeys(due_agent_ids, BehaviorId.IDLE)}
    return checkpoint.model_copy(update={"world": world, "recent_behaviors": recent})


def test_closed_shop_idle_fallback_survives_same_batch_object_conflict(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    """Minimal construction of the seed-12345/day-3/minute-5340 failure."""

    checkpoint = _decision_fixture(
        catalog,
        m3_catalogs,
        minute=1020,
        locations_by_agent={"npc_05": "cafe_bar", "npc_07": "shop"},
        due_agent_ids={"npc_05", "npc_07"},
        hungry_agent_ids={"npc_05", "npc_07"},
    )
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.EAT_AT_CAFE}),
    )

    result = engine.advance_to(1020)
    decisions = {str(item["agent_id"]): item for item in result.decisions}

    assert engine.rulebook.location_open("shop", 1020) is False
    assert decisions["npc_05"]["selected_behavior_id"] == BehaviorId.EAT_AT_CAFE.value
    assert decisions["npc_07"]["selected_behavior_id"] == BehaviorId.IDLE.value
    resolver_attempts = cast(list[dict[str, object]], decisions["npc_07"]["resolver_attempts"])
    assert [item["result"] for item in resolver_attempts] == [
        ProposalResult.OBJECT_SLOT_CONFLICT.value,
        ProposalResult.ACCEPTED.value,
    ]
    idle_action_id = str(decisions["npc_07"]["selected_action_id"])
    idle_runtime = engine.export_checkpoint().action_runtimes[idle_action_id]
    assert all(
        engine.export_checkpoint().reservations[item].kind != "LOCATION" for item in idle_runtime.reservation_ids
    )


@pytest.mark.parametrize(
    ("behavior_id", "agent_id", "location_id", "minute", "hungry", "empty_food"),
    [
        (BehaviorId.EAT_AT_CAFE, "npc_01", "cafe_bar", 1, True, False),
        (BehaviorId.BUY_GROCERIES, "npc_05", "shop", 1, False, True),
        (BehaviorId.WORK_SHIFT, "npc_01", "cafe_bar", 300, False, False),
    ],
)
def test_closed_business_actions_remain_rejected_before_local_idle_fallback(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
    agent_id: str,
    location_id: str,
    minute: int,
    hungry: bool,
    empty_food: bool,
) -> None:
    checkpoint = _decision_fixture(
        catalog,
        m3_catalogs,
        minute=minute,
        locations_by_agent={agent_id: location_id},
        due_agent_ids={agent_id},
        hungry_agent_ids={agent_id} if hungry else frozenset(),
        empty_food_agent_id=agent_id if empty_food else None,
    )
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE, behavior_id}),
    )

    result = engine.advance_to(minute)
    decision = next(item for item in result.decisions if item["agent_id"] == agent_id)

    assert engine.rulebook.location_open(location_id, minute) is False
    assert decision["selected_behavior_id"] == BehaviorId.IDLE.value
    resolver_attempts = cast(list[dict[str, object]], decision["resolver_attempts"])
    assert [item["result"] for item in resolver_attempts] == [
        ProposalResult.LOCATION_CLOSED.value,
        ProposalResult.ACCEPTED.value,
    ]


def test_cross_location_idle_cannot_bypass_closed_location_gate(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = _decision_fixture(
        catalog,
        m3_catalogs,
        minute=1,
        locations_by_agent={"npc_01": "cafe_bar"},
        due_agent_ids={"npc_01"},
    )
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE}),
    )
    local_context = _TickContext(checkpoint, 1)
    source = local_context.provisional_world(state_version=checkpoint.world.state_version)
    candidates = engine.rulebook.enumerate_candidates(
        source,
        "npc_01",
        work_session=None,
        conversations={},
        event_importance={},
        reserved_money=0,
        reserved_food=0,
        next_candidate_id=iter(["candidate_00000001"]).__next__,
        behavior_allowlist=frozenset({BehaviorId.IDLE}),
    )
    prediction = engine.rulebook.predict(source, candidates[0], prediction_id="prediction_00000001")
    local_scored = engine.rulebook.score_candidates(
        source,
        candidates,
        {"candidate_00000001": prediction},
        work_session=None,
        recent_behavior=None,
        event_importance={},
    )[0]
    local_proposal = engine._proposal(source, local_scored, "proposal_00000001")
    local_result, local_action_id = engine._resolve_and_create(
        local_context,
        source,
        local_proposal,
        local_scored,
    )

    assert local_result is ProposalResult.ACCEPTED
    assert local_action_id is not None
    assert all(
        local_context.reservations[item].kind != "LOCATION"
        for item in local_context.action_runtimes[local_action_id].reservation_ids
    )

    remote_candidate = local_scored.candidate.candidate.model_copy(
        update={"destination_location_id": "shop", "estimated_travel_minutes": 6}
    )
    remote_scored = local_scored.model_copy(
        update={"candidate": local_scored.candidate.model_copy(update={"candidate": remote_candidate})}
    )
    remote_context = _TickContext(checkpoint, 1)
    remote_proposal = engine._proposal(source, remote_scored, "proposal_00000002")
    remote_result, remote_action_id = engine._resolve_and_create(
        remote_context,
        source,
        remote_proposal,
        remote_scored,
    )

    assert engine.rulebook.location_open("shop", 7) is False
    assert remote_result is ProposalResult.LOCATION_CLOSED
    assert remote_action_id is None


def test_cancel_releases_participant_object_and_resource_reservations_atomically(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = {
        agent_id: agent.model_copy(update={"needs": NeedValues(**{**agent.needs.model_dump(), "energy": 0.0})})
        for agent_id, agent in checkpoint.world.agents.items()
    }
    checkpoint = checkpoint.model_copy(update={"world": checkpoint.world.model_copy(update={"agents": agents})})
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.SLEEP}),
    )
    engine.advance_to(1)
    action_id = min(engine.state.active_actions)
    reservation_ids = {
        item.reservation_id
        for item in engine.export_checkpoint().reservations.values()
        if item.owner_action_id == action_id
    }
    assert reservation_ids

    engine.cancel_action(action_id, reason="TARGETED_TEST_CANCEL")
    final = engine.export_checkpoint()

    assert action_id not in final.world.active_actions
    assert action_id not in final.action_runtimes
    assert not reservation_ids.intersection(final.reservations)
    assert all(action_id not in obj.occupied_slots.values() for obj in final.world.objects.values())
    assert_society_invariants(final, catalog, m3_catalogs)


def test_transaction_patch_replay_matches_checkpoint_exactly(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=24680)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    result = engine.advance_to(90)

    replayed = initial
    sequence = replayed.authority_record_count
    authority_hash = replayed.authority_log_hash
    for raw_record in result.authority_records:
        sequence += 1
        envelope = {
            "schema": "stwm.simulation.m3-authority-record/v1",
            "sequence": sequence,
            "kind": raw_record["kind"],
            "payload": raw_record["payload"],
        }
        if raw_record["kind"] == "transaction":
            payload = raw_record["payload"]
            assert isinstance(payload, dict)
            replayed = apply_transaction_record(replayed, payload)
        authority_hash = advance_authority_log_hash(authority_hash, envelope)
        replayed = replayed.model_copy(
            update={"authority_record_count": sequence, "authority_log_hash": authority_hash}
        )

    assert checkpoint_hash(replayed) == checkpoint_hash(engine.export_checkpoint())
    assert replayed == engine.export_checkpoint()
    assert_society_invariants(replayed, catalog, m3_catalogs)


def test_driver_chunk_size_does_not_change_short_society_authority(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    hashes: list[str] = []
    for chunk in (1, 7, 60):
        initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=97531)
        engine = SocietyEngine(catalog, m3_catalogs, initial)
        while engine.state.game_minute < 180:
            engine.advance_to(min(180, engine.state.game_minute + chunk))
        hashes.append(checkpoint_hash(engine.export_checkpoint()))

    assert hashes[0] == hashes[1] == hashes[2]


def test_transition_invariant_checks_event_prefix_without_materializing_a_slice(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=97531)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    for minute in range(1, 121):
        engine.advance_to(minute)
        if engine.checkpoint.events:
            break
    assert engine.checkpoint.events
    previous = engine.checkpoint
    engine.advance_to(engine.state.game_minute + 1)
    committed = engine.checkpoint

    assert_society_transition(previous, committed)
    events = list(committed.events)
    first = events[0]
    events[0] = first.model_copy(update={"payload": {**first.payload, "tampered": True}})
    tampered = committed.model_copy(update={"events": events})

    with pytest.raises(SocietyInvariantViolation, match="event ledger history was mutated"):
        assert_society_transition(previous, tampered)


def test_knowledge_invariant_checks_canonical_append_order_without_sort_copies(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=97531)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    agent_id: str | None = None
    for target in range(120, 1441, 120):
        engine.advance_to(target)
        agent_id = next(
            (candidate_id for candidate_id, agent in engine.state.agents.items() if len(agent.known_event_ids) >= 2),
            None,
        )
        if agent_id is not None:
            break
    assert agent_id is not None
    checkpoint = engine.checkpoint
    agents = dict(checkpoint.world.agents)
    agent = agents[agent_id]
    agents[agent_id] = agent.model_copy(update={"known_event_ids": list(reversed(agent.known_event_ids))})
    tampered = checkpoint.model_copy(update={"world": checkpoint.world.model_copy(update={"agents": agents})})

    with pytest.raises(SocietyInvariantViolation, match=f"public knowledge permission mismatch: {agent_id}"):
        assert_society_invariants(tampered, catalog, m3_catalogs)


def test_joint_action_cancel_releases_every_participant_and_reservation(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = {
        agent_id: agent.model_copy(
            update={"needs": NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.0, social=0.0)}
        )
        for agent_id, agent in checkpoint.world.agents.items()
    }
    checkpoint = checkpoint.model_copy(update={"world": checkpoint.world.model_copy(update={"agents": agents})})
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.INVITE_JOIN}),
    )
    for minute in range(1, 121):
        engine.advance_to(minute)
        if engine.export_checkpoint().joint_actions:
            break
    active = engine.export_checkpoint()
    assert active.joint_actions
    action_id = min(active.joint_actions)
    participants = list(active.world.active_actions[action_id].agent_ids)
    reservation_ids = set(active.action_runtimes[action_id].reservation_ids)

    engine.cancel_action(action_id, reason="TARGETED_JOINT_CANCEL")
    final = engine.export_checkpoint()

    assert action_id not in final.joint_actions
    assert action_id not in final.world.active_actions
    assert action_id not in final.action_runtimes
    assert not reservation_ids.intersection(final.reservations)
    assert all(final.world.agents[agent_id].current_action_id is None for agent_id in participants)
    assert all(action_id not in obj.occupied_slots.values() for obj in final.world.objects.values())
    assert_society_invariants(final, catalog, m3_catalogs)


def test_relationship_direction_witness_and_told_permissions_use_real_social_actions(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    agents = {
        agent_id: agent.model_copy(
            update={
                "needs": NeedValues(hunger=0.5, energy=0.5, hygiene=0.5, fun=0.0, social=0.0),
                "decision_due_at": 0 if agent_id == "npc_03" else 1000,
            }
        )
        for agent_id, agent in checkpoint.world.agents.items()
    }
    checkpoint = checkpoint.model_copy(update={"world": checkpoint.world.model_copy(update={"agents": agents})})
    before_edges = {(edge.source_agent_id, edge.target_agent_id): edge for edge in checkpoint.world.relationships}
    engine = SocietyEngine(
        catalog,
        m3_catalogs,
        checkpoint,
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.COMPLIMENT}),
    )
    social_event = None
    for minute in range(1, 31):
        result = engine.advance_to(minute)
        social_event = next(
            (
                event
                for event in result.events
                if event.event_type in {EventType.POSITIVE_INTERACTION, EventType.AWKWARD_INTERACTION}
                and event.actor_ids == ["npc_03"]
            ),
            None,
        )
        if social_event is not None:
            break
    assert social_event is not None
    target_id = social_event.affected_agent_ids[0]
    for action_id in list(engine.state.active_actions):
        engine.cancel_action(action_id, reason="TARGETED_SOCIAL_FIXTURE_RESET")
    after_social = engine.export_checkpoint()
    after_edges = {(edge.source_agent_id, edge.target_agent_id): edge for edge in after_social.world.relationships}
    assert after_edges[(target_id, "npc_03")] != before_edges[(target_id, "npc_03")]
    assert after_edges[("npc_03", target_id)] == before_edges[("npc_03", target_id)]
    witness_id = next(agent_id for agent_id in ("npc_03", "npc_04", "npc_05") if agent_id not in {"npc_03", target_id})
    witnessed = after_social.knowledge_records[knowledge_key(witness_id, social_event.event_id)]
    assert witnessed.acquisition_type is KnowledgeAcquisitionType.WITNESSED

    # Put one unknowing listener beside the speaker and move the already-knowing
    # household peers away. This is targeted fixture setup; the share itself is
    # still selected and committed by the production engine.
    moved_agents = dict(after_social.world.agents)
    moved_agents["npc_03"] = moved_agents["npc_03"].model_copy(update={"known_event_ids": [social_event.event_id]})
    knowledge = {
        key: record
        for key, record in after_social.knowledge_records.items()
        if record.agent_id != "npc_03" or record.event_id == social_event.event_id
    }
    moved_locations = dict(after_social.world.locations)
    home_a = moved_locations["home_a"]
    home_b = moved_locations["home_b"]
    moved_locations["home_a"] = home_a.model_copy(update={"current_agent_ids": ["npc_02", "npc_04", "npc_05"]})
    moved_locations["home_b"] = home_b.model_copy(update={"current_agent_ids": ["npc_01", "npc_03"]})
    for agent_id, moved_agent in moved_agents.items():
        location = moved_agent.current_location_id
        if agent_id == "npc_01":
            location = "home_b"
        elif agent_id in {"npc_04", "npc_05"}:
            location = "home_a"
        moved_agents[agent_id] = moved_agent.model_copy(
            update={
                "current_location_id": location,
                "decision_due_at": after_social.world.game_minute if agent_id == "npc_03" else 1000,
            }
        )
    moved_world = after_social.world.model_copy(update={"agents": moved_agents, "locations": moved_locations})
    share_engine = SocietyEngine(
        catalog,
        m3_catalogs,
        after_social.model_copy(update={"world": moved_world, "knowledge_records": knowledge}),
        behavior_allowlist=frozenset({BehaviorId.IDLE, BehaviorId.SHARE_EVENT}),
    )
    shared = False
    for minute in range(moved_world.game_minute + 1, moved_world.game_minute + 31):
        result = share_engine.advance_to(minute)
        if any(event.event_type is EventType.EVENT_SHARED for event in result.events):
            shared = True
            break
    assert shared
    told = share_engine.export_checkpoint().knowledge_records[knowledge_key("npc_01", social_event.event_id)]
    assert told.acquisition_type is KnowledgeAcquisitionType.TOLD
    assert told.source_agent_id == "npc_03"


def test_one_day_ten_npc_smoke_preserves_economy_and_work_settlement(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    result = engine.advance_to(1440)
    final = engine.export_checkpoint()
    decisions = cast(list[dict[str, Any]], result.decisions)
    completed_actions = [item for item in result.actions if item["phase"] == "COMPLETED"]

    assert final.world.game_minute == 1440
    assert sorted({str(item["agent_id"]) for item in decisions}) == [f"npc_{index:02d}" for index in range(1, 11)]
    assert all(session.finalized and session.paid for session in final.work_sessions.values())
    assert len(final.work_sessions) == 10
    assert_society_invariants(final, catalog, m3_catalogs)

    money_delta: Counter[str] = Counter()
    food_delta: Counter[str] = Counter()
    for event in final.events:
        if event.event_type is EventType.WORK_COMPLETED:
            household_id = final.world.agents[event.actor_ids[0]].household_id
            wage = event.payload["wage_minor_units"]
            assert isinstance(wage, int)
            money_delta[household_id] += wage
    for action in completed_actions:
        behavior_id = BehaviorId(str(action["behavior_id"]))
        participant_ids = [str(item) for item in cast(list[object], action["agent_ids"])]
        charged_agents = participant_ids if bool(action["joint"]) else participant_ids[:1]
        if behavior_id is BehaviorId.BUY_GROCERIES:
            household_id = final.world.agents[charged_agents[0]].household_id
            money_delta[household_id] -= catalog.economy.groceries.price
            food_delta[household_id] += catalog.economy.groceries.food_units_delta
        elif behavior_id is BehaviorId.EAT_AT_HOME:
            household_id = final.world.agents[charged_agents[0]].household_id
            food_delta[household_id] -= 1
        elif behavior_id in {BehaviorId.EAT_AT_CAFE, BehaviorId.DRINK_AT_BAR}:
            price = (
                catalog.economy.cafe_meal.price
                if behavior_id is BehaviorId.EAT_AT_CAFE
                else catalog.economy.bar_drink.price
            )
            for agent_id in charged_agents:
                money_delta[final.world.agents[agent_id].household_id] -= price
    for household_id, household in final.world.households.items():
        assert household.money == initial.world.households[household_id].money + money_delta[household_id]
        assert household.food_units == initial.world.households[household_id].food_units + food_delta[household_id]
