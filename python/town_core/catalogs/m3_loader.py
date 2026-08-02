"""Load and cross-validate additive M3 catalogs without changing the M1 CatalogBundle hash."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from town_core.catalogs.loader import CatalogValidationError, load_catalog
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorCategory, BehaviorId, CapabilityTag, ObjectType
from town_core.domain.m3_catalog_models import (
    BackgroundDialogueCatalog,
    DialogueOutcome,
    FullTownSemanticManifest,
    M3Catalogs,
    SemanticInstance,
)

SEMANTIC_MANIFEST_FILE = "semantic_instances.yaml"
BACKGROUND_DIALOGUE_FILE = "background_dialogue.yaml"

_FACING_BEHAVIORS = {
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.SHARE_EVENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
}
_ACCEPTANCE_BEHAVIORS = {
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
}


def _read_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise CatalogValidationError(f"missing M3 catalog file: {path}") from exc
    except yaml.YAMLError as exc:
        raise CatalogValidationError(f"invalid YAML in {path}: {exc}") from exc


def _capacity(objects: list[SemanticInstance], location_id: str, object_type: ObjectType) -> int:
    return sum(
        item.slot_count for item in objects if item.location_id == location_id and item.object_type is object_type
    )


def _capability_capacity(objects: list[SemanticInstance], location_id: str, capability: CapabilityTag) -> int:
    return sum(
        item.slot_count for item in objects if item.location_id == location_id and capability in item.capability_tags
    )


def _validate_semantic_manifest(manifest: FullTownSemanticManifest, catalog: CatalogBundle) -> list[str]:
    issues: list[str] = []
    expected_locations = {item.location_id for item in catalog.locations.locations}
    expected_agents = {item.agent_id for item in catalog.population.npcs}
    if set(manifest.location_ids) != expected_locations:
        issues.append("M3 semantic manifest location IDs must exactly match the frozen eight locations")
    if set(manifest.npc_view_ids) != expected_agents:
        issues.append("M3 semantic manifest NPC views must exactly match the frozen ten NPCs")

    type_configs = {item.object_type: item for item in catalog.objects.object_types}
    object_types = {item.object_type for item in manifest.objects}
    if object_types != set(ObjectType):
        issues.append("M3 semantic manifest must contain all fifteen frozen object types")
    for instance in manifest.objects:
        definition = type_configs[instance.object_type]
        if instance.location_id not in expected_locations:
            issues.append(f"semantic object {instance.object_id} references an unknown location")
        if not set(instance.capability_tags).issubset(set(definition.capability_tags)):
            issues.append(f"semantic object {instance.object_id} has capability tags outside its object type")
        if instance.slot_count != definition.default_slot_count:
            issues.append(f"semantic object {instance.object_id} must use catalog default slot count")
        if instance.assigned_agent_id is not None and instance.assigned_agent_id not in expected_agents:
            issues.append(f"semantic object {instance.object_id} references an unknown assigned agent")

    households = {item.home_location_id: item for item in catalog.households.households}
    for home_id, household in households.items():
        residents = set(household.member_ids)
        beds = [item for item in manifest.objects if item.location_id == home_id and item.object_type is ObjectType.BED]
        dining = [
            item
            for item in manifest.objects
            if item.location_id == home_id and item.object_type is ObjectType.DINING_SEAT
        ]
        if {item.assigned_agent_id for item in beds} != residents or len(beds) != len(residents):
            issues.append(f"{home_id} requires exactly one assigned bed per resident")
        if {item.assigned_agent_id for item in dining} != residents or len(dining) != len(residents):
            issues.append(f"{home_id} requires exactly one assigned dining seat per resident")
        for object_type in (ObjectType.FRIDGE, ObjectType.SHOWER, ObjectType.TV):
            if _capacity(manifest.objects, home_id, object_type) < 1:
                issues.append(f"{home_id} requires {object_type.value}")
        if _capacity(manifest.objects, home_id, ObjectType.SOFA) < len(residents):
            issues.append(f"{home_id} sofa capacity must cover every resident")

    workstation_requirements = {
        ("cafe_bar", CapabilityTag.CAFE_MORNING): 2,
        ("cafe_bar", CapabilityTag.CAFE_EVENING): 2,
        ("shop", CapabilityTag.SHOP): 2,
        ("workshop", CapabilityTag.WORKSHOP): 4,
    }
    for (location_id, capability), required in workstation_requirements.items():
        actual = sum(
            item.slot_count
            for item in manifest.objects
            if item.location_id == location_id
            and item.object_type is ObjectType.WORKSTATION
            and CapabilityTag.WORK in item.capability_tags
            and capability in item.capability_tags
        )
        if actual != required:
            issues.append(f"{location_id} requires exactly {required} {capability.value} workstation slots")
    for npc in catalog.population.npcs:
        assigned = [
            item
            for item in manifest.objects
            if item.object_type is ObjectType.WORKSTATION and item.assigned_agent_id == npc.agent_id
        ]
        if len(assigned) != 1:
            issues.append(f"{npc.agent_id} requires exactly one assigned workstation")
            continue
        workstation = assigned[0]
        if workstation.location_id != npc.assigned_work_location_id:
            issues.append(f"{npc.agent_id} workstation location does not match the frozen job")
        if npc.assigned_workstation_tag not in workstation.capability_tags:
            issues.append(f"{npc.agent_id} workstation is missing the frozen job capability")

    minimum_capacities = {
        ("shop", ObjectType.SHOP_SHELF): 2,
        ("shop", ObjectType.CHECKOUT_COUNTER): 1,
        ("shop", ObjectType.PUBLIC_SEAT): 2,
        ("workshop", ObjectType.PUBLIC_SEAT): 4,
        ("cafe_bar", ObjectType.CAFE_COUNTER): 1,
        ("cafe_bar", ObjectType.BAR_COUNTER): 1,
        ("cafe_bar", ObjectType.DINING_SEAT): 4,
        ("cafe_bar", ObjectType.PUBLIC_SEAT): 2,
        ("park", ObjectType.PARK_ROUTE): 8,
        ("park", ObjectType.PUBLIC_SEAT): 4,
        ("park", ObjectType.LEISURE_SPOT): 2,
        ("park", ObjectType.CONVERSATION_ANCHOR): 2,
    }
    for (location_id, object_type), minimum in minimum_capacities.items():
        if _capacity(manifest.objects, location_id, object_type) < minimum:
            issues.append(f"{location_id} requires at least {minimum} {object_type.value} slots")
    for location_id in ("cafe_bar", "shop", "workshop", "park"):
        if _capability_capacity(manifest.objects, location_id, CapabilityTag.SOCIAL_POSITION) < 2:
            issues.append(f"{location_id} requires a two-slot conversation anchor")

    required_animations = {
        semantic for behavior in catalog.behaviors.behaviors for semantic in behavior.unity.animation_semantics
    }
    if set(manifest.required_animation_semantics) != required_animations:
        issues.append("M3 animation manifest must exactly cover every configured behavior semantic")
    instance_animations = {
        semantic for instance in manifest.objects for semantic in instance.supported_animation_semantics
    }
    if not required_animations.issubset(instance_animations):
        issues.append("M3 semantic instances do not expose every required behavior animation")
    if set(manifest.required_prop_semantics) != {"MEAL", "GROCERY_BAG", "DRINK", "EVENT_ICON"}:
        issues.append("M3 prop manifest must exactly cover the four frozen prop semantics")
    if set(manifest.facing_behavior_ids) != _FACING_BEHAVIORS:
        issues.append("M3 facing behavior coverage does not match ADR-0011")
    return issues


def _validate_background_dialogue(dialogue: BackgroundDialogueCatalog, catalog: CatalogBundle) -> list[str]:
    issues: list[str] = []
    social_behaviors = {
        item.behavior_id for item in catalog.behaviors.behaviors if item.category is BehaviorCategory.SOCIAL
    }
    keys = {(item.behavior_id, item.outcome) for item in dialogue.templates}
    required = {(behavior_id, "DEFAULT") for behavior_id in social_behaviors}
    required.update(
        (behavior_id, outcome) for behavior_id in _ACCEPTANCE_BEHAVIORS for outcome in ("ACCEPTED", "REJECTED")
    )
    if keys != required:
        missing = sorted(f"{behavior.value}:{outcome}" for behavior, outcome in required - keys)
        extra = sorted(f"{behavior.value}:{outcome}" for behavior, outcome in keys - required)
        issues.append(f"background dialogue coverage mismatch; missing={missing}, extra={extra}")
    if not dialogue.fallback_line.strip():
        issues.append("background dialogue fallback must be non-empty")
    return issues


def load_m3_catalogs(config_root: str | Path, *, catalog: CatalogBundle | None = None) -> M3Catalogs:
    """Load the additive M3 catalogs while preserving the accepted M1 CatalogBundle."""

    root = Path(config_root)
    base_catalog = catalog or load_catalog(root)
    try:
        result = M3Catalogs.model_validate(
            {
                "semantic_instances": _read_yaml(root / SEMANTIC_MANIFEST_FILE),
                "background_dialogue": _read_yaml(root / BACKGROUND_DIALOGUE_FILE),
            }
        )
    except ValidationError as exc:
        raise CatalogValidationError(str(exc)) from exc
    issues = [
        *_validate_semantic_manifest(result.semantic_instances, base_catalog),
        *_validate_background_dialogue(result.background_dialogue, base_catalog),
    ]
    if issues:
        raise CatalogValidationError("M3 catalog cross-reference errors:\n- " + "\n- ".join(issues))
    return result


def m3_catalog_hash(catalogs: M3Catalogs) -> str:
    """Hash only the additive M3 catalogs; this never changes the M1 config hash."""

    payload = catalogs.model_dump(mode="json", exclude_none=False, by_alias=True)
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def select_background_dialogue_line(
    dialogue: BackgroundDialogueCatalog,
    *,
    behavior_id: BehaviorId,
    outcome: DialogueOutcome,
    deterministic_key: str,
) -> str:
    """Select a stable local line without API calls or authority mutation."""

    if not deterministic_key:
        raise ValueError("background dialogue deterministic_key must be non-empty")
    template = next(
        (item for item in dialogue.templates if item.behavior_id is behavior_id and item.outcome == outcome),
        None,
    )
    if template is None:
        return dialogue.fallback_line
    material = f"{dialogue.selection_seed_salt}|{behavior_id.value}|{outcome}|{deterministic_key}".encode()
    index = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % len(template.lines)
    return template.lines[index]
