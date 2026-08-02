using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using NUnit.Framework;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
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
                    UnityEngine.Object.DestroyImmediate(root);
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

        [TestCase("idle", "IDLE", "", false, TestName = "BehaviorPresentation_idle")]
        [TestCase("sleep", "SLEEP", "", false, TestName = "BehaviorPresentation_sleep")]
        [TestCase("eat_at_home", "EAT", "MEAL", false, TestName = "BehaviorPresentation_eat_at_home")]
        [TestCase("shower", "SHOWER_HIDDEN", "", false, TestName = "BehaviorPresentation_shower")]
        [TestCase("watch_tv", "SIT", "", false, TestName = "BehaviorPresentation_watch_tv")]
        [TestCase("relax_at_home", "SIT", "", false, TestName = "BehaviorPresentation_relax_at_home")]
        [TestCase("work_shift", "WORK_DESK,WORK_STANDING,WORK_WORKSHOP", "", false, TestName = "BehaviorPresentation_work_shift")]
        [TestCase("take_break", "SIT", "", false, TestName = "BehaviorPresentation_take_break")]
        [TestCase("buy_groceries", "WALK,CARRY_GROCERY", "GROCERY_BAG", false, TestName = "BehaviorPresentation_buy_groceries")]
        [TestCase("eat_at_cafe", "EAT", "MEAL", false, TestName = "BehaviorPresentation_eat_at_cafe")]
        [TestCase("drink_at_bar", "DRINK", "DRINK", false, TestName = "BehaviorPresentation_drink_at_bar")]
        [TestCase("walk_in_park", "WALK", "", false, TestName = "BehaviorPresentation_walk_in_park")]
        [TestCase("sit_in_park", "SIT", "", false, TestName = "BehaviorPresentation_sit_in_park")]
        [TestCase("greet", "TALK_NEUTRAL", "", true, TestName = "BehaviorPresentation_greet")]
        [TestCase("chat", "TALK_NEUTRAL", "", true, TestName = "BehaviorPresentation_chat")]
        [TestCase("joke", "TALK_POSITIVE", "", true, TestName = "BehaviorPresentation_joke")]
        [TestCase("compliment", "TALK_POSITIVE", "", true, TestName = "BehaviorPresentation_compliment")]
        [TestCase("share_event", "TALK_NEUTRAL", "EVENT_ICON", true, TestName = "BehaviorPresentation_share_event")]
        [TestCase("invite_join", "TALK_NEUTRAL", "", true, TestName = "BehaviorPresentation_invite_join")]
        [TestCase("apologize", "TALK_POSITIVE,TALK_NEUTRAL", "", true, TestName = "BehaviorPresentation_apologize")]
        [TestCase("confront", "TALK_NEGATIVE", "", true, TestName = "BehaviorPresentation_confront")]
        [TestCase("end_conversation", "IDLE", "", false, TestName = "BehaviorPresentation_end_conversation")]
        public void BehaviorPresentationMatchesAuthoritativeCatalog(
            string behaviorId,
            string expectedAnimationSemantics,
            string expectedPropSemantic,
            bool expectedFacing)
        {
            var catalog = File.ReadAllText(Path.GetFullPath(
                Path.Combine(Application.dataPath, "..", "..", "config/v0/behaviors.yaml")));
            var behavior = Regex.Match(
                catalog,
                "(?ms)^  - behavior_id: " + Regex.Escape(behaviorId)
                + @"\r?\n(?<body>.*?)(?=^  - behavior_id: |\z)");
            Assert.That(behavior.Success, Is.True, $"Missing authoritative behavior {behaviorId}.");
            var unity = Regex.Match(
                behavior.Groups["body"].Value,
                @"(?m)^    unity: \{animation_semantics: \[(?<animations>[^\]]+)\], requires_facing: (?<facing>true|false), prop_semantic: (?<prop>[A-Z_]+|null)\}$");
            Assert.That(unity.Success, Is.True, $"Missing Unity presentation row for {behaviorId}.");

            var expectedAnimations = expectedAnimationSemantics.Split(',');
            var catalogAnimations = unity.Groups["animations"].Value
                .Split(',')
                .Select(item => item.Trim())
                .ToArray();
            CollectionAssert.AreEqual(expectedAnimations, catalogAnimations);
            Assert.That(unity.Groups["facing"].Value, Is.EqualTo(expectedFacing ? "true" : "false"));
            Assert.That(
                unity.Groups["prop"].Value,
                Is.EqualTo(string.IsNullOrEmpty(expectedPropSemantic) ? "null" : expectedPropSemantic));

            var root = Track(new GameObject("behavior-presentation-" + behaviorId));
            var target = Track(new GameObject("behavior-facing-target-" + behaviorId));
            var animationDriver = root.AddComponent<NpcAnimationDriver>();
            animationDriver.ConfigureFallbackMappings(
                Enum.GetValues(typeof(AnimationSemantic)).Cast<AnimationSemantic>().ToArray());
            var propPresenter = root.AddComponent<NpcPropPresenter>();
            propPresenter.ConfigureMappings(
                Enum.GetValues(typeof(PropSemantic))
                    .Cast<PropSemantic>()
                    .Select(item => new PropSemanticMapping { semantic = item })
                    .ToArray());
            var facing = root.AddComponent<SocialFacingController>();
            facing.ConfigureSupportedBehaviors(new[]
            {
                "greet", "chat", "joke", "compliment", "share_event", "invite_join", "apologize", "confront"
            });
            var view = root.AddComponent<NpcView>();
            view.Configure("npc_01", null, animationDriver, null, propPresenter, facing);

            foreach (var semanticName in catalogAnimations)
            {
                Assert.That(Enum.TryParse(semanticName, out AnimationSemantic semantic), Is.True);
                Assert.That(animationDriver.IsMapped(semantic), Is.True);
                Assert.That(animationDriver.Play(semantic, "action_direct_" + behaviorId, false), Is.True);
                Assert.That(animationDriver.CurrentSemantic, Is.EqualTo(semantic));
            }

            var primaryParticipant = new ActionPresentationParticipant
            {
                AgentId = "npc_01",
                Role = ActionPresentationRole.ACTOR,
                AnimationSemantic = catalogAnimations[0],
                PropSemantic = string.IsNullOrEmpty(expectedPropSemantic) ? null : expectedPropSemantic
            };
            var group = new ActionPresentationGroup("action_" + behaviorId, new[] { primaryParticipant });
            var action = new ActionStartedV030Payload
            {
                ActionId = group.ActionId,
                BehaviorId = behaviorId,
                DestinationLocationId = "park"
            };
            view.BeginActionV030(action, primaryParticipant, group, "PERFORMING");
            Assert.That(view.CurrentBehaviorId, Is.EqualTo(behaviorId));
            Assert.That(view.CurrentPhase, Is.EqualTo("PERFORMING"));
            Assert.That(animationDriver.CurrentSemantic.ToString(), Is.EqualTo(catalogAnimations[0]));
            Assert.That(
                propPresenter.CurrentSemantic?.ToString(),
                Is.EqualTo(string.IsNullOrEmpty(expectedPropSemantic) ? null : expectedPropSemantic));

            Assert.That(facing.SupportsBehavior(behaviorId), Is.EqualTo(expectedFacing));
            Assert.That(
                facing.BeginAuthoritativeFacing(behaviorId, group.ActionId, target.transform),
                Is.EqualTo(expectedFacing));
            Assert.That(facing.FacingTarget, Is.EqualTo(expectedFacing ? target.transform : null));
            facing.Clear(group.ActionId);
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
