using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace STWM.AITown.Bridge
{
    public static class TownProtocol
    {
        public const string Version = "0.2.0";
        public const string LegacyBootstrapVersion = "0.1.0";
        public const string ConfigVersion = "v0";
        public const string SchemaVersion = "v0.1";
        public const string UnityEditorVersion = "6000.4.2f1";
        public const string DefaultWorldId = "demo_world";

        public static readonly HashSet<string> InboundMessageTypes = new HashSet<string>(StringComparer.Ordinal)
        {
            "server_hello",
            "asset_registry_result",
            "world_snapshot",
            "simulation_clock_updated",
            "action_started",
            "action_phase_changed",
            "action_cancelled",
            "agent_state_delta",
            "relationship_delta",
            "world_event_created",
            "dialogue_line_ready",
            "debug_decision_trace"
        };

        public static readonly HashSet<string> OutboundMessageTypes = new HashSet<string>(StringComparer.Ordinal)
        {
            "client_hello",
            "asset_registry",
            "client_ready",
            "movement_arrived",
            "movement_failed",
            "movement_cancelled",
            "presentation_completed",
            "player_utterance",
            "player_end_conversation",
            "set_time_scale_request",
            "pause_request"
        };

        public static readonly HashSet<string> ActionCorrelatedMessageTypes = new HashSet<string>(StringComparer.Ordinal)
        {
            "action_started",
            "action_phase_changed",
            "action_cancelled",
            "movement_arrived",
            "movement_failed",
            "movement_cancelled",
            "presentation_completed"
        };
    }

    public enum AnimationSemantic
    {
        IDLE,
        SLEEP,
        EAT,
        SHOWER_HIDDEN,
        SIT,
        WORK_DESK,
        WORK_STANDING,
        WORK_WORKSHOP,
        DRINK,
        WALK,
        TALK_NEUTRAL,
        TALK_POSITIVE,
        TALK_NEGATIVE,
        CARRY_GROCERY
    }

    public enum MovementFailureReason
    {
        NO_PATH,
        DESTINATION_DISABLED,
        SLOT_BLOCKED,
        AGENT_DISABLED,
        TIMEOUT,
        UNKNOWN
    }

    public enum MovementCancellationReason
    {
        NAVIGATION_STOPPED,
        SCENE_UNLOADED,
        CLIENT_SHUTDOWN,
        UNKNOWN
    }

    public enum AssetValidationSeverity
    {
        ERROR,
        WARNING,
        INFO
    }

    public sealed class TownEnvelope
    {
        [JsonProperty("protocol_version", Required = Required.Always)]
        public string ProtocolVersion { get; set; }

        [JsonProperty("message_id", Required = Required.Always)]
        public string MessageId { get; set; }

        [JsonProperty("message_type", Required = Required.Always)]
        public string MessageType { get; set; }

        [JsonProperty("sent_at_utc", Required = Required.Always)]
        public string SentAtUtc { get; set; }

        [JsonProperty("world_id", Required = Required.Always)]
        public string WorldId { get; set; }

        [JsonProperty("state_version", Required = Required.Always)]
        public long StateVersion { get; set; }

        [JsonProperty("correlation_id", Required = Required.AllowNull)]
        public string CorrelationId { get; set; }

        [JsonProperty("payload", Required = Required.Always)]
        public JObject Payload { get; set; }

        public T ReadPayload<T>()
        {
            if (Payload == null)
            {
                throw new JsonSerializationException("Envelope payload is null.");
            }

            return Payload.ToObject<T>() ?? throw new JsonSerializationException($"Could not decode payload {typeof(T).Name}.");
        }

        public string ToJson()
        {
            return JsonConvert.SerializeObject(this, Formatting.None);
        }

        public static TownEnvelope Create(
            string messageType,
            object payload,
            string worldId,
            long stateVersion,
            string correlationId = null)
        {
            if (!TownProtocol.OutboundMessageTypes.Contains(messageType))
            {
                throw new ArgumentException($"Not a frozen outbound message type: {messageType}", nameof(messageType));
            }

            var envelope = new TownEnvelope
            {
                ProtocolVersion = TownProtocol.Version,
                MessageId = TownMessageId.Next(),
                MessageType = messageType,
                SentAtUtc = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture),
                WorldId = worldId,
                StateVersion = Math.Max(0, stateVersion),
                CorrelationId = correlationId,
                Payload = JObject.FromObject(payload)
            };
            if (!ValidateActionCorrelation(envelope, out var error))
            {
                throw new ArgumentException(error, nameof(correlationId));
            }

            return envelope;
        }

        public static bool TryParse(string json, string expectedWorldId, out TownEnvelope envelope, out string error)
        {
            envelope = null;
            error = null;
            if (string.IsNullOrWhiteSpace(json))
            {
                error = "EMPTY_MESSAGE";
                return false;
            }

            try
            {
                envelope = JsonConvert.DeserializeObject<TownEnvelope>(json);
            }
            catch (JsonException exception)
            {
                error = $"INVALID_JSON: {exception.Message}";
                return false;
            }

            if (envelope == null)
            {
                error = "INVALID_ENVELOPE";
                return false;
            }

            var legacyServerHello = string.Equals(envelope.ProtocolVersion, TownProtocol.LegacyBootstrapVersion, StringComparison.Ordinal)
                                    && string.Equals(envelope.MessageType, "server_hello", StringComparison.Ordinal);
            if (!string.Equals(envelope.ProtocolVersion, TownProtocol.Version, StringComparison.Ordinal) && !legacyServerHello)
            {
                error = $"PROTOCOL_VERSION_MISMATCH: expected {TownProtocol.Version}, received {envelope.ProtocolVersion}";
                return false;
            }

            if (string.IsNullOrEmpty(envelope.MessageId) || !envelope.MessageId.StartsWith("msg_", StringComparison.Ordinal))
            {
                error = "INVALID_MESSAGE_ID";
                return false;
            }

            for (var index = 4; index < envelope.MessageId.Length; index++)
            {
                if (!char.IsDigit(envelope.MessageId[index]))
                {
                    error = "INVALID_MESSAGE_ID";
                    return false;
                }
            }

            if (envelope.MessageId.Length == 4)
            {
                error = "INVALID_MESSAGE_ID";
                return false;
            }

            if (!TownProtocol.InboundMessageTypes.Contains(envelope.MessageType))
            {
                error = $"UNKNOWN_MESSAGE_TYPE: {envelope.MessageType}";
                return false;
            }

            if (!string.Equals(envelope.WorldId, expectedWorldId, StringComparison.Ordinal))
            {
                error = $"WORLD_ID_MISMATCH: expected {expectedWorldId}, received {envelope.WorldId}";
                return false;
            }

            if (envelope.StateVersion < 0)
            {
                error = "NEGATIVE_STATE_VERSION";
                return false;
            }

            if (!DateTimeOffset.TryParse(
                    envelope.SentAtUtc,
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                    out _))
            {
                error = "INVALID_SENT_AT_UTC";
                return false;
            }

            if (envelope.Payload == null)
            {
                error = "MISSING_PAYLOAD";
                return false;
            }

            if (!ValidateActionCorrelation(envelope, out error))
            {
                return false;
            }

            return true;
        }

        private static bool ValidateActionCorrelation(TownEnvelope envelope, out string error)
        {
            error = null;
            if (!TownProtocol.ActionCorrelatedMessageTypes.Contains(envelope.MessageType))
            {
                return true;
            }

            var actionId = envelope.Payload?.Value<string>("action_id");
            if (string.IsNullOrEmpty(actionId) || !string.Equals(envelope.CorrelationId, actionId, StringComparison.Ordinal))
            {
                error = "ACTION_CORRELATION_MISMATCH";
                return false;
            }

            return true;
        }
    }

    internal static class TownMessageId
    {
        private static long sequence = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() * 1000L;

        public static string Next()
        {
            return $"msg_{Interlocked.Increment(ref sequence)}";
        }
    }

    public sealed class ClientHelloPayload
    {
        [JsonProperty("client_name")]
        public string ClientName { get; set; } = "unity";

        [JsonProperty("unity_editor_version")]
        public string UnityEditorVersion { get; set; } = TownProtocol.UnityEditorVersion;

        [JsonProperty("supported_protocol_versions", ObjectCreationHandling = ObjectCreationHandling.Replace)]
        public List<string> SupportedProtocolVersions { get; set; } = new List<string>
        {
            TownProtocol.Version,
            TownProtocol.LegacyBootstrapVersion
        };
    }

    public sealed class ServerHelloPayload
    {
        [JsonProperty("server_name")]
        public string ServerName { get; set; }

        [JsonProperty("accepted_protocol_version")]
        public string AcceptedProtocolVersion { get; set; }

        [JsonProperty("config_version")]
        public string ConfigVersion { get; set; }

        [JsonProperty("schema_version")]
        public string SchemaVersion { get; set; }
    }

    public sealed class RegisteredLocationDto
    {
        [JsonProperty("location_id")]
        public string LocationId { get; set; }

        [JsonProperty("location_type")]
        public string LocationType { get; set; }
    }

    public sealed class RegisteredInteractionSlotDto
    {
        [JsonProperty("slot_index")]
        public int SlotIndex { get; set; }

        [JsonProperty("supported_animation_semantics")]
        public List<string> SupportedAnimationSemantics { get; set; } = new List<string>();
    }

    public sealed class RegisteredObjectDto
    {
        [JsonProperty("object_id")]
        public string ObjectId { get; set; }

        [JsonProperty("object_type")]
        public string ObjectType { get; set; }

        [JsonProperty("location_id")]
        public string LocationId { get; set; }

        [JsonProperty("capability_tags")]
        public List<string> CapabilityTags { get; set; } = new List<string>();

        [JsonProperty("enabled")]
        public bool Enabled { get; set; }

        [JsonProperty("interaction_slots")]
        public List<RegisteredInteractionSlotDto> InteractionSlots { get; set; } = new List<RegisteredInteractionSlotDto>();
    }

    public sealed class RegisteredNpcViewDto
    {
        [JsonProperty("agent_id")]
        public string AgentId { get; set; }
    }

    public sealed class AssetRegistryPayload
    {
        [JsonProperty("locations")]
        public List<RegisteredLocationDto> Locations { get; set; } = new List<RegisteredLocationDto>();

        [JsonProperty("objects")]
        public List<RegisteredObjectDto> Objects { get; set; } = new List<RegisteredObjectDto>();

        [JsonProperty("npc_views")]
        public List<RegisteredNpcViewDto> NpcViews { get; set; } = new List<RegisteredNpcViewDto>();

        [JsonProperty("mapped_animation_semantics")]
        public List<string> MappedAnimationSemantics { get; set; } = new List<string>();
    }

    public sealed class AssetValidationIssueDto
    {
        [JsonProperty("severity")]
        public string Severity { get; set; }

        [JsonProperty("code")]
        public string Code { get; set; }

        [JsonProperty("message")]
        public string Message { get; set; }

        [JsonProperty("entity_id")]
        public string EntityId { get; set; }
    }

    public sealed class AssetRegistryResultPayload
    {
        [JsonProperty("accepted")]
        public bool Accepted { get; set; }

        [JsonProperty("issues")]
        public List<AssetValidationIssueDto> Issues { get; set; } = new List<AssetValidationIssueDto>();
    }

    public sealed class ClientReadyPayload
    {
        [JsonProperty("registry_message_id")]
        public string RegistryMessageId { get; set; }
    }

    public sealed class SimulationClockPayload
    {
        [JsonProperty("game_minute")]
        public long GameMinute { get; set; }

        [JsonProperty("time_scale")]
        public float TimeScale { get; set; }

        [JsonProperty("paused")]
        public bool Paused { get; set; }
    }

    public sealed class ActionStartedPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("agent_ids")]
        public List<string> AgentIds { get; set; } = new List<string>();

        [JsonProperty("behavior_id")]
        public string BehaviorId { get; set; }

        [JsonProperty("destination_location_id")]
        public string DestinationLocationId { get; set; }

        [JsonProperty("target_object_ids")]
        public List<string> TargetObjectIds { get; set; } = new List<string>();

        [JsonProperty("animation_semantic")]
        public string AnimationSemantic { get; set; }

        [JsonProperty("prop_semantic")]
        public string PropSemantic { get; set; }

        [JsonProperty("planned_duration_minutes")]
        public long PlannedDurationMinutes { get; set; }
    }

    public sealed class ActionPhaseChangedPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("phase")]
        public string Phase { get; set; }
    }

    public sealed class ActionCancelledPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("reason")]
        public string Reason { get; set; }
    }

    public sealed class AgentStateDeltaPayload
    {
        [JsonProperty("agent_id")]
        public string AgentId { get; set; }

        [JsonProperty("current_location_id")]
        public string CurrentLocationId { get; set; }

        [JsonProperty("current_action_id")]
        public string CurrentActionId { get; set; }

        [JsonProperty("needs")]
        public JObject Needs { get; set; }
    }

    public sealed class MovementArrivedPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("agent_id")]
        public string AgentId { get; set; }

        [JsonProperty("object_id")]
        public string ObjectId { get; set; }

        [JsonProperty("slot_index")]
        public int? SlotIndex { get; set; }
    }

    public sealed class MovementFailedPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("agent_id")]
        public string AgentId { get; set; }

        [JsonProperty("reason")]
        public string Reason { get; set; }
    }

    public sealed class MovementCancelledPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("agent_id")]
        public string AgentId { get; set; }

        [JsonProperty("reason")]
        public string Reason { get; set; }
    }

    public sealed class PresentationCompletedPayload
    {
        [JsonProperty("action_id")]
        public string ActionId { get; set; }

        [JsonProperty("agent_id")]
        public string AgentId { get; set; }
    }

    public sealed class SetTimeScaleRequestPayload
    {
        [JsonProperty("requested_time_scale")]
        public float RequestedTimeScale { get; set; }
    }

    public sealed class PauseRequestPayload
    {
        [JsonProperty("paused")]
        public bool Paused { get; set; }
    }
}
