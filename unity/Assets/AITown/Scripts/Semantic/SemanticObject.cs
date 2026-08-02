using System;
using System.Collections.Generic;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    public enum SemanticObjectType
    {
        BED,
        FRIDGE,
        DINING_SEAT,
        SHOWER,
        SOFA,
        TV,
        WORKSTATION,
        SHOP_SHELF,
        CHECKOUT_COUNTER,
        CAFE_COUNTER,
        BAR_COUNTER,
        PUBLIC_SEAT,
        PARK_ROUTE,
        LEISURE_SPOT,
        CONVERSATION_ANCHOR
    }

    public enum SemanticCapability
    {
        SLEEP,
        FOOD_SOURCE_HOME,
        SIT,
        EAT,
        HYGIENE,
        RELAX,
        WATCH_TV,
        ENTERTAINMENT,
        WORK,
        CAFE_MORNING,
        CAFE_EVENING,
        SHOP,
        WORKSHOP,
        GROCERY_SOURCE,
        PURCHASE,
        BUY_MEAL,
        BUY_DRINK,
        REST,
        WALK_ROUTE,
        SOCIAL_POSITION
    }

    [DisallowMultipleComponent]
    public sealed class SemanticObject : MonoBehaviour
    {
        [SerializeField] private string objectId;
        [SerializeField] private SemanticObjectType objectType;
        [SerializeField] private string locationId;
        [SerializeField] private SemanticCapability[] capabilityTags = Array.Empty<SemanticCapability>();
        [SerializeField] private bool semanticEnabled = true;
        [SerializeField] private InteractionSlot[] interactionSlots = Array.Empty<InteractionSlot>();

        public string ObjectId => objectId;
        public SemanticObjectType ObjectType => objectType;
        public string LocationId => locationId;
        public IReadOnlyList<SemanticCapability> CapabilityTags => capabilityTags;
        public bool SemanticEnabled => semanticEnabled && isActiveAndEnabled;
        public IReadOnlyList<InteractionSlot> InteractionSlots => interactionSlots;

        public bool HasCapability(SemanticCapability capability)
        {
            return capabilityTags != null && Array.IndexOf(capabilityTags, capability) >= 0;
        }

        public InteractionSlot FindSlot(STWM.AITown.Bridge.AnimationSemantic semantic)
        {
            if (interactionSlots == null)
            {
                return null;
            }

            foreach (var slot in interactionSlots)
            {
                if (slot != null && slot.Supports(semantic))
                {
                    return slot;
                }
            }

            return null;
        }

        public void Configure(
            string id,
            SemanticObjectType type,
            string semanticLocationId,
            bool enabled,
            SemanticCapability[] capabilities,
            params InteractionSlot[] slots)
        {
            objectId = id;
            objectType = type;
            locationId = semanticLocationId;
            semanticEnabled = enabled;
            capabilityTags = capabilities ?? Array.Empty<SemanticCapability>();
            interactionSlots = slots ?? Array.Empty<InteractionSlot>();
        }

        [ContextMenu("Collect child interaction slots")]
        public void CollectChildSlots()
        {
            interactionSlots = GetComponentsInChildren<InteractionSlot>(true);
            Array.Sort(interactionSlots, (left, right) => left.SlotIndex.CompareTo(right.SlotIndex));
        }
    }
}
