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
from town_core.domain.m3_catalog_models import BackgroundDialogueCatalog, FullTownSemanticManifest
from town_core.domain.m3_models import JointActionPresentationMetadata, M3CandidateAction
from town_core.domain.protocol_models import (
    ClientHelloBootstrapMessage,
    ClientHelloMessage,
    ClientHelloV030Message,
    PerceptionSnapshot,
    ProtocolMessage,
    ProtocolMessageV010,
    ProtocolMessageV020,
    ProtocolMessageV030,
    PythonToUnityMessage,
    PythonToUnityMessageV020,
    PythonToUnityMessageV030,
    UnityToPythonMessage,
    UnityToPythonMessageV020,
    UnityToPythonMessageV030,
)
from town_core.domain.state_models import WorldState

SCHEMA_ADAPTERS: Mapping[str, TypeAdapter[Any]] = {
    "catalog-bundle": TypeAdapter(CatalogBundle),
    "world-state": TypeAdapter(WorldState),
    "candidate-action": TypeAdapter(CandidateAction),
    "outcome-prediction": TypeAdapter(OutcomePrediction),
    "joint-action": TypeAdapter(JointAction),
    "state-transaction": TypeAdapter(StateTransaction),
    "protocol-message": TypeAdapter(ProtocolMessage),
    "protocol-message-v010-compat": TypeAdapter(ProtocolMessageV010),
    "client-hello-bootstrap": TypeAdapter(ClientHelloMessage),
    "python-to-unity-message": TypeAdapter(PythonToUnityMessage),
    "unity-to-python-message": TypeAdapter(UnityToPythonMessage),
    "perception-snapshot": TypeAdapter(PerceptionSnapshot),
    "player-speech-parse": TypeAdapter(PlayerSpeechParse),
    "speech-plan": TypeAdapter(SpeechPlan),
    "m3-candidate-action": TypeAdapter(M3CandidateAction),
    "m3-joint-action-presentation": TypeAdapter(JointActionPresentationMetadata),
    "m3-semantic-instances": TypeAdapter(FullTownSemanticManifest),
    "m3-background-dialogue": TypeAdapter(BackgroundDialogueCatalog),
    "protocol-message-v030": TypeAdapter(ProtocolMessageV030),
    "client-hello-bootstrap-v030": TypeAdapter(ClientHelloV030Message),
    "python-to-unity-message-v030": TypeAdapter(PythonToUnityMessageV030),
    "unity-to-python-message-v030": TypeAdapter(UnityToPythonMessageV030),
    "protocol-message-v020-compat": TypeAdapter(ProtocolMessageV020),
    "python-to-unity-message-v020-compat": TypeAdapter(PythonToUnityMessageV020),
    "unity-to-python-message-v020-compat": TypeAdapter(UnityToPythonMessageV020),
    "client-hello-bootstrap-all": TypeAdapter(ClientHelloBootstrapMessage),
}


EXAMPLES: Mapping[str, tuple[TypeAdapter[Any], dict[str, Any]]] = {
    "client-hello": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000001",
            "message_type": "client_hello",
            "sent_at_utc": "2026-01-01T00:00:00Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": None,
            "payload": {
                "client_name": "unity",
                "unity_editor_version": "6000.4.2f1",
                "supported_protocol_versions": ["0.2.0", "0.1.0"],
            },
        },
    ),
    "client-hello-v010-compat": (
        TypeAdapter(ProtocolMessageV010),
        {
            "protocol_version": "0.1.0",
            "message_id": "msg_000002",
            "message_type": "client_hello",
            "sent_at_utc": "2026-01-01T00:00:01Z",
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
    "server-hello": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000003",
            "message_type": "server_hello",
            "sent_at_utc": "2026-01-01T00:00:02Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": "msg_000001",
            "payload": {
                "server_name": "python_town_core",
                "accepted_protocol_version": "0.2.0",
                "config_version": "v0",
                "schema_version": "v0.1",
            },
        },
    ),
    "asset-registry": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000004",
            "message_type": "asset_registry",
            "sent_at_utc": "2026-01-01T00:00:03Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": "msg_000001",
            "payload": {
                "locations": [
                    {"location_id": "home_a", "location_type": "HOME"},
                    {"location_id": "cafe_bar", "location_type": "CAFE_BAR"},
                ],
                "objects": [
                    {
                        "object_id": "home_a_bed_01",
                        "object_type": "BED",
                        "location_id": "home_a",
                        "capability_tags": ["SLEEP"],
                        "enabled": True,
                        "interaction_slots": [{"slot_index": 0, "supported_animation_semantics": ["SLEEP"]}],
                    },
                    {
                        "object_id": "cafe_bar_workstation_01",
                        "object_type": "WORKSTATION",
                        "location_id": "cafe_bar",
                        "capability_tags": ["WORK", "CAFE_MORNING"],
                        "enabled": True,
                        "interaction_slots": [{"slot_index": 0, "supported_animation_semantics": ["WORK_STANDING"]}],
                    },
                ],
                "npc_views": [{"agent_id": "npc_01"}],
                "mapped_animation_semantics": ["WALK", "SLEEP", "WORK_STANDING"],
            },
        },
    ),
    "asset-registry-result": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000005",
            "message_type": "asset_registry_result",
            "sent_at_utc": "2026-01-01T00:00:04Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": "msg_000004",
            "payload": {
                "accepted": True,
                "issues": [
                    {
                        "severity": "WARNING",
                        "code": "M2_FULL_V0_LOCATION_MISSING",
                        "message": "A full-V0 location is outside the blocking M2 profile",
                        "entity_id": "park",
                    }
                ],
            },
        },
    ),
    "client-ready": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000007",
            "message_type": "client_ready",
            "sent_at_utc": "2026-01-01T00:00:06Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "msg_000004",
            "payload": {"registry_message_id": "msg_000004"},
        },
    ),
    "reconnect-world-snapshot": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000006",
            "message_type": "world_snapshot",
            "sent_at_utc": "2026-01-01T00:00:05Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "msg_000004",
            "payload": {
                "world": {
                    "schema_version": "v0.1",
                    "world_id": "demo_world",
                    "game_minute": 1024,
                    "random_seed": 12345,
                    "state_version": 1024,
                    "agents": {},
                    "households": {},
                    "locations": {},
                    "objects": {},
                    "relationships": [],
                    "active_actions": {},
                    "dialogue_session_ids": [],
                    "event_cursor": 0,
                    "model_version": None,
                    "config_hash": "0" * 64,
                }
            },
        },
    ),
    "action-started": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
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
            "protocol_version": "0.2.0",
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
    "movement-failed": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000045",
            "message_type": "movement_failed",
            "sent_at_utc": "2026-01-01T00:11:01Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "action_0000098",
            "payload": {"action_id": "action_0000098", "agent_id": "npc_03", "reason": "NO_PATH"},
        },
    ),
    "movement-cancelled": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000046",
            "message_type": "movement_cancelled",
            "sent_at_utc": "2026-01-01T00:11:02Z",
            "world_id": "demo_world",
            "state_version": 1024,
            "correlation_id": "action_0000098",
            "payload": {
                "action_id": "action_0000098",
                "agent_id": "npc_03",
                "reason": "NAVIGATION_STOPPED",
            },
        },
    ),
    "action-cancelled": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000047",
            "message_type": "action_cancelled",
            "sent_at_utc": "2026-01-01T00:11:03Z",
            "world_id": "demo_world",
            "state_version": 1025,
            "correlation_id": "action_0000098",
            "payload": {"action_id": "action_0000098", "reason": "MOVEMENT_CANCELLED"},
        },
    ),
    "presentation-completed": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
            "message_id": "msg_000048",
            "message_type": "presentation_completed",
            "sent_at_utc": "2026-01-01T00:11:04Z",
            "world_id": "demo_world",
            "state_version": 1025,
            "correlation_id": "action_0000098",
            "payload": {"action_id": "action_0000098", "agent_id": "npc_03"},
        },
    ),
    "player-utterance": (
        TypeAdapter(ProtocolMessage),
        {
            "protocol_version": "0.2.0",
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
    "client-hello-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000301",
            "message_type": "client_hello",
            "sent_at_utc": "2026-08-02T12:00:00Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": None,
            "payload": {
                "client_name": "unity",
                "unity_editor_version": "6000.4.2f1",
                "supported_protocol_versions": ["0.3.0", "0.2.0"],
            },
        },
    ),
    "server-hello-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000302",
            "message_type": "server_hello",
            "sent_at_utc": "2026-08-02T12:00:01Z",
            "world_id": "demo_world",
            "state_version": 0,
            "correlation_id": "msg_000301",
            "payload": {
                "server_name": "python_town_core",
                "accepted_protocol_version": "0.3.0",
                "config_version": "v0",
                "schema_version": "v0.1",
            },
        },
    ),
    "action-started-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000303",
            "message_type": "action_started",
            "sent_at_utc": "2026-08-02T12:00:02Z",
            "world_id": "demo_world",
            "state_version": 42,
            "correlation_id": "action_00000301",
            "payload": {
                "action_id": "action_00000301",
                "behavior_id": "chat",
                "destination_location_id": "park",
                "participants": [
                    {
                        "agent_id": "npc_01",
                        "role": "ACTOR",
                        "object_bindings": [{"object_id": "park_conversation_01", "slot_index": 0}],
                        "facing_target": {"target_agent_id": "npc_02", "target_object_id": None},
                        "animation_semantic": "TALK_NEUTRAL",
                        "prop_semantic": None,
                    },
                    {
                        "agent_id": "npc_02",
                        "role": "TARGET",
                        "object_bindings": [{"object_id": "park_conversation_01", "slot_index": 1}],
                        "facing_target": {"target_agent_id": "npc_01", "target_object_id": None},
                        "animation_semantic": "TALK_NEUTRAL",
                        "prop_semantic": None,
                    },
                ],
                "is_joint": True,
                "conversation_id": "conversation_000301",
                "planned_duration_minutes": 12,
            },
        },
    ),
    "reconnect-world-snapshot-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000304",
            "message_type": "world_snapshot",
            "sent_at_utc": "2026-08-02T12:00:03Z",
            "world_id": "demo_world",
            "state_version": 42,
            "correlation_id": "msg_000301",
            "payload": {
                "world": {
                    "schema_version": "v0.1",
                    "world_id": "demo_world",
                    "game_minute": 600,
                    "random_seed": 12345,
                    "state_version": 42,
                    "agents": {},
                    "households": {},
                    "locations": {},
                    "objects": {},
                    "relationships": [],
                    "active_actions": {
                        "action_00000301": {
                            "action_id": "action_00000301",
                            "behavior_id": "chat",
                            "agent_ids": ["npc_01", "npc_02"],
                            "phase": "PERFORMING",
                            "destination_location_id": "park",
                            "target_object_ids": ["park_conversation_01"],
                            "started_at_game_minute": 598,
                            "planned_end_game_minute": 610,
                        }
                    },
                    "dialogue_session_ids": ["conversation_000301"],
                    "event_cursor": 10,
                    "model_version": None,
                    "config_hash": "0" * 64,
                },
                "active_presentations": [
                    {
                        "action_id": "action_00000301",
                        "behavior_id": "chat",
                        "phase": "PERFORMING",
                        "destination_location_id": "park",
                        "participants": [
                            {
                                "agent_id": "npc_01",
                                "role": "ACTOR",
                                "object_bindings": [{"object_id": "park_conversation_01", "slot_index": 0}],
                                "facing_target": {"target_agent_id": "npc_02", "target_object_id": None},
                                "animation_semantic": "TALK_NEUTRAL",
                                "prop_semantic": None,
                            },
                            {
                                "agent_id": "npc_02",
                                "role": "TARGET",
                                "object_bindings": [{"object_id": "park_conversation_01", "slot_index": 1}],
                                "facing_target": {"target_agent_id": "npc_01", "target_object_id": None},
                                "animation_semantic": "TALK_NEUTRAL",
                                "prop_semantic": None,
                            },
                        ],
                        "is_joint": True,
                        "conversation_id": "conversation_000301",
                        "planned_end_game_minute": 610,
                    }
                ],
            },
        },
    ),
    "agent-state-delta-clear-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000305",
            "message_type": "agent_state_delta",
            "sent_at_utc": "2026-08-02T12:00:04Z",
            "world_id": "demo_world",
            "state_version": 43,
            "correlation_id": "action_00000301",
            "payload": {
                "agent_id": "npc_01",
                "field_mask": ["current_action_id"],
                "current_action_id": None,
            },
        },
    ),
    "household-state-delta-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000306",
            "message_type": "household_state_delta",
            "sent_at_utc": "2026-08-02T12:00:05Z",
            "world_id": "demo_world",
            "state_version": 44,
            "correlation_id": "action_00000302",
            "payload": {
                "household_id": "household_a",
                "field_mask": ["money", "food_units"],
                "money": 145,
                "food_units": 12,
            },
        },
    ),
    "debug-decision-trace-v030": (
        TypeAdapter(ProtocolMessageV030),
        {
            "protocol_version": "0.3.0",
            "message_id": "msg_000307",
            "message_type": "debug_decision_trace",
            "sent_at_utc": "2026-08-02T12:00:06Z",
            "world_id": "demo_world",
            "state_version": 45,
            "correlation_id": "decision_000301",
            "payload": {
                "decision_id": "decision_000301",
                "agent_id": "npc_01",
                "trigger": "DECISION_DUE",
                "source_state_version": 44,
                "candidates": [
                    {
                        "rank": 1,
                        "candidate_id": "candidate_000301",
                        "proposal_id": "proposal_000301",
                        "behavior_id": "eat_at_home",
                        "actor_id": "npc_01",
                        "target_agent_id": None,
                        "selected_context_event_id": None,
                        "target_conversation_id": None,
                        "invited_activity_id": None,
                        "destination_location_id": "home_a",
                        "hard_preview": {
                            "household_money_delta": 0,
                            "household_food_units_delta": -1,
                            "object_bindings": [
                                {"object_id": "home_a_fridge_01", "slot_index": 0},
                                {"object_id": "home_a_dining_seat_01", "slot_index": 0},
                            ],
                            "reservation_keys": ["slot:home_a_dining_seat_01:0", "food:household_a:1"],
                            "settlement_keys": ["meal:action_00000302"],
                        },
                        "prediction": {
                            "prediction_id": "prediction_000301",
                            "candidate_id": "candidate_000301",
                            "need_delta_preview": {
                                "hunger": 0.6,
                                "energy": 0.0,
                                "hygiene": 0.0,
                                "fun": 0.0,
                                "social": 0.0,
                            },
                            "actor_mood_delta": {"valence": 0.04, "stress": 0.0},
                            "target_mood_delta": None,
                            "relationship_direction": "TARGET_TO_ACTOR",
                            "relationship_delta_target_to_actor": None,
                            "acceptance_probability": None,
                            "event_probabilities": {"MEAL_CONSUMED": 1.0},
                        },
                        "utility_terms": {"needs": 1.2, "money_cost": 0.0},
                        "total_score": 1.2,
                        "resolver_result": "ACCEPTED",
                        "conflict_code": None,
                    },
                    {
                        "rank": 2,
                        "candidate_id": "candidate_000302",
                        "proposal_id": "proposal_000302",
                        "behavior_id": "work_shift",
                        "actor_id": "npc_01",
                        "target_agent_id": None,
                        "selected_context_event_id": None,
                        "target_conversation_id": None,
                        "invited_activity_id": None,
                        "destination_location_id": "cafe_bar",
                        "hard_preview": {
                            "household_money_delta": 0,
                            "household_food_units_delta": 0,
                            "object_bindings": [{"object_id": "cafe_bar_workstation_01", "slot_index": 0}],
                            "reservation_keys": ["slot:cafe_bar_workstation_01:0"],
                            "settlement_keys": ["wage:npc_01:day_0000"],
                        },
                        "prediction": {
                            "prediction_id": "prediction_000302",
                            "candidate_id": "candidate_000302",
                            "need_delta_preview": {
                                "hunger": 0.0,
                                "energy": -0.2,
                                "hygiene": -0.1,
                                "fun": -0.1,
                                "social": 0.0,
                            },
                            "actor_mood_delta": {"valence": 0.0, "stress": 0.05},
                            "target_mood_delta": None,
                            "relationship_direction": "TARGET_TO_ACTOR",
                            "relationship_delta_target_to_actor": None,
                            "acceptance_probability": None,
                            "event_probabilities": {"WORK_STARTED": 1.0},
                        },
                        "utility_terms": {"schedule": 0.9, "travel_cost": -0.2},
                        "total_score": 0.7,
                        "resolver_result": "OBJECT_SLOT_CONFLICT",
                        "conflict_code": "WORKSTATION_RESERVED",
                    },
                    {
                        "rank": 3,
                        "candidate_id": "candidate_000303",
                        "proposal_id": None,
                        "behavior_id": "idle",
                        "actor_id": "npc_01",
                        "target_agent_id": None,
                        "selected_context_event_id": None,
                        "target_conversation_id": None,
                        "invited_activity_id": None,
                        "destination_location_id": "home_a",
                        "hard_preview": {
                            "household_money_delta": 0,
                            "household_food_units_delta": 0,
                            "object_bindings": [],
                            "reservation_keys": [],
                            "settlement_keys": [],
                        },
                        "prediction": {
                            "prediction_id": "prediction_000303",
                            "candidate_id": "candidate_000303",
                            "need_delta_preview": {
                                "hunger": 0.0,
                                "energy": 0.0,
                                "hygiene": 0.0,
                                "fun": 0.0,
                                "social": 0.0,
                            },
                            "actor_mood_delta": {"valence": 0.0, "stress": -0.01},
                            "target_mood_delta": None,
                            "relationship_direction": "TARGET_TO_ACTOR",
                            "relationship_delta_target_to_actor": None,
                            "acceptance_probability": None,
                            "event_probabilities": {},
                        },
                        "utility_terms": {"idle_penalty": -0.1},
                        "total_score": -0.1,
                        "resolver_result": None,
                        "conflict_code": None,
                    },
                ],
                "selected_candidate_id": "candidate_000301",
                "selected_proposal_id": "proposal_000301",
            },
        },
    ),
    "m3-candidate-action": (
        TypeAdapter(M3CandidateAction),
        {
            "candidate_id": "candidate_000401",
            "actor_id": "npc_01",
            "behavior_id": "invite_join",
            "target_agent_id": "npc_02",
            "target_object_ids": [],
            "destination_location_id": "park",
            "estimated_travel_minutes": 0,
            "estimated_duration_minutes": 5,
            "hard_cost_preview": {"household_money": 0, "household_food_units": 0},
            "schedule_conflict_minutes": 0,
            "context_event_ids": [],
            "route_planning": "DISABLED",
            "selected_context_event_id": None,
            "target_conversation_id": None,
            "invited_activity_id": "walk_in_park",
        },
    ),
    "m3-joint-action-presentation": (
        TypeAdapter(JointActionPresentationMetadata),
        {
            "action_id": "action_00000401",
            "behavior_id": "walk_in_park",
            "invited_activity_id": "walk_in_park",
            "authority": "CENTRAL_RESOLVER",
            "source_state_version": 50,
            "location_id": "park",
            "conversation_id": "conversation_000401",
            "phase": "TRAVELING",
            "participants": [
                {
                    "agent_id": "npc_01",
                    "proposal_id": "proposal_000401",
                    "role": "ACTOR",
                    "object_bindings": [{"object_id": "park_route_01", "slot_index": 0}],
                },
                {
                    "agent_id": "npc_02",
                    "proposal_id": "proposal_000402",
                    "role": "PARTICIPANT",
                    "object_bindings": [{"object_id": "park_route_01", "slot_index": 1}],
                },
            ],
        },
    ),
}


VERSION_DOCUMENT = {
    "protocol_version": "0.3.0",
    "schema_version": "v0.1",
    "config_version": "v0",
    "feature_version": "v0.1",
    "python_version": "3.12",
    "unity_editor": "6000.4.2f1",
    "compatibility": {
        "current": "0.3.0",
        "breaking_changes_require_protocol_bump": True,
        "bootstrap_decodable_versions": ["0.3.0", "0.2.0", "0.1.0"],
        "active_m3_acceptance_versions": ["0.3.0"],
        "active_m2_acceptance_versions": ["0.2.0"],
        "legacy_decode_only_versions": ["0.1.0"],
        "movement_cancelled_versions": ["0.3.0", "0.2.0"],
        "m2_compatibility_artifacts_immutable": True,
    },
    "frozen_decisions": {
        "relationship_prediction": "TARGET_TO_ACTOR",
        "joint_action_authority": "CENTRAL_RESOLVER",
        "perception_authority": "HIGH_LEVEL_LOCATION",
        "route_planning": "DISABLED",
        "event_witness_scopes": ["PARTICIPANTS_ONLY", "HIGH_LEVEL_LOCATION"],
        "movement_cancelled_direction": "UNITY_TO_PYTHON_NON_AUTHORITATIVE_REPORT",
        "action_cancelled_direction": "PYTHON_TO_UNITY_AUTHORITATIVE_DECISION",
        "action_correlation": "CORRELATION_ID_EQUALS_ACTION_ID",
        "heartbeat": "WEBSOCKET_PING_PONG",
        "resync": "FULL_HANDSHAKE_REGISTRY_SNAPSHOT_CLIENT_READY",
        "m3_agent_delta_presence": "FIELD_MASK_NULL_MEANS_CLEAR",
        "m3_joint_presentation": "STRUCTURED_PARTICIPANTS_AND_BINDINGS",
        "m3_public_world_schema": "v0.1",
        "m3_authority_checkpoint": "SIM_OWNED_SIDECAR_V1",
    },
}

M3_SCHEMA_NAMES = {
    "m3-candidate-action",
    "m3-joint-action-presentation",
    "m3-semantic-instances",
    "m3-background-dialogue",
    "protocol-message-v030",
    "client-hello-bootstrap-v030",
    "python-to-unity-message-v030",
    "unity-to-python-message-v030",
    "client-hello-bootstrap-all",
}
PRESENCE_SENSITIVE_EXAMPLES = {"agent-state-delta-clear-v030", "household-state-delta-v030"}


def _dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def build_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    schemas = {
        name: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:ai-town:protocol:{'0.3.0' if name in M3_SCHEMA_NAMES else '0.2.0'}:{name}",
            **adapter.json_schema(),
        }
        for name, adapter in SCHEMA_ADAPTERS.items()
    }
    examples: dict[str, Any] = {}
    for name, (adapter, raw) in EXAMPLES.items():
        value = adapter.validate_python(raw)
        examples[name] = json.loads(
            adapter.dump_json(
                value,
                exclude_none=False,
                exclude_unset=name in PRESENCE_SENSITIVE_EXAMPLES,
            )
        )
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
