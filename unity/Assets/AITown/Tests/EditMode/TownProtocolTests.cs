using NUnit.Framework;
using STWM.AITown.Bridge;
using UnityEngine;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class TownProtocolTests
    {
        [Test]
        public void ProductionEndpointMatchesPythonServerDefault()
        {
            Assert.That(TownBridgeClient.DefaultEndpointUrl, Is.EqualTo("ws://127.0.0.1:8765/town"));
        }

        [TestCase(0f)]
        [TestCase(1f)]
        [TestCase(2f)]
        [TestCase(4f)]
        public void UnityLiveTimeScaleAllowlistAcceptsOnlyFrozenValues(float value)
        {
            Assert.That(TownBridgeClient.IsAllowedTimeScale(value), Is.True);
        }

        [TestCase(-1f)]
        [TestCase(0.5f)]
        [TestCase(3f)]
        [TestCase(8f)]
        public void UnityLiveTimeScaleAllowlistRejectsOtherValues(float value)
        {
            Assert.That(TownBridgeClient.IsAllowedTimeScale(value), Is.False);
        }

        [Test]
        public void PublicClockControlsRejectBeforeBridgeReady()
        {
            var root = new GameObject("BridgeControlBoundaryTest");
            var bridge = root.AddComponent<TownBridgeClient>();
            try
            {
                Assert.Throws<System.InvalidOperationException>(() => bridge.RequestTimeScale(1f));
                Assert.Throws<System.InvalidOperationException>(() => bridge.RequestPause(true));
                Assert.Throws<System.ArgumentOutOfRangeException>(() => bridge.RequestTimeScale(3f));
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }

        [Test]
        public void ClientHelloUsesFrozenEnvelopeAndPayload()
        {
            var envelope = TownEnvelope.Create(
                "client_hello",
                new ClientHelloPayload(),
                TownProtocol.DefaultWorldId,
                0);
            var payload = envelope.ReadPayload<ClientHelloPayload>();

            Assert.That(envelope.ProtocolVersion, Is.EqualTo(TownProtocol.Version));
            Assert.That(envelope.MessageType, Is.EqualTo("client_hello"));
            Assert.That(envelope.MessageId, Does.Match("^msg_[0-9]+$"));
            Assert.That(envelope.CorrelationId, Is.Null);
            Assert.That(payload.UnityEditorVersion, Is.EqualTo("6000.4.2f1"));
            CollectionAssert.AreEqual(
                new[] { "0.2.0", "0.1.0" },
                payload.SupportedProtocolVersions);
        }

        [Test]
        public void ParserRejectsIncompatibleProtocolVersion()
        {
            var json = Envelope(
                "99.0.0",
                "server_hello",
                0,
                "msg_101",
                "{\"server_name\":\"python_town_core\",\"accepted_protocol_version\":\"0.2.0\",\"config_version\":\"v0\",\"schema_version\":\"v0.1\"}");

            Assert.That(
                TownEnvelope.TryParse(json, TownProtocol.DefaultWorldId, out _, out var error),
                Is.False);
            Assert.That(error, Does.StartWith("PROTOCOL_VERSION_MISMATCH"));
        }

        [Test]
        public void ParserRejectsUnknownInboundMessageType()
        {
            var json = Envelope(TownProtocol.Version, "not_frozen", 0, "msg_102", "{}");

            Assert.That(
                TownEnvelope.TryParse(json, TownProtocol.DefaultWorldId, out _, out var error),
                Is.False);
            Assert.That(error, Does.StartWith("UNKNOWN_MESSAGE_TYPE"));
        }

        [Test]
        public void MovementCancelledUsesDistinctNonAuthoritativeReport()
        {
            var envelope = TownEnvelope.Create(
                "movement_cancelled",
                new MovementCancelledPayload
                {
                    ActionId = "action_7",
                    AgentId = "npc_01",
                    Reason = MovementCancellationReason.NAVIGATION_STOPPED.ToString()
                },
                TownProtocol.DefaultWorldId,
                42,
                "action_7");

            var payload = envelope.ReadPayload<MovementCancelledPayload>();
            Assert.That(envelope.ProtocolVersion, Is.EqualTo("0.2.0"));
            Assert.That(envelope.MessageType, Is.EqualTo("movement_cancelled"));
            Assert.That(envelope.CorrelationId, Is.EqualTo("action_7"));
            Assert.That(payload.Reason, Is.EqualTo("NAVIGATION_STOPPED"));
        }

        [Test]
        public void ActionMessagesRequireExactCorrelation()
        {
            Assert.That(
                () => TownEnvelope.Create(
                    "movement_failed",
                    new MovementFailedPayload
                    {
                        ActionId = "action_7",
                        AgentId = "npc_01",
                        Reason = MovementFailureReason.NO_PATH.ToString()
                    },
                    TownProtocol.DefaultWorldId,
                    42,
                    "action_8"),
                Throws.ArgumentException.With.Message.Contains("ACTION_CORRELATION_MISMATCH"));
        }

        internal static string Envelope(
            string protocolVersion,
            string messageType,
            long stateVersion,
            string messageId,
            string payloadJson,
            string correlationJson = "null")
        {
            return $"{{\"protocol_version\":\"{protocolVersion}\",\"message_id\":\"{messageId}\","
                   + $"\"message_type\":\"{messageType}\",\"sent_at_utc\":\"2026-08-02T00:00:00Z\","
                   + $"\"world_id\":\"{TownProtocol.DefaultWorldId}\",\"state_version\":{stateVersion},"
                   + $"\"correlation_id\":{correlationJson},\"payload\":{payloadJson}}}";
        }
    }
}
