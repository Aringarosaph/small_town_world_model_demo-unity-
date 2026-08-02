"""M3 complete heuristic-society QA diagnostics for STWM.

This module validates frozen M3 QA profiles and externally produced evidence.
It does not implement candidates, authority transitions, economy, social
effects, JointAction coordination, replay, Unity presentation, or soak runs.
Missing CONTRACTS, SIM, or UNITY surfaces are precise PENDING findings until
``--require-m3`` converts them to blocking failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final, cast

import yaml

REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_IMPORT_ROOT, REPOSITORY_IMPORT_ROOT / "python"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from town_core.catalogs import CatalogValidationError, load_catalog
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import MessageType

from tools.diagnostics.check_m0 import Status as M0Status
from tools.diagnostics.check_m0 import check_sensitive_files, find_repository_root
from tools.diagnostics.check_m2 import detect_unity_generated_path


class Status(StrEnum):
    PASS = "PASS"
    PENDING = "PENDING"
    FAIL = "FAIL"


class Owner(StrEnum):
    QA = "QA"
    CONTRACTS = "CONTRACTS"
    SIM = "SIM"
    UNITY = "UNITY"
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


PROJECT_NAME: Final = "Small Town World Model（STWM）"
ACCEPTED_M2_COMMIT: Final = "7b2618de09bd87eb49716ac40f1d0ba697f00351"
M3_ENTRY_COMMIT: Final = "2a516159ab41f88c90ea2932bbc117b595c569c3"
PROTOCOL_VERSION: Final = "0.3.0"
M2_PROTOCOL_VERSION: Final = "0.2.0"
CATALOG_PROTOCOL_VERSION: Final = "0.1.0"
UNITY_EDITOR_VERSION: Final = "6000.4.2f1"
READINESS_SCHEMA: Final = "stwm.qa.m3-readiness/v1"
EVIDENCE_SCHEMA: Final = "stwm.qa.m3-acceptance-evidence/v1"
FIXTURE_ROOT: Final = Path("integration_tests/fixtures/m3")
RELEASE_PROFILE_PATH: Final = FIXTURE_ROOT / "release-profile.json"
BEHAVIOR_MATRIX_PATH: Final = FIXTURE_ROOT / "behavior-matrix.json"
REGISTRY_PROFILE_PATH: Final = FIXTURE_ROOT / "full-registry-profile.json"
READINESS_TEMPLATE: Final = Path("docs/qa/M3_READINESS.template.json")
READINESS_JSON_SCHEMA: Final = Path("docs/qa/M3_READINESS.schema.json")
EVIDENCE_TEMPLATE: Final = Path("docs/qa/M3_ACCEPTANCE_EVIDENCE.template.json")
EVIDENCE_JSON_SCHEMA: Final = Path("docs/qa/M3_ACCEPTANCE_EVIDENCE.schema.json")
M3_BASELINE: Final = Path("docs/orchestration/M3_EXECUTION_BASELINE.md")
M3_ADR: Final = Path("docs/adr/0011-m3-society-authority-and-protocol-v030.md")
SEMANTIC_MANIFEST: Final = Path("config/v0/semantic_instances.yaml")
SIM_QA_ADAPTER: Final = Path("python/town_core/simulation/m3_qa_adapter.py")
UNITY_EVIDENCE_EXPORTER: Final = Path("unity/Assets/AITown/Editor/M3AcceptanceEvidenceExporter.cs")
UNITY_FULL_TOWN_BUILDER: Final = Path("unity/Assets/AITown/Editor/M3FullTownFixtureBuilder.cs")

AGENT_IDS: Final = tuple(f"npc_{index:02d}" for index in range(1, 11))
HOUSEHOLD_IDS: Final = ("household_a", "household_b", "household_c", "household_d")
LOCATION_IDS: Final = ("home_a", "home_b", "home_c", "home_d", "cafe_bar", "shop", "workshop", "park")
BEHAVIOR_IDS: Final = (
    "idle",
    "sleep",
    "eat_at_home",
    "shower",
    "watch_tv",
    "relax_at_home",
    "work_shift",
    "take_break",
    "buy_groceries",
    "eat_at_cafe",
    "drink_at_bar",
    "walk_in_park",
    "sit_in_park",
    "greet",
    "chat",
    "joke",
    "compliment",
    "share_event",
    "invite_join",
    "apologize",
    "confront",
    "end_conversation",
)
OBJECT_TYPES: Final = (
    "BED",
    "FRIDGE",
    "DINING_SEAT",
    "SHOWER",
    "SOFA",
    "TV",
    "WORKSTATION",
    "SHOP_SHELF",
    "CHECKOUT_COUNTER",
    "CAFE_COUNTER",
    "BAR_COUNTER",
    "PUBLIC_SEAT",
    "PARK_ROUTE",
    "LEISURE_SPOT",
    "CONVERSATION_ANCHOR",
)
INVITED_ACTIVITY_IDS: Final = (
    "watch_tv",
    "eat_at_cafe",
    "drink_at_bar",
    "walk_in_park",
    "sit_in_park",
)
SEEDS_7_DAY: Final = (12345, 24680, 97531, 314159, 271828)
SEEDS_30_DAY: Final = (12345, 24680, 97531)
DRIVER_CHUNKS: Final = (1, 7, 60)
CHECKPOINT_INTERVAL_MINUTES: Final = 360
FAST_TARGET_MINUTES: Final = 10
FAST_HARD_LIMIT_MINUTES: Final = 15
SLOW_SHARD_LIMIT: Final = 4
SLOW_SHARD_HARD_LIMIT_MINUTES: Final = 60

MAX_CANDIDATES_PER_AGENT: Final = 12
MAX_DECISION_BATCH: Final = 120
MAX_IDLE_MINUTES: Final = 1440
MAX_ZERO_NEED_MINUTES: Final = 360
MONEY_LOW_STREAK_LIMIT_DAYS: Final = 7
RELATIONSHIP_BOUNDARY_EPSILON: Final = 0.01
RELATIONSHIP_BOUNDARY_FRACTION_LIMIT: Final = 0.80
RELATIONSHIP_BOUNDARY_STREAK_DAYS: Final = 7
MAX_EVENTS_PER_DAY: Final = 1000
MAX_30_DAY_WALL_SECONDS: Final = 900
MAX_PEAK_RSS_BYTES: Final = 1024 * 1024 * 1024
MAX_RSS_SLOPE_BYTES_PER_DAY: Final = 1024 * 1024
MAX_DECISION_BATCH_P95_MS: Final = 50.0
MAX_TICK_P99_MS: Final = 100.0

BEHAVIOR_PROBES: Final = (
    "legal_candidate",
    "illegal_candidate",
    "hard_cost_preview",
    "resolver_accept",
    "resolver_reject",
    "reservation_and_lifecycle",
    "allowed_effects",
    "authoritative_replay",
    "unity_presentation",
)
EVIDENCE_GATES: Final = (
    "protocol_0_3",
    "compatibility_profiles",
    "catalog_surface",
    "shared_semantic_manifest",
    "full_registry",
    "behavior_matrix",
    "agent_liveness",
    "economy_conservation",
    "relationship_direction",
    "knowledge_permissions",
    "joint_action_atomicity",
    "checkpoint_resume",
    "determinism",
    "authoritative_replay",
    "soak_7_day",
    "soak_30_day",
    "pathology",
    "performance",
    "unity_semantics",
    "debug_explainability",
    "m0_m2_regressions",
    "repository_guard",
)
MATRIX_KEYS: Final = (
    "catalog_surface",
    "behavior_coverage",
    "agent_liveness",
    "household_economy",
    "relationship_summary",
    "knowledge_permissions",
    "joint_action",
    "determinism",
    "soak_runs",
    "pathology",
    "performance",
    "unity",
)
ARTIFACT_SCHEMAS: Final[dict[str, tuple[set[str], str | None]]] = {
    "authority_evidence": ({".json"}, "stwm.simulation.m3-authority-evidence/v1"),
    "behavior_matrix_report": ({".json"}, "stwm.simulation.m3-behavior-coverage/v1"),
    "full_registry": ({".json"}, None),
    "registry_report": ({".json"}, "stwm.unity.m3-registry-report/v1"),
    "soak_7_day_report": ({".json"}, "stwm.simulation.m3-soak-report/v1"),
    "soak_30_day_report": ({".json"}, "stwm.simulation.m3-soak-report/v1"),
    "replay_report": ({".json"}, "stwm.simulation.m3-replay-report/v1"),
    "pathology_report": ({".json"}, "stwm.simulation.m3-pathology-report/v1"),
    "performance_report": ({".json"}, "stwm.simulation.m3-performance-report/v1"),
    "unity_semantic_report": ({".json"}, "stwm.unity.m3-semantic-coverage/v1"),
    "debug_trace": ({".jsonl"}, "stwm.unity.m3-debug-trace/v1"),
    "editmode_results": ({".xml"}, None),
    "playmode_results": ({".xml"}, None),
    "batchmode_log": ({".log", ".txt"}, None),
    "repository_report": ({".json"}, "stwm.qa.m3-repository-report/v1"),
}
SOURCE_COMMIT_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
PYTHON_312_PATTERN: Final = re.compile(r"^3\.12(?:\.[0-9]+)?$")
MACHINE_PATH_PATTERN: Final = re.compile(r"(?:/Users/|/home/runner/|[A-Za-z]:\\Users\\)")
SECRET_PATTERN: Final = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|password|secret)\s*[:=]\s*[\"']?[^\s\"']{8,}"
)
EXTERNAL_ONLY_SCHEMAS: Final = {
    READINESS_SCHEMA,
    EVIDENCE_SCHEMA,
    "stwm.simulation.m3-authority-checkpoint/v1",
    *(schema for _, schema in ARTIFACT_SCHEMAS.values() if schema is not None),
}


class DiagnosticError(ValueError):
    """Raised for malformed QA fixtures or external evidence."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DiagnosticError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DiagnosticError(f"{label} must be an array")
    return cast(list[object], value)


def _string(value: Mapping[str, object], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise DiagnosticError(f"{label}.{key} must be a non-empty string")
    return item


def _integer(value: Mapping[str, object], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise DiagnosticError(f"{label}.{key} must be an integer")
    return item


def _number(value: Mapping[str, object], key: str, label: str) -> float:
    item = value.get(key)
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise DiagnosticError(f"{label}.{key} must be numeric")
    return float(item)


def _boolean(value: Mapping[str, object], key: str, label: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise DiagnosticError(f"{label}.{key} must be boolean")
    return item


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"cannot read {path}: {exc}") from exc
    return _mapping(raw, path.as_posix())


def _read_yaml(path: Path) -> Mapping[str, object]:
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DiagnosticError(f"cannot read {path}: {exc}") from exc
    return _mapping(raw, path.as_posix())


def _exact_keys(value: Mapping[str, object], expected: Sequence[str], label: str) -> None:
    actual = set(value)
    wanted = set(expected)
    if actual != wanted:
        raise DiagnosticError(f"{label} fields differ: expected {sorted(wanted)}, got {sorted(actual)}")


def _pass(*, check: str, code: str, message: str, owner: Owner, path: str | None = None) -> Finding:
    return Finding(check=check, status=Status.PASS, code=code, message=message, owner=owner, path=path)


def _fail(
    *,
    check: str,
    code: str,
    message: str,
    owner: Owner,
    remediation: str,
    path: str | None = None,
) -> Finding:
    return Finding(
        check=check,
        status=Status.FAIL,
        code=code,
        message=message,
        owner=owner,
        path=path,
        remediation=remediation,
    )


def _pending(
    *,
    check: str,
    code: str,
    message: str,
    owner: Owner,
    require_m3: bool,
    remediation: str,
    path: str | None = None,
) -> Finding:
    return Finding(
        check=check,
        status=Status.FAIL if require_m3 else Status.PENDING,
        code=code,
        message=message,
        owner=owner,
        path=path,
        remediation=remediation,
    )


def _git_candidates(root: Path) -> tuple[list[str], str | None]:
    completed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return [], completed.stderr.decode("utf-8", errors="replace").strip()
    return [item for item in completed.stdout.decode("utf-8", errors="surrogateescape").split("\0") if item], None


def _head_commit(root: Path) -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and SOURCE_COMMIT_PATTERN.fullmatch(value) else M3_ENTRY_COMMIT


def check_governance(root: Path, require_m3: bool) -> list[Finding]:
    ancestry = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ACCEPTED_M2_COMMIT, "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    findings = [
        (
            _pass(
                check="m3.governance",
                code="M3_ACCEPTED_M2_BASELINE",
                message=f"HEAD contains accepted M2 baseline {ACCEPTED_M2_COMMIT[:8]}",
                owner=Owner.ORCHESTRATOR,
            )
            if ancestry.returncode == 0
            else _fail(
                check="m3.governance",
                code="M3_ACCEPTED_M2_BASELINE",
                message=f"HEAD does not contain accepted M2 baseline {ACCEPTED_M2_COMMIT}",
                owner=Owner.ORCHESTRATOR,
                remediation="Recreate the M3 branch from the frozen 2a51615 entry commit.",
            )
        )
    ]
    for path, code, label in (
        (M3_BASELINE, "M3_EXECUTION_BASELINE", "M3 execution baseline"),
        (M3_ADR, "M3_ADR_0011", "ADR-0011"),
    ):
        findings.append(
            _pass(
                check="m3.governance",
                code=code,
                message=f"{label} is present",
                owner=Owner.ORCHESTRATOR,
                path=path.as_posix(),
            )
            if (root / path).is_file()
            else _pending(
                check="m3.governance",
                code=code + "_PENDING",
                message=f"{label} is absent",
                owner=Owner.ORCHESTRATOR,
                require_m3=require_m3,
                remediation="Integrate the frozen M3 entry commit before running the strict gate.",
                path=path.as_posix(),
            )
        )
    return findings


def check_repository_guard(root: Path) -> list[Finding]:
    m0_failures = [item for item in check_sensitive_files(root) if item.status is M0Status.FAIL]
    findings = [
        _pass(
            check="m3.repository",
            code="M3_SENSITIVE_FILE_GUARD",
            message="no sensitive/generated candidates were detected by the frozen repository guard",
            owner=Owner.QA,
        )
        if not m0_failures
        else _fail(
            check="m3.repository",
            code="M3_SENSITIVE_FILE_GUARD",
            message="; ".join(f"{item.path}: {item.message}" for item in m0_failures),
            owner=Owner.QA,
            remediation="Remove generated/sensitive content and rotate any exposed credential.",
        )
    ]
    paths, error = _git_candidates(root)
    if error:
        findings.append(
            _fail(
                check="m3.repository",
                code="M3_GIT_CANDIDATE_SCAN_FAILED",
                message=error,
                owner=Owner.QA,
                remediation="Restore a readable Git index and rerun the repository guard.",
            )
        )
        return findings
    generated = [(path, detect_unity_generated_path(path)) for path in paths]
    generated = [(path, detector) for path, detector in generated if detector is not None]
    findings.append(
        _pass(
            check="m3.repository",
            code="M3_UNITY_CACHE_GUARD",
            message="Unity caches/results and authority runs remain untracked",
            owner=Owner.QA,
        )
        if not generated
        else _fail(
            check="m3.repository",
            code="M3_UNITY_CACHE_GUARD",
            message="; ".join(f"{path}: unity-{detector}" for path, detector in generated),
            owner=Owner.QA,
            remediation="Keep Library/Logs/TestResults/runs and external evidence outside Git.",
        )
    )
    allowed_qa_documents = {READINESS_TEMPLATE.as_posix(), EVIDENCE_TEMPLATE.as_posix()}
    external_artifacts: list[str] = []
    for relative_path in paths:
        path = root / relative_path
        if relative_path in allowed_qa_documents or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
            first_record = path.read_text(encoding="utf-8").splitlines()[0]
            document = _mapping(json.loads(first_record), relative_path)
        except (DiagnosticError, IndexError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        schema = document.get("schema")
        is_full_registry_output = (
            document.get("protocol_version") == PROTOCOL_VERSION
            and document.get("message_type") == "asset_registry"
            and not relative_path.startswith("protocol/examples/")
        )
        if schema in EXTERNAL_ONLY_SCHEMAS or is_full_registry_output:
            external_artifacts.append(relative_path)
    findings.append(
        _pass(
            check="m3.repository",
            code="M3_EXTERNAL_ARTIFACT_REPOSITORY_GUARD",
            message="M3 readiness, producer evidence, registry, checkpoints, and release artifacts remain external",
            owner=Owner.QA,
        )
        if not external_artifacts
        else _fail(
            check="m3.repository",
            code="M3_EXTERNAL_ARTIFACT_REPOSITORY_GUARD",
            message="repository contains external-only M3 artifacts: " + ", ".join(external_artifacts),
            owner=Owner.QA,
            remediation="Remove generated M3 evidence from Git and retain only schemas, templates, and QA profiles.",
        )
    )
    return findings


def check_catalog_surface(root: Path) -> list[Finding]:
    try:
        catalog = load_catalog(root / "config/v0")
        actual = {
            "npcs": tuple(str(item.agent_id) for item in catalog.population.npcs),
            "households": tuple(str(item.household_id) for item in catalog.households.households),
            "locations": tuple(str(item.location_id) for item in catalog.locations.locations),
            "behaviors": tuple(item.behavior_id.value for item in catalog.behaviors.behaviors),
            "object_types": tuple(item.object_type.value for item in catalog.objects.object_types),
        }
        expected = {
            "npcs": AGENT_IDS,
            "households": HOUSEHOLD_IDS,
            "locations": LOCATION_IDS,
            "behaviors": BEHAVIOR_IDS,
            "object_types": OBJECT_TYPES,
        }
        if actual != expected:
            raise DiagnosticError(f"catalog surface differs: {actual}")
        if catalog.model.default_outcome_model != "heuristic" or catalog.model.neural_model_status != "deferred_to_m4":
            raise DiagnosticError("M3 must retain heuristic-only outcome configuration")
        if catalog.utility.max_candidates_per_agent != MAX_CANDIDATES_PER_AGENT:
            raise DiagnosticError("catalog max_candidates_per_agent is not 12")
    except (CatalogValidationError, DiagnosticError, OSError, ValueError) as exc:
        return [
            _fail(
                check="m3.catalog",
                code="M3_CATALOG_SURFACE",
                message=str(exc),
                owner=Owner.CONTRACTS,
                remediation="Restore the frozen 10/4/8/22/15 heuristic catalog without changing M0 IDs.",
            )
        ]
    return [
        _pass(
            check="m3.catalog",
            code="M3_CATALOG_SURFACE",
            message="catalog has exact 10/4/8/22/15 surface, 90 directed edges, and heuristic-only model status",
            owner=Owner.CONTRACTS,
        )
    ]


def _validate_release_profile(document: Mapping[str, object]) -> None:
    _exact_keys(
        document,
        (
            "schema",
            "seeds_7_day",
            "seeds_30_day",
            "driver_chunks_minutes",
            "checkpoint_interval_minutes",
            "fast_gate",
            "slow_gate",
            "pathology",
            "performance",
        ),
        "release profile",
    )
    if document.get("schema") != "stwm.qa.m3-release-profile/v1":
        raise DiagnosticError("release profile schema mismatch")
    if tuple(_sequence(document["seeds_7_day"], "seeds_7_day")) != SEEDS_7_DAY:
        raise DiagnosticError("7-day seed list differs from M3 baseline")
    if tuple(_sequence(document["seeds_30_day"], "seeds_30_day")) != SEEDS_30_DAY:
        raise DiagnosticError("30-day seed list differs from M3 baseline")
    if tuple(_sequence(document["driver_chunks_minutes"], "driver_chunks_minutes")) != DRIVER_CHUNKS:
        raise DiagnosticError("driver chunks differ from 1/7/60")
    if document.get("checkpoint_interval_minutes") != CHECKPOINT_INTERVAL_MINUTES:
        raise DiagnosticError("checkpoint interval must be six game hours")
    fast = _mapping(document["fast_gate"], "fast_gate")
    _exact_keys(fast, ("target_minutes", "hard_limit_minutes", "vcpus", "memory_gib"), "fast_gate")
    if fast != {"target_minutes": 10, "hard_limit_minutes": 15, "vcpus": 2, "memory_gib": 4}:
        raise DiagnosticError("fast gate budget differs from baseline")
    slow = _mapping(document["slow_gate"], "slow_gate")
    _exact_keys(
        slow,
        ("max_python_shards", "vcpus_per_shard", "memory_gib_per_shard", "hard_limit_minutes", "local_single_instance"),
        "slow_gate",
    )
    if slow != {
        "max_python_shards": 4,
        "vcpus_per_shard": 2,
        "memory_gib_per_shard": 4,
        "hard_limit_minutes": 60,
        "local_single_instance": True,
    }:
        raise DiagnosticError("slow gate budget differs from baseline")
    pathology = _mapping(document["pathology"], "pathology")
    expected_pathology = {
        "max_candidates_per_agent": 12,
        "max_decision_batch": 120,
        "max_idle_with_legal_non_idle_minutes": 1440,
        "max_recoverable_zero_need_minutes": 360,
        "money_low_streak_limit_days": 7,
        "relationship_boundary_epsilon": 0.01,
        "relationship_boundary_fraction_limit": 0.8,
        "relationship_boundary_streak_days": 7,
        "max_events_per_game_day": 1000,
    }
    if pathology != expected_pathology:
        raise DiagnosticError("pathology thresholds differ from M3 baseline")
    performance = _mapping(document["performance"], "performance")
    expected_performance = {
        "reference_machine": "producer Apple-silicon MacBook Air",
        "python_major_minor": "3.12",
        "max_30_day_wall_seconds": 900,
        "max_peak_rss_bytes": 1073741824,
        "max_rss_slope_bytes_per_game_day": 1048576,
        "max_decision_batch_p95_ms": 50,
        "max_tick_p99_ms": 100,
    }
    if performance != expected_performance:
        raise DiagnosticError("performance thresholds differ from M3 baseline")


def _validate_behavior_matrix(document: Mapping[str, object]) -> None:
    _exact_keys(
        document,
        ("schema", "catalog_protocol_version", "negotiated_protocol_version", "outcome_model", "cases"),
        "behavior matrix",
    )
    if document.get("schema") != "stwm.qa.m3-targeted-behavior-matrix/v1":
        raise DiagnosticError("behavior matrix schema mismatch")
    if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
        raise DiagnosticError("behavior matrix catalog provenance mismatch")
    if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("behavior matrix must target protocol 0.3.0")
    if document.get("outcome_model") != "heuristic":
        raise DiagnosticError("behavior matrix must use HeuristicOutcomeModel")
    cases = _sequence(document["cases"], "behavior matrix cases")
    observed: list[str] = []
    for index, raw in enumerate(cases):
        case = _mapping(raw, f"behavior matrix cases[{index}]")
        _exact_keys(case, ("behavior_id", "fixture_id", "required_probes"), f"behavior matrix cases[{index}]")
        behavior_id = _string(case, "behavior_id", f"behavior matrix cases[{index}]")
        observed.append(behavior_id)
        if case.get("fixture_id") != f"m3_behavior_{behavior_id}":
            raise DiagnosticError(f"behavior {behavior_id} fixture ID is not stable")
        if tuple(_sequence(case["required_probes"], f"behavior {behavior_id} required_probes")) != BEHAVIOR_PROBES:
            raise DiagnosticError(f"behavior {behavior_id} targeted probes are incomplete")
    if tuple(observed) != BEHAVIOR_IDS:
        raise DiagnosticError("behavior matrix must contain the 22 frozen IDs exactly once in catalog order")


def _validate_registry_profile(document: Mapping[str, object]) -> None:
    _exact_keys(
        document,
        (
            "schema",
            "profile",
            "missing_full_v0_severity",
            "surface",
            "homes",
            "workstations",
            "shop",
            "cafe_bar",
            "break_seats",
            "park",
            "public_locations",
        ),
        "registry profile",
    )
    if document.get("schema") != "stwm.qa.m3-full-registry-profile/v1" or document.get("profile") != "M3_FULL":
        raise DiagnosticError("registry profile metadata mismatch")
    if document.get("missing_full_v0_severity") != "ERROR":
        raise DiagnosticError("M3 full-surface omissions must be blocking ERROR")
    if _mapping(document["surface"], "surface") != {"locations": 8, "npc_views": 10, "object_types": 15}:
        raise DiagnosticError("registry surface counts differ from baseline")
    if _mapping(document["homes"], "homes") != {
        "bed_slots_per_resident": 1,
        "dining_slots_per_resident": 1,
        "fridges_per_home": 1,
        "showers_per_home": 1,
        "tvs_per_home": 1,
        "sofa_slots_per_resident": 1,
    }:
        raise DiagnosticError("home capacities differ from baseline")
    if _mapping(document["workstations"], "workstations") != {
        "CAFE_MORNING": 2,
        "CAFE_EVENING": 2,
        "SHOP": 2,
        "WORKSHOP": 4,
    }:
        raise DiagnosticError("workstation capacities differ from baseline")
    if _mapping(document["shop"], "shop") != {"shelf_slots": 2, "checkout_slots": 1}:
        raise DiagnosticError("shop capacities differ from baseline")
    if _mapping(document["cafe_bar"], "cafe_bar") != {
        "cafe_counter_slots": 1,
        "bar_counter_slots": 1,
        "dining_seat_slots": 4,
        "public_rest_seat_slots": 2,
    }:
        raise DiagnosticError("cafe/bar capacities differ from baseline")
    if _mapping(document["break_seats"], "break_seats") != {"shop": 2, "workshop": 4}:
        raise DiagnosticError("break-seat capacities differ from baseline")
    if _mapping(document["park"], "park") != {
        "route_slots": 8,
        "public_seat_slots": 4,
        "leisure_slots": 2,
        "conversation_anchor_slots": 2,
    }:
        raise DiagnosticError("park capacities differ from baseline")
    if _mapping(document["public_locations"], "public_locations") != {"conversation_anchor_slots_each": 2}:
        raise DiagnosticError("public-location conversation capacity differs from baseline")


def check_qa_profiles(root: Path) -> list[Finding]:
    validators = (
        (RELEASE_PROFILE_PATH, _validate_release_profile, "M3_RELEASE_PROFILE"),
        (BEHAVIOR_MATRIX_PATH, _validate_behavior_matrix, "M3_TARGETED_BEHAVIOR_MATRIX"),
        (REGISTRY_PROFILE_PATH, _validate_registry_profile, "M3_FULL_REGISTRY_PROFILE"),
    )
    findings: list[Finding] = []
    for path, validator, code in validators:
        try:
            validator(_read_json(root / path))
        except DiagnosticError as exc:
            findings.append(
                _fail(
                    check="m3.qa-profile",
                    code=code,
                    message=str(exc),
                    owner=Owner.QA,
                    remediation="Restore the exact ADR-0011/M3 baseline QA profile.",
                    path=path.as_posix(),
                )
            )
        else:
            findings.append(
                _pass(
                    check="m3.qa-profile",
                    code=code,
                    message=f"{path.name} matches the frozen M3 profile",
                    owner=Owner.QA,
                    path=path.as_posix(),
                )
            )
    return findings


def _validate_m3_protocol_version_policy(version: Mapping[str, object]) -> None:
    if version.get("protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("repository current protocol must be 0.3.0 for M3")
    compatibility = _mapping(version.get("compatibility"), "protocol.version.compatibility")
    active_m2 = compatibility.get("active_m2_acceptance_versions")
    active_m3 = compatibility.get("active_m3_acceptance_versions")
    bootstrap = compatibility.get("bootstrap_decodable_versions")
    if (
        active_m2 != [M2_PROTOCOL_VERSION]
        or active_m3 != [PROTOCOL_VERSION]
        or not isinstance(bootstrap, list)
        or bootstrap[:2] != [PROTOCOL_VERSION, M2_PROTOCOL_VERSION]
    ):
        raise DiagnosticError(
            "protocol/version.json must declare active_m2_acceptance_versions=['0.2.0'], "
            "active_m3_acceptance_versions=['0.3.0'], and prefer 0.3.0 before 0.2.0"
        )


def check_protocol_contract(root: Path, require_m3: bool) -> list[Finding]:
    version_path = root / "protocol/version.json"
    try:
        version = _read_json(version_path)
    except DiagnosticError as exc:
        return [
            _pending(
                check="m3.protocol",
                code="M3_PROTOCOL_0_3_PENDING",
                message=str(exc),
                owner=Owner.CONTRACTS,
                require_m3=require_m3,
                remediation="Integrate the CONTRACTS-owned protocol 0.3.0 re-freeze.",
                path="protocol/version.json",
            )
        ]
    if version.get("protocol_version") != PROTOCOL_VERSION:
        return [
            _pending(
                check="m3.protocol",
                code="M3_PROTOCOL_0_3_PENDING",
                message=f"active protocol remains {version.get('protocol_version')}; M3 requires 0.3.0",
                owner=Owner.CONTRACTS,
                require_m3=require_m3,
                remediation="Add version-aware 0.3.0 DTOs/Schemas/examples while preserving M2 0.2.0.",
                path="protocol/version.json",
            )
        ]
    try:
        _validate_m3_protocol_version_policy(version)
    except DiagnosticError as exc:
        return [
            _fail(
                check="m3.protocol",
                code="M3_PROTOCOL_COMPATIBILITY_INVALID",
                message=str(exc),
                owner=Owner.CONTRACTS,
                remediation="Regenerate protocol/version.json from ADR-0011 without removing the M2 profile.",
                path="protocol/version.json",
            )
        ]
    required_message_types = {
        "action_started",
        "world_snapshot",
        "agent_state_delta",
        "household_state_delta",
        "debug_decision_trace",
    }
    known = {item.value for item in MessageType}
    missing_types = sorted(required_message_types - known)
    examples: dict[str, Mapping[str, object]] = {}
    m2_preserved = False
    for path in (root / "protocol/examples").glob("*.json"):
        try:
            document = _read_json(path)
        except DiagnosticError:
            continue
        if document.get("protocol_version") == M2_PROTOCOL_VERSION:
            m2_preserved = True
        if document.get("protocol_version") == PROTOCOL_VERSION and isinstance(document.get("message_type"), str):
            examples[cast(str, document["message_type"])] = document
    missing_examples = sorted(required_message_types - set(examples))
    schema_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "protocol/jsonschema/protocol-message.schema.json",
            root / "protocol/jsonschema/python-to-unity-message.schema.json",
        )
        if path.is_file()
    )
    schema_missing = [
        token for token in (PROTOCOL_VERSION, "household_state_delta", "field_mask") if token not in schema_text
    ]
    problems = []
    if missing_types:
        problems.append(f"message enum missing {missing_types}")
    if missing_examples:
        problems.append(f"0.3 examples missing {missing_examples}")
    if schema_missing:
        problems.append(f"schema tokens missing {schema_missing}")
    if not m2_preserved:
        problems.append("0.2.0 compatibility examples are absent")
    if problems:
        return [
            _fail(
                check="m3.protocol",
                code="M3_PROTOCOL_0_3_PARTIAL",
                message="; ".join(problems),
                owner=Owner.CONTRACTS,
                remediation="Complete ADR-0011 protocol shapes and compatibility tests; partial integration cannot be pending.",
                path="protocol/",
            )
        ]
    return [
        _pass(
            check="m3.protocol",
            code="M3_PROTOCOL_0_3",
            message="protocol 0.3.0 M3 messages and retained 0.2.0 compatibility surface are present",
            owner=Owner.CONTRACTS,
            path="protocol/version.json",
        )
    ]


def _manifest_slot_count(item: Mapping[str, object], label: str) -> int:
    slot_count = item.get("slot_count")
    if not isinstance(slot_count, int) or isinstance(slot_count, bool) or slot_count <= 0:
        raise DiagnosticError(f"{label}.slot_count must be positive integer")
    return slot_count


def _validate_semantic_manifest_document(document: Mapping[str, object], catalog: CatalogBundle) -> None:
    _exact_keys(
        document,
        (
            "schema",
            "profile",
            "catalog_protocol_version",
            "locations",
            "npc_views",
            "objects",
            "mapped_animation_semantics",
            "mapped_prop_semantics",
            "facing_behavior_ids",
        ),
        "semantic manifest",
    )
    if document.get("schema") != "stwm.contracts.m3-semantic-instance-manifest/v1":
        raise DiagnosticError("shared semantic manifest schema mismatch")
    if document.get("profile") != "M3_FULL" or document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
        raise DiagnosticError("shared semantic manifest profile/provenance mismatch")
    locations = tuple(str(item) for item in _sequence(document["locations"], "manifest locations"))
    npc_views = tuple(str(item) for item in _sequence(document["npc_views"], "manifest npc_views"))
    if locations != LOCATION_IDS or npc_views != AGENT_IDS:
        raise DiagnosticError("manifest must contain exact ordered M3 locations and NPC views")
    objects = _sequence(document["objects"], "manifest objects")
    object_ids: set[str] = set()
    observed_types: set[str] = set()
    manifest_objects: list[Mapping[str, object]] = []
    allowed_capabilities = {
        item.object_type.value: {tag.value for tag in item.capability_tags} for item in catalog.objects.object_types
    }
    for index, raw in enumerate(objects):
        item = _mapping(raw, f"manifest objects[{index}]")
        _exact_keys(
            item,
            ("object_id", "object_type", "location_id", "capability_tags", "slot_count", "enabled"),
            f"manifest objects[{index}]",
        )
        object_id = _string(item, "object_id", f"manifest objects[{index}]")
        if object_id in object_ids:
            raise DiagnosticError(f"duplicate manifest object ID {object_id}")
        object_ids.add(object_id)
        object_type = _string(item, "object_type", f"manifest objects[{index}]")
        location_id = _string(item, "location_id", f"manifest objects[{index}]")
        if object_type not in OBJECT_TYPES or location_id not in LOCATION_IDS:
            raise DiagnosticError(f"invalid manifest object {object_id}")
        if item.get("enabled") is not True:
            raise DiagnosticError(f"required manifest object {object_id} is disabled")
        capabilities = {
            str(tag) for tag in _sequence(item["capability_tags"], f"manifest object {object_id} capabilities")
        }
        if not capabilities or not capabilities.issubset(allowed_capabilities[object_type]):
            raise DiagnosticError(f"manifest object {object_id} has no capabilities")
        _manifest_slot_count(item, f"manifest object {object_id}")
        observed_types.add(object_type)
        manifest_objects.append(item)
    if observed_types != set(OBJECT_TYPES):
        raise DiagnosticError(f"manifest object types differ: {sorted(observed_types)}")

    def capacity(location_id: str, object_type: str, capability: str | None = None) -> int:
        return sum(
            _manifest_slot_count(item, f"manifest object {item['object_id']}")
            for item in manifest_objects
            if item["location_id"] == location_id
            and item["object_type"] == object_type
            and (
                capability is None
                or capability in _sequence(item["capability_tags"], f"manifest object {item['object_id']} capabilities")
            )
        )

    def object_count(location_id: str, object_type: str) -> int:
        return sum(
            item["location_id"] == location_id and item["object_type"] == object_type for item in manifest_objects
        )

    for household in catalog.households.households:
        home = household.home_location_id
        residents = len(household.member_ids)
        if capacity(home, "BED") < residents or capacity(home, "DINING_SEAT") < residents:
            raise DiagnosticError(f"home {home} lacks one bed/dining slot per resident")
        if capacity(home, "SOFA") < residents:
            raise DiagnosticError(f"home {home} sofa capacity is below household size")
        for object_type in ("FRIDGE", "SHOWER", "TV"):
            if object_count(home, object_type) < 1:
                raise DiagnosticError(f"home {home} lacks required {object_type}")

    required_capacities = (
        ("cafe_bar", "WORKSTATION", "CAFE_MORNING", 2),
        ("cafe_bar", "WORKSTATION", "CAFE_EVENING", 2),
        ("shop", "WORKSTATION", "SHOP", 2),
        ("workshop", "WORKSTATION", "WORKSHOP", 4),
        ("shop", "SHOP_SHELF", None, 2),
        ("shop", "CHECKOUT_COUNTER", None, 1),
        ("cafe_bar", "CAFE_COUNTER", None, 1),
        ("cafe_bar", "BAR_COUNTER", None, 1),
        ("cafe_bar", "DINING_SEAT", None, 4),
        ("cafe_bar", "PUBLIC_SEAT", None, 2),
        ("shop", "PUBLIC_SEAT", None, 2),
        ("workshop", "PUBLIC_SEAT", None, 4),
        ("park", "PARK_ROUTE", None, 8),
        ("park", "PUBLIC_SEAT", None, 4),
        ("park", "LEISURE_SPOT", None, 2),
        ("park", "CONVERSATION_ANCHOR", None, 2),
    )
    for location_id, object_type, capability, minimum in required_capacities:
        if capacity(location_id, object_type, capability) < minimum:
            label = capability or object_type
            raise DiagnosticError(f"manifest {location_id} capacity for {label} is below {minimum}")
    public_locations = {
        location.location_id for location in catalog.locations.locations if location.location_type.value != "HOME"
    }
    for location_id in public_locations:
        if capacity(location_id, "CONVERSATION_ANCHOR") < 2:
            raise DiagnosticError(f"public location {location_id} lacks a two-slot conversation anchor")

    expected_animations = {
        semantic.value for behavior in catalog.behaviors.behaviors for semantic in behavior.unity.animation_semantics
    }
    expected_props = {
        behavior.unity.prop_semantic
        for behavior in catalog.behaviors.behaviors
        if behavior.unity.prop_semantic is not None
    }
    expected_facing = {
        behavior.behavior_id for behavior in catalog.behaviors.behaviors if behavior.unity.requires_facing
    }
    mapped_animations = {str(item) for item in _sequence(document["mapped_animation_semantics"], "manifest animations")}
    mapped_props = {str(item) for item in _sequence(document["mapped_prop_semantics"], "manifest props")}
    facing_behaviors = {str(item) for item in _sequence(document["facing_behavior_ids"], "manifest facing")}
    if not expected_animations.issubset(mapped_animations):
        raise DiagnosticError("manifest omits configured animation semantics")
    if not expected_props.issubset(mapped_props):
        raise DiagnosticError("manifest omits configured prop semantics")
    if facing_behaviors != expected_facing:
        raise DiagnosticError("manifest facing support differs from configured behaviors")


def check_semantic_manifest(root: Path, require_m3: bool) -> list[Finding]:
    path = root / SEMANTIC_MANIFEST
    if not path.is_file():
        return [
            _pending(
                check="m3.manifest",
                code="M3_SHARED_SEMANTIC_MANIFEST_PENDING",
                message="CONTRACTS shared full-town semantic-instance manifest is not integrated",
                owner=Owner.CONTRACTS,
                require_m3=require_m3,
                remediation=f"Publish {SEMANTIC_MANIFEST} using stwm.contracts.m3-semantic-instance-manifest/v1.",
                path=SEMANTIC_MANIFEST.as_posix(),
            )
        ]
    try:
        _validate_semantic_manifest_document(_read_yaml(path), load_catalog(root / "config/v0"))
    except (CatalogValidationError, DiagnosticError) as exc:
        return [
            _fail(
                check="m3.manifest",
                code="M3_SHARED_SEMANTIC_MANIFEST_INVALID",
                message=str(exc),
                owner=Owner.CONTRACTS,
                remediation="Regenerate the single shared manifest; Python and Unity may not keep competing lists.",
                path=SEMANTIC_MANIFEST.as_posix(),
            )
        ]
    return [
        _pass(
            check="m3.manifest",
            code="M3_SHARED_SEMANTIC_MANIFEST",
            message="shared M3 semantic-instance manifest has exact full-town surface",
            owner=Owner.CONTRACTS,
            path=SEMANTIC_MANIFEST.as_posix(),
        )
    ]


def check_upstream_adapters(root: Path, require_m3: bool) -> list[Finding]:
    findings: list[Finding] = []
    for path, code, owner, message, remediation in (
        (
            SIM_QA_ADAPTER,
            "M3_SIM_QA_ADAPTER",
            Owner.SIM,
            "SIM M3 authority/readiness adapter is integrated",
            "Implement the SIM-owned adapter that emits real authority/soak/replay facts without QA domain rules.",
        ),
        (
            UNITY_EVIDENCE_EXPORTER,
            "M3_UNITY_EVIDENCE_EXPORTER",
            Owner.UNITY,
            "Unity M3 evidence exporter is integrated",
            "Implement the Unity-owned exporter for stwm.qa.m3-acceptance-evidence/v1.",
        ),
        (
            UNITY_FULL_TOWN_BUILDER,
            "M3_UNITY_FULL_TOWN_FIXTURE",
            Owner.UNITY,
            "Unity M3 full-town functional-greybox builder is integrated",
            "Implement the shared-manifest-driven full-town fixture without final-art dependencies.",
        ),
    ):
        findings.append(
            _pass(check="m3.upstream", code=code, message=message, owner=owner, path=path.as_posix())
            if (root / path).is_file()
            else _pending(
                check="m3.upstream",
                code=code + "_PENDING",
                message=message.replace(" is integrated", " is not integrated"),
                owner=owner,
                require_m3=require_m3,
                remediation=remediation,
                path=path.as_posix(),
            )
        )
    return findings


def _validate_schema_file(path: Path, schema_id: str, top_level_keys: Sequence[str]) -> None:
    document = _read_json(path)
    if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise DiagnosticError(f"{path.name} must use JSON Schema 2020-12")
    if document.get("$id") != schema_id or document.get("additionalProperties") is not False:
        raise DiagnosticError(f"{path.name} metadata is not exact")
    if set(_sequence(document.get("required"), f"{path.name}.required")) != set(top_level_keys):
        raise DiagnosticError(f"{path.name} top-level required keys differ")
    properties = _mapping(document.get("properties"), f"{path.name}.properties")
    if set(properties) != set(top_level_keys):
        raise DiagnosticError(f"{path.name} top-level properties differ")


READINESS_KEYS: Final = (
    "schema",
    "project_name",
    "profile",
    "source_commit",
    "accepted_m2_commit",
    "m3_entry_commit",
    "catalog_protocol_version",
    "negotiated_protocol_version",
    "findings",
    "summary",
)
EVIDENCE_KEYS: Final = (
    "schema",
    "project_name",
    "profile",
    "source_commit",
    "accepted_m2_commit",
    "catalog_protocol_version",
    "negotiated_protocol_version",
    "unity_editor_version",
    "release_profile",
    "gates",
    "matrices",
    "artifacts",
)


def _validate_readiness_template(document: Mapping[str, object]) -> None:
    _exact_keys(document, READINESS_KEYS, "readiness template")
    if document.get("schema") != READINESS_SCHEMA or document.get("project_name") != PROJECT_NAME:
        raise DiagnosticError("readiness template schema/project mismatch")
    if document.get("profile") != "fast" or document.get("accepted_m2_commit") != ACCEPTED_M2_COMMIT:
        raise DiagnosticError("readiness template baseline mismatch")
    if document.get("m3_entry_commit") != M3_ENTRY_COMMIT:
        raise DiagnosticError("readiness template M3 entry mismatch")
    if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
        raise DiagnosticError("readiness template catalog provenance mismatch")
    if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("readiness template protocol mismatch")
    if document.get("source_commit") is not None:
        raise DiagnosticError("readiness template source_commit must be null placeholder")
    if document.get("findings") != []:
        raise DiagnosticError("readiness template findings must begin empty")
    if _mapping(document.get("summary"), "readiness summary") != {"pass": 0, "pending": 0, "fail": 0}:
        raise DiagnosticError("readiness template summary must begin at zero")


def _validate_evidence_template(document: Mapping[str, object]) -> None:
    _exact_keys(document, EVIDENCE_KEYS, "evidence template")
    if document.get("schema") != EVIDENCE_SCHEMA or document.get("project_name") != PROJECT_NAME:
        raise DiagnosticError("evidence template schema/project mismatch")
    if document.get("profile") != "release" or document.get("accepted_m2_commit") != ACCEPTED_M2_COMMIT:
        raise DiagnosticError("evidence template release baseline mismatch")
    if document.get("source_commit") is not None:
        raise DiagnosticError("evidence template source_commit must be null placeholder")
    if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
        raise DiagnosticError("evidence template catalog provenance mismatch")
    if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("evidence template protocol mismatch")
    if document.get("unity_editor_version") != UNITY_EDITOR_VERSION:
        raise DiagnosticError("evidence template Unity version mismatch")
    _validate_release_profile(_mapping(document.get("release_profile"), "release_profile"))
    gates = _mapping(document.get("gates"), "evidence gates")
    if set(gates) != set(EVIDENCE_GATES):
        raise DiagnosticError("evidence template gate set differs")
    for name, raw in gates.items():
        gate = _mapping(raw, f"gate {name}")
        if gate != {"status": "PENDING", "details": None}:
            raise DiagnosticError(f"gate {name} must start PENDING")
    matrices = _mapping(document.get("matrices"), "evidence matrices")
    if set(matrices) != set(MATRIX_KEYS):
        raise DiagnosticError("evidence template matrix set differs")
    artifacts = _mapping(document.get("artifacts"), "evidence artifacts")
    if set(artifacts) != set(ARTIFACT_SCHEMAS) or any(value is not None for value in artifacts.values()):
        raise DiagnosticError("evidence template artifacts must be exact null placeholders")


def check_qa_schemas(root: Path) -> list[Finding]:
    try:
        _validate_schema_file(root / READINESS_JSON_SCHEMA, READINESS_SCHEMA, READINESS_KEYS)
        _validate_schema_file(root / EVIDENCE_JSON_SCHEMA, EVIDENCE_SCHEMA, EVIDENCE_KEYS)
        _validate_readiness_template(_read_json(root / READINESS_TEMPLATE))
        _validate_evidence_template(_read_json(root / EVIDENCE_TEMPLATE))
    except DiagnosticError as exc:
        return [
            _fail(
                check="m3.qa-schema",
                code="M3_QA_SCHEMA_TEMPLATE",
                message=str(exc),
                owner=Owner.QA,
                remediation="Restore exact readiness/release JSON Schemas and templates.",
            )
        ]
    return [
        _pass(
            check="m3.qa-schema",
            code="M3_QA_SCHEMA_TEMPLATE",
            message="M3 readiness and acceptance evidence schemas/templates are exact",
            owner=Owner.QA,
        )
    ]


def _artifact_path(evidence_path: Path, descriptor: Mapping[str, object], label: str, root: Path) -> Path:
    relative_value = descriptor.get("path")
    if not isinstance(relative_value, str) or not relative_value:
        raise DiagnosticError(f"{label}.path must be a relative path")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise DiagnosticError(f"{label}.path escapes the evidence directory")
    path = (evidence_path.parent / relative).resolve()
    try:
        path.relative_to(evidence_path.parent.resolve())
    except ValueError as exc:
        raise DiagnosticError(f"{label}.path escapes the evidence directory") from exc
    try:
        path.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise DiagnosticError(f"{label}.path must remain outside the repository")
    if not path.is_file():
        raise DiagnosticError(f"{label}.path does not exist: {path}")
    return path


def _validate_artifact(
    name: str,
    raw_descriptor: object,
    evidence_path: Path,
    root: Path,
) -> None:
    descriptor = _mapping(raw_descriptor, f"artifact {name}")
    _exact_keys(descriptor, ("path", "sha256", "bytes", "redacted", "schema"), f"artifact {name}")
    expected_suffixes, expected_schema = ARTIFACT_SCHEMAS[name]
    if descriptor.get("redacted") is not True:
        raise DiagnosticError(f"artifact {name} must declare redacted=true")
    if descriptor.get("schema") != expected_schema:
        raise DiagnosticError(f"artifact {name}.schema must be {expected_schema!r}")
    digest = descriptor.get("sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise DiagnosticError(f"artifact {name}.sha256 must be 64 lowercase hex")
    declared_bytes = descriptor.get("bytes")
    if not isinstance(declared_bytes, int) or isinstance(declared_bytes, bool) or declared_bytes <= 0:
        raise DiagnosticError(f"artifact {name}.bytes must be positive integer")
    path = _artifact_path(evidence_path, descriptor, f"artifact {name}", root)
    if path.suffix.lower() not in expected_suffixes:
        raise DiagnosticError(f"artifact {name} has unexpected suffix {path.suffix}")
    raw = path.read_bytes()
    if len(raw) != declared_bytes or hashlib.sha256(raw).hexdigest() != digest:
        raise DiagnosticError(f"artifact {name} bytes/hash do not match file")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagnosticError(f"artifact {name} must be UTF-8") from exc
    if not text.strip() or MACHINE_PATH_PATTERN.search(text) or SECRET_PATTERN.search(text):
        raise DiagnosticError(f"artifact {name} is empty or contains unredacted sensitive/machine-local text")
    try:
        if path.suffix == ".xml":
            ET.fromstring(text)
        elif path.suffix == ".json":
            document = _mapping(json.loads(text), f"artifact {name} JSON")
            if expected_schema is not None and document.get("schema") != expected_schema:
                raise DiagnosticError(f"artifact {name} content schema mismatch")
            if name == "full_registry" and (
                document.get("protocol_version") != PROTOCOL_VERSION or document.get("message_type") != "asset_registry"
            ):
                raise DiagnosticError("artifact full_registry must be a protocol 0.3.0 asset_registry")
        elif path.suffix == ".jsonl":
            for number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                document = _mapping(json.loads(line), f"artifact {name} line {number}")
                if expected_schema is not None and document.get("schema") != expected_schema:
                    raise DiagnosticError(f"artifact {name} line {number} schema mismatch")
    except (ET.ParseError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"artifact {name} is malformed: {exc}") from exc


def _validate_catalog_matrix(matrix: Mapping[str, object]) -> None:
    expected = {
        "npcs": 10,
        "households": 4,
        "locations": 8,
        "behaviors": 22,
        "object_types": 15,
        "relationship_edges": 90,
        "needs": 5,
        "personality_axes": 4,
        "mood_axes": 2,
        "relationship_axes": 4,
    }
    if matrix != expected:
        raise DiagnosticError("catalog_surface matrix differs from frozen M3 counts")


def _validate_behavior_coverage(items: Sequence[object]) -> None:
    observed: list[str] = []
    keys = ("behavior_id", "fixture_id", *BEHAVIOR_PROBES, "release_soak_occurrence_count")
    for index, raw in enumerate(items):
        item = _mapping(raw, f"behavior_coverage[{index}]")
        _exact_keys(item, keys, f"behavior_coverage[{index}]")
        behavior_id = _string(item, "behavior_id", f"behavior_coverage[{index}]")
        observed.append(behavior_id)
        if item.get("fixture_id") != f"m3_behavior_{behavior_id}":
            raise DiagnosticError(f"behavior {behavior_id} fixture ID mismatch")
        if any(item.get(probe) is not True for probe in BEHAVIOR_PROBES):
            raise DiagnosticError(f"behavior {behavior_id} targeted coverage is incomplete")
        if _integer(item, "release_soak_occurrence_count", f"behavior {behavior_id}") <= 0:
            raise DiagnosticError(f"behavior {behavior_id} never occurred across the release soak set")
    if tuple(observed) != BEHAVIOR_IDS:
        raise DiagnosticError("behavior_coverage must contain exact ordered 22 behavior IDs")


def _validate_agent_liveness(items: Sequence[object]) -> None:
    observed: list[str] = []
    keys = (
        "agent_id",
        "enabled",
        "scheduled",
        "decision_count",
        "settled_action_count",
        "max_idle_with_legal_non_idle_minutes",
        "work_bound_violation_count",
    )
    for index, raw in enumerate(items):
        item = _mapping(raw, f"agent_liveness[{index}]")
        _exact_keys(item, keys, f"agent_liveness[{index}]")
        observed.append(_string(item, "agent_id", f"agent_liveness[{index}]"))
        if item.get("enabled") is not True or item.get("scheduled") is not True:
            raise DiagnosticError("every M3 agent must be enabled and scheduled")
        if (
            _integer(item, "decision_count", "agent_liveness") <= 0
            or _integer(item, "settled_action_count", "agent_liveness") <= 0
        ):
            raise DiagnosticError("every M3 agent must decide and settle actions")
        if _integer(item, "max_idle_with_legal_non_idle_minutes", "agent_liveness") > MAX_IDLE_MINUTES:
            raise DiagnosticError("agent exceeded 24-hour legal-alternative idle limit")
        if _integer(item, "work_bound_violation_count", "agent_liveness") != 0:
            raise DiagnosticError("agent work action exceeded its frozen bound")
    if tuple(observed) != AGENT_IDS:
        raise DiagnosticError("agent_liveness must contain exact ordered 10 NPC IDs")


def _validate_household_economy(items: Sequence[object]) -> None:
    observed: list[str] = []
    keys = (
        "household_id",
        "initial_money",
        "final_money",
        "unique_wages",
        "grocery_charges",
        "cafe_charges",
        "bar_charges",
        "initial_food",
        "final_food",
        "grocery_purchases",
        "completed_home_meals",
        "failed_or_cancelled_charge_count",
        "duplicate_settlement_count",
        "minimum_money",
        "minimum_food",
        "resource_recovery_within_workweek",
    )
    for index, raw in enumerate(items):
        item = _mapping(raw, f"household_economy[{index}]")
        _exact_keys(item, keys, f"household_economy[{index}]")
        observed.append(_string(item, "household_id", f"household_economy[{index}]"))
        expected_money = (
            _integer(item, "initial_money", "household_economy")
            + _integer(item, "unique_wages", "household_economy")
            - _integer(item, "grocery_charges", "household_economy")
            - _integer(item, "cafe_charges", "household_economy")
            - _integer(item, "bar_charges", "household_economy")
        )
        expected_food = (
            _integer(item, "initial_food", "household_economy")
            + 8 * _integer(item, "grocery_purchases", "household_economy")
            - _integer(item, "completed_home_meals", "household_economy")
        )
        if _integer(item, "final_money", "household_economy") != expected_money:
            raise DiagnosticError("household money conservation failed")
        if _integer(item, "final_food", "household_economy") != expected_food:
            raise DiagnosticError("household food conservation failed")
        for field in ("final_money", "final_food", "minimum_money", "minimum_food"):
            if _integer(item, field, "household_economy") < 0:
                raise DiagnosticError(f"household {field} became negative")
        if _integer(item, "failed_or_cancelled_charge_count", "household_economy") != 0:
            raise DiagnosticError("failed/cancelled action charged household resources")
        if _integer(item, "duplicate_settlement_count", "household_economy") != 0:
            raise DiagnosticError("household wage/charge was settled more than once")
        if item.get("resource_recovery_within_workweek") is not True:
            raise DiagnosticError("household failed frozen workweek resource recovery")
    if tuple(observed) != HOUSEHOLD_IDS:
        raise DiagnosticError("household_economy must contain exact ordered four households")


def _validate_social_matrices(matrices: Mapping[str, object]) -> None:
    relationship = _mapping(matrices["relationship_summary"], "relationship_summary")
    _exact_keys(
        relationship,
        (
            "edge_count",
            "out_of_range_count",
            "wrong_direction_count",
            "untraced_delta_count",
            "boundary_epsilon",
            "boundary_fraction_limit",
            "boundary_streak_days",
            "boundary_violation_count",
        ),
        "relationship_summary",
    )
    if relationship != {
        "edge_count": 90,
        "out_of_range_count": 0,
        "wrong_direction_count": 0,
        "untraced_delta_count": 0,
        "boundary_epsilon": 0.01,
        "boundary_fraction_limit": 0.8,
        "boundary_streak_days": 7,
        "boundary_violation_count": 0,
    }:
        raise DiagnosticError("relationship direction/trace/polarization matrix failed")
    knowledge = _mapping(matrices["knowledge_permissions"], "knowledge_permissions")
    expected_knowledge = {
        "direct_participant_covered": True,
        "witnessed_covered": True,
        "told_covered": True,
        "unknown_share_rejected": True,
        "speaker_known_event_only": True,
        "player_told_record_count": 0,
        "epistemic_graph_count": 0,
    }
    if knowledge != expected_knowledge:
        raise DiagnosticError("knowledge permission matrix failed or exceeds M3 scope")
    joint = _mapping(matrices["joint_action"], "joint_action")
    _exact_keys(
        joint,
        (
            "invited_activity_ids",
            "central_resolver",
            "acceptance_covered",
            "rejection_covered",
            "participant_exclusivity",
            "atomic_reservations",
            "cancel_release",
            "failure_release",
            "timeout_release",
            "split_action_count",
            "replay_match",
        ),
        "joint_action",
    )
    if tuple(_sequence(joint["invited_activity_ids"], "joint invited_activity_ids")) != INVITED_ACTIVITY_IDS:
        raise DiagnosticError("JointAction invitation allowlist differs")
    required_true = (
        "central_resolver",
        "acceptance_covered",
        "rejection_covered",
        "participant_exclusivity",
        "atomic_reservations",
        "cancel_release",
        "failure_release",
        "timeout_release",
        "replay_match",
    )
    if any(joint.get(key) is not True for key in required_true) or joint.get("split_action_count") != 0:
        raise DiagnosticError("JointAction atomicity/release/replay matrix failed")


def _validate_determinism(matrices: Mapping[str, object]) -> None:
    value = _mapping(matrices["determinism"], "determinism")
    _exact_keys(
        value,
        (
            "canonical_seed",
            "driver_chunks_minutes",
            "checkpoint_interval_minutes",
            "repeat_final_state_hash_match",
            "repeat_ledger_hash_match",
            "repeat_authority_log_hash_match",
            "chunk_final_state_hash_match",
            "chunk_ledger_hash_match",
            "chunk_authority_log_hash_match",
            "checkpoint_resume_final_state_hash_match",
            "checkpoint_resume_ledger_hash_match",
            "checkpoint_resume_authority_log_hash_match",
            "authoritative_replay_final_state_hash_match",
            "authoritative_replay_ledger_hash_match",
            "authoritative_replay_authority_log_hash_match",
            "checkpoint_resume_mismatch_count",
            "replay_mismatch_count",
            "source_run_mutation_count",
        ),
        "determinism",
    )
    if value.get("canonical_seed") != 12345:
        raise DiagnosticError("canonical determinism seed must be 12345")
    if tuple(_sequence(value["driver_chunks_minutes"], "determinism chunks")) != DRIVER_CHUNKS:
        raise DiagnosticError("determinism chunks must be 1/7/60")
    if value.get("checkpoint_interval_minutes") != CHECKPOINT_INTERVAL_MINUTES:
        raise DiagnosticError("checkpoint interval must be 360")
    for key in (
        "repeat_final_state_hash_match",
        "repeat_ledger_hash_match",
        "repeat_authority_log_hash_match",
        "chunk_final_state_hash_match",
        "chunk_ledger_hash_match",
        "chunk_authority_log_hash_match",
        "checkpoint_resume_final_state_hash_match",
        "checkpoint_resume_ledger_hash_match",
        "checkpoint_resume_authority_log_hash_match",
        "authoritative_replay_final_state_hash_match",
        "authoritative_replay_ledger_hash_match",
        "authoritative_replay_authority_log_hash_match",
    ):
        if value.get(key) is not True:
            raise DiagnosticError(f"determinism.{key} is not true")
    for key in ("checkpoint_resume_mismatch_count", "replay_mismatch_count", "source_run_mutation_count"):
        if value.get(key) != 0:
            raise DiagnosticError(f"determinism.{key} must be zero")
    runs = _sequence(matrices["soak_runs"], "soak_runs")
    expected_pairs = tuple((7, seed) for seed in SEEDS_7_DAY) + tuple((30, seed) for seed in SEEDS_30_DAY)
    observed_pairs: list[tuple[int, int]] = []
    keys = (
        "days",
        "seed",
        "status",
        "final_state_hash",
        "ledger_hash",
        "authority_log_hash",
        "replay_final_state_hash",
        "replay_ledger_hash",
        "replay_authority_log_hash",
        "invariant_violation_count",
        "artifact",
    )
    for index, raw in enumerate(runs):
        item = _mapping(raw, f"soak_runs[{index}]")
        _exact_keys(item, keys, f"soak_runs[{index}]")
        pair = (_integer(item, "days", "soak run"), _integer(item, "seed", "soak run"))
        observed_pairs.append(pair)
        if item.get("status") != "PASS" or item.get("invariant_violation_count") != 0:
            raise DiagnosticError(f"soak run {pair} did not pass invariants")
        for key in (
            "final_state_hash",
            "ledger_hash",
            "authority_log_hash",
            "replay_final_state_hash",
            "replay_ledger_hash",
            "replay_authority_log_hash",
        ):
            digest = item.get(key)
            if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
                raise DiagnosticError(f"soak run {pair} has invalid {key}")
        if item["final_state_hash"] != item["replay_final_state_hash"]:
            raise DiagnosticError(f"soak run {pair} replay final-state hash differs")
        if item["ledger_hash"] != item["replay_ledger_hash"]:
            raise DiagnosticError(f"soak run {pair} replay ledger hash differs")
        if item["authority_log_hash"] != item["replay_authority_log_hash"]:
            raise DiagnosticError(f"soak run {pair} replay authority-log hash differs")
        expected_artifact = "soak_7_day_report" if pair[0] == 7 else "soak_30_day_report"
        if item.get("artifact") != expected_artifact:
            raise DiagnosticError(f"soak run {pair} artifact reference differs")
    if tuple(observed_pairs) != expected_pairs:
        raise DiagnosticError("soak matrix must contain exact fixed 5x7 + 3x30 seed set")


def _validate_pathology(value: Mapping[str, object]) -> None:
    expected_keys = (
        "max_candidates_per_agent",
        "max_decision_batch",
        "reservation_leak_count",
        "slot_conflict_count",
        "permanent_idle_agent_count",
        "work_bound_violation_count",
        "max_recoverable_zero_need_minutes",
        "unrecovered_household_count",
        "max_all_households_money_low_streak_days",
        "relationship_boundary_violation_count",
        "max_events_per_game_day",
        "event_growth_linear",
        "untyped_event_count",
        "duplicate_semantic_event_count",
    )
    _exact_keys(value, expected_keys, "pathology")
    if _integer(value, "max_candidates_per_agent", "pathology") > MAX_CANDIDATES_PER_AGENT:
        raise DiagnosticError("candidate count exceeded 12")
    if _integer(value, "max_decision_batch", "pathology") > MAX_DECISION_BATCH:
        raise DiagnosticError("decision batch exceeded 120")
    for key in (
        "reservation_leak_count",
        "slot_conflict_count",
        "permanent_idle_agent_count",
        "work_bound_violation_count",
        "unrecovered_household_count",
        "relationship_boundary_violation_count",
        "untyped_event_count",
        "duplicate_semantic_event_count",
    ):
        if value.get(key) != 0:
            raise DiagnosticError(f"pathology.{key} must be zero")
    if _integer(value, "max_recoverable_zero_need_minutes", "pathology") > MAX_ZERO_NEED_MINUTES:
        raise DiagnosticError("recoverable need remained zero beyond six hours")
    if _number(value, "max_all_households_money_low_streak_days", "pathology") >= MONEY_LOW_STREAK_LIMIT_DAYS:
        raise DiagnosticError("all households remained money-low for seven days")
    if _integer(value, "max_events_per_game_day", "pathology") > MAX_EVENTS_PER_DAY:
        raise DiagnosticError("event count exceeded 1,000 per game day")
    if value.get("event_growth_linear") is not True:
        raise DiagnosticError("event growth was not linear")


def _validate_performance(value: Mapping[str, object]) -> None:
    keys = (
        "reference_machine",
        "os",
        "python_version",
        "rss_collection_method",
        "wall_time_seconds_30_day",
        "peak_rss_bytes",
        "post_warmup_rss_slope_bytes_per_game_day",
        "decision_batch_p95_ms",
        "tick_p99_ms",
    )
    _exact_keys(value, keys, "performance")
    if value.get("reference_machine") != "producer Apple-silicon MacBook Air":
        raise DiagnosticError("performance evidence reference machine mismatch")
    if not isinstance(value.get("os"), str) or not value.get("os"):
        raise DiagnosticError("performance evidence must record OS")
    python_version = value.get("python_version")
    if not isinstance(python_version, str) or PYTHON_312_PATTERN.fullmatch(python_version) is None:
        raise DiagnosticError("performance evidence must use Python 3.12")
    if not isinstance(value.get("rss_collection_method"), str) or not value.get("rss_collection_method"):
        raise DiagnosticError("performance evidence must record RSS collection method")
    if _number(value, "wall_time_seconds_30_day", "performance") >= MAX_30_DAY_WALL_SECONDS:
        raise DiagnosticError("30-day run did not finish within 15 minutes")
    if _integer(value, "peak_rss_bytes", "performance") >= MAX_PEAK_RSS_BYTES:
        raise DiagnosticError("peak RSS was not below 1 GiB")
    if _number(value, "post_warmup_rss_slope_bytes_per_game_day", "performance") > MAX_RSS_SLOPE_BYTES_PER_DAY:
        raise DiagnosticError("RSS slope exceeded 1 MiB/game-day")
    if _number(value, "decision_batch_p95_ms", "performance") >= MAX_DECISION_BATCH_P95_MS:
        raise DiagnosticError("decision batch p95 was not below 50 ms")
    if _number(value, "tick_p99_ms", "performance") >= MAX_TICK_P99_MS:
        raise DiagnosticError("tick p99 was not below 100 ms")


def _validate_unity(value: Mapping[str, object]) -> None:
    keys = (
        "npc_views",
        "locations",
        "object_types",
        "all_animation_semantics_mapped",
        "all_props_mapped",
        "all_facing_behaviors_supported",
        "all_required_slots_navmesh_reachable",
        "complete_snapshot_replacement",
        "explicit_null_clearing",
        "active_action_rebind",
        "stale_version_rejection",
        "duplicate_slot_claim_count",
        "joint_start_phase_cancel_fail_reconnect",
        "debug_ui_read_only",
        "debug_ui_complete_trace",
        "live_smoke_protocol_version",
        "editmode_skipped",
        "playmode_skipped",
    )
    _exact_keys(value, keys, "unity")
    if value.get("npc_views") != 10 or value.get("locations") != 8 or value.get("object_types") != 15:
        raise DiagnosticError("Unity full-town surface count mismatch")
    required_true = (
        "all_animation_semantics_mapped",
        "all_props_mapped",
        "all_facing_behaviors_supported",
        "all_required_slots_navmesh_reachable",
        "complete_snapshot_replacement",
        "explicit_null_clearing",
        "active_action_rebind",
        "stale_version_rejection",
        "joint_start_phase_cancel_fail_reconnect",
        "debug_ui_read_only",
        "debug_ui_complete_trace",
    )
    if any(value.get(key) is not True for key in required_true):
        raise DiagnosticError("Unity semantic/reconnect/debug evidence is incomplete")
    if value.get("duplicate_slot_claim_count") != 0:
        raise DiagnosticError("Unity reported duplicate slot claims")
    if value.get("live_smoke_protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("Unity live smoke did not negotiate protocol 0.3.0")
    if value.get("editmode_skipped") != 0 or value.get("playmode_skipped") != 0:
        raise DiagnosticError("M3 Unity acceptance may not contain skipped tests")


def validate_acceptance_evidence(evidence_path: Path, root: Path) -> list[Finding]:
    try:
        document = _read_json(evidence_path)
        _exact_keys(document, EVIDENCE_KEYS, "M3 acceptance evidence")
        if document.get("schema") != EVIDENCE_SCHEMA or document.get("project_name") != PROJECT_NAME:
            raise DiagnosticError("M3 evidence schema/project mismatch")
        if document.get("profile") != "release":
            raise DiagnosticError("M3 acceptance evidence profile must be release")
        source_commit = document.get("source_commit")
        if not isinstance(source_commit, str) or SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None:
            raise DiagnosticError("M3 evidence source_commit must be full lowercase Git SHA")
        if document.get("accepted_m2_commit") != ACCEPTED_M2_COMMIT:
            raise DiagnosticError("M3 evidence accepted M2 provenance mismatch")
        if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
            raise DiagnosticError("M3 evidence catalog provenance mismatch")
        if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
            raise DiagnosticError("M3 evidence negotiated protocol must be 0.3.0")
        if document.get("unity_editor_version") != UNITY_EDITOR_VERSION:
            raise DiagnosticError("M3 evidence Unity version mismatch")
        _validate_release_profile(_mapping(document["release_profile"], "release_profile"))
        gates = _mapping(document["gates"], "gates")
        if set(gates) != set(EVIDENCE_GATES):
            raise DiagnosticError("M3 evidence gate set differs")
        for name, raw in gates.items():
            gate = _mapping(raw, f"gate {name}")
            _exact_keys(gate, ("status", "details"), f"gate {name}")
            if gate.get("status") != "PASS" or not isinstance(gate.get("details"), str) or not gate.get("details"):
                raise DiagnosticError(f"gate {name} is not PASS with non-empty details")
        matrices = _mapping(document["matrices"], "matrices")
        if set(matrices) != set(MATRIX_KEYS):
            raise DiagnosticError("M3 evidence matrix set differs")
        _validate_catalog_matrix(_mapping(matrices["catalog_surface"], "catalog_surface"))
        _validate_behavior_coverage(_sequence(matrices["behavior_coverage"], "behavior_coverage"))
        _validate_agent_liveness(_sequence(matrices["agent_liveness"], "agent_liveness"))
        _validate_household_economy(_sequence(matrices["household_economy"], "household_economy"))
        _validate_social_matrices(matrices)
        _validate_determinism(matrices)
        _validate_pathology(_mapping(matrices["pathology"], "pathology"))
        _validate_performance(_mapping(matrices["performance"], "performance"))
        _validate_unity(_mapping(matrices["unity"], "unity"))
        artifacts = _mapping(document["artifacts"], "artifacts")
        if set(artifacts) != set(ARTIFACT_SCHEMAS):
            raise DiagnosticError("M3 evidence artifact set differs")
        for name, raw in artifacts.items():
            _validate_artifact(name, raw, evidence_path, root)
    except (DiagnosticError, OSError) as exc:
        return [
            _fail(
                check="m3.evidence",
                code="M3_ACCEPTANCE_EVIDENCE_INVALID",
                message=str(exc),
                owner=Owner.QA,
                remediation="Regenerate real external M3 evidence; do not edit summaries to manufacture PASS.",
                path=evidence_path.as_posix(),
            )
        ]
    return [
        _pass(
            check="m3.evidence",
            code="M3_ACCEPTANCE_EVIDENCE_VALID",
            message="external M3 release evidence has exact PASS gates, matrices, hashes, redaction, and artifacts",
            owner=Owner.QA,
            path=evidence_path.as_posix(),
        )
    ]


def validate_readiness_document(document: Mapping[str, object]) -> None:
    _exact_keys(document, READINESS_KEYS, "M3 readiness")
    if document.get("schema") != READINESS_SCHEMA or document.get("project_name") != PROJECT_NAME:
        raise DiagnosticError("readiness schema/project mismatch")
    if document.get("profile") != "fast":
        raise DiagnosticError("readiness profile must be fast")
    source_commit = document.get("source_commit")
    if not isinstance(source_commit, str) or SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise DiagnosticError("readiness source_commit must be full SHA")
    if document.get("accepted_m2_commit") != ACCEPTED_M2_COMMIT or document.get("m3_entry_commit") != M3_ENTRY_COMMIT:
        raise DiagnosticError("readiness accepted/entry provenance mismatch")
    if document.get("catalog_protocol_version") != CATALOG_PROTOCOL_VERSION:
        raise DiagnosticError("readiness catalog provenance mismatch")
    if document.get("negotiated_protocol_version") != PROTOCOL_VERSION:
        raise DiagnosticError("readiness negotiated protocol mismatch")
    findings = _sequence(document["findings"], "readiness findings")
    counts = {status.value.lower(): 0 for status in Status}
    finding_keys = ("check", "status", "code", "message", "owner", "path", "remediation")
    for index, raw in enumerate(findings):
        item = _mapping(raw, f"readiness findings[{index}]")
        _exact_keys(item, finding_keys, f"readiness findings[{index}]")
        status = item.get("status")
        if status not in {member.value for member in Status}:
            raise DiagnosticError(f"readiness finding {index} has invalid status")
        counts[status.lower()] += 1
    if _mapping(document["summary"], "readiness summary") != counts:
        raise DiagnosticError("readiness summary does not match findings")


def check_external_registry(root: Path, registry_path: Path, require_m3: bool) -> list[Finding]:
    manifest_path = root / SEMANTIC_MANIFEST
    if not manifest_path.is_file():
        return [
            _pending(
                check="m3.registry",
                code="M3_FULL_REGISTRY_MANIFEST_PENDING",
                message="cannot validate external M3_FULL registry before shared manifest integration",
                owner=Owner.CONTRACTS,
                require_m3=require_m3,
                remediation="Integrate the single shared semantic manifest, then rerun --registry.",
                path=registry_path.as_posix(),
            )
        ]
    try:
        manifest = _read_yaml(manifest_path)
        catalog = load_catalog(root / "config/v0")
        _validate_semantic_manifest_document(manifest, catalog)
        registry = _read_json(registry_path)
        if registry.get("protocol_version") != PROTOCOL_VERSION or registry.get("message_type") != "asset_registry":
            raise DiagnosticError("external registry must be protocol 0.3.0 asset_registry")
        payload = _mapping(registry.get("payload"), "asset_registry.payload")
        locations = {
            _string(_mapping(raw, "registry location"), "location_id", "registry location")
            for raw in _sequence(payload.get("locations"), "registry locations")
        }
        npcs = {
            _string(_mapping(raw, "registry npc"), "agent_id", "registry npc")
            for raw in _sequence(payload.get("npc_views"), "registry npc_views")
        }
        if locations != set(LOCATION_IDS) or npcs != set(AGENT_IDS):
            raise DiagnosticError("external registry does not contain exact 8 locations/10 NPC views")
        manifest_objects = {
            _string(item, "object_id", "manifest object"): item
            for raw in _sequence(manifest["objects"], "manifest objects")
            for item in (_mapping(raw, "manifest object"),)
        }
        registry_objects = {
            _string(item, "object_id", "registry object"): item
            for raw in _sequence(payload.get("objects"), "registry objects")
            for item in (_mapping(raw, "registry object"),)
        }
        if set(registry_objects) != set(manifest_objects):
            raise DiagnosticError("external registry object IDs differ from shared manifest")
        for object_id, expected in manifest_objects.items():
            observed = registry_objects[object_id]
            if observed.get("object_type") != expected.get("object_type") or observed.get(
                "location_id"
            ) != expected.get("location_id"):
                raise DiagnosticError(f"registry binding differs for {object_id}")
            if set(_sequence(observed.get("capability_tags"), f"registry {object_id} capabilities")) != set(
                _sequence(expected["capability_tags"], f"manifest {object_id} capabilities")
            ):
                raise DiagnosticError(f"registry capabilities differ for {object_id}")
            slots = _sequence(observed.get("interaction_slots"), f"registry {object_id} interaction_slots")
            if len(slots) < _manifest_slot_count(expected, f"manifest {object_id}"):
                raise DiagnosticError(f"registry slot capacity is insufficient for {object_id}")
        animations = set(_sequence(payload.get("mapped_animation_semantics"), "registry animations"))
        expected_animations = set(_sequence(manifest["mapped_animation_semantics"], "manifest animations"))
        if not expected_animations.issubset(animations):
            raise DiagnosticError("registry animation semantics are incomplete")
    except (CatalogValidationError, DiagnosticError) as exc:
        return [
            _fail(
                check="m3.registry",
                code="M3_FULL_REGISTRY_INVALID",
                message=str(exc),
                owner=Owner.UNITY,
                remediation="Export the full manifest-driven registry; M3_FULL omissions are blocking errors.",
                path=registry_path.as_posix(),
            )
        ]
    return [
        _pass(
            check="m3.registry",
            code="M3_FULL_REGISTRY_VALID",
            message="external protocol 0.3.0 registry exactly covers the shared full-town manifest",
            owner=Owner.UNITY,
            path=registry_path.as_posix(),
        )
    ]


def check_registry_evidence_binding(root: Path, registry_path: Path, evidence_path: Path) -> list[Finding]:
    try:
        evidence = _read_json(evidence_path)
        artifacts = _mapping(evidence.get("artifacts"), "M3 evidence artifacts")
        descriptor = _mapping(artifacts.get("full_registry"), "artifact full_registry")
        referenced = _artifact_path(evidence_path, descriptor, "artifact full_registry", root)
    except DiagnosticError as exc:
        return [
            _fail(
                check="m3.registry",
                code="M3_REGISTRY_EVIDENCE_BINDING",
                message=str(exc),
                owner=Owner.QA,
                remediation="Reference the same external M3_FULL registry in the evidence descriptor and --registry.",
            )
        ]
    return [
        _pass(
            check="m3.registry",
            code="M3_REGISTRY_EVIDENCE_BINDING",
            message="--registry and the acceptance evidence reference the same external M3_FULL export",
            owner=Owner.QA,
            path=registry_path.as_posix(),
        )
        if referenced == registry_path.resolve()
        else _fail(
            check="m3.registry",
            code="M3_REGISTRY_EVIDENCE_BINDING",
            message=f"--registry resolves to {registry_path.resolve()} but evidence references {referenced}",
            owner=Owner.QA,
            remediation="Use one registry export for the full-registry gate and release evidence.",
        )
    ]


def run_checks(
    root: Path,
    *,
    require_m3: bool = False,
    registry_path: Path | None = None,
    evidence_path: Path | None = None,
) -> list[Finding]:
    findings = [
        *check_governance(root, require_m3),
        *check_repository_guard(root),
        *check_catalog_surface(root),
        *check_qa_profiles(root),
        *check_qa_schemas(root),
        *check_protocol_contract(root, require_m3),
        *check_semantic_manifest(root, require_m3),
        *check_upstream_adapters(root, require_m3),
    ]
    if registry_path is None:
        findings.append(
            _pending(
                check="m3.registry",
                code="M3_FULL_REGISTRY_EVIDENCE_PENDING",
                message="no external M3_FULL asset_registry was supplied",
                owner=Owner.UNITY,
                require_m3=require_m3,
                remediation="Pass --registry with the real protocol 0.3.0 full-town export.",
            )
        )
    else:
        findings.extend(check_external_registry(root, registry_path, require_m3))
    if evidence_path is None:
        findings.append(
            _pending(
                check="m3.evidence",
                code="M3_ACCEPTANCE_EVIDENCE_PENDING",
                message="no external M3 release acceptance evidence was supplied",
                owner=Owner.QA,
                require_m3=require_m3,
                remediation="Run the fixed release seed matrix and Unity batchmode, then pass --evidence.",
            )
        )
    else:
        findings.extend(validate_acceptance_evidence(evidence_path, root))
    if registry_path is not None and evidence_path is not None:
        findings.extend(check_registry_evidence_binding(root, registry_path, evidence_path))
    return findings


def render_text(findings: Sequence[Finding]) -> str:
    lines: list[str] = []
    for finding in findings:
        suffix = f" [{finding.path}]" if finding.path else ""
        lines.append(f"{finding.status} {finding.code} ({finding.owner}): {finding.message}{suffix}")
        if finding.remediation:
            lines.append(f"  -> {finding.remediation}")
    counts = {status: sum(item.status is status for item in findings) for status in Status}
    lines.append("summary: " + ", ".join(f"{status.value.lower()}={counts[status]}" for status in Status))
    return "\n".join(lines)


def readiness_document(root: Path, findings: Sequence[Finding]) -> Mapping[str, object]:
    document: dict[str, object] = {
        "schema": READINESS_SCHEMA,
        "project_name": PROJECT_NAME,
        "profile": "fast",
        "source_commit": _head_commit(root),
        "accepted_m2_commit": ACCEPTED_M2_COMMIT,
        "m3_entry_commit": M3_ENTRY_COMMIT,
        "catalog_protocol_version": CATALOG_PROTOCOL_VERSION,
        "negotiated_protocol_version": PROTOCOL_VERSION,
        "findings": [asdict(item) for item in findings],
        "summary": {status.value.lower(): sum(item.status is status for item in findings) for status in Status},
    }
    validate_readiness_document(document)
    return document


def write_json_report(path: Path, root: Path, findings: Sequence[Finding]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(readiness_document(root, findings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root; auto-detected by default")
    parser.add_argument("--registry", type=Path, help="external protocol 0.3.0 M3_FULL asset_registry JSON")
    parser.add_argument("--evidence", type=Path, help="external stwm.qa.m3-acceptance-evidence/v1 JSON")
    parser.add_argument("--require-m3", action="store_true", help="convert every M3 PENDING to FAIL")
    parser.add_argument("--json-output", type=Path, help="write stwm.qa.m3-readiness/v1 report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve() if args.root else find_repository_root(Path(__file__))
    findings = run_checks(
        root,
        require_m3=args.require_m3,
        registry_path=args.registry.resolve() if args.registry else None,
        evidence_path=args.evidence.resolve() if args.evidence else None,
    )
    print(render_text(findings))
    if args.json_output:
        write_json_report(args.json_output.resolve(), root, findings)
    return 1 if any(item.status is Status.FAIL for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
