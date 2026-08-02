using System.Collections;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace STWM.AITown.Tests.PlayMode
{
    public sealed class M3FunctionalGrayboxPlayModeTests
    {
        [UnityTearDown]
        public IEnumerator TearDown()
        {
            var m3Scene = SceneManager.GetSceneByName("M3FunctionalGraybox");
            if (m3Scene.IsValid() && m3Scene.isLoaded)
            {
                var cleanup = SceneManager.CreateScene("M3PlayModeCleanup");
                SceneManager.SetActiveScene(cleanup);
                yield return SceneManager.UnloadSceneAsync(m3Scene);
            }
        }

        [UnityTest]
        public IEnumerator FullTownFixtureLoadsWithStrictSemanticAndRouteCoverage()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);

            var scan = TownSceneAssetRegistry.ScanFullV0(true);
            Assert.That(scan.HasErrors, Is.False, string.Join("\n", scan.Issues.Select(item => $"{item.Code}/{item.EntityId}")));
            Assert.That(scan.Payload.Locations.Count, Is.EqualTo(8));
            Assert.That(scan.Payload.NpcViews.Count, Is.EqualTo(10));
            Assert.That(scan.Payload.Objects.Select(item => item.ObjectType).Distinct().Count(), Is.EqualTo(15));
            Assert.That(scan.Payload.Objects.Sum(item => item.InteractionSlots.Count), Is.EqualTo(105));
        }

        [UnityTest]
        public IEnumerator ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var group = new ActionPresentationGroup("action_900", new[]
            {
                new ActionPresentationParticipant
                {
                    AgentId = "npc_02",
                    Role = ActionPresentationRole.TARGET,
                    FacingAgentId = "npc_01",
                    ObjectSlotBindings = new[]
                    {
                        new PresentationObjectSlotBinding { ObjectId = "park_conversation_01", SlotIndex = 1 }
                    }
                },
                new ActionPresentationParticipant
                {
                    AgentId = "npc_01",
                    Role = ActionPresentationRole.ACTOR,
                    FacingAgentId = "npc_02",
                    ObjectSlotBindings = new[]
                    {
                        new PresentationObjectSlotBinding { ObjectId = "park_conversation_01", SlotIndex = 0 }
                    }
                }
            });

            Assert.That(group.TryClaimAuthoritativeSlots(out var claimError), Is.True, claimError);
            Assert.That(group.ApplyAuthoritativeFacing("chat", out var facingError), Is.True, facingError);
            Assert.That(group.Claims.Select(item => item.SlotIndex), Is.EqualTo(new[] { 0, 1 }));
            Assert.That(TownSceneAssetRegistry.FindNpcView("npc_01").SocialFacingController.FacingTarget,
                Is.EqualTo(TownSceneAssetRegistry.FindNpcView("npc_02").transform));

            group.ClearFacing();
            group.ReleaseClaims();
            yield return null;
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").InteractionSlots
                .All(item => item.LocalPresentationClaimId == null), Is.True);
        }

        [UnityTest]
        public IEnumerator Recorded030HandshakeRebindsSnapshotThenClearsAndReleasesJointPresentation()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var bridge = UnityEngine.Object.FindFirstObjectByType<TownBridgeClient>();
            Assert.That(bridge, Is.Not.Null);
            Assert.That(bridge.ProtocolProfile, Is.EqualTo(TownBridgeProtocolProfile.M3_FULL_V030));

            bridge.BeginRecordedReplaySession("msg_000301", "msg_000399");
            Assert.That(bridge.ProcessInboundJson(ReadRepositoryFile("protocol/examples/server-hello-v030.json")), Is.True);
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.AwaitingRegistryResult));

            Assert.That(bridge.ProcessInboundJson(Envelope(
                "msg_000398",
                "asset_registry_result",
                0,
                "msg_000399",
                new JObject { ["accepted"] = true, ["issues"] = new JArray() })), Is.True);
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.AwaitingWorldSnapshot));

            Assert.That(bridge.ProcessInboundJson(ReadRepositoryFile("protocol/examples/reconnect-world-snapshot-v030.json")), Is.True);
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready));
            Assert.That(bridge.ActivePresentationGroupCount, Is.EqualTo(1));
            Assert.That(TownSceneAssetRegistry.FindNpcView("npc_01").CurrentActionId, Is.EqualTo("action_00000301"));
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").FindSlot(0).LocalPresentationClaimId, Does.Contain("npc_01"));

            Assert.That(bridge.ProcessInboundJson(ReadRepositoryFile("protocol/examples/agent-state-delta-clear-v030.json")), Is.True);
            Assert.That(TownSceneAssetRegistry.FindNpcView("npc_01").CurrentActionId, Is.Null);
            Assert.That(bridge.ProcessInboundJson(Envelope(
                "msg_000306",
                "action_phase_changed",
                44,
                "action_00000301",
                new JObject { ["action_id"] = "action_00000301", ["phase"] = "COMPLETED" })), Is.True);
            Assert.That(bridge.ActivePresentationGroupCount, Is.Zero);
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").InteractionSlots
                .All(item => item.LocalPresentationClaimId == null), Is.True);
        }

        [UnityTest]
        public IEnumerator Live030PythonBridgeCompletesFullRegistrySnapshotAndReadyWhenEnabled()
        {
            if (!string.Equals(Environment.GetEnvironmentVariable("STWM_M3_LIVE_BRIDGE"), "1", StringComparison.Ordinal))
            {
                Assert.Ignore("Set STWM_M3_LIVE_BRIDGE=1 after starting the production M3 Python BridgeWebSocketServer.");
            }

            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var bridge = UnityEngine.Object.FindFirstObjectByType<TownBridgeClient>();
            var endpoint = Environment.GetEnvironmentVariable("STWM_M3_LIVE_BRIDGE_URL")
                           ?? TownBridgeClient.DefaultEndpointUrl;
            var errors = new List<string>();
            bridge.ConfigureM3(endpoint, TownProtocol.DefaultWorldId, false);
            bridge.BridgeError += errors.Add;
            bridge.Connect();

            var deadline = Time.realtimeSinceStartup + 20f;
            while (bridge.ConnectionState != BridgeConnectionState.Ready
                   && bridge.ConnectionState != BridgeConnectionState.ProtocolRejected
                   && bridge.ConnectionState != BridgeConnectionState.DiagnosticOnly
                   && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready), string.Join(" | ", errors));
            Assert.That(bridge.ActiveProtocolVersion, Is.EqualTo("0.3.0"));
            Assert.That(bridge.EndpointUrl, Does.EndWith("/town"));
            bridge.Disconnect();
            yield return null;
        }

        private static string ReadRepositoryFile(string relativePath)
        {
            var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", relativePath));
            return File.ReadAllText(path);
        }

        private static string Envelope(string messageId, string messageType, long stateVersion, string correlationId, JObject payload)
        {
            return new JObject
            {
                ["protocol_version"] = TownProtocol.M3Version,
                ["message_id"] = messageId,
                ["message_type"] = messageType,
                ["sent_at_utc"] = "2026-08-02T12:00:00Z",
                ["world_id"] = TownProtocol.DefaultWorldId,
                ["state_version"] = stateVersion,
                ["correlation_id"] = correlationId,
                ["payload"] = payload
            }.ToString(Newtonsoft.Json.Formatting.None);
        }
    }
}
