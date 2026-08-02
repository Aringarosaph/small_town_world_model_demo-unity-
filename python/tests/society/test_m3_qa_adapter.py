from __future__ import annotations

import json
from pathlib import Path

import pytest
from town_core.bridge.m3_registry import M3FullAssetRegistryValidator
from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.cli import main as cli_main
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.m3_qa_adapter import EVIDENCE_SCHEMA, _ensure_external, _registry_payload

ROOT = Path(__file__).resolve().parents[3]


def test_m3_simulation_evidence_does_not_claim_the_qa_integration_schema() -> None:
    assert EVIDENCE_SCHEMA == "stwm.simulation.m3-readiness-evidence/v1"
    assert EVIDENCE_SCHEMA != "stwm.qa.m3-readiness/v1"


def test_m3_readiness_output_must_be_external() -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        _ensure_external(ROOT / "runs", ROOT / "runs" / "m3-readiness.json")


def test_m3_readiness_registry_probe_uses_shared_manifest() -> None:
    catalog = load_catalog(ROOT / "config" / "v0")
    m3_catalogs = load_m3_catalogs(ROOT / "config" / "v0", catalog=catalog)
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)

    result = M3FullAssetRegistryValidator(catalog, m3_catalogs, checkpoint.world).validate(
        _registry_payload(catalog, m3_catalogs)
    )

    assert result.accepted
    assert len(m3_catalogs.semantic_instances.objects) == 74


def test_m3_cli_invalid_run_is_machine_readable_and_nonzero(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    exit_code = cli_main(
        (
            "run-society",
            "--config",
            str(ROOT / "config" / "v0"),
            "--days",
            "0",
            "--out",
            str(tmp_path / "invalid"),
        )
    )
    document = json.loads(capsys.readouterr().out)

    assert exit_code != 0
    assert document["completed"] is False
    assert document["error_type"] == "ValueError"
