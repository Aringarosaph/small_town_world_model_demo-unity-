using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using STWM.AITown.Bridge;
using STWM.AITown.Semantic;
using UnityEditor;
using UnityEngine;

namespace STWM.AITown.Editor
{
    internal sealed class AssetRegistryExportDocument
    {
        [JsonProperty("schema")]
        public string Schema { get; set; } = "stwm.unity.asset-registry-export/v1";

        [JsonProperty("protocol_version")]
        public string ProtocolVersion { get; set; } = TownProtocol.Version;

        [JsonProperty("unity_editor")]
        public string UnityEditor { get; set; } = TownProtocol.UnityEditorVersion;

        [JsonProperty("registry")]
        public AssetRegistryPayload Registry { get; set; }

        [JsonProperty("issues")]
        public List<AssetValidationIssueDto> Issues { get; set; }
    }

    public static class TownAssetRegistryEditor
    {
        [MenuItem("AITown/Validate Current Scene")]
        public static void ValidateCurrentScene()
        {
            var scan = TownSceneAssetRegistry.ScanM2Fixture();
            LogIssues(scan.Issues);
            var errorCount = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.ERROR.ToString());
            var warningCount = scan.Issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString());
            EditorUtility.DisplayDialog(
                "STWM M2 scene validation",
                $"{errorCount} error(s), {warningCount} warning(s). See Console for deterministic issue codes.",
                "OK");
        }

        [MenuItem("AITown/Export Asset Registry")]
        public static void ExportAssetRegistry()
        {
            var path = EditorUtility.SaveFilePanel("Export STWM asset registry", "", "stwm-m2-asset-registry.json", "json");
            if (!string.IsNullOrWhiteSpace(path))
            {
                ExportTo(path);
                EditorUtility.RevealInFinder(path);
            }
        }

        [MenuItem("AITown/Run Bridge Diagnostics")]
        public static void RunBridgeDiagnostics()
        {
            if (Application.unityVersion != TownProtocol.UnityEditorVersion)
            {
                Debug.LogError($"[STWM] Editor mismatch: expected {TownProtocol.UnityEditorVersion}, running {Application.unityVersion}");
            }
            else
            {
                Debug.Log($"[STWM] Editor version OK: {Application.unityVersion}");
            }

            var scan = TownSceneAssetRegistry.ScanM2Fixture();
            LogIssues(scan.Issues);
            Debug.Log($"[STWM] M2 registry: {scan.Payload.Locations.Count} locations, {scan.Payload.Objects.Count} objects, {scan.Payload.NpcViews.Count} NPC view(s)");
        }

        public static void ExportAssetRegistryBatch()
        {
            var path = ReadCommandLineValue("-assetRegistryOutput");
            if (string.IsNullOrWhiteSpace(path))
            {
                throw new ArgumentException("Batch export requires -assetRegistryOutput <absolute-path>.");
            }

            ExportTo(path);
        }

        public static void ValidateM2Batch()
        {
            var scan = TownSceneAssetRegistry.ScanM2Fixture();
            LogIssues(scan.Issues);
            if (scan.HasErrors)
            {
                throw new InvalidOperationException("STWM M2 asset registry has blocking errors.");
            }
        }

        public static void ExportTo(string path)
        {
            var scan = TownSceneAssetRegistry.ScanM2Fixture();
            var document = new AssetRegistryExportDocument
            {
                Registry = scan.Payload,
                Issues = scan.Issues
            };
            var directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(directory))
            {
                Directory.CreateDirectory(directory);
            }

            File.WriteAllText(path, JsonConvert.SerializeObject(document, Formatting.Indented));
            LogIssues(scan.Issues);
            Debug.Log($"[STWM] Exported deterministic M2 asset registry to {Path.GetFullPath(path)}");
        }

        private static void LogIssues(IEnumerable<AssetValidationIssueDto> issues)
        {
            foreach (var issue in issues)
            {
                var text = $"[STWM][{issue.Severity}] {issue.Code} {issue.EntityId}: {issue.Message}";
                if (issue.Severity == AssetValidationSeverity.ERROR.ToString())
                {
                    Debug.LogError(text);
                }
                else if (issue.Severity == AssetValidationSeverity.WARNING.ToString())
                {
                    Debug.LogWarning(text);
                }
                else
                {
                    Debug.Log(text);
                }
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
