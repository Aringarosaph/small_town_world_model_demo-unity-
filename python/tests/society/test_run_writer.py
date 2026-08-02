from __future__ import annotations

import hashlib
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest
from pydantic import ValidationError
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.checkpoint import (
    advance_authority_log_hash,
    advance_authority_log_hash_from_canonical_bytes,
    canonical_json,
    canonical_json_sha256,
    canonical_json_utf8_chunks,
    canonical_json_utf8_length,
    checkpoint_hash,
    initial_authority_log_hash,
    validate_checkpoint_structure,
)
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.models import AuthorityCheckpoint, SocietyAdvanceResult
from town_core.society.run import AUTHORITY_KIND_FILENAMES, SocietyRunWriter, StreamingAuthorityHasher


def _writer_and_result(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> tuple[SocietyRunWriter, SocietyAdvanceResult]:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    writer = SocietyRunWriter(
        tmp_path / "run",
        catalog=catalog,
        m3_catalogs=m3_catalogs,
        initial=initial,
        days=1,
        chunk_minutes=60,
    )
    return writer, SocietyEngine(catalog, m3_catalogs, initial).advance_to(3)


def test_reference_structure_validation_matches_full_json_normalization(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    initial = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    engine = SocietyEngine(catalog, m3_catalogs, initial)
    committed = engine.advance_to(3)
    candidate = engine.export_checkpoint()
    full = AuthorityCheckpoint.model_validate(candidate.model_dump(mode="json", exclude_none=False))
    retained = validate_checkpoint_structure(candidate)

    assert committed.authority_log_hash == retained.authority_log_hash
    assert retained == full
    assert retained.model_dump(mode="json", exclude_none=False) == full.model_dump(mode="json", exclude_none=False)
    assert checkpoint_hash(retained) == checkpoint_hash(full)


def test_reference_structure_validation_rejects_invalid_outer_cursor(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    invalid = checkpoint.model_copy(update={"authority_record_count": -1})

    with pytest.raises(ValidationError):
        validate_checkpoint_structure(invalid)

    invalid_nested_value = checkpoint.model_copy(update={"events": ["not-a-world-event"]})
    with pytest.raises(ValidationError):
        validate_checkpoint_structure(invalid_nested_value)


def test_precanonicalized_hash_path_is_byte_identical() -> None:
    envelope = {
        "schema": "stwm.simulation.m3-authority-record/v1",
        "sequence": 1,
        "kind": "dialogue",
        "payload": {"visible_text": "今天天气不错。", "nullable": None},
    }
    canonical = canonical_json(envelope).encode("utf-8")
    initial = initial_authority_log_hash()

    assert advance_authority_log_hash_from_canonical_bytes(initial, canonical) == advance_authority_log_hash(
        initial, envelope
    )


def test_writer_streams_each_envelope_in_two_bounded_canonical_passes(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, result = _writer_and_result(tmp_path, catalog, m3_catalogs)
    real_chunks = canonical_json_utf8_chunks
    canonical_passes = 0

    def counted_chunks(value: object) -> Iterator[bytes]:
        nonlocal canonical_passes
        canonical_passes += 1
        yield from real_chunks(value)

    monkeypatch.setattr("town_core.society.run.canonical_json_utf8_chunks", counted_chunks)
    writer.append(result)

    expected_by_kind = {kind: bytearray() for kind in AUTHORITY_KIND_FILENAMES}
    expected_authority = bytearray()
    for sequence, raw_record in enumerate(result.authority_records, start=1):
        kind = str(raw_record["kind"])
        envelope = {
            "schema": "stwm.simulation.m3-authority-record/v1",
            "sequence": sequence,
            "kind": kind,
            "payload": raw_record["payload"],
        }
        line = canonical_json(envelope).encode("utf-8") + b"\n"
        expected_authority.extend(line)
        expected_by_kind[kind].extend(line)

    assert canonical_passes == 2 * len(result.authority_records)
    assert (writer.run_path / "authority.jsonl").read_bytes() == bytes(expected_authority)
    for kind, filename in AUTHORITY_KIND_FILENAMES.items():
        assert (writer.run_path / filename).read_bytes() == bytes(expected_by_kind[kind])
    assert writer.hasher.count == result.authority_record_count
    assert writer.hasher.hexdigest == result.authority_log_hash


def test_canonical_chunk_stream_matches_unicode_and_large_transaction_bytes() -> None:
    envelope: dict[str, object] = {
        "schema": "stwm.simulation.m3-authority-record/v1",
        "sequence": 1,
        "kind": "transaction",
        "payload": {
            "visible_text": "你好，Small Town World Model（STWM） 🌳",
            "known_event_ids": [f"event_{index:08d}" for index in range(5000)],
            "nullable": None,
        },
    }
    expected = canonical_json(envelope).encode("utf-8")
    chunks = list(canonical_json_utf8_chunks(envelope))

    assert len(chunks) > 100
    assert b"".join(chunks) == expected
    assert canonical_json_utf8_length(envelope) == len(expected)
    assert canonical_json_sha256(envelope) == hashlib.sha256(expected).hexdigest()

    authority = BytesIO()
    kind = BytesIO()
    hasher = StreamingAuthorityHasher()
    hasher.append_streamed(envelope, (authority, kind))

    assert authority.getvalue() == expected + b"\n"
    assert kind.getvalue() == expected + b"\n"
    assert hasher.hexdigest == advance_authority_log_hash_from_canonical_bytes(
        initial_authority_log_hash(),
        expected,
    )


class _TrackingStream:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.was_closed = False
        self.content = bytearray()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def write(self, value: bytes) -> int:
        if self.fail:
            raise OSError("targeted append failure")
        self.content.extend(value)
        return len(value)

    def close(self) -> None:
        self.was_closed = True


def test_writer_closes_every_open_stream_when_kind_append_fails(
    tmp_path: Path,
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, result = _writer_and_result(tmp_path, catalog, m3_catalogs)
    streams: list[_TrackingStream] = []

    def fake_open(path: Path, mode: str = "r", *args: object, **kwargs: object) -> _TrackingStream:
        assert mode == "ab"
        stream = _TrackingStream(fail=path.name == "transactions.jsonl")
        streams.append(stream)
        return stream

    monkeypatch.setattr(Path, "open", fake_open)
    with pytest.raises(OSError, match="targeted append failure"):
        writer.append(result)

    assert streams
    assert all(stream.was_closed for stream in streams)
