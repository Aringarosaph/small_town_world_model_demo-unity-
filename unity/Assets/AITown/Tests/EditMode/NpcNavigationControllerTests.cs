using NUnit.Framework;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine;
using UnityEngine.AI;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class NpcNavigationControllerTests
    {
        private GameObject npc;
        private NpcNavigationController controller;
        private FakeNavigationBackend backend;

        [SetUp]
        public void SetUp()
        {
            npc = new GameObject("npc_01");
            controller = npc.AddComponent<NpcNavigationController>();
            backend = new FakeNavigationBackend();
            controller.SetBackendForTests(backend);
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(npc);
        }

        [Test]
        public void CompletePathReportsArrival()
        {
            NpcNavigationRequest arrived = null;
            controller.Arrived += request => arrived = request;
            backend.RemainingDistance = 0f;
            backend.Velocity = Vector3.zero;

            controller.BeginNavigation(Request("action_1"));
            controller.TickForTests(0.01f);

            Assert.That(controller.State, Is.EqualTo(NpcNavigationState.Arrived));
            Assert.That(arrived?.ActionId, Is.EqualTo("action_1"));
        }

        [Test]
        public void PartialPathReportsNoPath()
        {
            MovementFailureReason? failure = null;
            controller.Failed += (_, reason) => failure = reason;
            backend.PathStatus = NavMeshPathStatus.PathPartial;

            controller.BeginNavigation(Request("action_2"));
            controller.TickForTests(0.01f);

            Assert.That(failure, Is.EqualTo(MovementFailureReason.NO_PATH));
            Assert.That(controller.State, Is.EqualTo(NpcNavigationState.Failed));
        }

        [Test]
        public void PendingPathCanTimeoutDeterministically()
        {
            MovementFailureReason? failure = null;
            controller.Failed += (_, reason) => failure = reason;
            backend.PathPending = true;

            controller.BeginNavigation(Request("action_3"));
            controller.TickForTests(31f);

            Assert.That(failure, Is.EqualTo(MovementFailureReason.TIMEOUT));
        }

        [Test]
        public void LocalCancellationIsDistinctFromFailure()
        {
            NpcNavigationCancellation cancellation = null;
            var failureCount = 0;
            controller.Cancelled += value => cancellation = value;
            controller.Failed += (_, _) => failureCount++;
            controller.BeginNavigation(Request("action_4"));

            controller.CancelNavigation(MovementCancellationReason.NAVIGATION_STOPPED, true);

            Assert.That(controller.State, Is.EqualTo(NpcNavigationState.Cancelled));
            Assert.That(cancellation?.Reason, Is.EqualTo(MovementCancellationReason.NAVIGATION_STOPPED));
            Assert.That(cancellation?.ReportToAuthority, Is.True);
            Assert.That(failureCount, Is.Zero);
        }

        [Test]
        public void ClaimedPresentationSlotReportsSlotBlocked()
        {
            var target = new GameObject("target");
            try
            {
                var slot = target.AddComponent<InteractionSlot>();
                slot.Configure(0, target.transform, null, AnimationSemantic.SLEEP);
                slot.TryClaimForPresentation("action_99");
                var semanticObject = target.AddComponent<SemanticObject>();
                semanticObject.Configure(
                    "home_a_bed_01",
                    SemanticObjectType.BED,
                    "home_a",
                    true,
                    new[] { SemanticCapability.SLEEP },
                    slot);
                MovementFailureReason? failure = null;
                controller.Failed += (_, reason) => failure = reason;

                controller.BeginNavigation(new NpcNavigationRequest
                {
                    ActionId = "action_5",
                    AgentId = "npc_01",
                    TargetObject = semanticObject,
                    TargetSlot = slot
                });

                Assert.That(failure, Is.EqualTo(MovementFailureReason.SLOT_BLOCKED));
            }
            finally
            {
                Object.DestroyImmediate(target);
            }
        }

        private NpcNavigationRequest Request(string actionId)
        {
            return new NpcNavigationRequest
            {
                ActionId = actionId,
                AgentId = "npc_01",
                DestinationAnchor = npc.transform
            };
        }

        private sealed class FakeNavigationBackend : INpcNavigationBackend
        {
            public bool IsActive { get; set; } = true;
            public bool IsOnNavMesh { get; set; } = true;
            public bool PathPending { get; set; }
            public NavMeshPathStatus PathStatus { get; set; } = NavMeshPathStatus.PathComplete;
            public float RemainingDistance { get; set; } = 10f;
            public Vector3 Velocity { get; set; } = Vector3.one;
            public bool SetDestinationResult { get; set; } = true;

            public bool SetDestination(Vector3 destination)
            {
                return SetDestinationResult;
            }

            public void ResetPath()
            {
            }
        }
    }
}
