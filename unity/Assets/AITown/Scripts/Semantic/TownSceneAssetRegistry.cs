using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    public sealed class TownAssetRegistryScan
    {
        public AssetRegistryPayload Payload { get; set; }
        public List<AssetValidationIssueDto> Issues { get; set; }
        public bool HasErrors => Issues.Any(issue => issue.Severity == AssetValidationSeverity.ERROR.ToString());
    }

    public static class TownSceneAssetRegistry
    {
        private static readonly string[] FullV0LocationIds =
        {
            "home_a", "home_b", "home_c", "home_d", "cafe_bar", "shop", "workshop", "park"
        };

        public static TownAssetRegistryScan ScanM2Fixture()
        {
            var locations = FindLocations();
            var objects = FindObjects();
            var views = FindNpcViews();
            var drivers = FindAnimationDrivers();
            var issues = new List<AssetValidationIssueDto>();

            AddDuplicateIssues(locations, item => item.LocationId, "DUPLICATE_LOCATION_ID", issues);
            AddDuplicateIssues(objects, item => item.ObjectId, "DUPLICATE_OBJECT_ID", issues);
            AddDuplicateIssues(views, item => item.AgentId, "DUPLICATE_AGENT_ID", issues);

            RequireLocation(locations, "home_a", issues);
            RequireLocation(locations, "cafe_bar", issues);
            RequireNpc(views, "npc_01", issues);
            foreach (var view in views)
            {
                if (view.NavigationController == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_NAVIGATION_CONTROLLER", "NpcView has no navigation controller.", view.AgentId);
                }

                if (view.AnimationDriver == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_ANIMATION_DRIVER", "NpcView has no animation-semantic adapter.", view.AgentId);
                }
            }
            RequireObject(objects, "home_a", SemanticObjectType.BED, new[] { SemanticCapability.SLEEP }, issues);
            RequireObject(objects, "home_a", SemanticObjectType.FRIDGE, new[] { SemanticCapability.FOOD_SOURCE_HOME }, issues);
            RequireObject(objects, "home_a", SemanticObjectType.DINING_SEAT, new[] { SemanticCapability.EAT }, issues);
            RequireObject(
                objects,
                "cafe_bar",
                SemanticObjectType.WORKSTATION,
                new[] { SemanticCapability.WORK, SemanticCapability.CAFE_MORNING },
                issues);

            foreach (var location in locations)
            {
                if (location.PrimaryEntrance == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_ENTRANCE_ANCHOR", "Location has no entrance/navigation anchor.", location.LocationId);
                }
            }

            foreach (var semanticObject in objects)
            {
                ValidateObject(semanticObject, locations, issues);
            }

            foreach (var fullLocation in FullV0LocationIds)
            {
                if (locations.All(item => item.LocationId != fullLocation))
                {
                    AddIssue(
                        issues,
                        AssetValidationSeverity.WARNING,
                        "FULL_V0_LOCATION_MISSING",
                        "Not blocking in M2; required by the complete M3 registry profile.",
                        fullLocation);
                }
            }

            foreach (SemanticObjectType fullObjectType in Enum.GetValues(typeof(SemanticObjectType)))
            {
                if (objects.All(item => item.ObjectType != fullObjectType))
                {
                    AddIssue(
                        issues,
                        AssetValidationSeverity.WARNING,
                        "FULL_V0_OBJECT_TYPE_MISSING",
                        "Not blocking in M2; required by the complete M3 registry profile.",
                        fullObjectType.ToString());
                }
            }

            var mapped = new HashSet<string>(StringComparer.Ordinal);
            foreach (var driver in drivers)
            {
                foreach (var semantic in driver.MappedSemantics)
                {
                    mapped.Add(semantic.ToString());
                }
            }

            RequireAnimation(mapped, AnimationSemantic.IDLE, issues);
            RequireAnimation(mapped, AnimationSemantic.WALK, issues);
            RequireAnimation(mapped, AnimationSemantic.SLEEP, issues);
            RequireAnimation(mapped, AnimationSemantic.EAT, issues);
            if (!mapped.Contains(AnimationSemantic.WORK_DESK.ToString())
                && !mapped.Contains(AnimationSemantic.WORK_STANDING.ToString())
                && !mapped.Contains(AnimationSemantic.WORK_WORKSHOP.ToString()))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_WORK_ANIMATION", "Map at least one frozen work animation semantic.", "npc_01");
            }

            issues.Sort(CompareIssues);
            return new TownAssetRegistryScan
            {
                Payload = new AssetRegistryPayload
                {
                    Locations = locations
                        .Where(item => !string.IsNullOrEmpty(item.LocationId))
                        .Select(item => new RegisteredLocationDto
                        {
                            LocationId = item.LocationId,
                            LocationType = item.LocationType.ToString()
                        })
                        .ToList(),
                    Objects = objects
                        .Where(item => !string.IsNullOrEmpty(item.ObjectId))
                        .Select(ToRegisteredObject)
                        .ToList(),
                    NpcViews = views
                        .Where(item => !string.IsNullOrEmpty(item.AgentId))
                        .Select(item => new RegisteredNpcViewDto { AgentId = item.AgentId })
                        .ToList(),
                    MappedAnimationSemantics = mapped.OrderBy(item => item, StringComparer.Ordinal).ToList()
                },
                Issues = issues
            };
        }

        public static SemanticLocation[] FindLocations()
        {
            return UnityEngine.Object.FindObjectsByType<SemanticLocation>(
                    FindObjectsInactive.Include,
                    FindObjectsSortMode.None)
                .OrderBy(item => item.LocationId, StringComparer.Ordinal)
                .ThenBy(item => item.GetInstanceID())
                .ToArray();
        }

        public static SemanticObject[] FindObjects()
        {
            return UnityEngine.Object.FindObjectsByType<SemanticObject>(
                    FindObjectsInactive.Include,
                    FindObjectsSortMode.None)
                .OrderBy(item => item.ObjectId, StringComparer.Ordinal)
                .ThenBy(item => item.GetInstanceID())
                .ToArray();
        }

        public static NpcView[] FindNpcViews()
        {
            return UnityEngine.Object.FindObjectsByType<NpcView>(
                    FindObjectsInactive.Include,
                    FindObjectsSortMode.None)
                .OrderBy(item => item.AgentId, StringComparer.Ordinal)
                .ThenBy(item => item.GetInstanceID())
                .ToArray();
        }

        public static NpcAnimationDriver[] FindAnimationDrivers()
        {
            return UnityEngine.Object.FindObjectsByType<NpcAnimationDriver>(
                    FindObjectsInactive.Include,
                    FindObjectsSortMode.None)
                .OrderBy(item => item.GetInstanceID())
                .ToArray();
        }

        public static NpcView FindNpcView(string agentId)
        {
            return FindNpcViews().FirstOrDefault(item => string.Equals(item.AgentId, agentId, StringComparison.Ordinal));
        }

        public static NpcView FindNpcViewByAction(string actionId)
        {
            return FindNpcViews().FirstOrDefault(item => string.Equals(item.CurrentActionId, actionId, StringComparison.Ordinal));
        }

        public static SemanticObject FindObject(string objectId)
        {
            return FindObjects().FirstOrDefault(item => string.Equals(item.ObjectId, objectId, StringComparison.Ordinal));
        }

        public static SemanticLocation FindLocation(string locationId)
        {
            return FindLocations().FirstOrDefault(item => string.Equals(item.LocationId, locationId, StringComparison.Ordinal));
        }

        private static RegisteredObjectDto ToRegisteredObject(SemanticObject item)
        {
            return new RegisteredObjectDto
            {
                ObjectId = item.ObjectId,
                ObjectType = item.ObjectType.ToString(),
                LocationId = item.LocationId,
                CapabilityTags = item.CapabilityTags.Select(value => value.ToString()).OrderBy(value => value, StringComparer.Ordinal).ToList(),
                Enabled = item.SemanticEnabled,
                InteractionSlots = item.InteractionSlots
                    .Where(slot => slot != null)
                    .OrderBy(slot => slot.SlotIndex)
                    .Select(slot => new RegisteredInteractionSlotDto
                    {
                        SlotIndex = slot.SlotIndex,
                        SupportedAnimationSemantics = slot.SupportedAnimationSemantics
                            .Select(value => value.ToString())
                            .OrderBy(value => value, StringComparer.Ordinal)
                            .ToList()
                    })
                    .ToList()
            };
        }

        private static void ValidateObject(
            SemanticObject semanticObject,
            IReadOnlyCollection<SemanticLocation> locations,
            ICollection<AssetValidationIssueDto> issues)
        {
            if (string.IsNullOrWhiteSpace(semanticObject.ObjectId))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "EMPTY_OBJECT_ID", "Semantic object ID is empty.", semanticObject.name);
            }

            if (locations.All(item => item.LocationId != semanticObject.LocationId))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "UNKNOWN_OBJECT_LOCATION", "Object location has no SemanticLocation binding.", semanticObject.ObjectId);
            }

            if (semanticObject.CapabilityTags.Count == 0)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_CAPABILITY", "Object has no frozen capability tag.", semanticObject.ObjectId);
            }

            if (semanticObject.InteractionSlots.Count == 0)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_INTERACTION_SLOT", "Object has no interaction slot.", semanticObject.ObjectId);
            }

            var slotIndexes = new HashSet<int>();
            foreach (var slot in semanticObject.InteractionSlots)
            {
                if (slot == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "NULL_INTERACTION_SLOT", "Object contains a missing slot reference.", semanticObject.ObjectId);
                }
                else if (!slotIndexes.Add(slot.SlotIndex))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "DUPLICATE_SLOT_INDEX", $"Duplicate slot index {slot.SlotIndex}.", semanticObject.ObjectId);
                }
            }
        }

        private static void RequireLocation(
            IEnumerable<SemanticLocation> locations,
            string locationId,
            ICollection<AssetValidationIssueDto> issues)
        {
            if (locations.All(item => item.LocationId != locationId))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M2_LOCATION_MISSING", "Required M2 SemanticLocation is missing.", locationId);
            }
        }

        private static void RequireNpc(
            IEnumerable<NpcView> views,
            string agentId,
            ICollection<AssetValidationIssueDto> issues)
        {
            if (views.All(item => item.AgentId != agentId))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M2_NPC_VIEW_MISSING", "Required M2 NpcView is missing.", agentId);
            }
        }

        private static void RequireObject(
            IEnumerable<SemanticObject> objects,
            string locationId,
            SemanticObjectType objectType,
            IEnumerable<SemanticCapability> capabilities,
            ICollection<AssetValidationIssueDto> issues)
        {
            var required = capabilities.ToArray();
            var match = objects.FirstOrDefault(item => item.LocationId == locationId
                                                       && item.ObjectType == objectType
                                                       && required.All(item.HasCapability)
                                                       && item.InteractionSlots.Count > 0);
            if (match == null)
            {
                AddIssue(
                    issues,
                    AssetValidationSeverity.ERROR,
                    "M2_OBJECT_BINDING_MISSING",
                    $"Required {objectType} with [{string.Join(",", required)}] and a slot is missing at {locationId}.",
                    locationId);
            }
        }

        private static void RequireAnimation(
            ISet<string> mapped,
            AnimationSemantic semantic,
            ICollection<AssetValidationIssueDto> issues)
        {
            if (!mapped.Contains(semantic.ToString()))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_ANIMATION_SEMANTIC", "Required M2 animation semantic is not mapped.", semantic.ToString());
            }
        }

        private static void AddDuplicateIssues<T>(
            IEnumerable<T> values,
            Func<T, string> keySelector,
            string code,
            ICollection<AssetValidationIssueDto> issues)
        {
            foreach (var group in values.Where(item => !string.IsNullOrWhiteSpace(keySelector(item)))
                         .GroupBy(keySelector, StringComparer.Ordinal)
                         .Where(group => group.Count() > 1))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, code, $"Semantic ID occurs {group.Count()} times.", group.Key);
            }
        }

        private static void AddIssue(
            ICollection<AssetValidationIssueDto> issues,
            AssetValidationSeverity severity,
            string code,
            string message,
            string entityId)
        {
            issues.Add(new AssetValidationIssueDto
            {
                Severity = severity.ToString(),
                Code = code,
                Message = message,
                EntityId = entityId
            });
        }

        private static int CompareIssues(AssetValidationIssueDto left, AssetValidationIssueDto right)
        {
            var severity = SeverityRank(left.Severity).CompareTo(SeverityRank(right.Severity));
            if (severity != 0)
            {
                return severity;
            }

            var code = string.Compare(left.Code, right.Code, StringComparison.Ordinal);
            return code != 0 ? code : string.Compare(left.EntityId, right.EntityId, StringComparison.Ordinal);
        }

        private static int SeverityRank(string severity)
        {
            if (severity == AssetValidationSeverity.ERROR.ToString())
            {
                return 0;
            }

            return severity == AssetValidationSeverity.WARNING.ToString() ? 1 : 2;
        }
    }
}
