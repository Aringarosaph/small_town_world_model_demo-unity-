"""Canonical M3 authority checkpoint persistence and hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from town_core.domain.state_models import WorldState
from town_core.society.models import M3_CHECKPOINT_SCHEMA, AuthorityCheckpoint

AUTHORITY_LOG_DOMAIN = b"stwm.simulation.m3-authority-log/v1\n"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def initial_transaction_chain_hash(world: WorldState) -> str:
    projection = {
        "schema": M3_CHECKPOINT_SCHEMA,
        "world": world.model_dump(mode="json", exclude_none=False),
    }
    return hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()


def initial_authority_log_hash() -> str:
    """Return the resumable empty-log hash for an M3 authority stream."""

    return hashlib.sha256(AUTHORITY_LOG_DOMAIN).hexdigest()


def advance_authority_log_hash(previous_hash: str, envelope: object) -> str:
    """Append one canonical envelope to a checkpoint-persistable hash chain."""

    if len(previous_hash) != 64:
        raise ValueError("M3 authority hash cursor must be a SHA-256 hex digest")
    canonical = canonical_json(envelope).encode("utf-8")
    material = bytes.fromhex(previous_hash) + len(canonical).to_bytes(8, "big") + canonical
    return hashlib.sha256(material).hexdigest()


def checkpoint_hash(checkpoint: AuthorityCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json", exclude_none=False, by_alias=True)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_checkpoint(path: Path, checkpoint: AuthorityCheckpoint) -> None:
    """Write a complete validated checkpoint using an atomic sibling replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            checkpoint.model_dump(mode="json", exclude_none=False, by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_checkpoint(path: Path) -> AuthorityCheckpoint:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("M3 authority checkpoint must be a JSON object")
    return AuthorityCheckpoint.model_validate(value)


def knowledge_key(agent_id: str, event_id: str) -> str:
    return f"{agent_id}|{event_id}"
