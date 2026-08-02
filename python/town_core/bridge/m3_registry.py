"""Blocking M3_FULL Unity asset-registry validation."""

from __future__ import annotations

from collections import Counter

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import AssetValidationSeverity
from town_core.domain.m3_catalog_models import M3Catalogs, SemanticInstance
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


class M3FullAssetRegistryValidator:
    """Require exact shared-manifest identity before M3 client readiness."""

    def __init__(self, catalog: CatalogBundle, m3_catalogs: M3Catalogs, state: WorldState) -> None:
        self.catalog = catalog
        self.m3_catalogs = m3_catalogs
        self.state = state

    def validate(self, registry: AssetRegistryPayload) -> AssetRegistryResultPayload:
        issues: list[AssetValidationIssue] = []
        self._duplicates(registry, issues)
        locations = {item.location_id: item for item in registry.locations}
        objects = {item.object_id: item for item in registry.objects}
        npc_views = {item.agent_id for item in registry.npc_views}
        manifest = self.m3_catalogs.semantic_instances

        expected_location_types = {item.location_id: item.location_type for item in self.catalog.locations.locations}
        self._exact_ids("LOCATION", set(expected_location_types), set(locations), issues)
        for location_id, expected_type in sorted(expected_location_types.items()):
            registered = locations.get(location_id)
            if registered is not None and registered.location_type is not expected_type:
                self._issue(issues, "M3_LOCATION_TYPE_MISMATCH", location_id)

        self._exact_ids("NPC_VIEW", set(manifest.npc_view_ids), npc_views, issues)
        expected_objects = {item.object_id: item for item in manifest.objects}
        self._exact_ids("OBJECT", set(expected_objects), set(objects), issues)
        for object_id, expected in sorted(expected_objects.items()):
            registered_object = objects.get(object_id)
            if registered_object is not None:
                self._validate_object(expected, registered_object, issues)

        mapped = set(registry.mapped_animation_semantics)
        required = set(manifest.required_animation_semantics)
        for semantic in sorted(required - mapped):
            self._issue(issues, "M3_ANIMATION_MISSING", semantic.value)
        for semantic in sorted(mapped - required):
            self._issue(issues, "M3_ANIMATION_UNDECLARED", semantic.value)

        # The 0.3 registry payload carries no prop/facing booleans. Complete
        # M3 NpcView identity is therefore the versioned Unity-side attestation
        # for the manifest's prop, facing, controller, and reachability checks.
        if npc_views == set(manifest.npc_view_ids):
            issues.append(
                AssetValidationIssue(
                    severity=AssetValidationSeverity.INFO,
                    code="M3_NPC_VIEW_LOCAL_ATTESTATION",
                    message="all M3 NpcViews attest local prop/facing/navigation checks",
                    entity_id=manifest.profile,
                )
            )

        issues.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], item.code, item.entity_id or "", item.message))
        return AssetRegistryResultPayload(
            accepted=not any(item.severity is AssetValidationSeverity.ERROR for item in issues),
            issues=issues,
        )

    def _validate_object(
        self,
        expected: SemanticInstance,
        registered: RegisteredObject,
        issues: list[AssetValidationIssue],
    ) -> None:
        if not registered.enabled:
            self._issue(issues, "M3_OBJECT_DISABLED", expected.object_id)
        if registered.object_type is not expected.object_type:
            self._issue(issues, "M3_OBJECT_TYPE_MISMATCH", expected.object_id)
        if registered.location_id != expected.location_id:
            self._issue(issues, "M3_OBJECT_LOCATION_MISMATCH", expected.object_id)
        if set(registered.capability_tags) != set(expected.capability_tags):
            self._issue(issues, "M3_OBJECT_CAPABILITY_MISMATCH", expected.object_id)
        slots = {item.slot_index: item for item in registered.interaction_slots}
        if set(slots) != set(range(expected.slot_count)):
            self._issue(issues, "M3_OBJECT_SLOT_SET_MISMATCH", expected.object_id)
        for slot_index, slot in sorted(slots.items()):
            if not set(expected.supported_animation_semantics).issubset(slot.supported_animation_semantics):
                self._issue(issues, "M3_SLOT_ANIMATION_MISSING", f"{expected.object_id}:{slot_index}")

    def _duplicates(self, registry: AssetRegistryPayload, issues: list[AssetValidationIssue]) -> None:
        groups = (
            ("DUPLICATE_LOCATION_ID", [item.location_id for item in registry.locations]),
            ("DUPLICATE_OBJECT_ID", [item.object_id for item in registry.objects]),
            ("DUPLICATE_NPC_VIEW_ID", [item.agent_id for item in registry.npc_views]),
        )
        for code, values in groups:
            for value, count in sorted(Counter(values).items()):
                if count > 1:
                    self._issue(issues, code, value)
        for obj in registry.objects:
            slots = [item.slot_index for item in obj.interaction_slots]
            for slot_index, count in sorted(Counter(slots).items()):
                if count > 1:
                    self._issue(issues, "DUPLICATE_INTERACTION_SLOT", f"{obj.object_id}:{slot_index}")

    def _exact_ids(
        self,
        label: str,
        expected: set[str],
        actual: set[str],
        issues: list[AssetValidationIssue],
    ) -> None:
        for entity_id in sorted(expected - actual):
            self._issue(issues, f"M3_{label}_MISSING", entity_id)
        for entity_id in sorted(actual - expected):
            self._issue(issues, f"M3_{label}_UNDECLARED", entity_id)

    @staticmethod
    def _issue(issues: list[AssetValidationIssue], code: str, entity_id: str) -> None:
        issues.append(
            AssetValidationIssue(
                severity=AssetValidationSeverity.ERROR,
                code=code,
                message=f"{code}: {entity_id}",
                entity_id=entity_id,
            )
        )
