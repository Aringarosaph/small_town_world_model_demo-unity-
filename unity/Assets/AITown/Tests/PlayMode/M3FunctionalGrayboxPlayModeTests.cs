using System.Collections;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using STWM.AITown.Bridge;
using STWM.AITown.Debugging;
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

            Assert.That(bridge.ProcessInboundJson(ReadRepositoryFile("protocol/examples/debug-decision-trace-v030.json")), Is.True);
            var debugPanel = UnityEngine.Object.FindFirstObjectByType<TownDebugPanel>();
            Assert.That(debugPanel.SelectedDecisionTrace, Is.Not.Null);
            Assert.That(debugPanel.SelectedDecisionTrace.Candidates.Count, Is.EqualTo(3));
            Assert.That(debugPanel.SelectedDecisionTrace.Candidates.Single(item => item.Rank == 1).ResolverResult,
                Is.EqualTo("ACCEPTED"));
        }

        [UnityTest]
        public IEnumerator Stale030DeltaIsRejectedWithoutPresentationMutation()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var bridge = UnityEngine.Object.FindFirstObjectByType<TownBridgeClient>();
            Assert.That(bridge, Is.Not.Null);
            CompleteRecordedHandshake(bridge);

            var view = TownSceneAssetRegistry.FindNpcView("npc_01");
            Assert.That(view.CurrentActionId, Is.EqualTo("action_00000301"));
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(42));
            var staleClear = Envelope(
                "msg_000307",
                "agent_state_delta",
                41,
                "action_00000301",
                new JObject
                {
                    ["agent_id"] = "npc_01",
                    ["current_action_id"] = JValue.CreateNull(),
                    ["field_mask"] = new JArray("current_action_id")
                });

            Assert.That(bridge.ProcessInboundJson(staleClear), Is.False);
            Assert.That(view.CurrentActionId, Is.EqualTo("action_00000301"));
            Assert.That(bridge.LastAppliedStateVersion, Is.EqualTo(42));
            Assert.That(bridge.ActivePresentationGroupCount, Is.EqualTo(1));
        }

        [UnityTest]
        public IEnumerator RecordedJointPresentationCancelAndFailReleaseClaims()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var bridge = UnityEngine.Object.FindFirstObjectByType<TownBridgeClient>();
            Assert.That(bridge, Is.Not.Null);
            CompleteRecordedHandshake(bridge);

            Assert.That(bridge.ActivePresentationGroupCount, Is.EqualTo(1));
            Assert.That(bridge.ProcessInboundJson(Envelope(
                "msg_000308",
                "action_cancelled",
                43,
                "action_00000301",
                new JObject { ["action_id"] = "action_00000301", ["reason"] = "RECORDED_QA_CANCEL" })), Is.True);
            Assert.That(bridge.ActivePresentationGroupCount, Is.Zero);
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").InteractionSlots
                .All(item => item.LocalPresentationClaimId == null), Is.True);

            Assert.That(bridge.ProcessInboundJson(JointActionStartedEnvelope(
                "action_00000302",
                "msg_000309",
                44)), Is.True);
            Assert.That(bridge.ActivePresentationGroupCount, Is.EqualTo(1));
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").InteractionSlots
                .Count(item => item.LocalPresentationClaimId != null), Is.EqualTo(2));
            Assert.That(bridge.ProcessInboundJson(Envelope(
                "msg_000310",
                "action_phase_changed",
                45,
                "action_00000302",
                new JObject { ["action_id"] = "action_00000302", ["phase"] = "FAILED" })), Is.True);
            Assert.That(bridge.ActivePresentationGroupCount, Is.Zero);
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_01").InteractionSlots
                .All(item => item.LocalPresentationClaimId == null), Is.True);
        }

        [UnityTest]
        public IEnumerator Live030PythonBridgeCompletesFullRegistrySnapshotTopKAndReconnectWhenEnabled()
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
            var inboundTypes = new HashSet<string>(StringComparer.Ordinal);
            TownEnvelope acceptedRegistry = null;
            JObject liveDebugTrace = null;
            bridge.ConfigureM3(endpoint, TownProtocol.DefaultWorldId, false);
            bridge.BridgeError += errors.Add;
            bridge.EnvelopeApplied += envelope =>
            {
                inboundTypes.Add(envelope.MessageType);
                if (envelope.MessageType == "debug_decision_trace" && liveDebugTrace == null)
                {
                    liveDebugTrace = JObject.FromObject(envelope);
                }
            };
            bridge.EnvelopeSending += envelope =>
            {
                if (envelope.MessageType == "asset_registry")
                {
                    acceptedRegistry = envelope;
                }
            };
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
            Assert.That(inboundTypes, Does.Contain("world_snapshot"));
            Assert.That(acceptedRegistry, Is.Not.Null);
            Assert.That(acceptedRegistry.ProtocolVersion, Is.EqualTo(TownProtocol.M3Version));
            Assert.That(acceptedRegistry.Payload["locations"].Count(), Is.EqualTo(8));
            Assert.That(acceptedRegistry.Payload["npc_views"].Count(), Is.EqualTo(10));

            var authorityDeadline = Time.realtimeSinceStartup + 5f;
            while ((!inboundTypes.Contains("action_started") || !inboundTypes.Contains("debug_decision_trace"))
                   && Time.realtimeSinceStartup < authorityDeadline)
            {
                yield return null;
            }

            Assert.That(inboundTypes, Does.Contain("action_started"), "Production server emitted no structured action_started.");
            Assert.That(inboundTypes, Does.Contain("debug_decision_trace"), "Production server emitted no authoritative Top-K trace.");
            Assert.That(errors, Is.Empty, "Production 0.3 messages must pass strict Unity decoding: " + string.Join(" | ", errors));
            var debugPanel = UnityEngine.Object.FindFirstObjectByType<TownDebugPanel>();
            Assert.That(debugPanel.SelectedDecisionTrace, Is.Not.Null);
            Assert.That(debugPanel.SelectedDecisionTrace.Candidates, Is.Not.Empty);
            WriteLiveArtifactsWhenRequested(acceptedRegistry, liveDebugTrace);

            var firstStateVersion = bridge.LastAppliedStateVersion;
            bridge.Disconnect();
            yield return null;
            UnityEngine.Object.Destroy(bridge.gameObject);
            yield return null;

            var reconnectObject = new GameObject("M3LiveReconnectBridge");
            var reconnect = reconnectObject.AddComponent<TownBridgeClient>();
            var reconnectErrors = new List<string>();
            var reconnectInboundTypes = new HashSet<string>(StringComparer.Ordinal);
            reconnect.ConfigureM3(endpoint, TownProtocol.DefaultWorldId, false);
            reconnect.BridgeError += reconnectErrors.Add;
            reconnect.EnvelopeApplied += envelope => reconnectInboundTypes.Add(envelope.MessageType);
            reconnect.Connect();

            deadline = Time.realtimeSinceStartup + 20f;
            while (reconnect.ConnectionState != BridgeConnectionState.Ready
                   && reconnect.ConnectionState != BridgeConnectionState.ProtocolRejected
                   && reconnect.ConnectionState != BridgeConnectionState.DiagnosticOnly
                   && Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            Assert.That(reconnect.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready), string.Join(" | ", reconnectErrors));
            Assert.That(reconnectInboundTypes, Does.Contain("world_snapshot"));
            Assert.That(reconnect.LastAppliedStateVersion, Is.GreaterThanOrEqualTo(firstStateVersion));
            Assert.That(reconnectErrors, Is.Empty, "Reconnect messages must pass strict Unity decoding: " + string.Join(" | ", reconnectErrors));
            reconnect.Disconnect();
            yield return null;
        }

        private static void WriteLiveArtifactsWhenRequested(TownEnvelope registry, JObject debugTraceEnvelope)
        {
            var registryPath = Environment.GetEnvironmentVariable("STWM_M3_LIVE_REGISTRY_OUTPUT");
            if (!string.IsNullOrWhiteSpace(registryPath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(registryPath)));
                File.WriteAllText(registryPath, registry.ToJson());
            }

            var tracePath = Environment.GetEnvironmentVariable("STWM_M3_LIVE_DEBUG_TRACE_OUTPUT");
            if (!string.IsNullOrWhiteSpace(tracePath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(tracePath)));
                var record = new JObject
                {
                    ["schema"] = "stwm.unity.m3-debug-trace/v1",
                    ["evidence_source"] = "live_python_bridge",
                    ["envelope"] = debugTraceEnvelope
                };
                File.WriteAllText(tracePath, record.ToString(Newtonsoft.Json.Formatting.None) + Environment.NewLine);
            }
        }

        private static void CompleteRecordedHandshake(TownBridgeClient bridge)
        {
            bridge.BeginRecordedReplaySession("msg_000301", "msg_000399");
            Assert.That(bridge.ProcessInboundJson(ReadRepositoryFile("protocol/examples/server-hello-v030.json")), Is.True);
            Assert.That(bridge.ProcessInboundJson(Envelope(
                "msg_000398",
                "asset_registry_result",
                0,
                "msg_000399",
                new JObject { ["accepted"] = true, ["issues"] = new JArray() })), Is.True);
            Assert.That(bridge.ProcessInboundJson(
                ReadRepositoryFile("protocol/examples/reconnect-world-snapshot-v030.json")), Is.True);
            Assert.That(bridge.ConnectionState, Is.EqualTo(BridgeConnectionState.Ready));
        }

        private static string JointActionStartedEnvelope(string actionId, string messageId, long stateVersion)
        {
            var envelope = JObject.Parse(ReadRepositoryFile("protocol/examples/action-started-v030.json"));
            envelope["message_id"] = messageId;
            envelope["state_version"] = stateVersion;
            envelope["correlation_id"] = actionId;
            envelope["payload"]["action_id"] = actionId;
            return envelope.ToString(Newtonsoft.Json.Formatting.None);
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
