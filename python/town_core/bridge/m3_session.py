"""Generation-safe protocol 0.3 M3_FULL handshake and ingress session."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from town_core.bridge.m3_registry import M3FullAssetRegistryValidator
from town_core.bridge.session import BridgeProtocolError, SessionPhase
from town_core.domain.enums import M3_PROTOCOL_VERSION, MessageType
from town_core.domain.protocol_models import (
    AssetRegistryResultV030Message,
    AssetRegistryV030Message,
    ClientHelloV030Message,
    ClientReadyV030Message,
    MovementArrivedV030Message,
    MovementCancelledV030Message,
    MovementFailedV030Message,
    PauseRequestV030Message,
    PresentationCompletedV030Message,
    PythonToUnityMessageV030,
    ServerHelloV030Message,
    ServerHelloV030Payload,
    SetTimeScaleRequestV030Message,
    UnityToPythonMessageV030,
    select_m3_protocol_version,
)

_UNITY_TO_PYTHON_ADAPTER: TypeAdapter[UnityToPythonMessageV030] = TypeAdapter(UnityToPythonMessageV030)
_V030: Any = M3_PROTOCOL_VERSION


class M3BridgeSession:
    """One M3 transport generation; only the current ready session may mutate."""

    def __init__(self, runtime: Any, *, generation: int) -> None:
        self.runtime = runtime
        self.generation = generation
        self.phase = SessionPhase.AWAITING_CLIENT_HELLO
        self.accepted_registry_message_id: str | None = None
        self.snapshot_state_version: int | None = None
        self.last_client_state_version = 0
        self.negotiated_protocol_version: str | None = None
        self._seen: dict[str, tuple[str, tuple[PythonToUnityMessageV030, ...]]] = {}

    def receive_json(self, raw: str | bytes | dict[str, Any]) -> tuple[PythonToUnityMessageV030, ...]:
        if not self.runtime.is_current_generation(self.generation):
            raise BridgeProtocolError(
                "OBSOLETE_CONNECTION_GENERATION",
                "a newer transport generation owns the M3 bridge",
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
                "FUTURE_STATE_VERSION", "client claims an M3 authority version Python has not committed"
            )

        outputs, repeatable = self._dispatch(message)
        self.last_client_state_version = max(self.last_client_state_version, message.state_version)
        self._seen[message.message_id] = (fingerprint, outputs if repeatable else ())
        return outputs

    def disconnect(self) -> None:
        self.phase = SessionPhase.DISCONNECTED
        self.runtime.disconnect(self.generation)

    def _dispatch(self, message: UnityToPythonMessageV030) -> tuple[tuple[PythonToUnityMessageV030, ...], bool]:
        if isinstance(message, ClientHelloV030Message):
            self._require_phase(SessionPhase.AWAITING_CLIENT_HELLO)
            try:
                selected = select_m3_protocol_version(message.payload.supported_protocol_versions)
            except ValueError as exc:
                raise BridgeProtocolError("M3_PROTOCOL_NEGOTIATION_FAILED", str(exc)) from exc
            self.negotiated_protocol_version = selected
            self.runtime.record_negotiated_protocol(self.generation, selected)
            hello_response = ServerHelloV030Message(
                protocol_version=_V030,
                message_id=self.runtime.next_message_id(),
                message_type=MessageType.SERVER_HELLO,
                sent_at_utc=self.runtime._now(),
                world_id=self.runtime.world_id,
                state_version=self.runtime.engine.state.state_version,
                correlation_id=message.message_id,
                payload=ServerHelloV030Payload(
                    server_name="python_town_core",
                    accepted_protocol_version=cast(Any, M3_PROTOCOL_VERSION),
                    config_version="v0",
                    schema_version="v0.1",
                ),
            )
            self.phase = SessionPhase.AWAITING_ASSET_REGISTRY
            return (hello_response,), True

        if isinstance(message, AssetRegistryV030Message):
            self._require_phase(SessionPhase.AWAITING_ASSET_REGISTRY)
            result = M3FullAssetRegistryValidator(
                self.runtime.catalog,
                self.runtime.m3_catalogs,
                self.runtime.engine.state,
            ).validate(message.payload)
            registry_response = AssetRegistryResultV030Message(
                protocol_version=_V030,
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
            self.runtime.record_snapshot_evidence(self.generation, message.message_id)
            self.phase = SessionPhase.AWAITING_CLIENT_READY
            return (registry_response, snapshot), True

        if isinstance(message, ClientReadyV030Message):
            self._require_phase(SessionPhase.AWAITING_CLIENT_READY)
            if message.payload.registry_message_id != self.accepted_registry_message_id:
                raise BridgeProtocolError("REGISTRY_ACK_MISMATCH", "client_ready references an unaccepted registry")
            if message.state_version != self.snapshot_state_version:
                raise BridgeProtocolError("SNAPSHOT_ACK_MISMATCH", "client_ready did not apply the fresh snapshot")
            self.runtime.mark_ready(self.generation)
            self.phase = SessionPhase.READY
            return (self.runtime.clock_message(correlation_id=message.message_id),), True

        self._require_phase(SessionPhase.READY)
        if isinstance(message, MovementArrivedV030Message):
            arrived = message.payload
            return (
                self.runtime.movement_arrived(
                    generation=self.generation,
                    action_id=arrived.action_id,
                    agent_id=arrived.agent_id,
                    state_version=message.state_version,
                    object_id=arrived.object_id,
                    slot_index=arrived.slot_index,
                ),
                False,
            )
        if isinstance(message, MovementFailedV030Message):
            failed = message.payload
            return (
                self.runtime.movement_failed(
                    generation=self.generation,
                    action_id=failed.action_id,
                    agent_id=failed.agent_id,
                    state_version=message.state_version,
                    reason=failed.reason,
                ),
                False,
            )
        if isinstance(message, MovementCancelledV030Message):
            cancelled = message.payload
            return (
                self.runtime.movement_cancelled(
                    generation=self.generation,
                    action_id=cancelled.action_id,
                    agent_id=cancelled.agent_id,
                    state_version=message.state_version,
                    reason=cancelled.reason,
                ),
                False,
            )
        if isinstance(message, PresentationCompletedV030Message):
            completed = message.payload
            return (
                self.runtime.presentation_completed(
                    generation=self.generation,
                    action_id=completed.action_id,
                    agent_id=completed.agent_id,
                    state_version=message.state_version,
                ),
                False,
            )
        if isinstance(message, SetTimeScaleRequestV030Message):
            return (self.runtime.set_time_scale(message.payload.requested_time_scale),), True
        if isinstance(message, PauseRequestV030Message):
            return (self.runtime.set_paused(message.payload.paused),), True
        raise BridgeProtocolError(
            "UNSUPPORTED_M3_CLIENT_MESSAGE",
            f"M3 authority does not accept {message.message_type.value} in this milestone",
        )

    def _validate(self, document: dict[str, Any]) -> UnityToPythonMessageV030:
        if document.get("protocol_version") != M3_PROTOCOL_VERSION:
            raise BridgeProtocolError(
                "INCOMPATIBLE_PROTOCOL_VERSION",
                f"M3_FULL accepts only {M3_PROTOCOL_VERSION!r}",
            )
        try:
            return _UNITY_TO_PYTHON_ADAPTER.validate_python(document)
        except ValidationError as exc:
            raise BridgeProtocolError("INVALID_M3_UNITY_TO_PYTHON_ENVELOPE", str(exc)) from exc

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

    @staticmethod
    def _fingerprint(document: dict[str, Any]) -> str:
        canonical = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
