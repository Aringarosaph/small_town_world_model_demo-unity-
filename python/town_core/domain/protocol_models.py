"""Versioned JSON/WebSocket DTOs for the Python authority/Unity boundary."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, model_validator

from town_core.domain.base import ContractModel
from town_core.domain.config_models import MoodValues, NeedValues
from town_core.domain.decision_models import OutcomePrediction
from town_core.domain.enums import (
    ActionParticipantRole,
    ActionPhase,
    AgentDeltaField,
    AnimationSemantic,
    AssetValidationSeverity,
    BehaviorId,
    CapabilityTag,
    DecisionTrigger,
    HouseholdDeltaField,
    LocationType,
    MessageType,
    MovementCancellationReason,
    MovementFailureReason,
    ObjectType,
    PerceptionAuthority,
    ProposalResult,
)
from town_core.domain.identifiers import (
    ActionId,
    AgentId,
    CandidateId,
    ConversationId,
    EventId,
    HouseholdId,
    LocationId,
    MessageId,
    ObjectId,
    ProposalId,
    WorldId,
)
from town_core.domain.state_models import RelationshipDelta, WorldEvent, WorldState

type SupportedProtocolVersion = Literal["0.1.0", "0.2.0"]
type M3SupportedProtocolVersion = Literal["0.1.0", "0.2.0", "0.3.0"]

_FACING_SOCIAL_BEHAVIORS = {
    BehaviorId.GREET,
    BehaviorId.CHAT,
    BehaviorId.JOKE,
    BehaviorId.COMPLIMENT,
    BehaviorId.SHARE_EVENT,
    BehaviorId.INVITE_JOIN,
    BehaviorId.APOLOGIZE,
    BehaviorId.CONFRONT,
}


def select_protocol_version(
    client_preference: Sequence[M3SupportedProtocolVersion],
    server_supported: Sequence[M3SupportedProtocolVersion] = ("0.3.0", "0.2.0", "0.1.0"),
) -> M3SupportedProtocolVersion:
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


def select_m3_protocol_version(
    client_preference: Sequence[M3SupportedProtocolVersion],
) -> Literal["0.3.0"]:
    """Negotiate the sole protocol version accepted by the active M3 gate."""

    if not client_preference or client_preference[0] != "0.3.0":
        raise ValueError("active M3 requires protocol 0.3.0 as the first client preference")
    return "0.3.0"


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

type ProtocolMessageV020 = ProtocolMessage
type PythonToUnityMessageV020 = PythonToUnityMessage
type UnityToPythonMessageV020 = UnityToPythonMessage


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


class EnvelopeV030Base(ContractModel):
    protocol_version: Literal["0.3.0"]
    message_id: MessageId
    message_type: MessageType
    sent_at_utc: datetime
    world_id: WorldId
    state_version: NonNegativeInt
    correlation_id: str | None


class ClientHelloV030Payload(ContractModel):
    client_name: Literal["unity"]
    unity_editor_version: Literal["6000.4.2f1"]
    supported_protocol_versions: Annotated[list[M3SupportedProtocolVersion], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_m3_preference(self) -> ClientHelloV030Payload:
        if len(self.supported_protocol_versions) != len(set(self.supported_protocol_versions)):
            raise ValueError("supported protocol versions must be unique and preference ordered")
        if self.supported_protocol_versions[0] != "0.3.0":
            raise ValueError("M3 client must prefer protocol 0.3.0")
        return self


class ServerHelloV030Payload(ContractModel):
    server_name: Literal["python_town_core"]
    accepted_protocol_version: Literal["0.3.0"]
    config_version: Literal["v0"]
    schema_version: Literal["v0.1"]


class FacingTargetV030(ContractModel):
    target_agent_id: AgentId | None = None
    target_object_id: ObjectId | None = None

    @model_validator(mode="after")
    def validate_exact_target(self) -> FacingTargetV030:
        if (self.target_agent_id is None) == (self.target_object_id is None):
            raise ValueError("facing target requires exactly one agent or object")
        return self


class ParticipantObjectBindingV030(ContractModel):
    object_id: ObjectId
    slot_index: NonNegativeInt


class ActionParticipantV030(ContractModel):
    agent_id: AgentId
    role: ActionParticipantRole
    object_bindings: list[ParticipantObjectBindingV030]
    facing_target: FacingTargetV030 | None
    animation_semantic: AnimationSemantic
    prop_semantic: str | None

    @model_validator(mode="after")
    def validate_bindings(self) -> ActionParticipantV030:
        bindings = [(item.object_id, item.slot_index) for item in self.object_bindings]
        if len(bindings) != len(set(bindings)):
            raise ValueError("participant object/slot bindings must be unique")
        return self


def _validate_action_participants(participants: Sequence[ActionParticipantV030], is_joint: bool) -> None:
    agent_ids = [item.agent_id for item in participants]
    if len(agent_ids) != len(set(agent_ids)):
        raise ValueError("action participant agents must be unique")
    if agent_ids != sorted(agent_ids):
        raise ValueError("action participants must use stable agent ID order")
    if sum(item.role is ActionParticipantRole.ACTOR for item in participants) != 1:
        raise ValueError("action presentation requires exactly one ACTOR")
    if is_joint != (len(participants) >= 2):
        raise ValueError("is_joint must match whether the action has multiple participants")
    bindings = [
        (binding.object_id, binding.slot_index)
        for participant in participants
        for binding in participant.object_bindings
    ]
    if len(bindings) != len(set(bindings)):
        raise ValueError("an action cannot bind multiple participants to the same object slot")


def _validate_social_presentation(behavior_id: BehaviorId, participants: Sequence[ActionParticipantV030]) -> None:
    if behavior_id not in _FACING_SOCIAL_BEHAVIORS:
        return
    actors = [item for item in participants if item.role is ActionParticipantRole.ACTOR]
    targets = [item for item in participants if item.role is ActionParticipantRole.TARGET]
    if len(targets) != 1:
        raise ValueError("facing social action requires exactly one TARGET")
    actor = actors[0]
    target = targets[0]
    if actor.facing_target is None or actor.facing_target.target_agent_id != target.agent_id:
        raise ValueError("social ACTOR must face the TARGET agent")
    if target.facing_target is None or target.facing_target.target_agent_id != actor.agent_id:
        raise ValueError("social TARGET must face the ACTOR agent")


class ActionStartedV030Payload(ContractModel):
    action_id: ActionId
    behavior_id: BehaviorId
    destination_location_id: LocationId
    participants: Annotated[list[ActionParticipantV030], Field(min_length=1, max_length=10)]
    is_joint: bool
    conversation_id: ConversationId | None
    planned_duration_minutes: NonNegativeInt

    @model_validator(mode="after")
    def validate_participants(self) -> ActionStartedV030Payload:
        _validate_action_participants(self.participants, self.is_joint)
        _validate_social_presentation(self.behavior_id, self.participants)
        return self


class ActiveActionPresentationV030(ContractModel):
    action_id: ActionId
    behavior_id: BehaviorId
    phase: ActionPhase
    destination_location_id: LocationId
    participants: Annotated[list[ActionParticipantV030], Field(min_length=1, max_length=10)]
    is_joint: bool
    conversation_id: ConversationId | None
    planned_end_game_minute: NonNegativeInt | None

    @model_validator(mode="after")
    def validate_participants(self) -> ActiveActionPresentationV030:
        _validate_action_participants(self.participants, self.is_joint)
        _validate_social_presentation(self.behavior_id, self.participants)
        return self


class WorldSnapshotV030Payload(ContractModel):
    world: WorldState
    active_presentations: list[ActiveActionPresentationV030]

    @model_validator(mode="after")
    def validate_active_presentations(self) -> WorldSnapshotV030Payload:
        ids = [item.action_id for item in self.active_presentations]
        if len(ids) != len(set(ids)):
            raise ValueError("active presentation action IDs must be unique")
        if set(ids) != set(self.world.active_actions):
            raise ValueError("active presentations must exactly cover public WorldState active actions")
        return self


class AgentStateDeltaV030Payload(ContractModel):
    agent_id: AgentId
    field_mask: Annotated[list[AgentDeltaField], Field(min_length=1)]
    current_location_id: LocationId | Literal["TRAVELING"] | None = None
    current_action_id: ActionId | None = None
    needs: NeedValues | None = None
    mood: MoodValues | None = None
    known_event_ids: list[EventId] | None = None

    @model_validator(mode="after")
    def validate_field_presence(self) -> AgentStateDeltaV030Payload:
        mask = {item.value for item in self.field_mask}
        if len(mask) != len(self.field_mask):
            raise ValueError("agent delta field_mask entries must be unique")
        supplied = set(self.model_fields_set) - {"agent_id", "field_mask"}
        if supplied != mask:
            raise ValueError("agent delta fields present in JSON must exactly match field_mask")
        return self


class HouseholdStateDeltaV030Payload(ContractModel):
    household_id: HouseholdId
    field_mask: Annotated[list[HouseholdDeltaField], Field(min_length=1)]
    money: NonNegativeInt | None = None
    food_units: NonNegativeInt | None = None

    @model_validator(mode="after")
    def validate_field_presence(self) -> HouseholdStateDeltaV030Payload:
        mask = {item.value for item in self.field_mask}
        if len(mask) != len(self.field_mask):
            raise ValueError("household delta field_mask entries must be unique")
        supplied = set(self.model_fields_set) - {"household_id", "field_mask"}
        if supplied != mask:
            raise ValueError("household delta fields present in JSON must exactly match field_mask")
        if any(getattr(self, name) is None for name in mask):
            raise ValueError("household money and food updates cannot be cleared")
        return self


class HardPreviewV030(ContractModel):
    household_money_delta: int
    household_food_units_delta: int
    object_bindings: list[ParticipantObjectBindingV030]
    reservation_keys: list[Annotated[str, Field(min_length=1)]]
    settlement_keys: list[Annotated[str, Field(min_length=1)]]

    @model_validator(mode="after")
    def validate_preview_identity(self) -> HardPreviewV030:
        bindings = [(item.object_id, item.slot_index) for item in self.object_bindings]
        if len(bindings) != len(set(bindings)):
            raise ValueError("hard preview object bindings must be unique")
        if len(self.reservation_keys) != len(set(self.reservation_keys)):
            raise ValueError("hard preview reservation keys must be unique")
        if len(self.settlement_keys) != len(set(self.settlement_keys)):
            raise ValueError("hard preview settlement keys must be unique")
        return self


class DebugCandidateTraceV030(ContractModel):
    rank: Annotated[int, Field(ge=1, le=12)]
    candidate_id: CandidateId
    proposal_id: ProposalId | None
    behavior_id: BehaviorId
    actor_id: AgentId
    target_agent_id: AgentId | None
    selected_context_event_id: EventId | None
    target_conversation_id: ConversationId | None
    invited_activity_id: BehaviorId | None
    destination_location_id: LocationId | None
    hard_preview: HardPreviewV030
    prediction: OutcomePrediction
    utility_terms: Annotated[dict[str, float], Field(min_length=1)]
    total_score: float
    resolver_result: ProposalResult | None
    conflict_code: Annotated[str | None, Field(pattern=r"^[A-Z][A-Z0-9_]*$")] = None

    @model_validator(mode="after")
    def validate_prediction_candidate(self) -> DebugCandidateTraceV030:
        if self.prediction.candidate_id != self.candidate_id:
            raise ValueError("debug prediction candidate_id must match the candidate row")
        if self.resolver_result is None:
            if self.proposal_id is not None or self.conflict_code is not None:
                raise ValueError("unattempted candidate must have null proposal_id, resolver_result, and conflict_code")
        elif self.proposal_id is None:
            raise ValueError("attempted candidate requires a proposal_id")
        elif self.resolver_result is ProposalResult.ACCEPTED:
            if self.conflict_code is not None:
                raise ValueError("accepted candidate cannot carry a conflict_code")
        elif self.conflict_code is None:
            raise ValueError("rejected Resolver attempt requires a conflict_code")
        return self


class DebugDecisionTraceV030Payload(ContractModel):
    decision_id: Annotated[str, Field(pattern=r"^decision_[0-9]+$")]
    agent_id: AgentId
    trigger: DecisionTrigger
    source_state_version: NonNegativeInt
    candidates: Annotated[list[DebugCandidateTraceV030], Field(min_length=1, max_length=12)]
    selected_candidate_id: CandidateId
    selected_proposal_id: ProposalId

    @model_validator(mode="after")
    def validate_top_k(self) -> DebugDecisionTraceV030Payload:
        candidate_ids = [item.candidate_id for item in self.candidates]
        ranks = [item.rank for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Top-K candidate IDs must be unique")
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("Top-K ranks must be contiguous and ordered")
        if sum(item.resolver_result is not None for item in self.candidates) > 2:
            raise ValueError("M3 permits at most two proposal/Resolver attempts per agent decision")
        if self.selected_candidate_id not in candidate_ids:
            raise ValueError("selected_candidate_id must appear in Top-K candidates")
        selected = self.candidates[candidate_ids.index(self.selected_candidate_id)]
        if selected.proposal_id != self.selected_proposal_id:
            raise ValueError("selected_proposal_id must match the selected candidate row")
        if selected.resolver_result is not ProposalResult.ACCEPTED:
            raise ValueError("selected candidate row must have resolver_result ACCEPTED")
        return self


class ClientHelloV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.CLIENT_HELLO]
    payload: ClientHelloV030Payload

    @model_validator(mode="after")
    def validate_bootstrap_version(self) -> ClientHelloV030Message:
        if self.protocol_version not in self.payload.supported_protocol_versions:
            raise ValueError("client_hello envelope version must appear in the supported version preference list")
        return self


class ServerHelloV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.SERVER_HELLO]
    payload: ServerHelloV030Payload


class AssetRegistryV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.ASSET_REGISTRY]
    payload: AssetRegistryPayload


class AssetRegistryResultV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.ASSET_REGISTRY_RESULT]
    payload: AssetRegistryResultPayload


class ClientReadyV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.CLIENT_READY]
    payload: ClientReadyPayload


class WorldSnapshotV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.WORLD_SNAPSHOT]
    payload: WorldSnapshotV030Payload


class SimulationClockUpdatedV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.SIMULATION_CLOCK_UPDATED]
    payload: SimulationClockPayload


class ActionCorrelatedV030Message(EnvelopeV030Base):
    correlation_id: ActionId

    @model_validator(mode="after")
    def validate_action_correlation(self) -> ActionCorrelatedV030Message:
        payload = self.__dict__.get("payload")
        payload_action_id = getattr(payload, "action_id", None)
        if payload_action_id is None or self.correlation_id != payload_action_id:
            raise ValueError("action message correlation_id must equal payload.action_id")
        return self


class ActionStartedV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.ACTION_STARTED]
    payload: ActionStartedV030Payload


class ActionPhaseChangedV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.ACTION_PHASE_CHANGED]
    payload: ActionPhaseChangedPayload


class ActionCancelledV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.ACTION_CANCELLED]
    payload: ActionCancelledPayload


class AgentStateDeltaV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.AGENT_STATE_DELTA]
    payload: AgentStateDeltaV030Payload


class HouseholdStateDeltaV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.HOUSEHOLD_STATE_DELTA]
    payload: HouseholdStateDeltaV030Payload


class RelationshipDeltaV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.RELATIONSHIP_DELTA]
    payload: RelationshipDeltaPayload


class WorldEventCreatedV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.WORLD_EVENT_CREATED]
    payload: WorldEventCreatedPayload


class DialogueLineReadyV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.DIALOGUE_LINE_READY]
    payload: DialogueLineReadyPayload


class DebugDecisionTraceV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.DEBUG_DECISION_TRACE]
    payload: DebugDecisionTraceV030Payload


class MovementArrivedV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.MOVEMENT_ARRIVED]
    payload: MovementArrivedPayload


class MovementFailedV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.MOVEMENT_FAILED]
    payload: MovementFailedPayload


class MovementCancelledV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.MOVEMENT_CANCELLED]
    payload: MovementCancelledPayload


class PresentationCompletedV030Message(ActionCorrelatedV030Message):
    message_type: Literal[MessageType.PRESENTATION_COMPLETED]
    payload: PresentationCompletedPayload


class PlayerUtteranceV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.PLAYER_UTTERANCE]
    payload: PlayerUtterancePayload


class PlayerEndConversationV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.PLAYER_END_CONVERSATION]
    payload: PlayerEndConversationPayload


class SetTimeScaleRequestV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.SET_TIME_SCALE_REQUEST]
    payload: SetTimeScaleRequestPayload


class PauseRequestV030Message(EnvelopeV030Base):
    message_type: Literal[MessageType.PAUSE_REQUEST]
    payload: PauseRequestPayload


type ProtocolMessageV030 = Annotated[
    ClientHelloV030Message
    | ServerHelloV030Message
    | AssetRegistryV030Message
    | AssetRegistryResultV030Message
    | ClientReadyV030Message
    | WorldSnapshotV030Message
    | SimulationClockUpdatedV030Message
    | ActionStartedV030Message
    | ActionPhaseChangedV030Message
    | ActionCancelledV030Message
    | AgentStateDeltaV030Message
    | HouseholdStateDeltaV030Message
    | RelationshipDeltaV030Message
    | WorldEventCreatedV030Message
    | DialogueLineReadyV030Message
    | DebugDecisionTraceV030Message
    | MovementArrivedV030Message
    | MovementFailedV030Message
    | MovementCancelledV030Message
    | PresentationCompletedV030Message
    | PlayerUtteranceV030Message
    | PlayerEndConversationV030Message
    | SetTimeScaleRequestV030Message
    | PauseRequestV030Message,
    Field(discriminator="message_type"),
]


type PythonToUnityMessageV030 = Annotated[
    ServerHelloV030Message
    | AssetRegistryResultV030Message
    | WorldSnapshotV030Message
    | SimulationClockUpdatedV030Message
    | ActionStartedV030Message
    | ActionPhaseChangedV030Message
    | ActionCancelledV030Message
    | AgentStateDeltaV030Message
    | HouseholdStateDeltaV030Message
    | RelationshipDeltaV030Message
    | WorldEventCreatedV030Message
    | DialogueLineReadyV030Message
    | DebugDecisionTraceV030Message,
    Field(discriminator="message_type"),
]


type UnityToPythonMessageV030 = Annotated[
    ClientHelloV030Message
    | AssetRegistryV030Message
    | ClientReadyV030Message
    | MovementArrivedV030Message
    | MovementFailedV030Message
    | MovementCancelledV030Message
    | PresentationCompletedV030Message
    | PlayerUtteranceV030Message
    | PlayerEndConversationV030Message
    | SetTimeScaleRequestV030Message
    | PauseRequestV030Message,
    Field(discriminator="message_type"),
]

type ClientHelloBootstrapMessage = Annotated[
    ClientHelloV030Message | ClientHelloMessage,
    Field(discriminator="protocol_version"),
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
