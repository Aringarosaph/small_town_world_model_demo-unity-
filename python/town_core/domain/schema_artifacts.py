"""Deterministically generate committed JSON Schema and example artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from town_core.domain.config_models import CatalogBundle
from town_core.domain.decision_models import CandidateAction, JointAction, OutcomePrediction, StateTransaction
from town_core.domain.dialogue_models import PlayerSpeechParse, SpeechPlan
from town_core.domain.protocol_models import PerceptionSnapshot, ProtocolMessage
from town_core.domain.state_models import WorldState

SCHEMA_ADAPTERS: Mapping[str, TypeAdapter[Any]] = {
    "catalog-bundle": TypeAdapter(CatalogBundle),
    "world-state": TypeAdapter(WorldState),
    "candidate-action": TypeAdapter(CandidateAction),
    "outcome-prediction": TypeAdapter(OutcomePrediction),
    "joint-action": TypeAdapter(JointAction),
    "state-transaction": TypeAdapter(StateTransaction),
    "protocol-message": TypeAdapter(ProtocolMessage),
    "perception-snapshot": TypeAdapter(PerceptionSnapshot),
    "player-speech-parse": TypeAdapter(PlayerSpeechParse),
    "speech-plan": TypeAdapter(SpeechPlan),
}


EXAMPLES: Mapping[str, tuple[TypeAdapter[Any], dict[str, Any]]] = {
    "client-hello": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.1.0",
            "message_id": "msg_000001",
            "message_type": "client_hello",
            "sent_at_utc": "2026-01-01T00:00:00Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": None,
            "payload": {
                "client_name": "unity",
                "unity_editor_version": "6000.4.2f1",
                "supported_protocol_versions": ["0.1.0"],
            },
        },
    ),
    "action-started": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.1.0",
            "message_id": "msg_000042",
            "message_type": "action_started",
            "sent_at_utc": "2026-01-01T00:10:00Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "action_0000098",
            "payload": {
                "action_id": "action_0000098",
                "agent_ids": ["npc_03"],
                "behavior_id": "eat_at_home",
                "destination_location_id": "home_b",
                "target_object_ids": ["home_b_fridge_01", "home_b_seat_02"],
                "animation_semantic": "EAT",
                "prop_semantic": "MEAL",
                "planned_duration_minutes": 30,
            },
        },
    ),
    "movement-arrived": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.1.0",
            "message_id": "msg_000043",
            "message_type": "movement_arrived",
            "sent_at_utc": "2026-01-01T00:11:00Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "action_0000098",
            "payload": {
                "action_id": "action_0000098",
                "agent_id": "npc_03",
                "object_id": "home_b_fridge_01",
                "slot_index": 0,
            },
        },
    ),
    "player-utterance": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.1.0",
            "message_id": "msg_000044",
            "message_type": "player_utterance",
            "sent_at_utc": "2026-01-01T00:12:00Z",
            "world_id": "demo_world",
            "state_version": 1030,
            "correlation_id": "conversation_00042",
            "payload": {
                "conversation_id": "conversation_00042",
                "player_id": "player",
                "target_agent_id": "npc_05",
                "text": "Why are you angry with npc_03?",
                "client_state_version": 1030,
            },
        },
    ),
    "perception-snapshot": (
        TypeAdapter(PerceptionSnapshot),
        {
            "observer_agent_id": "npc_03",
            "game_minute": 900,
            "authority": "HIGH_LEVEL_LOCATION",
            "authoritative_location_id": "workshop",
            "perceived_agents": [{"agent_id": "npc_04", "location_id": "workshop"}],
            "perceived_objects": [
                {
                    "object_id": "workshop_station_01",
                    "object_type": "WORKSTATION",
                    "location_id": "workshop",
                    "enabled": True,
                }
            ],
        },
    ),
    "outcome-prediction": (
        TypeAdapter(OutcomePrediction),
        {
            "prediction_id": "prediction_0007",
            "candidate_id": "candidate_0012",
            "need_delta_preview": {"hunger": 0.0, "energy": 0.0, "hygiene": 0.0, "fun": 0.03, "social": 0.08},
            "actor_mood_delta": {"valence": 0.02, "stress": -0.01},
            "target_mood_delta": {"valence": 0.04, "stress": -0.02},
            "relationship_direction": "TARGET_TO_ACTOR",
            "relationship_delta_target_to_actor": {
                "familiarity": 0.01,
                "affinity": 0.04,
                "trust": 0.02,
                "tension": -0.03,
            },
            "acceptance_probability": 0.78,
            "event_probabilities": {"POSITIVE_INTERACTION": 0.62, "AWKWARD_INTERACTION": 0.08},
        },
    ),
    "joint-action": (
        TypeAdapter(JointAction),
        {
            "action_id": "action_0000101",
            "behavior_id": "watch_tv",
            "authority": "CENTRAL_RESOLVER",
            "state_version": 1031,
            "location_id": "home_b",
            "participants": [
                {"agent_id": "npc_03", "proposal_id": "proposal_0011"},
                {"agent_id": "npc_04", "proposal_id": "proposal_0012"},
            ],
        },
    ),
    "player-speech-parse": (
        TypeAdapter(PlayerSpeechParse),
        {
            "speech_act": "ASK_ABOUT_EVENT",
            "target_agent_id": "npc_08",
            "referenced_agent_ids": ["npc_03"],
            "referenced_event_ids": ["event_00001234"],
            "invite_activity": None,
            "tone": {"warmth": 0.3, "hostility": 0.1, "urgency": 0.4},
            "claims": [],
            "confidence": 0.86,
            "requires_clarification": False,
        },
    ),
}


VERSION_DOCUMENT = {
    "protocol_version": "0.1.0",
    "schema_version": "v0.1",
    "config_version": "v0",
    "feature_version": "v0.1",
    "python_version": "3.12",
    "unity_editor": "6000.4.2f1",
    "compatibility": {"breaking_changes_require_protocol_bump": True},
    "frozen_decisions": {
        "relationship_prediction": "TARGET_TO_ACTOR",
        "joint_action_authority": "CENTRAL_RESOLVER",
        "perception_authority": "HIGH_LEVEL_LOCATION",
        "route_planning": "DISABLED",
        "event_witness_scopes": ["PARTICIPANTS_ONLY", "HIGH_LEVEL_LOCATION"],
    },
}


def _dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def build_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    schemas = {
        name: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:ai-town:protocol:0.1.0:{name}",
            **adapter.json_schema(),
        }
        for name, adapter in SCHEMA_ADAPTERS.items()
    }
    examples: dict[str, Any] = {}
    for name, (adapter, raw) in EXAMPLES.items():
        value = adapter.validate_python(raw)
        examples[name] = json.loads(adapter.dump_json(value, exclude_none=False))
    return schemas, examples


def write_artifacts(output_root: Path) -> None:
    schemas, examples = build_artifacts()
    _dump_json(output_root / "version.json", VERSION_DOCUMENT)
    for name, schema in schemas.items():
        _dump_json(output_root / "jsonschema" / f"{name}.schema.json", schema)
    for name, example in examples.items():
        _dump_json(output_root / "examples" / f"{name}.json", example)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("protocol"))
    args = parser.parse_args()
    write_artifacts(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
