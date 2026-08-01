"""Stable authority patches used by M1 evidence and non-recomputing replay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from town_core.domain.state_models import (
    ActionState,
    AgentState,
    HouseholdState,
    InteractionObjectState,
    LocationState,
    WorldState,
)
from town_core.simulation.initialization import state_hash


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _changed_models(previous: Mapping[str, Any], committed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.model_dump(mode="json", exclude_none=False)
        for key, value in committed.items()
        if key not in previous or previous[key] != value
    }


def build_state_patch(previous: WorldState, committed: WorldState) -> dict[str, Any]:
    """Build the smallest stable top-level patch needed to reconstruct state."""

    return {
        "game_minute": committed.game_minute,
        "state_version": committed.state_version,
        "event_cursor": committed.event_cursor,
        "agents_upsert": _changed_models(previous.agents, committed.agents),
        "households_upsert": _changed_models(previous.households, committed.households),
        "locations_upsert": _changed_models(previous.locations, committed.locations),
        "objects_upsert": _changed_models(previous.objects, committed.objects),
        "active_actions_upsert": _changed_models(previous.active_actions, committed.active_actions),
        "active_actions_remove": sorted(set(previous.active_actions) - set(committed.active_actions)),
    }


def build_transaction_record(
    previous: WorldState,
    committed: WorldState,
    *,
    committed_event_ids: list[str],
    changes: list[str],
    state_transaction: dict[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "transaction_id": f"transaction_{committed.state_version:08d}",
        "expected_state_version": previous.state_version,
        "committed_state_version": committed.state_version,
        "input_game_minute": committed.game_minute,
        "previous_state_hash": state_hash(previous),
        "state_patch": build_state_patch(previous, committed),
        "committed_event_ids": committed_event_ids,
        "changes": changes,
        "state_transaction": state_transaction,
        "committed_state_hash": state_hash(committed),
    }
    body["transaction_hash"] = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return body


def apply_transaction_record(state: WorldState, record: Mapping[str, Any]) -> WorldState:
    """Apply an ordered committed patch without re-running decision logic."""

    if record["expected_state_version"] != state.state_version:
        raise ValueError("replay transaction expected_state_version mismatch")
    if record["previous_state_hash"] != state_hash(state):
        raise ValueError("replay transaction previous_state_hash mismatch")

    body = {key: value for key, value in record.items() if key != "transaction_hash"}
    digest = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    if digest != record["transaction_hash"]:
        raise ValueError("replay transaction hash mismatch")

    patch = record["state_patch"]
    if not isinstance(patch, Mapping):
        raise TypeError("replay state_patch must be an object")
    agents = dict(state.agents)
    households = dict(state.households)
    locations = dict(state.locations)
    objects = dict(state.objects)
    active_actions = dict(state.active_actions)

    for key, value in _mapping(patch, "agents_upsert").items():
        agents[key] = AgentState.model_validate(value)
    for key, value in _mapping(patch, "households_upsert").items():
        households[key] = HouseholdState.model_validate(value)
    for key, value in _mapping(patch, "locations_upsert").items():
        locations[key] = LocationState.model_validate(value)
    for key, value in _mapping(patch, "objects_upsert").items():
        objects[key] = InteractionObjectState.model_validate(value)
    for key, value in _mapping(patch, "active_actions_upsert").items():
        active_actions[key] = ActionState.model_validate(value)
    removals = patch.get("active_actions_remove", [])
    if not isinstance(removals, list):
        raise TypeError("active_actions_remove must be a list")
    for action_id in removals:
        active_actions.pop(str(action_id), None)

    committed = state.model_copy(
        update={
            "game_minute": patch["game_minute"],
            "state_version": patch["state_version"],
            "event_cursor": patch["event_cursor"],
            "agents": agents,
            "households": households,
            "locations": locations,
            "objects": objects,
            "active_actions": active_actions,
        }
    )
    committed = WorldState.model_validate(committed.model_dump(mode="json", exclude_none=False))
    if state_hash(committed) != record["committed_state_hash"]:
        raise ValueError("replay committed_state_hash mismatch")
    return committed


def _mapping(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")
    return value
