"""Executable M1 authority invariants."""

from __future__ import annotations

from collections.abc import Sequence

from town_core.domain.state_models import WorldEvent, WorldState


class InvariantViolation(ValueError):
    """Raised before an invalid authority state can commit."""


def assert_world_invariants(
    state: WorldState,
    *,
    active_agent_id: str,
    events: Sequence[WorldEvent] = (),
) -> None:
    enabled = sorted(agent.agent_id for agent in state.agents.values() if agent.enabled)
    if enabled != [active_agent_id]:
        raise InvariantViolation(f"M1 requires exactly one enabled agent: {enabled}")

    action_owner: dict[str, str] = {}
    for action_id, action in state.active_actions.items():
        if action_id != action.action_id:
            raise InvariantViolation("active action key/id mismatch")
        for agent_id in action.agent_ids:
            if agent_id in action_owner:
                raise InvariantViolation(f"agent owns multiple primary actions: {agent_id}")
            action_owner[agent_id] = action_id
            if not state.agents[agent_id].enabled:
                raise InvariantViolation(f"inactive M1 agent owns action: {agent_id}")

    for agent_id, agent in state.agents.items():
        if agent.current_action_id != action_owner.get(agent_id):
            raise InvariantViolation(f"agent/action exclusivity mismatch: {agent_id}")
        containing_locations = [
            location.location_id for location in state.locations.values() if agent_id in location.current_agent_ids
        ]
        if agent.current_location_id == "TRAVELING":
            if containing_locations:
                raise InvariantViolation(f"traveling agent is still in a location: {agent_id}")
        elif containing_locations != [agent.current_location_id]:
            raise InvariantViolation(f"agent location membership mismatch: {agent_id}")

    occupied_owner: dict[tuple[str, int], str] = {}
    for object_id, obj in state.objects.items():
        if object_id != obj.object_id:
            raise InvariantViolation("object key/id mismatch")
        for slot, action_id in obj.occupied_slots.items():
            if slot >= obj.slot_count:
                raise InvariantViolation(f"occupied slot is out of range: {object_id}/{slot}")
            if action_id not in state.active_actions:
                raise InvariantViolation(f"slot refers to inactive action: {object_id}/{slot}")
            key = (object_id, slot)
            if key in occupied_owner:
                raise InvariantViolation(f"exclusive slot has multiple owners: {object_id}/{slot}")
            occupied_owner[key] = action_id

    agent_ids = set(state.agents)
    expected_pairs = {(source, target) for source in agent_ids for target in agent_ids if source != target}
    actual_pairs = {(item.source_agent_id, item.target_agent_id) for item in state.relationships}
    if actual_pairs != expected_pairs or len(actual_pairs) != len(state.relationships):
        raise InvariantViolation("directed relationship materialization is incomplete or duplicated")

    if state.event_cursor != len(events):
        raise InvariantViolation("event cursor does not match append-only ledger")
    for index, event in enumerate(events, start=1):
        if event.event_id != f"event_{index:08d}":
            raise InvariantViolation("event IDs are not stable and monotonic")
        if index > 1 and event.game_minute < events[index - 2].game_minute:
            raise InvariantViolation("event time order is not monotonic")


def assert_transition(previous: WorldState, committed: WorldState) -> None:
    if committed.state_version != previous.state_version + 1:
        raise InvariantViolation("each authority tick must increment state_version exactly once")
    if committed.game_minute != previous.game_minute + 1:
        raise InvariantViolation("M1 authority ticks must be consecutive one-minute steps")
    if committed.random_seed != previous.random_seed or committed.config_hash != previous.config_hash:
        raise InvariantViolation("authority identity changed during a transaction")
    for agent_id, previous_agent in previous.agents.items():
        if not previous_agent.enabled and committed.agents[agent_id] != previous_agent:
            raise InvariantViolation(f"inactive M1 agent changed: {agent_id}")
    for previous_relation, committed_relation in zip(previous.relationships, committed.relationships, strict=True):
        if previous_relation != committed_relation:
            raise InvariantViolation("M1 must not update relationships")
