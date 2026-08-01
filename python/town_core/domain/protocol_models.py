"""Versioned JSON/WebSocket DTOs for the Python authority/Unity boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import NeedValues
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import (
    ActionPhase,
    AnimationSemantic,
    AssetValidationSeverity,
    BehaviorId,
    CapabilityTag,
    LocationType,
    MessageType,
    MovementFailureReason,
    ObjectType,
    PerceptionAuthority,
)
from town_core.domain.identifiers import (
    ActionId,
    AgentId,
    ConversationId,
    LocationId,
    MessageId,
    ObjectId,
    WorldId,
)
from town_core.domain.state_models import RelationshipDelta, WorldEvent, WorldState


class EnvelopeBase(ContractModel):
    protocol_version: Literal["0.1.0"]
    message_id: MessageId
    message_type: MessageType
    sent_at_utc: datetime
    world_id: WorldId
    state_version: NonNegativeInt
    correlation_id: str | None


class ClientHelloPayload(ContractModel):
    client_name: Literal["unity"]
    unity_editor_version: Literal["6000.4.2f1"]
    supported_protocol_versions: Annotated[list[Literal["0.1.0"]], Field(min_length=1)]


class ServerHelloPayload(ContractModel):
    server_name: Literal["python_town_core"]
    accepted_protocol_version: Literal["0.1.0"]
    config_version: Literal["v0"]
    schema_version: Literal["v0.1"]


class RegisteredLocation(ContractModel):
    location_id: LocationId
    location_type: LocationType


class RegisteredInteractionSlot(ContractModel):
    slot_index: NonNegativeInt
    supported_animation_semantics: list[AnimationSemantic]


class RegisteredObject(ContractModel):
    object_id: ObjectId
    object_type: ObjectType
    location_id: LocationId
    capability_tags: Annotated[list[CapabilityTag], Field(min_length=1)]
    enabled: bool
    interaction_slots: Annotated[list[RegisteredInteractionSlot], Field(min_length=1)]


class RegisteredNpcView(ContractModel):
    agent_id: AgentId


class AssetRegistryPayload(ContractModel):
    locations: list[RegisteredLocation]
    objects: list[RegisteredObject]
    npc_views: list[RegisteredNpcView]
    mapped_animation_semantics: list[AnimationSemantic]


class AssetValidationIssue(ContractModel):
    severity: AssetValidationSeverity
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]
    message: str
    entity_id: str | None


class AssetRegistryResultPayload(ContractModel):
    accepted: bool
    issues: list[AssetValidationIssue]


class ClientReadyPayload(ContractModel):
    registry_message_id: MessageId


class WorldSnapshotPayload(ContractModel):
    world: WorldState


class SimulationClockPayload(ContractModel):
    game_minute: NonNegativeInt
    time_scale: Annotated[float, Field(ge=0.0, le=1000.0)]
    paused: bool


class ActionStartedPayload(ContractModel):
    action_id: ActionId
    agent_ids: Annotated[list[AgentId], Field(min_length=1)]
    behavior_id: BehaviorId
    destination_location_id: LocationId
    target_object_ids: list[ObjectId]
    animation_semantic: AnimationSemantic
    prop_semantic: str | None
    planned_duration_minutes: NonNegativeInt


class ActionPhaseChangedPayload(ContractModel):
    action_id: ActionId
    phase: ActionPhase


class ActionCancelledPayload(ContractModel):
    action_id: ActionId
    reason: str


class AgentStateDeltaPayload(ContractModel):
    agent_id: AgentId
    current_location_id: LocationId | Literal["TRAVELING"] | None = None
    current_action_id: ActionId | None = None
    needs: NeedValues | None = None


class RelationshipDeltaPayload(ContractModel):
    source_agent_id: AgentId
    target_agent_id: AgentId
    delta: RelationshipDelta


class WorldEventCreatedPayload(ContractModel):
    event: WorldEvent


class DialogueLineReadyPayload(ContractModel):
    conversation_id: ConversationId
    speaker_agent_id: AgentId
    text: Annotated[str, Field(min_length=1, max_length=1000)]


class DebugDecisionTracePayload(ContractModel):
    agent_id: AgentId
    selected_candidate_id: str
    prediction: OutcomePrediction
    utility_terms: dict[str, float]


class MovementArrivedPayload(ContractModel):
    action_id: ActionId
    agent_id: AgentId
    object_id: ObjectId | None
    slot_index: NonNegativeInt | None


class MovementFailedPayload(ContractModel):
    action_id: ActionId
    agent_id: AgentId
    reason: MovementFailureReason


class PresentationCompletedPayload(ContractModel):
    action_id: ActionId
    agent_id: AgentId


class PlayerUtterancePayload(ContractModel):
    conversation_id: ConversationId
    player_id: Literal["player"]
    target_agent_id: AgentId
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    client_state_version: NonNegativeInt


class PlayerEndConversationPayload(ContractModel):
    conversation_id: ConversationId
    target_agent_id: AgentId


class SetTimeScaleRequestPayload(ContractModel):
    requested_time_scale: Annotated[float, Field(ge=0.0, le=1000.0)]


class PauseRequestPayload(ContractModel):
    paused: bool


class ClientHelloMessage(EnvelopeBase):
    message_type: Literal[MessageType.CLIENT_HELLO]
    payload: ClientHelloPayload


class ServerHelloMessage(EnvelopeBase):
    message_type: Literal[MessageType.SERVER_HELLO]
    payload: ServerHelloPayload


class AssetRegistryMessage(EnvelopeBase):
    message_type: Literal[MessageType.ASSET_REGISTRY]
    payload: AssetRegistryPayload


class AssetRegistryResultMessage(EnvelopeBase):
    message_type: Literal[MessageType.ASSET_REGISTRY_RESULT]
    payload: AssetRegistryResultPayload


class ClientReadyMessage(EnvelopeBase):
    message_type: Literal[MessageType.CLIENT_READY]
    payload: ClientReadyPayload


class WorldSnapshotMessage(EnvelopeBase):
    message_type: Literal[MessageType.WORLD_SNAPSHOT]
    payload: WorldSnapshotPayload


class SimulationClockUpdatedMessage(EnvelopeBase):
    message_type: Literal[MessageType.SIMULATION_CLOCK_UPDATED]
    payload: SimulationClockPayload


class ActionStartedMessage(EnvelopeBase):
    message_type: Literal[MessageType.ACTION_STARTED]
    payload: ActionStartedPayload


class ActionPhaseChangedMessage(EnvelopeBase):
    message_type: Literal[MessageType.ACTION_PHASE_CHANGED]
    payload: ActionPhaseChangedPayload


class ActionCancelledMessage(EnvelopeBase):
    message_type: Literal[MessageType.ACTION_CANCELLED]
    payload: ActionCancelledPayload


class AgentStateDeltaMessage(EnvelopeBase):
    message_type: Literal[MessageType.AGENT_STATE_DELTA]
    payload: AgentStateDeltaPayload


class RelationshipDeltaMessage(EnvelopeBase):
    message_type: Literal[MessageType.RELATIONSHIP_DELTA]
    payload: RelationshipDeltaPayload


class WorldEventCreatedMessage(EnvelopeBase):
    message_type: Literal[MessageType.WORLD_EVENT_CREATED]
    payload: WorldEventCreatedPayload


class DialogueLineReadyMessage(EnvelopeBase):
    message_type: Literal[MessageType.DIALOGUE_LINE_READY]
    payload: DialogueLineReadyPayload


class DebugDecisionTraceMessage(EnvelopeBase):
    message_type: Literal[MessageType.DEBUG_DECISION_TRACE]
    payload: DebugDecisionTracePayload


class MovementArrivedMessage(EnvelopeBase):
    message_type: Literal[MessageType.MOVEMENT_ARRIVED]
    payload: MovementArrivedPayload


class MovementFailedMessage(EnvelopeBase):
    message_type: Literal[MessageType.MOVEMENT_FAILED]
    payload: MovementFailedPayload


class PresentationCompletedMessage(EnvelopeBase):
    message_type: Literal[MessageType.PRESENTATION_COMPLETED]
    payload: PresentationCompletedPayload


class PlayerUtteranceMessage(EnvelopeBase):
    message_type: Literal[MessageType.PLAYER_UTTERANCE]
    payload: PlayerUtterancePayload


class PlayerEndConversationMessage(EnvelopeBase):
    message_type: Literal[MessageType.PLAYER_END_CONVERSATION]
    payload: PlayerEndConversationPayload


class SetTimeScaleRequestMessage(EnvelopeBase):
    message_type: Literal[MessageType.SET_TIME_SCALE_REQUEST]
    payload: SetTimeScaleRequestPayload


class PauseRequestMessage(EnvelopeBase):
    message_type: Literal[MessageType.PAUSE_REQUEST]
    payload: PauseRequestPayload


type ProtocolMessage = Annotated[
    ClientHelloMessage
    | ServerHelloMessage
    | AssetRegistryMessage
    | AssetRegistryResultMessage
    | ClientReadyMessage
    | WorldSnapshotMessage
    | SimulationClockUpdatedMessage
    | ActionStartedMessage
    | ActionPhaseChangedMessage
    | ActionCancelledMessage
    | AgentStateDeltaMessage
    | RelationshipDeltaMessage
    | WorldEventCreatedMessage
    | DialogueLineReadyMessage
    | DebugDecisionTraceMessage
    | MovementArrivedMessage
    | MovementFailedMessage
    | PresentationCompletedMessage
    | PlayerUtteranceMessage
    | PlayerEndConversationMessage
    | SetTimeScaleRequestMessage
    | PauseRequestMessage,
    Field(discriminator="message_type"),
]


class PerceivedAgent(ContractModel):
    agent_id: AgentId
    location_id: LocationId


class PerceivedObject(ContractModel):
    object_id: ObjectId
    object_type: ObjectType
    location_id: LocationId
    enabled: bool


class PerceptionSnapshot(ContractModel):
    observer_agent_id: AgentId
    game_minute: NonNegativeInt
    authority: Literal[PerceptionAuthority.HIGH_LEVEL_LOCATION]
    authoritative_location_id: LocationId
    perceived_agents: list[PerceivedAgent]
    perceived_objects: list[PerceivedObject]

    @model_validator(mode="after")
    def validate_location_scope(self) -> PerceptionSnapshot:
        observed_locations = {
            *(agent.location_id for agent in self.perceived_agents),
            *(obj.location_id for obj in self.perceived_objects),
        }
        if observed_locations - {self.authoritative_location_id}:
            raise ValueError("V0 perception is limited to one high-level location")
        return self
