using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using STWM.AITown.Editor;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class M2AcceptanceEvidenceExporterTests
    {
        [Test]
        public void ExportsExternalRedactedQaV1Bundle()
        {
            var root = Path.Combine(Path.GetTempPath(), $"stwm-m2-evidence-test-{Guid.NewGuid():N}");
            var input = Path.Combine(root, "input");
            var output = Path.Combine(root, "output");
            Directory.CreateDirectory(input);
            var edit = Path.Combine(input, "edit.xml");
            var play = Path.Combine(input, "play.xml");
            var authorityEvidence = Path.Combine(input, "m2-authority-evidence.json");
            var authorityTranscript = Path.Combine(input, "bridge-authority-transcript.jsonl");
            File.WriteAllText(edit, PassingXml(16, false));
            File.WriteAllText(play, PassingXml(2, true));
            var transcript = AuthorityTranscript();
            File.WriteAllText(authorityTranscript, transcript, new UTF8Encoding(false));
            File.WriteAllText(
                authorityEvidence,
                AuthorityEvidence(ComputeSha256(authorityTranscript)),
                new UTF8Encoding(false));

            try
            {
                M2AcceptanceEvidenceExporter.ExportTo(
                    output,
                    new string('a', 40),
                    edit,
                    play,
                    authorityEvidence,
                    authorityTranscript);

                var evidence = File.ReadAllText(Path.Combine(output, "m2-evidence.json"));
                StringAssert.Contains($"\"schema\": \"{M2AcceptanceEvidenceExporter.EvidenceSchema}\"", evidence);
                Assert.That(Regex.Matches(evidence, "\\\"status\\\": \\\"PASS\\\"").Count, Is.EqualTo(14));
                var evidenceDocument = JObject.Parse(evidence);
                var observations = (JObject)evidenceDocument["observations"];
                var cancellation = (JObject)observations["cancellation"];
                var reconnect = (JObject)observations["reconnect"];
                CollectionAssert.AreEquivalent(
                    new[]
                    {
                        "conflicting_same_message_id_rejected_without_mutation",
                        "correlation_id_equals_action_id",
                        "direction",
                        "direction_rejected_without_mutation",
                        "duplicate_same_message_id_is_idempotent",
                        "future_state_version_rejected_without_mutation",
                        "python_authority_cancel_transaction_count",
                        "stale_exact_current_action_processed",
                        "stale_nonmatching_or_terminal_authority_mutation_count",
                        "stale_nonmatching_or_terminal_authority_transaction_count",
                        "stale_nonmatching_or_terminal_diagnostic_resync",
                        "unity_direct_authority_mutation_count"
                    },
                    cancellation.Properties().Select(item => item.Name));
                CollectionAssert.AreEquivalent(
                    new[]
                    {
                        "fresh_snapshot_not_older_than_last_acknowledged_version",
                        "full_hello_and_registry_repeated",
                        "late_obsolete_generation_authority_mutation_count",
                        "new_client_ready_before_resume",
                        "new_message_ids",
                        "obsolete_generation_rejected"
                    },
                    reconnect.Properties().Select(item => item.Name));
                Assert.That(cancellation.Value<int>("python_authority_cancel_transaction_count"), Is.EqualTo(1));
                Assert.That(
                    cancellation.Value<int>("stale_nonmatching_or_terminal_authority_transaction_count"),
                    Is.Zero);
                Assert.That(
                    cancellation.Value<int>("stale_nonmatching_or_terminal_authority_mutation_count"),
                    Is.Zero);
                Assert.That(cancellation.Value<bool>("stale_nonmatching_or_terminal_diagnostic_resync"), Is.True);
                Assert.That(File.Exists(Path.Combine(output, "asset-registry.json")), Is.True);
                Assert.That(File.ReadAllText(Path.Combine(output, "handshake-transcript.jsonl")),
                    Does.Not.Contain("/Users/"));
                Assert.That(File.ReadAllText(Path.Combine(output, "editmode-results.xml")),
                    Does.Not.Contain("/Users/"));
                StringAssert.Contains(
                    "live-websocket-smoke=\"passed\"",
                    File.ReadAllText(Path.Combine(output, "playmode-results.xml")));
                StringAssert.Contains(
                    "live_websocket_smoke=PASS transport=ClientWebSocket endpoint=/town",
                    File.ReadAllText(Path.Combine(output, "batchmode.log")));
                Assert.That(
                    File.ReadAllText(Path.Combine(output, "m2-authority-evidence.json")),
                    Is.EqualTo(File.ReadAllText(authorityEvidence)));
                Assert.That(
                    File.ReadAllText(Path.Combine(output, "bridge-authority-transcript.jsonl")),
                    Is.EqualTo(File.ReadAllText(authorityTranscript)));
                var combinedLines = File.ReadAllLines(Path.Combine(output, "handshake-transcript.jsonl"));
                var firstAuthorityLine = JObject.Parse(combinedLines[14]);
                Assert.That(firstAuthorityLine.Value<int>("sequence"), Is.EqualTo(15));
                Assert.That(firstAuthorityLine.Value<int>("sim_sequence"), Is.EqualTo(1));
                Assert.That(firstAuthorityLine.Value<string>("evidence_source"), Is.EqualTo("sim_authority_adapter"));
            }
            finally
            {
                if (Directory.Exists(root))
                {
                    Directory.Delete(root, true);
                }
            }
        }

        private static string PassingXml(int count, bool includeLiveSmoke)
        {
            var liveSmoke = includeLiveSmoke
                ? "<test-case fullname=\"STWM.AITown.Tests.PlayMode.TownBridgeClientPlayModeTests." +
                  "LivePythonBridgeCompletesProductionHandshakeWhenEnabled\" result=\"Passed\" />"
                : string.Empty;
            return $"<test-run result=\"Passed\" total=\"{count}\" passed=\"{count}\" failed=\"0\" " +
                   $"skipped=\"0\" inconclusive=\"0\"><test-suite fullname=\"/Users/redacted/project.dll\">" +
                   $"{liveSmoke}</test-suite></test-run>";
        }

        private static string AuthorityTranscript()
        {
            var before = AuthorityPoint('0', 0);
            var after = AuthorityPoint('1', 1);
            var final = AuthorityPoint('2', 2);
            var records = new List<JObject>
            {
                TranscriptRecord(1, "direction_reject", 1, "unity_message_received", "unity_to_python",
                    "action_cancelled", before, before, 0, 0, "REJECTED", "INVALID_UNITY_TO_PYTHON_ENVELOPE"),
                TranscriptRecord(2, "future_version", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", before, before, 0, 0, "REJECTED", "FUTURE_STATE_VERSION"),
                TranscriptRecord(3, "stale_exact_current_action", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", before, after, 1, 1, "ACCEPTED", null),
                TranscriptRecord(4, "stale_exact_current_action", 1, "python_message_emitted", "python_to_unity",
                    "action_cancelled", after, after, 0, 0, "EMITTED", null, 3),
                TranscriptRecord(5, "duplicate_same_id", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", after, after, 0, 0, "IDEMPOTENT_NOOP", null),
                TranscriptRecord(6, "conflicting_same_id", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", after, after, 0, 0, "REJECTED", "MESSAGE_ID_CONTENT_MISMATCH"),
                TranscriptRecord(7, "stale_nonmatching_or_terminal", 2, "unity_message_received", "unity_to_python",
                    "movement_cancelled", after, after, 0, 0, "DIAGNOSTIC_RESYNC", null),
                TranscriptRecord(8, "late_terminal", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", after, after, 0, 0, "DIAGNOSTIC_RESYNC", null),
                TranscriptRecord(9, "obsolete_generation", 1, "unity_message_received", "unity_to_python",
                    "movement_cancelled", after, after, 0, 0, "REJECTED", "OBSOLETE_CONNECTION_GENERATION"),
                TranscriptRecord(10, "pre_ready_advance", 2, "authority_probe_evaluated", "adapter_to_authority",
                    null, after, after, 0, 0, "GATED", "CLIENT_READY_GATE"),
                TranscriptRecord(11, "post_ready_advance", 2, "authority_probe_evaluated", "adapter_to_authority",
                    null, after, final, 1, 1, "COMMITTED", null)
            };
            return string.Join("\n", records.ConvertAll(item => item.ToString(Formatting.None))) + "\n";
        }

        private static string AuthorityEvidence(string transcriptSha)
        {
            var before = AuthorityPoint('0', 0);
            var after = AuthorityPoint('1', 1);
            var final = AuthorityPoint('2', 2);
            var cancellationProbes = new JObject
            {
                ["direction_reject"] = Probe("direction_reject", 1, before, before, 0, 0, "REJECTED", "INVALID_UNITY_TO_PYTHON_ENVELOPE", 1),
                ["future_version"] = Probe("future_version", 1, before, before, 0, 0, "REJECTED", "FUTURE_STATE_VERSION", 2),
                ["stale_exact_current_action"] = Probe("stale_exact_current_action", 1, before, after, 1, 1, "ACCEPTED", null, 3, 4),
                ["duplicate_same_id"] = Probe("duplicate_same_id", 1, after, after, 0, 0, "IDEMPOTENT_NOOP", null, 5),
                ["conflicting_same_id"] = Probe("conflicting_same_id", 1, after, after, 0, 0, "REJECTED", "MESSAGE_ID_CONTENT_MISMATCH", 6),
                ["stale_nonmatching_or_terminal"] = Probe("stale_nonmatching_or_terminal", 2, after, after, 0, 0, "DIAGNOSTIC_RESYNC", null, 7),
                ["late_terminal"] = Probe("late_terminal", 1, after, after, 0, 0, "DIAGNOSTIC_RESYNC", null, 8)
            };
            var reconnectProbes = new JObject
            {
                ["obsolete_generation"] = Probe("obsolete_generation", 1, after, after, 0, 0, "REJECTED", "OBSOLETE_CONNECTION_GENERATION", 9),
                ["pre_ready_advance"] = Probe("pre_ready_advance", 2, after, after, 0, 0, "GATED", "CLIENT_READY_GATE", 10),
                ["post_ready_advance"] = Probe("post_ready_advance", 2, after, final, 1, 1, "COMMITTED", null, 11),
                ["stale_nonmatching_or_terminal"] = cancellationProbes["stale_nonmatching_or_terminal"].DeepClone()
            };
            var oldSession = SessionObservation(1, before, "old");
            var newSession = SessionObservation(2, after, "new");
            var evidence = new JObject
            {
                ["schema"] = "stwm.bridge.m2-authority-evidence/v1",
                ["project_name"] = "Small Town World Model（STWM）",
                ["scenario"] = new JObject
                {
                    ["name"] = "m2_cancellation_reconnect",
                    ["active_agent_id"] = "npc_01",
                    ["seed"] = 12345
                },
                ["catalog_protocol_version"] = "0.1.0",
                ["negotiated_protocol_version"] = "0.2.0",
                ["passed"] = true,
                ["initial_authority"] = before,
                ["final_authority"] = final,
                ["transcript"] = new JObject
                {
                    ["schema"] = "stwm.bridge.m2-authority-transcript/v1",
                    ["relative_path"] = "bridge-authority-transcript.jsonl",
                    ["record_count"] = 11,
                    ["sha256"] = transcriptSha
                },
                ["observations"] = new JObject
                {
                    ["cancellation"] = new JObject
                    {
                        ["direction"] = "unity_to_python",
                        ["correlation_id_equals_action_id"] = true,
                        ["python_authority_cancel_transaction_count"] = 1,
                        ["unity_direct_authority_mutation_count"] = 0,
                        ["duplicate_same_message_id_is_idempotent"] = true,
                        ["conflicting_same_message_id_rejected_without_mutation"] = true,
                        ["direction_rejected_without_mutation"] = true,
                        ["future_state_version_rejected_without_mutation"] = true,
                        ["stale_exact_current_action_processed"] = true,
                        ["stale_state_message_authority_mutation_count"] = 0,
                        ["late_terminal_message_authority_mutation_count"] = 0,
                        ["probes"] = cancellationProbes,
                        ["evidence_refs"] = CancellationEvidenceRefs()
                    },
                    ["reconnect"] = new JObject
                    {
                        ["full_hello_and_registry_repeated"] = true,
                        ["new_message_ids"] = true,
                        ["fresh_snapshot_not_older_than_last_acknowledged_version"] = true,
                        ["new_client_ready_before_resume"] = true,
                        ["obsolete_generation_rejected"] = true,
                        ["late_obsolete_generation_authority_mutation_count"] = 0,
                        ["stale_state_message_authority_mutation_count"] = 0,
                        ["old_generation_last_acknowledged_state_version"] = 1,
                        ["fresh_snapshot"] = after.DeepClone(),
                        ["old_generation"] = oldSession,
                        ["new_generation"] = newSession,
                        ["probes"] = reconnectProbes,
                        ["evidence_refs"] = ReconnectEvidenceRefs()
                    }
                },
                ["runtime_evidence"] = new JObject { ["authority_inputs"] = new JArray("accepted_cancel") }
            };
            return evidence.ToString(Formatting.None);
        }

        private static JObject Probe(
            string id,
            int generation,
            JObject before,
            JObject after,
            int mutations,
            int transactions,
            string outcome,
            string errorCode,
            params int[] transcriptSequences)
        {
            return new JObject
            {
                ["probe_id"] = id,
                ["connection_generation"] = generation,
                ["before"] = before.DeepClone(),
                ["after"] = after.DeepClone(),
                ["authority_mutation_count"] = mutations,
                ["authority_transaction_count"] = transactions,
                ["outcome"] = outcome,
                ["error_code"] = errorCode == null ? JValue.CreateNull() : new JValue(errorCode),
                ["transcript_sequences"] = new JArray(transcriptSequences)
            };
        }

        private static JObject TranscriptRecord(
            int sequence,
            string probeId,
            int generation,
            string eventType,
            string direction,
            string messageType,
            JObject before,
            JObject after,
            int mutations,
            int transactions,
            string outcome,
            string errorCode,
            int? triggerSequence = null)
        {
            var authorityProbe = eventType == "authority_probe_evaluated";
            return new JObject
            {
                ["schema"] = "stwm.bridge.m2-authority-transcript/v1",
                ["sequence"] = sequence,
                ["event_type"] = eventType,
                ["probe_id"] = probeId,
                ["connection_generation"] = generation,
                ["direction"] = direction,
                ["message_id"] = authorityProbe ? JValue.CreateNull() : new JValue($"msg_{sequence:000}"),
                ["message_type"] = messageType == null ? JValue.CreateNull() : new JValue(messageType),
                ["state_version"] = before.Value<int>("state_version"),
                ["trigger_sequence"] = triggerSequence.HasValue
                    ? new JValue(triggerSequence.Value)
                    : JValue.CreateNull(),
                ["authority_before"] = before.DeepClone(),
                ["authority_after"] = after.DeepClone(),
                ["authority_mutation_count"] = mutations,
                ["authority_transaction_count"] = transactions,
                ["outcome"] = outcome,
                ["error_code"] = errorCode == null ? JValue.CreateNull() : new JValue(errorCode),
                ["envelope"] = authorityProbe ? JValue.CreateNull() : new JObject()
            };
        }

        private static JObject SessionObservation(int generation, JObject snapshot, string suffix)
        {
            return new JObject
            {
                ["generation"] = generation,
                ["catalog_protocol_version"] = "0.1.0",
                ["negotiated_protocol_version"] = "0.2.0",
                ["hello_message_id"] = $"msg_{suffix}_hello",
                ["server_hello_message_id"] = $"msg_{suffix}_server_hello",
                ["registry_message_id"] = $"msg_{suffix}_registry",
                ["registry_result_message_id"] = $"msg_{suffix}_registry_result",
                ["snapshot_message_id"] = $"msg_{suffix}_snapshot",
                ["snapshot"] = snapshot.DeepClone(),
                ["ready_message_id"] = $"msg_{suffix}_ready",
                ["ready_before_ack"] = false,
                ["ready_after_ack"] = true,
                ["last_client_applied_state_version"] = snapshot.Value<int>("state_version"),
                ["handshake_message_types"] = new JArray(
                    "client_hello",
                    "server_hello",
                    "asset_registry",
                    "asset_registry_result",
                    "world_snapshot",
                    "client_ready"),
                ["message_ids"] = new JArray($"msg_{suffix}_hello", $"msg_{suffix}_server_hello")
            };
        }

        private static JObject CancellationEvidenceRefs()
        {
            return new JObject
            {
                ["direction"] = "stale_exact_current_action",
                ["correlation_id_equals_action_id"] = "stale_exact_current_action",
                ["python_authority_cancel_transaction_count"] = "runtime_evidence.authority_inputs",
                ["unity_direct_authority_mutation_count"] = "stale_exact_current_action",
                ["duplicate_same_message_id_is_idempotent"] = "duplicate_same_id",
                ["conflicting_same_message_id_rejected_without_mutation"] = "conflicting_same_id",
                ["direction_rejected_without_mutation"] = "direction_reject",
                ["future_state_version_rejected_without_mutation"] = "future_version",
                ["stale_exact_current_action_processed"] = "stale_exact_current_action",
                ["stale_state_message_authority_mutation_count"] = "stale_nonmatching_or_terminal",
                ["late_terminal_message_authority_mutation_count"] = "late_terminal"
            };
        }

        private static JObject ReconnectEvidenceRefs()
        {
            return new JObject
            {
                ["full_hello_and_registry_repeated"] = "old_generation,new_generation",
                ["new_message_ids"] = "old_generation.message_ids,new_generation.message_ids",
                ["fresh_snapshot_not_older_than_last_acknowledged_version"] =
                    "old_generation_last_acknowledged_state_version,fresh_snapshot.state_version",
                ["new_client_ready_before_resume"] = "pre_ready_advance,new_generation,post_ready_advance",
                ["obsolete_generation_rejected"] = "obsolete_generation",
                ["late_obsolete_generation_authority_mutation_count"] = "obsolete_generation",
                ["stale_state_message_authority_mutation_count"] = "stale_nonmatching_or_terminal",
                ["old_generation_last_acknowledged_state_version"] = "old_generation"
            };
        }

        private static JObject AuthorityPoint(char hashCharacter, int version)
        {
            return new JObject
            {
                ["state_hash"] = new string(hashCharacter, 64),
                ["state_version"] = version,
                ["game_minute"] = version
            };
        }

        private static string ComputeSha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", string.Empty).ToLowerInvariant();
            }
        }
    }
}
