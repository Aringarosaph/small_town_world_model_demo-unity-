using System;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    public enum SemanticLocationType
    {
        HOME,
        CAFE_BAR,
        SHOP,
        WORKPLACE,
        PARK
    }

    [DisallowMultipleComponent]
    public sealed class SemanticLocation : MonoBehaviour
    {
        [SerializeField] private string locationId;
        [SerializeField] private SemanticLocationType locationType;
        [SerializeField] private string displayName;
        [SerializeField] private Transform[] entranceAnchors = Array.Empty<Transform>();

        public string LocationId => locationId;
        public SemanticLocationType LocationType => locationType;
        public string DisplayName => displayName;
        public Transform[] EntranceAnchors => entranceAnchors;

        public Transform PrimaryEntrance => entranceAnchors != null && entranceAnchors.Length > 0
            ? entranceAnchors[0]
            : null;

        public void Configure(
            string id,
            SemanticLocationType type,
            string visibleName,
            params Transform[] entrances)
        {
            locationId = id;
            locationType = type;
            displayName = visibleName;
            entranceAnchors = entrances ?? Array.Empty<Transform>();
        }
    }
}
