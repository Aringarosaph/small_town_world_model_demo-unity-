"""M3 checkpoint patches and tamper-evident transaction chain."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from town_core.domain.state_models import (
    ActionState,
    AgentState,
    HouseholdState,
    InteractionObjectState,
    KnowledgeRecord,
    LocationState,
    RelationshipState,
    WorldEvent,
    WorldState,
)
from town_core.society.checkpoint import canonical_json_sha256
from town_core.society.models import (
    M3_TRANSACTION_SCHEMA,
    ActionRuntimeRecord,
    AuthorityCheckpoint,
    ConversationRecord,
    JointActionRecord,
    ReservationRecord,
    SocietyCounters,
    WorkSessionRecord,
)


def relationship_key(source_agent_id: str, target_agent_id: str) -> str:
    return f"{source_agent_id}|{target_agent_id}"


def changed_models(previous: Mapping[str, Any], committed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.model_dump(mode="json", exclude_none=False)
        for key, value in committed.items()
        if key not in previous or previous[key] != value
    }


def build_society_patch(
    *,
    previous: AuthorityCheckpoint,
    committed: AuthorityCheckpoint,
) -> dict[str, Any]:
    previous_relationships = {
        relationship_key(item.source_agent_id, item.target_agent_id): item for item in previous.world.relationships
    }
    committed_relationships = {
        relationship_key(item.source_agent_id, item.target_agent_id): item for item in committed.world.relationships
    }
    return {
        "game_minute": committed.world.game_minute,
        "state_version": committed.world.state_version,
        "event_cursor": committed.world.event_cursor,
        "agents_upsert": changed_models(previous.world.agents, committed.world.agents),
        "households_upsert": changed_models(previous.world.households, committed.world.households),
        "locations_upsert": changed_models(previous.world.locations, committed.world.locations),
        "objects_upsert": changed_models(previous.world.objects, committed.world.objects),
        "relationships_upsert": changed_models(previous_relationships, committed_relationships),
        "active_actions_upsert": changed_models(previous.world.active_actions, committed.world.active_actions),
        "active_actions_remove": sorted(set(previous.world.active_actions) - set(committed.world.active_actions)),
        "dialogue_session_ids": list(committed.world.dialogue_session_ids),
        "events_append": [
            item.model_dump(mode="json", exclude_none=False) for item in committed.events[len(previous.events) :]
        ],
        "knowledge_upsert": changed_models(previous.knowledge_records, committed.knowledge_records),
        "work_sessions_upsert": changed_models(previous.work_sessions, committed.work_sessions),
        "reservations_upsert": changed_models(previous.reservations, committed.reservations),
        "reservations_remove": sorted(set(previous.reservations) - set(committed.reservations)),
        "conversations_upsert": changed_models(previous.conversations, committed.conversations),
        "joint_actions_upsert": changed_models(previous.joint_actions, committed.joint_actions),
        "joint_actions_remove": sorted(set(previous.joint_actions) - set(committed.joint_actions)),
        "action_runtimes_upsert": changed_models(previous.action_runtimes, committed.action_runtimes),
        "action_runtimes_remove": sorted(set(previous.action_runtimes) - set(committed.action_runtimes)),
        "recent_behaviors": {
            key: value.value if value is not None else None
            for key, value in committed.recent_behaviors.items()
            if previous.recent_behaviors.get(key) != value
        },
        "active_need_crises": {
            key: [item.value for item in value]
            for key, value in committed.active_need_crises.items()
            if previous.active_need_crises.get(key) != value
        },
        "low_resource_flags": {
            key: list(value)
            for key, value in committed.low_resource_flags.items()
            if previous.low_resource_flags.get(key) != value
        },
        "settlement_keys_append": committed.settlement_keys[len(previous.settlement_keys) :],
        "counters": committed.counters.model_dump(mode="json", exclude_none=False),
    }


def build_transaction_record(
    *,
    previous: AuthorityCheckpoint,
    committed_without_chain: AuthorityCheckpoint,
    changes: Sequence[str],
) -> tuple[dict[str, Any], AuthorityCheckpoint]:
    patch = build_society_patch(previous=previous, committed=committed_without_chain)
    sequence = committed_without_chain.counters.transaction
    authority_body = {
        "schema": M3_TRANSACTION_SCHEMA,
        "transaction_id": f"m3_transaction_{sequence:08d}",
        "expected_state_version": previous.world.state_version,
        "committed_state_version": committed_without_chain.world.state_version,
        "input_game_minute": committed_without_chain.world.game_minute,
        "patch": patch,
        "changes": list(changes),
    }
    next_chain = canonical_json_sha256(
        authority_body,
        prefix=previous.transaction_chain_hash.encode("utf-8"),
    )
    committed = committed_without_chain.model_copy(update={"transaction_chain_hash": next_chain})
    record = {
        **authority_body,
        "previous_transaction_chain_hash": previous.transaction_chain_hash,
        "committed_transaction_chain_hash": next_chain,
    }
    record["record_hash"] = canonical_json_sha256(record)
    return record, committed


def apply_transaction_record(checkpoint: AuthorityCheckpoint, record: Mapping[str, Any]) -> AuthorityCheckpoint:
    if record.get("schema") != M3_TRANSACTION_SCHEMA:
        raise ValueError("unsupported M3 transaction schema")
    if record["expected_state_version"] != checkpoint.world.state_version:
        raise ValueError("M3 replay expected_state_version mismatch")
    if record["previous_transaction_chain_hash"] != checkpoint.transaction_chain_hash:
        raise ValueError("M3 replay transaction-chain predecessor mismatch")
    unhashed = {key: value for key, value in record.items() if key != "record_hash"}
    digest = canonical_json_sha256(unhashed)
    if digest != record["record_hash"]:
        raise ValueError("M3 replay transaction record hash mismatch")
    authority_body = {
        key: record[key]
        for key in (
            "schema",
            "transaction_id",
            "expected_state_version",
            "committed_state_version",
            "input_game_minute",
            "patch",
            "changes",
        )
    }
    chain = canonical_json_sha256(
        authority_body,
        prefix=checkpoint.transaction_chain_hash.encode("utf-8"),
    )
    if chain != record["committed_transaction_chain_hash"]:
        raise ValueError("M3 replay committed transaction-chain hash mismatch")

    patch = record["patch"]
    if not isinstance(patch, Mapping):
        raise TypeError("M3 transaction patch must be an object")
    agents = _apply_models(checkpoint.world.agents, patch, "agents_upsert", AgentState)
    households = _apply_models(checkpoint.world.households, patch, "households_upsert", HouseholdState)
    locations = _apply_models(checkpoint.world.locations, patch, "locations_upsert", LocationState)
    objects = _apply_models(checkpoint.world.objects, patch, "objects_upsert", InteractionObjectState)
    active_actions = _apply_models(checkpoint.world.active_actions, patch, "active_actions_upsert", ActionState)
    for action_id in _sequence(patch, "active_actions_remove"):
        active_actions.pop(str(action_id), None)

    relationships = {
        relationship_key(item.source_agent_id, item.target_agent_id): item for item in checkpoint.world.relationships
    }
    for key, value in _mapping(patch, "relationships_upsert").items():
        relationships[key] = RelationshipState.model_validate(value)
    relationship_list = [relationships[key] for key in sorted(relationships)]

    events = [*checkpoint.events]
    events.extend(WorldEvent.model_validate(item) for item in _sequence(patch, "events_append"))
    world = checkpoint.world.model_copy(
        update={
            "game_minute": patch["game_minute"],
            "state_version": patch["state_version"],
            "event_cursor": patch["event_cursor"],
            "agents": agents,
            "households": households,
            "locations": locations,
            "objects": objects,
            "relationships": relationship_list,
            "active_actions": active_actions,
            "dialogue_session_ids": list(_sequence(patch, "dialogue_session_ids")),
        }
    )
    world = WorldState.model_validate(world.model_dump(mode="json", exclude_none=False))

    knowledge = _apply_models(checkpoint.knowledge_records, patch, "knowledge_upsert", KnowledgeRecord)
    work_sessions = _apply_models(checkpoint.work_sessions, patch, "work_sessions_upsert", WorkSessionRecord)
    reservations = _apply_models(checkpoint.reservations, patch, "reservations_upsert", ReservationRecord)
    for reservation_id in _sequence(patch, "reservations_remove"):
        reservations.pop(str(reservation_id), None)
    conversations = _apply_models(checkpoint.conversations, patch, "conversations_upsert", ConversationRecord)
    joint_actions = _apply_models(checkpoint.joint_actions, patch, "joint_actions_upsert", JointActionRecord)
    for action_id in _sequence(patch, "joint_actions_remove"):
        joint_actions.pop(str(action_id), None)
    runtimes = _apply_models(checkpoint.action_runtimes, patch, "action_runtimes_upsert", ActionRuntimeRecord)
    for action_id in _sequence(patch, "action_runtimes_remove"):
        runtimes.pop(str(action_id), None)

    recent = dict(checkpoint.recent_behaviors)
    for key, value in _mapping(patch, "recent_behaviors").items():
        recent[key] = None if value is None else value
    crises = dict(checkpoint.active_need_crises)
    for key, value in _mapping(patch, "active_need_crises").items():
        if not isinstance(value, list):
            raise TypeError("active_need_crises values must be lists")
        crises[key] = value
    low_flags = dict(checkpoint.low_resource_flags)
    for key, value in _mapping(patch, "low_resource_flags").items():
        if not isinstance(value, list):
            raise TypeError("low_resource_flags values must be lists")
        low_flags[key] = value
    settlements = [*checkpoint.settlement_keys, *(str(item) for item in _sequence(patch, "settlement_keys_append"))]

    committed = AuthorityCheckpoint(
        m3_catalog_hash=checkpoint.m3_catalog_hash,
        world=world,
        events=events,
        knowledge_records=knowledge,
        work_sessions=work_sessions,
        reservations=reservations,
        conversations=conversations,
        joint_actions=joint_actions,
        action_runtimes=runtimes,
        recent_behaviors=recent,
        active_need_crises=crises,
        low_resource_flags=low_flags,
        settlement_keys=settlements,
        counters=SocietyCounters.model_validate(patch["counters"]),
        authority_record_count=checkpoint.authority_record_count,
        authority_log_hash=checkpoint.authority_log_hash,
        transaction_chain_hash=chain,
    )
    return committed


def _mapping(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")
    return value


def _sequence(container: Mapping[str, Any], key: str) -> list[Any]:
    value = container.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


def _apply_models(
    previous: Mapping[str, Any],
    patch: Mapping[str, Any],
    key: str,
    model: type[Any],
) -> dict[str, Any]:
    result = dict(previous)
    for item_key, value in _mapping(patch, key).items():
        result[item_key] = model.model_validate(value)
    return result
