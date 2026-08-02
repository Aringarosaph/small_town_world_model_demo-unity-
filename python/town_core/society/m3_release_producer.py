"""Serial, resumable producer for SIM-owned M3 release evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from town_core.catalogs import load_catalog, load_m3_catalogs, m3_catalog_hash
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import ActionPhase, BehaviorId, EventType
from town_core.society.checkpoint import load_checkpoint
from town_core.society.replay import verify_society_run

PROJECT_NAME = "Small Town World Model（STWM）"
STATE_SCHEMA = "stwm.simulation.m3-release-producer-state/v1"
BUNDLE_SCHEMA = "stwm.simulation.m3-release-bundle/v1"
ARTIFACT_SCHEMAS = {
    "authority_evidence": "stwm.simulation.m3-authority-evidence/v1",
    "behavior_matrix_report": "stwm.simulation.m3-behavior-coverage/v1",
    "soak_7_day_report": "stwm.simulation.m3-soak-report/v1",
    "soak_30_day_report": "stwm.simulation.m3-soak-report/v1",
    "replay_report": "stwm.simulation.m3-replay-report/v1",
    "pathology_report": "stwm.simulation.m3-pathology-report/v1",
    "performance_report": "stwm.simulation.m3-performance-report/v1",
}
ARTIFACT_FILENAMES = {name: f"{name.replace('_', '-')}.json" for name in ARTIFACT_SCHEMAS}
SEEDS_7_DAY = (12345, 24680, 97531, 314159, 271828)
SEEDS_30_DAY = (12345, 24680, 97531)
DRIVER_CHUNKS = (1, 7, 60)
CHECKPOINT_INTERVAL_MINUTES = 360
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _catalog_config_hash(catalog: CatalogBundle) -> str:
    return hashlib.sha256(_canonical(catalog.model_dump(mode="json", exclude_none=False))).hexdigest()


def _repository_head() -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or SHA_PATTERN.fullmatch(value) is None:
        raise RuntimeError("could not resolve the repository source commit")
    return value


def _repository_is_clean() -> bool:
    completed = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("could not audit the repository working tree")
    return not completed.stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path.name}")
    return value


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"expected JSON object at {path.name}:{line_number}")
            yield value


def _payload(envelope: Mapping[str, Any]) -> dict[str, Any]:
    value = envelope.get("payload")
    if not isinstance(value, dict):
        raise TypeError("authority envelope payload must be an object")
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("M3 release output escaped its external root") from exc


def _ensure_external(output_root: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    output = output_root.resolve()
    if output == repository or repository in output.parents:
        raise ValueError("M3 release output_root must remain outside the repository")


def _process_exists(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _acquire_lock(lock_path: Path) -> None:
    lock_document = {"pid": os.getpid(), "host": platform.node(), "started_at_utc": _utc_now()}
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if attempt:
                raise RuntimeError("another M3 release producer owns this output root") from None
            try:
                existing = _read_json(lock_path)
                process_id = int(existing["pid"])
                same_host = existing.get("host") == platform.node()
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                raise RuntimeError("M3 release lock is unreadable; inspect it before recovery") from exc
            if not same_host or _process_exists(process_id):
                raise RuntimeError("another M3 release producer owns this output root") from None
            lock_path.unlink()
            continue
        try:
            os.write(descriptor, _canonical(lock_document))
        finally:
            os.close(descriptor)
        return
    raise RuntimeError("could not acquire the M3 release producer lock")


def _job_plan() -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = [
        {
            "job_id": "soak_7d_seed_12345_chunk_60",
            "role": "SOAK",
            "days": 7,
            "seed": 12345,
            "chunk_minutes": 60,
        },
        {
            "job_id": "canonical_repeat_seed_12345_chunk_60",
            "role": "CANONICAL_REPEAT",
            "days": 7,
            "seed": 12345,
            "chunk_minutes": 60,
        },
        {
            "job_id": "canonical_chunk_1_seed_12345",
            "role": "CANONICAL_CHUNK",
            "days": 7,
            "seed": 12345,
            "chunk_minutes": 1,
        },
        {
            "job_id": "canonical_chunk_7_seed_12345",
            "role": "CANONICAL_CHUNK",
            "days": 7,
            "seed": 12345,
            "chunk_minutes": 7,
        },
    ]
    jobs.extend(
        {
            "job_id": f"soak_7d_seed_{seed}_chunk_60",
            "role": "SOAK",
            "days": 7,
            "seed": seed,
            "chunk_minutes": 60,
        }
        for seed in SEEDS_7_DAY[1:]
    )
    jobs.extend(
        {
            "job_id": f"soak_30d_seed_{seed}_chunk_60",
            "role": "SOAK",
            "days": 30,
            "seed": seed,
            "chunk_minutes": 60,
        }
        for seed in SEEDS_30_DAY
    )
    return jobs


def _new_state(
    *,
    source_commit: str,
    catalog: CatalogBundle,
    catalog_hash: str,
) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "project_name": PROJECT_NAME,
        "source_commit": source_commit,
        "catalog_config_hash": _catalog_config_hash(catalog),
        "m3_catalog_hash": catalog_hash,
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "status": "PENDING",
        "artifacts": {},
        "jobs": [{**job, "status": "PENDING", "attempts": []} for job in _job_plan()],
    }


def _validate_state(state: Mapping[str, Any], *, source_commit: str, catalog: CatalogBundle, catalog_hash: str) -> None:
    if state.get("schema") != STATE_SCHEMA:
        raise ValueError("existing M3 release producer state has an unsupported schema")
    expected = (source_commit, _catalog_config_hash(catalog), catalog_hash)
    actual = (state.get("source_commit"), state.get("catalog_config_hash"), state.get("m3_catalog_hash"))
    if actual != expected:
        raise ValueError("existing M3 release state provenance differs; use a new external output root")
    observed_plan = [
        {key: item[key] for key in ("job_id", "role", "days", "seed", "chunk_minutes")}
        for item in state.get("jobs", [])
    ]
    if observed_plan != _job_plan():
        raise ValueError("existing M3 release state job matrix differs from the frozen plan")


def _invoke_production_run(config_path: Path, run_path: Path, job: Mapping[str, Any]) -> dict[str, Any]:
    command = (
        sys.executable,
        "-m",
        "town_core.cli",
        "run-society",
        "--config",
        str(config_path),
        "--days",
        str(job["days"]),
        "--seed",
        str(job["seed"]),
        "--chunk-minutes",
        str(job["chunk_minutes"]),
        "--out",
        str(run_path),
    )
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        document = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError("production run-society returned non-JSON output") from exc
    if not isinstance(document, dict):
        raise TypeError("production run-society output must be an object")
    if completed.returncode != 0:
        raise RuntimeError(f"production run-society failed: {document.get('error_type', 'unknown')}")
    return document


def _run_observation(catalog: CatalogBundle, run_path: Path) -> dict[str, Any]:
    initial = load_checkpoint(run_path / "initial_checkpoint.json")
    final = load_checkpoint(run_path / "final_checkpoint.json")
    summary = _read_json(run_path / "summary.json")
    decision_counts: Counter[str] = Counter()
    decision_batches: Counter[int] = Counter()
    max_candidates = 0
    idle_started: dict[str, int | None] = {agent_id: None for agent_id in initial.world.agents}
    max_idle: Counter[str] = Counter()
    for envelope in _iter_jsonl(run_path / "decisions.jsonl"):
        item = _payload(envelope)
        agent_id = str(item["agent_id"])
        minute = int(item["game_minute"])
        candidates = item.get("candidates", [])
        if not isinstance(candidates, list):
            raise TypeError("decision candidates must be a list")
        decision_counts[agent_id] += 1
        decision_batches[minute] += len(candidates)
        max_candidates = max(max_candidates, len(candidates))
        candidate_behaviors = {
            str(_payload_candidate(raw)["behavior_id"]) for raw in candidates if isinstance(raw, dict)
        }
        has_non_idle = any(value != BehaviorId.IDLE.value for value in candidate_behaviors)
        selected_idle = item.get("selected_behavior_id") == BehaviorId.IDLE.value
        if selected_idle and has_non_idle:
            idle_started[agent_id] = minute if idle_started[agent_id] is None else idle_started[agent_id]
        elif idle_started[agent_id] is not None:
            started = idle_started[agent_id]
            if started is None:
                raise AssertionError("idle streak disappeared during observation")
            max_idle[agent_id] = max(max_idle[agent_id], minute - started)
            idle_started[agent_id] = None
    for agent_id, started in idle_started.items():
        if started is not None:
            max_idle[agent_id] = max(max_idle[agent_id], final.world.game_minute - started)

    behavior_counts: Counter[str] = Counter()
    settled_counts: Counter[str] = Counter()
    terminal_phase: dict[str, str] = {}
    joint_participants: dict[str, tuple[str, ...]] = {}
    split_action_count = 0
    for envelope in _iter_jsonl(run_path / "actions.jsonl"):
        item = _payload(envelope)
        action_id = str(item["action_id"])
        participants = tuple(str(value) for value in item["agent_ids"])
        if item["phase"] == ActionPhase.CREATED.value:
            behavior_counts[str(item["behavior_id"])] += 1
            if bool(item["joint"]):
                joint_participants[action_id] = participants
        if bool(item["joint"]) and action_id in joint_participants and joint_participants[action_id] != participants:
            split_action_count += 1
        if item["phase"] in {
            ActionPhase.COMPLETED.value,
            ActionPhase.FAILED.value,
            ActionPhase.CANCELLED.value,
            ActionPhase.INTERRUPTED.value,
        }:
            terminal_phase[action_id] = str(item["phase"])
            for agent_id in participants:
                settled_counts[agent_id] += 1

    wage_by_household: Counter[str] = Counter()
    event_daily_counts: Counter[int] = Counter()
    event_semantic_keys: Counter[tuple[object, ...]] = Counter()
    acquisition_counts: Counter[str] = Counter(
        record.acquisition_type.value for record in final.knowledge_records.values()
    )
    invitation_counts: Counter[str] = Counter()
    for envelope in _iter_jsonl(run_path / "events.jsonl"):
        item = _payload(envelope)
        event_type = str(item["event_type"])
        event_daily_counts[int(item["game_minute"]) // 1440] += 1
        event_payload = item.get("payload", {})
        if not isinstance(event_payload, dict):
            raise TypeError("event payload must be an object")
        event_semantic_keys[
            (
                event_type,
                item.get("source_action_id"),
                tuple(item.get("actor_ids", [])),
                tuple(item.get("affected_agent_ids", [])),
                event_payload.get("session_id"),
                event_payload.get("need"),
            )
        ] += 1
        if event_type == EventType.WORK_COMPLETED.value:
            actor_id = str(item["actor_ids"][0])
            wage_by_household[final.world.agents[actor_id].household_id] += int(event_payload["wage_minor_units"])
        if event_type in {EventType.INVITATION_ACCEPTED.value, EventType.INVITATION_REJECTED.value}:
            invitation_counts[event_type] += 1

    households: dict[str, dict[str, Any]] = {
        household_id: {
            "money": household.money,
            "food": household.food_units,
            "minimum_money": household.money,
            "minimum_food": household.food_units,
            "crisis_started": None,
            "recovery_violation_count": 0,
        }
        for household_id, household in initial.world.households.items()
    }
    needs = {
        agent_id: {axis: float(value) for axis, value in agent.needs.model_dump().items()}
        for agent_id, agent in initial.world.agents.items()
    }
    zero_started: dict[tuple[str, str], int | None] = {
        (agent_id, axis): 0 if value <= 0.0 else None
        for agent_id, values in needs.items()
        for axis, value in values.items()
    }
    max_zero_minutes = 0
    relationships = {
        f"{edge.source_agent_id}|{edge.target_agent_id}": edge.model_dump(mode="json", exclude_none=False)
        for edge in initial.world.relationships
    }
    boundary_streak: Counter[str] = Counter()
    max_boundary_streak: Counter[str] = Counter()
    relationship_untraced = 0
    relationship_wrong_direction = 0
    known = {agent_id: set(agent.known_event_ids) for agent_id, agent in initial.world.agents.items()}
    shared_event_count = 0
    shared_without_speaker_knowledge = 0
    all_money_low_started: int | None = None
    max_all_money_low = 0
    for envelope in _iter_jsonl(run_path / "transactions.jsonl"):
        record = _payload(envelope)
        patch = record.get("patch")
        if not isinstance(patch, dict):
            raise TypeError("transaction patch must be an object")
        minute = int(patch["game_minute"])
        agents_upsert = patch.get("agents_upsert", {})
        if not isinstance(agents_upsert, dict):
            raise TypeError("agents_upsert must be an object")
        for agent_id, raw_agent in agents_upsert.items():
            if not isinstance(raw_agent, dict) or not isinstance(raw_agent.get("needs"), dict):
                raise TypeError("agent patch must contain needs")
            for axis, raw_value in raw_agent["needs"].items():
                value = float(raw_value)
                needs[str(agent_id)][str(axis)] = value
                key = (str(agent_id), str(axis))
                if value <= 0.0:
                    zero_started[key] = minute if zero_started[key] is None else zero_started[key]
                elif zero_started[key] is not None:
                    started = zero_started[key]
                    if started is None:
                        raise AssertionError("zero-need streak disappeared during observation")
                    max_zero_minutes = max(max_zero_minutes, minute - started)
                    zero_started[key] = None
        household_upsert = patch.get("households_upsert", {})
        if not isinstance(household_upsert, dict):
            raise TypeError("households_upsert must be an object")
        for household_id, raw_household in household_upsert.items():
            if not isinstance(raw_household, dict):
                raise TypeError("household patch must be an object")
            observation = households[str(household_id)]
            observation["money"] = int(raw_household["money"])
            observation["food"] = int(raw_household["food_units"])
            observation["minimum_money"] = min(int(observation["minimum_money"]), int(observation["money"]))
            observation["minimum_food"] = min(int(observation["minimum_food"]), int(observation["food"]))
        for observation in households.values():
            starved = int(observation["food"]) == 0 and int(observation["money"]) < catalog.economy.groceries.price
            started = observation["crisis_started"]
            if starved and started is None:
                observation["crisis_started"] = minute
            elif not starved and started is not None:
                if minute - int(started) > 7 * 1440:
                    observation["recovery_violation_count"] = int(observation["recovery_violation_count"]) + 1
                observation["crisis_started"] = None
        all_low = all(int(item["money"]) <= catalog.economy.money_low_threshold for item in households.values())
        if all_low:
            all_money_low_started = minute if all_money_low_started is None else all_money_low_started
            max_all_money_low = max(max_all_money_low, minute - all_money_low_started)
        else:
            all_money_low_started = None

        relationships_upsert = patch.get("relationships_upsert", {})
        if not isinstance(relationships_upsert, dict):
            raise TypeError("relationships_upsert must be an object")
        changes = record.get("changes", [])
        if not isinstance(changes, list):
            raise TypeError("transaction changes must be a list")
        traced = {str(value).removeprefix("relationship_updated:").replace(":", "|") for value in changes}
        relationship_untraced += sum(key not in traced for key in relationships_upsert)
        appended_events = patch.get("events_append", [])
        if not isinstance(appended_events, list):
            raise TypeError("events_append must be a list")
        expected_directions: set[str] = set()
        for raw_event in appended_events:
            if not isinstance(raw_event, dict):
                raise TypeError("appended event must be an object")
            actors = [str(value) for value in raw_event.get("actor_ids", [])]
            affected = [str(value) for value in raw_event.get("affected_agent_ids", [])]
            if actors:
                expected_directions.update(f"{source}|{actors[0]}" for source in affected if source != actors[0])
            if raw_event.get("event_type") == EventType.EVENT_SHARED.value:
                shared_event_count += 1
                raw_payload = raw_event.get("payload", {})
                event_id = raw_payload.get("shared_event_id") if isinstance(raw_payload, dict) else None
                if event_id not in known.get(actors[0], set()):
                    shared_without_speaker_knowledge += 1
        relationship_wrong_direction += sum(
            key not in expected_directions for key in relationships_upsert if expected_directions
        )
        relationships.update(relationships_upsert)
        knowledge_upsert = patch.get("knowledge_upsert", {})
        if not isinstance(knowledge_upsert, dict):
            raise TypeError("knowledge_upsert must be an object")
        for raw_record in knowledge_upsert.values():
            if isinstance(raw_record, dict):
                known[str(raw_record["agent_id"])].add(str(raw_record["event_id"]))
        if minute % 1440 == 0:
            for axis in ("familiarity", "affinity", "trust", "tension"):
                fraction = sum(
                    float(edge[axis]) <= 0.01 or float(edge[axis]) >= 0.99 for edge in relationships.values()
                ) / max(1, len(relationships))
                boundary_streak[axis] = boundary_streak[axis] + 1 if fraction > 0.8 else 0
                max_boundary_streak[axis] = max(max_boundary_streak[axis], boundary_streak[axis])
    for started in zero_started.values():
        if started is not None:
            max_zero_minutes = max(max_zero_minutes, final.world.game_minute - started)
    for observation in households.values():
        crisis_started = observation["crisis_started"]
        if crisis_started is not None and final.world.game_minute - int(crisis_started) > 7 * 1440:
            observation["recovery_violation_count"] = int(observation["recovery_violation_count"]) + 1

    charges: dict[str, Counter[str]] = {household_id: Counter() for household_id in households}
    grocery_purchases: Counter[str] = Counter()
    home_meals: Counter[str] = Counter()
    failed_charge_count = 0
    for action_id, phase in terminal_phase.items():
        if phase != ActionPhase.COMPLETED.value and f"action_resource:{action_id}" in final.settlement_keys:
            failed_charge_count += 1
    for envelope in _iter_jsonl(run_path / "actions.jsonl"):
        item = _payload(envelope)
        if item["phase"] != ActionPhase.COMPLETED.value:
            continue
        behavior = BehaviorId(str(item["behavior_id"]))
        charged_participants = [str(value) for value in item["agent_ids"]]
        charged = charged_participants if bool(item["joint"]) else charged_participants[:1]
        if behavior is BehaviorId.BUY_GROCERIES:
            household_id = final.world.agents[charged[0]].household_id
            charges[household_id]["grocery"] += catalog.economy.groceries.price
            grocery_purchases[household_id] += 1
        elif behavior is BehaviorId.EAT_AT_HOME:
            home_meals[final.world.agents[charged[0]].household_id] += 1
        elif behavior in {BehaviorId.EAT_AT_CAFE, BehaviorId.DRINK_AT_BAR}:
            charge_key = "cafe" if behavior is BehaviorId.EAT_AT_CAFE else "bar"
            price = catalog.economy.cafe_meal.price if charge_key == "cafe" else catalog.economy.bar_drink.price
            for agent_id in charged:
                charges[final.world.agents[agent_id].household_id][charge_key] += price
    economy = []
    for household_id in sorted(households):
        observation = households[household_id]
        initial_household = initial.world.households[household_id]
        final_household = final.world.households[household_id]
        economy.append(
            {
                "household_id": household_id,
                "initial_money": initial_household.money,
                "final_money": final_household.money,
                "unique_wages": wage_by_household[household_id],
                "grocery_charges": charges[household_id]["grocery"],
                "cafe_charges": charges[household_id]["cafe"],
                "bar_charges": charges[household_id]["bar"],
                "initial_food": initial_household.food_units,
                "final_food": final_household.food_units,
                "grocery_purchases": grocery_purchases[household_id],
                "completed_home_meals": home_meals[household_id],
                "failed_or_cancelled_charge_count": failed_charge_count,
                "duplicate_settlement_count": len(final.settlement_keys) - len(set(final.settlement_keys)),
                "minimum_money": observation["minimum_money"],
                "minimum_food": observation["minimum_food"],
                "resource_recovery_within_workweek": observation["recovery_violation_count"] == 0,
            }
        )
    event_types = {item.value for item in EventType}
    terminal_leaks = sum(reservation.owner_action_id in terminal_phase for reservation in final.reservations.values())
    work_bound_by_agent: Counter[str] = Counter()
    for action in final.world.active_actions.values():
        if (
            action.behavior_id is BehaviorId.WORK_SHIFT
            and action.planned_end_game_minute is not None
            and action.planned_end_game_minute < final.world.game_minute
        ):
            work_bound_by_agent.update(str(agent_id) for agent_id in action.agent_ids)
    work_bound_violations = sum(work_bound_by_agent.values())
    relationship_out_of_range = sum(
        not all(0.0 <= float(edge[axis]) <= 1.0 for axis in ("familiarity", "affinity", "trust", "tension"))
        for edge in relationships.values()
    )
    return {
        "run_id": str(summary["run_id"]),
        "behavior_counts": dict(behavior_counts),
        "agent_liveness": [
            {
                "agent_id": agent_id,
                "enabled": final.world.agents[agent_id].enabled,
                "scheduled": final.world.agents[agent_id].assigned_work_location_id is not None,
                "decision_count": decision_counts[agent_id],
                "settled_action_count": settled_counts[agent_id],
                "max_idle_with_legal_non_idle_minutes": max_idle[agent_id],
                "work_bound_violation_count": work_bound_by_agent[agent_id],
            }
            for agent_id in sorted(final.world.agents)
        ],
        "household_economy": economy,
        "relationship": {
            "edge_count": len(relationships),
            "out_of_range_count": relationship_out_of_range,
            "wrong_direction_count": relationship_wrong_direction,
            "untraced_delta_count": relationship_untraced,
            "boundary_violation_count": sum(value >= 7 for value in max_boundary_streak.values()),
        },
        "knowledge": {
            "acquisition_counts": dict(acquisition_counts),
            "shared_event_count": shared_event_count,
            "shared_without_speaker_knowledge_count": shared_without_speaker_knowledge,
        },
        "joint": {
            "joint_action_count": len(joint_participants),
            "invitation_accepted_count": invitation_counts[EventType.INVITATION_ACCEPTED.value],
            "invitation_rejected_count": invitation_counts[EventType.INVITATION_REJECTED.value],
            "split_action_count": split_action_count,
            "terminal_phase_counts": dict(Counter(terminal_phase.values())),
        },
        "pathology": {
            "max_candidates_per_agent": max_candidates,
            "max_decision_batch": max(decision_batches.values(), default=0),
            "reservation_leak_count": terminal_leaks,
            "slot_conflict_count": 0 if summary["invariants"]["passed"] else 1,
            "permanent_idle_agent_count": sum(value > 1440 for value in max_idle.values()),
            "work_bound_violation_count": work_bound_violations,
            "max_recoverable_zero_need_minutes": max_zero_minutes,
            "unrecovered_household_count": sum(
                int(item["recovery_violation_count"]) > 0 for item in households.values()
            ),
            "max_all_households_money_low_streak_days": round(max_all_money_low / 1440, 6),
            "relationship_boundary_violation_count": sum(value >= 7 for value in max_boundary_streak.values()),
            "max_events_per_game_day": max(event_daily_counts.values(), default=0),
            "event_growth_linear": all(count <= 1000 for count in event_daily_counts.values()),
            "untyped_event_count": sum(
                count for key, count in event_semantic_keys.items() if str(key[0]) not in event_types
            ),
            "duplicate_semantic_event_count": sum(max(0, count - 1) for count in event_semantic_keys.values()),
        },
        "performance": dict(summary["performance"]),
    }


def _payload_candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    society_candidate = raw.get("candidate")
    if not isinstance(society_candidate, dict):
        raise TypeError("scored candidate must contain a society candidate")
    candidate = society_candidate.get("candidate")
    if not isinstance(candidate, dict):
        raise TypeError("society candidate must contain an M3 candidate")
    return candidate


def _soak_jobs(state: Mapping[str, Any], days: int) -> list[dict[str, Any]]:
    return [item for item in state["jobs"] if item["role"] == "SOAK" and int(item["days"]) == days]


def _latest_attempt(job: Mapping[str, Any]) -> dict[str, Any]:
    attempts = job.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        raise ValueError(f"release job has no completed attempt: {job['job_id']}")
    value = attempts[-1]
    if not isinstance(value, dict) or value.get("status") != "COMPLETED":
        raise ValueError(f"release job latest attempt is incomplete: {job['job_id']}")
    return value


def _aggregate_artifacts(
    *,
    state: Mapping[str, Any],
    output_root: Path,
    catalog: CatalogBundle,
    source_commit: str,
    reference_machine: str,
) -> dict[str, dict[str, Any]]:
    jobs = [item for item in state["jobs"] if isinstance(item, dict)]
    observations = {
        str(job["job_id"]): _run_observation(catalog, output_root / str(_latest_attempt(job)["run_directory"]))
        for job in jobs
    }
    generated = _utc_now()
    common = {"project_name": PROJECT_NAME, "source_commit": source_commit, "generated_at_utc": generated}
    catalog_surface = {
        "npcs": len(catalog.population.npcs),
        "households": len(catalog.households.households),
        "locations": len(catalog.locations.locations),
        "behaviors": len(catalog.behaviors.behaviors),
        "object_types": len(catalog.objects.object_types),
        "relationship_edges": int(observations["soak_7d_seed_12345_chunk_60"]["relationship"]["edge_count"]),
        "needs": len(catalog.model.need_axes),
        "personality_axes": len(catalog.utility.personality_axes),
        "mood_axes": len(catalog.model.mood_axes),
        "relationship_axes": len(catalog.model.relationship_axes),
    }
    soak_rows: list[dict[str, Any]] = []
    for days, seeds in ((7, SEEDS_7_DAY), (30, SEEDS_30_DAY)):
        by_seed = {int(job["seed"]): job for job in _soak_jobs(state, days)}
        for seed in seeds:
            job = by_seed[seed]
            attempt = _latest_attempt(job)
            summary = attempt["summary"]
            replay = attempt["replay"]
            soak_rows.append(
                {
                    "days": days,
                    "seed": seed,
                    "status": "PASS",
                    "final_state_hash": summary["final_state_hash"],
                    "ledger_hash": summary["ledger_hash"],
                    "authority_log_hash": summary["authority_log_hash"],
                    "replay_final_state_hash": replay["actual_final_state_hash"],
                    "replay_ledger_hash": replay["actual_ledger_hash"],
                    "replay_authority_log_hash": replay["actual_authority_log_hash"],
                    "invariant_violation_count": 0,
                    "artifact": "soak_7_day_report" if days == 7 else "soak_30_day_report",
                }
            )
    baseline = next(job for job in jobs if job["job_id"] == "soak_7d_seed_12345_chunk_60")
    repeat = next(job for job in jobs if job["role"] == "CANONICAL_REPEAT")
    chunks = {int(job["chunk_minutes"]): job for job in jobs if job["role"] == "CANONICAL_CHUNK"}
    chunks[60] = baseline
    baseline_attempt = _latest_attempt(baseline)
    repeat_attempt = _latest_attempt(repeat)
    hash_fields = ("final_state_hash", "ledger_hash", "authority_log_hash")
    determinism = {
        "canonical_seed": 12345,
        "driver_chunks_minutes": list(DRIVER_CHUNKS),
        "checkpoint_interval_minutes": CHECKPOINT_INTERVAL_MINUTES,
        **{
            f"repeat_{field}_match": repeat_attempt["summary"][field] == baseline_attempt["summary"][field]
            for field in hash_fields
        },
        **{
            f"chunk_{field}_match": len({_latest_attempt(chunks[chunk])["summary"][field] for chunk in DRIVER_CHUNKS})
            == 1
            for field in hash_fields
        },
        **{
            f"checkpoint_resume_{field}_match": baseline_attempt["replay"][f"actual_{field}"]
            == baseline_attempt["summary"][field]
            for field in hash_fields
        },
        **{
            f"authoritative_replay_{field}_match": all(row[field] == row[f"replay_{field}"] for row in soak_rows)
            for field in hash_fields
        },
        "checkpoint_resume_mismatch_count": int(baseline_attempt["replay"]["checkpoint_mismatch_count"]),
        "replay_mismatch_count": sum(not bool(_latest_attempt(job)["replay"]["match"]) for job in jobs),
        "source_run_mutation_count": sum(
            int(_latest_attempt(job)["replay"]["source_run_mutation_count"]) for job in jobs
        ),
    }
    behavior_totals: Counter[str] = Counter()
    for job in jobs:
        if job["role"] == "SOAK":
            behavior_totals.update(observations[str(job["job_id"])]["behavior_counts"])
    behavior_cases: list[dict[str, Any]] = [
        {
            "behavior_id": behavior.value,
            "fixture_id": f"m3_behavior_{behavior.value}",
            "sim_targeted_probe_owner": "SIM_FAST_TARGETED_FIXTURES",
            "sim_targeted_probe_results": None,
            "release_soak_occurrence_count": behavior_totals[behavior.value],
            "unity_presentation": None,
            "unity_presentation_owner": "UNITY",
            "run_refs": [
                f"{_latest_attempt(job)['run_directory']}/actions.jsonl" for job in jobs if job["role"] == "SOAK"
            ],
        }
        for behavior in BehaviorId
    ]
    canonical_30 = next(job for job in jobs if job["job_id"] == "soak_30d_seed_12345_chunk_60")
    canonical_observation = observations[str(canonical_30["job_id"])]
    liveness_by_agent: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if job["role"] != "SOAK":
            continue
        for item in observations[str(job["job_id"])]["agent_liveness"]:
            agent_id = str(item["agent_id"])
            aggregate = liveness_by_agent.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "enabled": True,
                    "scheduled": True,
                    "decision_count": 0,
                    "settled_action_count": 0,
                    "max_idle_with_legal_non_idle_minutes": 0,
                    "work_bound_violation_count": 0,
                },
            )
            aggregate["enabled"] = bool(aggregate["enabled"] and item["enabled"])
            aggregate["scheduled"] = bool(aggregate["scheduled"] and item["scheduled"])
            aggregate["decision_count"] += int(item["decision_count"])
            aggregate["settled_action_count"] += int(item["settled_action_count"])
            aggregate["max_idle_with_legal_non_idle_minutes"] = max(
                int(aggregate["max_idle_with_legal_non_idle_minutes"]),
                int(item["max_idle_with_legal_non_idle_minutes"]),
            )
            aggregate["work_bound_violation_count"] += int(item["work_bound_violation_count"])
    pathology_keys_max = (
        "max_candidates_per_agent",
        "max_decision_batch",
        "max_recoverable_zero_need_minutes",
        "max_all_households_money_low_streak_days",
        "max_events_per_game_day",
    )
    pathology_keys_sum = (
        "reservation_leak_count",
        "slot_conflict_count",
        "permanent_idle_agent_count",
        "work_bound_violation_count",
        "unrecovered_household_count",
        "relationship_boundary_violation_count",
        "untyped_event_count",
        "duplicate_semantic_event_count",
    )
    soak_observations = [observations[str(job["job_id"])] for job in jobs if job["role"] == "SOAK"]
    pathology = {
        **{key: max(item["pathology"][key] for item in soak_observations) for key in pathology_keys_max},
        **{key: sum(item["pathology"][key] for item in soak_observations) for key in pathology_keys_sum},
        "event_growth_linear": all(item["pathology"]["event_growth_linear"] for item in soak_observations),
    }
    relationship_summary = {
        "edge_count": int(canonical_observation["relationship"]["edge_count"]),
        "out_of_range_count": sum(int(item["relationship"]["out_of_range_count"]) for item in soak_observations),
        "wrong_direction_count": sum(int(item["relationship"]["wrong_direction_count"]) for item in soak_observations),
        "untraced_delta_count": sum(int(item["relationship"]["untraced_delta_count"]) for item in soak_observations),
        "boundary_epsilon": 0.01,
        "boundary_fraction_limit": 0.8,
        "boundary_streak_days": 7,
        "boundary_violation_count": int(pathology["relationship_boundary_violation_count"]),
    }
    thirty_performance = [observations[str(job["job_id"])]["performance"] for job in jobs if int(job["days"]) == 30]
    performance = {
        "reference_machine": reference_machine,
        "os": str(thirty_performance[0]["platform"]),
        "python_version": str(thirty_performance[0]["python_version"]),
        "rss_collection_method": str(thirty_performance[0]["rss_collection_method"]),
        "wall_time_seconds_30_day": max(float(item["wall_seconds"]) for item in thirty_performance),
        "peak_rss_bytes": max(int(item["peak_rss_bytes"]) for item in thirty_performance),
        "post_warmup_rss_slope_bytes_per_game_day": max(
            float(item["post_warmup_rss_slope_bytes_per_game_day"]) for item in thirty_performance
        ),
        "decision_batch_p95_ms": max(float(item["decision_batch_p95_ms"]) for item in thirty_performance),
        "tick_p99_ms": max(float(item["tick_p99_ms"]) for item in thirty_performance),
    }
    replay_runs = [
        {
            "job_id": job["job_id"],
            "run_ref": _latest_attempt(job)["run_directory"],
            **_latest_attempt(job)["replay"],
        }
        for job in jobs
    ]
    unsupported = [
        {
            "qa_field": "matrices.behavior_coverage[].unity_presentation",
            "owner": "UNITY",
            "reason": "Unity presentation is not a Python authority fact.",
        },
        {
            "qa_field": "matrices.unity",
            "owner": "UNITY",
            "reason": "Unity batchmode and live presentation evidence are not generated by SIM.",
        },
        {
            "qa_field": "gates.m0_m2_regressions|gates.repository_guard",
            "owner": "QA",
            "reason": "Repository integration gates are evaluated by check_m3, not by a soak run.",
        },
        {
            "qa_field": "behavior targeted fixture probe booleans",
            "owner": "SIM_FAST_TARGETED_FIXTURES",
            "reason": "The release soak records occurrences; it does not relabel test assertions as run facts.",
        },
        {
            "qa_field": "matrices.knowledge_permissions.unknown_share_rejected",
            "owner": "SIM_FAST_TARGETED_FIXTURES",
            "reason": "Rejecting an unknown share is a targeted negative probe, not a positive soak observation.",
        },
        {
            "qa_field": "matrices.joint_action.cancel_release|failure_release|timeout_release",
            "owner": "SIM_FAST_TARGETED_FIXTURES",
            "reason": "Forced terminal-path release coverage requires targeted JointAction probes.",
        },
    ]
    authority = {
        "schema": ARTIFACT_SCHEMAS["authority_evidence"],
        **common,
        "profile": "M3_RELEASE_SOCIETY",
        "qa_matrix_projection": {
            "catalog_surface": catalog_surface,
            "agent_liveness": [liveness_by_agent[key] for key in sorted(liveness_by_agent)],
            "household_economy": canonical_observation["household_economy"],
            "relationship_summary": relationship_summary,
            "determinism": determinism,
            "soak_runs": soak_rows,
            "pathology": pathology,
            "performance": performance,
        },
        "catalog_protocol_version": catalog.world.protocol_version,
        "catalog_surface_observation": catalog_surface,
        "soak_run_evidence_refs": [
            {
                "days": int(job["days"]),
                "seed": int(job["seed"]),
                "summary": f"{_latest_attempt(job)['run_directory']}/summary.json",
                "authority_log": f"{_latest_attempt(job)['run_directory']}/authority.jsonl",
                "final_checkpoint": f"{_latest_attempt(job)['run_directory']}/final_checkpoint.json",
            }
            for job in jobs
            if job["role"] == "SOAK"
        ],
        "knowledge_observation": canonical_observation["knowledge"],
        "joint_action_observation": canonical_observation["joint"],
        "not_produced_qa_fields": unsupported,
    }
    behavior_report = {
        "schema": ARTIFACT_SCHEMAS["behavior_matrix_report"],
        **common,
        "cases": behavior_cases,
        "all_22_observed": all(int(item["release_soak_occurrence_count"]) > 0 for item in behavior_cases),
        "scope_note": "SIM release-soak occurrence evidence; targeted probe and Unity facts retain their owners.",
    }
    soak_reports = {}
    for days, name in ((7, "soak_7_day_report"), (30, "soak_30_day_report")):
        soak_reports[name] = {
            "schema": ARTIFACT_SCHEMAS[name],
            **common,
            "days": days,
            "expected_seeds": list(SEEDS_7_DAY if days == 7 else SEEDS_30_DAY),
            "chunk_minutes": 60,
            "runs": [row for row in soak_rows if row["days"] == days],
            "run_evidence_refs": [
                {
                    "seed": int(job["seed"]),
                    "run_directory": _latest_attempt(job)["run_directory"],
                    "summary": f"{_latest_attempt(job)['run_directory']}/summary.json",
                    "final_checkpoint": f"{_latest_attempt(job)['run_directory']}/final_checkpoint.json",
                    "authority_log": f"{_latest_attempt(job)['run_directory']}/authority.jsonl",
                }
                for job in _soak_jobs(state, days)
            ],
        }
    return {
        "authority_evidence": authority,
        "behavior_matrix_report": behavior_report,
        **soak_reports,
        "replay_report": {
            "schema": ARTIFACT_SCHEMAS["replay_report"],
            **common,
            "runs": replay_runs,
            "determinism": determinism,
        },
        "pathology_report": {
            "schema": ARTIFACT_SCHEMAS["pathology_report"],
            **common,
            "matrix": pathology,
            "run_observations": [
                {"job_id": job["job_id"], "pathology": observations[str(job["job_id"])]["pathology"]}
                for job in jobs
                if job["role"] == "SOAK"
            ],
        },
        "performance_report": {
            "schema": ARTIFACT_SCHEMAS["performance_report"],
            **common,
            "matrix": performance,
            "runs_30_day": [
                {
                    "job_id": job["job_id"],
                    "run_ref": _latest_attempt(job)["run_directory"],
                    "performance": observations[str(job["job_id"])]["performance"],
                }
                for job in jobs
                if int(job["days"]) == 30
            ],
        },
    }


def _artifact_descriptor(path: Path, root: Path, schema: str) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": _relative(path, root),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "redacted": True,
        "schema": schema,
    }


def _write_artifacts(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
    source_commit: str,
) -> dict[str, object]:
    artifact_root = output_root / "artifacts"
    descriptors: dict[str, dict[str, object]] = {}
    for name, document in documents.items():
        path = artifact_root / ARTIFACT_FILENAMES[name]
        _write_json(path, document)
        descriptors[name] = _artifact_descriptor(path, output_root, ARTIFACT_SCHEMAS[name])
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "project_name": PROJECT_NAME,
        "source_commit": source_commit,
        "generated_at_utc": _utc_now(),
        "profile": "M3_RELEASE_SOCIETY",
        "complete": True,
        "artifacts": descriptors,
        "explicitly_not_generated": [
            "stwm.qa.m3-acceptance-evidence/v1",
            "Unity registry/semantic/debug/EditMode/PlayMode/batchmode artifacts",
        ],
    }
    _write_json(output_root / "bundle-manifest.json", bundle)
    return bundle


def _validate_completed_bundle(state: Mapping[str, Any], output_root: Path) -> None:
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACT_SCHEMAS):
        raise ValueError("completed M3 release state has an incomplete artifact descriptor set")
    for name, raw_descriptor in artifacts.items():
        if not isinstance(raw_descriptor, dict):
            raise TypeError(f"artifact descriptor is not an object: {name}")
        path_value = raw_descriptor.get("path")
        if not isinstance(path_value, str):
            raise TypeError(f"artifact path is not a string: {name}")
        path = output_root / path_value
        _relative(path, output_root)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != raw_descriptor.get("sha256") or len(raw) != raw_descriptor.get("bytes"):
            raise ValueError(f"completed M3 release artifact digest differs: {name}")
        document = _read_json(path)
        if document.get("schema") != ARTIFACT_SCHEMAS[name]:
            raise ValueError(f"completed M3 release artifact schema differs: {name}")


def produce_release_evidence(
    *,
    config_path: Path,
    output_root: Path,
    source_commit: str,
    reference_machine: str,
    max_new_runs: int | None = None,
    plan_only: bool = False,
) -> dict[str, Any]:
    if SHA_PATTERN.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a full lowercase 40-character Git SHA")
    if _repository_head() != source_commit:
        raise ValueError("source_commit must equal the checked-out repository HEAD")
    if not _repository_is_clean():
        raise ValueError("M3 release evidence requires a clean repository working tree")
    if max_new_runs is not None and max_new_runs < 0:
        raise ValueError("max_new_runs cannot be negative")
    if reference_machine == "producer Apple-silicon MacBook Air" and (
        platform.system() != "Darwin" or platform.machine() != "arm64"
    ):
        raise ValueError("the frozen MacBook Air reference label requires a Darwin arm64 producer host")
    _ensure_external(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "producer-state.json"
    lock_path = output_root / "producer.lock"
    _acquire_lock(lock_path)
    try:
        catalog = load_catalog(config_path)
        m3_catalogs = load_m3_catalogs(config_path, catalog=catalog)
        catalog_hash = m3_catalog_hash(m3_catalogs)
        state = (
            _read_json(state_path)
            if state_path.exists()
            else _new_state(
                source_commit=source_commit,
                catalog=catalog,
                catalog_hash=catalog_hash,
            )
        )
        _validate_state(state, source_commit=source_commit, catalog=catalog, catalog_hash=catalog_hash)
        if plan_only:
            if not state_path.exists():
                _write_json(state_path, state)
            return {"completed": False, "status": state["status"], "planned_jobs": len(state["jobs"])}
        if state.get("status") == "COMPLETED":
            _validate_completed_bundle(state, output_root)
            return {
                "completed": True,
                "status": "COMPLETED",
                "bundle_manifest": "bundle-manifest.json",
                "artifacts": state["artifacts"],
            }
        completed_this_call = 0
        for job in state["jobs"]:
            if job["status"] == "COMPLETED":
                continue
            if max_new_runs is not None and completed_this_call >= max_new_runs:
                break
            attempts = job["attempts"]
            attempt_number = len(attempts) + 1
            run_path = output_root / "runs" / str(job["job_id"]) / f"attempt_{attempt_number:04d}"
            attempt: dict[str, Any] = {
                "attempt": attempt_number,
                "status": "IN_PROGRESS",
                "started_at_utc": _utc_now(),
                "run_directory": _relative(run_path, output_root),
            }
            attempts.append(attempt)
            state["status"] = "IN_PROGRESS"
            state["updated_at_utc"] = _utc_now()
            _write_json(state_path, state)
            try:
                summary = _invoke_production_run(config_path, run_path, job)
                replay = verify_society_run(run_path)
                required_hashes = ("final_state_hash", "ledger_hash", "authority_log_hash")
                if not replay["match"] or any(summary[field] != replay[f"actual_{field}"] for field in required_hashes):
                    raise RuntimeError("production run failed authoritative replay/hash verification")
                if not bool(summary["invariants"]["passed"]):
                    raise RuntimeError("production run reported invariant violations")
                attempt.update(
                    {
                        "status": "COMPLETED",
                        "completed_at_utc": _utc_now(),
                        "summary": {
                            key: summary[key]
                            for key in (
                                "run_id",
                                "seed",
                                "tick_count",
                                "final_state_hash",
                                "final_checkpoint_hash",
                                "ledger_hash",
                                "transaction_chain_hash",
                                "authority_log_hash",
                                "authority_record_count",
                            )
                        },
                        "replay": replay,
                    }
                )
                job["status"] = "COMPLETED"
                completed_this_call += 1
            except Exception as exc:
                attempt.update(
                    {
                        "status": "FAILED",
                        "completed_at_utc": _utc_now(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                job["status"] = "PENDING"
                state["status"] = "FAILED"
                state["updated_at_utc"] = _utc_now()
                _write_json(state_path, state)
                raise
            state["updated_at_utc"] = _utc_now()
            _write_json(state_path, state)
        complete = all(job["status"] == "COMPLETED" for job in state["jobs"])
        if not complete:
            state["status"] = "PARTIAL"
            state["updated_at_utc"] = _utc_now()
            _write_json(state_path, state)
            return {
                "completed": False,
                "status": "PARTIAL",
                "completed_jobs": sum(job["status"] == "COMPLETED" for job in state["jobs"]),
                "total_jobs": len(state["jobs"]),
            }
        documents = _aggregate_artifacts(
            state=state,
            output_root=output_root,
            catalog=catalog,
            source_commit=source_commit,
            reference_machine=reference_machine,
        )
        bundle = _write_artifacts(documents, output_root=output_root, source_commit=source_commit)
        state["status"] = "COMPLETED"
        state["updated_at_utc"] = _utc_now()
        state["artifacts"] = bundle["artifacts"]
        _write_json(state_path, state)
        return {
            "completed": True,
            "status": "COMPLETED",
            "bundle_manifest": "bundle-manifest.json",
            "artifacts": bundle["artifacts"],
        }
    finally:
        lock_path.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small Town World Model（STWM） M3 release soak producer")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--reference-machine",
        required=True,
        help='measured host label; QA release host uses "producer Apple-silicon MacBook Air"',
    )
    parser.add_argument("--max-new-runs", type=int, help="stop cleanly after N newly completed jobs")
    parser.add_argument("--plan-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = produce_release_evidence(
            config_path=args.config,
            output_root=args.output_root,
            source_commit=args.source_commit,
            reference_machine=args.reference_machine,
            max_new_runs=args.max_new_runs,
            plan_only=args.plan_only,
        )
    except (OSError, TypeError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"completed": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    document["host"] = {"system": platform.system(), "machine": platform.machine()}
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
