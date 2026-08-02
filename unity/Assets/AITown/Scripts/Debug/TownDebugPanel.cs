using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Bridge;
using UnityEngine;

namespace STWM.AITown.Debugging
{
    [DisallowMultipleComponent]
    public sealed class TownDebugPanel : MonoBehaviour
    {
        [SerializeField] private bool visible = true;
        [SerializeField] private Rect panelRect = new Rect(12f, 12f, 520f, 430f);
        [SerializeField] private TownBridgeClient bridgeClient;

        private readonly Queue<string> recentErrors = new Queue<string>();
        private readonly Queue<string> recentInfo = new Queue<string>();
        private readonly List<AssetValidationIssueDto> localRegistryIssues = new List<AssetValidationIssueDto>();
        private readonly List<AssetValidationIssueDto> serverRegistryIssues = new List<AssetValidationIssueDto>();

        private string connectionState = "Disconnected";
        private long gameMinute;
        private float timeScale;
        private bool paused;
        private string modelVersion = "none";
        private long snapshotStateVersion;
        private string selectedAgentId = "npc_01";
        private string behaviorId = "none";
        private string actionPhase = "none";
        private Vector2 scroll;

        public IReadOnlyCollection<string> RecentErrors => recentErrors;
        public string ConnectionState => connectionState;

        public void BindBridge(TownBridgeClient bridge)
        {
            bridgeClient = bridge;
        }

        public void SetConnectionState(string value)
        {
            connectionState = value;
        }

        public void SetClock(long minute, float scale, bool isPaused)
        {
            gameMinute = minute;
            timeScale = scale;
            paused = isPaused;
        }

        public void SetSnapshot(long minute, string model, long stateVersion)
        {
            gameMinute = minute;
            modelVersion = model;
            snapshotStateVersion = stateVersion;
        }

        public void SetNpcAction(string agentId, string behavior, string phase)
        {
            selectedAgentId = agentId;
            behaviorId = string.IsNullOrEmpty(behavior) ? "none" : behavior;
            actionPhase = string.IsNullOrEmpty(phase) ? "none" : phase;
        }

        public void SetRegistryIssues(IEnumerable<AssetValidationIssueDto> issues)
        {
            localRegistryIssues.Clear();
            localRegistryIssues.AddRange(issues ?? Enumerable.Empty<AssetValidationIssueDto>());
        }

        public void SetServerRegistryIssues(IEnumerable<AssetValidationIssueDto> issues)
        {
            serverRegistryIssues.Clear();
            serverRegistryIssues.AddRange(issues ?? Enumerable.Empty<AssetValidationIssueDto>());
        }

        public void RecordError(string error)
        {
            EnqueueBounded(recentErrors, error, 8);
        }

        public void RecordInfo(string info)
        {
            EnqueueBounded(recentInfo, info, 8);
        }

        private void OnGUI()
        {
            if (!visible)
            {
                return;
            }

            panelRect = GUILayout.Window(GetInstanceID(), panelRect, DrawWindow, "STWM Town Debug (presentation only)");
        }

        private void DrawWindow(int windowId)
        {
            scroll = GUILayout.BeginScrollView(scroll);
            GUILayout.Label($"Connection: {connectionState}");
            GUILayout.Label($"Clock: minute {gameMinute} | scale {timeScale:0.#}x | paused {paused}");
            DrawTimeControls();
            GUILayout.Label($"Snapshot: v{snapshotStateVersion} | model {modelVersion}");
            GUILayout.Label($"NPC: {selectedAgentId} | behavior {behaviorId} | phase {actionPhase}");
            GUILayout.Space(6f);
            DrawIssues("Local registry", localRegistryIssues);
            DrawIssues("Server registry", serverRegistryIssues);
            GUILayout.Space(6f);
            GUILayout.Label("Recent errors:");
            foreach (var error in recentErrors.Reverse())
            {
                GUILayout.Label($"• {error}");
            }

            GUILayout.Label("Recent info:");
            foreach (var info in recentInfo.Reverse())
            {
                GUILayout.Label($"• {info}");
            }

            GUILayout.EndScrollView();
            GUI.DragWindow(new Rect(0f, 0f, 10000f, 24f));
        }

        private void DrawTimeControls()
        {
            var previousEnabled = GUI.enabled;
            GUI.enabled = bridgeClient != null && bridgeClient.IsReady;
            GUILayout.BeginHorizontal();
            GUILayout.Label("Time request:", GUILayout.Width(86f));
            DrawTimeScaleButton("0x", 0f);
            DrawTimeScaleButton("1x", 1f);
            DrawTimeScaleButton("2x", 2f);
            DrawTimeScaleButton("4x", 4f);
            if (GUILayout.Button(paused ? "Resume" : "Pause", GUILayout.Width(68f)))
            {
                bridgeClient.RequestPause(!paused);
            }

            GUILayout.EndHorizontal();
            GUI.enabled = previousEnabled;
        }

        private void DrawTimeScaleButton(string label, float requestedScale)
        {
            if (GUILayout.Button(label, GUILayout.Width(40f)))
            {
                bridgeClient.RequestTimeScale(requestedScale);
            }
        }

        private static void DrawIssues(string title, IReadOnlyCollection<AssetValidationIssueDto> issues)
        {
            var errors = issues.Count(item => item.Severity == AssetValidationSeverity.ERROR.ToString());
            var warnings = issues.Count(item => item.Severity == AssetValidationSeverity.WARNING.ToString());
            GUILayout.Label($"{title}: {errors} error(s), {warnings} warning(s)");
            foreach (var issue in issues.Take(6))
            {
                GUILayout.Label($"• [{issue.Severity}] {issue.Code}: {issue.EntityId}");
            }
        }

        private static void EnqueueBounded(Queue<string> queue, string value, int capacity)
        {
            queue.Enqueue(value);
            while (queue.Count > capacity)
            {
                queue.Dequeue();
            }
        }
    }
}
