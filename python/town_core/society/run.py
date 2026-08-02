"""M3 society run writer, checkpoint cadence, and streaming authority hash."""

from __future__ import annotations

import json
import platform
import resource
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from town_core.catalogs import m3_catalog_hash
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.simulation.initialization import state_hash
from town_core.society.checkpoint import (
    advance_authority_log_hash,
    canonical_json,
    checkpoint_hash,
    initial_authority_log_hash,
    ledger_hash,
    write_checkpoint,
)
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import SocietyObjectFixture, build_initial_society_checkpoint
from town_core.society.invariants import assert_society_invariants
from town_core.society.models import M3_RUN_SCHEMA, AuthorityCheckpoint, SocietyAdvanceResult

CHECKPOINT_INTERVAL_MINUTES = 360


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    if not values:
        return
    with path.open("a", encoding="utf-8") as stream:
        for value in values:
            stream.write(canonical_json(value))
            stream.write("\n")


class StreamingAuthorityHasher:
    """Checkpoint-resumable chronological M3 authority hash chain."""

    def __init__(self, *, initial_hash: str | None = None, initial_count: int = 0) -> None:
        if initial_count < 0:
            raise ValueError("M3 authority cursor count cannot be negative")
        self._digest = initial_hash or initial_authority_log_hash()
        self.count = initial_count

    def append(self, record: dict[str, object]) -> None:
        if record.get("sequence") != self.count + 1:
            raise ValueError("M3 authority record sequence does not follow the checkpoint cursor")
        self._digest = advance_authority_log_hash(self._digest, record)
        self.count += 1

    @property
    def hexdigest(self) -> str:
        return self._digest


def authority_log_hash(
    records: list[dict[str, object]],
    *,
    initial_hash: str | None = None,
    initial_count: int = 0,
) -> str:
    hasher = StreamingAuthorityHasher(initial_hash=initial_hash, initial_count=initial_count)
    for record in records:
        hasher.append(record)
    return hasher.hexdigest


class SocietyRunWriter:
    def __init__(
        self,
        run_path: Path,
        *,
        catalog: CatalogBundle,
        m3_catalogs: M3Catalogs,
        initial: AuthorityCheckpoint,
        days: int,
        chunk_minutes: int,
    ) -> None:
        if run_path.exists():
            raise FileExistsError(f"M3 run path already exists: {run_path}")
        run_path.mkdir(parents=True)
        self.run_path = run_path
        self.run_id = run_path.name
        self.started_at_utc = _utc_now()
        self.hasher = StreamingAuthorityHasher(
            initial_hash=initial.authority_log_hash,
            initial_count=initial.authority_record_count,
        )
        self.sequence = initial.authority_record_count
        self.behavior_counts: Counter[str] = Counter()
        self.event_counts: Counter[str] = Counter()
        self.action_ids: set[str] = set()
        self.decision_count = 0
        self._metadata = {
            "schema": M3_RUN_SCHEMA,
            "project_name": "Small Town World Model（STWM）",
            "run_id": self.run_id,
            "mode": "HEADLESS_FAST_M3_SOCIETY",
            "status": "IN_PROGRESS",
            "started_at_utc": self.started_at_utc,
            "seed": initial.world.random_seed,
            "days": days,
            "chunk_minutes": chunk_minutes,
            "catalog_protocol_version": catalog.world.protocol_version,
            "negotiated_protocol_version": None,
            "checkpoint_schema": initial.schema_id,
            "checkpoint_interval_minutes": CHECKPOINT_INTERVAL_MINUTES,
            "config_hash": initial.world.config_hash,
            "m3_catalog_hash": initial.m3_catalog_hash,
            "semantic_profile": m3_catalogs.semantic_instances.profile,
        }
        _write_json(run_path / "metadata.json", self._metadata)
        config_snapshot = run_path / "config_snapshot"
        config_snapshot.mkdir()
        _write_json(config_snapshot / "catalog.json", catalog.model_dump(mode="json", exclude_none=False))
        _write_json(
            config_snapshot / "m3_catalogs.json",
            m3_catalogs.model_dump(mode="json", exclude_none=False, by_alias=True),
        )
        checkpoints = run_path / "checkpoints"
        checkpoints.mkdir()
        write_checkpoint(run_path / "initial_checkpoint.json", initial)
        write_checkpoint(checkpoints / "checkpoint_00000000.json", initial)
        for filename in (
            "authority.jsonl",
            "decisions.jsonl",
            "actions.jsonl",
            "transactions.jsonl",
            "events.jsonl",
            "dialogues.jsonl",
        ):
            (run_path / filename).touch()

    def append(self, result: SocietyAdvanceResult) -> None:
        by_kind: dict[str, list[dict[str, object]]] = {
            "decision": [],
            "action": [],
            "transaction": [],
            "event": [],
            "dialogue": [],
        }
        envelopes: list[dict[str, object]] = []
        for record in result.authority_records:
            kind = str(record["kind"])
            payload = record["payload"]
            if not isinstance(payload, dict):
                raise TypeError("M3 authority record payload must be an object")
            self.sequence += 1
            envelope: dict[str, object] = {
                "schema": "stwm.simulation.m3-authority-record/v1",
                "sequence": self.sequence,
                "kind": kind,
                "payload": payload,
            }
            self.hasher.append(envelope)
            envelopes.append(envelope)
            by_kind[kind].append(envelope)
            if kind == "decision":
                self.decision_count += 1
                self.behavior_counts[str(payload["selected_behavior_id"])] += 1
            elif kind == "action":
                self.action_ids.add(str(payload["action_id"]))
            elif kind == "event":
                self.event_counts[str(payload["event_type"])] += 1
        _append_jsonl(self.run_path / "authority.jsonl", envelopes)
        for kind, records in by_kind.items():
            filename = "dialogues.jsonl" if kind == "dialogue" else f"{kind}s.jsonl"
            _append_jsonl(self.run_path / filename, records)
        if self.hasher.count != result.authority_record_count or self.hasher.hexdigest != result.authority_log_hash:
            raise RuntimeError("M3 writer authority cursor diverged from the production engine")

    def write_periodic_checkpoint(self, checkpoint: AuthorityCheckpoint) -> None:
        write_checkpoint(
            self.run_path / "checkpoints" / f"checkpoint_{checkpoint.world.game_minute:08d}.json",
            checkpoint,
        )

    def finish(self, summary: dict[str, object], checkpoint: AuthorityCheckpoint) -> None:
        write_checkpoint(self.run_path / "final_checkpoint.json", checkpoint)
        self.write_periodic_checkpoint(checkpoint)
        _write_json(self.run_path / "summary.json", summary)
        self._metadata.update(
            {
                "status": "COMPLETED",
                "completed_at_utc": _utc_now(),
                "final_state_hash": summary["final_state_hash"],
                "final_checkpoint_hash": summary["final_checkpoint_hash"],
                "authority_log_hash": summary["authority_log_hash"],
            }
        )
        _write_json(self.run_path / "metadata.json", self._metadata)

    def fail(self, error: Exception) -> None:
        self._metadata.update(
            {
                "status": "FAILED",
                "completed_at_utc": _utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        _write_json(self.run_path / "metadata.json", self._metadata)


def make_society_run_path(output_root: Path, *, seed: int) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return output_root / f"m3_society_seed{seed}_{timestamp}_{uuid.uuid4().hex[:8]}"


def run_society(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    *,
    days: int,
    seed: int,
    output_root: Path = Path("runs"),
    run_path: Path | None = None,
    chunk_minutes: int = 1,
    object_fixture: SocietyObjectFixture | None = None,
    resume_checkpoint: AuthorityCheckpoint | None = None,
) -> dict[str, object]:
    if days <= 0:
        raise ValueError("M3 society days must be positive")
    if seed < 0:
        raise ValueError("M3 society seed must be non-negative")
    if chunk_minutes <= 0:
        raise ValueError("M3 society chunk_minutes must be positive")
    initial = resume_checkpoint or build_initial_society_checkpoint(
        catalog,
        m3_catalogs,
        seed=seed,
        object_fixture=object_fixture,
    )
    if initial.world.random_seed != seed:
        raise ValueError("resume checkpoint seed does not match requested M3 seed")
    destination = run_path or make_society_run_path(output_root, seed=seed)
    writer = SocietyRunWriter(
        destination,
        catalog=catalog,
        m3_catalogs=m3_catalogs,
        initial=initial,
        days=days,
        chunk_minutes=chunk_minutes,
    )
    if initial.m3_catalog_hash != m3_catalog_hash(m3_catalogs):
        raise ValueError("resume checkpoint M3 catalog hash does not match the requested catalogs")
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    start_minute = initial.world.game_minute
    end_minute = catalog.world.initial_game_minute + (days * 1440)
    if start_minute >= end_minute:
        raise ValueError("resume checkpoint is already at or beyond the requested M3 scenario end")
    started = time.perf_counter()
    rss_daily_samples = [
        {"game_day": start_minute // 1440, "game_minute": start_minute, "peak_rss_bytes": _peak_rss_bytes()}
    ]
    try:
        while engine.state.game_minute < end_minute:
            next_checkpoint = (
                (engine.state.game_minute // CHECKPOINT_INTERVAL_MINUTES) + 1
            ) * CHECKPOINT_INTERVAL_MINUTES
            target = min(
                end_minute,
                engine.state.game_minute + chunk_minutes,
                next_checkpoint,
            )
            writer.append(engine.advance_to(target))
            if engine.state.game_minute % CHECKPOINT_INTERVAL_MINUTES == 0:
                writer.write_periodic_checkpoint(engine.export_checkpoint())
            if engine.state.game_minute % 1440 == 0:
                rss_daily_samples.append(
                    {
                        "game_day": engine.state.game_minute // 1440,
                        "game_minute": engine.state.game_minute,
                        "peak_rss_bytes": _peak_rss_bytes(),
                    }
                )
        final = engine.export_checkpoint()
        assert_society_invariants(final, catalog, m3_catalogs)
        wall_seconds = time.perf_counter() - started
        behavior_counts = dict(sorted(writer.behavior_counts.items()))
        event_counts = dict(sorted(writer.event_counts.items()))
        daily_events: Counter[int] = Counter(event.game_minute // 1440 for event in final.events)
        summary: dict[str, object] = {
            "schema": M3_RUN_SCHEMA,
            "project_name": "Small Town World Model（STWM）",
            "run_id": writer.run_id,
            "run_path": str(writer.run_path.resolve()),
            "seed": seed,
            "start_game_minute": start_minute,
            "end_game_minute": final.world.game_minute,
            "tick_count": final.world.game_minute - start_minute,
            "transaction_count": final.counters.transaction - initial.counters.transaction,
            "enabled_agent_ids": sorted(agent.agent_id for agent in final.world.agents.values() if agent.enabled),
            "initial_state_hash": state_hash(initial.world),
            "final_state_hash": state_hash(final.world),
            "initial_checkpoint_hash": checkpoint_hash(initial),
            "final_checkpoint_hash": checkpoint_hash(final),
            "ledger_hash": ledger_hash(final),
            "transaction_chain_hash": final.transaction_chain_hash,
            "m3_catalog_hash": final.m3_catalog_hash,
            "authority_log_hash": writer.hasher.hexdigest,
            "authority_record_count": writer.hasher.count,
            "decision_count": final.counters.decision,
            "action_count": final.counters.action,
            "event_count": len(final.events),
            "selected_behavior_counts": behavior_counts,
            "event_type_counts": event_counts,
            "household_balances": {
                household_id: {
                    "money": household.money,
                    "food_units": household.food_units,
                }
                for household_id, household in sorted(final.world.households.items())
            },
            "work_sessions": len(final.work_sessions),
            "knowledge_records": len(final.knowledge_records),
            "conversation_records": len(final.conversations),
            "active_reservation_count": len(final.reservations),
            "active_joint_action_count": len(final.joint_actions),
            "pathology": {
                "max_events_per_game_day": max(daily_events.values(), default=0),
                "event_daily_counts": {str(day): count for day, count in sorted(daily_events.items())},
                "terminal_reservation_leaks": 0,
                "relationship_boundary_fraction": _relationship_boundary_fraction(final),
            },
            "performance": _performance_document(engine, wall_seconds, rss_daily_samples),
            "invariants": {"passed": True, "violations": []},
        }
        writer.finish(summary, final)
        return summary
    except Exception as exc:
        writer.fail(exc)
        raise


def _relationship_boundary_fraction(checkpoint: AuthorityCheckpoint) -> dict[str, float]:
    axes = ("familiarity", "affinity", "trust", "tension")
    count = max(1, len(checkpoint.world.relationships))
    return {
        axis: round(
            sum(
                1
                for edge in checkpoint.world.relationships
                if float(getattr(edge, axis)) <= 0.01 or float(getattr(edge, axis)) >= 0.99
            )
            / count,
            6,
        )
        for axis in axes
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 6)


def _peak_rss_bytes() -> int:
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    system = platform.system()
    return int(raw_rss if system == "Darwin" else raw_rss * 1024)


def _linear_slope(samples: list[dict[str, int]]) -> float:
    post_warmup = [item for item in samples if item["game_day"] >= 1]
    if len(post_warmup) < 2:
        return 0.0
    xs = [float(item["game_day"]) for item in post_warmup]
    ys = [float(item["peak_rss_bytes"]) for item in post_warmup]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        return 0.0
    return round(max(0.0, sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator), 6)


def _performance_document(
    engine: SocietyEngine,
    wall_seconds: float,
    rss_daily_samples: list[dict[str, int]],
) -> dict[str, object]:
    return {
        "wall_seconds": round(wall_seconds, 6),
        "tick_p99_ms": _percentile(engine.tick_durations_ms, 0.99),
        "decision_batch_p95_ms": _percentile(engine.decision_batch_durations_ms, 0.95),
        "peak_rss_bytes": _peak_rss_bytes(),
        "rss_collection_method": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "rss_daily_samples": rss_daily_samples,
        "post_warmup_rss_slope_bytes_per_game_day": _linear_slope(rss_daily_samples),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
    }
