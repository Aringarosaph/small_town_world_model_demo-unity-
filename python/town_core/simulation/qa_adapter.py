"""Production-runtime evidence adapter consumed by the M1 QA gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from town_core.catalogs import load_catalog
from town_core.decision.candidates import CandidateEnumerator
from town_core.decision.resolver import CentralResolver
from town_core.domain.config_models import CatalogBundle, NeedValues
from town_core.domain.decision_models import ActionProposal
from town_core.domain.enums import ActionPhase, BehaviorId, EventType, ProposalResult
from town_core.domain.state_models import ActionState, HouseholdState, WorldEvent, WorldState
from town_core.events import EventLedger
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state, state_hash
from town_core.simulation.invariants import InvariantViolation, assert_transition, assert_world_invariants
from town_core.simulation.run import authority_log_hash
from town_core.simulation.transactions import apply_transaction_record

EVIDENCE_SCHEMA = "stwm.qa.m1-evidence/v1"
PROJECT_NAME = "Small Town World Model（STWM）"
NEED_NAMES = ("hunger", "energy", "hygiene", "fun", "social")
BEHAVIOR_IDS = ("idle", "sleep", "eat_at_home", "work_shift")
RUN_MATRIX = (("baseline", 1), ("repeat", 1), ("chunk_7", 7), ("chunk_60", 60))
INVARIANT_KEYS = (
    "needs_in_range",
    "mood_in_range",
    "resources_nonnegative",
    "single_primary_action",
    "exclusive_slots",
    "action_lifecycle_valid",
    "state_versions_monotonic",
    "record_ids_monotonic",
    "event_ledger_append_only",
    "complete_decision_trace",
    "wages_exactly_once",
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected JSONL object: {path}:{line_number}")
        records.append(value)
    return records


def _authority_projection(run_path: Path, filename: str, key: str) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for envelope in _read_jsonl(run_path / filename):
        context = envelope.get("context")
        if not isinstance(context, dict) or not isinstance(context.get(key), dict):
            raise TypeError(f"{filename} is missing context.{key}")
        projected.append(context[key])
    return projected


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _relative_directory(path: Path, evidence_root: Path) -> str:
    try:
        return path.resolve().relative_to(evidence_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("M1 run evidence must remain below the evidence directory") from exc


def _invoke_cli(arguments: Sequence[str]) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, "-m", "town_core.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout.strip()
    try:
        document = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"CLI returned non-JSON output (exit={completed.returncode}): {output or completed.stderr.strip()}"
        ) from exc
    if not isinstance(document, dict):
        raise TypeError("CLI summary must be a JSON object")
    return completed.returncode, document


def _run_headless_cli(
    config_path: Path,
    output_root: Path,
    *,
    agent_id: str,
    days: int,
    seed: int,
    chunk_minutes: int,
) -> tuple[int, dict[str, Any]]:
    return _invoke_cli(
        (
            "run-headless",
            "--config",
            str(config_path),
            "--output-root",
            str(output_root),
            "--agent",
            agent_id,
            "--days",
            str(days),
            "--seed",
            str(seed),
            "--chunk-minutes",
            str(chunk_minutes),
        )
    )


def _iter_state_transactions(transaction: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    state_transaction = transaction.get("state_transaction")
    if not isinstance(state_transaction, dict):
        return
    batch = state_transaction.get("batch")
    if batch is None:
        yield state_transaction
        return
    if not isinstance(batch, list):
        raise TypeError("state_transaction.batch must be an array")
    for item in batch:
        if not isinstance(item, dict):
            raise TypeError("state_transaction batch item must be an object")
        yield item


def _wage_analysis(
    catalog: CatalogBundle,
    summary: Mapping[str, Any],
    transactions: Sequence[Mapping[str, Any]],
    initial: WorldState,
    final: WorldState,
    agent_id: str,
) -> dict[str, Any]:
    wage = catalog.economy.fixed_shift_wage
    household_id = initial.agents[agent_id].household_id
    settlements: Counter[str] = Counter()
    amounts: Counter[str] = Counter()
    completed_events: Counter[str] = Counter()
    for transaction in transactions:
        for state_transaction in _iter_state_transactions(transaction):
            resolved_actions = state_transaction.get("resolved_actions")
            if not isinstance(resolved_actions, list):
                raise TypeError("resolved_actions must be an array")
            for resolved in resolved_actions:
                if not isinstance(resolved, dict):
                    raise TypeError("resolved action must be an object")
                emitted_events = resolved.get("emitted_events", [])
                hard_effects = resolved.get("hard_effects", [])
                session_ids: list[str] = []
                for event in emitted_events:
                    if not isinstance(event, dict) or event.get("event_type") != EventType.WORK_COMPLETED.value:
                        continue
                    payload = event.get("payload")
                    if not isinstance(payload, dict):
                        raise TypeError("WORK_COMPLETED payload must be an object")
                    session_id = str(payload["session_id"])
                    completed_events[session_id] += 1
                    session_ids.append(session_id)
                money_effects = [
                    effect
                    for effect in hard_effects
                    if isinstance(effect, dict) and effect.get("field_path") == f"households.{household_id}.money"
                ]
                for session_id in session_ids:
                    for effect in money_effects:
                        delta = effect.get("delta_integer")
                        if isinstance(delta, int) and not isinstance(delta, bool):
                            settlements[session_id] += 1
                            amounts[session_id] += delta

    raw_sessions = summary.get("work_sessions")
    if not isinstance(raw_sessions, list):
        raise TypeError("run summary work_sessions must be an array")
    paid_ids = {
        str(session["session_id"])
        for session in raw_sessions
        if isinstance(session, dict) and session.get("paid") is True
    }
    unpaid_ids = {
        str(session["session_id"])
        for session in raw_sessions
        if isinstance(session, dict) and session.get("paid") is False and session.get("finalized") is True
    }
    money_delta = final.households[household_id].money - initial.households[household_id].money
    passed = (
        all(completed_events[session_id] == 1 for session_id in paid_ids)
        and all(settlements[session_id] == 1 and amounts[session_id] == wage for session_id in paid_ids)
        and all(completed_events[session_id] == 0 and settlements[session_id] == 0 for session_id in unpaid_ids)
        and set(settlements) == paid_ids
        and money_delta == len(paid_ids) * wage
    )
    return {
        "passed": passed,
        "paid_session_ids": sorted(paid_ids),
        "wage_settlement_count": sum(settlements.values()),
        "wage_amount": sum(amounts.values()),
        "money_delta": money_delta,
    }


def _action_lifecycle_valid(
    actions: Sequence[Mapping[str, Any]],
    final_active_action_ids: set[str],
) -> bool:
    phases: defaultdict[str, list[str]] = defaultdict(list)
    for record in actions:
        phases[str(record.get("action_id"))].append(str(record.get("phase")))
    allowed = {
        ActionPhase.CREATED.value: {ActionPhase.RESERVING.value},
        ActionPhase.RESERVING.value: {
            ActionPhase.TRAVELING.value,
            ActionPhase.ALIGNING.value,
            ActionPhase.PERFORMING.value,
        },
        ActionPhase.TRAVELING.value: {ActionPhase.ALIGNING.value, ActionPhase.PERFORMING.value},
        ActionPhase.ALIGNING.value: {ActionPhase.PERFORMING.value},
        ActionPhase.PERFORMING.value: {ActionPhase.RESOLVING.value},
        ActionPhase.RESOLVING.value: {ActionPhase.COMPLETED.value, ActionPhase.FAILED.value},
        ActionPhase.COMPLETED.value: set(),
        ActionPhase.FAILED.value: set(),
    }
    for action_id, sequence in phases.items():
        if not sequence or sequence[0] != ActionPhase.CREATED.value:
            return False
        if any(after not in allowed.get(before, set()) for before, after in pairwise(sequence)):
            return False
        if sequence[-1] not in {ActionPhase.COMPLETED.value, ActionPhase.FAILED.value}:
            if action_id not in final_active_action_ids:
                return False
        elif action_id in final_active_action_ids:
            return False
    return bool(phases)


def _record_ids_monotonic(
    transactions: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    events: Sequence[WorldEvent],
) -> bool:
    transaction_ok = all(
        item.get("transaction_id") == f"transaction_{index:08d}" for index, item in enumerate(transactions, start=1)
    )
    decision_ok = all(
        item.get("decision_id") == f"decision_{index:08d}" for index, item in enumerate(decisions, start=1)
    )
    first_seen_actions = list(dict.fromkeys(str(item.get("action_id")) for item in actions))
    action_ok = first_seen_actions == [f"action_{index:08d}" for index in range(1, len(first_seen_actions) + 1)]
    event_ok = all(event.event_id == f"event_{index:08d}" for index, event in enumerate(events, start=1))
    return transaction_ok and decision_ok and action_ok and event_ok


def _observe_run(
    catalog: CatalogBundle,
    summary: Mapping[str, Any],
    *,
    label: str,
    evidence_root: Path,
    agent_id: str,
) -> dict[str, Any]:
    run_path = Path(str(summary["run_path"])).resolve()
    initial = WorldState.model_validate(_read_json(run_path / "initial_snapshot.json"))
    recorded_final = WorldState.model_validate(_read_json(run_path / "final_snapshot.json"))
    transactions = _authority_projection(run_path, "transactions.jsonl", "authority_transaction")
    decisions = _authority_projection(run_path, "decisions.jsonl", "decision")
    actions = _authority_projection(run_path, "actions.jsonl", "action")
    event_dicts = _authority_projection(run_path, "events.jsonl", "world_event")
    events = [WorldEvent.model_validate(item) for item in event_dicts]
    event_by_id = {event.event_id: event for event in events}
    ledger = EventLedger(catalog)
    state = initial
    need_extrema = {
        need: {
            "min": float(getattr(initial.agents[agent_id].needs, need)),
            "max": float(getattr(initial.agents[agent_id].needs, need)),
        }
        for need in NEED_NAMES
    }
    first_tick_needs: dict[str, float] | None = None
    needs_in_range = True
    mood_in_range = True
    resources_nonnegative = True
    state_versions_monotonic = True
    authoritative_state_invariants = True
    inactive_activity_count = 0
    inactive_ids = set(initial.agents) - {agent_id}
    minutes: list[int] = []

    for transaction in transactions:
        minutes.append(int(transaction["input_game_minute"]))
        patch = transaction.get("state_patch")
        if isinstance(patch, dict):
            agents_upsert = patch.get("agents_upsert")
            if isinstance(agents_upsert, dict):
                inactive_activity_count += len(set(agents_upsert) & inactive_ids)
        previous = state
        state = apply_transaction_record(state, transaction)
        try:
            assert_transition(previous, state)
        except InvariantViolation:
            state_versions_monotonic = False
            authoritative_state_invariants = False
        committed_ids = transaction.get("committed_event_ids")
        if not isinstance(committed_ids, list):
            raise TypeError("committed_event_ids must be an array")
        committed_events = [event_by_id[str(event_id)] for event_id in committed_ids]
        try:
            ledger.commit(committed_events)
            assert_world_invariants(state, active_agent_id=agent_id, events=ledger.events)
        except (InvariantViolation, ValueError):
            authoritative_state_invariants = False
        needs = state.agents[agent_id].needs
        if first_tick_needs is None:
            first_tick_needs = {need: float(getattr(needs, need)) for need in NEED_NAMES}
        for need in NEED_NAMES:
            value = float(getattr(needs, need))
            need_extrema[need]["min"] = min(need_extrema[need]["min"], value)
            need_extrema[need]["max"] = max(need_extrema[need]["max"], value)
            needs_in_range = needs_in_range and 0.0 <= value <= 1.0
        mood = state.agents[agent_id].mood
        mood_in_range = mood_in_range and -1.0 <= mood.valence <= 1.0 and 0.0 <= mood.stress <= 1.0
        resources_nonnegative = resources_nonnegative and all(
            household.money >= 0 and household.food_units >= 0 for household in state.households.values()
        )

    if first_tick_needs is None:
        raise ValueError("headless run contains no committed transaction")
    if state != recorded_final:
        raise ValueError("observed transaction replay differs from final_snapshot.json")
    if tuple(ledger.events) != tuple(events):
        raise ValueError("event ledger reconstruction differs from events.jsonl")

    inactive_activity_count += sum(1 for decision in decisions if str(decision.get("agent_id")) in inactive_ids)
    inactive_activity_count += sum(
        1
        for action in actions
        if any(str(item) in inactive_ids for item in action.get("agent_ids", []) if isinstance(item, str))
    )
    inactive_activity_count += sum(
        1
        for event in events
        if any(item in inactive_ids for item in (*event.actor_ids, *event.affected_agent_ids, *event.witness_agent_ids))
    )

    expected_minutes = list(range(initial.game_minute + 1, recorded_final.game_minute + 1))
    minute_counts = Counter(minutes)
    skipped_tick_count = sum(1 for minute in expected_minutes if minute_counts[minute] == 0)
    duplicated_tick_count = sum(count - 1 for count in minute_counts.values() if count > 1)
    lifecycle_ok = _action_lifecycle_valid(actions, set(recorded_final.active_actions))
    selected_actions = {str(decision.get("selected_action_id")) for decision in decisions}
    action_behaviors = {
        str(action.get("action_id")): str(action.get("behavior_id"))
        for action in actions
        if action.get("phase") == ActionPhase.CREATED.value
    }
    complete_trace = len(selected_actions) == len(decisions) and all(
        action_behaviors.get(str(decision.get("selected_action_id"))) == decision.get("selected_behavior_id")
        and isinstance(decision.get("candidates"), list)
        and bool(decision["candidates"])
        and isinstance(decision.get("resolver_attempts"), list)
        and bool(decision["resolver_attempts"])
        for decision in decisions
    )
    record_ids_ok = _record_ids_monotonic(transactions, decisions, actions, events)
    wage = _wage_analysis(catalog, summary, transactions, initial, recorded_final, agent_id)
    raw_counts = summary.get("selected_behavior_counts")
    if not isinstance(raw_counts, dict):
        raise TypeError("selected_behavior_counts must be an object")
    behavior_counts = {behavior_id: int(raw_counts.get(behavior_id, 0)) for behavior_id in BEHAVIOR_IDS}
    records = {
        "decisions": decisions,
        "actions": actions,
        "transactions": transactions,
        "events": event_dicts,
    }
    actual_initial_hash = state_hash(initial)
    actual_final_hash = state_hash(recorded_final)
    actual_log_hash = authority_log_hash(records)
    if actual_initial_hash != summary.get("initial_state_hash"):
        raise ValueError("summary initial_state_hash differs from initial snapshot")
    if actual_final_hash != summary.get("final_state_hash"):
        raise ValueError("summary final_state_hash differs from final snapshot")
    if actual_log_hash != summary.get("authority_log_hash"):
        raise ValueError("summary authority_log_hash differs from all four authority logs")

    invariants = {
        "needs_in_range": needs_in_range,
        "mood_in_range": mood_in_range,
        "resources_nonnegative": resources_nonnegative,
        "single_primary_action": authoritative_state_invariants,
        "exclusive_slots": authoritative_state_invariants,
        "action_lifecycle_valid": lifecycle_ok,
        "state_versions_monotonic": state_versions_monotonic,
        "record_ids_monotonic": record_ids_ok,
        "event_ledger_append_only": authoritative_state_invariants and tuple(ledger.events) == tuple(events),
        "complete_decision_trace": complete_trace,
        "wages_exactly_once": bool(wage["passed"]),
    }
    if set(invariants) != set(INVARIANT_KEYS):
        raise AssertionError("internal M1 invariant evidence keys drifted")
    return {
        "label": label,
        "run_directory": _relative_directory(run_path, evidence_root),
        "seed": recorded_final.random_seed,
        "chunk_minutes": int(summary["chunk_minutes"]),
        "start_minute": initial.game_minute,
        "end_minute": recorded_final.game_minute,
        "tick_count": len(transactions),
        "skipped_tick_count": skipped_tick_count,
        "duplicated_tick_count": duplicated_tick_count,
        "active_agent_ids": sorted(agent.agent_id for agent in initial.agents.values() if agent.enabled),
        "inactive_actor_activity_count": inactive_activity_count,
        "action_count": len(action_behaviors),
        "decision_count": len(decisions),
        "event_count": len(events),
        "committed_transaction_count": len(transactions),
        "state_version_start": initial.state_version,
        "state_version_end": recorded_final.state_version,
        "initial_state_hash": actual_initial_hash,
        "final_state_hash": actual_final_hash,
        "authority_log_hash": actual_log_hash,
        "illegal_state_count": 0 if authoritative_state_invariants else 1,
        "invariants": invariants,
        "need_extrema": need_extrema,
        "need_decay_observations": {
            need: {
                "before": float(getattr(initial.agents[agent_id].needs, need)),
                "after": first_tick_needs[need],
                "elapsed_minutes": 1,
                "behavior_effect_applied": False,
            }
            for need in NEED_NAMES
        },
        "behavior_counts": behavior_counts,
        "wage_observation": wage,
    }


def _money_effects(transactions: Sequence[Mapping[str, Any]], household_id: str) -> tuple[int, int, bool]:
    count = 0
    amount = 0
    after_completion = True
    for transaction in transactions:
        for state_transaction in _iter_state_transactions(transaction):
            resolved_actions = state_transaction.get("resolved_actions", [])
            if not isinstance(resolved_actions, list):
                raise TypeError("resolved_actions must be an array")
            for resolved in resolved_actions:
                if not isinstance(resolved, dict):
                    continue
                effects = resolved.get("hard_effects", [])
                events = resolved.get("emitted_events", [])
                money = [
                    effect
                    for effect in effects
                    if isinstance(effect, dict) and effect.get("field_path") == f"households.{household_id}.money"
                ]
                if money:
                    completed = any(
                        isinstance(event, dict) and event.get("event_type") == EventType.WORK_COMPLETED.value
                        for event in events
                    )
                    after_completion = after_completion and completed
                for effect in money:
                    delta = effect.get("delta_integer")
                    if isinstance(delta, int) and not isinstance(delta, bool):
                        count += 1
                        amount += delta
    return count, amount, after_completion


def _relocate_active_agent(state: WorldState, agent_id: str, destination: str) -> WorldState:
    agent = state.agents[agent_id]
    locations = dict(state.locations)
    origin = locations[agent.current_location_id]
    locations[origin.location_id] = origin.model_copy(
        update={"current_agent_ids": [item for item in origin.current_agent_ids if item != agent_id]}
    )
    target = locations[destination]
    locations[destination] = target.model_copy(
        update={"current_agent_ids": sorted({*target.current_agent_ids, agent_id})}
    )
    agents = dict(state.agents)
    agents[agent_id] = agent.model_copy(update={"current_location_id": destination})
    return state.model_copy(update={"agents": agents, "locations": locations})


def _work_probe(catalog: CatalogBundle, agent_id: str, kind: str) -> dict[str, Any]:
    initial = build_initial_world_state(catalog, active_agent_id=agent_id)
    if kind == "late":
        initial = _relocate_active_agent(initial, agent_id, initial.agents[agent_id].assigned_work_location_id)
        agents = dict(initial.agents)
        agents[agent_id] = agents[agent_id].model_copy(update={"decision_due_at": 365})
        initial = initial.model_copy(update={"game_minute": 365, "state_version": 365, "agents": agents})
    elif kind == "missed":
        initial = initial.model_copy(
            update={
                "objects": {
                    object_id: (
                        obj.model_copy(update={"enabled": False})
                        if obj.object_type.value == "WORKSTATION"
                        and obj.location_id == initial.agents[agent_id].assigned_work_location_id
                        else obj
                    )
                    for object_id, obj in initial.objects.items()
                }
            }
        )
    elif kind != "completed":
        raise ValueError(f"unknown work probe: {kind}")

    engine = SimulationEngine(catalog, initial, active_agent_id=agent_id)
    result = engine.advance_to(840)
    events = list(result.events)
    transactions = list(result.transactions)
    event_counts = Counter(event.event_type.value for event in events)
    required_event = {
        "completed": EventType.WORK_COMPLETED.value,
        "late": EventType.WORK_LATE.value,
        "missed": EventType.WORK_MISSED.value,
    }[kind]
    if event_counts[required_event] != 1:
        raise ValueError(
            f"work probe {kind} observed {event_counts[required_event]} {required_event} events; expected exactly one"
        )
    household_id = initial.agents[agent_id].household_id
    settlement_count, wage_amount, wage_after_completion = _money_effects(transactions, household_id)
    sessions = engine.work_sessions
    if len(sessions) != 1:
        raise ValueError(f"work probe {kind} materialized {len(sessions)} sessions")
    session = sessions[0]
    completed = event_counts[EventType.WORK_COMPLETED.value] == 1 and session["paid"] is True
    return {
        "event_type": required_event,
        "completed": completed,
        "wage_settlement_count": settlement_count,
        "wage_amount": wage_amount,
        "wage_after_completion": wage_after_completion and completed,
        "event_type_counts": dict(sorted(event_counts.items())),
        "actual_start": session["first_work_minute"],
        "scheduled_start": session["start_game_minute"],
        "grace_minutes": session["grace_minutes"],
        "effective_work_minutes": session["effective_work_minutes"],
    }


def _exception_rejection(
    name: str,
    state: WorldState,
    operation: Callable[[], None],
    expected: tuple[type[Exception], ...],
) -> dict[str, Any]:
    before = state_hash(state)
    accepted = True
    rejection_code = "NO_REJECTION"
    try:
        operation()
    except expected as exc:
        accepted = False
        if isinstance(exc, ValidationError) and exc.errors():
            rejection_code = str(exc.errors()[0]["type"])
        else:
            rejection_code = type(exc).__name__
    return {
        "name": name,
        "accepted": accepted,
        "rejection_code": rejection_code,
        "state_hash_before": before,
        "state_hash_after": state_hash(state),
    }


def _negative_probes(catalog: CatalogBundle, agent_id: str) -> list[dict[str, Any]]:
    state = build_initial_world_state(catalog, active_agent_id=agent_id)
    household = state.households[state.agents[agent_id].household_id]

    def invalid_household(field: str) -> None:
        payload = household.model_dump(mode="json")
        payload[field] = -1
        HouseholdState.model_validate(payload)

    def invalid_needs() -> None:
        NeedValues(hunger=1.01, energy=0.5, hygiene=0.5, fun=0.5, social=0.5)

    def overlapping_action() -> None:
        first = ActionState(
            action_id="action_00000001",
            behavior_id=BehaviorId.IDLE,
            agent_ids=[agent_id],
            phase=ActionPhase.PERFORMING,
            destination_location_id=state.agents[agent_id].current_location_id,
            target_object_ids=[],
            started_at_game_minute=0,
            planned_end_game_minute=10,
        )
        second = first.model_copy(update={"action_id": "action_00000002"})
        agents = dict(state.agents)
        agents[agent_id] = agents[agent_id].model_copy(update={"current_action_id": first.action_id})
        invalid = state.model_copy(
            update={"agents": agents, "active_actions": {first.action_id: first, second.action_id: second}}
        )
        assert_world_invariants(invalid, active_agent_id=agent_id)

    enumerator = CandidateEnumerator(catalog)
    candidate = enumerator.enumerate(state, agent_id, work_window=None)[0]
    stale_proposal = ActionProposal(
        proposal_id="proposal_00000001",
        state_version=state.state_version + 1,
        actor_id=agent_id,
        candidate_id=candidate.candidate_id,
        behavior_id=candidate.behavior_id,
        target_agent_id=None,
        target_object_ids=candidate.target_object_ids,
        score=0.0,
        model_prediction_id="prediction_00000001",
    )
    before = state_hash(state)
    stale = CentralResolver(catalog).resolve(
        state,
        stale_proposal,
        candidate,
        reserved_food_units=0,
        work_window=None,
    )
    probes = [
        {
            "name": "stale_state_version",
            "accepted": stale.result is not ProposalResult.STATE_STALE,
            "rejection_code": stale.result.value,
            "state_hash_before": before,
            "state_hash_after": state_hash(state),
        },
        _exception_rejection("negative_money", state, lambda: invalid_household("money"), (ValidationError,)),
        _exception_rejection("negative_food", state, lambda: invalid_household("food_units"), (ValidationError,)),
        _exception_rejection("needs_out_of_range", state, invalid_needs, (ValidationError,)),
        _exception_rejection(
            "overlapping_primary_action",
            state,
            overlapping_action,
            (InvariantViolation,),
        ),
    ]

    ledger = EventLedger(catalog)
    first = ledger.create(
        EventType.MEAL_CONSUMED,
        staged_offset=0,
        game_minute=0,
        location_id=state.agents[agent_id].home_location_id,
        actor_ids=[agent_id],
        affected_agent_ids=[agent_id],
        witness_agent_ids=[],
        source_action_id=None,
        payload={"food_units": 1},
    )
    ledger.commit([first])
    ledger_before = _canonical_hash([event.model_dump(mode="json", exclude_none=False) for event in ledger.events])

    def mutate_event() -> None:
        forged = first.model_copy(update={"payload": {"food_units": 999}})
        ledger.commit([forged])

    event_probe = _exception_rejection("event_mutation", state, mutate_event, (ValueError,))
    event_probe["ledger_hash_before"] = ledger_before
    event_probe["ledger_hash_after"] = _canonical_hash(
        [event.model_dump(mode="json", exclude_none=False) for event in ledger.events]
    )
    probes.append(event_probe)
    return probes


def _corrupted_replay_probe(source_run: Path, output_root: Path) -> tuple[int, dict[str, Any]]:
    destination = output_root / f"corrupted-replay-probe-{uuid.uuid4().hex[:8]}"
    shutil.copytree(source_run, destination)
    events_path = destination / "events.jsonl"
    records = _read_jsonl(events_path)
    if not records:
        raise ValueError("baseline run has no event record for the corrupted replay probe")
    context = records[0].get("context")
    if not isinstance(context, dict):
        raise TypeError("baseline event context is malformed")
    context.pop("world_event", None)
    events_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    return _invoke_cli(("replay", "--run", str(destination), "--output-root", str(output_root)))


def build_evidence(
    catalog: CatalogBundle,
    *,
    config_path: Path,
    output_root: Path,
    evidence_root: Path,
    agent_id: str,
    days: int,
    seed: int,
    chunk_minutes: Sequence[int],
) -> tuple[dict[str, Any], bool]:
    if tuple(chunk_minutes) != (1, 7, 60):
        raise ValueError("M1 QA chunk list must be exactly 1,7,60")
    output_root.mkdir(parents=True, exist_ok=True)
    raw_runs: dict[str, dict[str, Any]] = {}
    run_exit_codes: dict[str, int] = {}
    for label, chunk in RUN_MATRIX:
        exit_code, summary = _run_headless_cli(
            config_path,
            output_root,
            agent_id=agent_id,
            days=days,
            seed=seed,
            chunk_minutes=chunk,
        )
        if exit_code != 0:
            raise RuntimeError(f"{label} run-headless failed: {summary}")
        raw_runs[label] = summary
        run_exit_codes[label] = exit_code

    runs = [
        _observe_run(
            catalog,
            raw_runs[label],
            label=label,
            evidence_root=evidence_root,
            agent_id=agent_id,
        )
        for label, _chunk in RUN_MATRIX
    ]
    baseline = runs[0]
    baseline_path = Path(str(raw_runs["baseline"]["run_path"])).resolve()
    source_tree_before = _tree_hash(baseline_path)
    replay_exit_code, replay_summary = _invoke_cli(
        ("replay", "--run", str(baseline_path), "--output-root", str(output_root))
    )
    source_tree_after = _tree_hash(baseline_path)
    if replay_exit_code != 0:
        raise RuntimeError(f"baseline replay failed: {replay_summary}")
    replay_path = Path(str(replay_summary["replay_output_path"])).resolve()
    baseline["replay"] = {
        "output_directory": _relative_directory(replay_path, evidence_root),
        "transaction_count": int(replay_summary["transaction_count"]),
        "expected_final_state_hash": str(replay_summary["expected_final_hash"]),
        "actual_final_state_hash": str(replay_summary["actual_final_hash"]),
        "match": bool(replay_summary["match"])
        and replay_summary["expected_authority_log_hash"] == replay_summary["actual_authority_log_hash"],
        "source_tree_hash_before": source_tree_before,
        "source_tree_hash_after": source_tree_after,
    }

    corrupted_exit_code, corrupted_summary = _corrupted_replay_probe(baseline_path, output_root)
    corrupted_machine_readable = (
        corrupted_exit_code != 0
        and corrupted_summary.get("completed") is False
        and corrupted_summary.get("error_type") == "KeyError"
    )
    work_probes = {
        "completed": _work_probe(catalog, agent_id, "completed"),
        "late": _work_probe(catalog, agent_id, "late"),
        "missed": _work_probe(catalog, agent_id, "missed"),
    }
    negative_probes = _negative_probes(catalog, agent_id)
    cli_contract = {
        "run_headless_exit_code": run_exit_codes["baseline"],
        "replay_exit_code": replay_exit_code,
        "run_headless_summary_machine_readable": isinstance(raw_runs["baseline"], dict),
        "replay_summary_machine_readable": isinstance(replay_summary, dict),
        "invalid_input_nonzero": corrupted_machine_readable,
    }
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "project_name": PROJECT_NAME,
        "scenario": {
            "agent_id": agent_id,
            "seed": seed,
            "days": days,
            "start_minute": 0,
            "end_minute": days * 1440,
            "allowed_behavior_ids": list(BEHAVIOR_IDS),
            "chunk_minutes": list(chunk_minutes),
        },
        "runs": runs,
        "work_probes": work_probes,
        "negative_probes": negative_probes,
        "cli_contract": cli_contract,
    }
    state_hashes = {str(run["final_state_hash"]) for run in runs}
    log_hashes = {str(run["authority_log_hash"]) for run in runs}
    initial_hashes = {str(run["initial_state_hash"]) for run in runs}
    passed = (
        len(state_hashes) == len(log_hashes) == len(initial_hashes) == 1
        and all(
            run["tick_count"] == days * 1440
            and run["skipped_tick_count"] == 0
            and run["duplicated_tick_count"] == 0
            and run["inactive_actor_activity_count"] == 0
            and run["illegal_state_count"] == 0
            and all(run["invariants"].values())
            and all(run["behavior_counts"][behavior_id] > 0 for behavior_id in BEHAVIOR_IDS)
            for run in runs
        )
        and work_probes["completed"]["completed"] is True
        and work_probes["completed"]["wage_settlement_count"] == 1
        and work_probes["late"]["completed"] is True
        and work_probes["late"]["wage_settlement_count"] == 1
        and work_probes["missed"]["completed"] is False
        and work_probes["missed"]["wage_settlement_count"] == 0
        and all(probe["accepted"] is False for probe in negative_probes)
        and all(probe["state_hash_before"] == probe["state_hash_after"] for probe in negative_probes)
        and cli_contract["run_headless_exit_code"] == 0
        and cli_contract["replay_exit_code"] == 0
        and all(
            cli_contract[key]
            for key in (
                "run_headless_summary_machine_readable",
                "replay_summary_machine_readable",
                "invalid_input_nonzero",
            )
        )
        and bool(baseline["replay"]["match"])
        and source_tree_before == source_tree_after
    )
    return evidence, passed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate real M1 black-box QA evidence")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--agent", default="npc_01")
    parser.add_argument("--days", default=3, type=int)
    parser.add_argument("--seed", default=12345, type=int)
    parser.add_argument("--chunk-minutes", default="1,7,60")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    chunks = tuple(int(item) for item in args.chunk_minutes.split(",") if item)
    output_root = args.output_root.resolve()
    evidence_path = args.evidence.resolve()
    try:
        evidence, passed = build_evidence(
            load_catalog(args.config),
            config_path=args.config.resolve(),
            output_root=output_root,
            evidence_root=evidence_path.parent,
            agent_id=args.agent,
            days=args.days,
            seed=args.seed,
            chunk_minutes=chunks,
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError, KeyError, AssertionError, ValidationError) as exc:
        print(
            json.dumps(
                {"completed": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps({"completed": passed, "evidence": str(evidence_path)}, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
