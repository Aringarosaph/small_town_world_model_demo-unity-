using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Bridge;
using UnityEngine;

namespace STWM.AITown.Animation
{
    [Serializable]
    public sealed class AnimationSemanticMapping
    {
        public AnimationSemantic semantic;
        public string triggerParameter;
        public string boolParameter;
        public string stateName;
    }

    [DisallowMultipleComponent]
    public sealed class NpcAnimationDriver : MonoBehaviour
    {
        [SerializeField] private Animator animator;
        [SerializeField] private List<AnimationSemanticMapping> mappings = new List<AnimationSemanticMapping>();
        [SerializeField] private bool allowNoAnimatorFallback = true;
        [SerializeField, Min(0.01f)] private float fallbackPresentationSeconds = 0.25f;

        private AnimationSemantic? currentSemantic;
        private string currentActionId;
        private float completionCountdown;
        private bool completionArmed;

        public IEnumerable<AnimationSemantic> MappedSemantics => mappings
            .Where(item => item != null)
            .Select(item => item.semantic)
            .Distinct();

        public AnimationSemantic? CurrentSemantic => currentSemantic;

        public event Action<string> PresentationCompleted;

        private void Awake()
        {
            if (animator == null)
            {
                animator = GetComponent<Animator>();
            }
        }

        private void Update()
        {
            if (!completionArmed)
            {
                return;
            }

            completionCountdown -= Time.unscaledDeltaTime;
            if (completionCountdown <= 0f)
            {
                CompleteCurrentPresentation();
            }
        }

        public bool IsMapped(AnimationSemantic semantic)
        {
            return mappings.Any(item => item != null && item.semantic == semantic);
        }

        public bool Play(AnimationSemantic semantic, string actionId, bool armCompletion)
        {
            var mapping = mappings.FirstOrDefault(item => item != null && item.semantic == semantic);
            if (mapping == null)
            {
                return false;
            }

            ResetPreviousBool();
            currentSemantic = semantic;
            currentActionId = actionId;
            if (animator != null)
            {
                if (!string.IsNullOrWhiteSpace(mapping.boolParameter) && HasParameter(mapping.boolParameter, AnimatorControllerParameterType.Bool))
                {
                    animator.SetBool(mapping.boolParameter, true);
                }

                if (!string.IsNullOrWhiteSpace(mapping.triggerParameter) && HasParameter(mapping.triggerParameter, AnimatorControllerParameterType.Trigger))
                {
                    animator.SetTrigger(mapping.triggerParameter);
                }

                if (!string.IsNullOrWhiteSpace(mapping.stateName))
                {
                    animator.CrossFade(mapping.stateName, 0.1f);
                }
            }

            completionArmed = armCompletion && allowNoAnimatorFallback;
            completionCountdown = fallbackPresentationSeconds;
            return true;
        }

        public void SetLocomotion(bool walking, string actionId)
        {
            Play(walking ? AnimationSemantic.WALK : AnimationSemantic.IDLE, actionId, false);
        }

        public void CompleteCurrentPresentation()
        {
            if (!completionArmed)
            {
                return;
            }

            completionArmed = false;
            var completedActionId = currentActionId;
            if (!string.IsNullOrEmpty(completedActionId))
            {
                PresentationCompleted?.Invoke(completedActionId);
            }
        }

        public void Stop(string actionId)
        {
            if (!string.Equals(currentActionId, actionId, StringComparison.Ordinal))
            {
                return;
            }

            completionArmed = false;
            SetLocomotion(false, actionId);
        }

        public void ConfigureFallbackMappings(params AnimationSemantic[] semantics)
        {
            mappings = (semantics ?? Array.Empty<AnimationSemantic>())
                .Distinct()
                .Select(item => new AnimationSemanticMapping { semantic = item })
                .ToList();
            allowNoAnimatorFallback = true;
        }

        public void SetFallbackDurationForTests(float seconds)
        {
            fallbackPresentationSeconds = Mathf.Max(0.01f, seconds);
        }

        private void ResetPreviousBool()
        {
            if (animator == null || !currentSemantic.HasValue)
            {
                return;
            }

            var previous = mappings.FirstOrDefault(item => item != null && item.semantic == currentSemantic.Value);
            if (previous != null
                && !string.IsNullOrWhiteSpace(previous.boolParameter)
                && HasParameter(previous.boolParameter, AnimatorControllerParameterType.Bool))
            {
                animator.SetBool(previous.boolParameter, false);
            }
        }

        private bool HasParameter(string parameterName, AnimatorControllerParameterType type)
        {
            return animator.parameters.Any(item => item.name == parameterName && item.type == type);
        }
    }
}
