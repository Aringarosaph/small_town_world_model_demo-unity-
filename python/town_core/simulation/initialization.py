"""Deterministic construction of a persistable M1 ``WorldState``."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from town_core.domain.config_models import CatalogBundle, RelationshipRangeSet
from town_core.domain.enums import RelationshipRole
from town_core.domain.state_models import (
    AgentState,
    HouseholdState,
    LocationState,
    RelationshipState,
    WorldState,
)
from town_core.simulation.headless_fixture import DEFAULT_M1_HEADLESS_FIXTURE, HeadlessSemanticObjectFixture


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def catalog_hash(catalog: CatalogBundle) -> str:
    """Hash the validated effective catalog rather than filesystem metadata."""

    payload = catalog.model_dump(mode="json", exclude_none=False)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def state_hash(state: WorldState) -> str:
    """Return the canonical authoritative-state SHA-256 digest."""

    payload = state.model_dump(mode="json", exclude_none=False)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _stable_unit(seed: int, source_id: str, target_id: str, axis: str) -> float:
    material = f"stwm-m1|relationship-v1|{seed}|{source_id}|{target_id}|{axis}".encode()
    integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return integer / float((1 << 64) - 1)


def _range_value(
    ranges: RelationshipRangeSet,
    axis: str,
    seed: int,
    source_id: str,
    target_id: str,
) -> float:
    bounds_by_axis = {
        "familiarity": ranges.familiarity,
        "affinity": ranges.affinity,
        "trust": ranges.trust,
        "tension": ranges.tension,
    }
    bounds = bounds_by_axis[axis]
    unit = _stable_unit(seed, source_id, target_id, axis)
    return round(bounds.minimum + ((bounds.maximum - bounds.minimum) * unit), 6)


def _relationship_roles_and_ranges(
    catalog: CatalogBundle,
    source_id: str,
    target_id: str,
) -> tuple[list[RelationshipRole], RelationshipRangeSet]:
    npc_by_id = {npc.agent_id: npc for npc in catalog.population.npcs}
    source = npc_by_id[source_id]
    target = npc_by_id[target_id]
    roles: list[RelationshipRole] = []
    if source.household_id == target.household_id:
        roles.append(RelationshipRole.HOUSEHOLD_MEMBER)
    if source.assigned_work_location_id == target.assigned_work_location_id:
        roles.append(RelationshipRole.COWORKER)
    if not roles:
        roles.append(RelationshipRole.ACQUAINTANCE)

    initialization = catalog.population.relationship_initialization
    if RelationshipRole.HOUSEHOLD_MEMBER in roles:
        ranges = initialization.same_household
    elif RelationshipRole.COWORKER in roles:
        ranges = initialization.coworker
    else:
        ranges = initialization.other
    return roles, ranges


def _build_relationships(catalog: CatalogBundle, seed: int) -> list[RelationshipState]:
    agent_ids = sorted(npc.agent_id for npc in catalog.population.npcs)
    relationships: list[RelationshipState] = []
    for source_id in agent_ids:
        for target_id in agent_ids:
            if source_id == target_id:
                continue
            roles, ranges = _relationship_roles_and_ranges(catalog, source_id, target_id)
            relationships.append(
                RelationshipState(
                    source_agent_id=source_id,
                    target_agent_id=target_id,
                    roles=roles,
                    familiarity=_range_value(ranges, "familiarity", seed, source_id, target_id),
                    affinity=_range_value(ranges, "affinity", seed, source_id, target_id),
                    trust=_range_value(ranges, "trust", seed, source_id, target_id),
                    tension=_range_value(ranges, "tension", seed, source_id, target_id),
                    last_interaction_minute=None,
                )
            )
    return relationships


def build_initial_world_state(
    catalog: CatalogBundle,
    *,
    seed: int | None = None,
    active_agent_id: str = "npc_01",
    object_fixture: HeadlessSemanticObjectFixture = DEFAULT_M1_HEADLESS_FIXTURE,
) -> WorldState:
    """Build the deterministic M1 state without mutating the frozen catalog."""

    runtime_seed = catalog.world.random_seed if seed is None else seed
    if runtime_seed < 0:
        raise ValueError("world seed must be non-negative")
    configured_agent_ids = {npc.agent_id for npc in catalog.population.npcs}
    if active_agent_id not in configured_agent_ids:
        raise ValueError(f"active agent is not configured: {active_agent_id}")
    initial_minute = catalog.world.initial_game_minute
    objects = object_fixture.materialize(catalog)
    object_ids_by_location: defaultdict[str, list[str]] = defaultdict(list)
    for object_id, object_state in objects.items():
        object_ids_by_location[object_state.location_id].append(object_id)

    agents = {
        npc.agent_id: AgentState(
            agent_id=npc.agent_id,
            household_id=npc.household_id,
            display_name_key=npc.display_name_key,
            home_location_id=npc.home_location_id,
            current_location_id=npc.home_location_id,
            assigned_work_location_id=npc.assigned_work_location_id,
            assigned_workstation_tag=npc.assigned_workstation_tag,
            current_action_id=None,
            needs=npc.initial_needs,
            personality=npc.personality,
            mood=npc.initial_mood,
            schedule_id=npc.schedule_id,
            known_event_ids=[],
            social_cooldowns={},
            decision_due_at=initial_minute,
            enabled=npc.agent_id == active_agent_id,
        )
        for npc in catalog.population.npcs
    }
    households = {
        household.household_id: HouseholdState(
            household_id=household.household_id,
            member_ids=list(household.member_ids),
            home_location_id=household.home_location_id,
            money=household.initial_money,
            food_units=household.initial_food_units,
        )
        for household in catalog.households.households
    }
    locations = {
        location.location_id: LocationState(
            location_id=location.location_id,
            location_type=location.location_type,
            current_agent_ids=sorted(
                agent.agent_id for agent in agents.values() if agent.current_location_id == location.location_id
            ),
            object_ids=sorted(object_ids_by_location[location.location_id]),
        )
        for location in catalog.locations.locations
    }
    return WorldState(
        schema_version=catalog.world.schema_version,
        world_id=catalog.world.world_id,
        game_minute=initial_minute,
        random_seed=runtime_seed,
        state_version=0,
        agents=agents,
        households=households,
        locations=locations,
        objects=objects,
        relationships=_build_relationships(catalog, runtime_seed),
        active_actions={},
        dialogue_session_ids=[],
        event_cursor=0,
        model_version=None,
        config_hash=catalog_hash(catalog),
    )
