from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from town_core.domain.decision_models import CandidateAction, JointAction, OutcomePrediction
from town_core.domain.protocol_models import PerceptionSnapshot
from town_core.domain.state_models import HouseholdState


def test_relationship_prediction_is_target_to_actor_only() -> None:
    raw: dict[str, Any] = {
        "prediction_id": "prediction_0001",
        "candidate_id": "candidate_0001",
        "need_delta_preview": {"hunger": 0, "energy": 0, "hygiene": 0, "fun": 0, "social": 0},
        "actor_mood_delta": {"valence": 0, "stress": 0},
        "target_mood_delta": {"valence": 0, "stress": 0},
        "relationship_direction": "ACTOR_TO_TARGET",
        "relationship_delta_target_to_actor": {"familiarity": 0, "affinity": 0, "trust": 0, "tension": 0},
        "acceptance_probability": 0.5,
        "event_probabilities": {},
    }

    with pytest.raises(ValidationError):
        OutcomePrediction.model_validate(raw)


def test_joint_action_requires_central_authority_and_stable_order() -> None:
    raw: dict[str, Any] = {
        "action_id": "action_0001",
        "behavior_id": "watch_tv",
        "authority": "CENTRAL_RESOLVER",
        "state_version": 1,
        "location_id": "home_a",
        "participants": [
            {"agent_id": "npc_02", "proposal_id": "proposal_0002"},
            {"agent_id": "npc_01", "proposal_id": "proposal_0001"},
        ],
    }

    with pytest.raises(ValidationError, match="agent ID order"):
        JointAction.model_validate(raw)

    raw["participants"].reverse()
    assert JointAction.model_validate(raw).authority == "CENTRAL_RESOLVER"


def test_perception_is_limited_to_authoritative_high_level_location() -> None:
    raw = {
        "observer_agent_id": "npc_01",
        "game_minute": 10,
        "authority": "HIGH_LEVEL_LOCATION",
        "authoritative_location_id": "home_a",
        "perceived_agents": [{"agent_id": "npc_02", "location_id": "park"}],
        "perceived_objects": [],
    }

    with pytest.raises(ValidationError, match="high-level location"):
        PerceptionSnapshot.model_validate(raw)


def test_candidate_contract_has_no_route_or_waypoint_capability() -> None:
    raw = {
        "candidate_id": "candidate_0001",
        "actor_id": "npc_01",
        "behavior_id": "sleep",
        "target_agent_id": None,
        "target_object_ids": ["home_a_bed_01"],
        "destination_location_id": "home_a",
        "estimated_travel_minutes": 0,
        "estimated_duration_minutes": 120,
        "hard_cost_preview": {"household_money": 0, "household_food_units": 0},
        "schedule_conflict_minutes": 0,
        "context_event_ids": [],
        "route_planning": "DISABLED",
        "waypoints": ["door_01"],
    }

    with pytest.raises(ValidationError, match="Extra inputs"):
        CandidateAction.model_validate(raw)


def test_household_resources_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        HouseholdState(
            household_id="household_a",
            member_ids=["npc_01"],
            home_location_id="home_a",
            money=-1,
            food_units=0,
        )
