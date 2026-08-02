"""ADR-0009 M2-scoped semantic asset registry validation."""

from __future__ import annotations

from collections import Counter

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import (
    AnimationSemantic,
    AssetValidationSeverity,
    LocationType,
    ObjectType,
)
from town_core.domain.protocol_models import (
    AssetRegistryPayload,
    AssetRegistryResultPayload,
    AssetValidationIssue,
    RegisteredObject,
)
from town_core.domain.state_models import WorldState

_SEVERITY_ORDER = {
    AssetValidationSeverity.ERROR: 0,
    AssetValidationSeverity.WARNING: 1,
    AssetValidationSeverity.INFO: 2,
}


class M2ScopedAssetRegistryValidator:
    """Validate the blocking one-NPC route and report complete-V0 gaps."""

    def __init__(self, catalog: CatalogBundle, state: WorldState, *, active_agent_id: str = "npc_01") -> None:
        self.catalog = catalog
        self.state = state
        self.active_agent_id = active_agent_id
        agent = state.agents[active_agent_id]
        self._required_location_types = {
            agent.home_location_id: LocationType.HOME,
            agent.assigned_work_location_id: LocationType.CAFE_BAR,
        }
        self._required_object_ids = tuple(
            sorted(
                object_id
                for object_id, obj in state.objects.items()
                if obj.metadata.get("assigned_agent_id") == active_agent_id
                and obj.object_type in {ObjectType.BED, ObjectType.DINING_SEAT, ObjectType.WORKSTATION}
            )
            + [f"{agent.home_location_id}_fridge_01"]
        )

    def validate(self, registry: AssetRegistryPayload) -> AssetRegistryResultPayload:
        issues: list[AssetValidationIssue] = []
        self._duplicates(registry, issues)
        locations = {item.location_id: item for item in registry.locations}
        objects = {item.object_id: item for item in registry.objects}
        npc_views = {item.agent_id for item in registry.npc_views}

        for location_id, expected_type in self._required_location_types.items():
            registered_location = locations.get(location_id)
            if registered_location is None:
                self._issue(issues, AssetValidationSeverity.ERROR, "M2_LOCATION_MISSING", location_id)
            elif registered_location.location_type is not expected_type:
                self._issue(issues, AssetValidationSeverity.ERROR, "M2_LOCATION_TYPE_MISMATCH", location_id)

        if self.active_agent_id not in npc_views:
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_NPC_VIEW_MISSING", self.active_agent_id)

        for object_id in self._required_object_ids:
            expected = self.state.objects.get(object_id)
            registered_object = objects.get(object_id)
            if expected is None:
                self._issue(issues, AssetValidationSeverity.ERROR, "M2_AUTHORITY_OBJECT_MISSING", object_id)
                continue
            if registered_object is None:
                self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_MISSING", object_id)
                continue
            self._validate_required_object(registered_object, expected.location_id, expected.object_type, issues)

        required_animations = {
            AnimationSemantic.IDLE,
            AnimationSemantic.SLEEP,
            AnimationSemantic.EAT,
            AnimationSemantic.WORK_STANDING,
        }
        mapped = set(registry.mapped_animation_semantics)
        for semantic in sorted(required_animations - mapped):
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_ANIMATION_MISSING", semantic.value)

        configured_locations = {item.location_id for item in self.catalog.locations.locations}
        for location_id in sorted(configured_locations - set(locations) - set(self._required_location_types)):
            self._issue(issues, AssetValidationSeverity.WARNING, "V0_LOCATION_NOT_REGISTERED", location_id)
        configured_types = {item.object_type for item in self.catalog.objects.object_types}
        registered_types = {item.object_type for item in registry.objects}
        required_types = {self.state.objects[item].object_type for item in self._required_object_ids}
        for object_type in sorted(configured_types - registered_types - required_types):
            self._issue(issues, AssetValidationSeverity.WARNING, "V0_OBJECT_TYPE_NOT_REGISTERED", object_type.value)
        configured_agents = {item.agent_id for item in self.catalog.population.npcs}
        for agent_id in sorted(configured_agents - npc_views - {self.active_agent_id}):
            self._issue(issues, AssetValidationSeverity.WARNING, "V0_NPC_VIEW_NOT_REGISTERED", agent_id)

        issues.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], item.code, item.entity_id or "", item.message))
        return AssetRegistryResultPayload(
            accepted=not any(item.severity is AssetValidationSeverity.ERROR for item in issues),
            issues=issues,
        )

    def _duplicates(self, registry: AssetRegistryPayload, issues: list[AssetValidationIssue]) -> None:
        groups = (
            ("DUPLICATE_LOCATION_ID", [item.location_id for item in registry.locations]),
            ("DUPLICATE_OBJECT_ID", [item.object_id for item in registry.objects]),
            ("DUPLICATE_NPC_VIEW_ID", [item.agent_id for item in registry.npc_views]),
        )
        for code, values in groups:
            for value, count in sorted(Counter(values).items()):
                if count > 1:
                    self._issue(issues, AssetValidationSeverity.ERROR, code, value)
        for obj in registry.objects:
            slots = [slot.slot_index for slot in obj.interaction_slots]
            for slot, count in sorted(Counter(slots).items()):
                if count > 1:
                    self._issue(
                        issues, AssetValidationSeverity.ERROR, "DUPLICATE_INTERACTION_SLOT", f"{obj.object_id}:{slot}"
                    )

    def _validate_required_object(
        self,
        registered: RegisteredObject,
        expected_location: str,
        expected_type: ObjectType,
        issues: list[AssetValidationIssue],
    ) -> None:
        if not registered.enabled:
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_DISABLED", registered.object_id)
        if registered.location_id != expected_location:
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_LOCATION_MISMATCH", registered.object_id)
        if registered.object_type is not expected_type:
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_TYPE_MISMATCH", registered.object_id)
        expected_caps = set(self.state.objects[registered.object_id].capability_tags)
        if not expected_caps.issubset(set(registered.capability_tags)):
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_CAPABILITY_MISSING", registered.object_id)
        if not registered.interaction_slots:
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_OBJECT_SLOT_MISSING", registered.object_id)
            return
        required_semantic = {
            ObjectType.BED: AnimationSemantic.SLEEP,
            ObjectType.DINING_SEAT: AnimationSemantic.EAT,
            ObjectType.WORKSTATION: AnimationSemantic.WORK_STANDING,
        }.get(expected_type)
        if required_semantic is not None and not any(
            required_semantic in slot.supported_animation_semantics for slot in registered.interaction_slots
        ):
            self._issue(issues, AssetValidationSeverity.ERROR, "M2_SLOT_ANIMATION_MISSING", registered.object_id)

    @staticmethod
    def _issue(
        issues: list[AssetValidationIssue],
        severity: AssetValidationSeverity,
        code: str,
        entity_id: str,
    ) -> None:
        issues.append(
            AssetValidationIssue(
                severity=severity,
                code=code,
                message=f"{code}: {entity_id}",
                entity_id=entity_id,
            )
        )
