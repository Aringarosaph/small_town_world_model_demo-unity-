using System;
using STWM.AITown.Bridge;
using STWM.AITown.Semantic;
using UnityEngine;
using UnityEngine.AI;

namespace STWM.AITown.NPC
{
    public enum NpcNavigationState
    {
        Idle,
        Navigating,
        Arrived,
        Failed,
        Cancelled
    }

    public sealed class NpcNavigationRequest
    {
        public string ActionId { get; set; }
        public string AgentId { get; set; }
        public SemanticObject TargetObject { get; set; }
        public InteractionSlot TargetSlot { get; set; }
        public Transform DestinationAnchor { get; set; }
    }

    public sealed class NpcNavigationCancellation
    {
        public string ActionId { get; set; }
        public string AgentId { get; set; }
        public MovementCancellationReason Reason { get; set; }
        public bool ReportToAuthority { get; set; }
    }

    public interface INpcNavigationBackend
    {
        bool IsActive { get; }
        bool IsOnNavMesh { get; }
        bool PathPending { get; }
        NavMeshPathStatus PathStatus { get; }
        float RemainingDistance { get; }
        Vector3 Velocity { get; }
        bool SetDestination(Vector3 destination);
        void ResetPath();
    }

    internal sealed class NavMeshAgentBackend : INpcNavigationBackend
    {
        private readonly NavMeshAgent agent;

        public NavMeshAgentBackend(NavMeshAgent agent)
        {
            this.agent = agent;
        }

        public bool IsActive => agent != null && agent.isActiveAndEnabled;
        public bool IsOnNavMesh => agent != null && agent.isOnNavMesh;
        public bool PathPending => agent != null && agent.pathPending;
        public NavMeshPathStatus PathStatus => agent != null ? agent.pathStatus : NavMeshPathStatus.PathInvalid;
        public float RemainingDistance => agent != null ? agent.remainingDistance : float.PositiveInfinity;
        public Vector3 Velocity => agent != null ? agent.velocity : Vector3.zero;

        public bool SetDestination(Vector3 destination)
        {
            return agent != null && agent.SetDestination(destination);
        }

        public void ResetPath()
        {
            if (agent != null && agent.isActiveAndEnabled && agent.isOnNavMesh)
            {
                agent.ResetPath();
            }
        }
    }

    [DisallowMultipleComponent]
    public sealed class NpcNavigationController : MonoBehaviour
    {
        [SerializeField] private NavMeshAgent navMeshAgent;
        [SerializeField, Min(0.01f)] private float arrivalTolerance = 0.15f;
        [SerializeField, Min(0.1f)] private float timeoutSeconds = 30f;

        private INpcNavigationBackend backend;
        private NpcNavigationRequest activeRequest;
        private float elapsedSeconds;

        public NpcNavigationState State { get; private set; } = NpcNavigationState.Idle;
        public string ActiveActionId => activeRequest?.ActionId;

        public event Action<NpcNavigationRequest> Arrived;
        public event Action<NpcNavigationRequest, MovementFailureReason> Failed;
        public event Action<NpcNavigationCancellation> Cancelled;

        private void Awake()
        {
            if (navMeshAgent == null)
            {
                navMeshAgent = GetComponent<NavMeshAgent>();
            }

            backend = backend ?? new NavMeshAgentBackend(navMeshAgent);
        }

        private void Update()
        {
            Tick(Time.unscaledDeltaTime);
        }

        public void Configure(NavMeshAgent agent, float timeout)
        {
            navMeshAgent = agent;
            backend = new NavMeshAgentBackend(agent);
            timeoutSeconds = Mathf.Max(0.1f, timeout);
        }

        public void SetBackendForTests(INpcNavigationBackend testBackend)
        {
            backend = testBackend ?? throw new ArgumentNullException(nameof(testBackend));
        }

        public bool BeginNavigation(NpcNavigationRequest request)
        {
            if (request == null || string.IsNullOrEmpty(request.ActionId) || string.IsNullOrEmpty(request.AgentId))
            {
                throw new ArgumentException("Navigation request requires action and agent IDs.", nameof(request));
            }

            if (activeRequest != null)
            {
                CancelNavigation(MovementCancellationReason.NAVIGATION_STOPPED, true);
            }

            activeRequest = request;
            elapsedSeconds = 0f;
            if (request.TargetObject != null && !request.TargetObject.SemanticEnabled)
            {
                Fail(MovementFailureReason.DESTINATION_DISABLED);
                return false;
            }

            if (request.TargetSlot != null && !request.TargetSlot.TryClaimForPresentation(request.ActionId))
            {
                Fail(MovementFailureReason.SLOT_BLOCKED);
                return false;
            }

            if (backend == null)
            {
                backend = new NavMeshAgentBackend(navMeshAgent);
            }

            if (!backend.IsActive || !backend.IsOnNavMesh)
            {
                Fail(MovementFailureReason.AGENT_DISABLED);
                return false;
            }

            var destination = request.TargetSlot != null
                ? request.TargetSlot.Position
                : request.DestinationAnchor != null
                    ? request.DestinationAnchor.position
                    : transform.position;
            if (!backend.SetDestination(destination))
            {
                Fail(MovementFailureReason.NO_PATH);
                return false;
            }

            State = NpcNavigationState.Navigating;
            return true;
        }

        public void TickForTests(float unscaledDeltaSeconds)
        {
            Tick(unscaledDeltaSeconds);
        }

        public void CancelNavigation(MovementCancellationReason reason, bool reportToAuthority)
        {
            if (activeRequest == null)
            {
                return;
            }

            var request = activeRequest;
            backend?.ResetPath();
            request.TargetSlot?.ReleasePresentationClaim(request.ActionId);
            activeRequest = null;
            State = NpcNavigationState.Cancelled;
            Cancelled?.Invoke(new NpcNavigationCancellation
            {
                ActionId = request.ActionId,
                AgentId = request.AgentId,
                Reason = reason,
                ReportToAuthority = reportToAuthority
            });
        }

        public void ReleasePresentationClaim(string actionId)
        {
            if (activeRequest != null && string.Equals(activeRequest.ActionId, actionId, StringComparison.Ordinal))
            {
                activeRequest.TargetSlot?.ReleasePresentationClaim(actionId);
                activeRequest = null;
                State = NpcNavigationState.Idle;
            }
        }

        private void Tick(float deltaSeconds)
        {
            if (State != NpcNavigationState.Navigating || activeRequest == null)
            {
                return;
            }

            elapsedSeconds += Mathf.Max(0f, deltaSeconds);
            if (elapsedSeconds >= timeoutSeconds)
            {
                Fail(MovementFailureReason.TIMEOUT);
                return;
            }

            if (backend.PathPending)
            {
                return;
            }

            if (backend.PathStatus == NavMeshPathStatus.PathInvalid
                || backend.PathStatus == NavMeshPathStatus.PathPartial)
            {
                Fail(MovementFailureReason.NO_PATH);
                return;
            }

            if (backend.RemainingDistance <= arrivalTolerance && backend.Velocity.sqrMagnitude <= 0.01f)
            {
                var request = activeRequest;
                backend.ResetPath();
                if (request.TargetSlot != null)
                {
                    transform.rotation = request.TargetSlot.Rotation;
                }

                State = NpcNavigationState.Arrived;
                Arrived?.Invoke(request);
            }
        }

        private void Fail(MovementFailureReason reason)
        {
            var request = activeRequest;
            if (request == null)
            {
                return;
            }

            backend?.ResetPath();
            request.TargetSlot?.ReleasePresentationClaim(request.ActionId);
            activeRequest = null;
            State = NpcNavigationState.Failed;
            Failed?.Invoke(request, reason);
        }
    }
}
