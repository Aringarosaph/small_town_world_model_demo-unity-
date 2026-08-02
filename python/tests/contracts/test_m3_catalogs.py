from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from town_core.catalogs import (
    CatalogValidationError,
    load_catalog,
    load_m3_catalogs,
    m3_catalog_hash,
    select_background_dialogue_line,
)
from town_core.domain.enums import BehaviorCategory, BehaviorId, ObjectType
from town_core.simulation.initialization import catalog_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPO_ROOT / "config" / "v0"
ACCEPTED_M1_CATALOG_HASH = "6e6c688145ff74ed5326e00bebad3f86e38b5560c6469deaf65f505afe20d5cf"
M3_CATALOG_HASH = "cd7e8b1161f3bbddc1e68b8495815a7cd80cd65dd097287ab34d228efc655340"


def test_m3_catalogs_load_without_changing_accepted_m1_hash() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    m3 = load_m3_catalogs(CONFIG_ROOT, catalog=catalog)

    assert catalog_hash(catalog) == ACCEPTED_M1_CATALOG_HASH
    assert m3_catalog_hash(m3) == M3_CATALOG_HASH
    assert len(m3.semantic_instances.objects) == 74
    assert {item.object_type for item in m3.semantic_instances.objects} == set(ObjectType)


def test_full_town_manifest_has_exact_identity_and_capacity_contracts() -> None:
    m3 = load_m3_catalogs(CONFIG_ROOT)
    manifest = m3.semantic_instances

    assert manifest.profile == "M3_FULL"
    assert len(manifest.location_ids) == 8
    assert len(manifest.npc_view_ids) == 10
    assert manifest.require_entrance_slot_reachability is True
    assert set(manifest.required_prop_semantics) == {"MEAL", "GROCERY_BAG", "DRINK", "EVENT_ICON"}
    assert set(manifest.facing_behavior_ids) == {
        BehaviorId.GREET,
        BehaviorId.CHAT,
        BehaviorId.JOKE,
        BehaviorId.COMPLIMENT,
        BehaviorId.SHARE_EVENT,
        BehaviorId.INVITE_JOIN,
        BehaviorId.APOLOGIZE,
        BehaviorId.CONFRONT,
    }


def test_background_dialogue_is_complete_nonempty_chinese_and_deterministic() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    dialogue = load_m3_catalogs(CONFIG_ROOT, catalog=catalog).background_dialogue
    social = {item.behavior_id for item in catalog.behaviors.behaviors if item.category is BehaviorCategory.SOCIAL}
    default_coverage = {item.behavior_id for item in dialogue.templates if item.outcome == "DEFAULT"}

    assert default_coverage == social
    assert dialogue.fallback_line.strip()
    assert any("\u4e00" <= character <= "\u9fff" for character in dialogue.fallback_line)
    assert all(line.strip() for template in dialogue.templates for line in template.lines)
    assert all(
        any("\u4e00" <= character <= "\u9fff" for character in line)
        for template in dialogue.templates
        for line in template.lines
    )
    first = select_background_dialogue_line(
        dialogue,
        behavior_id=BehaviorId.CHAT,
        outcome="ACCEPTED",
        deterministic_key="action_0001",
    )
    second = select_background_dialogue_line(
        dialogue,
        behavior_id=BehaviorId.CHAT,
        outcome="ACCEPTED",
        deterministic_key="action_0001",
    )
    assert first == second and first


def test_manifest_capacity_drift_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "v0"
    shutil.copytree(CONFIG_ROOT, broken)
    path = broken / "semantic_instances.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["objects"] = [item for item in raw["objects"] if item["object_id"] != "home_b_bed_03"]
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="bed"):
        load_m3_catalogs(broken)
