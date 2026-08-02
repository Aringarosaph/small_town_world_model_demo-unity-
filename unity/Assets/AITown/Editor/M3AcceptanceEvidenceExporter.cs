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
using UnityEngine;

namespace STWM.AITown.Editor
{
    public sealed class M3PartialTestSummary
    {
        [JsonProperty("total")]
        public int Total { get; set; }

        [JsonProperty("passed")]
        public int Passed { get; set; }

        [JsonProperty("failed")]
        public int Failed { get; set; }

        [JsonProperty("skipped")]
        public int Skipped { get; set; }

        [JsonProperty("inconclusive")]
        public int Inconclusive { get; set; }

        [JsonProperty("required_cases")]
        public List<string> RequiredCases { get; set; } = new List<string>();
    }

    /// <summary>
    /// Consumes real SIM and Unity evidence without translating it into final
    /// release facts. The QA release schema is PASS-only, so this exporter
    /// deliberately emits a separate PENDING schema until the ordered 7/30-day
    /// producer artifacts exist.
    /// </summary>
    public static class M3AcceptanceEvidenceExporter
    {
        public const string PartialSchema = "stwm.unity.m3-partial-acceptance-evidence/v1";
        public const string SimReadinessSchema = "stwm.simulation.m3-readiness-evidence/v1";
        public const string RegistryReportSchema = "stwm.unity.m3-registry-report/v1";
        public const string SemanticCoverageSchema = "stwm.unity.m3-semantic-coverage/v1";
        public const string DebugTraceSchema = "stwm.unity.m3-debug-trace/v1";
        public const string EvidenceFileName = "m3-unity-partial-acceptance-evidence.json";

        private const string ProjectName = "Small Town World Model（STWM）";
        private const string AcceptedM2Commit = "7b2618de09bd87eb49716ac40f1d0ba697f00351";
        private const string LiveCase = "Live030PythonBridgeCompletesFullRegistrySnapshotTopKAndReconnectWhenEnabled";
        private const string JointCase = "ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing";
        private const string ClearCase = "Recorded030HandshakeRebindsSnapshotThenClearsAndReleasesJointPresentation";
        private static readonly Regex CommitPattern = new Regex("^[0-9a-f]{40}$", RegexOptions.CultureInvariant);
        private static readonly Regex UnixUserRootPattern = new Regex(@"/Users/[^/\s]+", RegexOptions.CultureInvariant);
        private static readonly Regex WindowsUserRootPattern = new Regex(@"[A-Za-z]:\\Users\\[^\\\s]+", RegexOptions.CultureInvariant);
        private static readonly Regex SecretPattern = new Regex(
            "(?i)(api[_-]?key|authorization|bearer|password|secret)\\s*[:=]\\s*[\\\"']?[^\\s\\\"']{8,}",
            RegexOptions.CultureInvariant);

        public static void ExportPartialBatch()
        {
            var outputRoot = RequiredArgument("-m3OutputRoot");
            var simReadinessPath = RequiredArgument("-m3SimReadiness");
            var liveRegistryPath = RequiredArgument("-m3LiveRegistry");
            var liveDebugTracePath = RequiredArgument("-m3LiveDebugTrace");
            var editModePath = RequiredArgument("-m3EditModeResults");
            var playModePath = RequiredArgument("-m3PlayModeResults");
            var batchLogPath = RequiredArgument("-m3BatchLog");
            var sourceCommit = RequiredArgument("-m3SourceCommit");

            ExportPartial(
                outputRoot,
                simReadinessPath,
                liveRegistryPath,
                liveDebugTracePath,
                editModePath,
                playModePath,
                batchLogPath,
                sourceCommit);
        }

        public static JObject ExportPartial(
            string outputRoot,
            string simReadinessPath,
            string liveRegistryPath,
            string liveDebugTracePath,
            string editModePath,
            string playModePath,
            string batchLogPath,
            string sourceCommit)
        {
            outputRoot = RequireExternalDirectory(outputRoot);
            if (!CommitPattern.IsMatch(sourceCommit ?? string.Empty))
            {
                throw new ArgumentException("M3 partial evidence requires -m3SourceCommit as 40 lowercase hex.");
            }

            Directory.CreateDirectory(outputRoot);
            simReadinessPath = RequireExistingExternalFile(simReadinessPath);
            liveRegistryPath = RequireExistingExternalFile(liveRegistryPath);
            liveDebugTracePath = RequireExistingExternalFile(liveDebugTracePath);
            editModePath = RequireExistingExternalFile(editModePath);
            playModePath = RequireExistingExternalFile(playModePath);
            batchLogPath = RequireExistingExternalFile(batchLogPath);
            EnsureInsideBundle(outputRoot, simReadinessPath, "SIM readiness");
            EnsureInsideBundle(outputRoot, liveRegistryPath, "live registry");
            EnsureInsideBundle(outputRoot, liveDebugTracePath, "live debug trace");

            var simReadiness = JObject.Parse(File.ReadAllText(simReadinessPath));
            ValidateSimReadiness(simReadiness);
            var liveRegistry = JObject.Parse(File.ReadAllText(liveRegistryPath));
            ValidateLiveRegistry(liveRegistry);
            ValidateLiveDebugTrace(liveDebugTracePath);
            var editSummary = ValidateTestResults(editModePath, Array.Empty<string>());
            var playSummary = ValidateTestResults(playModePath, new[] { LiveCase, JointCase, ClearCase });

            M3FunctionalGrayboxBuilder.BuildAndSave();
            var manifest = M3SemanticManifestDocument.LoadDefault();
            var scan = TownSceneAssetRegistry.ScanFullV0(true, manifest);
            var routeReport = M3RouteValidator.Validate(
                TownSceneAssetRegistry.FindLocations(),
                TownSceneAssetRegistry.FindObjects());
            if (scan.HasErrors || routeReport.HasErrors)
            {
                throw new InvalidOperationException("M3 partial acceptance export is blocked by Unity registry or route errors.");
            }

            var unityDirectory = Path.Combine(outputRoot, "unity");
            Directory.CreateDirectory(unityDirectory);
            var registryReportPath = Path.Combine(unityDirectory, "registry-report.json");
            var semanticReportPath = Path.Combine(unityDirectory, "unity-semantic-coverage.json");
            var sanitizedEditPath = Path.Combine(unityDirectory, "editmode-results.xml");
            var sanitizedPlayPath = Path.Combine(unityDirectory, "playmode-results.xml");
            var sanitizedLogPath = Path.Combine(unityDirectory, "unity-batchmode.log");
            WriteJson(registryReportPath, CreateRegistryReport(scan, manifest, routeReport));
            WriteJson(semanticReportPath, CreateSemanticCoverage(scan, manifest, routeReport));
            editSummary = CopySanitizedXmlTestResults(editModePath, sanitizedEditPath, Array.Empty<string>());
            playSummary = CopySanitizedXmlTestResults(
                playModePath,
                sanitizedPlayPath,
                new[] { LiveCase, JointCase, ClearCase });
            CopySanitizedText(batchLogPath, sanitizedLogPath);

            var artifacts = new JObject
            {
                ["sim_readiness"] = Describe(outputRoot, simReadinessPath, SimReadinessSchema),
                ["full_registry"] = Describe(outputRoot, liveRegistryPath, null),
                ["registry_report"] = Describe(outputRoot, registryReportPath, RegistryReportSchema),
                ["unity_semantic_report"] = Describe(outputRoot, semanticReportPath, SemanticCoverageSchema),
                ["debug_trace"] = Describe(outputRoot, liveDebugTracePath, DebugTraceSchema),
                ["editmode_results"] = Describe(outputRoot, sanitizedEditPath, null),
                ["playmode_results"] = Describe(outputRoot, sanitizedPlayPath, null),
                ["batchmode_log"] = Describe(outputRoot, sanitizedLogPath, null)
            };
            var document = new JObject
            {
                ["schema"] = PartialSchema,
                ["project_name"] = ProjectName,
                ["status"] = "PENDING",
                ["acceptance_eligible"] = false,
                ["source_commit"] = sourceCommit,
                ["accepted_m2_commit"] = AcceptedM2Commit,
                ["catalog_protocol_version"] = "0.1.0",
                ["negotiated_protocol_version"] = TownProtocol.M3Version,
                ["unity_editor_version"] = TownProtocol.UnityEditorVersion,
                ["generated_at_utc"] = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture),
                ["gates"] = new JObject
                {
                    ["sim_authority_readiness"] = Gate("PASS", "sim_external_artifact", "Real one-day SIM authority/readiness artifact passed strict identity and bridge checks."),
                    ["protocol_0_3_live"] = Gate("PASS", "unity_client_websocket", "Production /town negotiated 0.3.0, accepted M3_FULL registry, applied snapshot, reached Ready, emitted Top-K, and completed a fresh second handshake."),
                    ["full_registry"] = Gate("PASS", "live_asset_registry_envelope", "The exact asset_registry envelope accepted by the production server is retained in this bundle."),
                    ["structured_presentation"] = Gate("PASS", "unity_playmode", "Structured participants, stable JointAction claims, explicit clear, active snapshot rebind, and authoritative Top-K fixtures passed."),
                    ["unity_semantics"] = Gate("PASS", "unity_scene_scan", "The authoritative YAML-backed 10/8/15/105 semantic and route scan passed."),
                    ["editmode"] = Gate("PASS", "unity_test_runner", $"{editSummary.Passed}/{editSummary.Total} passed; zero failed/skipped/inconclusive."),
                    ["playmode_live"] = Gate("PASS", "unity_test_runner", $"{playSummary.Passed}/{playSummary.Total} passed; zero failed/skipped/inconclusive; live reconnect case passed."),
                    ["soak_7_day"] = Gate("PENDING", "sim_release_slow", "The ordered five-seed 7-day slow-soak artifact was not supplied."),
                    ["soak_30_day"] = Gate("PENDING", "sim_release_slow", "The ordered three-seed 30-day slow-soak artifact was not supplied."),
                    ["final_release"] = Gate("PENDING", "orchestrator", "PASS-only stwm.qa.m3-acceptance-evidence/v1 cannot be emitted before the complete producer artifact set exists.")
                },
                ["unity_test_summary"] = JObject.FromObject(new { editmode = editSummary, playmode = playSummary }),
                ["artifacts"] = artifacts,
                ["pending_reasons"] = new JArray(
                    "M3_7_DAY_SLOW_SOAK_NOT_SUPPLIED",
                    "M3_30_DAY_SLOW_SOAK_NOT_SUPPLIED",
                    "FINAL_RELEASE_PRODUCER_ARTIFACT_SET_INCOMPLETE")
            };
            var evidencePath = Path.Combine(outputRoot, EvidenceFileName);
            WriteJson(evidencePath, document);
            Debug.Log($"[STWM] Exported truthful M3 partial acceptance evidence (PENDING, acceptance_eligible=false) to {evidencePath}");
            return document;
        }

        public static void ValidateSimReadiness(JObject document)
        {
            RequireExactKeys(document, "SIM readiness",
                "schema", "project_name", "generated_at_utc", "passed", "scenario", "protocol", "runs",
                "determinism", "checkpoint_resume", "replay", "economy", "bridge", "cli_contract", "soak_plan");
            RequireString(document, "schema", SimReadinessSchema, "SIM readiness");
            RequireString(document, "project_name", ProjectName, "SIM readiness");
            RequireTrue(document, "passed", "SIM readiness");

            var scenario = RequireObject(document, "scenario", "SIM readiness");
            RequireExactKeys(scenario, "SIM scenario", "days", "enabled_agent_ids", "seed", "semantic_profile");
            RequireInteger(scenario, "days", 1, "SIM scenario");
            RequireInteger(scenario, "seed", 12345, "SIM scenario");
            RequireString(scenario, "semantic_profile", "M3_FULL", "SIM scenario");
            RequireAgentSet(scenario["enabled_agent_ids"] as JArray, "SIM scenario enabled_agent_ids");

            var protocol = RequireObject(document, "protocol", "SIM readiness");
            RequireExactKeys(protocol, "SIM protocol", "active_negotiated_protocol_version", "catalog_protocol_version", "checkpoint_schema");
            RequireString(protocol, "active_negotiated_protocol_version", TownProtocol.M3Version, "SIM protocol");
            RequireString(protocol, "catalog_protocol_version", "0.1.0", "SIM protocol");
            RequireString(protocol, "checkpoint_schema", "stwm.simulation.m3-authority-checkpoint/v1", "SIM protocol");

            var determinism = RequireObject(document, "determinism", "SIM readiness");
            RequireTrue(determinism, "all_hashes_match", "SIM determinism");
            var replay = RequireObject(document, "replay", "SIM readiness");
            RequireTrue(replay, "match", "SIM replay");
            var economy = RequireObject(document, "economy", "SIM readiness");
            RequireTrue(economy, "all_equations_match", "SIM economy");
            RequireTrue(economy, "resources_nonnegative", "SIM economy");
            RequireTrue(economy, "settlement_keys_unique", "SIM economy");

            var bridge = RequireObject(document, "bridge", "SIM readiness");
            RequireExactKeys(bridge, "SIM bridge",
                "catalog_protocol_version", "client_ready_gate_observed", "first_generation_message_counts",
                "first_generation_ready", "fresh_snapshot_covers_all_active_actions",
                "fresh_snapshot_not_older_than_prior_generation", "fresh_snapshot_state_version",
                "negotiated_protocol_version", "new_generation_ready_before_ack", "obsolete_generation_rejected",
                "reconnect_generation", "semantic_profile", "sessions");
            RequireString(bridge, "catalog_protocol_version", "0.1.0", "SIM bridge");
            RequireString(bridge, "negotiated_protocol_version", TownProtocol.M3Version, "SIM bridge");
            RequireString(bridge, "semantic_profile", "M3_FULL", "SIM bridge");
            RequireTrue(bridge, "first_generation_ready", "SIM bridge");
            RequireTrue(bridge, "client_ready_gate_observed", "SIM bridge");
            RequireTrue(bridge, "fresh_snapshot_covers_all_active_actions", "SIM bridge");
            RequireTrue(bridge, "fresh_snapshot_not_older_than_prior_generation", "SIM bridge");
            RequireTrue(bridge, "obsolete_generation_rejected", "SIM bridge");
            if (bridge.Value<bool?>("new_generation_ready_before_ack") != false)
            {
                throw new InvalidDataException("SIM bridge must prove the reconnect generation remained gated before client_ready.");
            }
            RequireInteger(bridge, "reconnect_generation", 2, "SIM bridge");
            var messageCounts = RequireObject(bridge, "first_generation_message_counts", "SIM bridge");
            foreach (var type in new[] { "action_started", "agent_state_delta", "debug_decision_trace" })
            {
                if (messageCounts.Value<int?>(type).GetValueOrDefault() <= 0)
                {
                    throw new InvalidDataException($"SIM bridge emitted no {type} message.");
                }
            }

            var soak = RequireObject(document, "soak_plan", "SIM readiness");
            RequireExactKeys(soak, "SIM soak plan",
                "fixed_30_day_seeds", "fixed_7_day_seeds", "full_slow_soak_executed", "reason");
            if (soak.Value<bool?>("full_slow_soak_executed") != false)
            {
                throw new InvalidDataException("This partial exporter only accepts the current readiness artifact with slow soak explicitly not executed.");
            }
            RequireIntegerArray(soak["fixed_7_day_seeds"] as JArray, new[] { 12345, 24680, 97531, 314159, 271828 }, "7-day seeds");
            RequireIntegerArray(soak["fixed_30_day_seeds"] as JArray, new[] { 12345, 24680, 97531 }, "30-day seeds");
        }

        public static M3PartialTestSummary ValidateTestResults(string path, IEnumerable<string> requiredCases)
        {
            var document = new XmlDocument();
            document.Load(path);
            var root = document.DocumentElement ?? throw new InvalidDataException("Unity test XML has no root element.");
            var summary = new M3PartialTestSummary
            {
                Total = ReadIntAttribute(root, "total"),
                Passed = ReadIntAttribute(root, "passed"),
                Failed = ReadIntAttribute(root, "failed"),
                Skipped = ReadIntAttribute(root, "skipped"),
                Inconclusive = ReadIntAttribute(root, "inconclusive")
            };
            if (summary.Total <= 0 || summary.Passed != summary.Total || summary.Failed != 0
                || summary.Skipped != 0 || summary.Inconclusive != 0
                || !string.Equals(root.GetAttribute("result"), "Passed", StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Unity test XML is not zero-skip PASS: total={summary.Total}, passed={summary.Passed}, failed={summary.Failed}, skipped={summary.Skipped}, inconclusive={summary.Inconclusive}.");
            }

            var cases = document.SelectNodes("//test-case")?.Cast<XmlElement>().ToArray() ?? Array.Empty<XmlElement>();
            foreach (var requiredCase in requiredCases ?? Array.Empty<string>())
            {
                var match = cases.FirstOrDefault(item =>
                    (item.GetAttribute("name") ?? string.Empty).Contains(requiredCase)
                    || (item.GetAttribute("fullname") ?? string.Empty).Contains(requiredCase));
                if (match == null || !string.Equals(match.GetAttribute("result"), "Passed", StringComparison.Ordinal))
                {
                    throw new InvalidDataException($"Unity PlayMode evidence is missing required passed case {requiredCase}.");
                }
                summary.RequiredCases.Add(requiredCase);
            }
            return summary;
        }

        private static void ValidateLiveRegistry(JObject registry)
        {
            RequireString(registry, "protocol_version", TownProtocol.M3Version, "live registry");
            RequireString(registry, "message_type", "asset_registry", "live registry");
            if (string.IsNullOrWhiteSpace(registry.Value<string>("message_id"))
                || string.IsNullOrWhiteSpace(registry.Value<string>("correlation_id")))
            {
                throw new InvalidDataException("Live registry is missing message/correlation audit identity.");
            }
            var payload = RequireObject(registry, "payload", "live registry");
            if ((payload["locations"] as JArray)?.Count != 8
                || (payload["npc_views"] as JArray)?.Count != 10
                || (payload["mapped_animation_semantics"] as JArray)?.Count != 14)
            {
                throw new InvalidDataException("Live M3_FULL registry has incomplete location, NPC, or animation coverage.");
            }
            var objects = payload["objects"] as JArray;
            if (objects == null
                || objects.Children<JObject>().Select(item => item.Value<string>("object_type")).Distinct(StringComparer.Ordinal).Count() != 15
                || objects.Children<JObject>().Sum(item => (item["interaction_slots"] as JArray)?.Count ?? 0) != 105)
            {
                throw new InvalidDataException("Live M3_FULL registry has incomplete object type or slot coverage.");
            }
        }

        private static void ValidateLiveDebugTrace(string path)
        {
            var lines = File.ReadAllLines(path).Where(item => !string.IsNullOrWhiteSpace(item)).ToArray();
            if (lines.Length == 0)
            {
                throw new InvalidDataException("Live debug trace JSONL is empty.");
            }
            foreach (var line in lines)
            {
                var record = JObject.Parse(line);
                RequireString(record, "schema", DebugTraceSchema, "live debug trace");
                RequireString(record, "evidence_source", "live_python_bridge", "live debug trace");
                var envelope = RequireObject(record, "envelope", "live debug trace");
                RequireString(envelope, "protocol_version", TownProtocol.M3Version, "live debug trace envelope");
                RequireString(envelope, "message_type", "debug_decision_trace", "live debug trace envelope");
                var payload = RequireObject(envelope, "payload", "live debug trace envelope");
                if ((payload["candidates"] as JArray)?.Count <= 0
                    || string.IsNullOrWhiteSpace(payload.Value<string>("selected_candidate_id")))
                {
                    throw new InvalidDataException("Live debug trace omits authoritative Top-K rows or selection.");
                }
            }
        }

        private static JObject CreateRegistryReport(
            TownAssetRegistryScan scan,
            M3SemanticManifestDocument manifest,
            M3RouteValidationReport routeReport)
        {
            return new JObject
            {
                ["schema"] = RegistryReportSchema,
                ["status"] = "PASS",
                ["evidence_source"] = "unity_scene_scan",
                ["profile"] = scan.Profile,
                ["manifest_schema"] = manifest.Schema,
                ["manifest_source"] = M3SemanticManifestDocument.RepositoryRelativePath,
                ["counts"] = new JObject
                {
                    ["locations"] = scan.Payload.Locations.Count,
                    ["npc_views"] = scan.Payload.NpcViews.Count,
                    ["objects"] = scan.Payload.Objects.Count,
                    ["object_types"] = scan.Payload.Objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count(),
                    ["interaction_slots"] = scan.Payload.Objects.Sum(item => item.InteractionSlots.Count),
                    ["animation_semantics"] = scan.Payload.MappedAnimationSemantics.Count,
                    ["routes"] = routeReport.RouteCount
                },
                ["blocking_issue_count"] = scan.Issues.Count(item => item.Severity == "ERROR") + routeReport.Issues.Count(item => item.Severity == "ERROR"),
                ["issues"] = JArray.FromObject(scan.Issues)
            };
        }

        private static JObject CreateSemanticCoverage(
            TownAssetRegistryScan scan,
            M3SemanticManifestDocument manifest,
            M3RouteValidationReport routeReport)
        {
            return new JObject
            {
                ["schema"] = SemanticCoverageSchema,
                ["status"] = "PASS",
                ["evidence_source"] = "unity_scene_scan_and_playmode",
                ["profile"] = "M3_FULL",
                ["npc_views"] = scan.Payload.NpcViews.Count,
                ["locations"] = scan.Payload.Locations.Count,
                ["object_types"] = scan.Payload.Objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count(),
                ["interaction_slots"] = scan.Payload.Objects.Sum(item => item.InteractionSlots.Count),
                ["required_animation_semantics"] = JArray.FromObject(manifest.RequiredAnimationSemantics),
                ["mapped_animation_semantics"] = JArray.FromObject(scan.Payload.MappedAnimationSemantics),
                ["required_prop_semantics"] = JArray.FromObject(manifest.RequiredPropSemantics),
                ["facing_behavior_ids"] = JArray.FromObject(manifest.FacingBehaviorIds),
                ["route_count"] = routeReport.RouteCount,
                ["route_errors"] = routeReport.Issues.Count(item => item.Severity == "ERROR"),
                ["structured_joint_clear_reconnect_covered_by_playmode"] = true
            };
        }

        private static JObject Gate(string status, string evidenceSource, string details)
        {
            return new JObject
            {
                ["status"] = status,
                ["evidence_source"] = evidenceSource,
                ["details"] = details
            };
        }

        private static JObject Describe(string outputRoot, string path, string schema)
        {
            var fullPath = Path.GetFullPath(path);
            EnsureInsideBundle(outputRoot, fullPath, "artifact");
            var bytes = File.ReadAllBytes(fullPath);
            string digest;
            using (var sha = SHA256.Create())
            {
                digest = BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", string.Empty).ToLowerInvariant();
            }
            var relative = fullPath.Substring(outputRoot.TrimEnd(Path.DirectorySeparatorChar).Length)
                .TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                .Replace(Path.DirectorySeparatorChar, '/');
            return new JObject
            {
                ["path"] = relative,
                ["sha256"] = digest,
                ["bytes"] = bytes.Length,
                ["redacted"] = true,
                ["schema"] = schema == null ? JValue.CreateNull() : new JValue(schema)
            };
        }

        public static M3PartialTestSummary CopySanitizedXmlTestResults(
            string source,
            string destination,
            IEnumerable<string> requiredCases)
        {
            var required = (requiredCases ?? Array.Empty<string>()).ToArray();
            var sourceSummary = ValidateTestResults(source, required);
            var document = new XmlDocument { PreserveWhitespace = true };
            document.Load(source);
            SanitizeXmlNode(document);
            var settings = new XmlWriterSettings
            {
                Encoding = new UTF8Encoding(false),
                Indent = false,
                NewLineHandling = NewLineHandling.None
            };
            using (var writer = XmlWriter.Create(destination, settings))
            {
                document.Save(writer);
            }

            var sanitizedText = File.ReadAllText(destination);
            EnsureSanitizedText(sanitizedText, destination);
            var sanitizedSummary = ValidateTestResults(destination, required);
            if (sourceSummary.Total != sanitizedSummary.Total
                || sourceSummary.Passed != sanitizedSummary.Passed
                || sourceSummary.Failed != sanitizedSummary.Failed
                || sourceSummary.Skipped != sanitizedSummary.Skipped
                || sourceSummary.Inconclusive != sanitizedSummary.Inconclusive
                || !sourceSummary.RequiredCases.SequenceEqual(sanitizedSummary.RequiredCases))
            {
                throw new InvalidDataException("Sanitized Unity XML changed test results or required-case evidence.");
            }
            return sanitizedSummary;
        }

        private static void SanitizeXmlNode(XmlNode node)
        {
            if (node.Attributes != null)
            {
                foreach (XmlAttribute attribute in node.Attributes)
                {
                    attribute.Value = SanitizeEvidenceText(attribute.Value);
                }
            }
            if (node.NodeType == XmlNodeType.Text || node.NodeType == XmlNodeType.CDATA)
            {
                node.Value = SanitizeEvidenceText(node.Value ?? string.Empty);
            }
            foreach (XmlNode child in node.ChildNodes)
            {
                SanitizeXmlNode(child);
            }
        }

        private static void CopySanitizedText(string source, string destination)
        {
            var text = SanitizeEvidenceText(File.ReadAllText(source));
            EnsureSanitizedText(text, source);
            File.WriteAllText(destination, text);
        }

        private static string SanitizeEvidenceText(string text)
        {
            var repositoryRoot = RepositoryRoot();
            text = text.Replace(repositoryRoot, "REPOSITORY_ROOT");
            var userHome = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrEmpty(userHome))
            {
                text = text.Replace(userHome, "USER_HOME");
            }
            text = UnixUserRootPattern.Replace(text, "USER_HOME");
            text = WindowsUserRootPattern.Replace(text, "USER_HOME");
            return text;
        }

        private static void EnsureSanitizedText(string text, string source)
        {
            if (text.Contains("/Users/") || text.Contains("/home/runner/") || SecretPattern.IsMatch(text))
            {
                throw new InvalidDataException($"Sanitization did not remove machine-local or sensitive text from {source}.");
            }
        }

        private static void WriteJson(string path, JToken document)
        {
            File.WriteAllText(path, document.ToString(Newtonsoft.Json.Formatting.Indented) + Environment.NewLine);
        }

        private static string RequiredArgument(string name)
        {
            var arguments = Environment.GetCommandLineArgs();
            for (var index = 0; index < arguments.Length - 1; index++)
            {
                if (arguments[index] == name)
                {
                    return arguments[index + 1];
                }
            }
            throw new ArgumentException($"M3 partial acceptance export requires {name} <value>.");
        }

        private static string RequireExternalDirectory(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !Path.IsPathRooted(path))
            {
                throw new ArgumentException("M3 evidence output must be an absolute external directory.");
            }
            var fullPath = Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            EnsureOutsideRepository(fullPath);
            return fullPath;
        }

        private static string RequireExistingExternalFile(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !Path.IsPathRooted(path))
            {
                throw new ArgumentException("M3 evidence inputs must be absolute external file paths.");
            }
            var fullPath = Path.GetFullPath(path);
            EnsureOutsideRepository(fullPath);
            if (!File.Exists(fullPath))
            {
                throw new FileNotFoundException("M3 evidence input does not exist.", fullPath);
            }
            return fullPath;
        }

        private static void EnsureOutsideRepository(string path)
        {
            var root = RepositoryRoot();
            if (string.Equals(path, root, StringComparison.Ordinal)
                || path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                throw new ArgumentException("M3 evidence and inputs must remain outside the repository tree.");
            }
        }

        private static void EnsureInsideBundle(string outputRoot, string path, string label)
        {
            var root = Path.GetFullPath(outputRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var candidate = Path.GetFullPath(path);
            if (!candidate.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                throw new ArgumentException($"{label} must remain inside the external M3 evidence bundle so references cannot dangle.");
            }
        }

        private static string RepositoryRoot()
        {
            return Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."))
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }

        private static JObject RequireObject(JObject owner, string key, string label)
        {
            return owner[key] as JObject ?? throw new InvalidDataException($"{label}.{key} must be an object.");
        }

        private static void RequireExactKeys(JObject value, string label, params string[] expected)
        {
            var actual = new HashSet<string>(value.Properties().Select(item => item.Name), StringComparer.Ordinal);
            if (!actual.SetEquals(expected))
            {
                throw new InvalidDataException($"{label} keys differ: {string.Join(",", actual.OrderBy(item => item))}.");
            }
        }

        private static void RequireString(JObject owner, string key, string expected, string label)
        {
            if (!string.Equals(owner.Value<string>(key), expected, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"{label}.{key} must equal {expected}.");
            }
        }

        private static void RequireTrue(JObject owner, string key, string label)
        {
            if (owner.Value<bool?>(key) != true)
            {
                throw new InvalidDataException($"{label}.{key} must be true.");
            }
        }

        private static void RequireInteger(JObject owner, string key, int expected, string label)
        {
            if (owner.Value<int?>(key) != expected)
            {
                throw new InvalidDataException($"{label}.{key} must equal {expected}.");
            }
        }

        private static void RequireIntegerArray(JArray value, int[] expected, string label)
        {
            if (value == null || !value.Values<int>().SequenceEqual(expected))
            {
                throw new InvalidDataException($"{label} differ from the frozen release seeds.");
            }
        }

        private static void RequireAgentSet(JArray value, string label)
        {
            var expected = Enumerable.Range(1, 10).Select(index => $"npc_{index:00}").ToArray();
            if (value == null || !value.Values<string>().SequenceEqual(expected))
            {
                throw new InvalidDataException($"{label} must contain npc_01 through npc_10 in order.");
            }
        }

        private static int ReadIntAttribute(XmlElement element, string name)
        {
            if (!int.TryParse(element.GetAttribute(name), NumberStyles.None, CultureInfo.InvariantCulture, out var value))
            {
                throw new InvalidDataException($"Unity test XML root has no integer {name} attribute.");
            }
            return value;
        }
    }
}
