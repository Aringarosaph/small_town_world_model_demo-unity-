"""Authoritative M3 checkpoint-patch replay without policy recomputation."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import checkpoint_hash, load_checkpoint, write_checkpoint
from town_core.society.invariants import assert_society_invariants
from town_core.society.models import M3_RUN_SCHEMA
from town_core.society.run import StreamingAuthorityHasher
from town_core.society.transactions import apply_transaction_record


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected JSON object at {path.name}:{line_number}")
        result.append(value)
    return result


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_society_run(
    source_run: Path,
    *,
    output_root: Path | None = None,
    from_checkpoint: Path | None = None,
) -> dict[str, object]:
    source_run = source_run.resolve()
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

    checkpoint = (
        load_checkpoint(from_checkpoint)
        if from_checkpoint is not None
        else load_checkpoint(source_run / "initial_checkpoint.json")
    )
    replay_start_version = checkpoint.world.state_version
    authority_records = _read_jsonl(source_run / "authority.jsonl")
    hasher = StreamingAuthorityHasher(
        initial_hash=checkpoint.authority_log_hash,
        initial_count=checkpoint.authority_record_count,
    )
    expected_sequence = checkpoint.authority_record_count
    transactions = 0
    for envelope in authority_records:
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

    expected_final = load_checkpoint(source_run / "final_checkpoint.json")
    expected_final_hash = str(source_summary["final_checkpoint_hash"])
    actual_final_hash = checkpoint_hash(checkpoint)
    actual_authority_hash = hasher.hexdigest
    match = (
        checkpoint.model_dump(mode="json", exclude_none=False)
        == expected_final.model_dump(mode="json", exclude_none=False)
        and actual_final_hash == expected_final_hash
        and actual_authority_hash == source_summary["authority_log_hash"]
    )

    assert_society_invariants(checkpoint, catalog, m3_catalogs)

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
        "replay_start_state_version": replay_start_version,
        "transaction_count": transactions,
        "expected_final_checkpoint_hash": expected_final_hash,
        "actual_final_checkpoint_hash": actual_final_hash,
        "expected_authority_log_hash": source_summary["authority_log_hash"],
        "actual_authority_log_hash": actual_authority_hash,
        "match": match,
        "invariants": {"passed": True, "violations": []},
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
        "status": "COMPLETED" if match else "FAILED",
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_run_id": source_summary["run_id"],
        "final_checkpoint_hash": actual_final_hash,
        "authority_log_hash": actual_authority_hash,
    }
    (destination / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    after_hashes = {name: _file_hash(source_run / name) for name in required}
    if after_hashes != source_hashes:
        raise RuntimeError("M3 replay mutated its source run")
    return replay_summary
