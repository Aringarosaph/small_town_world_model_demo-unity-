"""Explicit semantic-object fixture for the one-NPC M1 Headless slice."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import CapabilityTag, ObjectType
from town_core.domain.state_models import InteractionObjectState


@dataclass(frozen=True, slots=True)
class HeadlessSemanticObjectFixture:
    """Materialize catalog-typed objects without claiming Unity asset identity."""

    fixture_id: str = "stwm.m1.headless-semantic-objects/v1"

    def materialize(self, catalog: CatalogBundle) -> dict[str, InteractionObjectState]:
        type_by_id = {item.object_type: item for item in catalog.objects.object_types}
        objects: dict[str, InteractionObjectState] = {}

        def add_object(
            object_id: str,
            object_type: ObjectType,
            location_id: str,
            capability_tags: list[CapabilityTag] | None = None,
            metadata: dict[str, str] | None = None,
        ) -> None:
            definition = type_by_id[object_type]
            objects[object_id] = InteractionObjectState(
                object_id=object_id,
                object_type=object_type,
                location_id=location_id,
                capability_tags=capability_tags or list(definition.capability_tags),
                slot_count=definition.default_slot_count,
                occupied_slots={},
                enabled=True,
                unity_binding_required=definition.unity_binding_required,
                metadata=metadata or {"runtime_source": "HEADLESS_M1", "fixture_id": self.fixture_id},
            )

        for household in sorted(catalog.households.households, key=lambda item: item.household_id):
            home_id = household.home_location_id
            add_object(f"{home_id}_fridge_01", ObjectType.FRIDGE, home_id)
            for index, agent_id in enumerate(sorted(household.member_ids), start=1):
                metadata = {
                    "runtime_source": "HEADLESS_M1",
                    "fixture_id": self.fixture_id,
                    "assigned_agent_id": agent_id,
                }
                add_object(f"{home_id}_bed_{index:02d}", ObjectType.BED, home_id, metadata=metadata)
                add_object(f"{home_id}_dining_seat_{index:02d}", ObjectType.DINING_SEAT, home_id, metadata=metadata)

        workstation_index: defaultdict[str, int] = defaultdict(int)
        for npc in sorted(catalog.population.npcs, key=lambda item: item.agent_id):
            location_id = npc.assigned_work_location_id
            workstation_index[location_id] += 1
            index = workstation_index[location_id]
            add_object(
                f"{location_id}_workstation_{index:02d}",
                ObjectType.WORKSTATION,
                location_id,
                capability_tags=[CapabilityTag.WORK, npc.assigned_workstation_tag],
                metadata={
                    "runtime_source": "HEADLESS_M1",
                    "fixture_id": self.fixture_id,
                    "assigned_agent_id": npc.agent_id,
                    "workstation_tag": npc.assigned_workstation_tag.value,
                },
            )
        return objects


DEFAULT_M1_HEADLESS_FIXTURE = HeadlessSemanticObjectFixture()
