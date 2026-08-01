"""Apply ordered M1 transactions without re-running policy logic."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from town_core.domain.state_models import WorldEvent, WorldState
from town_core.simulation.initialization import state_hash
from town_core.simulation.invariants import assert_transition, assert_world_invariants
from town_core.simulation.run import RUN_SCHEMA, authority_log_hash, make_run_path
from town_core.simulation.transactions import apply_transaction_record


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected JSON object at {path.name}:{line_number}")
        records.append(value)
    return records


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_run(source_run: Path, *, output_root: Path | None = None) -> dict[str, Any]:
    source_run = source_run.resolve()
    required = (
        "metadata.json",
        "config_snapshot/catalog.json",
        "initial_snapshot.json",
        "decisions.jsonl",
        "actions.jsonl",
        "transactions.jsonl",
        "events.jsonl",
        "final_snapshot.json",
        "summary.json",
    )
    missing = [name for name in required if not (source_run / name).is_file()]
    if missing:
        raise FileNotFoundError(f"source run is incomplete: {missing}")
    source_digests_before = {name: _file_digest(source_run / name) for name in required}
    metadata = _read_json(source_run / "metadata.json")
    source_summary = _read_json(source_run / "summary.json")
    state = WorldState.model_validate(_read_json(source_run / "initial_snapshot.json"))
    initial_state = state

    transaction_envelopes = _read_jsonl(source_run / "transactions.jsonl")
    authority_records: dict[str, list[dict[str, Any]]] = {
        "decisions": [],
        "actions": [],
        "transactions": [],
        "events": [],
    }
    for expected_index, envelope in enumerate(transaction_envelopes, start=1):
        context = envelope.get("context")
        if not isinstance(context, dict):
            raise TypeError("transaction envelope context must be an object")
        transaction = context.get("authority_transaction")
        if not isinstance(transaction, dict):
            raise TypeError("transaction envelope is missing authority_transaction")
        if transaction.get("transaction_id") != f"transaction_{expected_index:08d}":
            raise ValueError("transaction IDs are not stable and monotonic")
        previous = state
        state = apply_transaction_record(state, transaction)
        assert_transition(previous, state)
        authority_records["transactions"].append(transaction)

    for envelope in _read_jsonl(source_run / "decisions.jsonl"):
        context = envelope.get("context")
        if not isinstance(context, dict) or not isinstance(context.get("decision"), dict):
            raise TypeError("decision envelope is missing authority projection")
        authority_records["decisions"].append(context["decision"])
    for envelope in _read_jsonl(source_run / "actions.jsonl"):
        context = envelope.get("context")
        if not isinstance(context, dict) or not isinstance(context.get("action"), dict):
            raise TypeError("action envelope is missing authority projection")
        authority_records["actions"].append(context["action"])

    event_envelopes = _read_jsonl(source_run / "events.jsonl")
    events = []
    for envelope in event_envelopes:
        context = envelope.get("context")
        if not isinstance(context, dict):
            raise TypeError("event envelope context must be an object")
        event_projection = context["world_event"]
        if not isinstance(event_projection, dict):
            raise TypeError("world_event authority projection must be an object")
        authority_records["events"].append(event_projection)
        events.append(WorldEvent.model_validate(event_projection))
    active_agent_id = str(source_summary["active_agent_id"])
    assert_world_invariants(state, active_agent_id=active_agent_id, events=events)

    actual_authority_log_hash = authority_log_hash(authority_records)
    expected_hash = str(source_summary["final_state_hash"])
    actual_hash = state_hash(state)
    match = (
        actual_hash == expected_hash
        and actual_authority_log_hash == source_summary["authority_log_hash"]
        and state.model_dump(mode="json", exclude_none=False) == _read_json(source_run / "final_snapshot.json")
    )

    root = output_root or source_run.parent
    destination = make_run_path(root, mode="replay", seed=int(source_summary["seed"]))
    resolved_destination = destination.resolve()
    if resolved_destination == source_run or source_run in resolved_destination.parents:
        raise ValueError("replay output must be a sibling of, not inside, the source run")
    destination.mkdir(parents=True)
    shutil.copytree(source_run / "config_snapshot", destination / "config_snapshot")
    for filename in (
        "initial_snapshot.json",
        "decisions.jsonl",
        "actions.jsonl",
        "transactions.jsonl",
        "events.jsonl",
    ):
        shutil.copy2(source_run / filename, destination / filename)
    (destination / "final_snapshot.json").write_text(
        json.dumps(state.model_dump(mode="json", exclude_none=False), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    replay_summary = {
        "schema": RUN_SCHEMA,
        "project": "Small Town World Model（STWM）",
        "source_run": str(source_run),
        "source_run_id": source_summary["run_id"],
        "replay_output_path": str(destination.resolve()),
        "transaction_count": len(transaction_envelopes),
        "initial_state_hash": state_hash(initial_state),
        "expected_final_hash": expected_hash,
        "actual_final_hash": actual_hash,
        "expected_authority_log_hash": source_summary["authority_log_hash"],
        "actual_authority_log_hash": actual_authority_log_hash,
        "match": match,
        "invariants": {"passed": True, "violations": []},
    }
    (destination / "summary.json").write_text(
        json.dumps(replay_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    replay_metadata = {
        "schema": RUN_SCHEMA,
        "project": "Small Town World Model（STWM）",
        "run_id": destination.name,
        "mode": "REPLAY",
        "status": "COMPLETED" if match else "FAILED",
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_run_id": metadata["run_id"],
        "source_run_path": str(source_run),
        "final_state_hash": actual_hash,
        "authority_log_hash": actual_authority_log_hash,
    }
    (destination / "metadata.json").write_text(
        json.dumps(replay_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_digests_after = {name: _file_digest(source_run / name) for name in required}
    if source_digests_after != source_digests_before:
        raise RuntimeError("replay mutated its source run")
    return replay_summary
