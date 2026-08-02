"""Versioned JSON/WebSocket DTOs for the Python authority/Unity boundary."""

from __future__ import annotations

from collections.abc import Sequence
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
    MovementCancellationReason,
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

type SupportedProtocolVersion = Literal["0.1.0", "0.2.0"]


def select_protocol_version(
    client_preference: Sequence[SupportedProtocolVersion],
    server_supported: Sequence[SupportedProtocolVersion] = ("0.2.0", "0.1.0"),
) -> SupportedProtocolVersion:
    """Select the first client-preferred version also understood by the server."""

    for version in client_preference:
        if version in server_supported:
            return version
    raise ValueError("client and server have no compatible protocol version")


def select_m2_protocol_version(
    client_preference: Sequence[SupportedProtocolVersion],
) -> Literal["0.2.0"]:
    """Negotiate the sole protocol version accepted by the active M2 gate."""

    if not client_preference or client_preference[0] != "0.2.0":
        raise ValueError("active M2 requires protocol 0.2.0 as the first client preference")
    return "0.2.0"


class BootstrapEnvelopeBase(ContractModel):
    protocol_version: SupportedProtocolVersion
    message_id: MessageId
    message_type: MessageType
    sent_at_utc: datetime
    world_id: WorldId
    state_version: NonNegativeInt
    correlation_id: str | None


class EnvelopeBase(BootstrapEnvelopeBase):
    protocol_version: Literal["0.2.0"]


class ClientHelloPayload(ContractModel):
    client_name: Literal["unity"]
    unity_editor_version: Literal["6000.4.2f1"]
    supported_protocol_versions: Annotated[list[SupportedProtocolVersion], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_preference_order(self) -> ClientHelloPayload:
        if len(self.supported_protocol_versions) != len(set(self.supported_protocol_versions)):
            raise ValueError("supported protocol versions must be unique and preference ordered")
        return self


class ServerHelloPayload(ContractModel):
    server_name: Literal["python_town_core"]
    accepted_protocol_version: SupportedProtocolVersion
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


class MovementCancelledPayload(ContractModel):
    action_id: ActionId
    agent_id: AgentId
    reason: MovementCancellationReason


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


class ClientHelloMessage(BootstrapEnvelopeBase):
    message_type: Literal[MessageType.CLIENT_HELLO]
    payload: ClientHelloPayload

    @model_validator(mode="after")
    def validate_bootstrap_version(self) -> ClientHelloMessage:
        if self.protocol_version not in self.payload.supported_protocol_versions:
            raise ValueError("client_hello envelope version must appear in the supported version preference list")
        return self


class ServerHelloMessage(BootstrapEnvelopeBase):
    message_type: Literal[MessageType.SERVER_HELLO]
    payload: ServerHelloPayload

    @model_validator(mode="after")
    def validate_selected_version(self) -> ServerHelloMessage:
        if self.protocol_version != self.payload.accepted_protocol_version:
            raise ValueError("server_hello envelope must use the selected protocol version")
        return self


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


class ActionCorrelatedMessage(EnvelopeBase):
    correlation_id: ActionId

    @model_validator(mode="after")
    def validate_action_correlation(self) -> ActionCorrelatedMessage:
        payload = self.__dict__.get("payload")
        payload_action_id = getattr(payload, "action_id", None)
        if payload_action_id is None or self.correlation_id != payload_action_id:
            raise ValueError("action message correlation_id must equal payload.action_id")
        return self


class ActionStartedMessage(ActionCorrelatedMessage):
    message_type: Literal[MessageType.ACTION_STARTED]
    payload: ActionStartedPayload


class ActionPhaseChangedMessage(ActionCorrelatedMessage):
    message_type: Literal[MessageType.ACTION_PHASE_CHANGED]
    payload: ActionPhaseChangedPayload


class ActionCancelledMessage(ActionCorrelatedMessage):
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


class MovementArrivedMessage(ActionCorrelatedMessage):
    message_type: Literal[MessageType.MOVEMENT_ARRIVED]
    payload: MovementArrivedPayload


class MovementFailedMessage(ActionCorrelatedMessage):
    message_type: Literal[MessageType.MOVEMENT_FAILED]
    payload: MovementFailedPayload


class MovementCancelledMessage(ActionCorrelatedMessage):
    protocol_version: Literal["0.2.0"]
    message_type: Literal[MessageType.MOVEMENT_CANCELLED]
    payload: MovementCancelledPayload


class PresentationCompletedMessage(ActionCorrelatedMessage):
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
    | MovementCancelledMessage
    | PresentationCompletedMessage
    | PlayerUtteranceMessage
    | PlayerEndConversationMessage
    | SetTimeScaleRequestMessage
    | PauseRequestMessage,
    Field(discriminator="message_type"),
]

type PythonToUnityMessage = Annotated[
    ServerHelloMessage
    | AssetRegistryResultMessage
    | WorldSnapshotMessage
    | SimulationClockUpdatedMessage
    | ActionStartedMessage
    | ActionPhaseChangedMessage
    | ActionCancelledMessage
    | AgentStateDeltaMessage
    | RelationshipDeltaMessage
    | WorldEventCreatedMessage
    | DialogueLineReadyMessage
    | DebugDecisionTraceMessage,
    Field(discriminator="message_type"),
]

type UnityToPythonMessage = Annotated[
    ClientHelloMessage
    | AssetRegistryMessage
    | ClientReadyMessage
    | MovementArrivedMessage
    | MovementFailedMessage
    | MovementCancelledMessage
    | PresentationCompletedMessage
    | PlayerUtteranceMessage
    | PlayerEndConversationMessage
    | SetTimeScaleRequestMessage
    | PauseRequestMessage,
    Field(discriminator="message_type"),
]


class ClientHelloV010Payload(ContractModel):
    client_name: Literal["unity"]
    unity_editor_version: Literal["6000.4.2f1"]
    supported_protocol_versions: Annotated[list[Literal["0.1.0"]], Field(min_length=1)]


class ServerHelloV010Payload(ContractModel):
    server_name: Literal["python_town_core"]
    accepted_protocol_version: Literal["0.1.0"]
    config_version: Literal["v0"]
    schema_version: Literal["v0.1"]


class EnvelopeV010Base(ContractModel):
    protocol_version: Literal["0.1.0"]
    message_id: MessageId
    message_type: MessageType
    sent_at_utc: datetime
    world_id: WorldId
    state_version: NonNegativeInt
    correlation_id: str | None


class ClientHelloV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.CLIENT_HELLO]
    payload: ClientHelloV010Payload


class ServerHelloV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.SERVER_HELLO]
    payload: ServerHelloV010Payload


class AssetRegistryV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.ASSET_REGISTRY]
    payload: AssetRegistryPayload


class AssetRegistryResultV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.ASSET_REGISTRY_RESULT]
    payload: AssetRegistryResultPayload


class ClientReadyV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.CLIENT_READY]
    payload: ClientReadyPayload


class WorldSnapshotV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.WORLD_SNAPSHOT]
    payload: WorldSnapshotPayload


class SimulationClockUpdatedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.SIMULATION_CLOCK_UPDATED]
    payload: SimulationClockPayload


class ActionStartedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.ACTION_STARTED]
    payload: ActionStartedPayload


class ActionPhaseChangedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.ACTION_PHASE_CHANGED]
    payload: ActionPhaseChangedPayload


class ActionCancelledV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.ACTION_CANCELLED]
    payload: ActionCancelledPayload


class AgentStateDeltaV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.AGENT_STATE_DELTA]
    payload: AgentStateDeltaPayload


class RelationshipDeltaV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.RELATIONSHIP_DELTA]
    payload: RelationshipDeltaPayload


class WorldEventCreatedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.WORLD_EVENT_CREATED]
    payload: WorldEventCreatedPayload


class DialogueLineReadyV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.DIALOGUE_LINE_READY]
    payload: DialogueLineReadyPayload


class DebugDecisionTraceV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.DEBUG_DECISION_TRACE]
    payload: DebugDecisionTracePayload


class MovementArrivedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.MOVEMENT_ARRIVED]
    payload: MovementArrivedPayload


class MovementFailedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.MOVEMENT_FAILED]
    payload: MovementFailedPayload


class PresentationCompletedV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.PRESENTATION_COMPLETED]
    payload: PresentationCompletedPayload


class PlayerUtteranceV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.PLAYER_UTTERANCE]
    payload: PlayerUtterancePayload


class PlayerEndConversationV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.PLAYER_END_CONVERSATION]
    payload: PlayerEndConversationPayload


class SetTimeScaleRequestV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.SET_TIME_SCALE_REQUEST]
    payload: SetTimeScaleRequestPayload


class PauseRequestV010Message(EnvelopeV010Base):
    message_type: Literal[MessageType.PAUSE_REQUEST]
    payload: PauseRequestPayload


type ProtocolMessageV010 = Annotated[
    ClientHelloV010Message
    | ServerHelloV010Message
    | AssetRegistryV010Message
    | AssetRegistryResultV010Message
    | ClientReadyV010Message
    | WorldSnapshotV010Message
    | SimulationClockUpdatedV010Message
    | ActionStartedV010Message
    | ActionPhaseChangedV010Message
    | ActionCancelledV010Message
    | AgentStateDeltaV010Message
    | RelationshipDeltaV010Message
    | WorldEventCreatedV010Message
    | DialogueLineReadyV010Message
    | DebugDecisionTraceV010Message
    | MovementArrivedV010Message
    | MovementFailedV010Message
    | PresentationCompletedV010Message
    | PlayerUtteranceV010Message
    | PlayerEndConversationV010Message
    | SetTimeScaleRequestV010Message
    | PauseRequestV010Message,
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
