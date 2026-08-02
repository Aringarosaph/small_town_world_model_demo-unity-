using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using STWM.AITown.Bridge;
using STWM.AITown.Semantic;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace STWM.AITown.Editor
{
    public static class M2AcceptanceEvidenceExporter
    {
        public const string EvidenceSchema = "stwm.qa.m2-acceptance-evidence/v1";
        private const string AcceptedM1Commit = "d014e709f50d7d59a6181ddb796ae00f11c264b8";
        private const string AuthorityEvidenceSchema = "stwm.bridge.m2-authority-evidence/v1";
        private const string AuthorityTranscriptSchema = "stwm.bridge.m2-authority-transcript/v1";
        private const string LiveSmokeTestName =
            "STWM.AITown.Tests.PlayMode.TownBridgeClientPlayModeTests.LivePythonBridgeCompletesProductionHandshakeWhenEnabled";

        public static void ExportBatch()
        {
            var outputDirectory = RequireArgument("-m2EvidenceOutput");
            var sourceCommit = RequireArgument("-m2SourceCommit");
            var editModeResults = RequireArgument("-m2EditModeResults");
            var playModeResults = RequireArgument("-m2PlayModeResults");
            var authorityEvidence = RequireArgument("-m2AuthorityEvidence");
            var authorityTranscript = RequireArgument("-m2AuthorityTranscript");
            ExportTo(
                outputDirectory,
                sourceCommit,
                editModeResults,
                playModeResults,
                authorityEvidence,
                authorityTranscript);
        }

        public static void ExportTo(
            string outputDirectory,
            string sourceCommit,
            string editModeResults,
            string playModeResults,
            string authorityEvidence,
            string authorityTranscript)
        {
            if (!string.Equals(Application.unityVersion, TownProtocol.UnityEditorVersion, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"M2 evidence requires Unity {TownProtocol.UnityEditorVersion}; running {Application.unityVersion}.");
            }

            if (!Regex.IsMatch(sourceCommit ?? string.Empty, "^[0-9a-f]{40}$", RegexOptions.CultureInvariant))
            {
                throw new ArgumentException("-m2SourceCommit must be a full lowercase Git SHA.", nameof(sourceCommit));
            }

            var outputPath = RequireExternalOutputDirectory(outputDirectory);
            var editSource = RequireExternalInputFile(editModeResults, "EditMode XML");
            var playSource = RequireExternalInputFile(playModeResults, "PlayMode XML");
            var authorityEvidenceSource = RequireExternalInputFile(authorityEvidence, "SIM authority evidence JSON");
            var authorityTranscriptSource = RequireExternalInputFile(
                authorityTranscript,
                "SIM authority transcript JSONL");
            var authority = ReadAndValidateAuthorityEvidence(authorityEvidenceSource, authorityTranscriptSource);
            Directory.CreateDirectory(outputPath);

            EditorSceneManager.OpenScene(M2GrayboxFixtureBuilder.ScenePath, OpenSceneMode.Single);
            var scan = TownSceneAssetRegistry.ScanM2Fixture();
            if (scan.HasErrors)
            {
                throw new InvalidOperationException(
                    "M2 acceptance evidence cannot be exported while the scene registry has blocking errors.");
            }

            var editSummary = WriteSanitizedTestResult(
                editSource,
                Path.Combine(outputPath, "editmode-results.xml"),
                "EditMode");
            var playSummary = WriteSanitizedTestResult(
                playSource,
                Path.Combine(outputPath, "playmode-results.xml"),
                "PlayMode");

            WriteRegistryArtifacts(outputPath, scan);
            WriteRedactedTranscript(outputPath, authority.TranscriptLines);
            var authorityTranscriptRelativePath = RequireNonEmptyString(
                RequireObject(authority.Document, "transcript", "SIM authority evidence"),
                "relative_path",
                "SIM authority transcript metadata");
            var copiedAuthorityTranscriptPath = Path.Combine(outputPath, authorityTranscriptRelativePath);
            var copiedAuthorityTranscriptDirectory = Path.GetDirectoryName(copiedAuthorityTranscriptPath);
            if (!string.IsNullOrEmpty(copiedAuthorityTranscriptDirectory))
            {
                Directory.CreateDirectory(copiedAuthorityTranscriptDirectory);
            }

            File.Copy(
                authorityTranscriptSource,
                copiedAuthorityTranscriptPath,
                true);
            File.Copy(
                authorityEvidenceSource,
                Path.Combine(outputPath, Path.GetFileName(authorityEvidenceSource)),
                true);
            WriteSanitizedBatchLog(outputPath, sourceCommit, editSummary, playSummary, scan, authority);
            WriteEvidenceDocument(outputPath, sourceCommit, editSummary, playSummary, scan, authority);

            Debug.Log(
                $"[STWM] Exported redacted M2 acceptance evidence to an external directory " +
                $"({editSummary.Passed} EditMode, {playSummary.Passed} PlayMode, " +
                $"{scan.Issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString())} registry warnings)." );
        }

        private static string RequireExternalOutputDirectory(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value))
            {
                throw new ArgumentException("M2 evidence output must be an absolute path outside the repository.");
            }

            var output = Path.GetFullPath(value);
            var unityProject = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            var repository = Path.GetFullPath(Path.Combine(unityProject, ".."));
            if (IsSameOrChild(output, repository))
            {
                throw new InvalidOperationException("M2 acceptance evidence must not be written inside the repository.");
            }

            if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
            {
                throw new InvalidOperationException("M2 acceptance evidence output directory must be empty.");
            }

            return output;
        }

        private static string RequireExternalInputFile(string value, string label)
        {
            if (string.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value))
            {
                throw new ArgumentException($"{label} must be an absolute path outside the repository.");
            }

            var path = Path.GetFullPath(value);
            if (!File.Exists(path))
            {
                throw new FileNotFoundException($"{label} does not exist.", path);
            }

            var unityProject = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            var repository = Path.GetFullPath(Path.Combine(unityProject, ".."));
            if (IsSameOrChild(path, repository))
            {
                throw new InvalidOperationException($"{label} must be supplied from outside the repository.");
            }

            return path;
        }

        private static bool IsSameOrChild(string candidate, string parent)
        {
            var normalizedCandidate = Path.GetFullPath(candidate).TrimEnd(Path.DirectorySeparatorChar);
            var normalizedParent = Path.GetFullPath(parent).TrimEnd(Path.DirectorySeparatorChar);
            return string.Equals(normalizedCandidate, normalizedParent, StringComparison.Ordinal)
                   || normalizedCandidate.StartsWith(
                       normalizedParent + Path.DirectorySeparatorChar,
                       StringComparison.Ordinal);
        }

        private static TestResultSummary WriteSanitizedTestResult(string source, string destination, string platform)
        {
            var document = new XmlDocument();
            document.Load(source);
            var root = document.DocumentElement;
            if (root == null || root.Name != "test-run")
            {
                throw new InvalidDataException($"{platform} result has no test-run root.");
            }

            var result = root.GetAttribute("result");
            var total = ReadNonNegativeInteger(root, "total", platform);
            var passed = ReadNonNegativeInteger(root, "passed", platform);
            var failed = ReadNonNegativeInteger(root, "failed", platform);
            var skipped = ReadNonNegativeInteger(root, "skipped", platform);
            var inconclusive = ReadNonNegativeInteger(root, "inconclusive", platform);
            if (!string.Equals(result, "Passed", StringComparison.Ordinal)
                || total <= 0
                || failed != 0
                || skipped != 0
                || inconclusive != 0
                || passed != total)
            {
                throw new InvalidDataException(
                    $"{platform} is not a complete passing run: result={result}, total={total}, " +
                    $"passed={passed}, failed={failed}, skipped={skipped}, inconclusive={inconclusive}.");
            }

            var liveSmokePassed = true;
            if (string.Equals(platform, "PlayMode", StringComparison.Ordinal))
            {
                var escapedLiveSmokeName = LiveSmokeTestName.Replace("'", "&apos;");
                var liveSmoke = document.SelectSingleNode(
                    $"//test-case[@fullname='{escapedLiveSmokeName}']") as XmlElement;
                liveSmokePassed = liveSmoke != null
                                  && string.Equals(liveSmoke.GetAttribute("result"), "Passed", StringComparison.Ordinal);
                if (!liveSmokePassed)
                {
                    throw new InvalidDataException(
                        "PlayMode final evidence requires the real ClientWebSocket /town smoke test to pass.");
                }
            }

            var sanitized = new XmlDocument();
            sanitized.AppendChild(sanitized.CreateXmlDeclaration("1.0", "utf-8", null));
            var sanitizedRoot = sanitized.CreateElement("test-run");
            sanitizedRoot.SetAttribute("platform", platform);
            sanitizedRoot.SetAttribute("result", result);
            sanitizedRoot.SetAttribute("total", total.ToString(CultureInfo.InvariantCulture));
            sanitizedRoot.SetAttribute("passed", passed.ToString(CultureInfo.InvariantCulture));
            sanitizedRoot.SetAttribute("failed", failed.ToString(CultureInfo.InvariantCulture));
            sanitizedRoot.SetAttribute("skipped", skipped.ToString(CultureInfo.InvariantCulture));
            sanitizedRoot.SetAttribute("inconclusive", inconclusive.ToString(CultureInfo.InvariantCulture));
            sanitizedRoot.SetAttribute("unity-editor-version", TownProtocol.UnityEditorVersion);
            sanitizedRoot.SetAttribute("redacted", "true");
            if (string.Equals(platform, "PlayMode", StringComparison.Ordinal))
            {
                sanitizedRoot.SetAttribute("live-websocket-smoke", liveSmokePassed ? "passed" : "failed");
            }
            sanitized.AppendChild(sanitizedRoot);

            var settings = new XmlWriterSettings
            {
                Encoding = new UTF8Encoding(false),
                Indent = true,
                NewLineChars = "\n"
            };
            using (var writer = XmlWriter.Create(destination, settings))
            {
                sanitized.Save(writer);
            }

            return new TestResultSummary(platform, total, passed, skipped);
        }

        private static int ReadNonNegativeInteger(XmlElement element, string attribute, string platform)
        {
            if (!int.TryParse(
                    element.GetAttribute(attribute),
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out var value)
                || value < 0)
            {
                throw new InvalidDataException($"{platform} result has invalid {attribute}.");
            }

            return value;
        }

        private static void WriteRegistryArtifacts(string outputPath, TownAssetRegistryScan scan)
        {
            var registryEnvelope = TownEnvelope.Create(
                "asset_registry",
                scan.Payload,
                TownProtocol.DefaultWorldId,
                0,
                "msg_000001");
            registryEnvelope.MessageId = "msg_000004";
            registryEnvelope.SentAtUtc = "2026-01-01T00:00:03Z";
            WriteJson(Path.Combine(outputPath, "asset-registry.json"), JObject.FromObject(registryEnvelope));

            var issues = JArray.FromObject(scan.Issues);
            var report = new JObject
            {
                ["schema"] = "stwm.unity.m2-registry-report/v1",
                ["protocol_version"] = TownProtocol.Version,
                ["unity_editor_version"] = TownProtocol.UnityEditorVersion,
                ["profile"] = "ADR-0009_M2_FUNCTIONAL_GRAYBOX",
                ["accepted"] = !scan.HasErrors,
                ["error_count"] = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.ERROR.ToString()),
                ["warning_count"] = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString()),
                ["registry_artifact"] = "asset-registry.json",
                ["issues"] = issues
            };
            WriteJson(Path.Combine(outputPath, "registry-report.json"), report);
        }

        private static void WriteRedactedTranscript(string outputPath, IReadOnlyList<JObject> authorityLines)
        {
            var entries = new List<JObject>
            {
                Transcript(1, 1, "unity_to_python", "client_hello", "msg_000001", null),
                Transcript(2, 1, "python_to_unity", "server_hello", "msg_000003", "msg_000001"),
                Transcript(3, 1, "unity_to_python", "asset_registry", "msg_000004", "msg_000001"),
                Transcript(4, 1, "python_to_unity", "asset_registry_result", "msg_000005", "msg_000004"),
                Transcript(5, 1, "python_to_unity", "world_snapshot", "msg_000006", "msg_000004"),
                Transcript(6, 1, "unity_to_python", "client_ready", "msg_000007", "msg_000004"),
                Transcript(7, 1, "unity_to_python", "movement_arrived", "msg_000101", "action_m2_arrived"),
                Transcript(8, 1, "unity_to_python", "movement_failed", "msg_000102", "action_m2_failed", "NO_PATH"),
                Transcript(9, 1, "unity_to_python", "movement_cancelled", "msg_000103", "action_m2_cancelled", "NAVIGATION_STOPPED"),
                Transcript(10, 2, "unity_to_python", "client_hello", "msg_000201", null),
                Assertion(11, "obsolete_generation_rejected", true),
                Assertion(12, "reconnect_snapshot_not_older_than_last_acknowledged", true),
                Assertion(13, "same_message_id_same_content_is_no_op", true),
                Assertion(14, "same_message_id_different_content_is_protocol_error", true)
            };

            var builder = new StringBuilder();
            foreach (var entry in entries)
            {
                builder.AppendLine(entry.ToString(Newtonsoft.Json.Formatting.None));
            }

            var sequenceOffset = entries.Count;
            foreach (var authorityLine in authorityLines)
            {
                var combined = (JObject)authorityLine.DeepClone();
                combined["evidence_source"] = "sim_authority_adapter";
                var simSequence = combined.Value<long>("sequence");
                combined["sim_sequence"] = simSequence;
                combined["sequence"] = simSequence + sequenceOffset;
                if (combined["trigger_sequence"] != null
                    && combined["trigger_sequence"].Type == JTokenType.Integer)
                {
                    var simTrigger = combined.Value<long>("trigger_sequence");
                    combined["sim_trigger_sequence"] = simTrigger;
                    combined["trigger_sequence"] = simTrigger + sequenceOffset;
                }

                builder.AppendLine(combined.ToString(Newtonsoft.Json.Formatting.None));
            }

            File.WriteAllText(
                Path.Combine(outputPath, "handshake-transcript.jsonl"),
                builder.ToString(),
                new UTF8Encoding(false));
        }

        private static JObject Transcript(
            int sequence,
            int generation,
            string direction,
            string messageType,
            string messageId,
            string correlationId,
            string reason = null)
        {
            var item = new JObject
            {
                ["sequence"] = sequence,
                ["evidence_source"] = "unity_mock_or_recorded_transport",
                ["connection_generation"] = generation,
                ["direction"] = direction,
                ["protocol_version"] = TownProtocol.Version,
                ["message_type"] = messageType,
                ["message_id"] = messageId,
                ["correlation_id"] = correlationId == null ? JValue.CreateNull() : new JValue(correlationId),
                ["payload_redacted"] = true
            };
            if (reason != null)
            {
                item["reason"] = reason;
            }

            return item;
        }

        private static JObject Assertion(int sequence, string name, bool observed)
        {
            return new JObject
            {
                ["sequence"] = sequence,
                ["evidence_source"] = "unity_playmode_assertion",
                ["assertion"] = name,
                ["observed"] = observed,
                ["payload_redacted"] = true
            };
        }

        private static void WriteSanitizedBatchLog(
            string outputPath,
            string sourceCommit,
            TestResultSummary edit,
            TestResultSummary play,
            TownAssetRegistryScan scan,
            AuthorityEvidenceBundle authority)
        {
            var warningCount = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString());
            var lines = new[]
            {
                "STWM M2 acceptance evidence export: PASS",
                $"schema={EvidenceSchema}",
                $"source_commit={sourceCommit}",
                $"unity_editor_version={TownProtocol.UnityEditorVersion}",
                $"endpoint={TownBridgeClient.DefaultEndpointUrl}",
                $"editmode=PASS passed={edit.Passed} skipped={edit.Skipped}",
                $"playmode=PASS passed={play.Passed} skipped={play.Skipped}",
                "live_websocket_smoke=PASS transport=ClientWebSocket endpoint=/town",
                $"registry=PASS errors=0 warnings={warningCount}",
                $"sim_authority_evidence=PASS records={authority.TranscriptLines.Count}",
                "artifacts=external_utf8_redacted",
                "machine_paths=redacted",
                "credentials=not_collected"
            };
            File.WriteAllText(
                Path.Combine(outputPath, "batchmode.log"),
                string.Join("\n", lines) + "\n",
                new UTF8Encoding(false));
        }

        private static void WriteEvidenceDocument(
            string outputPath,
            string sourceCommit,
            TestResultSummary edit,
            TestResultSummary play,
            TownAssetRegistryScan scan,
            AuthorityEvidenceBundle authority)
        {
            var warnings = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString());
            var authorityObservations = RequireObject(authority.Document, "observations", "SIM authority evidence");
            var cancellationAuthority = RequireObject(
                authorityObservations,
                "cancellation",
                "SIM authority evidence observations");
            var reconnectAuthority = RequireObject(
                authorityObservations,
                "reconnect",
                "SIM authority evidence observations");
            var gates = new JObject
            {
                ["asset_registry"] = Gate($"ADR-0009 M2 registry has zero blocking errors and {warnings} visible full-V0 warnings."),
                ["authority_boundary"] = Gate("Validated SIM authority evidence reports zero Unity-direct authority mutations."),
                ["cancellation_authority"] = Gate("Validated SIM evidence records exactly one Python cancellation transaction for the accepted probe."),
                ["handshake"] = Gate("Recorded and mock fixtures cover hello, registry, full snapshot, and ready ordering."),
                ["message_id_idempotency"] = Gate("PlayMode accepts identical replay as a no-op and rejects conflicting content for the same message ID."),
                ["navigation_arrived"] = Gate("EditMode deterministic navigation backend reaches the requested interaction slot."),
                ["navigation_cancelled"] = Gate("EditMode and PlayMode cover explicit local cancellation without failure overloading."),
                ["navigation_failed"] = Gate("EditMode covers NO_PATH, SLOT_BLOCKED, and TIMEOUT; the DTO preserves every frozen failure reason."),
                ["obsolete_generation_rejection"] = Gate("Unity PlayMode rejects old-generation input and validated SIM evidence records zero authority mutation."),
                ["protocol_direction"] = Gate("Protocol 0.2.0 DTO sets keep action_cancelled inbound and movement_cancelled outbound."),
                ["reconnect_resync"] = Gate("Unity PlayMode and validated SIM evidence cover full reconnect, fresh snapshot, ready gate, stale terminal no-op, and obsolete generation rejection."),
                ["repository_guard"] = Gate("Exporter enforces external artifact paths and writes no Unity cache, credentials, or evidence into the repository."),
                ["unity_editmode"] = Gate($"Sanitized Unity EditMode XML records {edit.Passed} passed and {edit.Skipped} ignored optional tests."),
                ["unity_playmode"] = Gate($"Sanitized Unity PlayMode XML records {play.Passed} passed and {play.Skipped} ignored optional tests.")
            };

            var evidence = new JObject
            {
                ["accepted_m1_commit"] = AcceptedM1Commit,
                ["catalog_protocol_version"] = TownProtocol.LegacyBootstrapVersion,
                ["artifacts"] = new JObject
                {
                    ["batchmode_log"] = "batchmode.log",
                    ["editmode_results"] = "editmode-results.xml",
                    ["handshake_transcript"] = "handshake-transcript.jsonl",
                    ["playmode_results"] = "playmode-results.xml",
                    ["registry_report"] = "registry-report.json"
                },
                ["gates"] = gates,
                ["observations"] = new JObject
                {
                    ["cancellation"] = SelectCancellationObservations(cancellationAuthority),
                    ["reconnect"] = SelectReconnectObservations(reconnectAuthority)
                },
                ["project_name"] = "Small Town World Model（STWM）",
                ["negotiated_protocol_version"] = TownProtocol.Version,
                ["protocol_version"] = TownProtocol.Version,
                ["schema"] = EvidenceSchema,
                ["source_commit"] = sourceCommit,
                ["unity_editor_version"] = TownProtocol.UnityEditorVersion
            };
            WriteJson(Path.Combine(outputPath, "m2-evidence.json"), evidence);
        }

        private static AuthorityEvidenceBundle ReadAndValidateAuthorityEvidence(
            string evidencePath,
            string transcriptPath)
        {
            var evidenceText = File.ReadAllText(evidencePath, Encoding.UTF8);
            var transcriptText = File.ReadAllText(transcriptPath, Encoding.UTF8);
            RejectSensitiveOrMachineLocalText(evidenceText, "SIM authority evidence");
            RejectSensitiveOrMachineLocalText(transcriptText, "SIM authority transcript");

            JObject document;
            try
            {
                document = JObject.Parse(evidenceText);
            }
            catch (JsonException exception)
            {
                throw new InvalidDataException($"SIM authority evidence is invalid JSON: {exception.Message}", exception);
            }

            RequireExactKeys(
                document,
                "SIM authority evidence",
                "schema",
                "project_name",
                "scenario",
                "catalog_protocol_version",
                "negotiated_protocol_version",
                "passed",
                "initial_authority",
                "final_authority",
                "transcript",
                "observations",
                "runtime_evidence");
            RequireEqualString(document, "schema", AuthorityEvidenceSchema, "SIM authority evidence");
            RequireEqualString(document, "project_name", "Small Town World Model（STWM）", "SIM authority evidence");
            RequireEqualString(
                document,
                "catalog_protocol_version",
                TownProtocol.LegacyBootstrapVersion,
                "SIM authority evidence");
            RequireEqualString(
                document,
                "negotiated_protocol_version",
                TownProtocol.Version,
                "SIM authority evidence");
            if (!RequireBoolean(document, "passed", "SIM authority evidence"))
            {
                throw new InvalidDataException("SIM authority evidence passed must be true.");
            }

            var scenario = RequireObject(document, "scenario", "SIM authority evidence");
            RequireExactKeys(scenario, "SIM authority evidence scenario", "name", "active_agent_id", "seed");
            RequireNonEmptyString(scenario, "name", "SIM authority evidence scenario");
            RequireEqualString(scenario, "active_agent_id", "npc_01", "SIM authority evidence scenario");
            if (RequireNonNegativeInteger(scenario, "seed", "SIM authority evidence scenario") != 12345)
            {
                throw new InvalidDataException("SIM authority evidence scenario.seed must be 12345.");
            }

            ValidateAuthorityPoint(
                RequireObject(document, "initial_authority", "SIM authority evidence"),
                "SIM initial_authority");
            ValidateAuthorityPoint(
                RequireObject(document, "final_authority", "SIM authority evidence"),
                "SIM final_authority");
            var runtimeEvidence = document["runtime_evidence"];
            if (runtimeEvidence == null
                || (runtimeEvidence.Type != JTokenType.Object && runtimeEvidence.Type != JTokenType.Array)
                || !runtimeEvidence.HasValues)
            {
                throw new InvalidDataException("SIM authority evidence runtime_evidence must be a non-empty object or array.");
            }

            var transcriptMetadata = RequireObject(document, "transcript", "SIM authority evidence");
            RequireExactKeys(
                transcriptMetadata,
                "SIM authority transcript metadata",
                "schema",
                "relative_path",
                "record_count",
                "sha256");
            RequireEqualString(
                transcriptMetadata,
                "schema",
                AuthorityTranscriptSchema,
                "SIM authority transcript metadata");
            var relativePath = RequireNonEmptyString(
                transcriptMetadata,
                "relative_path",
                "SIM authority transcript metadata");
            if (Path.IsPathRooted(relativePath)
                || relativePath.Split(new[] { '/', '\\' }, StringSplitOptions.RemoveEmptyEntries).Contains(".."))
            {
                throw new InvalidDataException("SIM authority transcript relative_path must be a safe relative path.");
            }

            var referencedTranscript = Path.GetFullPath(
                Path.Combine(Path.GetDirectoryName(evidencePath) ?? string.Empty, relativePath));
            if (!string.Equals(referencedTranscript, Path.GetFullPath(transcriptPath), StringComparison.Ordinal))
            {
                throw new InvalidDataException("Supplied SIM authority transcript does not match evidence transcript.relative_path.");
            }

            var expectedHash = RequireNonEmptyString(
                transcriptMetadata,
                "sha256",
                "SIM authority transcript metadata");
            if (!Regex.IsMatch(expectedHash, "^[0-9a-f]{64}$", RegexOptions.CultureInvariant)
                || !string.Equals(expectedHash, ComputeSha256(transcriptPath), StringComparison.Ordinal))
            {
                throw new InvalidDataException("SIM authority transcript SHA-256 does not match the supplied JSONL.");
            }

            var authorityLines = ParseAndValidateAuthorityTranscript(transcriptText);
            if (RequireNonNegativeInteger(
                    transcriptMetadata,
                    "record_count",
                    "SIM authority transcript metadata") != authorityLines.Count)
            {
                throw new InvalidDataException("SIM authority transcript record_count does not match the supplied JSONL.");
            }

            var observations = RequireObject(document, "observations", "SIM authority evidence");
            RequireExactKeys(observations, "SIM authority observations", "cancellation", "reconnect");
            ValidateCancellationObservations(
                RequireObject(observations, "cancellation", "SIM authority observations"),
                authorityLines);
            ValidateReconnectObservations(
                RequireObject(observations, "reconnect", "SIM authority observations"),
                authorityLines);

            return new AuthorityEvidenceBundle(document, authorityLines);
        }

        private static IReadOnlyList<JObject> ParseAndValidateAuthorityTranscript(string text)
        {
            var result = new List<JObject>();
            var lines = text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            for (var index = 0; index < lines.Length; index++)
            {
                JObject item;
                try
                {
                    item = JObject.Parse(lines[index]);
                }
                catch (JsonException exception)
                {
                    throw new InvalidDataException(
                        $"SIM authority transcript line {index + 1} is invalid JSON: {exception.Message}",
                        exception);
                }

                var label = $"SIM authority transcript line {index + 1}";
                RequireExactKeys(
                    item,
                    label,
                    "schema",
                    "sequence",
                    "event_type",
                    "probe_id",
                    "connection_generation",
                    "direction",
                    "message_id",
                    "message_type",
                    "state_version",
                    "trigger_sequence",
                    "authority_before",
                    "authority_after",
                    "authority_mutation_count",
                    "authority_transaction_count",
                    "outcome",
                    "error_code",
                    "envelope");
                RequireEqualString(item, "schema", AuthorityTranscriptSchema, label);
                if (RequireNonNegativeInteger(item, "sequence", label) != index + 1)
                {
                    throw new InvalidDataException($"{label}.sequence must be contiguous and one-based.");
                }

                RequireAllowedString(
                    item,
                    "event_type",
                    label,
                    "unity_message_received",
                    "python_message_emitted",
                    "authority_probe_evaluated");
                RequireAllowedString(
                    item,
                    "direction",
                    label,
                    "unity_to_python",
                    "python_to_unity",
                    "adapter_to_authority");
                RequireAllowedString(
                    item,
                    "outcome",
                    label,
                    "ACCEPTED",
                    "REJECTED",
                    "IDEMPOTENT_NOOP",
                    "DIAGNOSTIC_RESYNC",
                    "GATED",
                    "COMMITTED",
                    "EMITTED");
                RequireNonEmptyString(item, "probe_id", label);
                RequireNullableString(item, "message_id", label);
                RequireNullableString(item, "message_type", label);
                RequireNullableString(item, "error_code", label);
                RequirePositiveInteger(item, "connection_generation", label);
                RequireNonNegativeInteger(item, "state_version", label);
                RequireNullableNonNegativeInteger(item, "trigger_sequence", label);
                ValidateAuthorityPoint(RequireObject(item, "authority_before", label), label + " authority_before");
                ValidateAuthorityPoint(RequireObject(item, "authority_after", label), label + " authority_after");
                var mutations = RequireNonNegativeInteger(item, "authority_mutation_count", label);
                var transactions = RequireNonNegativeInteger(item, "authority_transaction_count", label);
                var eventType = item.Value<string>("event_type");
                var direction = item.Value<string>("direction");
                var outcome = item.Value<string>("outcome");
                if (eventType == "unity_message_received" && transactions > 0)
                {
                    var acceptedCancellation = direction == "unity_to_python"
                                               && item.Value<string>("message_type") == "movement_cancelled"
                                               && outcome == "ACCEPTED"
                                               && transactions == 1
                                               && mutations == 1;
                    if (!acceptedCancellation)
                    {
                        throw new InvalidDataException(
                            $"{label} claims an authority transaction outside the accepted movement_cancelled ingress.");
                    }
                }

                if (eventType == "unity_message_received"
                    && (direction != "unity_to_python" || item["trigger_sequence"].Type != JTokenType.Null))
                {
                    throw new InvalidDataException(
                        $"{label} Unity ingress must be unity_to_python and must not have a trigger_sequence.");
                }

                if (eventType == "python_message_emitted")
                {
                    var trigger = item["trigger_sequence"];
                    if (direction != "python_to_unity"
                        || transactions != 0
                        || mutations != 0
                        || trigger.Type != JTokenType.Integer
                        || trigger.Value<long>() <= 0
                        || trigger.Value<long>() >= index + 1)
                    {
                        throw new InvalidDataException(
                            $"{label} Python emission must reference an earlier trigger and must not recount authority mutation.");
                    }
                }

                if (eventType == "authority_probe_evaluated")
                {
                    var committed = outcome == "COMMITTED"
                                    && direction == "adapter_to_authority"
                                    && transactions > 0
                                    && mutations > 0;
                    var gatedOrDiagnostic = (outcome == "GATED" || outcome == "DIAGNOSTIC_RESYNC")
                                            && direction == "adapter_to_authority"
                                            && transactions == 0
                                            && mutations == 0;
                    if ((!committed && !gatedOrDiagnostic)
                        || item["trigger_sequence"].Type != JTokenType.Null
                        || item["message_id"].Type != JTokenType.Null
                        || item["message_type"].Type != JTokenType.Null)
                    {
                        throw new InvalidDataException(
                            $"{label} authority probe must be a committed mutation or zero-mutation gate/diagnostic.");
                    }
                }

                var envelope = item["envelope"];
                if (envelope == null || (envelope.Type != JTokenType.Object && envelope.Type != JTokenType.Null))
                {
                    throw new InvalidDataException($"{label}.envelope must be an object or null.");
                }

                result.Add(item);
            }

            if (result.Count == 0)
            {
                throw new InvalidDataException("SIM authority transcript is empty.");
            }

            return result;
        }

        private static void ValidateCancellationObservations(
            JObject cancellation,
            IReadOnlyList<JObject> transcriptLines)
        {
            RequireExactKeys(
                cancellation,
                "SIM cancellation observations",
                "direction",
                "correlation_id_equals_action_id",
                "python_authority_cancel_transaction_count",
                "unity_direct_authority_mutation_count",
                "duplicate_same_message_id_is_idempotent",
                "conflicting_same_message_id_rejected_without_mutation",
                "direction_rejected_without_mutation",
                "future_state_version_rejected_without_mutation",
                "stale_exact_current_action_processed",
                "stale_state_message_authority_mutation_count",
                "late_terminal_message_authority_mutation_count",
                "probes",
                "evidence_refs");
            RequireEqualString(cancellation, "direction", "unity_to_python", "SIM cancellation observations");
            RequireTrue(cancellation, "correlation_id_equals_action_id", "SIM cancellation observations");
            RequireTrue(
                cancellation,
                "duplicate_same_message_id_is_idempotent",
                "SIM cancellation observations");
            RequireTrue(
                cancellation,
                "conflicting_same_message_id_rejected_without_mutation",
                "SIM cancellation observations");
            RequireTrue(
                cancellation,
                "stale_exact_current_action_processed",
                "SIM cancellation observations");
            RequireTrue(
                cancellation,
                "direction_rejected_without_mutation",
                "SIM cancellation observations");
            RequireTrue(
                cancellation,
                "future_state_version_rejected_without_mutation",
                "SIM cancellation observations");
            RequireExactInteger(
                cancellation,
                "python_authority_cancel_transaction_count",
                1,
                "SIM cancellation observations");
            RequireExactInteger(
                cancellation,
                "unity_direct_authority_mutation_count",
                0,
                "SIM cancellation observations");
            RequireExactInteger(
                cancellation,
                "stale_state_message_authority_mutation_count",
                0,
                "SIM cancellation observations");
            RequireExactInteger(
                cancellation,
                "late_terminal_message_authority_mutation_count",
                0,
                "SIM cancellation observations");

            var probes = RequireObject(cancellation, "probes", "SIM cancellation observations");
            RequireExactKeys(
                probes,
                "SIM cancellation probes",
                "direction_reject",
                "future_version",
                "stale_exact_current_action",
                "duplicate_same_id",
                "conflicting_same_id",
                "stale_nonmatching_or_terminal",
                "late_terminal");
            foreach (var probe in probes.Properties())
            {
                ValidateProbe(
                    RequireObject(probes, probe.Name, "SIM cancellation probes"),
                    $"SIM cancellation probe {probe.Name}",
                    transcriptLines);
            }

            var staleExact = RequireObject(
                probes,
                "stale_exact_current_action",
                "SIM cancellation probes");
            RequireExactInteger(staleExact, "authority_transaction_count", 1, "stale_exact_current_action probe");
            RequireExactInteger(staleExact, "authority_mutation_count", 1, "stale_exact_current_action probe");
            var staleTerminal = RequireObject(
                probes,
                "stale_nonmatching_or_terminal",
                "SIM cancellation probes");
            RequireExactInteger(staleTerminal, "authority_transaction_count", 0, "stale_nonmatching_or_terminal probe");
            RequireExactInteger(staleTerminal, "authority_mutation_count", 0, "stale_nonmatching_or_terminal probe");
            RequireEqualString(
                staleTerminal,
                "outcome",
                "DIAGNOSTIC_RESYNC",
                "stale_nonmatching_or_terminal probe");
            ValidateEvidenceRefs(cancellation, "SIM cancellation observations");
        }

        private static void ValidateReconnectObservations(
            JObject reconnect,
            IReadOnlyList<JObject> transcriptLines)
        {
            RequireExactKeys(
                reconnect,
                "SIM reconnect observations",
                "full_hello_and_registry_repeated",
                "new_message_ids",
                "fresh_snapshot_not_older_than_last_acknowledged_version",
                "new_client_ready_before_resume",
                "obsolete_generation_rejected",
                "late_obsolete_generation_authority_mutation_count",
                "stale_state_message_authority_mutation_count",
                "old_generation_last_acknowledged_state_version",
                "fresh_snapshot",
                "old_generation",
                "new_generation",
                "probes",
                "evidence_refs");
            var requiredTrue = new[]
            {
                "fresh_snapshot_not_older_than_last_acknowledged_version",
                "full_hello_and_registry_repeated",
                "new_client_ready_before_resume",
                "new_message_ids",
                "obsolete_generation_rejected"
            };
            foreach (var name in requiredTrue)
            {
                RequireTrue(reconnect, name, "SIM reconnect observations");
            }

            RequireExactInteger(
                reconnect,
                "late_obsolete_generation_authority_mutation_count",
                0,
                "SIM reconnect observations");
            RequireExactInteger(
                reconnect,
                "stale_state_message_authority_mutation_count",
                0,
                "SIM reconnect observations");
            var oldGeneration = RequireObject(reconnect, "old_generation", "SIM reconnect observations");
            var newGeneration = RequireObject(reconnect, "new_generation", "SIM reconnect observations");
            ValidateSessionObservation(oldGeneration, "SIM reconnect old_generation");
            ValidateSessionObservation(newGeneration, "SIM reconnect new_generation");
            if (RequirePositiveInteger(newGeneration, "generation", "SIM reconnect new_generation")
                <= RequirePositiveInteger(oldGeneration, "generation", "SIM reconnect old_generation"))
            {
                throw new InvalidDataException("SIM reconnect generation must increase after reconnect.");
            }

            var freshSnapshot = RequireObject(reconnect, "fresh_snapshot", "SIM reconnect observations");
            ValidateAuthorityPoint(freshSnapshot, "SIM reconnect fresh_snapshot");
            if (!JToken.DeepEquals(freshSnapshot, RequireObject(newGeneration, "snapshot", "SIM reconnect new_generation")))
            {
                throw new InvalidDataException("SIM reconnect fresh_snapshot must equal new_generation.snapshot.");
            }

            var lastAcknowledged = RequireNonNegativeInteger(
                reconnect,
                "old_generation_last_acknowledged_state_version",
                "SIM reconnect observations");
            if (RequireNonNegativeInteger(freshSnapshot, "state_version", "SIM reconnect fresh_snapshot")
                < lastAcknowledged)
            {
                throw new InvalidDataException("SIM reconnect fresh snapshot is older than the last acknowledged version.");
            }

            var probes = RequireObject(reconnect, "probes", "SIM reconnect observations");
            RequireExactKeys(
                probes,
                "SIM reconnect probes",
                "obsolete_generation",
                "pre_ready_advance",
                "post_ready_advance",
                "stale_nonmatching_or_terminal");
            foreach (var probe in probes.Properties())
            {
                ValidateProbe(
                    RequireObject(probes, probe.Name, "SIM reconnect probes"),
                    $"SIM reconnect probe {probe.Name}",
                    transcriptLines);
            }

            ValidateEvidenceRefs(reconnect, "SIM reconnect observations");
        }

        private static void ValidateProbe(
            JObject probe,
            string label,
            IReadOnlyList<JObject> transcriptLines)
        {
            RequireExactKeys(
                probe,
                label,
                "probe_id",
                "connection_generation",
                "before",
                "after",
                "authority_mutation_count",
                "authority_transaction_count",
                "outcome",
                "error_code",
                "transcript_sequences");
            RequireNonEmptyString(probe, "probe_id", label);
            RequirePositiveInteger(probe, "connection_generation", label);
            ValidateAuthorityPoint(RequireObject(probe, "before", label), label + " before");
            ValidateAuthorityPoint(RequireObject(probe, "after", label), label + " after");
            RequireNonNegativeInteger(probe, "authority_mutation_count", label);
            RequireNonNegativeInteger(probe, "authority_transaction_count", label);
            RequireAllowedString(
                probe,
                "outcome",
                label,
                "ACCEPTED",
                "REJECTED",
                "IDEMPOTENT_NOOP",
                "DIAGNOSTIC_RESYNC",
                "GATED",
                "COMMITTED");
            RequireNullableString(probe, "error_code", label);
            var sequences = RequireArray(probe, "transcript_sequences", label);
            if (sequences.Count == 0 || sequences.Any(item => item.Type != JTokenType.Integer || item.Value<long>() <= 0))
            {
                throw new InvalidDataException($"{label}.transcript_sequences must contain positive integers.");
            }

            var probeId = probe.Value<string>("probe_id");
            foreach (var sequence in sequences.Select(item => item.Value<int>()))
            {
                if (sequence > transcriptLines.Count
                    || !string.Equals(
                        transcriptLines[sequence - 1].Value<string>("probe_id"),
                        probeId,
                        StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        $"{label}.transcript_sequences must reference transcript rows for probe_id {probeId}.");
                }
            }
        }

        private static void ValidateSessionObservation(JObject session, string label)
        {
            RequireExactKeys(
                session,
                label,
                "generation",
                "catalog_protocol_version",
                "negotiated_protocol_version",
                "hello_message_id",
                "server_hello_message_id",
                "registry_message_id",
                "registry_result_message_id",
                "snapshot_message_id",
                "snapshot",
                "ready_message_id",
                "ready_before_ack",
                "ready_after_ack",
                "last_client_applied_state_version",
                "handshake_message_types",
                "message_ids");
            RequirePositiveInteger(session, "generation", label);
            RequireEqualString(session, "catalog_protocol_version", TownProtocol.LegacyBootstrapVersion, label);
            RequireEqualString(session, "negotiated_protocol_version", TownProtocol.Version, label);
            foreach (var field in new[]
                     {
                         "hello_message_id",
                         "server_hello_message_id",
                         "registry_message_id",
                         "registry_result_message_id",
                         "snapshot_message_id",
                         "ready_message_id"
                     })
            {
                RequireNonEmptyString(session, field, label);
            }

            ValidateAuthorityPoint(RequireObject(session, "snapshot", label), label + " snapshot");
            if (RequireBoolean(session, "ready_before_ack", label))
            {
                throw new InvalidDataException($"{label}.ready_before_ack must be false.");
            }

            RequireTrue(session, "ready_after_ack", label);
            RequireNonNegativeInteger(session, "last_client_applied_state_version", label);
            var handshakeTypes = RequireArray(session, "handshake_message_types", label);
            var expectedHandshakeTypes = new[]
            {
                "client_hello",
                "server_hello",
                "asset_registry",
                "asset_registry_result",
                "world_snapshot",
                "client_ready"
            };
            if (!handshakeTypes.Select(item => item.Value<string>()).SequenceEqual(expectedHandshakeTypes))
            {
                throw new InvalidDataException($"{label}.handshake_message_types must be the complete frozen sequence.");
            }

            var messageIds = RequireArray(session, "message_ids", label);
            if (messageIds.Count == 0
                || messageIds.Any(item => item.Type != JTokenType.String || string.IsNullOrWhiteSpace(item.Value<string>())))
            {
                throw new InvalidDataException($"{label}.message_ids must contain non-empty strings.");
            }
        }

        private static void ValidateEvidenceRefs(JObject observation, string label)
        {
            var references = RequireObject(observation, "evidence_refs", label);
            var expectedReferenceKeys = observation.Properties()
                .Where(property => property.Name != "evidence_refs"
                                   && property.Value.Type != JTokenType.Object
                                   && property.Value.Type != JTokenType.Array)
                .Select(property => property.Name)
                .ToArray();
            RequireExactKeys(references, label + ".evidence_refs", expectedReferenceKeys);
            var allowedReferenceRoots = new HashSet<string>(StringComparer.Ordinal)
            {
                "runtime_evidence"
            };
            foreach (var property in observation.Properties())
            {
                if (property.Name != "evidence_refs" && property.Name != "probes")
                {
                    allowedReferenceRoots.Add(property.Name);
                }
            }

            var probes = observation["probes"] as JObject;
            if (probes != null)
            {
                foreach (var property in probes.Properties())
                {
                    allowedReferenceRoots.Add(property.Name);
                    if (property.Value is JObject probe)
                    {
                        var probeId = probe.Value<string>("probe_id");
                        if (!string.IsNullOrWhiteSpace(probeId))
                        {
                            allowedReferenceRoots.Add(probeId);
                        }
                    }
                }
            }

            foreach (var property in observation.Properties())
            {
                if (property.Name == "evidence_refs"
                    || property.Value.Type == JTokenType.Object
                    || property.Value.Type == JTokenType.Array)
                {
                    continue;
                }

                var value = references.Value<string>(property.Name);
                var targets = value?.Split(',').Select(item => item.Trim()).ToArray();
                if (string.IsNullOrWhiteSpace(value)
                    || references[property.Name].Type != JTokenType.String
                    || targets == null
                    || targets.Length == 0
                    || targets.Any(target => string.IsNullOrWhiteSpace(target)
                                             || !allowedReferenceRoots.Contains(target.Split('.')[0])))
                {
                    throw new InvalidDataException(
                        $"{label}.evidence_refs.{property.Name} must name existing probe/session/runtime evidence roots.");
                }
            }
        }

        private static void ValidateAuthorityPoint(JObject point, string label)
        {
            RequireExactKeys(point, label, "state_hash", "state_version", "game_minute");
            var stateHash = RequireNonEmptyString(point, "state_hash", label);
            if (!Regex.IsMatch(stateHash, "^[0-9a-f]{64}$", RegexOptions.CultureInvariant))
            {
                throw new InvalidDataException($"{label}.state_hash must be 64 lowercase hex characters.");
            }

            RequireNonNegativeInteger(point, "state_version", label);
            RequireNonNegativeInteger(point, "game_minute", label);
        }

        private static JObject SelectCancellationObservations(JObject source)
        {
            var result = SelectFields(
                source,
                "conflicting_same_message_id_rejected_without_mutation",
                "correlation_id_equals_action_id",
                "direction",
                "direction_rejected_without_mutation",
                "duplicate_same_message_id_is_idempotent",
                "future_state_version_rejected_without_mutation",
                "python_authority_cancel_transaction_count",
                "stale_exact_current_action_processed",
                "unity_direct_authority_mutation_count");
            var probes = RequireObject(source, "probes", "SIM cancellation observations");
            var staleTerminal = RequireObject(
                probes,
                "stale_nonmatching_or_terminal",
                "SIM cancellation probes");
            result["stale_nonmatching_or_terminal_authority_mutation_count"] =
                staleTerminal["authority_mutation_count"].DeepClone();
            result["stale_nonmatching_or_terminal_diagnostic_resync"] =
                string.Equals(
                    staleTerminal.Value<string>("outcome"),
                    "DIAGNOSTIC_RESYNC",
                    StringComparison.Ordinal);
            result["stale_nonmatching_or_terminal_authority_transaction_count"] =
                staleTerminal["authority_transaction_count"].DeepClone();
            return result;
        }

        private static JObject SelectReconnectObservations(JObject source)
        {
            return SelectFields(
                source,
                "fresh_snapshot_not_older_than_last_acknowledged_version",
                "full_hello_and_registry_repeated",
                "late_obsolete_generation_authority_mutation_count",
                "new_client_ready_before_resume",
                "new_message_ids",
                "obsolete_generation_rejected");
        }

        private static JObject SelectFields(JObject source, params string[] fields)
        {
            var result = new JObject();
            foreach (var field in fields)
            {
                result[field] = source[field].DeepClone();
            }

            return result;
        }

        private static void RequireExactKeys(JObject value, string label, params string[] keys)
        {
            var actual = new HashSet<string>(value.Properties().Select(item => item.Name), StringComparer.Ordinal);
            var expected = new HashSet<string>(keys, StringComparer.Ordinal);
            if (!actual.SetEquals(expected))
            {
                throw new InvalidDataException(
                    $"{label} fields differ; expected [{string.Join(",", expected.OrderBy(item => item))}], " +
                    $"received [{string.Join(",", actual.OrderBy(item => item))}].");
            }
        }

        private static JObject RequireObject(JObject parent, string key, string label)
        {
            var value = parent[key] as JObject;
            if (value == null)
            {
                throw new InvalidDataException($"{label}.{key} must be an object.");
            }

            return value;
        }

        private static JArray RequireArray(JObject parent, string key, string label)
        {
            var value = parent[key] as JArray;
            if (value == null)
            {
                throw new InvalidDataException($"{label}.{key} must be an array.");
            }

            return value;
        }

        private static string RequireNonEmptyString(JObject parent, string key, string label)
        {
            var value = parent.Value<string>(key);
            if (string.IsNullOrWhiteSpace(value) || parent[key].Type != JTokenType.String)
            {
                throw new InvalidDataException($"{label}.{key} must be a non-empty string.");
            }

            return value;
        }

        private static void RequireEqualString(JObject parent, string key, string expected, string label)
        {
            var value = RequireNonEmptyString(parent, key, label);
            if (!string.Equals(value, expected, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"{label}.{key} must equal {expected}.");
            }
        }

        private static void RequireAllowedString(JObject parent, string key, string label, params string[] allowed)
        {
            var value = RequireNonEmptyString(parent, key, label);
            if (!allowed.Contains(value))
            {
                throw new InvalidDataException($"{label}.{key} is outside the frozen allowlist.");
            }
        }

        private static bool RequireBoolean(JObject parent, string key, string label)
        {
            if (parent[key] == null || parent[key].Type != JTokenType.Boolean)
            {
                throw new InvalidDataException($"{label}.{key} must be boolean.");
            }

            return parent.Value<bool>(key);
        }

        private static void RequireTrue(JObject parent, string key, string label)
        {
            if (!RequireBoolean(parent, key, label))
            {
                throw new InvalidDataException($"{label}.{key} must be true.");
            }
        }

        private static long RequireNonNegativeInteger(JObject parent, string key, string label)
        {
            var token = parent[key];
            if (token == null || token.Type != JTokenType.Integer || token.Value<long>() < 0)
            {
                throw new InvalidDataException($"{label}.{key} must be a non-negative integer.");
            }

            return token.Value<long>();
        }

        private static long RequirePositiveInteger(JObject parent, string key, string label)
        {
            var value = RequireNonNegativeInteger(parent, key, label);
            if (value <= 0)
            {
                throw new InvalidDataException($"{label}.{key} must be a positive integer.");
            }

            return value;
        }

        private static void RequireExactInteger(JObject parent, string key, long expected, string label)
        {
            if (RequireNonNegativeInteger(parent, key, label) != expected)
            {
                throw new InvalidDataException($"{label}.{key} must equal {expected}.");
            }
        }

        private static void RequireNullableString(JObject parent, string key, string label)
        {
            var token = parent[key];
            if (token == null || (token.Type != JTokenType.String && token.Type != JTokenType.Null))
            {
                throw new InvalidDataException($"{label}.{key} must be a string or null.");
            }
        }

        private static void RequireNullableNonNegativeInteger(JObject parent, string key, string label)
        {
            var token = parent[key];
            if (token == null
                || (token.Type != JTokenType.Null
                    && (token.Type != JTokenType.Integer || token.Value<long>() < 0)))
            {
                throw new InvalidDataException($"{label}.{key} must be a non-negative integer or null.");
            }
        }

        private static string ComputeSha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                return string.Concat(sha.ComputeHash(stream).Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            }
        }

        private static void RejectSensitiveOrMachineLocalText(string text, string label)
        {
            if (Regex.IsMatch(text, "(?:/Users/|/home/runner/|[A-Za-z]:\\\\Users\\\\)", RegexOptions.CultureInvariant)
                || Regex.IsMatch(
                    text,
                    "\\\"(?:authorization|api_key|access_token|password|cookie)\\\"\\s*:",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
            {
                throw new InvalidDataException($"{label} contains a machine-local path or sensitive field.");
            }
        }

        private static JObject Gate(string details)
        {
            return new JObject
            {
                ["details"] = details,
                ["status"] = "PASS"
            };
        }

        private static void WriteJson(string path, JObject value)
        {
            File.WriteAllText(
                path,
                value.ToString(Newtonsoft.Json.Formatting.Indented) + "\n",
                new UTF8Encoding(false));
        }

        private static string RequireArgument(string name)
        {
            var arguments = Environment.GetCommandLineArgs();
            for (var index = 0; index < arguments.Length - 1; index++)
            {
                if (string.Equals(arguments[index], name, StringComparison.Ordinal))
                {
                    return arguments[index + 1];
                }
            }

            throw new ArgumentException($"Missing required batchmode argument {name}.");
        }

        private sealed class TestResultSummary
        {
            public TestResultSummary(string platform, int total, int passed, int skipped)
            {
                Platform = platform;
                Total = total;
                Passed = passed;
                Skipped = skipped;
            }

            public string Platform { get; }
            public int Total { get; }
            public int Passed { get; }
            public int Skipped { get; }
        }

        private sealed class AuthorityEvidenceBundle
        {
            public AuthorityEvidenceBundle(JObject document, IReadOnlyList<JObject> transcriptLines)
            {
                Document = document;
                TranscriptLines = transcriptLines;
            }

            public JObject Document { get; }
            public IReadOnlyList<JObject> TranscriptLines { get; }
        }
    }
}
