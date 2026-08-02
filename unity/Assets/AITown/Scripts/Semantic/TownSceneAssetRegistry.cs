using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.NPC;
using UnityEngine;
using UnityEngine.AI;

namespace STWM.AITown.Semantic
{
    public sealed class TownAssetRegistryScan
    {
        public string Profile { get; set; }
        public string ManifestSchema { get; set; }
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
                Profile = "M2_SCOPED",
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

        public static TownAssetRegistryScan ScanFullV0(
            bool validateRoutes = true,
            M3SemanticManifestDocument manifest = null)
        {
            manifest = manifest ?? M3SemanticManifestDocument.LoadDefault();
            manifest.ValidateDefinition();
            var locations = FindLocations();
            var objects = FindObjects();
            var views = FindNpcViews();
            var drivers = FindAnimationDrivers();
            var issues = new List<AssetValidationIssueDto>();

            AddDuplicateIssues(locations, item => item.LocationId, "DUPLICATE_LOCATION_ID", issues);
            AddDuplicateIssues(objects, item => item.ObjectId, "DUPLICATE_OBJECT_ID", issues);
            AddDuplicateIssues(views, item => item.AgentId, "DUPLICATE_AGENT_ID", issues);

            var expectedLocations = manifest.Locations.ToDictionary(item => item.LocationId, StringComparer.Ordinal);
            foreach (var expected in expectedLocations.Values)
            {
                var actual = locations.FirstOrDefault(item => string.Equals(item.LocationId, expected.LocationId, StringComparison.Ordinal));
                if (actual == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_LOCATION_MISSING", "Required M3 SemanticLocation is missing.", expected.LocationId);
                    continue;
                }

                if (!string.Equals(actual.LocationType.ToString(), expected.LocationType, StringComparison.Ordinal))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_LOCATION_TYPE_MISMATCH", $"Expected {expected.LocationType}, received {actual.LocationType}.", expected.LocationId);
                }

                if (actual.PrimaryEntrance == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_ENTRANCE_ANCHOR", "Location has no entrance/navigation anchor.", actual.LocationId);
                }
            }

            foreach (var unexpected in locations.Where(item => !expectedLocations.ContainsKey(item.LocationId)))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_UNKNOWN_LOCATION", "Location is outside the frozen M3 manifest.", unexpected.LocationId);
            }

            var expectedAgents = new HashSet<string>(manifest.Npcs.Select(item => item.AgentId), StringComparer.Ordinal);
            foreach (var agentId in expectedAgents)
            {
                var view = views.FirstOrDefault(item => string.Equals(item.AgentId, agentId, StringComparison.Ordinal));
                if (view == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_NPC_VIEW_MISSING", "Required M3 NpcView is missing.", agentId);
                    continue;
                }

                ValidateFullNpcView(view, manifest, issues);
            }

            foreach (var unexpected in views.Where(item => !expectedAgents.Contains(item.AgentId)))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_UNKNOWN_NPC_VIEW", "NpcView is outside the frozen M3 manifest.", unexpected.AgentId);
            }

            var expectedObjects = manifest.ExpandObjects().ToDictionary(item => item.ObjectId, StringComparer.Ordinal);
            foreach (var expected in expectedObjects.Values)
            {
                var actual = objects.FirstOrDefault(item => string.Equals(item.ObjectId, expected.ObjectId, StringComparison.Ordinal));
                if (actual == null)
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_OBJECT_MISSING", "Required M3 semantic object is missing.", expected.ObjectId);
                    continue;
                }

                ValidateFullObject(actual, expected, locations, issues);
            }

            foreach (var unexpected in objects.Where(item => !expectedObjects.ContainsKey(item.ObjectId)))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_UNKNOWN_OBJECT", "Semantic object is outside the frozen M3 manifest.", unexpected.ObjectId);
            }

            var mapped = new HashSet<string>(
                drivers.SelectMany(item => item.MappedSemantics).Select(item => item.ToString()),
                StringComparer.Ordinal);
            foreach (var semantic in manifest.RequiredAnimationSemantics)
            {
                if (!mapped.Contains(semantic))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_ANIMATION_SEMANTIC_MISSING", "Required M3 animation semantic is not mapped.", semantic);
                }
            }

            if (validateRoutes)
            {
                issues.AddRange(M3RouteValidator.Validate(locations, objects).Issues);
                foreach (var view in views)
                {
                    if (!NavMesh.SamplePosition(view.transform.position, out _, 2f, NavMesh.AllAreas))
                    {
                        AddIssue(issues, AssetValidationSeverity.ERROR, "M3_NPC_OFF_NAVMESH", "NpcView start point is outside the baked NavMesh.", view.AgentId);
                    }
                }
            }

            issues.Sort(CompareIssues);
            return new TownAssetRegistryScan
            {
                Profile = "M3_FULL",
                ManifestSchema = manifest.Schema,
                Payload = BuildPayload(locations, objects, views, mapped),
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

        private static AssetRegistryPayload BuildPayload(
            IEnumerable<SemanticLocation> locations,
            IEnumerable<SemanticObject> objects,
            IEnumerable<NpcView> views,
            IEnumerable<string> mapped)
        {
            return new AssetRegistryPayload
            {
                Locations = locations
                    .Where(item => !string.IsNullOrEmpty(item.LocationId))
                    .OrderBy(item => item.LocationId, StringComparer.Ordinal)
                    .Select(item => new RegisteredLocationDto
                    {
                        LocationId = item.LocationId,
                        LocationType = item.LocationType.ToString()
                    })
                    .ToList(),
                Objects = objects
                    .Where(item => !string.IsNullOrEmpty(item.ObjectId))
                    .OrderBy(item => item.ObjectId, StringComparer.Ordinal)
                    .Select(ToRegisteredObject)
                    .ToList(),
                NpcViews = views
                    .Where(item => !string.IsNullOrEmpty(item.AgentId))
                    .OrderBy(item => item.AgentId, StringComparer.Ordinal)
                    .Select(item => new RegisteredNpcViewDto { AgentId = item.AgentId })
                    .ToList(),
                MappedAnimationSemantics = mapped.OrderBy(item => item, StringComparer.Ordinal).ToList()
            };
        }

        private static void ValidateFullNpcView(
            NpcView view,
            M3SemanticManifestDocument manifest,
            ICollection<AssetValidationIssueDto> issues)
        {
            if (view.NavigationController == null)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_NAVIGATION_CONTROLLER", "NpcView has no navigation controller.", view.AgentId);
            }

            if (view.GetComponent<NavMeshAgent>() == null)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_NAVMESH_AGENT_MISSING", "NpcView has no NavMeshAgent presentation component.", view.AgentId);
            }

            if (view.AnimationDriver == null)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "MISSING_ANIMATION_DRIVER", "NpcView has no animation-semantic adapter.", view.AgentId);
            }
            else
            {
                var mapped = new HashSet<string>(view.AnimationDriver.MappedSemantics.Select(item => item.ToString()), StringComparer.Ordinal);
                foreach (var semantic in manifest.RequiredAnimationSemantics.Where(item => !mapped.Contains(item)))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_NPC_ANIMATION_MISSING", "NpcView cannot present a required behavior animation.", $"{view.AgentId}/{semantic}");
                }
            }

            if (view.PropPresenter == null)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_PROP_PRESENTER_MISSING", "NpcView has no prop-semantic presenter.", view.AgentId);
            }
            else
            {
                var props = new HashSet<string>(view.PropPresenter.SupportedSemantics.Select(item => item.ToString()), StringComparer.Ordinal);
                foreach (var semantic in manifest.RequiredPropSemantics.Where(item => !props.Contains(item)))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_PROP_SEMANTIC_MISSING", "NpcView cannot present a required prop semantic.", $"{view.AgentId}/{semantic}");
                }
            }

            if (view.SocialFacingController == null)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_FACING_CONTROLLER_MISSING", "NpcView has no social-facing controller.", view.AgentId);
            }
            else
            {
                foreach (var behaviorId in manifest.FacingBehaviorIds.Where(item => !view.SocialFacingController.SupportsBehavior(item)))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_FACING_BEHAVIOR_MISSING", "NpcView cannot face its authoritative social target.", $"{view.AgentId}/{behaviorId}");
                }
            }
        }

        private static void ValidateFullObject(
            SemanticObject actual,
            M3ObjectDefinition expected,
            IReadOnlyCollection<SemanticLocation> locations,
            ICollection<AssetValidationIssueDto> issues)
        {
            ValidateObject(actual, locations, issues);
            if (!string.Equals(actual.ObjectType.ToString(), expected.ObjectType, StringComparison.Ordinal))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_OBJECT_TYPE_MISMATCH", $"Expected {expected.ObjectType}, received {actual.ObjectType}.", expected.ObjectId);
            }

            if (!string.Equals(actual.LocationId, expected.LocationId, StringComparison.Ordinal))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_OBJECT_LOCATION_MISMATCH", $"Expected {expected.LocationId}, received {actual.LocationId}.", expected.ObjectId);
            }

            if (!actual.SemanticEnabled)
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_OBJECT_DISABLED", "Required M3 semantic object is disabled.", expected.ObjectId);
            }

            var actualCapabilities = new HashSet<string>(actual.CapabilityTags.Select(item => item.ToString()), StringComparer.Ordinal);
            if (!actualCapabilities.SetEquals(expected.CapabilityTags))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_OBJECT_CAPABILITY_MISMATCH", $"Expected [{string.Join(",", expected.CapabilityTags)}].", expected.ObjectId);
            }

            var actualSlots = actual.InteractionSlots.Where(item => item != null).OrderBy(item => item.SlotIndex).ToArray();
            if (actualSlots.Length != expected.SlotCount
                || !actualSlots.Select(item => item.SlotIndex).SequenceEqual(Enumerable.Range(0, expected.SlotCount)))
            {
                AddIssue(issues, AssetValidationSeverity.ERROR, "M3_DEFAULT_SLOT_COUNT_MISMATCH", $"Expected contiguous slots 0..{expected.SlotCount - 1}.", expected.ObjectId);
            }

            var requiredSemantics = new HashSet<string>(expected.AnimationSemantics, StringComparer.Ordinal);
            foreach (var slot in actualSlots)
            {
                var actualSemantics = new HashSet<string>(slot.SupportedAnimationSemantics.Select(item => item.ToString()), StringComparer.Ordinal);
                if (!actualSemantics.SetEquals(requiredSemantics))
                {
                    AddIssue(issues, AssetValidationSeverity.ERROR, "M3_SLOT_ANIMATION_MISMATCH", $"Expected [{string.Join(",", expected.AnimationSemantics)}].", $"{expected.ObjectId}/slot_{slot.SlotIndex}");
                }
            }
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
