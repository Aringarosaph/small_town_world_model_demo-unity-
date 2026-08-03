from __future__ import annotations

import json
from pathlib import Path

import pytest
from town_core.modeling.analyze_dataset import _ensure_external, _summarize_records
from town_core.modeling.dataset import REPOSITORY_ROOT


def _record(
    *,
    group: str,
    scenario: str,
    selected: bool,
    masks: dict[str, object],
) -> dict[str, object]:
    return {
        "decision_group_id": group,
        "scenario_group_id": scenario,
        "split": "train",
        "behavior_id": "greet",
        "selected_by_teacher": selected,
        "example_json": json.dumps(
            {
                "feature": {"masks": masks},
                "label": {
                    "prediction": {
                        "need_delta_preview": {
                            "hunger": 0.1,
                            "energy": 0.0,
                            "hygiene": 0.0,
                            "fun": 0.0,
                            "social": -0.1,
                        },
                        "actor_mood_delta": {"valence": 0.1, "stress": -0.1},
                        "target_mood_delta": {"valence": 0.1, "stress": 0.0},
                        "relationship_delta_target_to_actor": {
                            "familiarity": 0.1,
                            "affinity": 0.1,
                            "trust": 0.0,
                            "tension": -0.1,
                        },
                    },
                    "resolver_attempted": selected,
                    "resolver_result": "ACCEPTED" if selected else None,
                },
            }
        ),
    }


def test_quality_summary_accepts_complete_group_and_mask_coverage() -> None:
    true_masks: dict[str, object] = {
        "target_present": True,
        "relationship_present": True,
        "acceptance_present": True,
        "target_mood_present": True,
        "relationship_delta_present": True,
        "event_mask": [True, False, False, False],
    }
    false_masks: dict[str, object] = {
        "target_present": False,
        "relationship_present": False,
        "acceptance_present": False,
        "target_mood_present": False,
        "relationship_delta_present": False,
        "event_mask": [False, False, False, False],
    }
    report = _summarize_records(
        [
            _record(group="group_1", scenario="scenario_1", selected=True, masks=true_masks),
            _record(group="group_1", scenario="scenario_1", selected=False, masks=false_masks),
            _record(group="group_2", scenario="scenario_2", selected=True, masks=true_masks),
        ],
        behavior_ids=["greet"],
        acceptance_behavior_ids=["greet"],
        splits=["train"],
        minimum_rows=3,
        minimum_groups=2,
    )

    assert report["passed"] is True
    assert report["selection"]["group_anomaly_count"] == 0  # type: ignore[index]
    assert report["group_size"] == {"minimum": 1, "maximum": 2, "mean": 1.5, "p50": 1, "p95": 2}
    assert report["label_axis_sign_counts"]["relationship.tension"] == {  # type: ignore[index]
        "negative": 3,
        "zero": 0,
        "positive": 0,
    }


def test_quality_summary_rejects_group_without_selection() -> None:
    masks: dict[str, object] = {
        "target_present": True,
        "relationship_present": True,
        "acceptance_present": True,
        "target_mood_present": True,
        "relationship_delta_present": True,
        "event_mask": [True, False, False, False],
    }
    report = _summarize_records(
        [_record(group="group_1", scenario="scenario_1", selected=False, masks=masks)],
        behavior_ids=["greet"],
        acceptance_behavior_ids=["greet"],
        splits=["train"],
        minimum_rows=1,
        minimum_groups=1,
    )

    assert report["passed"] is False
    assert report["gates"]["exactly_one_teacher_selection_per_group"] is False  # type: ignore[index]


def test_quality_output_must_remain_external(tmp_path: Path) -> None:
    _ensure_external(tmp_path / "quality.json")
    with pytest.raises(ValueError, match="outside the repository"):
        _ensure_external(REPOSITORY_ROOT / "forbidden-quality.json")
