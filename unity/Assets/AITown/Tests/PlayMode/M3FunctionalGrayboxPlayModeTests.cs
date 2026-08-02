using System.Collections;
using System.Linq;
using NUnit.Framework;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace STWM.AITown.Tests.PlayMode
{
    public sealed class M3FunctionalGrayboxPlayModeTests
    {
        [UnityTearDown]
        public IEnumerator TearDown()
        {
            var m3Scene = SceneManager.GetSceneByName("M3FunctionalGraybox");
            if (m3Scene.IsValid() && m3Scene.isLoaded)
            {
                var cleanup = SceneManager.CreateScene("M3PlayModeCleanup");
                SceneManager.SetActiveScene(cleanup);
                yield return SceneManager.UnloadSceneAsync(m3Scene);
            }
        }

        [UnityTest]
        public IEnumerator FullTownFixtureLoadsWithStrictSemanticAndRouteCoverage()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);

            var scan = TownSceneAssetRegistry.ScanFullV0(true);
            Assert.That(scan.HasErrors, Is.False, string.Join("\n", scan.Issues.Select(item => $"{item.Code}/{item.EntityId}")));
            Assert.That(scan.Payload.Locations.Count, Is.EqualTo(8));
            Assert.That(scan.Payload.NpcViews.Count, Is.EqualTo(10));
            Assert.That(scan.Payload.Objects.Select(item => item.ObjectType).Distinct().Count(), Is.EqualTo(15));
            Assert.That(scan.Payload.Objects.Sum(item => item.InteractionSlots.Count), Is.EqualTo(105));
        }

        [UnityTest]
        public IEnumerator ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing()
        {
            yield return SceneManager.LoadSceneAsync("M3FunctionalGraybox", LoadSceneMode.Single);
            var group = new ActionPresentationGroup("action_900", new[]
            {
                new ActionPresentationParticipant
                {
                    AgentId = "npc_02",
                    Role = ActionPresentationRole.TARGET,
                    FacingAgentId = "npc_01",
                    ObjectSlotBindings = new[]
                    {
                        new PresentationObjectSlotBinding { ObjectId = "park_conversation_anchor_01", SlotIndex = 1 }
                    }
                },
                new ActionPresentationParticipant
                {
                    AgentId = "npc_01",
                    Role = ActionPresentationRole.ACTOR,
                    FacingAgentId = "npc_02",
                    ObjectSlotBindings = new[]
                    {
                        new PresentationObjectSlotBinding { ObjectId = "park_conversation_anchor_01", SlotIndex = 0 }
                    }
                }
            });

            Assert.That(group.TryClaimAuthoritativeSlots(out var claimError), Is.True, claimError);
            Assert.That(group.ApplyAuthoritativeFacing("chat", out var facingError), Is.True, facingError);
            Assert.That(group.Claims.Select(item => item.SlotIndex), Is.EqualTo(new[] { 0, 1 }));
            Assert.That(TownSceneAssetRegistry.FindNpcView("npc_01").SocialFacingController.FacingTarget,
                Is.EqualTo(TownSceneAssetRegistry.FindNpcView("npc_02").transform));

            group.ClearFacing();
            group.ReleaseClaims();
            yield return null;
            Assert.That(TownSceneAssetRegistry.FindObject("park_conversation_anchor_01").InteractionSlots
                .All(item => item.LocalPresentationClaimId == null), Is.True);
        }
    }
}
