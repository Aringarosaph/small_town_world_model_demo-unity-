using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using STWM.AITown.Debugging;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine;

namespace STWM.AITown.Bridge
{
    public enum BridgeConnectionState
    {
        Disconnected,
        Connecting,
        AwaitingServerHello,
        AwaitingRegistryResult,
        AwaitingWorldSnapshot,
        Ready,
        DiagnosticOnly,
        Reconnecting,
        ProtocolRejected
    }

    public enum TownBridgeProtocolProfile
    {
        M2_SCOPED_V020,
        M3_FULL_V030
    }

    [DisallowMultipleComponent]
    public sealed class TownBridgeClient : MonoBehaviour
    {
        private const int SeenMessageCapacity = 4096;
        public const string DefaultEndpointUrl = "ws://127.0.0.1:8765/town";

        [Header("Local authority endpoint")]
        [SerializeField] private string endpointUrl = DefaultEndpointUrl;
        [SerializeField] private string worldId = TownProtocol.DefaultWorldId;
        [SerializeField] private bool connectOnStart = true;
        [SerializeField] private TownBridgeProtocolProfile protocolProfile = TownBridgeProtocolProfile.M2_SCOPED_V020;

        [Header("Transport liveness")]
        [SerializeField, Min(1f)] private float keepAliveSeconds = 10f;
        [SerializeField, Min(1f)] private float handshakeTimeoutSeconds = 15f;
        [SerializeField, Min(0.1f)] private float reconnectInitialSeconds = 0.5f;
        [SerializeField, Min(0.5f)] private float reconnectMaximumSeconds = 10f;

        [Header("Presentation")]
        [SerializeField] private TownDebugPanel debugPanel;

        private readonly ConcurrentQueue<InboundFrame> inboundMessages = new ConcurrentQueue<InboundFrame>();
        private readonly ConcurrentQueue<Action> mainThreadActions = new ConcurrentQueue<Action>();
        private readonly Dictionary<string, JToken> seenMessageContents = new Dictionary<string, JToken>(StringComparer.Ordinal);
        private readonly Queue<string> seenMessageOrder = new Queue<string>();
        private readonly Dictionary<string, NpcView> actionViews = new Dictionary<string, NpcView>(StringComparer.Ordinal);
        private readonly Dictionary<string, ActionPresentationGroup> actionGroups = new Dictionary<string, ActionPresentationGroup>(StringComparer.Ordinal);
        private readonly Dictionary<string, JObject> householdAuthority = new Dictionary<string, JObject>(StringComparer.Ordinal);
        private readonly Dictionary<string, string> agentHouseholds = new Dictionary<string, string>(StringComparer.Ordinal);
        private readonly SemaphoreSlim sendGate = new SemaphoreSlim(1, 1);

        private Func<ITownSocketTransport> transportFactory = () => new ClientWebSocketTransport();
        private ITownSocketTransport transport;
        private CancellationTokenSource connectionCancellation;
        private bool connectInFlight;
        private bool shuttingDown;
        private bool recordedReplaySession;
        private float reconnectAtUnscaledTime;
        private int reconnectAttempt;
        private DateTime lastInboundUtc;
        private string clientHelloMessageId;
        private string registryMessageId;
        private string recordedRegistryMessageId;
        private long lastAppliedStateVersion = -1;
        private long minimumResyncStateVersion = -1;
        private int connectionGeneration;
        private bool localRegistryHasErrors;

        public BridgeConnectionState ConnectionState { get; private set; } = BridgeConnectionState.Disconnected;
        public long LastAppliedStateVersion => Math.Max(0, lastAppliedStateVersion);
        public string WorldId => worldId;
        public string EndpointUrl => endpointUrl;
        public int ConnectionGeneration => connectionGeneration;
        public bool IsReady => ConnectionState == BridgeConnectionState.Ready;
        public TownBridgeProtocolProfile ProtocolProfile => protocolProfile;
        public string ActiveProtocolVersion => protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030
            ? TownProtocol.M3Version
            : TownProtocol.M2Version;
        public int ActivePresentationGroupCount => actionGroups.Count;

        public event Action<BridgeConnectionState> ConnectionStateChanged;
        public event Action<TownEnvelope> EnvelopeApplied;
        public event Action<TownEnvelope> EnvelopeSending;
        public event Action<string> BridgeError;
        public event Action<string, string, MovementCancellationReason> MovementCancellationReported;

        private void Awake()
        {
            if (debugPanel == null)
            {
                debugPanel = FindFirstObjectByType<TownDebugPanel>();
            }

            debugPanel?.BindBridge(this);
        }

        private void Start()
        {
            if (!string.Equals(Application.unityVersion, TownProtocol.UnityEditorVersion, StringComparison.Ordinal))
            {
                RejectProtocol($"UNITY_VERSION_MISMATCH: expected {TownProtocol.UnityEditorVersion}, running {Application.unityVersion}");
                return;
            }

            if (connectOnStart)
            {
                Connect();
            }
        }

        private void Update()
        {
            if (shuttingDown)
            {
                while (mainThreadActions.TryDequeue(out _)) { }
                while (inboundMessages.TryDequeue(out _)) { }
                return;
            }

            while (mainThreadActions.TryDequeue(out var callback))
            {
                callback();
            }

            var processed = 0;
            while (processed < 128 && inboundMessages.TryDequeue(out var frame))
            {
                if (frame.Generation == connectionGeneration)
                {
                    ProcessInboundJson(frame.Json);
                }
                else
                {
                    debugPanel?.RecordInfo($"Obsolete connection generation ignored: {frame.Generation}");
                }

                processed++;
            }

            if (ConnectionState == BridgeConnectionState.Reconnecting && Time.unscaledTime >= reconnectAtUnscaledTime)
            {
                Connect();
            }

            if (IsHandshakeState(ConnectionState)
                && lastInboundUtc != default
                && (DateTime.UtcNow - lastInboundUtc).TotalSeconds > handshakeTimeoutSeconds)
            {
                HandleTransportEnded("HANDSHAKE_TIMEOUT", connectionGeneration);
            }
        }

        private void OnDestroy()
        {
            shuttingDown = true;
            ResetPresentationProjection();
            connectionCancellation?.Cancel();
            transport?.Dispose();
            transport = null;
            connectionCancellation?.Dispose();
            connectionCancellation = null;
            sendGate.Dispose();
        }

        public void Configure(string endpoint, string expectedWorldId, bool shouldConnectOnStart)
        {
            endpointUrl = endpoint;
            worldId = expectedWorldId;
            connectOnStart = shouldConnectOnStart;
            protocolProfile = TownBridgeProtocolProfile.M2_SCOPED_V020;
        }

        public void ConfigureM3(string endpoint, string expectedWorldId, bool shouldConnectOnStart)
        {
            endpointUrl = endpoint;
            worldId = expectedWorldId;
            connectOnStart = shouldConnectOnStart;
            protocolProfile = TownBridgeProtocolProfile.M3_FULL_V030;
        }

        public void BindDebugPanel(TownDebugPanel panel)
        {
            debugPanel = panel;
            panel?.BindBridge(this);
        }

        public void SetTransportFactoryForTests(Func<ITownSocketTransport> factory)
        {
            transportFactory = factory ?? throw new ArgumentNullException(nameof(factory));
        }

        public void Connect()
        {
            if (shuttingDown || connectInFlight || ConnectionState == BridgeConnectionState.ProtocolRejected)
            {
                return;
            }

            if (!Uri.TryCreate(endpointUrl, UriKind.Absolute, out var endpoint)
                || (endpoint.Scheme != "ws" && endpoint.Scheme != "wss"))
            {
                RejectProtocol($"INVALID_ENDPOINT: {endpointUrl}");
                return;
            }

            connectInFlight = true;
            recordedReplaySession = false;
            recordedRegistryMessageId = null;
            clientHelloMessageId = null;
            var generation = Interlocked.Increment(ref connectionGeneration);
            Transition(ConnectionState == BridgeConnectionState.Reconnecting
                ? BridgeConnectionState.Reconnecting
                : BridgeConnectionState.Connecting);
            ConnectSessionAsync(endpoint, generation).Forget(this, "connect");
        }

        public void Disconnect()
        {
            shuttingDown = true;
            connectionCancellation?.Cancel();
            CloseTransportAsync().Forget(this, "disconnect");
            Transition(BridgeConnectionState.Disconnected);
        }

        public void InjectInboundForReplay(string json)
        {
            inboundMessages.Enqueue(new InboundFrame(connectionGeneration, json));
        }

        public void InjectInboundForTests(int generation, string json)
        {
            inboundMessages.Enqueue(new InboundFrame(generation, json));
        }

        public void BeginRecordedReplaySession(
            string clientHelloMessageIdOverride = null,
            string registryMessageIdOverride = null)
        {
            if (transport != null && transport.State == WebSocketState.Open)
            {
                throw new InvalidOperationException("Recorded replay cannot replace a live bridge session.");
            }

            registryMessageId = null;
            recordedRegistryMessageId = registryMessageIdOverride;
            clientHelloMessageId = clientHelloMessageIdOverride;
            recordedReplaySession = true;
            Interlocked.Increment(ref connectionGeneration);
            lastInboundUtc = DateTime.UtcNow;
            Transition(BridgeConnectionState.AwaitingServerHello);
        }

        public bool ProcessInboundJson(string json)
        {
            if (!TownEnvelope.TryParse(
                    json,
                    worldId,
                    ActiveProtocolVersion,
                    protocolProfile == TownBridgeProtocolProfile.M2_SCOPED_V020,
                    out var envelope,
                    out var error))
            {
                if (error.StartsWith("PROTOCOL_VERSION_MISMATCH", StringComparison.Ordinal))
                {
                    RejectProtocol(error);
                }
                else
                {
                    ReportError(error);
                }

                return false;
            }

            var replayStatus = RememberMessage(envelope);
            if (replayStatus == MessageReplayStatus.Duplicate)
            {
                debugPanel?.RecordInfo($"Duplicate ignored: {envelope.MessageId}");
                return false;
            }

            if (replayStatus == MessageReplayStatus.Conflict)
            {
                ReportError($"MESSAGE_ID_CONTENT_CONFLICT: {envelope.MessageId}");
                return false;
            }

            lastInboundUtc = DateTime.UtcNow;
            try
            {
                return ApplyEnvelope(envelope);
            }
            catch (Exception exception) when (exception is JsonException || exception is InvalidOperationException)
            {
                ReportError($"MESSAGE_REJECTED {envelope.MessageId}: {exception.Message}");
                return false;
            }
        }

        public void ReportMovementArrived(string actionId, string agentId, string objectId, int? slotIndex)
        {
            Send(CreateOutbound(
                "movement_arrived",
                new MovementArrivedPayload
                {
                    ActionId = actionId,
                    AgentId = agentId,
                    ObjectId = objectId,
                    SlotIndex = slotIndex
                },
                worldId,
                LastAppliedStateVersion,
                actionId));
        }

        public void ReportMovementFailed(string actionId, string agentId, MovementFailureReason reason)
        {
            Send(CreateOutbound(
                "movement_failed",
                new MovementFailedPayload
                {
                    ActionId = actionId,
                    AgentId = agentId,
                    Reason = reason.ToString()
                },
                worldId,
                LastAppliedStateVersion,
                actionId));
        }

        public void ReportMovementCancelled(string actionId, string agentId, MovementCancellationReason reason)
        {
            Send(CreateOutbound(
                "movement_cancelled",
                new MovementCancelledPayload
                {
                    ActionId = actionId,
                    AgentId = agentId,
                    Reason = reason.ToString()
                },
                worldId,
                LastAppliedStateVersion,
                actionId));
            MovementCancellationReported?.Invoke(actionId, agentId, reason);
        }

        public void ReportPresentationCompleted(string actionId, string agentId)
        {
            Send(CreateOutbound(
                "presentation_completed",
                new PresentationCompletedPayload { ActionId = actionId, AgentId = agentId },
                worldId,
                LastAppliedStateVersion,
                actionId));
        }

        public void RequestTimeScale(float requestedTimeScale)
        {
            if (!IsAllowedTimeScale(requestedTimeScale))
            {
                throw new ArgumentOutOfRangeException(
                    nameof(requestedTimeScale),
                    requestedTimeScale,
                    "UNITY_LIVE time scale must be exactly 0x, 1x, 2x, or 4x.");
            }

            EnsureReadyForControlRequest("set_time_scale_request");

            Send(CreateOutbound(
                "set_time_scale_request",
                new SetTimeScaleRequestPayload { RequestedTimeScale = requestedTimeScale },
                worldId,
                LastAppliedStateVersion));
        }

        public void RequestPause(bool shouldPause)
        {
            EnsureReadyForControlRequest("pause_request");
            Send(CreateOutbound(
                "pause_request",
                new PauseRequestPayload { Paused = shouldPause },
                worldId,
                LastAppliedStateVersion));
        }

        public static bool IsAllowedTimeScale(float value)
        {
            return value == 0f || value == 1f || value == 2f || value == 4f;
        }

        private void EnsureReadyForControlRequest(string messageType)
        {
            if (!IsReady)
            {
                throw new InvalidOperationException(
                    $"{messageType} requires a completed {ActiveProtocolVersion} handshake, registry, snapshot, and client_ready.");
            }
        }

        private async Task ConnectSessionAsync(Uri endpoint, int generation)
        {
            ITownSocketTransport nextTransport = null;
            try
            {
                connectionCancellation?.Cancel();
                connectionCancellation?.Dispose();
                connectionCancellation = new CancellationTokenSource();
                nextTransport = transportFactory();
                await nextTransport.ConnectAsync(
                        endpoint,
                        TimeSpan.FromSeconds(keepAliveSeconds),
                        connectionCancellation.Token)
                    .ConfigureAwait(false);
                if (generation != Volatile.Read(ref connectionGeneration))
                {
                    nextTransport.Dispose();
                    return;
                }

                transport?.Dispose();
                transport = nextTransport;
                nextTransport = null;
                _ = ReceiveLoopAsync(transport, generation, connectionCancellation.Token);
                mainThreadActions.Enqueue(() =>
                {
                    if (generation != connectionGeneration)
                    {
                        return;
                    }

                    connectInFlight = false;
                    reconnectAttempt = 0;
                    registryMessageId = null;
                    lastInboundUtc = DateTime.UtcNow;
                    Transition(BridgeConnectionState.AwaitingServerHello);
                    var helloPayload = protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030
                        ? (object)new ClientHelloV030Payload()
                        : new ClientHelloPayload();
                    var clientHello = CreateOutbound(
                        "client_hello",
                        helloPayload,
                        worldId,
                        LastAppliedStateVersion);
                    clientHelloMessageId = clientHello.MessageId;
                    Send(clientHello);
                });
            }
            catch (Exception exception) when (exception is WebSocketException
                                              || exception is OperationCanceledException
                                              || exception is InvalidOperationException)
            {
                nextTransport?.Dispose();
                mainThreadActions.Enqueue(() =>
                {
                    if (generation != connectionGeneration)
                    {
                        return;
                    }

                    connectInFlight = false;
                    HandleTransportEnded($"CONNECT_FAILED: {exception.Message}", generation);
                });
            }
        }

        private async Task ReceiveLoopAsync(
            ITownSocketTransport activeTransport,
            int generation,
            CancellationToken cancellationToken)
        {
            try
            {
                while (!cancellationToken.IsCancellationRequested && activeTransport.State == WebSocketState.Open)
                {
                    var text = await activeTransport.ReceiveTextAsync(cancellationToken).ConfigureAwait(false);
                    if (text == null)
                    {
                        break;
                    }

                    inboundMessages.Enqueue(new InboundFrame(generation, text));
                }
            }
            catch (Exception exception) when (exception is WebSocketException
                                              || exception is OperationCanceledException
                                              || exception is InvalidOperationException
                                              || exception is System.IO.InvalidDataException)
            {
                if (!cancellationToken.IsCancellationRequested)
                {
                    mainThreadActions.Enqueue(() => HandleTransportEnded($"RECEIVE_FAILED: {exception.Message}", generation));
                }

                return;
            }

            if (!cancellationToken.IsCancellationRequested)
            {
                mainThreadActions.Enqueue(() => HandleTransportEnded("REMOTE_CLOSED", generation));
            }
        }

        private bool ApplyEnvelope(TownEnvelope envelope)
        {
            switch (envelope.MessageType)
            {
                case "server_hello":
                    return ApplyServerHello(envelope);
                case "asset_registry_result":
                    return ApplyAssetRegistryResult(envelope);
                case "world_snapshot":
                    return ApplyWorldSnapshot(envelope);
            }

            if (ConnectionState != BridgeConnectionState.Ready)
            {
                ReportError($"STATE_MESSAGE_BEFORE_RESYNC: {envelope.MessageType}");
                return false;
            }

            if (envelope.StateVersion < lastAppliedStateVersion)
            {
                debugPanel?.RecordInfo($"Stale ignored: {envelope.MessageId} v{envelope.StateVersion}");
                return false;
            }

            switch (envelope.MessageType)
            {
                case "simulation_clock_updated":
                    var clock = envelope.ReadPayload<SimulationClockPayload>();
                    debugPanel?.SetClock(clock.GameMinute, clock.TimeScale, clock.Paused);
                    break;
                case "action_started":
                    if (protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030)
                    {
                        ApplyActionStartedV030(envelope.ReadPayload<ActionStartedV030Payload>());
                    }
                    else
                    {
                        ApplyActionStarted(envelope.ReadPayload<ActionStartedPayload>());
                    }
                    break;
                case "action_phase_changed":
                    ApplyActionPhase(envelope.ReadPayload<ActionPhaseChangedPayload>());
                    break;
                case "action_cancelled":
                    ApplyActionCancelled(envelope.ReadPayload<ActionCancelledPayload>());
                    break;
                case "agent_state_delta":
                    if (protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030)
                    {
                        ApplyAgentDeltaV030(AgentStateDeltaV030Payload.Parse(envelope.Payload));
                    }
                    else
                    {
                        ApplyAgentDelta(envelope.ReadPayload<AgentStateDeltaPayload>());
                    }
                    break;
                case "household_state_delta":
                    RequireM3Message(envelope.MessageType);
                    ApplyHouseholdDeltaV030(HouseholdStateDeltaV030Payload.Parse(envelope.Payload));
                    break;
                case "debug_decision_trace":
                    RequireM3Message(envelope.MessageType);
                    var trace = envelope.ReadPayload<DebugDecisionTraceV030Payload>();
                    trace.Validate();
                    debugPanel?.SetDecisionTrace(trace);
                    break;
                default:
                    debugPanel?.RecordInfo($"Observed {envelope.MessageType} at v{envelope.StateVersion}");
                    break;
            }

            lastAppliedStateVersion = Math.Max(lastAppliedStateVersion, envelope.StateVersion);
            EnvelopeApplied?.Invoke(envelope);
            return true;
        }

        private bool ApplyServerHello(TownEnvelope envelope)
        {
            if (ConnectionState != BridgeConnectionState.AwaitingServerHello)
            {
                ReportError($"UNEXPECTED_SERVER_HELLO_IN_{ConnectionState}");
                return false;
            }

            var hello = envelope.ReadPayload<ServerHelloPayload>();
            if (!string.Equals(envelope.ProtocolVersion, hello.AcceptedProtocolVersion, StringComparison.Ordinal)
                || !string.Equals(envelope.CorrelationId, clientHelloMessageId, StringComparison.Ordinal)
                || hello.ServerName != "python_town_core"
                || hello.AcceptedProtocolVersion != ActiveProtocolVersion
                || hello.ConfigVersion != TownProtocol.ConfigVersion
                || hello.SchemaVersion != TownProtocol.SchemaVersion)
            {
                RejectProtocol("SERVER_HELLO_CONTRACT_MISMATCH");
                return false;
            }

            var scan = protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030
                ? TownSceneAssetRegistry.ScanFullV0(true)
                : TownSceneAssetRegistry.ScanM2Fixture();
            localRegistryHasErrors = scan.HasErrors;
            debugPanel?.SetRegistryIssues(scan.Issues);
            var registry = CreateOutbound(
                "asset_registry",
                scan.Payload,
                worldId,
                envelope.StateVersion,
                clientHelloMessageId);
            if (!string.IsNullOrEmpty(recordedRegistryMessageId))
            {
                registry.MessageId = recordedRegistryMessageId;
            }

            registryMessageId = registry.MessageId;
            Send(registry);
            Transition(BridgeConnectionState.AwaitingRegistryResult);
            return true;
        }

        private bool ApplyAssetRegistryResult(TownEnvelope envelope)
        {
            if (ConnectionState != BridgeConnectionState.AwaitingRegistryResult)
            {
                ReportError($"UNEXPECTED_REGISTRY_RESULT_IN_{ConnectionState}");
                return false;
            }

            var result = envelope.ReadPayload<AssetRegistryResultPayload>();
            if (!string.Equals(envelope.CorrelationId, registryMessageId, StringComparison.Ordinal))
            {
                ReportError("ASSET_REGISTRY_RESULT_CORRELATION_MISMATCH");
                return false;
            }

            debugPanel?.SetServerRegistryIssues(result.Issues);
            if (!result.Accepted || localRegistryHasErrors)
            {
                Transition(BridgeConnectionState.DiagnosticOnly);
                ReportError(result.Accepted
                    ? $"LOCAL_{ScanProfileName()}_ASSET_REGISTRY_BLOCKED_READY"
                    : "ASSET_REGISTRY_REJECTED");
                return false;
            }

            Transition(BridgeConnectionState.AwaitingWorldSnapshot);
            return true;
        }

        private bool ApplyWorldSnapshot(TownEnvelope envelope)
        {
            if (ConnectionState != BridgeConnectionState.AwaitingWorldSnapshot
                && ConnectionState != BridgeConnectionState.Ready)
            {
                ReportError($"UNEXPECTED_WORLD_SNAPSHOT_IN_{ConnectionState}");
                return false;
            }

            WorldSnapshotV030Payload snapshotV030 = null;
            if (protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030)
            {
                snapshotV030 = envelope.ReadPayload<WorldSnapshotV030Payload>();
                snapshotV030.Validate();
            }

            var world = snapshotV030?.World ?? envelope.Payload["world"] as JObject;
            if (world == null)
            {
                throw new JsonSerializationException("world_snapshot payload has no world object.");
            }

            var snapshotWorldId = world.Value<string>("world_id");
            var snapshotStateVersion = world.Value<long?>("state_version");
            if (!string.Equals(snapshotWorldId, worldId, StringComparison.Ordinal)
                || !snapshotStateVersion.HasValue
                || snapshotStateVersion.Value != envelope.StateVersion)
            {
                throw new InvalidOperationException("world_snapshot envelope/world authority identity mismatch.");
            }

            if (envelope.StateVersion < minimumResyncStateVersion)
            {
                ReportError($"RECONNECT_SNAPSHOT_REGRESSION: minimum {minimumResyncStateVersion}, received {envelope.StateVersion}");
                return false;
            }

            lastAppliedStateVersion = envelope.StateVersion;
            ResetPresentationProjection();
            ApplySnapshotToViews(world);
            if (snapshotV030 != null)
            {
                foreach (var presentation in snapshotV030.ActivePresentations)
                {
                    BindStructuredPresentation(presentation, presentation.Phase);
                }
            }
            if (ConnectionState == BridgeConnectionState.AwaitingWorldSnapshot)
            {
                Send(CreateOutbound(
                    "client_ready",
                    new ClientReadyPayload { RegistryMessageId = registryMessageId },
                    worldId,
                    lastAppliedStateVersion,
                    registryMessageId));
                Transition(BridgeConnectionState.Ready);
            }

            EnvelopeApplied?.Invoke(envelope);
            return true;
        }

        private void ApplySnapshotToViews(JObject world)
        {
            var agents = world["agents"] as JObject;
            if (agents == null)
            {
                throw new JsonSerializationException("World snapshot is missing agents.");
            }

            debugPanel?.SetAvailableAgents(agents.Properties().Select(item => item.Name));

            householdAuthority.Clear();
            agentHouseholds.Clear();
            var snapshotHouseholds = world["households"] as JObject;
            if (snapshotHouseholds != null)
            {
                foreach (var property in snapshotHouseholds.Properties())
                {
                    if (property.Value is JObject household)
                    {
                        householdAuthority[property.Name] = (JObject)household.DeepClone();
                    }
                }
            }

            foreach (var view in TownSceneAssetRegistry.FindNpcViews())
            {
                view.BindBridge(this);
                if (agents[view.AgentId] is JObject agent)
                {
                    view.ApplySnapshotAgent(agent);
                }
            }

            if (debugPanel != null)
            {
                var households = world["households"] as JObject;
                var relationships = world["relationships"] as JArray;
                foreach (var property in agents.Properties())
                {
                    if (!(property.Value is JObject agent))
                    {
                        continue;
                    }

                    var householdId = agent.Value<string>("household_id");
                    if (!string.IsNullOrEmpty(householdId))
                    {
                        agentHouseholds[property.Name] = householdId;
                    }
                    var household = households?[householdId] as JObject;
                    var relationshipCount = relationships?.OfType<JObject>()
                        .Count(item => string.Equals(item.Value<string>("source_agent_id"), property.Name, StringComparison.Ordinal)) ?? 0;
                    debugPanel.SetNpcSurface(new TownNpcDebugSurface
                    {
                        AgentId = property.Name,
                        AuthorityLocationId = agent.Value<string>("current_location_id") ?? "unknown",
                        HouseholdId = householdId ?? "unknown",
                        HouseholdResources = household == null
                            ? "pending"
                            : $"money={household["money"]}; food={household["food_units"]}",
                        Needs = agent["needs"]?.ToString(Formatting.None) ?? "pending",
                        Mood = agent["mood"]?.ToString(Formatting.None) ?? "pending",
                        Relationships = relationshipCount.ToString(),
                        KnownEvents = (agent["known_event_ids"] as JArray)?.Count.ToString() ?? "pending",
                        BehaviorId = "none",
                        ActionPhase = "none"
                    });
                }
            }

            debugPanel?.SetSnapshot(
                world.Value<long?>("game_minute") ?? 0,
                world.Value<string>("model_version") ?? "heuristic",
                lastAppliedStateVersion);
        }

        private void ApplyActionStarted(ActionStartedPayload payload)
        {
            foreach (var agentId in payload.AgentIds)
            {
                var view = TownSceneAssetRegistry.FindNpcView(agentId);
                if (view == null)
                {
                    ReportError($"NPC_VIEW_NOT_FOUND: {agentId}");
                    continue;
                }

                view.BindBridge(this);
                view.BeginAction(payload);
                actionViews[payload.ActionId] = view;
                debugPanel?.SetNpcAction(agentId, payload.BehaviorId, "CREATED");
            }
        }

        private void ApplyActionStartedV030(ActionStartedV030Payload payload)
        {
            if (payload.PlannedDurationMinutes < 0)
            {
                throw new InvalidOperationException("M3 action planned_duration_minutes cannot be negative.");
            }

            BindStructuredPresentation(payload, "CREATED");
        }

        private void ApplyActionPhase(ActionPhaseChangedPayload payload)
        {
            if (actionGroups.TryGetValue(payload.ActionId, out var group))
            {
                foreach (var participant in group.Participants)
                {
                    var participantView = TownSceneAssetRegistry.FindNpcView(participant.AgentId);
                    participantView?.ApplyActionPhase(payload.ActionId, payload.Phase);
                    debugPanel?.SetNpcAction(participant.AgentId, participantView?.CurrentBehaviorId, payload.Phase);
                }

                if (IsTerminalPhase(payload.Phase))
                {
                    ReleaseGroup(payload.ActionId, group);
                }
                return;
            }

            if (!actionViews.TryGetValue(payload.ActionId, out var view))
            {
                view = TownSceneAssetRegistry.FindNpcViewByAction(payload.ActionId);
            }

            view?.ApplyActionPhase(payload.ActionId, payload.Phase);
            if (view != null)
            {
                debugPanel?.SetNpcAction(view.AgentId, view.CurrentBehaviorId, payload.Phase);
            }

            if (payload.Phase == "COMPLETED" || payload.Phase == "FAILED" || payload.Phase == "CANCELLED" || payload.Phase == "INTERRUPTED")
            {
                actionViews.Remove(payload.ActionId);
            }
        }

        private void ApplyActionCancelled(ActionCancelledPayload payload)
        {
            if (actionGroups.TryGetValue(payload.ActionId, out var group))
            {
                foreach (var participant in group.Participants)
                {
                    TownSceneAssetRegistry.FindNpcView(participant.AgentId)
                        ?.CancelAuthoritativeAction(payload.ActionId, payload.Reason);
                    debugPanel?.SetNpcAction(participant.AgentId, null, "CANCELLED");
                }
                ReleaseGroup(payload.ActionId, group);
                return;
            }

            if (actionViews.TryGetValue(payload.ActionId, out var view))
            {
                view.CancelAuthoritativeAction(payload.ActionId, payload.Reason);
            }

            actionViews.Remove(payload.ActionId);
        }

        private static void ApplyAgentDelta(AgentStateDeltaPayload payload)
        {
            TownSceneAssetRegistry.FindNpcView(payload.AgentId)?.ApplyAgentDelta(payload);
        }

        private void ApplyAgentDeltaV030(AgentStateDeltaV030Payload payload)
        {
            var view = TownSceneAssetRegistry.FindNpcView(payload.AgentId);
            view?.ApplyAgentDeltaV030(payload);
            UpdateDebugSurfaceFromView(payload.AgentId, view);
        }

        private void ApplyHouseholdDeltaV030(HouseholdStateDeltaV030Payload payload)
        {
            if (!householdAuthority.TryGetValue(payload.HouseholdId, out var household))
            {
                household = new JObject();
                householdAuthority[payload.HouseholdId] = household;
            }

            foreach (var field in payload.FieldMask)
            {
                household[field] = payload.RawPayload[field].DeepClone();
            }
            debugPanel?.SetHouseholdResources(
                payload.HouseholdId,
                household.Value<long?>("money"),
                household.Value<long?>("food_units"));
        }

        private void BindStructuredPresentation(StructuredActionPresentationV030 action, string phase)
        {
            if (actionGroups.ContainsKey(action.ActionId))
            {
                throw new InvalidOperationException($"M3 presentation action already bound: {action.ActionId}.");
            }

            var participants = action.ValidateAndProjectParticipants();
            var missingAgent = participants.FirstOrDefault(item => TownSceneAssetRegistry.FindNpcView(item.AgentId) == null);
            if (missingAgent != null)
            {
                throw new InvalidOperationException($"NPC_VIEW_NOT_FOUND: {missingAgent.AgentId}");
            }

            var group = new ActionPresentationGroup(action.ActionId, participants);
            if (!group.TryClaimAuthoritativeSlots(out var claimError))
            {
                group.ClearFacing();
                group.ReleaseClaims();
                throw new InvalidOperationException(claimError);
            }
            if (!group.ApplyAuthoritativeFacing(action.BehaviorId, out var facingError))
            {
                group.ClearFacing();
                group.ReleaseClaims();
                throw new InvalidOperationException(facingError);
            }

            actionGroups[action.ActionId] = group;
            foreach (var participant in participants)
            {
                var view = TownSceneAssetRegistry.FindNpcView(participant.AgentId);
                view.BindBridge(this);
                view.BeginActionV030(action, participant, group, phase);
                debugPanel?.SetNpcAction(participant.AgentId, action.BehaviorId, phase);
            }
        }

        private void ResetPresentationProjection()
        {
            foreach (var group in actionGroups.Values)
            {
                group.ClearFacing();
                group.ReleaseClaims();
            }
            actionGroups.Clear();
            actionViews.Clear();
            foreach (var view in TownSceneAssetRegistry.FindNpcViews())
            {
                view.ResetPresentationForSnapshot();
            }
        }

        private void ReleaseGroup(string actionId, ActionPresentationGroup group)
        {
            group.ClearFacing();
            group.ReleaseClaims();
            actionGroups.Remove(actionId);
        }

        private void UpdateDebugSurfaceFromView(string agentId, NpcView view)
        {
            if (view == null)
            {
                return;
            }
            var householdId = agentHouseholds.TryGetValue(agentId, out var value) ? value : "unknown";
            householdAuthority.TryGetValue(householdId, out var household);
            debugPanel?.SetNpcSurface(new TownNpcDebugSurface
            {
                AgentId = agentId,
                AuthorityLocationId = view.CachedAuthorityLocationId ?? "null",
                HouseholdId = householdId,
                HouseholdResources = household == null ? "pending" : $"money={household["money"]}; food={household["food_units"]}",
                Needs = view.CachedNeeds?.ToString(Formatting.None) ?? "null",
                Mood = view.CachedMood?.ToString(Formatting.None) ?? "null",
                KnownEvents = view.CachedKnownEventIds?.Count.ToString() ?? "null",
                Relationships = "snapshot",
                BehaviorId = view.CurrentBehaviorId ?? "none",
                ActionPhase = view.CurrentPhase
            });
        }

        private void RequireM3Message(string messageType)
        {
            if (protocolProfile != TownBridgeProtocolProfile.M3_FULL_V030)
            {
                throw new InvalidOperationException($"{messageType} is Python-to-Unity protocol 0.3.0 only.");
            }
        }

        private string ScanProfileName()
        {
            return protocolProfile == TownBridgeProtocolProfile.M3_FULL_V030 ? "M3_FULL" : "M2_SCOPED";
        }

        private static bool IsTerminalPhase(string phase)
        {
            return phase == "COMPLETED" || phase == "FAILED" || phase == "CANCELLED" || phase == "INTERRUPTED";
        }

        private TownEnvelope CreateOutbound(
            string messageType,
            object payload,
            string envelopeWorldId,
            long stateVersion,
            string correlationId = null)
        {
            return TownEnvelope.Create(
                messageType,
                payload,
                envelopeWorldId,
                stateVersion,
                correlationId,
                ActiveProtocolVersion);
        }

        private void Send(TownEnvelope envelope)
        {
            EnvelopeSending?.Invoke(envelope);
            if (recordedReplaySession)
            {
                return;
            }
            SendAsync(envelope).Forget(this, $"send {envelope.MessageType}");
        }

        private async Task SendAsync(TownEnvelope envelope)
        {
            var activeTransport = transport;
            var sendGeneration = connectionGeneration;
            if (activeTransport == null || activeTransport.State != WebSocketState.Open)
            {
                mainThreadActions.Enqueue(() => ReportError($"SEND_WHILE_DISCONNECTED: {envelope.MessageType}"));
                return;
            }

            await sendGate.WaitAsync().ConfigureAwait(false);
            try
            {
                await activeTransport.SendTextAsync(envelope.ToJson(), connectionCancellation.Token).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is WebSocketException
                                              || exception is OperationCanceledException
                                              || exception is InvalidOperationException)
            {
                if (!shuttingDown)
                {
                    mainThreadActions.Enqueue(() => HandleTransportEnded($"SEND_FAILED: {exception.Message}", sendGeneration));
                }
            }
            finally
            {
                sendGate.Release();
            }
        }

        private async Task CloseTransportAsync()
        {
            var activeTransport = transport;
            if (activeTransport == null)
            {
                return;
            }

            try
            {
                using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(1)))
                {
                    await activeTransport.CloseAsync(timeout.Token).ConfigureAwait(false);
                }
            }
            catch (Exception)
            {
                // Disposal below is authoritative for the local transport lifetime.
            }
            finally
            {
                activeTransport.Dispose();
                if (ReferenceEquals(transport, activeTransport))
                {
                    transport = null;
                }
            }
        }

        private MessageReplayStatus RememberMessage(TownEnvelope envelope)
        {
            var content = JObject.FromObject(envelope);
            if (seenMessageContents.TryGetValue(envelope.MessageId, out var previous))
            {
                return JToken.DeepEquals(previous, content)
                    ? MessageReplayStatus.Duplicate
                    : MessageReplayStatus.Conflict;
            }

            seenMessageContents.Add(envelope.MessageId, content);
            seenMessageOrder.Enqueue(envelope.MessageId);
            while (seenMessageOrder.Count > SeenMessageCapacity)
            {
                seenMessageContents.Remove(seenMessageOrder.Dequeue());
            }

            return MessageReplayStatus.New;
        }

        private void HandleTransportEnded(string reason, int generation)
        {
            if (generation != connectionGeneration
                || shuttingDown
                || ConnectionState == BridgeConnectionState.ProtocolRejected
                || ConnectionState == BridgeConnectionState.Reconnecting)
            {
                return;
            }

            connectionCancellation?.Cancel();
            connectInFlight = false;
            minimumResyncStateVersion = Math.Max(minimumResyncStateVersion, lastAppliedStateVersion);
            reconnectAttempt++;
            var delay = Math.Min(
                reconnectMaximumSeconds,
                reconnectInitialSeconds * Math.Pow(2, Math.Min(8, reconnectAttempt - 1)));
            reconnectAtUnscaledTime = Time.unscaledTime + (float)delay;
            Transition(BridgeConnectionState.Reconnecting);
            ReportError($"{reason}; retry in {delay:0.0}s with full handshake/snapshot");
        }

        private void RejectProtocol(string error)
        {
            connectionCancellation?.Cancel();
            connectInFlight = false;
            Transition(BridgeConnectionState.ProtocolRejected);
            ReportError(error);
        }

        private void Transition(BridgeConnectionState next)
        {
            if (ConnectionState == next)
            {
                return;
            }

            ConnectionState = next;
            debugPanel?.SetConnectionState(next.ToString());
            ConnectionStateChanged?.Invoke(next);
        }

        private void ReportError(string error)
        {
            debugPanel?.RecordError(error);
            BridgeError?.Invoke(error);
            UnityEngine.Debug.LogWarning($"[STWM Bridge] {error}", this);
        }

        private static bool IsHandshakeState(BridgeConnectionState state)
        {
            return state == BridgeConnectionState.AwaitingServerHello
                   || state == BridgeConnectionState.AwaitingRegistryResult
                   || state == BridgeConnectionState.AwaitingWorldSnapshot;
        }

        private readonly struct InboundFrame
        {
            public InboundFrame(int generation, string json)
            {
                Generation = generation;
                Json = json;
            }

            public int Generation { get; }
            public string Json { get; }
        }

        private enum MessageReplayStatus
        {
            New,
            Duplicate,
            Conflict
        }
    }

    internal static class TaskObservationExtensions
    {
        public static async void Forget(this Task task, UnityEngine.Object context, string operation)
        {
            try
            {
                await task;
            }
            catch (Exception exception)
            {
                UnityEngine.Debug.LogException(new Exception($"STWM async operation failed: {operation}", exception), context);
            }
        }
    }
}
