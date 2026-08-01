from __future__ import annotations

import json
from pathlib import Path

from town_core.domain.schema_artifacts import EXAMPLES, SCHEMA_ADAPTERS, VERSION_DOCUMENT, build_artifacts

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = REPO_ROOT / "protocol"


def test_committed_artifacts_match_generator() -> None:
    schemas, examples = build_artifacts()

    assert json.loads((PROTOCOL_ROOT / "version.json").read_text(encoding="utf-8")) == VERSION_DOCUMENT
    for name, schema in schemas.items():
        committed = json.loads((PROTOCOL_ROOT / "jsonschema" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert committed == schema
    for name, example in examples.items():
        committed = json.loads((PROTOCOL_ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        assert committed == example


def test_all_examples_validate_against_their_models() -> None:
    for name, (adapter, _) in EXAMPLES.items():
        committed = json.loads((PROTOCOL_ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        adapter.validate_python(committed)


def test_all_schema_files_are_objects() -> None:
    for name in SCHEMA_ADAPTERS:
        schema = json.loads((PROTOCOL_ROOT / "jsonschema" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert isinstance(schema, dict)
        assert "$defs" in schema or "oneOf" in schema
