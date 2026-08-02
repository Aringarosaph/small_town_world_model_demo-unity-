from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from town_core.bridge.runtime import BridgeRuntime
from town_core.catalogs import load_catalog
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import PROTOCOL_VERSION, AnimationSemantic, LocationType, MessageType
from town_core.domain.protocol_models import (
    AssetRegistryMessage,
    AssetRegistryPayload,
    ClientHelloMessage,
    ClientHelloPayload,
    ClientReadyMessage,
    ClientReadyPayload,
    RegisteredInteractionSlot,
    RegisteredLocation,
    RegisteredNpcView,
    RegisteredObject,
)
from town_core.simulation.clock import RuntimeMode
from town_core.simulation.engine import SimulationEngine
from town_core.simulation.initialization import build_initial_world_state

ROOT = Path(__file__).resolve().parents[3]
FIXED_NOW = datetime(2026, 8, 2, tzinfo=UTC)


@pytest.fixture(scope="session")
def catalog() -> CatalogBundle:
    return load_catalog(ROOT / "config" / "v0")


@pytest.fixture
def runtime(catalog: CatalogBundle) -> BridgeRuntime:
    state = build_initial_world_state(catalog, seed=12345, active_agent_id="npc_01")
    engine = SimulationEngine(
        catalog,
        state,
        active_agent_id="npc_01",
        runtime_mode=RuntimeMode.UNITY_LIVE,
    )
    return BridgeRuntime(catalog, engine, now=lambda: FIXED_NOW)


def client_hello(runtime: BridgeRuntime, message_id: str = "msg_10000001") -> ClientHelloMessage:
    return ClientHelloMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.CLIENT_HELLO,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=None,
        payload=ClientHelloPayload(
            client_name="unity",
            unity_editor_version="6000.4.2f1",
            supported_protocol_versions=[cast(Any, PROTOCOL_VERSION)],
        ),
    )


def valid_registry_payload(runtime: BridgeRuntime) -> AssetRegistryPayload:
    state = runtime.engine.state
    semantic_by_type = {
        "BED": AnimationSemantic.SLEEP,
        "FRIDGE": AnimationSemantic.EAT,
        "DINING_SEAT": AnimationSemantic.EAT,
        "WORKSTATION": AnimationSemantic.WORK_STANDING,
    }
    required_ids = [
        "home_a_bed_01",
        "home_a_fridge_01",
        "home_a_dining_seat_01",
        "cafe_bar_workstation_01",
    ]
    objects = []
    for object_id in required_ids:
        source = state.objects[object_id]
        objects.append(
            RegisteredObject(
                object_id=object_id,
                object_type=source.object_type,
                location_id=source.location_id,
                capability_tags=source.capability_tags,
                enabled=True,
                interaction_slots=[
                    RegisteredInteractionSlot(
                        slot_index=0,
                        supported_animation_semantics=[semantic_by_type[source.object_type.value]],
                    )
                ],
            )
        )
    return AssetRegistryPayload(
        locations=[
            RegisteredLocation(location_id="home_a", location_type=LocationType.HOME),
            RegisteredLocation(location_id="cafe_bar", location_type=LocationType.CAFE_BAR),
        ],
        objects=objects,
        npc_views=[RegisteredNpcView(agent_id="npc_01")],
        mapped_animation_semantics=[
            AnimationSemantic.IDLE,
            AnimationSemantic.SLEEP,
            AnimationSemantic.EAT,
            AnimationSemantic.WORK_STANDING,
        ],
    )


def asset_registry(
    runtime: BridgeRuntime,
    message_id: str = "msg_10000002",
    payload: AssetRegistryPayload | None = None,
) -> AssetRegistryMessage:
    return AssetRegistryMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.ASSET_REGISTRY,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=runtime.engine.state.state_version,
        correlation_id=None,
        payload=payload or valid_registry_payload(runtime),
    )


def ready_message(
    runtime: BridgeRuntime,
    state_version: int,
    message_id: str = "msg_10000003",
    registry_message_id: str = "msg_10000002",
) -> ClientReadyMessage:
    return ClientReadyMessage(
        protocol_version=cast(Any, PROTOCOL_VERSION),
        message_id=message_id,
        message_type=MessageType.CLIENT_READY,
        sent_at_utc=FIXED_NOW,
        world_id=runtime.world_id,
        state_version=state_version,
        correlation_id=None,
        payload=ClientReadyPayload(registry_message_id=registry_message_id),
    )


def complete_handshake(runtime: BridgeRuntime) -> Any:
    session = runtime.open_session()
    session.receive_json(client_hello(runtime).model_dump(mode="json"))
    registry_outputs = session.receive_json(asset_registry(runtime).model_dump(mode="json"))
    snapshot = registry_outputs[1]
    session.receive_json(ready_message(runtime, snapshot.state_version).model_dump(mode="json"))
    return session
