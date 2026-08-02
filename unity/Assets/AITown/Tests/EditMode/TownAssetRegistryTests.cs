using System.Linq;
using NUnit.Framework;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class TownAssetRegistryTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            CreateValidInventory();
        }

        [Test]
        public void ValidM2InventoryHasNoBlockingErrorsAndKeepsFullV0Warnings()
        {
            var scan = TownSceneAssetRegistry.ScanM2Fixture();

            Assert.That(scan.HasErrors, Is.False, string.Join("\n", scan.Issues.Select(item => item.Code)));
            Assert.That(scan.Payload.Locations.Select(item => item.LocationId), Is.EqualTo(new[] { "cafe_bar", "home_a" }));
            Assert.That(scan.Payload.NpcViews.Single().AgentId, Is.EqualTo("npc_01"));
            Assert.That(scan.Issues.Any(item => item.Code == "FULL_V0_LOCATION_MISSING"), Is.True);
            Assert.That(scan.Issues.Any(item => item.Code == "FULL_V0_OBJECT_TYPE_MISSING"), Is.True);
        }

        [Test]
        public void DuplicateSemanticIdIsBlockingAndIdentifiesEntity()
        {
            CreateObject(
                "home_a_bed_01",
                SemanticObjectType.BED,
                "home_a",
                new[] { SemanticCapability.SLEEP },
                AnimationSemantic.SLEEP);

            var issue = TownSceneAssetRegistry.ScanM2Fixture().Issues
                .Single(item => item.Code == "DUPLICATE_OBJECT_ID");

            Assert.That(issue.Severity, Is.EqualTo("ERROR"));
            Assert.That(issue.EntityId, Is.EqualTo("home_a_bed_01"));
        }

        [Test]
        public void MissingRequiredCapabilityIsBlocking()
        {
            var workstation = TownSceneAssetRegistry.FindObject("cafe_bar_workstation_01");
            workstation.Configure(
                workstation.ObjectId,
                workstation.ObjectType,
                workstation.LocationId,
                true,
                new[] { SemanticCapability.WORK },
                workstation.InteractionSlots.ToArray());

            var scan = TownSceneAssetRegistry.ScanM2Fixture();

            Assert.That(scan.HasErrors, Is.True);
            Assert.That(scan.Issues.Any(item => item.Code == "M2_OBJECT_BINDING_MISSING" && item.EntityId == "cafe_bar"), Is.True);
        }

        private static void CreateValidInventory()
        {
            CreateLocation("home_a", SemanticLocationType.HOME);
            CreateLocation("cafe_bar", SemanticLocationType.CAFE_BAR);
            CreateObject("home_a_bed_01", SemanticObjectType.BED, "home_a", new[] { SemanticCapability.SLEEP }, AnimationSemantic.SLEEP);
            CreateObject("home_a_fridge_01", SemanticObjectType.FRIDGE, "home_a", new[] { SemanticCapability.FOOD_SOURCE_HOME }, AnimationSemantic.IDLE);
            CreateObject("home_a_dining_seat_01", SemanticObjectType.DINING_SEAT, "home_a", new[] { SemanticCapability.SIT, SemanticCapability.EAT }, AnimationSemantic.EAT);
            CreateObject("cafe_bar_workstation_01", SemanticObjectType.WORKSTATION, "cafe_bar", new[] { SemanticCapability.WORK, SemanticCapability.CAFE_MORNING }, AnimationSemantic.WORK_STANDING);

            var npc = new GameObject("npc_01");
            var navigation = npc.AddComponent<NpcNavigationController>();
            var animation = npc.AddComponent<NpcAnimationDriver>();
            animation.ConfigureFallbackMappings(
                AnimationSemantic.IDLE,
                AnimationSemantic.WALK,
                AnimationSemantic.SLEEP,
                AnimationSemantic.EAT,
                AnimationSemantic.WORK_STANDING);
            npc.AddComponent<NpcView>().Configure("npc_01", navigation, animation);
        }

        private static void CreateLocation(string id, SemanticLocationType type)
        {
            var root = new GameObject(id);
            var entrance = new GameObject("Entrance");
            entrance.transform.SetParent(root.transform);
            root.AddComponent<SemanticLocation>().Configure(id, type, id, entrance.transform);
        }

        private static void CreateObject(
            string id,
            SemanticObjectType type,
            string locationId,
            SemanticCapability[] capabilities,
            AnimationSemantic semantic)
        {
            var root = new GameObject(id);
            var slot = root.AddComponent<InteractionSlot>();
            slot.Configure(0, root.transform, null, semantic);
            root.AddComponent<SemanticObject>().Configure(id, type, locationId, true, capabilities, slot);
        }
    }
}
