using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using STWM.AITown.NPC;

namespace STWM.AITown.Bridge
{
    public sealed class ClientHelloV030Payload
    {
        [JsonProperty("client_name")]
        public string ClientName { get; set; } = "unity";

        [JsonProperty("unity_editor_version")]
        public string UnityEditorVersion { get; set; } = TownProtocol.UnityEditorVersion;

        [JsonProperty("supported_protocol_versions", ObjectCreationHandling = ObjectCreationHandling.Replace)]
        public List<string> SupportedProtocolVersions { get; set; } = new List<string>
        {
            TownProtocol.M3Version,
            TownProtocol.M2Version
        };
    }

    public sealed class ParticipantObjectBindingV030
    {
        [JsonProperty("object_id", Required = Required.Always)]
        public string ObjectId { get; set; }

        [JsonProperty("slot_index", Required = Required.Always)]
        public int SlotIndex { get; set; }
    }

    public sealed class FacingTargetV030
    {
        [JsonProperty("target_agent_id", Required = Required.AllowNull)]
        public string TargetAgentId { get; set; }

        [JsonProperty("target_object_id", Required = Required.AllowNull)]
        public string TargetObjectId { get; set; }

        public void Validate()
        {
            if (string.IsNullOrEmpty(TargetAgentId) == string.IsNullOrEmpty(TargetObjectId))
            {
                throw new InvalidOperationException("M3 facing target requires exactly one agent or object ID.");
            }
        }
    }

    public sealed class ActionParticipantV030
    {
        [JsonProperty("agent_id", Required = Required.Always)]
        public string AgentId { get; set; }

        [JsonProperty("role", Required = Required.Always)]
        public string Role { get; set; }

        [JsonProperty("object_bindings", Required = Required.Always)]
        public List<ParticipantObjectBindingV030> ObjectBindings { get; set; } = new List<ParticipantObjectBindingV030>();

        [JsonProperty("facing_target", Required = Required.AllowNull)]
        public FacingTargetV030 FacingTarget { get; set; }

        [JsonProperty("animation_semantic", Required = Required.Always)]
        public string AnimationSemantic { get; set; }

        [JsonProperty("prop_semantic", Required = Required.AllowNull)]
        public string PropSemantic { get; set; }

        public ActionPresentationParticipant ToPresentationParticipant()
        {
            var allowedProps = new HashSet<string>(new[] { "MEAL", "GROCERY_BAG", "DRINK", "EVENT_ICON" }, StringComparer.Ordinal);
            if (!Enum.TryParse(Role, out ActionPresentationRole parsedRole)
                || !Enum.TryParse(this.AnimationSemantic, out STWM.AITown.Bridge.AnimationSemantic _)
                || (!string.IsNullOrEmpty(PropSemantic) && !allowedProps.Contains(PropSemantic)))
            {
                throw new InvalidOperationException($"Invalid M3 participant role/animation for {AgentId}.");
            }

            FacingTarget?.Validate();
            var bindings = ObjectBindings ?? new List<ParticipantObjectBindingV030>();
            if (bindings.Any(item => item == null || string.IsNullOrWhiteSpace(item.ObjectId) || item.SlotIndex < 0)
                || bindings.Select(item => item.ObjectId + ":" + item.SlotIndex).Distinct(StringComparer.Ordinal).Count() != bindings.Count)
            {
                throw new InvalidOperationException($"Invalid or duplicate M3 participant binding for {AgentId}.");
            }

            return new ActionPresentationParticipant
            {
                AgentId = AgentId,
                Role = parsedRole,
                FacingAgentId = FacingTarget?.TargetAgentId,
                FacingObjectId = FacingTarget?.TargetObjectId,
                AnimationSemantic = AnimationSemantic,
                PropSemantic = PropSemantic,
                ObjectSlotBindings = bindings.Select(item => new PresentationObjectSlotBinding
                {
                    ObjectId = item.ObjectId,
                    SlotIndex = item.SlotIndex
                }).ToArray()
            };
        }
    }

    public abstract class StructuredActionPresentationV030
    {
        [JsonProperty("action_id", Required = Required.Always)]
        public string ActionId { get; set; }

        [JsonProperty("behavior_id", Required = Required.Always)]
        public string BehaviorId { get; set; }

        [JsonProperty("destination_location_id", Required = Required.Always)]
        public string DestinationLocationId { get; set; }

        [JsonProperty("participants", Required = Required.Always)]
        public List<ActionParticipantV030> Participants { get; set; } = new List<ActionParticipantV030>();

        [JsonProperty("is_joint", Required = Required.Always)]
        public bool IsJoint { get; set; }

        [JsonProperty("conversation_id", Required = Required.AllowNull)]
        public string ConversationId { get; set; }

        public IReadOnlyList<ActionPresentationParticipant> ValidateAndProjectParticipants()
        {
            if (string.IsNullOrWhiteSpace(ActionId)
                || string.IsNullOrWhiteSpace(BehaviorId)
                || string.IsNullOrWhiteSpace(DestinationLocationId)
                || Participants == null
                || Participants.Count < 1
                || Participants.Count > 10)
            {
                throw new InvalidOperationException("M3 structured action identity/participant count is invalid.");
            }

            var projected = Participants.Select(item => item?.ToPresentationParticipant()
                ?? throw new InvalidOperationException("M3 action participant cannot be null.")).ToArray();
            var ids = projected.Select(item => item.AgentId).ToArray();
            if (ids.Any(string.IsNullOrWhiteSpace)
                || ids.Distinct(StringComparer.Ordinal).Count() != ids.Length
                || !ids.SequenceEqual(ids.OrderBy(item => item, StringComparer.Ordinal))
                || projected.Count(item => item.Role == ActionPresentationRole.ACTOR) != 1
                || IsJoint != (projected.Length >= 2))
            {
                throw new InvalidOperationException("M3 action participants violate stable order, role, uniqueness, or joint semantics.");
            }

            var claims = projected.SelectMany(item => item.ObjectSlotBindings)
                .Select(item => item.ObjectId + ":" + item.SlotIndex).ToArray();
            if (claims.Distinct(StringComparer.Ordinal).Count() != claims.Length)
            {
                throw new InvalidOperationException("M3 action participants bind the same object slot more than once.");
            }

            var facingBehaviors = new HashSet<string>(new[]
            {
                "greet", "chat", "joke", "compliment", "share_event", "invite_join", "apologize", "confront"
            }, StringComparer.Ordinal);
            if (facingBehaviors.Contains(BehaviorId))
            {
                var actor = projected.Single(item => item.Role == ActionPresentationRole.ACTOR);
                var targets = projected.Where(item => item.Role == ActionPresentationRole.TARGET).ToArray();
                if (targets.Length != 1
                    || actor.FacingAgentId != targets[0].AgentId
                    || targets[0].FacingAgentId != actor.AgentId)
                {
                    throw new InvalidOperationException("M3 social action ACTOR/TARGET facing is not reciprocal.");
                }
            }

            return projected;
        }
    }

    public sealed class ActionStartedV030Payload : StructuredActionPresentationV030
    {
        [JsonProperty("planned_duration_minutes", Required = Required.Always)]
        public long PlannedDurationMinutes { get; set; }
    }

    public sealed class ActiveActionPresentationV030 : StructuredActionPresentationV030
    {
        [JsonProperty("phase", Required = Required.Always)]
        public string Phase { get; set; }

        [JsonProperty("planned_end_game_minute", Required = Required.AllowNull)]
        public long? PlannedEndGameMinute { get; set; }
    }

    public sealed class WorldSnapshotV030Payload
    {
        [JsonProperty("world", Required = Required.Always)]
        public JObject World { get; set; }

        [JsonProperty("active_presentations", Required = Required.Always)]
        public List<ActiveActionPresentationV030> ActivePresentations { get; set; } = new List<ActiveActionPresentationV030>();

        public void Validate()
        {
            if (World == null || !(World["active_actions"] is JObject activeActions))
            {
                throw new InvalidOperationException("M3 world snapshot requires a world and active_actions map.");
            }

            var presentations = ActivePresentations ?? new List<ActiveActionPresentationV030>();
            foreach (var item in presentations)
            {
                item.ValidateAndProjectParticipants();
            }

            var presentationIds = presentations.Select(item => item.ActionId).ToArray();
            if (presentationIds.Distinct(StringComparer.Ordinal).Count() != presentationIds.Length
                || !new HashSet<string>(presentationIds, StringComparer.Ordinal)
                    .SetEquals(activeActions.Properties().Select(item => item.Name)))
            {
                throw new InvalidOperationException("M3 active_presentations must exactly cover world.active_actions.");
            }
        }
    }

    public sealed class AgentStateDeltaV030Payload
    {
        private static readonly HashSet<string> AllowedFields = new HashSet<string>(new[]
        {
            "current_location_id", "current_action_id", "needs", "mood", "known_event_ids"
        }, StringComparer.Ordinal);

        public string AgentId { get; private set; }
        public IReadOnlyList<string> FieldMask { get; private set; }
        public JObject RawPayload { get; private set; }

        public bool Has(string fieldName) => FieldMask.Contains(fieldName);
        public JToken Value(string fieldName) => RawPayload[fieldName];

        public static AgentStateDeltaV030Payload Parse(JObject payload)
        {
            var agentId = payload?.Value<string>("agent_id");
            var maskArray = payload?["field_mask"] as JArray;
            if (string.IsNullOrWhiteSpace(agentId) || maskArray == null || maskArray.Count == 0)
            {
                throw new InvalidOperationException("M3 agent delta requires agent_id and a non-empty field_mask.");
            }

            var mask = maskArray.Select(item => item.Type == JTokenType.String ? item.Value<string>() : null).ToArray();
            var supplied = payload.Properties()
                .Select(item => item.Name)
                .Where(item => item != "agent_id" && item != "field_mask")
                .ToArray();
            if (mask.Any(item => string.IsNullOrEmpty(item) || !AllowedFields.Contains(item))
                || mask.Distinct(StringComparer.Ordinal).Count() != mask.Length
                || !new HashSet<string>(mask, StringComparer.Ordinal).SetEquals(supplied))
            {
                throw new InvalidOperationException("M3 agent delta field presence must exactly equal its unique field_mask.");
            }

            return new AgentStateDeltaV030Payload
            {
                AgentId = agentId,
                FieldMask = mask,
                RawPayload = (JObject)payload.DeepClone()
            };
        }
    }

    public sealed class HouseholdStateDeltaV030Payload
    {
        private static readonly HashSet<string> AllowedFields = new HashSet<string>(new[] { "money", "food_units" }, StringComparer.Ordinal);

        public string HouseholdId { get; private set; }
        public IReadOnlyList<string> FieldMask { get; private set; }
        public JObject RawPayload { get; private set; }

        public static HouseholdStateDeltaV030Payload Parse(JObject payload)
        {
            var householdId = payload?.Value<string>("household_id");
            var maskArray = payload?["field_mask"] as JArray;
            if (string.IsNullOrWhiteSpace(householdId) || maskArray == null || maskArray.Count == 0)
            {
                throw new InvalidOperationException("M3 household delta requires household_id and a non-empty field_mask.");
            }

            var mask = maskArray.Values<string>().ToArray();
            var supplied = payload.Properties().Select(item => item.Name)
                .Where(item => item != "household_id" && item != "field_mask").ToArray();
            if (mask.Any(item => !AllowedFields.Contains(item))
                || mask.Distinct(StringComparer.Ordinal).Count() != mask.Length
                || !new HashSet<string>(mask, StringComparer.Ordinal).SetEquals(supplied)
                || mask.Any(item => payload[item] == null || payload[item].Type == JTokenType.Null || payload.Value<long>(item) < 0))
            {
                throw new InvalidOperationException("M3 household delta fields must exactly match field_mask and be non-negative values.");
            }

            return new HouseholdStateDeltaV030Payload
            {
                HouseholdId = householdId,
                FieldMask = mask,
                RawPayload = (JObject)payload.DeepClone()
            };
        }
    }

    public sealed class HardPreviewV030
    {
        [JsonProperty("household_money_delta", Required = Required.Always)] public long HouseholdMoneyDelta { get; set; }
        [JsonProperty("household_food_units_delta", Required = Required.Always)] public long HouseholdFoodUnitsDelta { get; set; }
        [JsonProperty("object_bindings", Required = Required.Always)] public List<ParticipantObjectBindingV030> ObjectBindings { get; set; } = new List<ParticipantObjectBindingV030>();
        [JsonProperty("reservation_keys", Required = Required.Always)] public List<string> ReservationKeys { get; set; } = new List<string>();
        [JsonProperty("settlement_keys", Required = Required.Always)] public List<string> SettlementKeys { get; set; } = new List<string>();
    }

    public sealed class DebugCandidateTraceV030
    {
        [JsonProperty("rank", Required = Required.Always)] public int Rank { get; set; }
        [JsonProperty("candidate_id", Required = Required.Always)] public string CandidateId { get; set; }
        [JsonProperty("proposal_id", Required = Required.AllowNull)] public string ProposalId { get; set; }
        [JsonProperty("behavior_id", Required = Required.Always)] public string BehaviorId { get; set; }
        [JsonProperty("actor_id", Required = Required.Always)] public string ActorId { get; set; }
        [JsonProperty("target_agent_id", Required = Required.AllowNull)] public string TargetAgentId { get; set; }
        [JsonProperty("selected_context_event_id", Required = Required.AllowNull)] public string SelectedContextEventId { get; set; }
        [JsonProperty("target_conversation_id", Required = Required.AllowNull)] public string TargetConversationId { get; set; }
        [JsonProperty("invited_activity_id", Required = Required.AllowNull)] public string InvitedActivityId { get; set; }
        [JsonProperty("destination_location_id", Required = Required.AllowNull)] public string DestinationLocationId { get; set; }
        [JsonProperty("hard_preview", Required = Required.Always)] public HardPreviewV030 HardPreview { get; set; }
        [JsonProperty("prediction", Required = Required.Always)] public JObject Prediction { get; set; }
        [JsonProperty("utility_terms", Required = Required.Always)] public Dictionary<string, double> UtilityTerms { get; set; } = new Dictionary<string, double>();
        [JsonProperty("total_score", Required = Required.Always)] public double TotalScore { get; set; }
        [JsonProperty("resolver_result", Required = Required.AllowNull)] public string ResolverResult { get; set; }
        [JsonProperty("conflict_code", Required = Required.AllowNull)] public string ConflictCode { get; set; }
    }

    public sealed class DebugDecisionTraceV030Payload
    {
        [JsonProperty("decision_id", Required = Required.Always)] public string DecisionId { get; set; }
        [JsonProperty("agent_id", Required = Required.Always)] public string AgentId { get; set; }
        [JsonProperty("trigger", Required = Required.Always)] public string Trigger { get; set; }
        [JsonProperty("source_state_version", Required = Required.Always)] public long SourceStateVersion { get; set; }
        [JsonProperty("candidates", Required = Required.Always)] public List<DebugCandidateTraceV030> Candidates { get; set; } = new List<DebugCandidateTraceV030>();
        [JsonProperty("selected_candidate_id", Required = Required.Always)] public string SelectedCandidateId { get; set; }
        [JsonProperty("selected_proposal_id", Required = Required.Always)] public string SelectedProposalId { get; set; }

        public void Validate()
        {
            if (string.IsNullOrWhiteSpace(DecisionId)
                || string.IsNullOrWhiteSpace(AgentId)
                || Candidates == null
                || Candidates.Count < 1
                || Candidates.Count > 12
                || !Candidates.Select(item => item.Rank).SequenceEqual(Enumerable.Range(1, Candidates.Count))
                || Candidates.Select(item => item.CandidateId).Distinct(StringComparer.Ordinal).Count() != Candidates.Count)
            {
                throw new InvalidOperationException("M3 Top-K decision identity, ranks, or candidate IDs are invalid.");
            }

            var attempted = 0;
            foreach (var row in Candidates)
            {
                var isAttempted = row.ResolverResult != null;
                if (isAttempted) attempted++;
                if ((!isAttempted && (row.ProposalId != null || row.ConflictCode != null))
                    || (isAttempted && row.ProposalId == null)
                    || (row.ResolverResult == "ACCEPTED" && row.ConflictCode != null)
                    || (isAttempted && row.ResolverResult != "ACCEPTED" && row.ConflictCode == null)
                    || row.Prediction == null
                    || row.Prediction.Value<string>("candidate_id") != row.CandidateId
                    || row.HardPreview == null
                    || row.UtilityTerms == null
                    || row.UtilityTerms.Count == 0)
                {
                    throw new InvalidOperationException($"M3 Top-K Resolver tuple/preview is invalid for {row.CandidateId}.");
                }
            }

            var selected = Candidates.SingleOrDefault(item => item.CandidateId == SelectedCandidateId);
            if (attempted > 2
                || selected == null
                || selected.ResolverResult != "ACCEPTED"
                || selected.ProposalId != SelectedProposalId)
            {
                throw new InvalidOperationException("M3 Top-K selected candidate/proposal/Resolver result is inconsistent.");
            }
        }
    }
}
