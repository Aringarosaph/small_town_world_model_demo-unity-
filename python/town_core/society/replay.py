"""Authoritative M3 checkpoint-patch replay without policy recomputation."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.simulation.initialization import state_hash
from town_core.society.checkpoint import checkpoint_hash, ledger_hash, load_checkpoint, write_checkpoint
from town_core.society.invariants import assert_society_invariants
from town_core.society.models import M3_RUN_SCHEMA, AuthorityCheckpoint
from town_core.society.run import StreamingAuthorityHasher
from town_core.society.transactions import apply_transaction_record


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path.name}")
    return value


def _read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"expected JSON object at {path.name}:{line_number}")
            yield value


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_society_run(
    source_run: Path,
    *,
    from_checkpoint: Path | None,
) -> tuple[AuthorityCheckpoint, dict[str, object]]:
    required = (
        "metadata.json",
        "config_snapshot/catalog.json",
        "config_snapshot/m3_catalogs.json",
        "initial_checkpoint.json",
        "authority.jsonl",
        "transactions.jsonl",
        "final_checkpoint.json",
        "summary.json",
    )
    missing = [name for name in required if not (source_run / name).is_file()]
    if missing:
        raise FileNotFoundError(f"M3 source run is incomplete: {missing}")
    source_hashes = {name: _file_hash(source_run / name) for name in required}
    source_summary = _read_json(source_run / "summary.json")
    catalog = CatalogBundle.model_validate(_read_json(source_run / "config_snapshot/catalog.json"))
    m3_catalogs = M3Catalogs.model_validate(_read_json(source_run / "config_snapshot/m3_catalogs.json"))

    checkpoint = load_checkpoint(from_checkpoint or source_run / "initial_checkpoint.json")
    replay_start_version = checkpoint.world.state_version
    hasher = StreamingAuthorityHasher(
        initial_hash=checkpoint.authority_log_hash,
        initial_count=checkpoint.authority_record_count,
    )
    checkpoint_by_cursor: dict[int, list[tuple[Path, AuthorityCheckpoint]]] = {}
    if from_checkpoint is None:
        for path in sorted((source_run / "checkpoints").glob("checkpoint_*.json")):
            expected = load_checkpoint(path)
            checkpoint_by_cursor.setdefault(expected.authority_record_count, []).append((path, expected))
    checkpoint_mismatches: list[str] = []
    checked_checkpoint_count = 0

    def check_cursor() -> None:
        nonlocal checked_checkpoint_count
        for path, expected in checkpoint_by_cursor.pop(checkpoint.authority_record_count, []):
            checked_checkpoint_count += 1
            if checkpoint_hash(checkpoint) != checkpoint_hash(expected):
                checkpoint_mismatches.append(path.name)

    check_cursor()
    expected_sequence = checkpoint.authority_record_count
    transactions = 0
    for envelope in _read_jsonl(source_run / "authority.jsonl"):
        sequence = envelope.get("sequence")
        if not isinstance(sequence, int):
            raise TypeError("M3 authority record sequence must be an integer")
        if sequence <= checkpoint.authority_record_count:
            continue
        expected_sequence += 1
        if sequence != expected_sequence:
            raise ValueError("M3 authority record sequence is not stable and contiguous")
        if envelope.get("kind") == "transaction":
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                raise TypeError("M3 transaction authority payload must be an object")
            checkpoint = apply_transaction_record(checkpoint, payload)
            transactions += 1
        hasher.append(envelope)
        checkpoint = checkpoint.model_copy(
            update={
                "authority_record_count": hasher.count,
                "authority_log_hash": hasher.hexdigest,
            }
        )
        check_cursor()

    if checkpoint_by_cursor:
        checkpoint_mismatches.extend(path.name for paths in checkpoint_by_cursor.values() for path, _expected in paths)
    expected_final = load_checkpoint(source_run / "final_checkpoint.json")
    expected_final_checkpoint_hash = str(source_summary["final_checkpoint_hash"])
    expected_final_state_hash = str(source_summary["final_state_hash"])
    expected_ledger_hash = str(source_summary.get("ledger_hash", ledger_hash(expected_final)))
    actual_final_checkpoint_hash = checkpoint_hash(checkpoint)
    actual_final_state_hash = state_hash(checkpoint.world)
    actual_ledger_hash = ledger_hash(checkpoint)
    actual_authority_hash = hasher.hexdigest
    match = (
        checkpoint.model_dump(mode="json", exclude_none=False)
        == expected_final.model_dump(mode="json", exclude_none=False)
        and actual_final_checkpoint_hash == expected_final_checkpoint_hash
        and actual_final_state_hash == expected_final_state_hash
        and actual_ledger_hash == expected_ledger_hash
        and actual_authority_hash == source_summary["authority_log_hash"]
        and not checkpoint_mismatches
    )
    assert_society_invariants(checkpoint, catalog, m3_catalogs)
    after_hashes = {name: _file_hash(source_run / name) for name in required}
    source_mutation_count = sum(source_hashes[name] != after_hashes[name] for name in required)
    if source_mutation_count:
        raise RuntimeError("M3 replay mutated its source run")
    report: dict[str, object] = {
        "replay_start_state_version": replay_start_version,
        "transaction_count": transactions,
        "expected_final_state_hash": expected_final_state_hash,
        "actual_final_state_hash": actual_final_state_hash,
        "expected_final_checkpoint_hash": expected_final_checkpoint_hash,
        "actual_final_checkpoint_hash": actual_final_checkpoint_hash,
        "expected_ledger_hash": expected_ledger_hash,
        "actual_ledger_hash": actual_ledger_hash,
        "expected_authority_log_hash": source_summary["authority_log_hash"],
        "actual_authority_log_hash": actual_authority_hash,
        "checked_checkpoint_count": checked_checkpoint_count,
        "checkpoint_mismatch_count": len(checkpoint_mismatches),
        "checkpoint_mismatches": checkpoint_mismatches,
        "source_run_mutation_count": source_mutation_count,
        "match": match,
        "invariants": {"passed": True, "violations": []},
    }
    return checkpoint, report


def verify_society_run(
    source_run: Path,
    *,
    from_checkpoint: Path | None = None,
) -> dict[str, object]:
    """Verify replay and every persisted checkpoint without copying run data."""

    source_run = source_run.resolve()
    _checkpoint, report = _verify_society_run(source_run, from_checkpoint=from_checkpoint)
    return report


def replay_society_run(
    source_run: Path,
    *,
    output_root: Path | None = None,
    from_checkpoint: Path | None = None,
) -> dict[str, object]:
    source_run = source_run.resolve()
    source_summary = _read_json(source_run / "summary.json")
    checkpoint, verification = _verify_society_run(source_run, from_checkpoint=from_checkpoint)

    root = output_root or source_run.parent
    destination = root / f"m3_replay_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    resolved_destination = destination.resolve()
    if resolved_destination == source_run or source_run in resolved_destination.parents:
        raise ValueError("M3 replay output must be a sibling of, not inside, its source run")
    destination.mkdir(parents=True)
    shutil.copytree(source_run / "config_snapshot", destination / "config_snapshot")
    shutil.copytree(source_run / "checkpoints", destination / "checkpoints")
    for filename in (
        "initial_checkpoint.json",
        "authority.jsonl",
        "decisions.jsonl",
        "actions.jsonl",
        "transactions.jsonl",
        "events.jsonl",
        "dialogues.jsonl",
    ):
        shutil.copy2(source_run / filename, destination / filename)
    write_checkpoint(destination / "final_checkpoint.json", checkpoint)
    replay_summary: dict[str, object] = {
        "schema": M3_RUN_SCHEMA,
        "project_name": "Small Town World Model（STWM）",
        "mode": "M3_AUTHORITY_REPLAY",
        "source_run": str(source_run),
        "source_run_id": source_summary["run_id"],
        "replay_output_path": str(destination.resolve()),
        **verification,
    }
    (destination / "summary.json").write_text(
        json.dumps(replay_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "schema": M3_RUN_SCHEMA,
        "project_name": "Small Town World Model（STWM）",
        "run_id": destination.name,
        "mode": "M3_AUTHORITY_REPLAY",
        "status": "COMPLETED" if verification["match"] else "FAILED",
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_run_id": source_summary["run_id"],
        "final_checkpoint_hash": verification["actual_final_checkpoint_hash"],
        "authority_log_hash": verification["actual_authority_log_hash"],
    }
    (destination / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return replay_summary
