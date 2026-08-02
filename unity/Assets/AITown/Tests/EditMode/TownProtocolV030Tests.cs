using System;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using UnityEngine;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class TownProtocolV030Tests
    {
        [Test]
        public void M3ClientHelloPrefers030ThenM2Compatibility()
        {
            var envelope = TownEnvelope.Create(
                "client_hello",
                new ClientHelloV030Payload(),
                TownProtocol.DefaultWorldId,
                0,
                null,
                TownProtocol.M3Version);
            var payload = envelope.ReadPayload<ClientHelloV030Payload>();

            Assert.That(envelope.ProtocolVersion, Is.EqualTo("0.3.0"));
            CollectionAssert.AreEqual(new[] { "0.3.0", "0.2.0" }, payload.SupportedProtocolVersions);
        }

        [Test]
        public void M3ParserRejects020Fallback()
        {
            var json = "{\"protocol_version\":\"0.2.0\",\"message_id\":\"msg_301\",\"message_type\":\"server_hello\",\"sent_at_utc\":\"2026-08-02T12:00:00Z\",\"world_id\":\"demo_world\",\"state_version\":0,\"correlation_id\":\"msg_300\",\"payload\":{\"server_name\":\"python_town_core\",\"accepted_protocol_version\":\"0.2.0\",\"config_version\":\"v0\",\"schema_version\":\"v0.1\"}}";

            Assert.That(TownEnvelope.TryParse(json, TownProtocol.DefaultWorldId, TownProtocol.M3Version, false, out _, out var error), Is.False);
            Assert.That(error, Does.StartWith("PROTOCOL_VERSION_MISMATCH"));
        }

        [Test]
        public void ExplicitNullDeltaPreservesPresenceAndRejectsMaskMismatch()
        {
            var clear = AgentStateDeltaV030Payload.Parse(JObject.Parse(
                "{\"agent_id\":\"npc_01\",\"current_action_id\":null,\"field_mask\":[\"current_action_id\"]}"));

            Assert.That(clear.Has("current_action_id"), Is.True);
            Assert.That(clear.Value("current_action_id").Type, Is.EqualTo(JTokenType.Null));
            Assert.Throws<InvalidOperationException>(() => AgentStateDeltaV030Payload.Parse(JObject.Parse(
                "{\"agent_id\":\"npc_01\",\"current_action_id\":null,\"field_mask\":[\"needs\"]}")));
        }

        [Test]
        public void ExplicitNullDeltaClearsEveryNullableNpcPresentationCache()
        {
            var root = new GameObject("M3DeltaClearView");
            try
            {
                var view = root.AddComponent<NpcView>();
                view.Configure("npc_01", null, null);
                view.ApplySnapshotAgent(JObject.Parse(
                    "{\"current_location_id\":\"home_a\",\"current_action_id\":\"action_1\",\"needs\":{\"energy\":0.5},\"mood\":{\"valence\":0.1},\"known_event_ids\":[\"event_1\"]}"));
                var clear = AgentStateDeltaV030Payload.Parse(JObject.Parse(
                    "{\"agent_id\":\"npc_01\",\"field_mask\":[\"current_location_id\",\"current_action_id\",\"needs\",\"mood\",\"known_event_ids\"],\"current_location_id\":null,\"current_action_id\":null,\"needs\":null,\"mood\":null,\"known_event_ids\":null}"));
                view.ApplyAgentDeltaV030(clear);

                Assert.That(view.CachedAuthorityLocationId, Is.Null);
                Assert.That(view.CurrentActionId, Is.Null);
                Assert.That(view.CachedNeeds, Is.Null);
                Assert.That(view.CachedMood, Is.Null);
                Assert.That(view.CachedKnownEventIds, Is.Null);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        [Test]
        public void HouseholdDeltaDirectionExistsOnlyOn030PythonToUnitySurface()
        {
            const string payload = "{\"household_id\":\"household_a\",\"money\":125,\"field_mask\":[\"money\"]}";
            var v020 = Envelope("0.2.0", "household_state_delta", payload);
            var v030 = Envelope("0.3.0", "household_state_delta", payload);

            Assert.That(TownEnvelope.TryParse(v020, TownProtocol.DefaultWorldId, TownProtocol.M2Version, false, out _, out _), Is.False);
            Assert.That(TownEnvelope.TryParse(v030, TownProtocol.DefaultWorldId, TownProtocol.M3Version, false, out _, out _), Is.True);
            Assert.That(TownProtocol.OutboundMessageTypes, Does.Not.Contain("household_state_delta"));
        }

        [Test]
        public void HouseholdDeltaCannotClearAuthorityValue()
        {
            Assert.Throws<InvalidOperationException>(() => HouseholdStateDeltaV030Payload.Parse(JObject.Parse(
                "{\"household_id\":\"household_a\",\"money\":null,\"field_mask\":[\"money\"]}")));
            var valid = HouseholdStateDeltaV030Payload.Parse(JObject.Parse(
                "{\"household_id\":\"household_a\",\"money\":125,\"field_mask\":[\"money\"]}"));
            Assert.That(valid.RawPayload.Value<long>("money"), Is.EqualTo(125));
        }

        [Test]
        public void FrozenStructuredActionAndReconnectExamplesValidate()
        {
            var actionEnvelope = JObject.Parse(ReadRepositoryFile("protocol/examples/action-started-v030.json"))
                .ToObject<TownEnvelope>();
            var action = actionEnvelope.ReadPayload<ActionStartedV030Payload>();
            var participants = action.ValidateAndProjectParticipants();
            Assert.That(participants.Count, Is.EqualTo(2));
            Assert.That(participants[0].AgentId, Is.EqualTo("npc_01"));
            Assert.That(participants[0].FacingAgentId, Is.EqualTo("npc_02"));

            var snapshotEnvelope = JObject.Parse(ReadRepositoryFile("protocol/examples/reconnect-world-snapshot-v030.json"))
                .ToObject<TownEnvelope>();
            var snapshot = snapshotEnvelope.ReadPayload<WorldSnapshotV030Payload>();
            Assert.DoesNotThrow(snapshot.Validate);
            Assert.That(snapshot.ActivePresentations.Count, Is.EqualTo(1));
        }

        [Test]
        public void FrozenTopKExampleEnforcesSelectedAcceptedTuple()
        {
            var envelope = JObject.Parse(ReadRepositoryFile("protocol/examples/debug-decision-trace-v030.json"))
                .ToObject<TownEnvelope>();
            var trace = envelope.ReadPayload<DebugDecisionTraceV030Payload>();
            Assert.DoesNotThrow(trace.Validate);
            Assert.That(trace.Candidates.Count, Is.EqualTo(3));

            trace.Candidates[2].ProposalId = "proposal_999";
            Assert.Throws<InvalidOperationException>(trace.Validate);
        }

        [Test]
        public void M3BridgeProfileIsExplicitAndDoesNotChangeM2Default()
        {
            var root = new GameObject("M3ProfileTest");
            try
            {
                var bridge = root.AddComponent<TownBridgeClient>();
                Assert.That(bridge.ProtocolProfile, Is.EqualTo(TownBridgeProtocolProfile.M2_SCOPED_V020));
                bridge.ConfigureM3(TownBridgeClient.DefaultEndpointUrl, TownProtocol.DefaultWorldId, false);
                Assert.That(bridge.ProtocolProfile, Is.EqualTo(TownBridgeProtocolProfile.M3_FULL_V030));
                Assert.That(bridge.ActiveProtocolVersion, Is.EqualTo("0.3.0"));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static string ReadRepositoryFile(string relativePath)
        {
            var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", relativePath));
            return File.ReadAllText(path);
        }

        private static string Envelope(string protocolVersion, string messageType, string payload)
        {
            return $"{{\"protocol_version\":\"{protocolVersion}\",\"message_id\":\"msg_399\",\"message_type\":\"{messageType}\",\"sent_at_utc\":\"2026-08-02T12:00:00Z\",\"world_id\":\"demo_world\",\"state_version\":1,\"correlation_id\":null,\"payload\":{payload}}}";
        }
    }
}
