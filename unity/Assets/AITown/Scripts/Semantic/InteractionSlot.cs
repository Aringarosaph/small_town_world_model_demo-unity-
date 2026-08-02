using System;
using System.Collections.Generic;
using STWM.AITown.Bridge;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    [DisallowMultipleComponent]
    public sealed class InteractionSlot : MonoBehaviour
    {
        [SerializeField, Min(0)] private int slotIndex;
        [SerializeField] private Transform anchorTransform;
        [SerializeField] private Transform facingTransform;
        [SerializeField] private AnimationSemantic[] supportedAnimationSemantics = Array.Empty<AnimationSemantic>();
        [SerializeField] private bool showOccupancyGizmo = true;

        private string localPresentationActionId;

        public int SlotIndex => slotIndex;
        public Transform AnchorTransform => anchorTransform != null ? anchorTransform : transform;
        public Transform FacingTransform => facingTransform;
        public IReadOnlyList<AnimationSemantic> SupportedAnimationSemantics => supportedAnimationSemantics;
        public string LocalPresentationActionId => localPresentationActionId;

        public Vector3 Position => AnchorTransform.position;

        public Quaternion Rotation
        {
            get
            {
                if (facingTransform != null)
                {
                    var direction = facingTransform.position - Position;
                    direction.y = 0f;
                    if (direction.sqrMagnitude > 0.0001f)
                    {
                        return Quaternion.LookRotation(direction.normalized, Vector3.up);
                    }
                }

                return AnchorTransform.rotation;
            }
        }

        public bool Supports(AnimationSemantic semantic)
        {
            if (supportedAnimationSemantics == null || supportedAnimationSemantics.Length == 0)
            {
                return true;
            }

            return Array.IndexOf(supportedAnimationSemantics, semantic) >= 0;
        }

        public bool TryClaimForPresentation(string actionId)
        {
            if (string.IsNullOrEmpty(localPresentationActionId)
                || string.Equals(localPresentationActionId, actionId, StringComparison.Ordinal))
            {
                localPresentationActionId = actionId;
                return true;
            }

            return false;
        }

        public void ReleasePresentationClaim(string actionId)
        {
            if (string.Equals(localPresentationActionId, actionId, StringComparison.Ordinal))
            {
                localPresentationActionId = null;
            }
        }

        public void Configure(
            int index,
            Transform anchor,
            Transform facing,
            params AnimationSemantic[] semantics)
        {
            slotIndex = Math.Max(0, index);
            anchorTransform = anchor;
            facingTransform = facing;
            supportedAnimationSemantics = semantics ?? Array.Empty<AnimationSemantic>();
        }

        private void OnDrawGizmos()
        {
            if (!showOccupancyGizmo)
            {
                return;
            }

            Gizmos.color = string.IsNullOrEmpty(localPresentationActionId)
                ? new Color(0.2f, 0.9f, 0.4f, 0.8f)
                : new Color(1f, 0.4f, 0.15f, 0.9f);
            Gizmos.DrawWireSphere(Position, 0.25f);
            Gizmos.DrawRay(Position, Rotation * Vector3.forward * 0.6f);
        }
    }
}
