using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace STWM.AITown.NPC
{
    [DisallowMultipleComponent]
    public sealed class SocialFacingController : MonoBehaviour
    {
        [SerializeField] private string[] supportedBehaviorIds = Array.Empty<string>();
        [SerializeField, Min(1f)] private float degreesPerSecond = 720f;

        private Transform facingTarget;
        private string currentActionId;

        public IReadOnlyCollection<string> SupportedBehaviorIds => supportedBehaviorIds;
        public string CurrentActionId => currentActionId;
        public Transform FacingTarget => facingTarget;

        private void LateUpdate()
        {
            if (facingTarget == null)
            {
                return;
            }

            var direction = facingTarget.position - transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude <= 0.0001f)
            {
                return;
            }

            var desired = Quaternion.LookRotation(direction.normalized, Vector3.up);
            transform.rotation = Quaternion.RotateTowards(
                transform.rotation,
                desired,
                degreesPerSecond * Time.unscaledDeltaTime);
        }

        public bool SupportsBehavior(string behaviorId)
        {
            return supportedBehaviorIds.Contains(behaviorId, StringComparer.Ordinal);
        }

        public bool BeginAuthoritativeFacing(string behaviorId, string actionId, Transform target)
        {
            if (!SupportsBehavior(behaviorId) || string.IsNullOrEmpty(actionId) || target == null)
            {
                return false;
            }

            currentActionId = actionId;
            facingTarget = target;
            return true;
        }

        public void Clear(string actionId)
        {
            if (!string.Equals(currentActionId, actionId, StringComparison.Ordinal))
            {
                return;
            }

            currentActionId = null;
            facingTarget = null;
        }

        public void ConfigureSupportedBehaviors(IEnumerable<string> behaviorIds)
        {
            supportedBehaviorIds = (behaviorIds ?? Enumerable.Empty<string>())
                .Where(item => !string.IsNullOrWhiteSpace(item))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(item => item, StringComparer.Ordinal)
                .ToArray();
        }
    }
}
