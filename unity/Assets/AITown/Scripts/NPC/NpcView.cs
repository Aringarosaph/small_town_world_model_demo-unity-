using System;
using Newtonsoft.Json.Linq;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.Semantic;
using UnityEngine;

namespace STWM.AITown.NPC
{
    [DisallowMultipleComponent]
    public sealed class NpcView : MonoBehaviour
    {
        [SerializeField] private string agentId;
        [SerializeField] private NpcNavigationController navigationController;
        [SerializeField] private NpcAnimationDriver animationDriver;
        [SerializeField] private NpcPropPresenter propPresenter;
        [SerializeField] private SocialFacingController socialFacingController;
        [SerializeField] private GameObject statusIndicator;

        private TownBridgeClient bridge;
        private AnimationSemantic currentAnimationSemantic = AnimationSemantic.IDLE;
        private string currentPropSemantic;

        public string AgentId => agentId;
        public NpcNavigationController NavigationController => navigationController;
        public NpcAnimationDriver AnimationDriver => animationDriver;
        public NpcPropPresenter PropPresenter => propPresenter;
        public SocialFacingController SocialFacingController => socialFacingController;
        public string CurrentActionId { get; private set; }
        public string CurrentBehaviorId { get; private set; }
        public string CurrentPhase { get; private set; } = "NONE";
        public string CachedAuthorityLocationId { get; private set; }
        public JObject CachedNeeds { get; private set; }

        private void Awake()
        {
            if (navigationController == null)
            {
                navigationController = GetComponent<NpcNavigationController>();
            }

            if (animationDriver == null)
            {
                animationDriver = GetComponent<NpcAnimationDriver>();
            }

            if (propPresenter == null)
            {
                propPresenter = GetComponent<NpcPropPresenter>();
            }

            if (socialFacingController == null)
            {
                socialFacingController = GetComponent<SocialFacingController>();
            }

            SubscribePresentationEvents();
        }

        private void OnDestroy()
        {
            if (navigationController != null)
            {
                navigationController.Arrived -= OnNavigationArrived;
                navigationController.Failed -= OnNavigationFailed;
                navigationController.Cancelled -= OnNavigationCancelled;
            }

            if (animationDriver != null)
            {
                animationDriver.PresentationCompleted -= OnPresentationCompleted;
            }
        }

        public void Configure(
            string id,
            NpcNavigationController navigation,
            NpcAnimationDriver animations,
            GameObject indicator = null,
            NpcPropPresenter props = null,
            SocialFacingController facing = null)
        {
            agentId = id;
            navigationController = navigation;
            animationDriver = animations;
            statusIndicator = indicator;
            propPresenter = props != null ? props : GetComponent<NpcPropPresenter>();
            socialFacingController = facing != null ? facing : GetComponent<SocialFacingController>();
            SubscribePresentationEvents();
        }

        public void BindBridge(TownBridgeClient client)
        {
            bridge = client;
        }

        public void ApplySnapshotAgent(JObject agent)
        {
            CachedAuthorityLocationId = agent.Value<string>("current_location_id");
            CurrentActionId = agent.Value<string>("current_action_id");
            CachedNeeds = agent["needs"] as JObject;
            if (statusIndicator != null)
            {
                statusIndicator.SetActive(agent.Value<bool?>("enabled") ?? false);
            }
        }

        public void ApplyAgentDelta(AgentStateDeltaPayload delta)
        {
            if (delta.CurrentLocationId != null)
            {
                CachedAuthorityLocationId = delta.CurrentLocationId;
            }

            if (delta.CurrentActionId != null)
            {
                CurrentActionId = delta.CurrentActionId;
            }

            if (delta.Needs != null)
            {
                CachedNeeds = delta.Needs;
            }
        }

        public void BeginAction(ActionStartedPayload action)
        {
            if (action == null || !action.AgentIds.Contains(agentId))
            {
                return;
            }

            if (!Enum.TryParse(action.AnimationSemantic, out currentAnimationSemantic))
            {
                currentAnimationSemantic = AnimationSemantic.IDLE;
            }

            CurrentActionId = action.ActionId;
            CurrentBehaviorId = action.BehaviorId;
            CurrentPhase = "CREATED";
            currentPropSemantic = action.PropSemantic;
            var request = BuildNavigationRequest(action, currentAnimationSemantic);
            if (request != null && navigationController != null)
            {
                if (navigationController.BeginNavigation(request))
                {
                    animationDriver?.SetLocomotion(true, action.ActionId);
                }
            }
        }

        public void ApplyActionPhase(string actionId, string phase)
        {
            if (!string.Equals(CurrentActionId, actionId, StringComparison.Ordinal))
            {
                return;
            }

            CurrentPhase = phase;
            if (phase == "PERFORMING")
            {
                animationDriver?.Play(currentAnimationSemantic, actionId, true);
                propPresenter?.Show(currentPropSemantic, actionId);
            }
            else if (phase == "COMPLETED" || phase == "FAILED" || phase == "CANCELLED" || phase == "INTERRUPTED")
            {
                navigationController?.ReleasePresentationClaim(actionId);
                animationDriver?.Stop(actionId);
                propPresenter?.Hide(actionId);
                socialFacingController?.Clear(actionId);
                CurrentActionId = null;
                CurrentBehaviorId = null;
                currentPropSemantic = null;
            }
        }

        public void CancelAuthoritativeAction(string actionId, string reason)
        {
            if (!string.Equals(CurrentActionId, actionId, StringComparison.Ordinal))
            {
                return;
            }

            navigationController?.CancelNavigation(MovementCancellationReason.NAVIGATION_STOPPED, false);
            animationDriver?.Stop(actionId);
            propPresenter?.Hide(actionId);
            socialFacingController?.Clear(actionId);
            CurrentPhase = "CANCELLED";
            CurrentActionId = null;
            CurrentBehaviorId = null;
            currentPropSemantic = null;
        }

        private NpcNavigationRequest BuildNavigationRequest(ActionStartedPayload action, AnimationSemantic semantic)
        {
            foreach (var objectId in action.TargetObjectIds)
            {
                var semanticObject = TownSceneAssetRegistry.FindObject(objectId);
                var slot = semanticObject?.FindSlot(semantic);
                if (semanticObject != null && slot != null)
                {
                    return new NpcNavigationRequest
                    {
                        ActionId = action.ActionId,
                        AgentId = agentId,
                        TargetObject = semanticObject,
                        TargetSlot = slot
                    };
                }
            }

            var location = TownSceneAssetRegistry.FindLocation(action.DestinationLocationId);
            if (location?.PrimaryEntrance != null)
            {
                return new NpcNavigationRequest
                {
                    ActionId = action.ActionId,
                    AgentId = agentId,
                    DestinationAnchor = location.PrimaryEntrance
                };
            }

            return null;
        }

        private void SubscribePresentationEvents()
        {
            if (navigationController != null)
            {
                navigationController.Arrived -= OnNavigationArrived;
                navigationController.Failed -= OnNavigationFailed;
                navigationController.Cancelled -= OnNavigationCancelled;
                navigationController.Arrived += OnNavigationArrived;
                navigationController.Failed += OnNavigationFailed;
                navigationController.Cancelled += OnNavigationCancelled;
            }

            if (animationDriver != null)
            {
                animationDriver.PresentationCompleted -= OnPresentationCompleted;
                animationDriver.PresentationCompleted += OnPresentationCompleted;
            }
        }

        private void OnNavigationArrived(NpcNavigationRequest request)
        {
            animationDriver?.SetLocomotion(false, request.ActionId);
            bridge?.ReportMovementArrived(
                request.ActionId,
                agentId,
                request.TargetObject?.ObjectId,
                request.TargetSlot?.SlotIndex);
        }

        private void OnNavigationFailed(NpcNavigationRequest request, MovementFailureReason reason)
        {
            animationDriver?.SetLocomotion(false, request.ActionId);
            bridge?.ReportMovementFailed(request.ActionId, agentId, reason);
        }

        private void OnNavigationCancelled(NpcNavigationCancellation cancellation)
        {
            animationDriver?.SetLocomotion(false, cancellation.ActionId);
            if (cancellation.ReportToAuthority)
            {
                bridge?.ReportMovementCancelled(cancellation.ActionId, agentId, cancellation.Reason);
            }
        }

        private void OnPresentationCompleted(string actionId)
        {
            if (string.Equals(CurrentActionId, actionId, StringComparison.Ordinal))
            {
                bridge?.ReportPresentationCompleted(actionId, agentId);
            }
        }
    }
}
