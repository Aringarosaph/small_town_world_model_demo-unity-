from __future__ import annotations

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import ActionPhase, MovementCancellationReason, MovementFailureReason
from town_core.domain.state_models import ActionState
from town_core.simulation.clock import RuntimeMode
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state, state_hash


def _engine_at_travel(catalog: CatalogBundle, *, timeout: int = 15) -> tuple[SimulationEngine, ActionState]:
    state = build_initial_world_state(catalog, seed=12345, active_agent_id="npc_01")
    engine = SimulationEngine(
        catalog,
        state,
        active_agent_id="npc_01",
        runtime_mode=RuntimeMode.UNITY_LIVE,
        movement_timeout_minutes=timeout,
    )
    for minute in range(1, 500):
        engine.advance_to(minute)
        agent = engine.state.agents["npc_01"]
        if agent.current_action_id is not None:
            action = engine.state.active_actions[agent.current_action_id]
            if action.phase is ActionPhase.TRAVELING:
                return engine, action
    raise AssertionError("accepted M1 policy did not produce the M2 work travel")


def _reserved_slot(engine: SimulationEngine, action_id: str) -> tuple[str, int]:
    for object_id, obj in engine.state.objects.items():
        for slot_index, owner in obj.occupied_slots.items():
            if owner == action_id:
                return object_id, slot_index
    raise AssertionError("traveling action has no reservation")


def test_arrival_drives_authority_phase_without_advancing_game_time(catalog: CatalogBundle) -> None:
    engine, action = _engine_at_travel(catalog)
    minute = engine.state.game_minute
    version = engine.state.state_version
    object_id, slot_index = _reserved_slot(engine, action.action_id)
    before_rejection = state_hash(engine.state)

    try:
        engine.report_movement_arrived(
            action_id=action.action_id,
            agent_id="npc_01",
            expected_state_version=version,
            object_id=None,
            slot_index=None,
        )
    except ValueError as exc:
        assert "interaction slot" in str(exc)
    else:
        raise AssertionError("slot-less movement arrival was accepted")
    assert state_hash(engine.state) == before_rejection

    result = engine.report_movement_arrived(
        action_id=action.action_id,
        agent_id="npc_01",
        expected_state_version=version,
        object_id=object_id,
        slot_index=slot_index,
    )

    committed = engine.state.active_actions[action.action_id]
    assert engine.state.game_minute == minute
    assert engine.state.state_version == version + 1
    assert engine.state.agents["npc_01"].current_location_id == "cafe_bar"
    assert committed.phase in {ActionPhase.ALIGNING, ActionPhase.PERFORMING}
    assert result.transactions[0]["input_game_minute"] == minute
    assert any(record["phase"] in {"ALIGNING", "PERFORMING"} for record in result.actions)


def test_movement_failure_releases_reservations_and_cannot_change_resources(catalog: CatalogBundle) -> None:
    engine, action = _engine_at_travel(catalog)
    before_minute = engine.state.game_minute
    before_version = engine.state.state_version
    before_resources = engine.state.households["household_a"]

    result = engine.report_movement_failed(
        action_id=action.action_id,
        agent_id="npc_01",
        expected_state_version=before_version,
        reason=MovementFailureReason.NO_PATH,
    )

    assert engine.state.game_minute == before_minute
    assert engine.state.state_version == before_version + 1
    assert engine.state.households["household_a"] == before_resources
    assert engine.state.agents["npc_01"].current_location_id == "home_a"
    assert engine.state.agents["npc_01"].current_action_id is None
    assert action.action_id not in engine.state.active_actions
    assert all(action.action_id not in obj.occupied_slots.values() for obj in engine.state.objects.values())
    assert result.actions[-1]["phase"] == "FAILED"
    assert result.actions[-1]["failure_reason"] == "NO_PATH"


def test_rejected_stale_report_does_not_mutate_authority(catalog: CatalogBundle) -> None:
    engine, action = _engine_at_travel(catalog)
    before = state_hash(engine.state)

    try:
        engine.report_movement_failed(
            action_id=action.action_id,
            agent_id="npc_01",
            expected_state_version=engine.state.state_version - 1,
            reason=MovementFailureReason.SLOT_BLOCKED,
        )
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale report was accepted")

    assert state_hash(engine.state) == before


def test_python_timeout_is_deterministic_and_does_not_wait_for_animation(catalog: CatalogBundle) -> None:
    engine, action = _engine_at_travel(catalog, timeout=2)
    terminal_records: list[dict[str, object]] = []
    for _ in range(20):
        result = engine.advance_to(engine.state.game_minute + 1)
        terminal_records.extend(
            record
            for record in result.actions
            if record["action_id"] == action.action_id and record["phase"] == "FAILED"
        )
        if terminal_records:
            break

    assert len(terminal_records) == 1
    assert terminal_records[0]["failure_reason"] == "TIMEOUT"


def test_stale_but_exact_cancellation_commits_once_without_resource_settlement(catalog: CatalogBundle) -> None:
    engine, action = _engine_at_travel(catalog)
    reported_version = engine.state.state_version
    engine.advance_to(engine.state.game_minute + 1)
    before_minute = engine.state.game_minute
    before_version = engine.state.state_version
    before_household = engine.state.households["household_a"]

    result = engine.report_movement_cancelled(
        action_id=action.action_id,
        agent_id="npc_01",
        expected_state_version=reported_version,
        reason=MovementCancellationReason.NAVIGATION_STOPPED,
    )

    assert engine.state.game_minute == before_minute
    assert engine.state.state_version == before_version + 1
    assert engine.state.households["household_a"] == before_household
    assert engine.state.agents["npc_01"].current_location_id == "home_a"
    assert engine.state.agents["npc_01"].current_action_id is None
    assert all(action.action_id not in obj.occupied_slots.values() for obj in engine.state.objects.values())
    assert result.actions[-1]["phase"] == "CANCELLED"
    assert result.actions[-1]["failure_reason"] == "NAVIGATION_STOPPED"
