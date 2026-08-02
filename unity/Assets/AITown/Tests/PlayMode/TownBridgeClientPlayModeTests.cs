using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine;
using UnityEngine.TestTools;

namespace STWM.AITown.Tests.PlayMode
{
    public sealed class TownBridgeClientPlayModeTests
    {
        private readonly List<GameObject> roots = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var root in roots)
            {
                if (root != null)
                {
                    UnityEngine.Object.DestroyImmediate(root);
                }
            }

            roots.Clear();
        }

        [UnityTest]
        public IEnumerator MockServerCompletesHandshakeAndReportsCancellation()
        {
            CreateValidM2Inventory();
            var mock = new MockTownSocketTransport();
            var bridge = CreateBridge(() => mock);
            yield return null;

            bridge.Connect();
            yield return WaitForSend(mock, "client_hello");
            var clientHelloMessageId = ExtractString(mock.LastSent("client_hello"), "message_id");
            mock.EnqueueInbound(ServerHello("msg_101", 4, clientHelloMessageId));
            yield return WaitForSend(mock, "asset_registry");
            var registryJson = mock.LastSent("asset_registry");
            var registryMessageId = ExtractString(registryJson, "message_id");
            Assert.That(ExtractString(registryJson, "correlation_id"), Is.EqualTo(clientHelloMessageId));
            mock.EnqueueInbound(RegistryResult("msg_102", 4, registryMessageId));
            mock.EnqueueInbound(WorldSnapshot("msg_103", 5));
            yield return WaitForSend(mock, "client_ready");

            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready));
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(5));
            CollectionAssert.IsSubsetOf(
                new[] { "client_hello", "asset_registry", "client_ready" },
                mock.SentMessageTypes);

            var errors = new List<string>();
            bridge.BridgeError += errors.Add;
            var clock = Clock("msg_150", 6, 480);
            Assert.That(bridge.ProcessInboundJson(clock), Is.True);
            Assert.That(bridge.ProcessInboundJson(clock), Is.False);
            Assert.That(bridge.ProcessInboundJson(Clock("msg_150", 6, 481)), Is.False);
            Assert.That(errors, Has.Some.Contains("MESSAGE_ID_CONTENT_CONFLICT"));

            bridge.RequestTimeScale(4f);
            yield return WaitForSend(mock, "set_time_scale_request");
            StringAssert.Contains("\"requested_time_scale\":4.0", mock.LastSent("set_time_scale_request"));
            Assert.Throws<ArgumentOutOfRangeException>(() => bridge.RequestTimeScale(3f));
            bridge.RequestPause(true);
            yield return WaitForSend(mock, "pause_request");
            StringAssert.Contains("\"paused\":true", mock.LastSent("pause_request"));

            bridge.ReportMovementCancelled(
                "action_7",
                "npc_01",
                MovementCancellationReason.NAVIGATION_STOPPED);
            yield return WaitForSend(mock, "movement_cancelled");

            var cancellation = mock.LastSent("movement_cancelled");
            StringAssert.Contains("\"protocol_version\":\"0.2.0\"", cancellation);
            StringAssert.Contains("\"correlation_id\":\"action_7\"", cancellation);
            StringAssert.Contains("\"reason\":\"NAVIGATION_STOPPED\"", cancellation);
        }

        [UnityTest]
        public IEnumerator ReconnectRequiresFreshHandshakeAndRejectsObsoleteGeneration()
        {
            CreateValidM2Inventory();
            var first = new MockTownSocketTransport();
            var second = new MockTownSocketTransport();
            var transports = new Queue<ITownSocketTransport>(new ITownSocketTransport[] { first, second });
            var bridge = CreateBridge(() => transports.Dequeue());
            yield return null;

            bridge.Connect();
            yield return CompleteHandshake(bridge, first, 200, 10);
            var oldGeneration = bridge.ConnectionGeneration;
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready));

            first.CompleteRemoteClose();
            yield return new WaitUntil(() => bridge.ConnectionState == BridgeConnectionState.Reconnecting);
            yield return new WaitUntil(() => bridge.ConnectionGeneration > oldGeneration);
            yield return WaitForSend(second, "client_hello");
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.AwaitingServerHello));

            var reconnectClientHelloId = ExtractString(second.LastSent("client_hello"), "message_id");
            second.EnqueueInbound(ServerHello("msg_301", 10, reconnectClientHelloId));
            yield return WaitForSend(second, "asset_registry");
            var secondRegistryMessageId = ExtractString(second.LastSent("asset_registry"), "message_id");
            second.EnqueueInbound(RegistryResult("msg_302", 10, secondRegistryMessageId));
            second.EnqueueInbound(WorldSnapshot("msg_303", 9));
            yield return null;
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.AwaitingWorldSnapshot));
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(10));

            second.EnqueueInbound(WorldSnapshot("msg_304", 11));
            yield return WaitForSend(second, "client_ready");
            yield return new WaitUntil(() => bridge.ConnectionState == BridgeConnectionState.Ready);
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready));
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(11));

            bridge.InjectInboundForTests(
                oldGeneration,
                Clock("msg_399", 99, 999));
            yield return null;
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(11));
        }

        [UnityTest]
        public IEnumerator RejectsServerHelloWhoseEnvelopeDoesNotEqualSelectedVersion()
        {
            CreateValidM2Inventory();
            var mock = new MockTownSocketTransport();
            var bridge = CreateBridge(() => mock);
            yield return null;

            bridge.Connect();
            yield return WaitForSend(mock, "client_hello");
            var clientHelloMessageId = ExtractString(mock.LastSent("client_hello"), "message_id");
            mock.EnqueueInbound(ServerHello("msg_401", 0, clientHelloMessageId, TownProtocol.LegacyBootstrapVersion));
            var deadline = Time.realtimeSinceStartup + 1f;
            while (bridge.ConnectionState == BridgeConnectionState.AwaitingServerHello
                   && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.ProtocolRejected));
            Assert.That(mock.SentMessageTypes, Does.Not.Contain("asset_registry"));
        }

        [UnityTest]
        public IEnumerator LivePythonBridgeCompletesProductionHandshakeWhenEnabled()
        {
            if (!string.Equals(
                    Environment.GetEnvironmentVariable("STWM_M2_LIVE_BRIDGE"),
                    "1",
                    StringComparison.Ordinal))
            {
                Assert.Ignore("Set STWM_M2_LIVE_BRIDGE=1 after starting the production Python BridgeWebSocketServer.");
            }

            var endpoint = Environment.GetEnvironmentVariable("STWM_M2_LIVE_BRIDGE_URL")
                           ?? TownBridgeClient.DefaultEndpointUrl;
            Assert.That(Uri.TryCreate(endpoint, UriKind.Absolute, out var uri), Is.True);
            Assert.That(uri.Scheme, Is.EqualTo("ws"));
            Assert.That(
                uri.Host,
                Is.EqualTo("127.0.0.1").Or.EqualTo("localhost").Or.EqualTo("::1"));
            Assert.That(uri.AbsolutePath, Is.EqualTo("/town"));

            CreateValidM2Inventory();
            var root = Track(new GameObject("TownBridgeLiveSmoke"));
            var bridge = root.AddComponent<TownBridgeClient>();
            bridge.Configure(endpoint, TownProtocol.DefaultWorldId, false);
            var errors = new List<string>();
            bridge.BridgeError += errors.Add;
            yield return null;

            bridge.Connect();
            var deadline = Time.realtimeSinceStartup + 15f;
            while (bridge.ConnectionState != BridgeConnectionState.Ready
                   && bridge.ConnectionState != BridgeConnectionState.ProtocolRejected
                   && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready), string.Join(" | ", errors));
            Assert.That(bridge.EndpointUrl, Does.EndWith("/town"));
            bridge.Disconnect();
            yield return null;
        }

        private IEnumerator CompleteHandshake(
            TownBridgeClient bridge,
            MockTownSocketTransport mock,
            int messageBase,
            long snapshotVersion,
            bool helloAlreadySent = false)
        {
            if (!helloAlreadySent)
            {
                yield return WaitForSend(mock, "client_hello");
            }

            var clientHelloMessageId = ExtractString(mock.LastSent("client_hello"), "message_id");
            mock.EnqueueInbound(ServerHello(
                $"msg_{messageBase + 1}",
                snapshotVersion - 1,
                clientHelloMessageId));
            yield return WaitForSend(mock, "asset_registry");
            var registryMessageId = ExtractString(mock.LastSent("asset_registry"), "message_id");
            mock.EnqueueInbound(RegistryResult($"msg_{messageBase + 2}", snapshotVersion - 1, registryMessageId));
            mock.EnqueueInbound(WorldSnapshot($"msg_{messageBase + 3}", snapshotVersion));
            yield return WaitForSend(mock, "client_ready");
            yield return new WaitUntil(() => bridge.ConnectionState == BridgeConnectionState.Ready);
        }

        private TownBridgeClient CreateBridge(Func<ITownSocketTransport> transportFactory)
        {
            var root = Track(new GameObject("TownBridgeTest"));
            var bridge = root.AddComponent<TownBridgeClient>();
            bridge.Configure(TownBridgeClient.DefaultEndpointUrl, TownProtocol.DefaultWorldId, false);
            Assert.That(bridge.EndpointUrl, Is.EqualTo("ws://127.0.0.1:8765/town"));
            bridge.SetTransportFactoryForTests(transportFactory);
            return bridge;
        }

        private void CreateValidM2Inventory()
        {
            CreateLocation("home_a", SemanticLocationType.HOME);
            CreateLocation("cafe_bar", SemanticLocationType.CAFE_BAR);
            CreateObject("home_a_bed_01", SemanticObjectType.BED, "home_a", new[] { SemanticCapability.SLEEP }, AnimationSemantic.SLEEP);
            CreateObject("home_a_fridge_01", SemanticObjectType.FRIDGE, "home_a", new[] { SemanticCapability.FOOD_SOURCE_HOME }, AnimationSemantic.IDLE);
            CreateObject("home_a_dining_seat_01", SemanticObjectType.DINING_SEAT, "home_a", new[] { SemanticCapability.SIT, SemanticCapability.EAT }, AnimationSemantic.EAT);
            CreateObject("cafe_bar_workstation_01", SemanticObjectType.WORKSTATION, "cafe_bar", new[] { SemanticCapability.WORK, SemanticCapability.CAFE_MORNING }, AnimationSemantic.WORK_STANDING);

            var npc = Track(new GameObject("npc_01"));
            var navigation = npc.AddComponent<NpcNavigationController>();
            var animation = npc.AddComponent<NpcAnimationDriver>();
            animation.ConfigureFallbackMappings(
                AnimationSemantic.IDLE,
                AnimationSemantic.WALK,
                AnimationSemantic.SLEEP,
                AnimationSemantic.EAT,
                AnimationSemantic.WORK_STANDING);
            npc.AddComponent<NpcView>().Configure("npc_01", navigation, animation);
        }

        private void CreateLocation(string id, SemanticLocationType type)
        {
            var root = Track(new GameObject(id));
            var entrance = new GameObject("Entrance");
            entrance.transform.SetParent(root.transform);
            root.AddComponent<SemanticLocation>().Configure(id, type, id, entrance.transform);
        }

        private void CreateObject(
            string id,
            SemanticObjectType type,
            string locationId,
            SemanticCapability[] capabilities,
            AnimationSemantic semantic)
        {
            var root = Track(new GameObject(id));
            var slot = root.AddComponent<InteractionSlot>();
            slot.Configure(0, root.transform, null, semantic);
            root.AddComponent<SemanticObject>().Configure(id, type, locationId, true, capabilities, slot);
        }

        private GameObject Track(GameObject value)
        {
            roots.Add(value);
            return value;
        }

        private static IEnumerator WaitForSend(MockTownSocketTransport mock, string messageType)
        {
            yield return new WaitUntil(() => mock.SentMessageTypes.Contains(messageType));
        }

        private static string ServerHello(
            string messageId,
            long stateVersion,
            string clientHelloMessageId,
            string envelopeProtocolVersion = TownProtocol.Version)
        {
            return Envelope(
                messageId,
                "server_hello",
                stateVersion,
                $"\"{clientHelloMessageId}\"",
                "{\"server_name\":\"python_town_core\",\"accepted_protocol_version\":\"0.2.0\",\"config_version\":\"v0\",\"schema_version\":\"v0.1\"}",
                envelopeProtocolVersion);
        }

        private static string RegistryResult(string messageId, long stateVersion, string registryMessageId)
        {
            return Envelope(
                messageId,
                "asset_registry_result",
                stateVersion,
                $"\"{registryMessageId}\"",
                "{\"accepted\":true,\"issues\":[]}");
        }

        private static string WorldSnapshot(string messageId, long stateVersion)
        {
            var payload = $"{{\"world\":{{\"world_id\":\"{TownProtocol.DefaultWorldId}\",\"state_version\":{stateVersion},"
                          + "\"game_minute\":420,\"model_version\":\"heuristic\",\"agents\":{\"npc_01\":{"
                          + "\"current_location_id\":\"home_a\",\"current_action_id\":null,\"needs\":{},\"enabled\":true}}}}";
            return Envelope(messageId, "world_snapshot", stateVersion, "null", payload);
        }

        private static string Clock(string messageId, long stateVersion, long minute)
        {
            return Envelope(
                messageId,
                "simulation_clock_updated",
                stateVersion,
                "null",
                $"{{\"game_minute\":{minute},\"time_scale\":1.0,\"paused\":false}}");
        }

        private static string Envelope(
            string messageId,
            string messageType,
            long stateVersion,
            string correlationJson,
            string payloadJson,
            string protocolVersion = TownProtocol.Version)
        {
            return $"{{\"protocol_version\":\"{protocolVersion}\",\"message_id\":\"{messageId}\","
                   + $"\"message_type\":\"{messageType}\",\"sent_at_utc\":\"2026-08-02T00:00:00Z\","
                   + $"\"world_id\":\"{TownProtocol.DefaultWorldId}\",\"state_version\":{stateVersion},"
                   + $"\"correlation_id\":{correlationJson},\"payload\":{payloadJson}}}";
        }

        private static string ExtractString(string json, string property)
        {
            var prefix = $"\"{property}\":\"";
            var start = json.IndexOf(prefix, StringComparison.Ordinal);
            Assert.That(start, Is.GreaterThanOrEqualTo(0), json);
            start += prefix.Length;
            var end = json.IndexOf('"', start);
            Assert.That(end, Is.GreaterThan(start), json);
            return json.Substring(start, end - start);
        }

        private sealed class MockTownSocketTransport : ITownSocketTransport
        {
            private readonly object gate = new object();
            private readonly Queue<string> inbound = new Queue<string>();
            private readonly List<string> sent = new List<string>();
            private readonly SemaphoreSlim inboundSignal = new SemaphoreSlim(0);
            private WebSocketState state = WebSocketState.None;

            public WebSocketState State => state;

            public IReadOnlyList<string> SentMessageTypes
            {
                get
                {
                    lock (gate)
                    {
                        return sent.Select(item => ExtractString(item, "message_type")).ToArray();
                    }
                }
            }

            public Task ConnectAsync(Uri endpoint, TimeSpan keepAliveInterval, CancellationToken cancellationToken)
            {
                state = WebSocketState.Open;
                return Task.CompletedTask;
            }

            public Task SendTextAsync(string text, CancellationToken cancellationToken)
            {
                lock (gate)
                {
                    sent.Add(text);
                }

                return Task.CompletedTask;
            }

            public async Task<string> ReceiveTextAsync(CancellationToken cancellationToken)
            {
                await inboundSignal.WaitAsync(cancellationToken);
                lock (gate)
                {
                    return inbound.Dequeue();
                }
            }

            public Task CloseAsync(CancellationToken cancellationToken)
            {
                state = WebSocketState.Closed;
                return Task.CompletedTask;
            }

            public void EnqueueInbound(string message)
            {
                lock (gate)
                {
                    inbound.Enqueue(message);
                }

                inboundSignal.Release();
            }

            public void CompleteRemoteClose()
            {
                state = WebSocketState.CloseReceived;
                EnqueueInbound(null);
            }

            public string LastSent(string messageType)
            {
                lock (gate)
                {
                    return sent.Last(item => ExtractString(item, "message_type") == messageType);
                }
            }

            public void Dispose()
            {
                state = WebSocketState.Closed;
            }
        }
    }
}
