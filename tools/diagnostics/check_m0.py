"""Milestone M0 repository, scope, secret, and freeze diagnostics.

The checker intentionally validates frozen public facts and authoritative
validator behavior without reimplementing the product Schema. Upstream-owned
artifacts may be reported as PENDING during parallel M0 work, but strict mode
always returns a non-zero status until the repository is genuinely M0-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final


class Status(StrEnum):
    PASS = "PASS"
    PENDING = "PENDING"
    FAIL = "FAIL"


class Owner(StrEnum):
    QA = "QA"
    CONTRACTS = "CONTRACTS"
    ORCHESTRATOR = "ORCHESTRATOR"
    UNITY_BRIDGE = "UNITY-BRIDGE"


@dataclass(frozen=True)
class Finding:
    check: str
    status: Status
    code: str
    message: str
    owner: Owner
    path: str | None = None
    remediation: str | None = None


@dataclass(frozen=True)
class PathRequirement:
    path: str
    kind: str
    owner: Owner
    nonempty: bool = False


QA_REQUIRED_PATHS: Final[tuple[PathRequirement, ...]] = (
    PathRequirement(".github/workflows/python-ci.yml", "file", Owner.QA),
    PathRequirement(".github/requirements/qa.txt", "file", Owner.QA),
    PathRequirement("integration_tests", "directory", Owner.QA, nonempty=True),
    PathRequirement("python/tests/qa", "directory", Owner.QA, nonempty=True),
    PathRequirement("tools/diagnostics/check_m0.py", "file", Owner.QA),
    PathRequirement("tools/diagnostics/prepare_m0_freeze.py", "file", Owner.QA),
    PathRequirement("docs/qa/M0_ACCEPTANCE.md", "file", Owner.QA),
    PathRequirement("docs/qa/RUNS_CONTRACT.md", "file", Owner.QA),
    PathRequirement("docs/qa/LOG_FORMAT.md", "file", Owner.QA),
    PathRequirement("docs/handoffs/AITOWN-QA.md", "file", Owner.QA),
)

UPSTREAM_REQUIRED_PATHS: Final[tuple[PathRequirement, ...]] = (
    PathRequirement("pyproject.toml", "file", Owner.CONTRACTS),
    PathRequirement(".env.example", "file", Owner.ORCHESTRATOR),
    PathRequirement("config/v0/world.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/population.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/households.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/locations.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/objects.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/behaviors.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/schedules.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/economy.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/utility.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/events.yaml", "file", Owner.CONTRACTS),
    PathRequirement("config/v0/model.yaml", "file", Owner.CONTRACTS),
    PathRequirement("protocol/version.json", "file", Owner.CONTRACTS),
    PathRequirement("protocol/jsonschema", "directory", Owner.CONTRACTS, nonempty=True),
    PathRequirement("protocol/examples", "directory", Owner.CONTRACTS, nonempty=True),
    PathRequirement(
        "python/town_core/domain", "directory", Owner.CONTRACTS, nonempty=True
    ),
    PathRequirement("docs/specs", "directory", Owner.CONTRACTS, nonempty=True),
    PathRequirement("docs/adr", "directory", Owner.CONTRACTS, nonempty=True),
    PathRequirement("docs/orchestration/MASTER_PLAN.md", "file", Owner.ORCHESTRATOR),
    PathRequirement("docs/orchestration/CURRENT_STATUS.md", "file", Owner.ORCHESTRATOR),
    PathRequirement("docs/orchestration/DECISION_LOG.md", "file", Owner.ORCHESTRATOR),
    PathRequirement(
        "docs/orchestration/INTEGRATION_MATRIX.md", "file", Owner.ORCHESTRATOR
    ),
    PathRequirement("docs/orchestration/KNOWN_ISSUES.md", "file", Owner.ORCHESTRATOR),
    PathRequirement(
        "docs/orchestration/RELEASE_CHECKLIST.md", "file", Owner.ORCHESTRATOR
    ),
    PathRequirement("unity/Assets/AITown/Scripts", "directory", Owner.UNITY_BRIDGE),
    PathRequirement(
        "unity/Assets/AITown/Scripts/Bridge", "directory", Owner.UNITY_BRIDGE
    ),
    PathRequirement(
        "unity/Assets/AITown/Scripts/Semantic", "directory", Owner.UNITY_BRIDGE
    ),
    PathRequirement("unity/Assets/AITown/Scripts/NPC", "directory", Owner.UNITY_BRIDGE),
    PathRequirement(
        "unity/Assets/AITown/Scripts/Animation", "directory", Owner.UNITY_BRIDGE
    ),
    PathRequirement(
        "unity/Assets/AITown/Scripts/Dialogue", "directory", Owner.UNITY_BRIDGE
    ),
    PathRequirement("unity/Assets/AITown/Scripts/UI", "directory", Owner.UNITY_BRIDGE),
    PathRequirement(
        "unity/Assets/AITown/Scripts/Debug", "directory", Owner.UNITY_BRIDGE
    ),
    PathRequirement("unity/Assets/AITown/Editor", "directory", Owner.UNITY_BRIDGE),
    PathRequirement("unity/Assets/AITown/Tests", "directory", Owner.UNITY_BRIDGE),
)

EXPECTED_CATALOGS: Final[dict[str, tuple[str, tuple[str, ...], bool]]] = {
    "npc": (
        "config/v0/population.yaml",
        tuple(f"npc_{index:02d}" for index in range(1, 11)),
        True,
    ),
    "household": (
        "config/v0/households.yaml",
        ("household_a", "household_b", "household_c", "household_d"),
        True,
    ),
    "location": (
        "config/v0/locations.yaml",
        (
            "home_a",
            "home_b",
            "home_c",
            "home_d",
            "cafe_bar",
            "shop",
            "workshop",
            "park",
        ),
        True,
    ),
    "behavior": (
        "config/v0/behaviors.yaml",
        (
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
        ),
        True,
    ),
    "object_type": (
        "config/v0/objects.yaml",
        (
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
        ),
        False,
    ),
}

CATALOG_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "npc": ("agent_id", "npc_id"),
    "household": ("household_id",),
    "location": ("location_id",),
    "behavior": ("behavior_id",),
    "object_type": ("object_type",),
}

FROZEN_DIMENSIONS: Final[dict[str, tuple[str, ...]]] = {
    "needs": ("hunger", "energy", "hygiene", "fun", "social"),
    "personality": ("sociability", "discipline", "frugality", "irritability"),
    "mood": ("valence", "stress"),
    "relationship": ("familiarity", "affinity", "trust", "tension"),
}

MINIMUM_EVENT_TYPES: Final[tuple[str, ...]] = (
    "MEAL_CONSUMED",
    "GROCERIES_PURCHASED",
    "HOUSEHOLD_FOOD_LOW",
    "HOUSEHOLD_MONEY_LOW",
    "NEED_CRISIS",
    "WORK_STARTED",
    "WORK_COMPLETED",
    "WORK_LATE",
    "WORK_MISSED",
    "COWORKER_EXTRA_LOAD",
    "FIRST_GREETING",
    "POSITIVE_INTERACTION",
    "AWKWARD_INTERACTION",
    "INVITATION_ACCEPTED",
    "INVITATION_REJECTED",
    "APOLOGY_ACCEPTED",
    "APOLOGY_REJECTED",
    "CONFLICT_STARTED",
    "CONFLICT_ESCALATED",
    "CONFLICT_REDUCED",
    "EVENT_SHARED",
    "CONVERSATION_STARTED",
    "CONVERSATION_ENDED",
)

FREEZE_CHECKLIST_KEYS: Final[tuple[str, ...]] = (
    "npc_ids_10",
    "household_ids_4",
    "location_ids_8",
    "npc_household_job_shift_assignments",
    "behavior_ids_22",
    "object_types_15",
    "behavior_contracts",
    "needs_5",
    "personality_axes_4",
    "mood_axes_2",
    "relationship_axes_4",
    "event_enum",
    "economy_prices_and_wages",
    "travel_matrix",
    "unity_animation_semantics",
    "websocket_protocol_version",
    "deepseek_speech_schema",
    "golden_chain_initial_conditions",
    "data_feature_version",
    "v0_non_goals_documented",
)

FREEZE_MANIFEST_PATH: Final = "tools/diagnostics/m0_config_freeze.json"
DEFAULT_CONFIG_VALIDATOR: Final[tuple[str, ...]] = (
    sys.executable,
    "-m",
    "town_core.cli",
    "validate-config",
    "--config",
    "config/v0",
)

TEXT_SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
)

ENV_SECRET_RE: Final = re.compile(
    r"(?im)^\s*(?:export\s+)?"
    r"(?:DEEPSEEK|OPENAI|ANTHROPIC|AWS|GOOGLE|GITHUB|SLACK)?"
    r"[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD)\s*=\s*([^\s#]+)"
)
PLACEHOLDER_VALUES: Final[frozenset[str]] = frozenset(
    {
        "",
        "changeme",
        "dummy",
        "example",
        "placeholder",
        "redacted",
        "test",
        "unset",
        "your_api_key_here",
    }
)


def find_repository_root(start: Path | None = None) -> Path:
    """Find a repository root without requiring Git to be installed."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"no repository root found from {current}")


def _relative_display(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _directory_has_files(path: Path) -> bool:
    return any(item.is_file() for item in path.rglob("*"))


def check_structure(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for requirement in (*QA_REQUIRED_PATHS, *UPSTREAM_REQUIRED_PATHS):
        path = root / requirement.path
        correct_kind = path.is_file() if requirement.kind == "file" else path.is_dir()
        if not correct_kind:
            findings.append(
                Finding(
                    check="repository-structure",
                    status=Status.FAIL,
                    code="REQUIRED_PATH_MISSING",
                    message=f"required M0 {requirement.kind} is missing",
                    owner=requirement.owner,
                    path=requirement.path,
                    remediation=f"{requirement.owner} must provide this M0 artifact",
                )
            )
            continue
        if requirement.nonempty and path.is_dir() and not _directory_has_files(path):
            findings.append(
                Finding(
                    check="repository-structure",
                    status=Status.FAIL,
                    code="REQUIRED_DIRECTORY_EMPTY",
                    message="required M0 directory contains no tracked artifact",
                    owner=requirement.owner,
                    path=requirement.path,
                    remediation="add the milestone-owned artifact; an empty directory is not evidence",
                )
            )
            continue
        findings.append(
            Finding(
                check="repository-structure",
                status=Status.PASS,
                code="REQUIRED_PATH_PRESENT",
                message=f"required M0 {requirement.kind} is present",
                owner=requirement.owner,
                path=requirement.path,
            )
        )
    return findings


def _git_candidate_paths(root: Path) -> tuple[list[str], str | None]:
    command = ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        return [], error or f"git ls-files exited {completed.returncode}"
    decoded = completed.stdout.decode("utf-8", errors="surrogateescape")
    return [value for value in decoded.split("\0") if value], None


def detect_sensitive_path(relative_path: str) -> str | None:
    """Return a high-confidence sensitive/generated path detector name."""
    normalized = PurePosixPath(relative_path)
    parts = tuple(part.lower() for part in normalized.parts)
    name = normalized.name.lower()

    if name != ".env.example" and (name == ".env" or name.startswith(".env.")):
        return "environment-file"
    if name in {
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
        "service-account.json",
        "service_account.json",
    }:
        return "credential-file"
    if normalized.suffix.lower() in {".key", ".p12", ".pem", ".pfx"}:
        return "private-key-file"
    if parts[:1] == ("runs",):
        return "runtime-output"
    if len(parts) >= 2 and parts[0] == "data" and parts[1] == "generated":
        return "generated-dataset"
    if (
        len(parts) >= 2
        and parts[0] == "models"
        and (
            parts[1] == "checkpoints"
            or normalized.suffix.lower() in {".onnx", ".pt", ".pth"}
        )
    ):
        return "model-artifact"
    if (
        len(parts) >= 2
        and parts[0] == "unity"
        and parts[1]
        in {
            "library",
            "logs",
            "temp",
        }
    ):
        return "unity-generated"
    if any(
        part in {"llm_cache", "llm-cache", "cached_llm_responses"} for part in parts
    ):
        return "llm-cache"
    return None


def detect_secret_content(text: str) -> tuple[str, ...]:
    """Return detector names without returning or logging the matched secret."""
    detectors = [name for name, pattern in TEXT_SECRET_PATTERNS if pattern.search(text)]
    for match in ENV_SECRET_RE.finditer(text):
        raw_value = match.group(1).strip().strip("\"'")
        normalized = raw_value.lower()
        if (
            normalized not in PLACEHOLDER_VALUES
            and not normalized.startswith(("${", "{{", "<"))
            and len(raw_value) >= 8
        ):
            detectors.append("assigned-secret")
            break
    return tuple(sorted(set(detectors)))


def check_sensitive_files(root: Path) -> list[Finding]:
    paths, error = _git_candidate_paths(root)
    if error is not None:
        return [
            Finding(
                check="sensitive-files",
                status=Status.FAIL,
                code="GIT_PATH_SCAN_FAILED",
                message=f"unable to enumerate candidate files: {error}",
                owner=Owner.QA,
                remediation="run the diagnostic inside a Git worktree",
            )
        ]

    findings: list[Finding] = []
    scanned_text_files = 0
    for relative_path in paths:
        detector = detect_sensitive_path(relative_path)
        if detector is not None:
            findings.append(
                Finding(
                    check="sensitive-files",
                    status=Status.FAIL,
                    code="SENSITIVE_PATH_TRACKED",
                    message=f"candidate file matches detector {detector}",
                    owner=Owner.QA,
                    path=relative_path,
                    remediation="remove the artifact from Git and rotate any exposed credential",
                )
            )
            continue

        path = root / relative_path
        try:
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            raw = path.read_bytes()
        except OSError as exc:
            findings.append(
                Finding(
                    check="sensitive-files",
                    status=Status.FAIL,
                    code="CANDIDATE_FILE_UNREADABLE",
                    message=f"candidate file could not be scanned: {exc}",
                    owner=Owner.QA,
                    path=relative_path,
                )
            )
            continue
        if b"\x00" in raw:
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanned_text_files += 1
        for content_detector in detect_secret_content(content):
            findings.append(
                Finding(
                    check="sensitive-files",
                    status=Status.FAIL,
                    code="SECRET_PATTERN_FOUND",
                    message=f"content matches detector {content_detector}; value is intentionally hidden",
                    owner=Owner.QA,
                    path=relative_path,
                    remediation="remove and rotate the secret, then replace it with an environment placeholder",
                )
            )

    if not findings:
        findings.append(
            Finding(
                check="sensitive-files",
                status=Status.PASS,
                code="NO_SENSITIVE_CANDIDATES",
                message=f"scanned {len(paths)} paths and {scanned_text_files} UTF-8 files",
                owner=Owner.QA,
            )
        )
    return findings


def extract_catalog_ids(text: str, field_names: Sequence[str]) -> list[str]:
    """Extract scalar IDs from explicit Schema-owned YAML fields."""
    field_pattern = "|".join(re.escape(field) for field in field_names)
    pattern = re.compile(
        rf"^\s*(?:-\s*)?(?:{field_pattern})\s*:\s*[\"']?([^\s#\"']+)",
        flags=re.MULTILINE,
    )
    return [match.group(1) for match in pattern.finditer(text)]


def _read_contract_text(root: Path) -> str:
    chunks: list[str] = []
    for relative_root in ("config/v0", "protocol", "python/town_core/domain"):
        base = root / relative_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(chunks)


def _catalog_finding(
    *,
    catalog: str,
    path: str,
    expected: Sequence[str],
    actual_values: Sequence[str],
    require_unique: bool,
) -> Finding:
    expected_set = set(expected)
    actual_set = set(actual_values)
    missing = sorted(expected_set - actual_set)
    extras = sorted(actual_set - expected_set)
    duplicates = sorted(value for value in actual_set if actual_values.count(value) > 1)
    problems: list[str] = []
    if missing:
        problems.append(f"missing={missing}")
    if extras:
        problems.append(f"extra={extras}")
    if require_unique and duplicates:
        problems.append(f"duplicates={duplicates}")
    if problems:
        return Finding(
            check="m0-frozen-scope",
            status=Status.FAIL,
            code="CATALOG_SCOPE_MISMATCH",
            message=f"{catalog} catalog does not match the frozen M0 set: {'; '.join(problems)}",
            owner=Owner.CONTRACTS,
            path=path,
            remediation="align the authoritative catalog with the V0 specification or record an ADR",
        )
    return Finding(
        check="m0-frozen-scope",
        status=Status.PASS,
        code="CATALOG_SCOPE_MATCHES",
        message=f"{catalog} catalog matches all {len(expected)} frozen values",
        owner=Owner.CONTRACTS,
        path=path,
    )


def _config_validator_command() -> tuple[str, ...]:
    override = os.environ.get("AITOWN_M0_CONFIG_VALIDATE_CMD")
    return tuple(shlex.split(override)) if override else DEFAULT_CONFIG_VALIDATOR


def _run_config_validator(root: Path) -> Finding:
    command = _config_validator_command()
    if not command:
        return Finding(
            check="m0-config-validation",
            status=Status.FAIL,
            code="CONFIG_VALIDATOR_COMMAND_EMPTY",
            message="AITOWN_M0_CONFIG_VALIDATE_CMD resolved to an empty command",
            owner=Owner.CONTRACTS,
            remediation="provide a non-empty authoritative config validation command",
        )
    env = os.environ.copy()
    python_path = str(root / "python")
    existing_python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{python_path}{os.pathsep}{existing_python_path}"
        if existing_python_path
        else python_path
    )
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Finding(
            check="m0-config-validation",
            status=Status.FAIL,
            code="CONFIG_VALIDATOR_NOT_RUNNABLE",
            message=f"authoritative config validator could not run: {exc}",
            owner=Owner.CONTRACTS,
            remediation="provide the default town_core CLI or set AITOWN_M0_CONFIG_VALIDATE_CMD",
        )
    if completed.returncode != 0:
        output = "\n".join(
            value.strip()
            for value in (completed.stdout, completed.stderr)
            if value.strip()
        )
        if len(output) > 1_500:
            output = f"{output[:1_500]}... [truncated]"
        return Finding(
            check="m0-config-validation",
            status=Status.FAIL,
            code="CONFIG_VALIDATOR_FAILED",
            message=(
                f"authoritative config validator exited {completed.returncode}"
                + (f": {output}" if output else "")
            ),
            owner=Owner.CONTRACTS,
            remediation=f"reproduce with: {shlex.join(command)}",
        )
    return Finding(
        check="m0-config-validation",
        status=Status.PASS,
        code="CONFIG_VALIDATOR_PASSED",
        message=f"authoritative config validator passed: {shlex.join(command)}",
        owner=Owner.CONTRACTS,
    )


def check_frozen_scope(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for catalog, (relative_path, expected, require_unique) in EXPECTED_CATALOGS.items():
        path = root / relative_path
        if not path.is_file():
            findings.append(
                Finding(
                    check="m0-frozen-scope",
                    status=Status.FAIL,
                    code="CATALOG_FILE_MISSING",
                    message=f"cannot validate frozen {catalog} scope because its catalog is missing",
                    owner=Owner.CONTRACTS,
                    path=relative_path,
                    remediation="integrate the authoritative CONTRACTS catalog",
                )
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    check="m0-frozen-scope",
                    status=Status.FAIL,
                    code="CATALOG_FILE_UNREADABLE",
                    message=f"cannot read catalog as UTF-8: {exc}",
                    owner=Owner.CONTRACTS,
                    path=relative_path,
                )
            )
            continue
        actual = extract_catalog_ids(text, CATALOG_FIELDS[catalog])
        if not actual:
            findings.append(
                Finding(
                    check="m0-frozen-scope",
                    status=Status.FAIL,
                    code="CATALOG_IDS_NOT_DISCOVERABLE",
                    message=f"no explicit {CATALOG_FIELDS[catalog]} fields were found",
                    owner=Owner.CONTRACTS,
                    path=relative_path,
                    remediation="align the QA extractor after CONTRACTS freezes the authoritative field names",
                )
            )
            continue
        findings.append(
            _catalog_finding(
                catalog=catalog,
                path=relative_path,
                expected=expected,
                actual_values=actual,
                require_unique=require_unique,
            )
        )

    contract_text = _read_contract_text(root)
    for dimension, expected_names in FROZEN_DIMENSIONS.items():
        missing = [
            name
            for name in expected_names
            if re.search(rf"\b{re.escape(name)}\b", contract_text) is None
        ]
        findings.append(
            Finding(
                check="m0-frozen-scope",
                status=Status.FAIL if missing else Status.PASS,
                code="FROZEN_DIMENSION_MISSING"
                if missing
                else "FROZEN_DIMENSION_PRESENT",
                message=(
                    f"{dimension} is missing frozen names: {missing}"
                    if missing
                    else f"{dimension} exposes all {len(expected_names)} frozen names"
                ),
                owner=Owner.CONTRACTS,
                remediation=(
                    "add the names to the authoritative Schema/config or record an ADR"
                    if missing
                    else None
                ),
            )
        )

    events_path = root / "config/v0/events.yaml"
    event_text = (
        events_path.read_text(encoding="utf-8") if events_path.is_file() else ""
    )
    missing_events = [event for event in MINIMUM_EVENT_TYPES if event not in event_text]
    findings.append(
        Finding(
            check="m0-frozen-scope",
            status=Status.FAIL if missing_events else Status.PASS,
            code="MINIMUM_EVENTS_MISSING"
            if missing_events
            else "MINIMUM_EVENTS_PRESENT",
            message=(
                f"minimum M0 event enum is missing: {missing_events}"
                if missing_events
                else f"all {len(MINIMUM_EVENT_TYPES)} minimum M0 event types are present"
            ),
            owner=Owner.CONTRACTS,
            path="config/v0/events.yaml",
            remediation=(
                "integrate the V0 minimum event enum; additional correction events are allowed"
                if missing_events
                else None
            ),
        )
    )

    if not (root / "config/v0").is_dir() or not (root / "python/town_core").is_dir():
        findings.append(
            Finding(
                check="m0-config-validation",
                status=Status.FAIL,
                code="CONFIG_VALIDATOR_INPUT_MISSING",
                message="authoritative config tree or town_core package has not been integrated",
                owner=Owner.CONTRACTS,
                remediation="integrate CONTRACTS, then run the authoritative config validator",
            )
        )
    else:
        findings.append(_run_config_validator(root))
    return findings


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def eligible_freeze_paths(root: Path) -> set[str]:
    eligible: set[str] = set()
    roots = (root / "config/v0", root / "protocol", root / "python/town_core/domain")
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix.lower() != ".pyc"
                and path.name != ".DS_Store"
            ):
                eligible.add(_relative_display(root, path))
    return eligible


def _safe_manifest_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    candidate = (root / pure).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def check_config_freeze(root: Path) -> list[Finding]:
    manifest_path = root / FREEZE_MANIFEST_PATH
    if not manifest_path.is_file():
        return [
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_MANIFEST_MISSING",
                message="M0 freeze manifest is absent; hashes and Appendix D sign-off are not recorded",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
                remediation=(
                    "after CONTRACTS integration, run prepare_m0_freeze.py and have the "
                    "Orchestrator review and complete every generated checklist item"
                ),
            )
        ]

    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_MANIFEST_INVALID_JSON",
                message=f"freeze manifest is not valid UTF-8 JSON: {exc}",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        ]
    if not isinstance(document, dict):
        return [
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_MANIFEST_WRONG_SHAPE",
                message="freeze manifest root must be an object",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        ]

    findings: list[Finding] = []
    if document.get("schema") != "aitown.qa.m0-freeze/v1":
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_MANIFEST_SCHEMA_UNSUPPORTED",
                message="expected schema aitown.qa.m0-freeze/v1",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )
    source_commit = document.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{7,40}", source_commit) is None
    ):
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_SOURCE_COMMIT_INVALID",
                message="source_commit must identify the reviewed integration commit",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )
    if not isinstance(document.get("approved_by"), str) or not document.get(
        "approved_by"
    ):
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_APPROVER_MISSING",
                message="approved_by must name the Orchestrator approval record",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )
    approved_at = document.get("approved_at_utc")
    if not isinstance(approved_at, str) or not approved_at.strip():
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_APPROVAL_TIME_MISSING",
                message="approved_at_utc must record the manual review time",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )

    checklist = document.get("checklist")
    if not isinstance(checklist, dict):
        checklist = {}
    unchecked = [key for key in FREEZE_CHECKLIST_KEYS if checklist.get(key) is not True]
    extras = sorted(str(key) for key in checklist if key not in FREEZE_CHECKLIST_KEYS)
    if unchecked or extras:
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_CHECKLIST_INCOMPLETE",
                message=f"unchecked={unchecked}; unknown={extras}",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
                remediation="review every V0 Appendix D item; do not auto-approve the checklist",
            )
        )

    file_entries = document.get("files")
    if not isinstance(file_entries, list):
        file_entries = []
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_FILES_INVALID",
                message="files must be a list of path/sha256 objects",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )

    recorded_paths: set[str] = set()
    for index, entry in enumerate(file_entries):
        if not isinstance(entry, dict):
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FREEZE_FILE_ENTRY_INVALID",
                    message=f"files[{index}] must be an object",
                    owner=Owner.ORCHESTRATOR,
                    path=FREEZE_MANIFEST_PATH,
                )
            )
            continue
        raw_path = entry.get("path")
        candidate = _safe_manifest_path(root, raw_path)
        digest = entry.get("sha256")
        if candidate is None or not isinstance(raw_path, str):
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FREEZE_PATH_UNSAFE",
                    message=f"files[{index}].path must be a safe repository-relative path",
                    owner=Owner.ORCHESTRATOR,
                    path=FREEZE_MANIFEST_PATH,
                )
            )
            continue
        normalized_path = PurePosixPath(raw_path).as_posix()
        if normalized_path in recorded_paths:
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FREEZE_PATH_DUPLICATED",
                    message="file appears more than once in freeze manifest",
                    owner=Owner.ORCHESTRATOR,
                    path=normalized_path,
                )
            )
            continue
        recorded_paths.add(normalized_path)
        if not candidate.is_file():
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FROZEN_FILE_MISSING",
                    message="a frozen file no longer exists",
                    owner=Owner.CONTRACTS,
                    path=normalized_path,
                    remediation="restore it or approve a new freeze through Orchestrator review",
                )
            )
            continue
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FREEZE_DIGEST_INVALID",
                    message="sha256 must be 64 lowercase hexadecimal characters",
                    owner=Owner.ORCHESTRATOR,
                    path=normalized_path,
                )
            )
            continue
        actual_digest = sha256_file(candidate)
        if actual_digest != digest:
            findings.append(
                Finding(
                    check="m0-config-freeze",
                    status=Status.FAIL,
                    code="FROZEN_FILE_CHANGED",
                    message="content hash differs from the approved M0 freeze",
                    owner=Owner.CONTRACTS,
                    path=normalized_path,
                    remediation="revert the drift or approve it with an ADR and a new freeze",
                )
            )

    eligible_paths = eligible_freeze_paths(root)
    missing_coverage = sorted(eligible_paths - recorded_paths)
    stale_coverage = sorted(recorded_paths - eligible_paths)
    if missing_coverage or stale_coverage:
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.FAIL,
                code="FREEZE_COVERAGE_MISMATCH",
                message=f"unrecorded={missing_coverage}; stale={stale_coverage}",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
                remediation="regenerate reviewed hashes for config, protocol, and domain Schema files",
            )
        )

    if not findings:
        findings.append(
            Finding(
                check="m0-config-freeze",
                status=Status.PASS,
                code="CONFIG_FREEZE_VERIFIED",
                message=f"verified {len(recorded_paths)} frozen files and all Appendix D sign-offs",
                owner=Owner.ORCHESTRATOR,
                path=FREEZE_MANIFEST_PATH,
            )
        )
    return findings


def _as_pending(finding: Finding, allow_pending: bool) -> Finding:
    if (
        allow_pending
        and finding.status is Status.FAIL
        and finding.owner is not Owner.QA
    ):
        return replace(
            finding,
            status=Status.PENDING,
            message=f"{finding.message} (allowed only during parallel M0 integration)",
        )
    return finding


def run_checks(
    root: Path,
    selected_checks: Sequence[str],
    *,
    allow_pending_m0_inputs: bool,
) -> list[Finding]:
    check_functions = {
        "structure": check_structure,
        "sensitive": check_sensitive_files,
        "scope": check_frozen_scope,
        "freeze": check_config_freeze,
    }
    names = (
        tuple(check_functions) if "all" in selected_checks else tuple(selected_checks)
    )
    findings: list[Finding] = []
    for name in names:
        findings.extend(check_functions[name](root))
    return [_as_pending(finding, allow_pending_m0_inputs) for finding in findings]


def render_text(findings: Iterable[Finding], *, verbose: bool = False) -> str:
    materialized = list(findings)
    visible = (
        materialized
        if verbose
        else [item for item in materialized if item.status is not Status.PASS]
    )
    lines: list[str] = []
    for finding in visible:
        location = f" path={finding.path}" if finding.path else ""
        lines.append(
            f"[{finding.status}] {finding.check}/{finding.code} "
            f"owner={finding.owner}{location}: {finding.message}"
        )
        if finding.remediation:
            lines.append(f"  remediation: {finding.remediation}")
    counts = {
        status: sum(item.status is status for item in materialized) for status in Status
    }
    lines.append(
        "summary: "
        f"pass={counts[Status.PASS]} pending={counts[Status.PENDING]} fail={counts[Status.FAIL]}"
    )
    return "\n".join(lines)


def write_json_report(path: Path, root: Path, findings: Sequence[Finding]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "aitown.qa.m0-diagnostics/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "repository_root": str(root),
        "summary": {
            status.value.lower(): sum(item.status is status for item in findings)
            for status in Status
        },
        "findings": [asdict(item) for item in findings],
    }
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        choices=("all", "structure", "sensitive", "scope", "freeze"),
        default=None,
        help="check group to run; may be repeated (default: all)",
    )
    parser.add_argument(
        "--allow-pending-m0-inputs",
        action="store_true",
        help="downgrade missing upstream M0 inputs to PENDING; QA failures still fail",
    )
    parser.add_argument(
        "--json-output", type=Path, help="write a machine-readable report"
    )
    parser.add_argument("--verbose", action="store_true", help="print passing findings")
    parser.add_argument("--root", type=Path, help="repository root override")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.resolve() if args.root else find_repository_root()
    except RuntimeError as exc:
        print(f"[FAIL] repository-root/NOT_FOUND owner=QA: {exc}", file=sys.stderr)
        return 2
    selected_checks: Sequence[str] = args.check or ("all",)
    findings = run_checks(
        root,
        selected_checks,
        allow_pending_m0_inputs=args.allow_pending_m0_inputs,
    )
    print(render_text(findings, verbose=args.verbose))
    if args.json_output:
        write_json_report(args.json_output, root, findings)
    return 1 if any(finding.status is Status.FAIL for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
