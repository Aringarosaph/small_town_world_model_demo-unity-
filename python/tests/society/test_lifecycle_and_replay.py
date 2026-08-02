from __future__ import annotations

from collections import Counter
from typing import Any, cast

from town_core.domain.config_models import CatalogBundle, NeedValues
from town_core.domain.enums import BehaviorId, EventType, KnowledgeAcquisitionType
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import advance_authority_log_hash, checkpoint_hash, knowledge_key
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.invariants import assert_society_invariants
from town_core.society.transactions import apply_transaction_record


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
