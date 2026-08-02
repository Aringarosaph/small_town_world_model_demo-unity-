using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using STWM.AITown.Animation;
using STWM.AITown.Debugging;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class M3PresentationSkeletonTests
    {
        private readonly List<GameObject> roots = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var root in roots)
            {
                if (root != null)
                {
                    Object.DestroyImmediate(root);
                }
            }

            roots.Clear();
        }

        [Test]
        public void ActionPresentationGroupSortsParticipantsAndClaimsDistinctSlotsAtomically()
        {
            var semanticObject = CreateTwoSlotObject();
            var group = new ActionPresentationGroup("action_300", new[]
            {
                Participant("npc_02", semanticObject.ObjectId, 1),
                Participant("npc_01", semanticObject.ObjectId, 0)
            });

            Assert.That(group.Participants.Select(item => item.AgentId), Is.EqualTo(new[] { "npc_01", "npc_02" }));
            Assert.That(group.TryClaimAuthoritativeSlots(out var error), Is.True, error);
            Assert.That(group.Claims.Select(item => item.AgentId), Is.EqualTo(new[] { "npc_01", "npc_02" }));
            Assert.That(semanticObject.FindSlot(0).LocalPresentationClaimId, Does.Contain("npc_01"));
            Assert.That(semanticObject.FindSlot(1).LocalPresentationClaimId, Does.Contain("npc_02"));

            group.ReleaseClaims();
            Assert.That(semanticObject.FindSlot(0).LocalPresentationClaimId, Is.Null);
            Assert.That(semanticObject.FindSlot(1).LocalPresentationClaimId, Is.Null);
        }

        [Test]
        public void ConflictingParticipantBindingRollsBackWholeLocalClaimSet()
        {
            var semanticObject = CreateTwoSlotObject();
            var group = new ActionPresentationGroup("action_301", new[]
            {
                Participant("npc_01", semanticObject.ObjectId, 0),
                Participant("npc_02", semanticObject.ObjectId, 0)
            });

            Assert.That(group.TryClaimAuthoritativeSlots(out var error), Is.False);
            Assert.That(error, Does.StartWith("PRESENTATION_SLOT_ALREADY_CLAIMED"));
            Assert.That(group.Claims, Is.Empty);
            Assert.That(semanticObject.FindSlot(0).LocalPresentationClaimId, Is.Null);
        }

        [Test]
        public void PropPresenterAndTenNpcSelectorRemainReadOnlyPresentationState()
        {
            var root = Track(new GameObject("presentation"));
            var prop = root.AddComponent<NpcPropPresenter>();
            prop.ConfigureMappings(
                new PropSemanticMapping { semantic = PropSemantic.MEAL },
                new PropSemanticMapping { semantic = PropSemantic.GROCERY_BAG },
                new PropSemanticMapping { semantic = PropSemantic.DRINK },
                new PropSemanticMapping { semantic = PropSemantic.EVENT_ICON });
            Assert.That(prop.Show("MEAL", "action_302"), Is.True);
            Assert.That(prop.CurrentSemantic, Is.EqualTo(PropSemantic.MEAL));
            prop.Hide("action_302");
            Assert.That(prop.CurrentSemantic, Is.Null);

            var panel = root.AddComponent<TownDebugPanel>();
            panel.SetAvailableAgents(Enumerable.Range(1, 10).Reverse().Select(index => $"npc_{index:00}"));
            Assert.That(panel.AvailableAgentIds.First(), Is.EqualTo("npc_01"));
            Assert.That(panel.AvailableAgentIds.Last(), Is.EqualTo("npc_10"));
            Assert.That(panel.SelectAgent("npc_07"), Is.True);
            Assert.That(panel.SelectedAgentId, Is.EqualTo("npc_07"));
            Assert.That(panel.SelectAgent("npc_99"), Is.False);
        }

        private SemanticObject CreateTwoSlotObject()
        {
            var root = Track(new GameObject("park_conversation_01"));
            var slot0Root = new GameObject("slot0");
            slot0Root.transform.SetParent(root.transform);
            var slot1Root = new GameObject("slot1");
            slot1Root.transform.SetParent(root.transform);
            var slot0 = slot0Root.AddComponent<InteractionSlot>();
            var slot1 = slot1Root.AddComponent<InteractionSlot>();
            slot0.Configure(0, slot0.transform, null, STWM.AITown.Bridge.AnimationSemantic.TALK_NEUTRAL);
            slot1.Configure(1, slot1.transform, null, STWM.AITown.Bridge.AnimationSemantic.TALK_NEUTRAL);
            var semanticObject = root.AddComponent<SemanticObject>();
            semanticObject.Configure(
                "park_conversation_01",
                SemanticObjectType.CONVERSATION_ANCHOR,
                "park",
                true,
                new[] { SemanticCapability.SOCIAL_POSITION },
                slot0,
                slot1);
            return semanticObject;
        }

        private static ActionPresentationParticipant Participant(string agentId, string objectId, int slotIndex)
        {
            return new ActionPresentationParticipant
            {
                AgentId = agentId,
                Role = ActionPresentationRole.PARTICIPANT,
                ObjectSlotBindings = new[]
                {
                    new PresentationObjectSlotBinding { ObjectId = objectId, SlotIndex = slotIndex }
                }
            };
        }

        private GameObject Track(GameObject value)
        {
            roots.Add(value);
            return value;
        }
    }
}
