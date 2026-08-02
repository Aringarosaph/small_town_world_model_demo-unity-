using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using STWM.AITown.Bridge;
using UnityEngine;

namespace STWM.AITown.Debugging
{
    public sealed class TownNpcDebugSurface
    {
        public string AgentId { get; set; }
        public string AuthorityLocationId { get; set; } = "pending";
        public string HouseholdId { get; set; } = "pending";
        public string HouseholdResources { get; set; } = "pending";
        public string Needs { get; set; } = "pending";
        public string Mood { get; set; } = "pending";
        public string Relationships { get; set; } = "pending";
        public string KnownEvents { get; set; } = "pending";
        public string BehaviorId { get; set; } = "none";
        public string ActionPhase { get; set; } = "none";
    }

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
        private readonly List<string> availableAgentIds = new List<string>();
        private readonly Dictionary<string, TownNpcDebugSurface> npcSurfaces = new Dictionary<string, TownNpcDebugSurface>();
        private readonly Dictionary<string, DebugDecisionTraceV030Payload> decisionTraces = new Dictionary<string, DebugDecisionTraceV030Payload>();

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
        public string SelectedAgentId => selectedAgentId;
        public IReadOnlyList<string> AvailableAgentIds => availableAgentIds;
        public DebugDecisionTraceV030Payload SelectedDecisionTrace =>
            decisionTraces.TryGetValue(selectedAgentId, out var trace) ? trace : null;

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
            EnsureAgent(agentId);
            var surface = npcSurfaces[agentId];
            surface.BehaviorId = string.IsNullOrEmpty(behavior) ? "none" : behavior;
            surface.ActionPhase = string.IsNullOrEmpty(phase) ? "none" : phase;
            if (string.Equals(selectedAgentId, agentId, System.StringComparison.Ordinal))
            {
                behaviorId = surface.BehaviorId;
                actionPhase = surface.ActionPhase;
            }
        }

        public void SetAvailableAgents(IEnumerable<string> agentIds)
        {
            availableAgentIds.Clear();
            availableAgentIds.AddRange((agentIds ?? Enumerable.Empty<string>())
                .Where(item => !string.IsNullOrWhiteSpace(item))
                .Distinct(System.StringComparer.Ordinal)
                .OrderBy(item => item, System.StringComparer.Ordinal));
            foreach (var agentId in availableAgentIds)
            {
                EnsureAgent(agentId);
            }

            if (!availableAgentIds.Contains(selectedAgentId))
            {
                SelectAgent(availableAgentIds.FirstOrDefault());
            }
        }

        public bool SelectAgent(string agentId)
        {
            if (string.IsNullOrEmpty(agentId) || !availableAgentIds.Contains(agentId))
            {
                return false;
            }

            selectedAgentId = agentId;
            var surface = npcSurfaces[agentId];
            behaviorId = surface.BehaviorId;
            actionPhase = surface.ActionPhase;
            return true;
        }

        public void SetNpcSurface(TownNpcDebugSurface surface)
        {
            if (surface == null || string.IsNullOrWhiteSpace(surface.AgentId))
            {
                return;
            }

            EnsureAgent(surface.AgentId);
            npcSurfaces[surface.AgentId] = surface;
            if (string.Equals(selectedAgentId, surface.AgentId, System.StringComparison.Ordinal))
            {
                behaviorId = surface.BehaviorId;
                actionPhase = surface.ActionPhase;
            }
        }

        public void SetDecisionTrace(DebugDecisionTraceV030Payload trace)
        {
            if (trace == null)
            {
                return;
            }

            trace.Validate();
            EnsureAgent(trace.AgentId);
            decisionTraces[trace.AgentId] = trace;
        }

        public void SetHouseholdResources(string householdId, long? money, long? foodUnits)
        {
            foreach (var surface in npcSurfaces.Values.Where(item => item.HouseholdId == householdId))
            {
                surface.HouseholdResources = $"money={(money.HasValue ? money.Value.ToString() : "null")}; food={(foodUnits.HasValue ? foodUnits.Value.ToString() : "null")}";
            }
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
            DrawAgentSelector();
            GUILayout.Label($"NPC: {selectedAgentId} | behavior {behaviorId} | phase {actionPhase}");
            DrawSelectedNpcSurface();
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

        private void DrawAgentSelector()
        {
            if (availableAgentIds.Count == 0)
            {
                GUILayout.Label("NPC selector: PENDING registry/snapshot");
                return;
            }

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("<", GUILayout.Width(28f)))
            {
                CycleAgent(-1);
            }

            GUILayout.Label($"Selected {selectedAgentId}", GUILayout.Width(130f));
            if (GUILayout.Button(">", GUILayout.Width(28f)))
            {
                CycleAgent(1);
            }

            GUILayout.EndHorizontal();
            GUILayout.BeginHorizontal();
            foreach (var agentId in availableAgentIds)
            {
                if (GUILayout.Button(agentId.Replace("npc_", string.Empty), GUILayout.Width(32f)))
                {
                    SelectAgent(agentId);
                }
            }

            GUILayout.EndHorizontal();
        }

        private void DrawSelectedNpcSurface()
        {
            if (!npcSurfaces.TryGetValue(selectedAgentId, out var surface))
            {
                GUILayout.Label("Authority surface: PENDING protocol 0.3 snapshot");
                return;
            }

            GUILayout.Label($"Location {surface.AuthorityLocationId} | household {surface.HouseholdId}");
            GUILayout.Label($"Household resources: {surface.HouseholdResources}");
            GUILayout.Label($"Needs: {surface.Needs}");
            GUILayout.Label($"Mood: {surface.Mood}");
            GUILayout.Label($"Relationships: {surface.Relationships} | known events: {surface.KnownEvents}");
            DrawDecisionTrace();
        }

        private void DrawDecisionTrace()
        {
            if (!decisionTraces.TryGetValue(selectedAgentId, out var trace))
            {
                GUILayout.Label("Top-K: PENDING authoritative debug_decision_trace");
                return;
            }

            GUILayout.Label($"Decision {trace.DecisionId} | {trace.Trigger} | source v{trace.SourceStateVersion}");
            GUILayout.Label($"Selected {trace.SelectedCandidateId} / {trace.SelectedProposalId}");
            foreach (var row in trace.Candidates)
            {
                var selected = row.CandidateId == trace.SelectedCandidateId ? "SELECTED" : "";
                GUILayout.Label($"#{row.Rank} {row.BehaviorId} score={row.TotalScore:0.###} {row.ResolverResult ?? "NOT_ATTEMPTED"} {row.ConflictCode ?? selected}");
                GUILayout.Label($"  hard: money {row.HardPreview.HouseholdMoneyDelta:+#;-#;0}, food {row.HardPreview.HouseholdFoodUnitsDelta:+#;-#;0}, bindings {row.HardPreview.ObjectBindings.Count}, reservations {row.HardPreview.ReservationKeys.Count}");
                GUILayout.Label($"  prediction: {row.Prediction.ToString(Formatting.None)}");
                GUILayout.Label($"  utility: {string.Join(", ", row.UtilityTerms.OrderBy(item => item.Key).Select(item => $"{item.Key}={item.Value:0.###}"))}");
            }
        }

        private void CycleAgent(int offset)
        {
            if (availableAgentIds.Count == 0)
            {
                return;
            }

            var current = availableAgentIds.IndexOf(selectedAgentId);
            var next = (current + offset + availableAgentIds.Count) % availableAgentIds.Count;
            SelectAgent(availableAgentIds[next]);
        }

        private void EnsureAgent(string agentId)
        {
            if (string.IsNullOrWhiteSpace(agentId))
            {
                return;
            }

            if (!availableAgentIds.Contains(agentId))
            {
                availableAgentIds.Add(agentId);
                availableAgentIds.Sort(System.StringComparer.Ordinal);
            }

            if (!npcSurfaces.ContainsKey(agentId))
            {
                npcSurfaces.Add(agentId, new TownNpcDebugSurface { AgentId = agentId });
            }
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
