"""Canonical M3 authority checkpoint persistence and hashing."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import signal
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from town_core.domain.state_models import WorldState
from town_core.society.models import M3_CHECKPOINT_SCHEMA, AuthorityCheckpoint

AUTHORITY_LOG_DOMAIN = b"stwm.simulation.m3-authority-log/v1\n"
LEDGER_HASH_DOMAIN = "stwm.simulation.m3-authority-ledger/v1"
_CHILD_RESULT_LIMIT_BYTES = 16_384
_CANONICAL_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)


@dataclass(frozen=True)
class IsolatedCheckpointWriteResult:
    """Auditable result returned by the synchronous checkpoint writer child."""

    peak_rss_bytes: int
    checkpoint_hash: str | None


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_json_utf8_chunks(value: object) -> Iterator[bytes]:
    """Yield the exact canonical JSON bytes without joining the full document."""

    for chunk in _CANONICAL_ENCODER.iterencode(value):
        yield chunk.encode("utf-8")


def canonical_json_utf8_length(value: object) -> int:
    return sum(len(chunk) for chunk in canonical_json_utf8_chunks(value))


def canonical_json_sha256(value: object, *, prefix: bytes = b"") -> str:
    digest = hashlib.sha256(prefix)
    for chunk in canonical_json_utf8_chunks(value):
        digest.update(chunk)
    return digest.hexdigest()


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
    canonical_length = canonical_json_utf8_length(envelope)
    digest = hashlib.sha256()
    digest.update(bytes.fromhex(previous_hash))
    digest.update(canonical_length.to_bytes(8, "big"))
    for chunk in canonical_json_utf8_chunks(envelope):
        digest.update(chunk)
    return digest.hexdigest()


def advance_authority_log_hash_from_canonical_bytes(previous_hash: str, canonical: bytes) -> str:
    """Advance the authority chain from the exact bytes persisted to JSONL."""

    if len(previous_hash) != 64:
        raise ValueError("M3 authority hash cursor must be a SHA-256 hex digest")
    material = bytes.fromhex(previous_hash) + len(canonical).to_bytes(8, "big") + canonical
    return hashlib.sha256(material).hexdigest()


def validate_checkpoint_structure(checkpoint: AuthorityCheckpoint) -> AuthorityCheckpoint:
    """Validate the complete outer checkpoint while retaining frozen model instances.

    Every nested authority record enters the engine as a validated frozen
    ``ContractModel``. Reusing those instances avoids repeatedly serializing
    and rebuilding the entire immutable ledger history. Container shapes,
    scalar cursors, hashes, and newly introduced nested values are still
    validated by the complete ``AuthorityCheckpoint`` schema each tick.
    """

    values = {name: getattr(checkpoint, name) for name in AuthorityCheckpoint.model_fields}
    return AuthorityCheckpoint.model_validate(values)


def checkpoint_hash(checkpoint: AuthorityCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json", exclude_none=False, by_alias=True)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def ledger_hash(checkpoint: AuthorityCheckpoint) -> str:
    """Hash the persistent M3 ledgers independently from mutable world state."""

    projection = {
        "schema": LEDGER_HASH_DOMAIN,
        "events": [item.model_dump(mode="json", exclude_none=False) for item in checkpoint.events],
        "knowledge_records": {
            key: value.model_dump(mode="json", exclude_none=False)
            for key, value in sorted(checkpoint.knowledge_records.items())
        },
        "work_sessions": {
            key: value.model_dump(mode="json", exclude_none=False)
            for key, value in sorted(checkpoint.work_sessions.items())
        },
        "conversations": {
            key: value.model_dump(mode="json", exclude_none=False)
            for key, value in sorted(checkpoint.conversations.items())
        },
        "joint_actions": {
            key: value.model_dump(mode="json", exclude_none=False)
            for key, value in sorted(checkpoint.joint_actions.items())
        },
        "settlement_keys": list(checkpoint.settlement_keys),
    }
    return hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()


def _write_checkpoint_in_process(
    path: Path,
    checkpoint: AuthorityCheckpoint,
    *,
    include_checkpoint_hash: bool,
) -> str | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = checkpoint.model_dump(mode="json", exclude_none=False, by_alias=True)
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest() if include_checkpoint_hash else None
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(
            payload,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")
    temporary.replace(path)
    return digest


def write_checkpoint(path: Path, checkpoint: AuthorityCheckpoint) -> None:
    """Write a complete validated checkpoint using an atomic sibling replace."""

    _write_checkpoint_in_process(path, checkpoint, include_checkpoint_hash=False)


def _current_process_peak_rss_bytes() -> int:
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw_rss if platform.system() == "Darwin" else raw_rss * 1024)


def _write_all(file_descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(file_descriptor, payload[offset:])


def _waitpid(child_pid: int) -> int:
    while True:
        try:
            waited_pid, status = os.waitpid(child_pid, 0)
        except InterruptedError:
            continue
        if waited_pid != child_pid:
            raise RuntimeError("waitpid returned an unexpected M3 checkpoint writer pid")
        return status


def _terminate_checkpoint_writer(child_pid: int) -> None:
    try:
        os.kill(child_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        _waitpid(child_pid)
    except ChildProcessError:
        pass


def _cleanup_checkpoint_temporary(path: Path) -> None:
    path.with_name(f".{path.name}.tmp").unlink(missing_ok=True)


def _decode_child_result(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise RuntimeError("M3 checkpoint writer child returned no result")
    if len(payload) > _CHILD_RESULT_LIMIT_BYTES:
        raise RuntimeError("M3 checkpoint writer child result exceeded its bounded protocol")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("M3 checkpoint writer child returned malformed JSON") from exc
    if not isinstance(decoded, dict):
        raise TypeError("M3 checkpoint writer child result must be an object")
    return decoded


def write_checkpoint_isolated(
    path: Path,
    checkpoint: AuthorityCheckpoint,
    *,
    include_checkpoint_hash: bool = False,
) -> IsolatedCheckpointWriteResult:
    """Persist one checkpoint in a synchronous, allocator-isolated child.

    The authority thread is required to be the process's only thread. The
    parent blocks until the child atomically replaces the target and reports a
    bounded result. A failed or signalled child cannot advance authority and
    leaves any previously committed target intact.
    """

    system = platform.system()
    if system not in {"Darwin", "Linux"}:
        raise RuntimeError(f"isolated M3 checkpoint persistence is unsupported on {system}")
    if threading.active_count() != 1:
        raise RuntimeError("isolated M3 checkpoint persistence requires a single-threaded process")
    path.parent.mkdir(parents=True, exist_ok=True)
    read_descriptor, write_descriptor = os.pipe()
    try:
        child_pid = os.fork()
    except BaseException:
        os.close(read_descriptor)
        os.close(write_descriptor)
        raise
    if child_pid == 0:
        os.close(read_descriptor)
        exit_code = 0
        try:
            digest = _write_checkpoint_in_process(
                path,
                checkpoint,
                include_checkpoint_hash=include_checkpoint_hash,
            )
            result: dict[str, object] = {
                "ok": True,
                "peak_rss_bytes": _current_process_peak_rss_bytes(),
                "checkpoint_hash": digest,
            }
        except BaseException as exc:  # noqa: BLE001 - child must never unwind into authority
            exit_code = 1
            result = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:4096],
            }
        try:
            encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            if len(encoded) <= _CHILD_RESULT_LIMIT_BYTES:
                _write_all(write_descriptor, encoded)
            else:
                exit_code = 2
        except (OSError, TypeError, ValueError, UnicodeError):
            exit_code = 2
        finally:
            os.close(write_descriptor)
            os._exit(exit_code)

    os.close(write_descriptor)
    collected = bytearray()
    try:
        while True:
            chunk = os.read(read_descriptor, 4096)
            if not chunk:
                break
            collected.extend(chunk)
            if len(collected) > _CHILD_RESULT_LIMIT_BYTES:
                break
        os.close(read_descriptor)
        read_descriptor = -1
        status = _waitpid(child_pid)
    except BaseException:
        if read_descriptor >= 0:
            os.close(read_descriptor)
        _terminate_checkpoint_writer(child_pid)
        _cleanup_checkpoint_temporary(path)
        raise

    try:
        if os.WIFSIGNALED(status):
            raise RuntimeError(f"M3 checkpoint writer child terminated by signal {os.WTERMSIG(status)}")
        if not os.WIFEXITED(status):
            raise RuntimeError("M3 checkpoint writer child did not exit normally")
        result = _decode_child_result(bytes(collected))
        if os.WEXITSTATUS(status) != 0 or result.get("ok") is not True:
            error_type = str(result.get("error_type", "UnknownError"))
            error = str(result.get("error", "checkpoint writer child failed"))
            raise RuntimeError(f"M3 checkpoint writer child failed: {error_type}: {error}")
        peak_rss_bytes = result.get("peak_rss_bytes")
        reported_digest = result.get("checkpoint_hash")
        if not isinstance(peak_rss_bytes, int) or peak_rss_bytes <= 0:
            raise RuntimeError("M3 checkpoint writer child returned an invalid peak RSS")
        if reported_digest is not None and (not isinstance(reported_digest, str) or len(reported_digest) != 64):
            raise RuntimeError("M3 checkpoint writer child returned an invalid checkpoint hash")
        if include_checkpoint_hash and reported_digest is None:
            raise RuntimeError("M3 checkpoint writer child omitted the requested checkpoint hash")
        if not path.is_file():
            raise RuntimeError("M3 checkpoint writer child did not commit the target")
        return IsolatedCheckpointWriteResult(
            peak_rss_bytes=peak_rss_bytes,
            checkpoint_hash=reported_digest,
        )
    except BaseException:
        _cleanup_checkpoint_temporary(path)
        raise


def load_checkpoint(path: Path) -> AuthorityCheckpoint:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("M3 authority checkpoint must be a JSON object")
    return AuthorityCheckpoint.model_validate(value)


def knowledge_key(agent_id: str, event_id: str) -> str:
    return f"{agent_id}|{event_id}"
