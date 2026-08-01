"""YAML loading plus cross-file reference validation for config/v0."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import (
    BehaviorCategory,
    BehaviorId,
    CapabilityTag,
    EventType,
    LocationType,
    NeedName,
    ObjectType,
    TargetKind,
)

CONFIG_FILES = {
    "world": "world.yaml",
    "population": "population.yaml",
    "households": "households.yaml",
    "locations": "locations.yaml",
    "objects": "objects.yaml",
    "behaviors": "behaviors.yaml",
    "schedules": "schedules.yaml",
    "economy": "economy.yaml",
    "utility": "utility.yaml",
    "events": "events.yaml",
    "model": "model.yaml",
    "prompts": "prompts/manifest.yaml",
}

EXPECTED_AGENT_IDS = {f"npc_{index:02d}" for index in range(1, 11)}
EXPECTED_HOUSEHOLD_IDS = {f"household_{suffix}" for suffix in "abcd"}
EXPECTED_LOCATION_IDS = {"home_a", "home_b", "home_c", "home_d", "cafe_bar", "shop", "workshop", "park"}
EXPECTED_COUNTS = {"npcs": 10, "households": 4, "locations": 8, "behaviors": 22, "object_types": 15}
EXPECTED_HOUSEHOLDS = {
    "household_a": (["npc_01", "npc_02"], "home_a"),
    "household_b": (["npc_03", "npc_04", "npc_05"], "home_b"),
    "household_c": (["npc_06", "npc_07"], "home_c"),
    "household_d": (["npc_08", "npc_09", "npc_10"], "home_d"),
}
EXPECTED_WORK = {
    "npc_01": ("cafe_bar", CapabilityTag.CAFE_MORNING, 360, 840),
    "npc_02": ("workshop", CapabilityTag.WORKSHOP, 480, 960),
    "npc_03": ("workshop", CapabilityTag.WORKSHOP, 480, 960),
    "npc_04": ("workshop", CapabilityTag.WORKSHOP, 480, 960),
    "npc_05": ("shop", CapabilityTag.SHOP, 540, 1020),
    "npc_06": ("cafe_bar", CapabilityTag.CAFE_EVENING, 840, 1320),
    "npc_07": ("shop", CapabilityTag.SHOP, 540, 1020),
    "npc_08": ("cafe_bar", CapabilityTag.CAFE_EVENING, 840, 1320),
    "npc_09": ("workshop", CapabilityTag.WORKSHOP, 480, 960),
    "npc_10": ("cafe_bar", CapabilityTag.CAFE_MORNING, 360, 840),
}


class CatalogValidationError(ValueError):
    """Raised when syntactic or cross-catalog contract validation fails."""


def _read_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise CatalogValidationError(f"missing catalog file: {path}") from exc
    except yaml.YAMLError as exc:
        raise CatalogValidationError(f"invalid YAML in {path}: {exc}") from exc


def _duplicates(values: Iterable[Hashable]) -> set[Hashable]:
    seen: set[Hashable] = set()
    duplicates: set[Hashable] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return duplicates


def _require_unique(label: str, values: Iterable[Hashable], issues: list[str]) -> None:
    duplicates = _duplicates(values)
    if duplicates:
        issues.append(f"duplicate {label}: {sorted(str(item) for item in duplicates)}")


def _require_exact(label: str, actual: set[Any], expected: set[Any], issues: list[str]) -> None:
    if actual != expected:
        missing = sorted(str(item) for item in expected - actual)
        extra = sorted(str(item) for item in actual - expected)
        issues.append(f"{label} mismatch; missing={missing}, extra={extra}")


def _validate_cross_references(bundle: CatalogBundle, root: Path) -> list[str]:
    issues: list[str] = []
    npcs = bundle.population.npcs
    households = bundle.households.households
    locations = bundle.locations.locations
    behaviors = bundle.behaviors.behaviors
    object_types = bundle.objects.object_types
    schedules = bundle.schedules.schedules

    if dict(bundle.world.fixed_counts) != EXPECTED_COUNTS:
        issues.append(f"fixed counts mismatch: {dict(bundle.world.fixed_counts)}")
    _require_exact("NPC IDs", {npc.agent_id for npc in npcs}, EXPECTED_AGENT_IDS, issues)
    _require_exact("household IDs", {household.household_id for household in households}, EXPECTED_HOUSEHOLD_IDS, issues)
    _require_exact("location IDs", {location.location_id for location in locations}, EXPECTED_LOCATION_IDS, issues)
    _require_exact("behavior IDs", {behavior.behavior_id for behavior in behaviors}, set(BehaviorId), issues)
    _require_exact("object types", {item.object_type for item in object_types}, set(ObjectType), issues)
    _require_exact("event types", {item.event_type for item in bundle.events.event_types}, set(EventType), issues)

    for label, values in (
        ("NPC ID", (npc.agent_id for npc in npcs)),
        ("household ID", (household.household_id for household in households)),
        ("location ID", (location.location_id for location in locations)),
        ("behavior ID", (behavior.behavior_id for behavior in behaviors)),
        ("object type", (item.object_type for item in object_types)),
        ("schedule ID", (schedule.schedule_id for schedule in schedules)),
        ("event type", (item.event_type for item in bundle.events.event_types)),
    ):
        _require_unique(label, values, issues)

    location_by_id = {location.location_id: location for location in locations}
    household_by_id = {household.household_id: household for household in households}
    schedule_by_id = {schedule.schedule_id: schedule for schedule in schedules}
    object_type_ids = {item.object_type for item in object_types}

    expected_location_types = {
        "home_a": LocationType.HOME,
        "home_b": LocationType.HOME,
        "home_c": LocationType.HOME,
        "home_d": LocationType.HOME,
        "cafe_bar": LocationType.CAFE_BAR,
        "shop": LocationType.SHOP,
        "workshop": LocationType.WORKPLACE,
        "park": LocationType.PARK,
    }
    for location_id, expected_type in expected_location_types.items():
        location = location_by_id.get(location_id)
        if location and location.location_type != expected_type:
            issues.append(f"{location_id} must use location type {expected_type}")

    for location in locations:
        expected_destinations = EXPECTED_LOCATION_IDS - {location.location_id}
        _require_exact(
            f"travel destinations for {location.location_id}",
            set(location.travel_minutes),
            expected_destinations,
            issues,
        )
        for destination, minutes in location.travel_minutes.items():
            reverse = location_by_id.get(destination)
            if reverse and reverse.travel_minutes.get(location.location_id) != minutes:
                issues.append(f"V0 travel matrix must be symmetric: {location.location_id} <-> {destination}")

    member_owner: dict[str, str] = {}
    for household in households:
        _require_unique(f"member in {household.household_id}", household.member_ids, issues)
        if household.home_location_id not in location_by_id:
            issues.append(f"{household.household_id} references unknown home {household.home_location_id}")
        for member_id in household.member_ids:
            if member_id in member_owner:
                issues.append(f"{member_id} belongs to multiple households")
            member_owner[member_id] = household.household_id
        expected_household = EXPECTED_HOUSEHOLDS.get(household.household_id)
        if expected_household and (household.member_ids, household.home_location_id) != expected_household:
            issues.append(f"{household.household_id} does not match the frozen V0 membership/home assignment")
    _require_exact("household members", set(member_owner), EXPECTED_AGENT_IDS, issues)

    work_counts: dict[str, int] = {"cafe_bar": 0, "shop": 0, "workshop": 0}
    for npc in npcs:
        household_lookup = household_by_id.get(npc.household_id)
        if household_lookup is None or member_owner.get(npc.agent_id) != npc.household_id:
            issues.append(f"{npc.agent_id} household reference is not reciprocal")
        elif household_lookup.home_location_id != npc.home_location_id:
            issues.append(f"{npc.agent_id} home does not match household home")
        if npc.assigned_work_location_id not in work_counts:
            issues.append(f"{npc.agent_id} has invalid work location {npc.assigned_work_location_id}")
        else:
            work_counts[npc.assigned_work_location_id] += 1
        schedule = schedule_by_id.get(npc.schedule_id)
        if schedule is None:
            issues.append(f"{npc.agent_id} references unknown schedule {npc.schedule_id}")
        else:
            entry = schedule.entries[0]
            if entry.entry_id != f"{npc.agent_id}_work":
                issues.append(f"{npc.agent_id} schedule entry ID is inconsistent")
            if entry.location_id != npc.assigned_work_location_id:
                issues.append(f"{npc.agent_id} schedule and work location disagree")
            expected_work = EXPECTED_WORK[npc.agent_id]
            actual_work = (
                npc.assigned_work_location_id,
                npc.assigned_workstation_tag,
                entry.start_minute_of_day,
                entry.end_minute_of_day,
            )
            if actual_work != expected_work:
                issues.append(f"{npc.agent_id} does not match the frozen V0 job/shift assignment")
    if work_counts != {"cafe_bar": 4, "shop": 2, "workshop": 4}:
        issues.append(f"work distribution mismatch: {work_counts}")

    expected_schedules = {f"schedule_npc_{index:02d}" for index in range(1, 11)}
    _require_exact("schedule IDs", set(schedule_by_id), expected_schedules, issues)
    if bundle.population.relationship_initialization.generation_seed != bundle.world.random_seed:
        issues.append("relationship initialization seed must equal the frozen world seed")

    event_types = {item.event_type for item in bundle.events.event_types}
    allowed_economy_keys = {"fixed_shift_wage", "groceries", "cafe_meal", "bar_drink"}
    for behavior in behaviors:
        referenced_types = {
            object_type
            for requirement in behavior.object_requirements
            for object_type in requirement.accepted_object_types
        }
        unknown_types = referenced_types - object_type_ids
        if unknown_types:
            issues.append(f"{behavior.behavior_id} references unknown object types {sorted(unknown_types)}")
        if not set(behavior.emitted_event_types).issubset(event_types):
            issues.append(f"{behavior.behavior_id} references unknown event types")
        for effect in behavior.hard_effects:
            if effect.economy_key and effect.economy_key not in allowed_economy_keys:
                issues.append(f"{behavior.behavior_id} uses unknown economy key {effect.economy_key}")
        if behavior.category is BehaviorCategory.SOCIAL:
            allowed_targets = {TargetKind.AGENT, TargetKind.CONVERSATION}
            if behavior.target_kind not in allowed_targets:
                issues.append(f"social behavior {behavior.behavior_id} must target an agent or conversation")
            if "same_high_level_location" not in behavior.candidate_conditions:
                issues.append(f"social behavior {behavior.behavior_id} must require same_high_level_location")

    expected_need_axes = set(NeedName)
    _require_exact("need decay axes", set(bundle.utility.need_decay_per_game_hour), expected_need_axes, issues)
    _require_exact("need crisis axes", set(bundle.utility.need_crisis_thresholds), expected_need_axes, issues)

    expected_acceptance = {
        BehaviorId.GREET,
        BehaviorId.CHAT,
        BehaviorId.JOKE,
        BehaviorId.COMPLIMENT,
        BehaviorId.INVITE_JOIN,
        BehaviorId.APOLOGIZE,
        BehaviorId.CONFRONT,
    }
    _require_exact("acceptance behaviors", set(bundle.model.acceptance_behaviors), expected_acceptance, issues)

    prompt_ids = {template.prompt_id for template in bundle.prompts.templates}
    _require_exact("prompt IDs", prompt_ids, {"parse_player_utterance", "verbalize_speech_plan"}, issues)
    for template in bundle.prompts.templates:
        template_path = root / "prompts" / template.template_file
        try:
            contents = template_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            issues.append(f"missing prompt template {template_path}")
            continue
        for variable in template.required_variables:
            if "{{" + variable + "}}" not in contents:
                issues.append(f"prompt {template.prompt_id} does not contain variable {variable}")

    return issues


def load_catalog(config_root: str | Path) -> CatalogBundle:
    """Load every required V0 catalog file and validate the complete reference graph."""

    root = Path(config_root)
    raw = {field: _read_yaml(root / filename) for field, filename in CONFIG_FILES.items()}
    try:
        bundle = CatalogBundle.model_validate(raw)
    except ValidationError as exc:
        raise CatalogValidationError(str(exc)) from exc
    issues = _validate_cross_references(bundle, root)
    if issues:
        raise CatalogValidationError("catalog cross-reference errors:\n- " + "\n- ".join(issues))
    return bundle
