using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using STWM.AITown.Bridge;
using STWM.AITown.Semantic;
using UnityEngine;

namespace STWM.AITown.Editor
{
    public class M3EvidenceGate
    {
        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("evidence_source")]
        public string EvidenceSource { get; set; }

        [JsonProperty("detail")]
        public string Detail { get; set; }
    }

    public sealed class M3LocalFixtureEvidence : M3EvidenceGate
    {
        [JsonProperty("location_count")]
        public int LocationCount { get; set; }

        [JsonProperty("npc_view_count")]
        public int NpcViewCount { get; set; }

        [JsonProperty("object_count")]
        public int ObjectCount { get; set; }

        [JsonProperty("object_type_count")]
        public int ObjectTypeCount { get; set; }

        [JsonProperty("slot_count")]
        public int SlotCount { get; set; }

        [JsonProperty("route_count")]
        public int RouteCount { get; set; }
    }

    public sealed class M3ReadinessFrameworkDocument
    {
        [JsonProperty("schema")]
        public string Schema { get; set; } = "stwm.unity.m3-readiness-framework/v1";

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("acceptance_eligible")]
        public bool AcceptanceEligible { get; set; }

        [JsonProperty("project_name")]
        public string ProjectName { get; set; } = "Small Town World Model";

        [JsonProperty("baseline_commit")]
        public string BaselineCommit { get; set; } = "2a51615";

        [JsonProperty("unity_editor_version")]
        public string UnityEditorVersion { get; set; } = TownProtocol.UnityEditorVersion;

        [JsonProperty("generated_at_utc")]
        public string GeneratedAtUtc { get; set; }

        [JsonProperty("manifest_schema")]
        public string ManifestSchema { get; set; }

        [JsonProperty("shared_contract_manifest_status")]
        public string SharedContractManifestStatus { get; set; }

        [JsonProperty("local_fixture")]
        public M3LocalFixtureEvidence LocalFixture { get; set; }

        [JsonProperty("protocol_0_3")]
        public M3EvidenceGate Protocol030 { get; set; }

        [JsonProperty("sim_authority")]
        public M3EvidenceGate SimAuthority { get; set; }

        [JsonProperty("editmode_results")]
        public M3EvidenceGate EditModeResults { get; set; }

        [JsonProperty("playmode_results")]
        public M3EvidenceGate PlayModeResults { get; set; }

        [JsonProperty("artifacts")]
        public Dictionary<string, string> Artifacts { get; set; } = new Dictionary<string, string>();

        [JsonProperty("pending_reasons")]
        public List<string> PendingReasons { get; set; } = new List<string>();
    }

    /// <summary>
    /// Produces a deliberately non-acceptance M3 framework bundle until real
    /// protocol 0.3, SIM authority, and zero-skipped test inputs exist.
    /// </summary>
    public static class M3ReadinessEvidenceExporter
    {
        public const string EvidenceFileName = "m3-unity-readiness-framework.json";
        public const string RegistryFileName = "m3-local-registry.json";

        public static void ExportPendingBatch()
        {
            var outputRoot = ReadCommandLineValue("-m3OutputRoot");
            if (string.IsNullOrWhiteSpace(outputRoot) || !Path.IsPathRooted(outputRoot))
            {
                throw new ArgumentException("M3 framework export requires -m3OutputRoot <absolute-external-directory>.");
            }

            outputRoot = Path.GetFullPath(outputRoot);
            EnsureExternalPath(outputRoot);
            Directory.CreateDirectory(outputRoot);
            M3FunctionalGrayboxBuilder.BuildAndSave();
            var manifest = M3SemanticManifestDocument.LoadDefault();
            var scan = TownSceneAssetRegistry.ScanFullV0(true, manifest);
            var routeReport = M3RouteValidator.Validate(
                TownSceneAssetRegistry.FindLocations(),
                TownSceneAssetRegistry.FindObjects());
            var document = CreateFrameworkDocument(scan, manifest, routeReport);

            TownAssetRegistryEditor.ExportM3To(Path.Combine(outputRoot, RegistryFileName));
            document.Artifacts["local_registry"] = RegistryFileName;
            var evidencePath = Path.Combine(outputRoot, EvidenceFileName);
            File.WriteAllText(evidencePath, JsonConvert.SerializeObject(document, Formatting.Indented));
            Debug.Log($"[STWM] Exported M3 readiness framework ({document.Status}, never acceptance PASS) to {evidencePath}");
            if (scan.HasErrors)
            {
                throw new InvalidOperationException("M3 readiness framework contains blocking Unity-local errors.");
            }
        }

        public static M3ReadinessFrameworkDocument CreateFrameworkDocument(
            TownAssetRegistryScan scan,
            M3SemanticManifestDocument manifest,
            M3RouteValidationReport routeReport)
        {
            if (scan == null || manifest == null || routeReport == null)
            {
                throw new ArgumentNullException("M3 readiness framework inputs cannot be null.");
            }

            var localShapeValid = scan.Payload != null
                                  && scan.Payload.Locations.Count == 8
                                  && scan.Payload.NpcViews.Count == 10
                                  && scan.Payload.Objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count() == 15
                                  && scan.Payload.Objects.Sum(item => item.InteractionSlots.Count) == 105
                                  && routeReport.EntranceCount == 8
                                  && routeReport.SlotCount == 105
                                  && routeReport.RouteCount == 840;
            var localStatus = scan.HasErrors || routeReport.HasErrors || !localShapeValid ? "FAIL" : "PASS";
            return new M3ReadinessFrameworkDocument
            {
                Status = localStatus == "FAIL" ? "FAIL" : "PENDING",
                AcceptanceEligible = false,
                GeneratedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"),
                ManifestSchema = manifest.Schema,
                SharedContractManifestStatus = manifest.SharedContractManifestStatus,
                LocalFixture = new M3LocalFixtureEvidence
                {
                    Status = localStatus,
                    EvidenceSource = "unity_local_scan",
                    Detail = localStatus == "PASS"
                        ? "Unity-owned semantic components, capacities, and baked route matrix passed."
                        : "Unity-owned strict scan or route matrix failed.",
                    LocationCount = scan.Payload.Locations.Count,
                    NpcViewCount = scan.Payload.NpcViews.Count,
                    ObjectCount = scan.Payload.Objects.Count,
                    ObjectTypeCount = scan.Payload.Objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count(),
                    SlotCount = scan.Payload.Objects.Sum(item => item.InteractionSlots.Count),
                    RouteCount = routeReport.RouteCount
                },
                Protocol030 = Pending("contracts_external", "Protocol 0.3 DTO/schema/live smoke has not been supplied to this increment."),
                SimAuthority = Pending("sim_external", "Real M3 SIM authority evidence/transcript has not been supplied."),
                EditModeResults = Pending("unity_test_runner", "Zero-skipped final EditMode XML is not an input to the framework exporter yet."),
                PlayModeResults = Pending("unity_test_runner", "Zero-skipped final PlayMode/live 0.3 XML is not an input to the framework exporter yet."),
                PendingReasons = new List<string>
                {
                    "CONTRACTS_0_3_NOT_INTEGRATED",
                    "SIM_M3_AUTHORITY_EVIDENCE_NOT_INTEGRATED",
                    "FINAL_ZERO_SKIPPED_TEST_EVIDENCE_NOT_INTEGRATED"
                }
            };
        }

        private static M3EvidenceGate Pending(string source, string detail)
        {
            return new M3EvidenceGate
            {
                Status = "PENDING",
                EvidenceSource = source,
                Detail = detail
            };
        }

        private static void EnsureExternalPath(string outputRoot)
        {
            var repositoryRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."))
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var candidate = outputRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (string.Equals(candidate, repositoryRoot, StringComparison.Ordinal)
                || candidate.StartsWith(repositoryRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                throw new ArgumentException("M3 evidence output must be outside the repository tree.");
            }
        }

        private static string ReadCommandLineValue(string name)
        {
            var arguments = Environment.GetCommandLineArgs();
            for (var index = 0; index < arguments.Length - 1; index++)
            {
                if (arguments[index] == name)
                {
                    return arguments[index + 1];
                }
            }

            return null;
        }
    }
}
