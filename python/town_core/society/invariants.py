"""Executable M3 society authority invariants."""

from __future__ import annotations

from town_core.catalogs import m3_catalog_hash
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import ActionPhase
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.models import AuthorityCheckpoint


class SocietyInvariantViolation(ValueError):
    """Raised before an invalid M3 authority checkpoint can commit."""


def assert_society_invariants(
    checkpoint: AuthorityCheckpoint,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    state = checkpoint.world
    if checkpoint.m3_catalog_hash != m3_catalog_hash(m3_catalogs):
        raise SocietyInvariantViolation("M3 additive catalog identity changed")
    manifest_ids = {item.object_id for item in m3_catalogs.semantic_instances.objects}
    if set(state.objects) != manifest_ids:
        raise SocietyInvariantViolation("world objects do not exactly match the shared M3 semantic manifest")
    configured = sorted(npc.agent_id for npc in catalog.population.npcs if npc.enabled)
    enabled = sorted(agent.agent_id for agent in state.agents.values() if agent.enabled)
    if enabled != configured or len(enabled) != 10:
        raise SocietyInvariantViolation(f"M3 requires the ten configured enabled NPCs: {enabled}")

    action_owner: dict[str, str] = {}
    for action_id, action in state.active_actions.items():
        if action_id != action.action_id:
            raise SocietyInvariantViolation("active action key/id mismatch")
        if action.phase in {ActionPhase.COMPLETED, ActionPhase.CANCELLED, ActionPhase.FAILED, ActionPhase.INTERRUPTED}:
            raise SocietyInvariantViolation(f"terminal action remains active: {action_id}")
        if action_id not in checkpoint.action_runtimes:
            raise SocietyInvariantViolation(f"active action has no checkpoint runtime: {action_id}")
        for agent_id in action.agent_ids:
            if agent_id in action_owner:
                raise SocietyInvariantViolation(f"agent owns multiple primary actions: {agent_id}")
            action_owner[agent_id] = action_id
            if not state.agents[agent_id].enabled:
                raise SocietyInvariantViolation(f"disabled agent owns an action: {agent_id}")

    for agent_id, agent in state.agents.items():
        if agent.current_action_id != action_owner.get(agent_id):
            raise SocietyInvariantViolation(f"agent/action exclusivity mismatch: {agent_id}")
        containing = sorted(
            location.location_id for location in state.locations.values() if agent_id in location.current_agent_ids
        )
        if agent.current_location_id == "TRAVELING":
            if containing:
                raise SocietyInvariantViolation(f"traveling agent remains in a location: {agent_id}")
        elif containing != [agent.current_location_id]:
            raise SocietyInvariantViolation(f"agent location membership mismatch: {agent_id}")

    reservation_ids = set(checkpoint.reservations)
    for action_id, runtime in checkpoint.action_runtimes.items():
        if action_id not in state.active_actions:
            raise SocietyInvariantViolation(f"terminal or missing action owns runtime: {action_id}")
        if set(runtime.reservation_ids) - reservation_ids:
            raise SocietyInvariantViolation(f"action owns missing reservation: {action_id}")
        if sorted(runtime.participant_ids) != sorted(state.active_actions[action_id].agent_ids):
            raise SocietyInvariantViolation(f"runtime participant mismatch: {action_id}")

    participant_owner: dict[str, str] = {}
    location_reservations: dict[str, int] = {}
    for reservation_id, reservation in checkpoint.reservations.items():
        if reservation_id != reservation.reservation_id:
            raise SocietyInvariantViolation("reservation key/id mismatch")
        if reservation.owner_action_id not in state.active_actions:
            raise SocietyInvariantViolation(f"reservation belongs to inactive action: {reservation_id}")
        if reservation.expires_at_game_minute < state.game_minute:
            raise SocietyInvariantViolation(f"expired reservation remains active: {reservation_id}")
        if reservation.kind == "PARTICIPANT":
            agent_id = str(reservation.participant_agent_id)
            if agent_id in participant_owner:
                raise SocietyInvariantViolation(f"participant has two reservations: {agent_id}")
            participant_owner[agent_id] = reservation.owner_action_id
        elif reservation.kind == "LOCATION":
            location_id = str(reservation.location_id)
            location_reservations[location_id] = location_reservations.get(location_id, 0) + 1

    if participant_owner != action_owner:
        raise SocietyInvariantViolation("participant reservations do not match primary action ownership")

    object_claims: dict[tuple[str, int], str] = {}
    for object_id, obj in state.objects.items():
        for slot, action_id in obj.occupied_slots.items():
            if slot >= obj.slot_count:
                raise SocietyInvariantViolation(f"object slot out of range: {object_id}/{slot}")
            if action_id not in state.active_actions:
                raise SocietyInvariantViolation(f"object slot belongs to inactive action: {object_id}/{slot}")
            slot_key = (object_id, slot)
            if slot_key in object_claims:
                raise SocietyInvariantViolation(f"object slot has multiple owners: {object_id}/{slot}")
            object_claims[slot_key] = action_id
    reservation_claims = {
        (str(item.object_id), int(item.slot_index)): item.owner_action_id
        for item in checkpoint.reservations.values()
        if item.kind == "OBJECT_SLOT" and item.object_id is not None and item.slot_index is not None
    }
    if object_claims != reservation_claims:
        raise SocietyInvariantViolation("object occupancy does not match authority reservations")

    location_capacity = {item.location_id: item.capacity for item in catalog.locations.locations}
    for location_id, location in state.locations.items():
        if len(location.current_agent_ids) + location_reservations.get(location_id, 0) > location_capacity[location_id]:
            raise SocietyInvariantViolation(f"location capacity exceeded or over-reserved: {location_id}")

    reserved_money: dict[str, int] = {}
    reserved_food: dict[str, int] = {}
    for reservation in checkpoint.reservations.values():
        if reservation.kind != "HOUSEHOLD_RESOURCE" or reservation.household_id is None:
            continue
        household_id = reservation.household_id
        reserved_money[household_id] = reserved_money.get(household_id, 0) + reservation.money_units
        reserved_food[household_id] = reserved_food.get(household_id, 0) + reservation.food_units
    for household_id, household in state.households.items():
        if reserved_money.get(household_id, 0) > household.money:
            raise SocietyInvariantViolation(f"reserved money exceeds balance: {household_id}")
        if reserved_food.get(household_id, 0) > household.food_units:
            raise SocietyInvariantViolation(f"reserved food exceeds inventory: {household_id}")

    agent_ids = set(state.agents)
    expected_pairs = {(source, target) for source in agent_ids for target in agent_ids if source != target}
    actual_pairs = {(item.source_agent_id, item.target_agent_id) for item in state.relationships}
    if actual_pairs != expected_pairs or len(actual_pairs) != len(state.relationships):
        raise SocietyInvariantViolation("directed relationship materialization is incomplete or duplicated")

    if state.event_cursor != len(checkpoint.events):
        raise SocietyInvariantViolation("event cursor does not match append-only ledger")
    for index, event in enumerate(checkpoint.events, start=1):
        if event.event_id != f"event_{index:08d}":
            raise SocietyInvariantViolation("event IDs are not stable and monotonic")
        if index > 1 and event.game_minute < checkpoint.events[index - 2].game_minute:
            raise SocietyInvariantViolation("event game-minute order is not monotonic")

    expected_known: dict[str, list[str]] = {agent_id: [] for agent_id in state.agents}
    for ledger_key, knowledge_record in checkpoint.knowledge_records.items():
        if ledger_key != f"{knowledge_record.agent_id}|{knowledge_record.event_id}":
            raise SocietyInvariantViolation("knowledge record key mismatch")
        expected_known[knowledge_record.agent_id].append(knowledge_record.event_id)
    for agent_id, agent in state.agents.items():
        if sorted(agent.known_event_ids) != sorted(expected_known[agent_id]):
            raise SocietyInvariantViolation(f"public knowledge permission mismatch: {agent_id}")

    active_conversations = sorted(
        conversation_id for conversation_id, record in checkpoint.conversations.items() if record.active
    )
    if sorted(state.dialogue_session_ids) != active_conversations:
        raise SocietyInvariantViolation("public dialogue session IDs do not match ConversationLedger")

    for action_id, joint_record in checkpoint.joint_actions.items():
        if action_id not in state.active_actions or not checkpoint.action_runtimes[action_id].joint:
            raise SocietyInvariantViolation(f"JointAction has no shared active action: {action_id}")
        if sorted(item.agent_id for item in joint_record.joint_action.participants) != sorted(
            state.active_actions[action_id].agent_ids
        ):
            raise SocietyInvariantViolation(f"JointAction participant mismatch: {action_id}")

    if len(checkpoint.settlement_keys) != len(set(checkpoint.settlement_keys)):
        raise SocietyInvariantViolation("settlement key committed more than once")


def assert_society_transition(previous: AuthorityCheckpoint, committed: AuthorityCheckpoint) -> None:
    if committed.world.state_version != previous.world.state_version + 1:
        raise SocietyInvariantViolation("M3 authority tick must increment state_version exactly once")
    if committed.world.game_minute != previous.world.game_minute + 1:
        raise SocietyInvariantViolation("M3 authority ticks must advance exactly one game minute")
    if committed.world.random_seed != previous.world.random_seed:
        raise SocietyInvariantViolation("world seed changed during society transaction")
    if committed.world.config_hash != previous.world.config_hash:
        raise SocietyInvariantViolation("catalog identity changed during society transaction")
    if committed.m3_catalog_hash != previous.m3_catalog_hash:
        raise SocietyInvariantViolation("additive M3 catalog identity changed during society transaction")
    if committed.events[: len(previous.events)] != previous.events:
        raise SocietyInvariantViolation("event ledger history was mutated")
