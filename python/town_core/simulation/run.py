"""Headless execution and structured M1 run evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from town_core.domain.config_models import CatalogBundle
from town_core.domain.state_models import WorldState
from town_core.simulation.engine import AdvanceResult, SimulationEngine
from town_core.simulation.initialization import build_initial_world_state, state_hash
from town_core.simulation.invariants import assert_world_invariants

RUN_SCHEMA = "stwm.simulation.m1-run/v1"
AUTHORITY_LOG_KINDS = ("decisions", "actions", "transactions", "events")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _dump_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
            stream.write("\n")


def authority_log_hash(records: Mapping[str, list[dict[str, Any]]]) -> str:
    """Hash all ordered authority projections while excluding run metadata."""

    projection = {kind: records[kind] for kind in AUTHORITY_LOG_KINDS}
    canonical = json.dumps(projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_envelope(
    *,
    timestamp_utc: str,
    run_id: str,
    event: str,
    component: str,
    message: str,
    correlation_id: str | None,
    state_version: int | None,
    game_minute: int | None,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp_utc": timestamp_utc,
        "level": "INFO",
        "event": event,
        "component": component,
        "run_id": run_id,
        "message": message,
        "correlation_id": correlation_id,
        "state_version": state_version,
        "game_minute": game_minute,
        "context": dict(context),
    }


class RunWriter:
    def __init__(
        self,
        run_path: Path,
        *,
        catalog: CatalogBundle,
        state: WorldState,
        active_agent_id: str,
        days: int,
        chunk_minutes: int,
        source_run_id: str | None = None,
    ) -> None:
        if run_path.exists():
            raise FileExistsError(f"run output already exists: {run_path}")
        run_path.mkdir(parents=True)
        self.run_path = run_path
        self.run_id = run_path.name
        self.started_utc = _utc_now()
        self._authority_records: dict[str, list[dict[str, Any]]] = {kind: [] for kind in AUTHORITY_LOG_KINDS}
        self._decision_count = 0
        self._action_ids: set[str] = set()
        self._event_count = 0
        self._selected_behaviors: Counter[str] = Counter()
        self._event_types: Counter[str] = Counter()
        self._metadata: dict[str, Any] = {
            "schema": RUN_SCHEMA,
            "project": "Small Town World Model（STWM）",
            "run_id": self.run_id,
            "mode": "HEADLESS_FAST" if source_run_id is None else "REPLAY",
            "status": "IN_PROGRESS",
            "started_at_utc": self.started_utc,
            "completed_at_utc": None,
            "world_id": state.world_id,
            "seed": state.random_seed,
            "active_agent_id": active_agent_id,
            "days": days,
            "chunk_minutes": chunk_minutes,
            "config_hash": state.config_hash,
            "schema_version": state.schema_version,
            "protocol_version": catalog.world.protocol_version,
            "feature_version": catalog.model.feature_version,
            "outcome_provider": "M1_CATALOG_BOUNDED_HEURISTIC" if source_run_id is None else None,
            "source_run_id": source_run_id,
        }
        _dump_json(self.run_path / "metadata.json", self._metadata)
        config_snapshot = self.run_path / "config_snapshot"
        config_snapshot.mkdir()
        _dump_json(config_snapshot / "catalog.json", catalog.model_dump(mode="json", exclude_none=False))
        self.write_snapshot("initial_snapshot.json", state)
        for filename in ("decisions.jsonl", "actions.jsonl", "transactions.jsonl", "events.jsonl"):
            (self.run_path / filename).touch()

    @property
    def authority_log_hash(self) -> str:
        return authority_log_hash(self._authority_records)

    def write_snapshot(self, filename: str, state: WorldState) -> None:
        _dump_json(self.run_path / filename, state.model_dump(mode="json", exclude_none=False))

    def append(self, result: AdvanceResult) -> None:
        transaction_records = []
        for transaction in result.transactions:
            self._authority_records["transactions"].append(transaction)
            transaction_records.append(
                _record_envelope(
                    timestamp_utc=self.started_utc,
                    run_id=self.run_id,
                    event="authority_transaction_committed",
                    component="town_core.simulation",
                    message="one game-minute authority transaction committed",
                    correlation_id=str(transaction["transaction_id"]),
                    state_version=int(transaction["committed_state_version"]),
                    game_minute=int(transaction["input_game_minute"]),
                    context={"authority_transaction": transaction},
                )
            )
        _append_jsonl(self.run_path / "transactions.jsonl", transaction_records)

        decision_records = []
        for decision in result.decisions:
            self._decision_count += 1
            self._selected_behaviors[str(decision["selected_behavior_id"])] += 1
            self._authority_records["decisions"].append(decision)
            decision_records.append(
                _record_envelope(
                    timestamp_utc=self.started_utc,
                    run_id=self.run_id,
                    event="decision_committed",
                    component="town_core.decision",
                    message="candidate selected and accepted by central Resolver",
                    correlation_id=str(decision["decision_id"]),
                    state_version=int(decision["committed_state_version"]),
                    game_minute=int(decision["game_minute"]),
                    context={"decision": decision},
                )
            )
        _append_jsonl(self.run_path / "decisions.jsonl", decision_records)

        action_records = []
        for action in result.actions:
            action_id = str(action["action_id"])
            self._action_ids.add(action_id)
            self._authority_records["actions"].append(action)
            action_records.append(
                _record_envelope(
                    timestamp_utc=self.started_utc,
                    run_id=self.run_id,
                    event="action_phase_recorded",
                    component="town_core.simulation",
                    message="authority action lifecycle phase recorded",
                    correlation_id=action_id,
                    state_version=int(action["state_version"]),
                    game_minute=int(action["game_minute"]),
                    context={"action": action},
                )
            )
        _append_jsonl(self.run_path / "actions.jsonl", action_records)

        event_records = []
        for world_event in result.events:
            self._event_count += 1
            self._event_types[world_event.event_type.value] += 1
            event_projection = world_event.model_dump(mode="json", exclude_none=False)
            self._authority_records["events"].append(event_projection)
            event_records.append(
                _record_envelope(
                    timestamp_utc=self.started_utc,
                    run_id=self.run_id,
                    event="world_event_committed",
                    component="town_core.events",
                    message="append-only world event committed",
                    correlation_id=world_event.event_id,
                    state_version=None,
                    game_minute=world_event.game_minute,
                    context={"world_event": event_projection},
                )
            )
        _append_jsonl(self.run_path / "events.jsonl", event_records)

    def finish(self, summary: dict[str, Any], state: WorldState) -> None:
        self.write_snapshot("final_snapshot.json", state)
        _dump_json(self.run_path / "summary.json", summary)
        self._metadata.update(
            {
                "status": "COMPLETED",
                "completed_at_utc": _utc_now(),
                "final_state_hash": summary["final_state_hash"],
                "authority_log_hash": summary["authority_log_hash"],
            }
        )
        _dump_json(self.run_path / "metadata.json", self._metadata)

    def fail(self, error: Exception) -> None:
        self._metadata.update(
            {
                "status": "FAILED",
                "completed_at_utc": _utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        _dump_json(self.run_path / "metadata.json", self._metadata)

    def counts(self) -> dict[str, Any]:
        return {
            "decision_count": self._decision_count,
            "action_count": len(self._action_ids),
            "event_count": self._event_count,
            "selected_behavior_counts": dict(sorted(self._selected_behaviors.items())),
            "event_type_counts": dict(sorted(self._event_types.items())),
        }


def make_run_path(output_root: Path, *, mode: str, seed: int) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    nonce = uuid.uuid4().hex[:8]
    return output_root / f"{timestamp}-{mode}-{seed}-{nonce}"


def run_headless(
    catalog: CatalogBundle,
    *,
    active_agent_id: str,
    days: int,
    seed: int,
    output_root: Path = Path("runs"),
    run_path: Path | None = None,
    chunk_minutes: int = 1,
) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("days must be positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if chunk_minutes <= 0:
        raise ValueError("chunk_minutes must be positive")
    initial_state = build_initial_world_state(catalog, seed=seed, active_agent_id=active_agent_id)
    initial_hash = state_hash(initial_state)
    destination = run_path or make_run_path(output_root, mode="headless", seed=seed)
    writer = RunWriter(
        destination,
        catalog=catalog,
        state=initial_state,
        active_agent_id=active_agent_id,
        days=days,
        chunk_minutes=chunk_minutes,
    )
    engine = SimulationEngine(catalog, initial_state, active_agent_id=active_agent_id)
    end_minute = initial_state.game_minute + (days * 1440)
    try:
        while engine.state.game_minute < end_minute:
            target = min(end_minute, engine.state.game_minute + chunk_minutes)
            writer.append(engine.advance_to(target))
        assert_world_invariants(engine.state, active_agent_id=active_agent_id, events=engine.ledger.events)
        counts = writer.counts()
        summary: dict[str, Any] = {
            "schema": RUN_SCHEMA,
            "project": "Small Town World Model（STWM）",
            "run_id": writer.run_id,
            "run_path": str(writer.run_path.resolve()),
            "start_game_minute": initial_state.game_minute,
            "end_game_minute": engine.state.game_minute,
            "tick_count": engine.state.game_minute - initial_state.game_minute,
            "transaction_count": engine.state.state_version - initial_state.state_version,
            "active_agent_id": active_agent_id,
            "seed": seed,
            "chunk_minutes": chunk_minutes,
            "initial_state_hash": initial_hash,
            "final_state_hash": state_hash(engine.state),
            "authority_log_hash": writer.authority_log_hash,
            "invariants": {"passed": True, "violations": []},
            "work_sessions": list(engine.work_sessions),
            "knowledge_record_count": len(engine.knowledge_records),
            **counts,
        }
        writer.finish(summary, engine.state)
        return summary
    except Exception as exc:
        writer.fail(exc)
        raise
