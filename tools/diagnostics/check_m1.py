"""Black-box M1 acceptance diagnostics for Small Town World Model（STWM）.

The checker consumes evidence emitted by the simulation-owned QA adapter.  It
does not import or reproduce simulation rules.  Before the M1 runtime lands it
reports one explicit PENDING finding; once any SIM runtime package is present,
an absent/broken adapter or invalid evidence is a hard failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final, cast

REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_IMPORT_ROOT, REPOSITORY_IMPORT_ROOT / "python"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from town_core.catalogs import CatalogValidationError, load_catalog

from tools.diagnostics.check_m0 import Status as M0Status
from tools.diagnostics.check_m0 import check_sensitive_files, find_repository_root


class Status(StrEnum):
    PASS = "PASS"
    PENDING = "PENDING"
    FAIL = "FAIL"


class Owner(StrEnum):
    QA = "QA"
    SIM = "SIM"
    ORCHESTRATOR = "ORCHESTRATOR"


@dataclass(frozen=True)
class Finding:
    check: str
    status: Status
    code: str
    message: str
    owner: Owner
    path: str | None = None
    remediation: str | None = None


class EvidenceError(ValueError):
    """Raised for a malformed simulation evidence document."""


PROJECT_NAME: Final = "Small Town World Model（STWM）"
EVIDENCE_SCHEMA: Final = "stwm.qa.m1-evidence/v1"
REPORT_SCHEMA: Final = "stwm.qa.m1-diagnostics/v1"
DEFAULT_SEED: Final = 12345
DEFAULT_DAYS: Final = 3
EXPECTED_MINUTES: Final = 4320
ACTIVE_AGENT: Final = "npc_01"
NEED_NAMES: Final = ("hunger", "energy", "hygiene", "fun", "social")
BEHAVIOR_IDS: Final = ("idle", "sleep", "eat_at_home", "work_shift")
RUN_MATRIX: Final[dict[str, int]] = {
    "baseline": 1,
    "repeat": 1,
    "chunk_7": 7,
    "chunk_60": 60,
}
REQUIRED_RUN_FILES: Final = (
    "metadata.json",
    "initial_snapshot.json",
    "decisions.jsonl",
    "actions.jsonl",
    "transactions.jsonl",
    "events.jsonl",
    "final_snapshot.json",
    "summary.json",
)
REQUIRED_RUN_DIRECTORIES: Final = ("config_snapshot",)
INVARIANT_KEYS: Final = (
    "needs_in_range",
    "mood_in_range",
    "resources_nonnegative",
    "single_primary_action",
    "exclusive_slots",
    "action_lifecycle_valid",
    "state_versions_monotonic",
    "record_ids_monotonic",
    "event_ledger_append_only",
    "complete_decision_trace",
    "wages_exactly_once",
)
NEGATIVE_PROBES: Final = (
    "stale_state_version",
    "negative_money",
    "negative_food",
    "needs_out_of_range",
    "overlapping_primary_action",
    "event_mutation",
)
SIM_RUNTIME_PATHS: Final = (
    "python/town_core/simulation",
    "python/town_core/decision",
    "python/town_core/events",
    "python/town_core/replay",
)
SIM_ADAPTER_PATH: Final = "python/town_core/simulation/qa_adapter.py"
DEFAULT_ADAPTER: Final = (
    sys.executable,
    "-m",
    "town_core.simulation.qa_adapter",
)
HASH_PATTERN: Final = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be an array")
    return cast(list[object], value)


def _string(mapping: Mapping[str, object], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label}.{key} must be a non-empty string")
    return value


def _integer(mapping: Mapping[str, object], key: str, label: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvidenceError(f"{label}.{key} must be an integer")
    return value


def _number(mapping: Mapping[str, object], key: str, label: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise EvidenceError(f"{label}.{key} must be numeric")
    return float(value)


def _boolean(mapping: Mapping[str, object], key: str, label: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise EvidenceError(f"{label}.{key} must be boolean")
    return value


def _string_set(value: object, label: str) -> set[str]:
    items = _sequence(value, label)
    if not all(isinstance(item, str) and item for item in items):
        raise EvidenceError(f"{label} must contain only non-empty strings")
    return set(cast(Sequence[str], items))


def _hash(mapping: Mapping[str, object], key: str, label: str) -> str:
    value = _string(mapping, key, label)
    if HASH_PATTERN.fullmatch(value) is None:
        raise EvidenceError(f"{label}.{key} must be a SHA-256 digest")
    return value.removeprefix("sha256:")


def _add_result(
    findings: list[Finding],
    *,
    check: str,
    code: str,
    ok: bool,
    success: str,
    failure: str,
    owner: Owner = Owner.SIM,
    path: str | None = None,
    remediation: str | None = None,
) -> None:
    findings.append(
        Finding(
            check=check,
            status=Status.PASS if ok else Status.FAIL,
            code=code,
            message=success if ok else failure,
            owner=owner,
            path=path,
            remediation=None if ok else remediation,
        )
    )


def _resolve_artifact_directory(evidence_root: Path, value: str, label: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise EvidenceError(f"{label} must be relative to the evidence root")
    path = (evidence_root / relative).resolve()
    try:
        path.relative_to(evidence_root.resolve())
    except ValueError as exc:
        raise EvidenceError(f"{label} escapes the evidence root") from exc
    return path


def _validate_artifacts(
    runs: Mapping[str, Mapping[str, object]], evidence_root: Path, repository_root: Path
) -> tuple[bool, str]:
    errors: list[str] = []
    for label, run in runs.items():
        try:
            run_directory = _resolve_artifact_directory(
                evidence_root,
                _string(run, "run_directory", f"runs.{label}"),
                f"runs.{label}.run_directory",
            )
        except EvidenceError as exc:
            errors.append(str(exc))
            continue
        try:
            run_directory.relative_to(repository_root.resolve())
        except ValueError:
            pass
        else:
            errors.append(f"runs.{label}.run_directory must not be inside the repository")
        if not run_directory.is_dir():
            errors.append(f"runs.{label}.run_directory does not exist: {run_directory}")
            continue
        for name in REQUIRED_RUN_FILES:
            if not (run_directory / name).is_file():
                errors.append(f"runs.{label} is missing {name}")
        for name in REQUIRED_RUN_DIRECTORIES:
            if not (run_directory / name).is_dir():
                errors.append(f"runs.{label} is missing {name}/")
    return not errors, "; ".join(errors)


def _validate_scenario(document: Mapping[str, object]) -> tuple[bool, str]:
    scenario = _mapping(document.get("scenario"), "scenario")
    errors: list[str] = []
    expected_scalars: tuple[tuple[str, object], ...] = (
        ("agent_id", ACTIVE_AGENT),
        ("seed", DEFAULT_SEED),
        ("days", DEFAULT_DAYS),
        ("start_minute", 0),
        ("end_minute", EXPECTED_MINUTES),
    )
    for key, expected in expected_scalars:
        if scenario.get(key) != expected:
            errors.append(f"scenario.{key}={scenario.get(key)!r}, expected {expected!r}")
    if _string_set(scenario.get("allowed_behavior_ids"), "scenario.allowed_behavior_ids") != set(BEHAVIOR_IDS):
        errors.append("scenario.allowed_behavior_ids must be the exact M1 four-behavior allowlist")
    chunks = _sequence(scenario.get("chunk_minutes"), "scenario.chunk_minutes")
    if chunks != [1, 7, 60]:
        errors.append("scenario.chunk_minutes must be [1, 7, 60]")
    return not errors, "; ".join(errors)


def _index_runs(document: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for index, raw_run in enumerate(_sequence(document.get("runs"), "runs")):
        run = _mapping(raw_run, f"runs[{index}]")
        label = _string(run, "label", f"runs[{index}]")
        if label in indexed:
            raise EvidenceError(f"duplicate run label: {label}")
        indexed[label] = run
    if set(indexed) != set(RUN_MATRIX):
        raise EvidenceError(f"run labels must be exactly {sorted(RUN_MATRIX)}")
    return indexed


def _validate_run_matrix(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    errors: list[str] = []
    for label, expected_chunk in RUN_MATRIX.items():
        run = runs[label]
        expected: tuple[tuple[str, object], ...] = (
            ("seed", DEFAULT_SEED),
            ("chunk_minutes", expected_chunk),
            ("start_minute", 0),
            ("end_minute", EXPECTED_MINUTES),
            ("tick_count", EXPECTED_MINUTES),
            ("active_agent_ids", [ACTIVE_AGENT]),
            ("inactive_actor_activity_count", 0),
        )
        for key, value in expected:
            if run.get(key) != value:
                errors.append(f"runs.{label}.{key}={run.get(key)!r}, expected {value!r}")
        for key in ("action_count", "decision_count", "event_count", "committed_transaction_count"):
            if _integer(run, key, f"runs.{label}") <= 0:
                errors.append(f"runs.{label}.{key} must be positive")
    return not errors, "; ".join(errors)


def _validate_clock_and_versions(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    errors: list[str] = []
    for label, run in runs.items():
        if _integer(run, "skipped_tick_count", f"runs.{label}") != 0:
            errors.append(f"runs.{label} skipped authority ticks")
        if _integer(run, "duplicated_tick_count", f"runs.{label}") != 0:
            errors.append(f"runs.{label} duplicated authority ticks")
        start = _integer(run, "state_version_start", f"runs.{label}")
        end = _integer(run, "state_version_end", f"runs.{label}")
        if start < 0 or end <= start:
            errors.append(f"runs.{label} has invalid authority version bounds {start}->{end}")
    return not errors, "; ".join(errors)


def _validate_invariants(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    errors: list[str] = []
    for label, run in runs.items():
        invariants = _mapping(run.get("invariants"), f"runs.{label}.invariants")
        missing = set(INVARIANT_KEYS) - set(invariants)
        if missing:
            errors.append(f"runs.{label}.invariants missing {sorted(missing)}")
        for key in INVARIANT_KEYS:
            if key in invariants and not _boolean(invariants, key, f"runs.{label}.invariants"):
                errors.append(f"runs.{label}.invariants.{key} is false")
        if _integer(run, "illegal_state_count", f"runs.{label}") != 0:
            errors.append(f"runs.{label} reports illegal authority states")
    return not errors, "; ".join(errors)


def _validate_needs(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    errors: list[str] = []
    for label, run in runs.items():
        extrema = _mapping(run.get("need_extrema"), f"runs.{label}.need_extrema")
        observations = _mapping(run.get("need_decay_observations"), f"runs.{label}.need_decay_observations")
        if set(extrema) != set(NEED_NAMES):
            errors.append(f"runs.{label}.need_extrema must contain exactly the five needs")
        if set(observations) != set(NEED_NAMES):
            errors.append(f"runs.{label}.need_decay_observations must contain exactly the five needs")
        for need in NEED_NAMES:
            if need not in extrema or need not in observations:
                continue
            bounds = _mapping(extrema[need], f"runs.{label}.need_extrema.{need}")
            minimum = _number(bounds, "min", f"runs.{label}.need_extrema.{need}")
            maximum = _number(bounds, "max", f"runs.{label}.need_extrema.{need}")
            if not 0.0 <= minimum <= maximum <= 1.0:
                errors.append(f"runs.{label}.{need} extrema are outside [0, 1]")
            decay = _mapping(observations[need], f"runs.{label}.need_decay_observations.{need}")
            before = _number(decay, "before", f"runs.{label}.need_decay_observations.{need}")
            after = _number(decay, "after", f"runs.{label}.need_decay_observations.{need}")
            elapsed = _integer(decay, "elapsed_minutes", f"runs.{label}.need_decay_observations.{need}")
            effect_applied = _boolean(decay, "behavior_effect_applied", f"runs.{label}.need_decay_observations.{need}")
            if not (0.0 <= after < before <= 1.0 and elapsed > 0 and not effect_applied):
                errors.append(f"runs.{label}.{need} lacks an isolated negative decay observation")
    return not errors, "; ".join(errors)


def _validate_behaviors(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    errors: list[str] = []
    for label, run in runs.items():
        counts = _mapping(run.get("behavior_counts"), f"runs.{label}.behavior_counts")
        if set(counts) != set(BEHAVIOR_IDS):
            errors.append(f"runs.{label}.behavior_counts is not the exact M1 allowlist")
            continue
        for behavior_id in BEHAVIOR_IDS:
            count = counts[behavior_id]
            if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                errors.append(f"runs.{label}.behavior_counts.{behavior_id} must be positive")
    return not errors, "; ".join(errors)


def _validate_determinism(runs: Mapping[str, Mapping[str, object]]) -> tuple[bool, str]:
    initial_hashes = {_hash(run, "initial_state_hash", f"runs.{label}") for label, run in runs.items()}
    state_hashes = {_hash(run, "final_state_hash", f"runs.{label}") for label, run in runs.items()}
    log_hashes = {_hash(run, "authority_log_hash", f"runs.{label}") for label, run in runs.items()}
    ok = len(initial_hashes) == 1 and len(state_hashes) == 1 and len(log_hashes) == 1
    return ok, "same-seed or chunked runs produced different initial/final state or ordered-log hashes"


def _validate_replay(runs: Mapping[str, Mapping[str, object]], evidence_root: Path) -> tuple[bool, str]:
    baseline = runs["baseline"]
    replay = _mapping(baseline.get("replay"), "runs.baseline.replay")
    errors: list[str] = []
    expected_hash = _hash(replay, "expected_final_state_hash", "runs.baseline.replay")
    actual_hash = _hash(replay, "actual_final_state_hash", "runs.baseline.replay")
    if expected_hash != actual_hash or expected_hash != _hash(baseline, "final_state_hash", "runs.baseline"):
        errors.append("replay final hash does not match the recorded baseline hash")
    if not _boolean(replay, "match", "runs.baseline.replay"):
        errors.append("replay match flag is false")
    if _integer(replay, "transaction_count", "runs.baseline.replay") != _integer(
        baseline, "committed_transaction_count", "runs.baseline"
    ):
        errors.append("replay transaction count differs from the baseline commit count")
    before = _hash(replay, "source_tree_hash_before", "runs.baseline.replay")
    after = _hash(replay, "source_tree_hash_after", "runs.baseline.replay")
    if before != after:
        errors.append("replay mutated the source run")
    source_directory = _resolve_artifact_directory(
        evidence_root,
        _string(baseline, "run_directory", "runs.baseline"),
        "runs.baseline.run_directory",
    )
    replay_directory = _resolve_artifact_directory(
        evidence_root,
        _string(replay, "output_directory", "runs.baseline.replay"),
        "runs.baseline.replay.output_directory",
    )
    if source_directory == replay_directory or source_directory in replay_directory.parents:
        errors.append("replay output must be a sibling run, not the source or its descendant")
    if not replay_directory.is_dir():
        errors.append(f"replay output directory does not exist: {replay_directory}")
    else:
        for name in REQUIRED_RUN_FILES:
            if not (replay_directory / name).is_file():
                errors.append(f"replay output is missing {name}")
        for name in REQUIRED_RUN_DIRECTORIES:
            if not (replay_directory / name).is_dir():
                errors.append(f"replay output is missing {name}/")
    return not errors, "; ".join(errors)


def _validate_work(document: Mapping[str, object], fixed_shift_wage: int) -> tuple[bool, str]:
    probes = _mapping(document.get("work_probes"), "work_probes")
    errors: list[str] = []
    if set(probes) != {"completed", "late", "missed"}:
        errors.append("work_probes must contain completed, late, and missed")
        return False, "; ".join(errors)
    expected: dict[str, tuple[str, bool, int]] = {
        "completed": ("WORK_COMPLETED", True, 1),
        "late": ("WORK_LATE", True, 1),
        "missed": ("WORK_MISSED", False, 0),
    }
    for name, (event_type, completed, wage_count) in expected.items():
        probe = _mapping(probes[name], f"work_probes.{name}")
        if _string(probe, "event_type", f"work_probes.{name}") != event_type:
            errors.append(f"work_probes.{name} lacks {event_type}")
        if _boolean(probe, "completed", f"work_probes.{name}") is not completed:
            errors.append(f"work_probes.{name}.completed is incorrect")
        if _integer(probe, "wage_settlement_count", f"work_probes.{name}") != wage_count:
            errors.append(f"work_probes.{name} has an invalid wage settlement count")
        amount = _integer(probe, "wage_amount", f"work_probes.{name}")
        expected_amount = fixed_shift_wage if wage_count else 0
        if amount != expected_amount:
            errors.append(f"work_probes.{name}.wage_amount={amount}, expected {expected_amount}")
        if wage_count and not _boolean(probe, "wage_after_completion", f"work_probes.{name}"):
            errors.append(f"work_probes.{name} settled a wage before completion")
    return not errors, "; ".join(errors)


def _validate_negative_probes(document: Mapping[str, object]) -> tuple[bool, str]:
    indexed: dict[str, Mapping[str, object]] = {}
    for index, raw_probe in enumerate(_sequence(document.get("negative_probes"), "negative_probes")):
        probe = _mapping(raw_probe, f"negative_probes[{index}]")
        name = _string(probe, "name", f"negative_probes[{index}]")
        if name in indexed:
            raise EvidenceError(f"duplicate negative probe: {name}")
        indexed[name] = probe
    errors: list[str] = []
    if set(indexed) != set(NEGATIVE_PROBES):
        errors.append(f"negative probes must be exactly {sorted(NEGATIVE_PROBES)}")
        return False, "; ".join(errors)
    for name, probe in indexed.items():
        if _boolean(probe, "accepted", f"negative_probes.{name}"):
            errors.append(f"negative_probes.{name} was accepted")
        _string(probe, "rejection_code", f"negative_probes.{name}")
        if _hash(probe, "state_hash_before", f"negative_probes.{name}") != _hash(
            probe, "state_hash_after", f"negative_probes.{name}"
        ):
            errors.append(f"negative_probes.{name} mutated authority state")
        if name == "event_mutation" and _hash(probe, "ledger_hash_before", f"negative_probes.{name}") != _hash(
            probe, "ledger_hash_after", f"negative_probes.{name}"
        ):
            errors.append("negative_probes.event_mutation changed the append-only ledger")
    return not errors, "; ".join(errors)


def _validate_cli_contract(document: Mapping[str, object]) -> tuple[bool, str]:
    cli = _mapping(document.get("cli_contract"), "cli_contract")
    errors: list[str] = []
    if _integer(cli, "run_headless_exit_code", "cli_contract") != 0:
        errors.append("run-headless returned non-zero")
    if _integer(cli, "replay_exit_code", "cli_contract") != 0:
        errors.append("replay returned non-zero")
    for key in ("run_headless_summary_machine_readable", "replay_summary_machine_readable", "invalid_input_nonzero"):
        if not _boolean(cli, key, "cli_contract"):
            errors.append(f"cli_contract.{key} is false")
    return not errors, "; ".join(errors)


def validate_evidence(evidence_path: Path, repository_root: Path) -> list[Finding]:
    """Validate one SIM-produced M1 evidence document and referenced run trees."""
    try:
        raw: object = json.loads(evidence_path.read_text(encoding="utf-8"))
        document = _mapping(raw, "evidence")
        if document.get("schema") != EVIDENCE_SCHEMA:
            raise EvidenceError(f"evidence.schema must be {EVIDENCE_SCHEMA!r}")
        if document.get("project_name") != PROJECT_NAME:
            raise EvidenceError(f"evidence.project_name must be {PROJECT_NAME!r}")
        scenario_ok, scenario_error = _validate_scenario(document)
        runs = _index_runs(document)
        catalog = load_catalog(repository_root / "config/v0")
        validators: tuple[tuple[str, str, tuple[bool, str]], ...] = (
            ("m1.scenario", "M1_SCENARIO", (scenario_ok, scenario_error)),
            ("m1.run_matrix", "M1_RUN_MATRIX", _validate_run_matrix(runs)),
            ("m1.artifacts", "M1_RUN_ARTIFACTS", _validate_artifacts(runs, evidence_path.parent, repository_root)),
            ("m1.clock", "M1_CLOCK_AND_VERSIONS", _validate_clock_and_versions(runs)),
            ("m1.invariants", "M1_RUNTIME_INVARIANTS", _validate_invariants(runs)),
            ("m1.needs", "M1_NEEDS", _validate_needs(runs)),
            ("m1.behaviors", "M1_BEHAVIORS", _validate_behaviors(runs)),
            ("m1.determinism", "M1_DETERMINISM", _validate_determinism(runs)),
            ("m1.replay", "M1_REPLAY", _validate_replay(runs, evidence_path.parent)),
            ("m1.work", "M1_WORK_AND_WAGES", _validate_work(document, catalog.economy.fixed_shift_wage)),
            ("m1.rejections", "M1_INVALID_STATE_REJECTIONS", _validate_negative_probes(document)),
            ("m1.cli", "M1_CLI_CONTRACT", _validate_cli_contract(document)),
        )
    except (OSError, json.JSONDecodeError, EvidenceError, CatalogValidationError, KeyError) as exc:
        return [
            Finding(
                check="m1.evidence",
                status=Status.FAIL,
                code="M1_EVIDENCE_INVALID",
                message=str(exc),
                owner=Owner.SIM,
                path=evidence_path.as_posix(),
                remediation="Regenerate evidence through the SIM-owned M1 QA adapter; do not hand-edit it.",
            )
        ]

    findings: list[Finding] = []
    _add_result(
        findings,
        check="m1.evidence",
        code="M1_EVIDENCE_SCHEMA",
        ok=True,
        success=f"accepted {EVIDENCE_SCHEMA} for {PROJECT_NAME}",
        failure="unreachable",
        path=evidence_path.as_posix(),
    )
    for check, code, (ok, error) in validators:
        _add_result(
            findings,
            check=check,
            code=code,
            ok=ok,
            success=f"{check} evidence satisfies the M1 gate",
            failure=error,
            path=evidence_path.as_posix(),
            remediation="Fix the authority runtime or SIM evidence adapter, then regenerate the M1 evidence.",
        )
    return findings


def _sensitive_findings(repository_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    failures = [finding for finding in check_sensitive_files(repository_root) if finding.status is M0Status.FAIL]
    _add_result(
        findings,
        check="m1.sensitive",
        code="M1_SENSITIVE_AND_GENERATED_GUARD",
        ok=not failures,
        success="no tracked sensitive or generated runtime output detected",
        failure="; ".join(f"{item.path}: {item.message}" for item in failures),
        owner=Owner.QA,
        remediation="Remove the tracked secret/generated artifact and rotate any exposed credential.",
    )
    return findings


def _adapter_command(repository_root: Path, output_root: Path, evidence_path: Path) -> list[str]:
    override = os.environ.get("STWM_M1_QA_ADAPTER_CMD")
    command = shlex.split(override) if override else list(DEFAULT_ADAPTER)
    return [
        *command,
        "--config",
        str(repository_root / "config/v0"),
        "--output-root",
        str(output_root),
        "--evidence",
        str(evidence_path),
        "--agent",
        ACTIVE_AGENT,
        "--days",
        str(DEFAULT_DAYS),
        "--seed",
        str(DEFAULT_SEED),
        "--chunk-minutes",
        "1,7,60",
    ]


def _pending_or_missing_sim(repository_root: Path, require_sim: bool) -> list[Finding] | None:
    present = [path for path in SIM_RUNTIME_PATHS if (repository_root / path).is_dir()]
    adapter_present = (repository_root / SIM_ADAPTER_PATH).is_file()
    if not present and not adapter_present:
        status = Status.FAIL if require_sim else Status.PENDING
        return [
            Finding(
                check="m1.adapter",
                status=status,
                code="M1_SIM_NOT_INTEGRATED",
                message="SIM authority runtime is not present on this branch; M1 black-box execution is pending integration.",
                owner=Owner.SIM,
                remediation=(
                    "Integrate AITOWN-SIM and its qa_adapter, or omit --require-sim during parallel branch development."
                ),
            )
        ]
    missing = [path for path in (*SIM_RUNTIME_PATHS, SIM_ADAPTER_PATH) if not (repository_root / path).exists()]
    if missing:
        return [
            Finding(
                check="m1.adapter",
                status=Status.FAIL,
                code="M1_SIM_ADAPTER_INCOMPLETE",
                message=f"partial SIM integration is missing: {', '.join(missing)}",
                owner=Owner.SIM,
                remediation="Complete the SIM runtime packages and the exact M1 QA adapter interface before integration.",
            )
        ]
    return None


def run_checks(
    repository_root: Path,
    *,
    evidence_path: Path | None = None,
    output_root: Path | None = None,
    require_sim: bool = False,
    timeout_seconds: int = 180,
) -> list[Finding]:
    """Run repository guards and validate or generate M1 black-box evidence."""
    findings = _sensitive_findings(repository_root)
    if evidence_path is not None:
        try:
            evidence_path.resolve().relative_to(repository_root.resolve())
        except ValueError:
            pass
        else:
            findings.append(
                Finding(
                    check="m1.evidence",
                    status=Status.FAIL,
                    code="M1_EVIDENCE_INSIDE_REPOSITORY",
                    message="generated M1 evidence must remain outside the repository",
                    owner=Owner.QA,
                    path=evidence_path.as_posix(),
                )
            )
            return findings
        if not evidence_path.is_file():
            findings.append(
                Finding(
                    check="m1.evidence",
                    status=Status.FAIL,
                    code="M1_EVIDENCE_MISSING",
                    message=f"requested evidence file does not exist: {evidence_path}",
                    owner=Owner.SIM,
                )
            )
            return findings
        return [*findings, *validate_evidence(evidence_path, repository_root)]

    unavailable = _pending_or_missing_sim(repository_root, require_sim)
    if unavailable is not None:
        return [*findings, *unavailable]

    if output_root is None:
        raise ValueError("output_root is required when executing the SIM adapter")
    try:
        output_root.resolve().relative_to(repository_root.resolve())
    except ValueError:
        pass
    else:
        findings.append(
            Finding(
                check="m1.artifacts",
                status=Status.FAIL,
                code="M1_OUTPUT_ROOT_INSIDE_REPOSITORY",
                message="M1 output root must be outside the repository",
                owner=Owner.QA,
                path=output_root.as_posix(),
            )
        )
        return findings
    output_root.mkdir(parents=True, exist_ok=True)
    generated_evidence = output_root / "m1_qa_evidence.json"
    try:
        generated_evidence.unlink(missing_ok=True)
    except OSError as exc:
        findings.append(
            Finding(
                check="m1.adapter",
                status=Status.FAIL,
                code="M1_STALE_EVIDENCE_UNREMOVABLE",
                message=f"cannot clear stale generated evidence: {exc}",
                owner=Owner.QA,
                path=generated_evidence.as_posix(),
            )
        )
        return findings
    command = _adapter_command(repository_root, output_root, generated_evidence)
    environment = os.environ.copy()
    python_path = str(repository_root / "python")
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (python_path, environment.get("PYTHONPATH", ""))))
    try:
        completed = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        findings.append(
            Finding(
                check="m1.adapter",
                status=Status.FAIL,
                code="M1_SIM_ADAPTER_EXECUTION_FAILED",
                message=str(exc),
                owner=Owner.SIM,
                remediation="Make the SIM QA adapter executable under Python 3.12 and keep the three-day run within CI limits.",
            )
        )
        return findings
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        findings.append(
            Finding(
                check="m1.adapter",
                status=Status.FAIL,
                code="M1_SIM_ADAPTER_NONZERO",
                message=f"adapter exited {completed.returncode}: {detail}",
                owner=Owner.SIM,
                remediation="Fix the SIM adapter/runtime failure; a present integration may not downgrade to PENDING.",
            )
        )
        return findings
    if not generated_evidence.is_file():
        findings.append(
            Finding(
                check="m1.adapter",
                status=Status.FAIL,
                code="M1_SIM_ADAPTER_NO_EVIDENCE",
                message=f"adapter succeeded without writing {generated_evidence}",
                owner=Owner.SIM,
                remediation="Implement the stwm.qa.m1-evidence/v1 output contract.",
            )
        )
        return findings
    findings.append(
        Finding(
            check="m1.adapter",
            status=Status.PASS,
            code="M1_SIM_ADAPTER_EXECUTED",
            message="SIM-owned adapter produced M1 evidence",
            owner=Owner.SIM,
            path=generated_evidence.as_posix(),
        )
    )
    return [*findings, *validate_evidence(generated_evidence, repository_root)]


def render_text(findings: Sequence[Finding]) -> str:
    lines = []
    for finding in findings:
        suffix = f" [{finding.path}]" if finding.path else ""
        lines.append(f"{finding.status} {finding.code} ({finding.owner}): {finding.message}{suffix}")
        if finding.remediation:
            lines.append(f"  -> {finding.remediation}")
    counts = {status: sum(item.status is status for item in findings) for status in Status}
    lines.append("summary: " + ", ".join(f"{status.value.lower()}={counts[status]}" for status in Status))
    return "\n".join(lines)


def write_json_report(path: Path, findings: Sequence[Finding]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": REPORT_SCHEMA,
        "project_name": PROJECT_NAME,
        "findings": [asdict(finding) for finding in findings],
        "summary": {status.value.lower(): sum(item.status is status for item in findings) for status in Status},
    }
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root (auto-detected by default)")
    parser.add_argument("--evidence", type=Path, help="validate existing SIM evidence instead of executing the adapter")
    parser.add_argument("--output-root", type=Path, help="generated evidence root outside the repository")
    parser.add_argument("--require-sim", action="store_true", help="convert the pre-integration PENDING result to FAIL")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve() if args.root else find_repository_root(Path(__file__))
    evidence = args.evidence.resolve() if args.evidence else None
    output_root = args.output_root.resolve() if args.output_root else None
    if evidence is None and output_root is None:
        output_root = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "stwm-m1-qa"
    findings = run_checks(
        root,
        evidence_path=evidence,
        output_root=output_root,
        require_sim=args.require_sim,
        timeout_seconds=args.timeout_seconds,
    )
    print(render_text(findings))
    if args.json_output:
        write_json_report(args.json_output, findings)
    return 1 if any(finding.status is Status.FAIL for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
