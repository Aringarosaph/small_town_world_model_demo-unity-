from __future__ import annotations

from collections import Counter
from typing import Any, cast

from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId, ObjectType
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint


def test_society_initialization_enables_ten_and_preserves_directed_edges(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)

    assert sorted(agent_id for agent_id, agent in checkpoint.world.agents.items() if agent.enabled) == [
        f"npc_{index:02d}" for index in range(1, 11)
    ]
    assert len(checkpoint.world.relationships) == 90
    assert {item.object_type for item in checkpoint.world.objects.values()} == set(ObjectType)
    assert checkpoint.world.event_cursor == 0
    assert checkpoint.world.state_version == 0


def test_four_behavior_bootstrap_uses_one_snapshot_and_global_ids(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=12345)
    allowlist = frozenset(
        {
            BehaviorId.IDLE,
            BehaviorId.SLEEP,
            BehaviorId.EAT_AT_HOME,
            BehaviorId.WORK_SHIFT,
        }
    )
    result = SocietyEngine(catalog, m3_catalogs, checkpoint, behavior_allowlist=allowlist).advance_to(1)
    decisions = cast(list[dict[str, Any]], result.decisions)

    assert len(decisions) == 10
    assert {item["source_state_version"] for item in decisions} == {0}
    assert all(len(item["candidates"]) <= 12 for item in decisions)
    assert sum(len(item["candidates"]) for item in decisions) <= 120
    assert {str(item["selected_behavior_id"]) for item in decisions} <= {item.value for item in allowlist}
    candidate_ids = [
        str(candidate["candidate"]["candidate"]["candidate_id"])
        for decision in decisions
        for candidate in decision["candidates"]
    ]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert sorted(candidate_ids) == [f"candidate_{index:08d}" for index in range(1, len(candidate_ids) + 1)]
    action_ids = sorted({str(item["action_id"]) for item in result.actions if str(item["phase"]) == "CREATED"})
    assert action_ids == [f"action_{index:08d}" for index in range(1, 11)]
    assert Counter(action["phase"] for action in result.actions)["CREATED"] == 10
