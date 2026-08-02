"""Generation-safe M2 WebSocket handshake and protocol session."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from town_core.bridge.registry import M2ScopedAssetRegistryValidator
from town_core.domain.enums import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS, MessageType
from town_core.domain.protocol_models import (
    AssetRegistryMessage,
    AssetRegistryResultMessage,
    ClientHelloMessage,
    ClientReadyMessage,
    MovementArrivedMessage,
    MovementCancelledMessage,
    MovementFailedMessage,
    PauseRequestMessage,
    PresentationCompletedMessage,
    ProtocolMessage,
    ServerHelloMessage,
    ServerHelloPayload,
    SetTimeScaleRequestMessage,
    UnityToPythonMessage,
    select_m2_protocol_version,
)

_UNITY_TO_PYTHON_ADAPTER: TypeAdapter[UnityToPythonMessage] = TypeAdapter(UnityToPythonMessage)


class SessionPhase(StrEnum):
    AWAITING_CLIENT_HELLO = "AWAITING_CLIENT_HELLO"
    AWAITING_ASSET_REGISTRY = "AWAITING_ASSET_REGISTRY"
    AWAITING_CLIENT_READY = "AWAITING_CLIENT_READY"
    READY = "READY"
    DISCONNECTED = "DISCONNECTED"


class BridgeProtocolError(ValueError):
    """Readable transport/protocol failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str, *, resync_required: bool = False) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.resync_required = resync_required


class BridgeSession:
    """One connection generation; old generations can never mutate authority."""

    def __init__(self, runtime: Any, *, generation: int) -> None:
        self.runtime = runtime
        self.generation = generation
        self.phase = SessionPhase.AWAITING_CLIENT_HELLO
        self.accepted_registry_message_id: str | None = None
        self.snapshot_state_version: int | None = None
        self.last_client_state_version = 0
        self.negotiated_protocol_version: str | None = None
        self._seen: dict[str, tuple[str, tuple[ProtocolMessage, ...]]] = {}

    def receive_json(self, raw: str | bytes | dict[str, Any]) -> tuple[ProtocolMessage, ...]:
        if not self.runtime.is_current_generation(self.generation):
            raise BridgeProtocolError(
                "OBSOLETE_CONNECTION_GENERATION",
                "a newer transport generation owns the bridge",
                resync_required=True,
            )
        document = self._decode(raw)
        fingerprint = self._fingerprint(document)
        message_id = document.get("message_id")
        if isinstance(message_id, str) and message_id in self._seen:
            previous_fingerprint, repeat_outputs = self._seen[message_id]
            if fingerprint != previous_fingerprint:
                raise BridgeProtocolError(
                    "MESSAGE_ID_CONTENT_MISMATCH",
                    "the same message_id was reused with different content",
                )
            return repeat_outputs
        message = self._validate(document)
        if message.world_id != self.runtime.world_id:
            raise BridgeProtocolError("WORLD_ID_MISMATCH", "message targets another authority world")
        if message.state_version > self.runtime.engine.state.state_version:
            raise BridgeProtocolError(
                "FUTURE_STATE_VERSION", "client claims an authority version Python has not committed"
            )

        outputs, repeatable = self._dispatch(message)
        self.last_client_state_version = max(self.last_client_state_version, message.state_version)
        self._seen[message.message_id] = (fingerprint, outputs if repeatable else ())
        return outputs

    def disconnect(self) -> None:
        self.phase = SessionPhase.DISCONNECTED
        self.runtime.disconnect(self.generation)

    def _dispatch(self, message: ProtocolMessage) -> tuple[tuple[ProtocolMessage, ...], bool]:
        if isinstance(message, ClientHelloMessage):
            self._require_phase(SessionPhase.AWAITING_CLIENT_HELLO)
            try:
                selected_version = select_m2_protocol_version(message.payload.supported_protocol_versions)
            except ValueError as exc:
                raise BridgeProtocolError("M2_PROTOCOL_NEGOTIATION_FAILED", str(exc)) from exc
            self.negotiated_protocol_version = selected_version
            self.runtime.record_negotiated_protocol(self.generation, selected_version)
            hello_response = ServerHelloMessage(
                protocol_version=selected_version,
                message_id=self.runtime.next_message_id(),
                message_type=MessageType.SERVER_HELLO,
                sent_at_utc=self.runtime._now(),
                world_id=self.runtime.world_id,
                state_version=self.runtime.engine.state.state_version,
                correlation_id=message.message_id,
                payload=ServerHelloPayload(
                    server_name="python_town_core",
                    accepted_protocol_version=selected_version,
                    config_version="v0",
                    schema_version="v0.1",
                ),
            )
            self.phase = SessionPhase.AWAITING_ASSET_REGISTRY
            return (hello_response,), True

        if isinstance(message, AssetRegistryMessage):
            self._require_phase(SessionPhase.AWAITING_ASSET_REGISTRY)
            result = M2ScopedAssetRegistryValidator(
                self.runtime.catalog,
                self.runtime.engine.state,
                active_agent_id=self.runtime.engine.active_agent_id,
            ).validate(message.payload)
            registry_response = AssetRegistryResultMessage(
                protocol_version=cast(Any, PROTOCOL_VERSION),
                message_id=self.runtime.next_message_id(),
                message_type=MessageType.ASSET_REGISTRY_RESULT,
                sent_at_utc=self.runtime._now(),
                world_id=self.runtime.world_id,
                state_version=self.runtime.engine.state.state_version,
                correlation_id=message.message_id,
                payload=result,
            )
            if not result.accepted:
                return (registry_response,), True
            snapshot = self.runtime.snapshot_message(correlation_id=message.message_id)
            self.accepted_registry_message_id = message.message_id
            self.snapshot_state_version = snapshot.state_version
            self.runtime.record_snapshot_evidence(self.generation, message.message_id, snapshot.state_version)
            self.phase = SessionPhase.AWAITING_CLIENT_READY
            return (registry_response, snapshot), True

        if isinstance(message, ClientReadyMessage):
            self._require_phase(SessionPhase.AWAITING_CLIENT_READY)
            if message.payload.registry_message_id != self.accepted_registry_message_id:
                raise BridgeProtocolError("REGISTRY_ACK_MISMATCH", "client_ready references an unaccepted registry")
            if message.state_version != self.snapshot_state_version:
                raise BridgeProtocolError("SNAPSHOT_ACK_MISMATCH", "client_ready did not apply the fresh snapshot")
            self.runtime.mark_ready(self.generation)
            self.phase = SessionPhase.READY
            return (self.runtime.clock_message(correlation_id=message.message_id),), True

        self._require_phase(SessionPhase.READY)
        if isinstance(message, MovementArrivedMessage):
            arrived_payload = message.payload
            return (
                self.runtime.movement_arrived(
                    generation=self.generation,
                    action_id=arrived_payload.action_id,
                    agent_id=arrived_payload.agent_id,
                    state_version=message.state_version,
                    object_id=arrived_payload.object_id,
                    slot_index=arrived_payload.slot_index,
                ),
                False,
            )
        if isinstance(message, MovementFailedMessage):
            failed_payload = message.payload
            return (
                self.runtime.movement_failed(
                    generation=self.generation,
                    action_id=failed_payload.action_id,
                    agent_id=failed_payload.agent_id,
                    state_version=message.state_version,
                    reason=failed_payload.reason,
                ),
                False,
            )
        if isinstance(message, MovementCancelledMessage):
            cancelled_payload = message.payload
            return (
                self.runtime.movement_cancelled(
                    generation=self.generation,
                    action_id=cancelled_payload.action_id,
                    agent_id=cancelled_payload.agent_id,
                    state_version=message.state_version,
                    reason=cancelled_payload.reason,
                ),
                False,
            )
        if isinstance(message, PresentationCompletedMessage):
            presentation_payload = message.payload
            return (
                self.runtime.presentation_completed(
                    generation=self.generation,
                    action_id=presentation_payload.action_id,
                    agent_id=presentation_payload.agent_id,
                    state_version=message.state_version,
                ),
                False,
            )
        if isinstance(message, SetTimeScaleRequestMessage):
            return (self.runtime.set_time_scale(message.payload.requested_time_scale),), True
        if isinstance(message, PauseRequestMessage):
            return (self.runtime.set_paused(message.payload.paused),), True
        raise BridgeProtocolError("UNSUPPORTED_CLIENT_MESSAGE", f"Python cannot accept {message.message_type.value}")

    def _require_phase(self, expected: SessionPhase) -> None:
        if self.phase is not expected:
            raise BridgeProtocolError(
                "HANDSHAKE_ORDER_VIOLATION",
                f"expected {expected.value}, current phase is {self.phase.value}",
            )

    @staticmethod
    def _decode(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeProtocolError("INVALID_JSON", str(exc)) from exc
        if not isinstance(document, dict):
            raise BridgeProtocolError("INVALID_ENVELOPE", "message root must be an object")
        return document

    def _validate(self, document: dict[str, Any]) -> UnityToPythonMessage:
        supplied_version = document.get("protocol_version")
        is_bootstrap = document.get("message_type") == MessageType.CLIENT_HELLO.value
        accepted_versions = SUPPORTED_PROTOCOL_VERSIONS if is_bootstrap else (self.negotiated_protocol_version,)
        if supplied_version not in accepted_versions:
            raise BridgeProtocolError(
                "INCOMPATIBLE_PROTOCOL_VERSION",
                f"session accepts {accepted_versions}, received {supplied_version!r}",
            )
        try:
            return _UNITY_TO_PYTHON_ADAPTER.validate_python(document)
        except ValidationError as exc:
            raise BridgeProtocolError("INVALID_UNITY_TO_PYTHON_ENVELOPE", str(exc)) from exc

    @staticmethod
    def _fingerprint(document: dict[str, Any]) -> str:
        canonical = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
