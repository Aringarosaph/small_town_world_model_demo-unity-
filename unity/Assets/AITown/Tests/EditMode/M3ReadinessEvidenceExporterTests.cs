using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using STWM.AITown.Bridge;
using STWM.AITown.Editor;
using STWM.AITown.Semantic;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class M3ReadinessEvidenceExporterTests
    {
        [Test]
        public void FrameworkCanPassUnityLocalGateButNeverFabricatesM3Acceptance()
        {
            var manifest = M3SemanticManifestDocument.LoadDefault();
            var scan = new TownAssetRegistryScan
            {
                Profile = "M3_FULL",
                ManifestSchema = manifest.Schema,
                Payload = new AssetRegistryPayload
                {
                    Locations = manifest.Locations.Select(item => new RegisteredLocationDto
                    {
                        LocationId = item.LocationId,
                        LocationType = item.LocationType
                    }).ToList(),
                    Objects = manifest.ExpandObjects().Select(item => new RegisteredObjectDto
                    {
                        ObjectId = item.ObjectId,
                        ObjectType = item.ObjectType,
                        LocationId = item.LocationId,
                        InteractionSlots = Enumerable.Range(0, item.SlotCount)
                            .Select(index => new RegisteredInteractionSlotDto { SlotIndex = index })
                            .ToList()
                    }).ToList(),
                    NpcViews = manifest.NpcViewIds.Select(item => new RegisteredNpcViewDto { AgentId = item }).ToList()
                },
                Issues = new List<AssetValidationIssueDto>()
            };
            var routeReport = new M3RouteValidationReport
            {
                EntranceCount = 8,
                SlotCount = 105,
                RouteCount = 840
            };

            var document = M3ReadinessEvidenceExporter.CreateFrameworkDocument(scan, manifest, routeReport);

            Assert.That(document.LocalFixture.Status, Is.EqualTo("PASS"));
            Assert.That(document.Status, Is.EqualTo("PENDING"));
            Assert.That(document.AcceptanceEligible, Is.False);
            Assert.That(document.Protocol030.Status, Is.EqualTo("PASS"));
            Assert.That(document.SimAuthority.Status, Is.EqualTo("PENDING"));
            Assert.That(document.LiveInterop.Status, Is.EqualTo("PENDING"));
            Assert.That(document.ManifestSource, Is.EqualTo("config/v0/semantic_instances.yaml"));
            Assert.That(document.CatalogProtocolVersion, Is.EqualTo("0.1.0"));
            Assert.That(document.PendingReasons, Does.Not.Contain("CONTRACTS_0_3_NOT_INTEGRATED"));
        }
    }
}
