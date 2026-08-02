"""Additive M3 society initialization preserving the accepted M1 builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from town_core.catalogs import m3_catalog_hash
from town_core.domain.config_models import CatalogBundle
from town_core.domain.m3_catalog_models import FullTownSemanticManifest, M3Catalogs
from town_core.domain.state_models import InteractionObjectState, WorldState
from town_core.simulation.headless_fixture import HeadlessSemanticObjectFixture
from town_core.simulation.initialization import build_initial_world_state
from town_core.society.checkpoint import initial_authority_log_hash, initial_transaction_chain_hash
from town_core.society.models import AuthorityCheckpoint


class SocietyObjectFixture(Protocol):
    def materialize(self, catalog: CatalogBundle) -> dict[str, InteractionObjectState]: ...


@dataclass(frozen=True, slots=True)
class ManifestSemanticObjectFixture:
    """Materialize the CONTRACTS-owned shared M3 semantic manifest."""

    manifest: FullTownSemanticManifest

    def materialize(self, catalog: CatalogBundle) -> dict[str, InteractionObjectState]:
        configured_types = {item.object_type: item for item in catalog.objects.object_types}
        return {
            instance.object_id: InteractionObjectState(
                object_id=instance.object_id,
                object_type=instance.object_type,
                location_id=instance.location_id,
                capability_tags=list(instance.capability_tags),
                slot_count=instance.slot_count,
                occupied_slots={},
                enabled=True,
                unity_binding_required=configured_types[instance.object_type].unity_binding_required,
                metadata={
                    "runtime_source": "M3_SHARED_MANIFEST",
                    "semantic_profile": self.manifest.profile,
                    **(
                        {"assigned_agent_id": instance.assigned_agent_id}
                        if instance.assigned_agent_id is not None
                        else {}
                    ),
                },
            )
            for instance in self.manifest.objects
        }


def build_initial_society_state(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    *,
    seed: int | None = None,
    object_fixture: SocietyObjectFixture | None = None,
) -> WorldState:
    """Build ten-enabled-NPC state without changing the M1 initialization API.

    The default object source is the CONTRACTS-owned shared M3 manifest. A
    narrow fixture override remains available only for targeted authority tests.
    """

    fixture = object_fixture or ManifestSemanticObjectFixture(m3_catalogs.semantic_instances)
    state = build_initial_world_state(
        catalog,
        seed=seed,
        active_agent_id="npc_01",
        object_fixture=cast(HeadlessSemanticObjectFixture, fixture),
    )
    configured_enabled = {npc.agent_id: npc.enabled for npc in catalog.population.npcs}
    agents = {
        agent_id: agent.model_copy(update={"enabled": configured_enabled[agent_id]})
        for agent_id, agent in state.agents.items()
    }
    society = state.model_copy(update={"agents": agents})
    return WorldState.model_validate(society.model_dump(mode="json", exclude_none=False))


def build_initial_society_checkpoint(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    *,
    seed: int | None = None,
    object_fixture: SocietyObjectFixture | None = None,
) -> AuthorityCheckpoint:
    world = build_initial_society_state(
        catalog,
        m3_catalogs,
        seed=seed,
        object_fixture=object_fixture,
    )
    return AuthorityCheckpoint(
        world=world,
        m3_catalog_hash=m3_catalog_hash(m3_catalogs),
        recent_behaviors={agent_id: None for agent_id in sorted(world.agents)},
        active_need_crises={agent_id: [] for agent_id in sorted(world.agents)},
        low_resource_flags={household_id: [] for household_id in sorted(world.households)},
        authority_log_hash=initial_authority_log_hash(),
        transaction_chain_hash=initial_transaction_chain_hash(world),
    )
