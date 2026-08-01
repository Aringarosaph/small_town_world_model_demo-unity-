from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from town_core.catalogs import CatalogValidationError, load_catalog
from town_core.cli import main
from town_core.domain.enums import BehaviorId, EventType, EventWitnessScope, ObjectType

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPO_ROOT / "config" / "v0"


def test_complete_v0_catalog_loads() -> None:
    catalog = load_catalog(CONFIG_ROOT)

    assert len(catalog.population.npcs) == 10
    assert len(catalog.households.households) == 4
    assert len(catalog.locations.locations) == 8
    assert {behavior.behavior_id for behavior in catalog.behaviors.behaviors} == set(BehaviorId)
    assert {item.object_type for item in catalog.objects.object_types} == set(ObjectType)
    assert {item.event_type for item in catalog.events.event_types} == set(EventType)


def test_population_and_economy_match_v0_authority() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    work_counts: dict[str, int] = {}
    for npc in catalog.population.npcs:
        work_counts[npc.assigned_work_location_id] = work_counts.get(npc.assigned_work_location_id, 0) + 1

    assert work_counts == {"cafe_bar": 4, "workshop": 4, "shop": 2}
    assert all(isinstance(household.initial_money, int) for household in catalog.households.households)
    assert all(isinstance(household.initial_food_units, int) for household in catalog.households.households)
    assert catalog.economy.allow_negative_money is False
    assert catalog.economy.allow_negative_food is False


def test_event_visibility_distinguishes_private_and_location_witnesses() -> None:
    catalog = load_catalog(CONFIG_ROOT)
    scope_by_type = {event.event_type: event.witness_scope for event in catalog.events.event_types}

    assert scope_by_type[EventType.APOLOGY_ACCEPTED] is EventWitnessScope.PARTICIPANTS_ONLY
    assert scope_by_type[EventType.CONFLICT_ESCALATED] is EventWitnessScope.HIGH_LEVEL_LOCATION
    assert set(scope_by_type.values()) == set(EventWitnessScope)


def test_cross_reference_error_is_reported(tmp_path: Path) -> None:
    broken_root = tmp_path / "v0"
    shutil.copytree(CONFIG_ROOT, broken_root)
    population_path = broken_root / "population.yaml"
    raw = yaml.safe_load(population_path.read_text(encoding="utf-8"))
    raw["npcs"][0]["home_location_id"] = "missing_home"
    population_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(CatalogValidationError, match="unknown|does not match"):
        load_catalog(broken_root)


def test_cli_command_is_qa_compatible(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate-config", "--config", str(CONFIG_ROOT)])

    assert exit_code == 0
    assert '"valid": true' in capsys.readouterr().out
