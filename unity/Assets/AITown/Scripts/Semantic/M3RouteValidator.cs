using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Bridge;
using UnityEngine;
using UnityEngine.AI;

namespace STWM.AITown.Semantic
{
    public sealed class M3RouteValidationReport
    {
        public int EntranceCount { get; set; }
        public int SlotCount { get; set; }
        public int RouteCount { get; set; }
        public List<AssetValidationIssueDto> Issues { get; set; } = new List<AssetValidationIssueDto>();
        public bool HasErrors => Issues.Any(item => item.Severity == AssetValidationSeverity.ERROR.ToString());
    }

    public static class M3RouteValidator
    {
        private const float SampleRadius = 2f;

        public static M3RouteValidationReport Validate(
            IEnumerable<SemanticLocation> locations,
            IEnumerable<SemanticObject> objects)
        {
            var report = new M3RouteValidationReport();
            var entrances = new List<(string Id, Vector3 Position)>();
            foreach (var location in locations.OrderBy(item => item.LocationId, StringComparer.Ordinal))
            {
                for (var index = 0; index < location.EntranceAnchors.Length; index++)
                {
                    var entrance = location.EntranceAnchors[index];
                    if (entrance == null)
                    {
                        AddError(report, "M3_NULL_ENTRANCE", "Location contains a null entrance anchor.", location.LocationId);
                        continue;
                    }

                    if (!NavMesh.SamplePosition(entrance.position, out var hit, SampleRadius, NavMesh.AllAreas))
                    {
                        AddError(report, "M3_ENTRANCE_OFF_NAVMESH", "Location entrance is outside the baked NavMesh.", $"{location.LocationId}/entrance_{index}");
                        continue;
                    }

                    entrances.Add(($"{location.LocationId}/entrance_{index}", hit.position));
                }
            }

            var slots = new List<(string Id, Vector3 Position)>();
            foreach (var semanticObject in objects.Where(item => item.SemanticEnabled)
                         .OrderBy(item => item.ObjectId, StringComparer.Ordinal))
            {
                foreach (var slot in semanticObject.InteractionSlots.Where(item => item != null)
                             .OrderBy(item => item.SlotIndex))
                {
                    if (!NavMesh.SamplePosition(slot.Position, out var hit, SampleRadius, NavMesh.AllAreas))
                    {
                        AddError(report, "M3_SLOT_OFF_NAVMESH", "Required interaction slot is outside the baked NavMesh.", $"{semanticObject.ObjectId}/slot_{slot.SlotIndex}");
                        continue;
                    }

                    slots.Add(($"{semanticObject.ObjectId}/slot_{slot.SlotIndex}", hit.position));
                }
            }

            report.EntranceCount = entrances.Count;
            report.SlotCount = slots.Count;
            foreach (var entrance in entrances)
            {
                foreach (var slot in slots)
                {
                    report.RouteCount++;
                    var path = new NavMeshPath();
                    if (!NavMesh.CalculatePath(entrance.Position, slot.Position, NavMesh.AllAreas, path)
                        || path.status != NavMeshPathStatus.PathComplete)
                    {
                        AddError(
                            report,
                            "M3_ROUTE_INCOMPLETE",
                            $"Required route is not complete ({path.status}).",
                            $"{entrance.Id}->{slot.Id}");
                    }
                }
            }

            report.Issues.Sort((left, right) => string.Compare(left.EntityId, right.EntityId, StringComparison.Ordinal));
            return report;
        }

        private static void AddError(M3RouteValidationReport report, string code, string message, string entityId)
        {
            report.Issues.Add(new AssetValidationIssueDto
            {
                Severity = AssetValidationSeverity.ERROR.ToString(),
                Code = code,
                Message = message,
                EntityId = entityId
            });
        }
    }
}
