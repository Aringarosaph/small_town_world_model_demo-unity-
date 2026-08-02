using System;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using STWM.AITown.Editor;
using STWM.AITown.Semantic;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class M3SemanticManifestTests
    {
        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void ManifestFreezesFullTownCountsAndBaselineCapacities()
        {
            var manifest = M3SemanticManifestDocument.LoadDefault();
            var objects = manifest.ExpandObjects();

            Assert.That(manifest.Schema, Is.EqualTo("stwm.catalog.m3-semantic-instances/v1"));
            Assert.That(manifest.Profile, Is.EqualTo("M3_FULL"));
            Assert.That(manifest.CatalogProtocolVersion, Is.EqualTo("0.1.0"));
            Assert.That(manifest.SharedContractManifestStatus, Is.EqualTo("CONSUMED_CONTRACTS_0_3"));
            Assert.That(manifest.SourcePath, Does.EndWith("config/v0/semantic_instances.yaml"));
            Assert.That(manifest.Locations.Count, Is.EqualTo(8));
            Assert.That(manifest.Npcs.Count, Is.EqualTo(10));
            Assert.That(objects.Select(item => item.ObjectType).Distinct().Count(), Is.EqualTo(15));
            Assert.That(objects.Count, Is.EqualTo(74));
            Assert.That(objects.Sum(item => item.SlotCount), Is.EqualTo(105));
            Assert.That(manifest.RequiredAnimationSemantics.Count, Is.EqualTo(14));
            Assert.That(manifest.RequiredPropSemantics.Count, Is.EqualTo(4));
            Assert.That(manifest.FacingBehaviorIds.Count, Is.EqualTo(8));

            var defaultSlots = new Dictionary<string, int>
            {
                ["BED"] = 1,
                ["FRIDGE"] = 1,
                ["DINING_SEAT"] = 1,
                ["SHOWER"] = 1,
                ["SOFA"] = 2,
                ["TV"] = 4,
                ["WORKSTATION"] = 1,
                ["SHOP_SHELF"] = 2,
                ["CHECKOUT_COUNTER"] = 1,
                ["CAFE_COUNTER"] = 1,
                ["BAR_COUNTER"] = 1,
                ["PUBLIC_SEAT"] = 1,
                ["PARK_ROUTE"] = 8,
                ["LEISURE_SPOT"] = 2,
                ["CONVERSATION_ANCHOR"] = 2
            };
            foreach (var semanticObject in objects)
            {
                Assert.That(semanticObject.SlotCount, Is.EqualTo(defaultSlots[semanticObject.ObjectType]), semanticObject.ObjectId);
            }

            foreach (var home in new[] { "home_a", "home_b", "home_c", "home_d" })
            {
                var residents = manifest.Npcs.Count(item => item.HomeLocationId == home);
                Assert.That(Slots(objects, home, "BED"), Is.EqualTo(residents), home);
                Assert.That(Slots(objects, home, "DINING_SEAT"), Is.EqualTo(residents), home);
                Assert.That(Slots(objects, home, "SOFA"), Is.GreaterThanOrEqualTo(residents), home);
                Assert.That(Count(objects, home, "FRIDGE"), Is.EqualTo(1), home);
                Assert.That(Count(objects, home, "SHOWER"), Is.EqualTo(1), home);
                Assert.That(Count(objects, home, "TV"), Is.EqualTo(1), home);
            }

            Assert.That(CapabilitySlots(objects, "cafe_bar", "CAFE_MORNING"), Is.EqualTo(2));
            Assert.That(CapabilitySlots(objects, "cafe_bar", "CAFE_EVENING"), Is.EqualTo(2));
            Assert.That(CapabilitySlots(objects, "shop", "SHOP"), Is.EqualTo(2));
            Assert.That(CapabilitySlots(objects, "workshop", "WORKSHOP"), Is.EqualTo(4));
            Assert.That(Slots(objects, "park", "PARK_ROUTE"), Is.EqualTo(8));
        }

        [Test]
        public void InMemoryBuilderPassesStrictComponentAndCapacityProfileWithoutRouteGate()
        {
            var manifest = M3SemanticManifestDocument.LoadDefault();
            M3FunctionalGrayboxBuilder.BuildInMemory(false);

            var scan = TownSceneAssetRegistry.ScanFullV0(false, manifest);

            Assert.That(scan.Profile, Is.EqualTo("M3_FULL"));
            Assert.That(scan.HasErrors, Is.False, string.Join("\n", scan.Issues.Select(item => $"{item.Code}/{item.EntityId}")));
            Assert.That(scan.Payload.Locations.Count, Is.EqualTo(8));
            Assert.That(scan.Payload.NpcViews.Count, Is.EqualTo(10));
            Assert.That(scan.Payload.Objects.Count, Is.EqualTo(74));
            Assert.That(TownSceneAssetRegistry.ScanM2Fixture().HasErrors, Is.False, "M2 scoped profile must remain a regression surface.");
        }

        [Test]
        public void MissingPropComponentIsBlockingOnlyInFullProfile()
        {
            var manifest = M3SemanticManifestDocument.LoadDefault();
            M3FunctionalGrayboxBuilder.BuildInMemory(false);
            UnityEngine.Object.DestroyImmediate(TownSceneAssetRegistry.FindNpcView("npc_01").PropPresenter);

            var full = TownSceneAssetRegistry.ScanFullV0(false, manifest);
            var m2 = TownSceneAssetRegistry.ScanM2Fixture();

            Assert.That(full.Issues.Any(item => item.Code == "M3_PROP_PRESENTER_MISSING" && item.EntityId == "npc_01"), Is.True);
            Assert.That(m2.HasErrors, Is.False);
        }

        private static int Count(System.Collections.Generic.IReadOnlyList<M3ObjectDefinition> objects, string location, string type)
        {
            return objects.Count(item => item.LocationId == location && item.ObjectType == type);
        }

        private static int Slots(System.Collections.Generic.IReadOnlyList<M3ObjectDefinition> objects, string location, string type)
        {
            return objects.Where(item => item.LocationId == location && item.ObjectType == type).Sum(item => item.SlotCount);
        }

        private static int CapabilitySlots(System.Collections.Generic.IReadOnlyList<M3ObjectDefinition> objects, string location, string capability)
        {
            return objects.Where(item => item.LocationId == location && item.CapabilityTags.Contains(capability)).Sum(item => item.SlotCount);
        }
    }
}
