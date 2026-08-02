using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Semantic;

namespace STWM.AITown.NPC
{
    public enum ActionPresentationRole
    {
        ACTOR,
        TARGET,
        PARTICIPANT
    }

    public sealed class PresentationObjectSlotBinding
    {
        public string ObjectId { get; set; }
        public int SlotIndex { get; set; }
    }

    public sealed class ActionPresentationParticipant
    {
        public string AgentId { get; set; }
        public ActionPresentationRole Role { get; set; }
        public string FacingAgentId { get; set; }
        public IReadOnlyList<PresentationObjectSlotBinding> ObjectSlotBindings { get; set; }
            = Array.Empty<PresentationObjectSlotBinding>();
    }

    public sealed class ClaimedPresentationSlot
    {
        public string AgentId { get; set; }
        public string ObjectId { get; set; }
        public int SlotIndex { get; set; }
        public string ClaimId { get; set; }
        public InteractionSlot Slot { get; set; }
    }

    /// <summary>
    /// Presentation-only aggregate for one authoritative action ID. It never
    /// chooses participants or slots; it only consumes explicit future 0.3
    /// bindings and claims them atomically in stable order.
    /// </summary>
    public sealed class ActionPresentationGroup
    {
        private readonly List<ClaimedPresentationSlot> claims = new List<ClaimedPresentationSlot>();

        public ActionPresentationGroup(string actionId, IEnumerable<ActionPresentationParticipant> participants)
        {
            if (string.IsNullOrWhiteSpace(actionId))
            {
                throw new ArgumentException("Action presentation group requires an action ID.", nameof(actionId));
            }

            ActionId = actionId;
            Participants = (participants ?? throw new ArgumentNullException(nameof(participants)))
                .OrderBy(item => item.AgentId, StringComparer.Ordinal)
                .ToArray();
            if (Participants.Count == 0
                || Participants.Any(item => string.IsNullOrWhiteSpace(item.AgentId))
                || Participants.Select(item => item.AgentId).Distinct(StringComparer.Ordinal).Count() != Participants.Count)
            {
                throw new ArgumentException("Action presentation participants require unique agent IDs.", nameof(participants));
            }
        }

        public string ActionId { get; }
        public IReadOnlyList<ActionPresentationParticipant> Participants { get; }
        public IReadOnlyList<ClaimedPresentationSlot> Claims => claims;

        public bool TryClaimAuthoritativeSlots(out string error)
        {
            error = null;
            if (claims.Count > 0)
            {
                return true;
            }

            var requested = Participants
                .SelectMany(participant => (participant.ObjectSlotBindings ?? Array.Empty<PresentationObjectSlotBinding>())
                    .Select(binding => new { participant.AgentId, Binding = binding }))
                .OrderBy(item => item.AgentId, StringComparer.Ordinal)
                .ThenBy(item => item.Binding.ObjectId, StringComparer.Ordinal)
                .ThenBy(item => item.Binding.SlotIndex)
                .ToArray();

            foreach (var item in requested)
            {
                var semanticObject = TownSceneAssetRegistry.FindObject(item.Binding.ObjectId);
                var slot = semanticObject?.FindSlot(item.Binding.SlotIndex);
                if (semanticObject == null || slot == null)
                {
                    error = $"AUTHORITATIVE_PRESENTATION_BINDING_NOT_FOUND: {item.AgentId}/{item.Binding.ObjectId}/{item.Binding.SlotIndex}";
                    ReleaseClaims();
                    return false;
                }

                var claimId = $"{ActionId}:{item.AgentId}:{item.Binding.ObjectId}:{item.Binding.SlotIndex}";
                if (!slot.TryClaimForPresentation(claimId))
                {
                    error = $"PRESENTATION_SLOT_ALREADY_CLAIMED: {item.Binding.ObjectId}/{item.Binding.SlotIndex}";
                    ReleaseClaims();
                    return false;
                }

                claims.Add(new ClaimedPresentationSlot
                {
                    AgentId = item.AgentId,
                    ObjectId = item.Binding.ObjectId,
                    SlotIndex = item.Binding.SlotIndex,
                    ClaimId = claimId,
                    Slot = slot
                });
            }

            return true;
        }

        public bool ApplyAuthoritativeFacing(string behaviorId, out string error)
        {
            error = null;
            foreach (var participant in Participants)
            {
                if (string.IsNullOrEmpty(participant.FacingAgentId))
                {
                    continue;
                }

                var source = TownSceneAssetRegistry.FindNpcView(participant.AgentId);
                var target = TownSceneAssetRegistry.FindNpcView(participant.FacingAgentId);
                if (source?.SocialFacingController == null || target == null
                    || !source.SocialFacingController.BeginAuthoritativeFacing(
                        behaviorId,
                        ActionId,
                        target.transform))
                {
                    error = $"AUTHORITATIVE_FACING_BINDING_INVALID: {participant.AgentId}->{participant.FacingAgentId}";
                    ClearFacing();
                    return false;
                }
            }

            return true;
        }

        public void ReleaseClaims()
        {
            foreach (var claim in claims)
            {
                claim.Slot?.ReleasePresentationClaim(claim.ClaimId);
            }

            claims.Clear();
        }

        public void ClearFacing()
        {
            foreach (var participant in Participants)
            {
                TownSceneAssetRegistry.FindNpcView(participant.AgentId)?.SocialFacingController?.Clear(ActionId);
            }
        }
    }
}
