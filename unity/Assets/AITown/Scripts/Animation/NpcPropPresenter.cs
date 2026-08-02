using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace STWM.AITown.Animation
{
    public enum PropSemantic
    {
        MEAL,
        GROCERY_BAG,
        DRINK,
        EVENT_ICON
    }

    [Serializable]
    public sealed class PropSemanticMapping
    {
        public PropSemantic semantic;
        public GameObject presentationObject;
    }

    [DisallowMultipleComponent]
    public sealed class NpcPropPresenter : MonoBehaviour
    {
        [SerializeField] private List<PropSemanticMapping> mappings = new List<PropSemanticMapping>();

        public IEnumerable<PropSemantic> SupportedSemantics => mappings
            .Where(item => item != null)
            .Select(item => item.semantic)
            .Distinct();

        public PropSemantic? CurrentSemantic { get; private set; }
        public string CurrentActionId { get; private set; }

        private void Awake()
        {
            HideAll();
        }

        public bool Supports(PropSemantic semantic)
        {
            return mappings.Any(item => item != null && item.semantic == semantic);
        }

        public bool Show(string semanticName, string actionId)
        {
            if (string.IsNullOrEmpty(semanticName))
            {
                HideAll();
                return true;
            }

            if (!Enum.TryParse(semanticName, out PropSemantic semantic))
            {
                return false;
            }

            var mapping = mappings.FirstOrDefault(item => item != null && item.semantic == semantic);
            if (mapping == null)
            {
                return false;
            }

            HideAll();
            CurrentSemantic = semantic;
            CurrentActionId = actionId;
            if (mapping.presentationObject != null)
            {
                mapping.presentationObject.SetActive(true);
            }

            return true;
        }

        public void Hide(string actionId)
        {
            if (string.Equals(CurrentActionId, actionId, StringComparison.Ordinal))
            {
                HideAll();
            }
        }

        public void ConfigureMappings(params PropSemanticMapping[] values)
        {
            mappings = (values ?? Array.Empty<PropSemanticMapping>())
                .Where(item => item != null)
                .GroupBy(item => item.semantic)
                .Select(group => group.First())
                .ToList();
            HideAll();
        }

        private void HideAll()
        {
            foreach (var mapping in mappings)
            {
                if (mapping?.presentationObject != null)
                {
                    mapping.presentationObject.SetActive(false);
                }
            }

            CurrentSemantic = null;
            CurrentActionId = null;
        }
    }
}
