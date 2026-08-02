using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    /// <summary>
    /// Strict, dependency-free consumer for the CONTRACTS-owned M3 catalog.
    /// The YAML file under config/v0 is the only semantic-instance inventory;
    /// Unity does not copy it into Resources or maintain a second object list.
    /// </summary>
    [Serializable]
    public sealed class M3SemanticManifestDocument
    {
        public const string ExpectedSchema = "stwm.catalog.m3-semantic-instances/v1";
        public const string ExpectedProfile = "M3_FULL";
        public const string ExpectedCatalogProtocolVersion = "0.1.0";
        public const string RepositoryRelativePath = "config/v0/semantic_instances.yaml";

        [JsonProperty("schema")]
        public string Schema { get; set; }

        [JsonProperty("profile")]
        public string Profile { get; set; }

        [JsonProperty("catalog_protocol_version")]
        public string CatalogProtocolVersion { get; set; }

        [JsonProperty("location_ids")]
        public List<string> LocationIds { get; set; } = new List<string>();

        [JsonProperty("npc_view_ids")]
        public List<string> NpcViewIds { get; set; } = new List<string>();

        [JsonProperty("objects")]
        public List<M3ObjectDefinition> Objects { get; set; } = new List<M3ObjectDefinition>();

        [JsonProperty("required_animation_semantics")]
        public List<string> RequiredAnimationSemantics { get; set; } = new List<string>();

        [JsonProperty("required_prop_semantics")]
        public List<string> RequiredPropSemantics { get; set; } = new List<string>();

        [JsonProperty("facing_behavior_ids")]
        public List<string> FacingBehaviorIds { get; set; } = new List<string>();

        [JsonProperty("require_entrance_slot_reachability")]
        public bool RequireEntranceSlotReachability { get; set; }

        [JsonIgnore]
        public string SourcePath { get; private set; }

        [JsonIgnore]
        public string SharedContractManifestStatus => "CONSUMED_CONTRACTS_0_3";

        [JsonIgnore]
        public IReadOnlyList<M3LocationDefinition> Locations => LocationIds
            .Select(M3PresentationLayout.CreateLocation)
            .ToArray();

        [JsonIgnore]
        public IReadOnlyList<M3NpcDefinition> Npcs
        {
            get
            {
                var assignedHomes = Objects
                    .Where(item => string.Equals(item.ObjectType, "BED", StringComparison.Ordinal)
                                   && !string.IsNullOrEmpty(item.AssignedAgentId))
                    .ToDictionary(item => item.AssignedAgentId, item => item.LocationId, StringComparer.Ordinal);
                return NpcViewIds.Select(agentId => new M3NpcDefinition
                {
                    AgentId = agentId,
                    HomeLocationId = assignedHomes.TryGetValue(agentId, out var home) ? home : null
                }).ToArray();
            }
        }

        public IReadOnlyList<M3ObjectDefinition> ExpandObjects()
        {
            return Objects.OrderBy(item => item.ObjectId, StringComparer.Ordinal).ToArray();
        }

        public void ValidateDefinition()
        {
            if (!string.Equals(Schema, ExpectedSchema, StringComparison.Ordinal)
                || !string.Equals(Profile, ExpectedProfile, StringComparison.Ordinal)
                || !string.Equals(CatalogProtocolVersion, ExpectedCatalogProtocolVersion, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"M3 semantic manifest identity mismatch: {Schema}/{Profile}/{CatalogProtocolVersion}.");
            }

            if (LocationIds.Count != 8 || NpcViewIds.Count != 10 || Objects.Count != 74)
            {
                throw new InvalidOperationException("M3 semantic manifest requires exactly 8 locations, 10 NPC views, and 74 objects.");
            }

            RequireUnique(LocationIds, "location IDs");
            RequireUnique(NpcViewIds, "NPC view IDs");
            RequireUnique(Objects.Select(item => item.ObjectId), "object IDs");
            if (Objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count() != 15
                || Objects.Sum(item => item.SlotCount) != 105)
            {
                throw new InvalidOperationException("M3 semantic manifest must cover 15 object types and 105 slots.");
            }

            var locationSet = new HashSet<string>(LocationIds, StringComparer.Ordinal);
            var npcSet = new HashSet<string>(NpcViewIds, StringComparer.Ordinal);
            foreach (var item in Objects)
            {
                if (string.IsNullOrWhiteSpace(item.ObjectType)
                    || !locationSet.Contains(item.LocationId)
                    || item.SlotCount <= 0
                    || item.CapabilityTags.Length == 0
                    || item.AnimationSemantics.Length == 0
                    || (!string.IsNullOrEmpty(item.AssignedAgentId) && !npcSet.Contains(item.AssignedAgentId)))
                {
                    throw new InvalidOperationException($"Invalid M3 semantic object definition: {item.ObjectId}.");
                }

                RequireUnique(item.CapabilityTags, $"capabilities for {item.ObjectId}");
                RequireUnique(item.AnimationSemantics, $"animation semantics for {item.ObjectId}");
            }

            RequireUnique(RequiredAnimationSemantics, "required animation semantics");
            RequireUnique(RequiredPropSemantics, "required prop semantics");
            RequireUnique(FacingBehaviorIds, "facing behavior IDs");
            if (RequiredAnimationSemantics.Count != 14
                || RequiredPropSemantics.Count != 4
                || FacingBehaviorIds.Count != 8
                || !RequireEntranceSlotReachability)
            {
                throw new InvalidOperationException("M3 semantic manifest presentation coverage is incomplete.");
            }

            var bedOwners = Objects
                .Where(item => string.Equals(item.ObjectType, "BED", StringComparison.Ordinal))
                .Select(item => item.AssignedAgentId)
                .ToArray();
            RequireUnique(bedOwners, "assigned bed agents");
            if (!new HashSet<string>(bedOwners, StringComparer.Ordinal).SetEquals(npcSet))
            {
                throw new InvalidOperationException("Every M3 NPC must have exactly one authoritative assigned bed.");
            }
        }

        public static M3SemanticManifestDocument LoadDefault()
        {
            var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", RepositoryRelativePath));
            if (!File.Exists(path))
            {
                throw new InvalidOperationException($"Missing CONTRACTS-owned M3 semantic manifest at {path}.");
            }

            return Parse(File.ReadAllText(path), path);
        }

        public static M3SemanticManifestDocument Parse(string yaml, string sourcePath = RepositoryRelativePath)
        {
            if (string.IsNullOrWhiteSpace(yaml))
            {
                throw new InvalidOperationException("M3 semantic manifest is empty.");
            }

            var document = new M3SemanticManifestDocument { SourcePath = sourcePath };
            foreach (var rawLine in yaml.Replace("\r\n", "\n").Split('\n'))
            {
                var line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal) || line == "objects:")
                {
                    continue;
                }

                if (line.StartsWith("- {", StringComparison.Ordinal) && line.EndsWith("}", StringComparison.Ordinal))
                {
                    document.Objects.Add(ParseObject(line.Substring(3, line.Length - 4)));
                    continue;
                }

                var separator = line.IndexOf(':');
                if (separator <= 0)
                {
                    throw new InvalidOperationException($"Unsupported M3 manifest YAML line: {line}");
                }

                var key = line.Substring(0, separator).Trim();
                var value = line.Substring(separator + 1).Trim();
                switch (key)
                {
                    case "schema": document.Schema = value; break;
                    case "profile": document.Profile = value; break;
                    case "catalog_protocol_version": document.CatalogProtocolVersion = value; break;
                    case "location_ids": document.LocationIds = ParseList(value); break;
                    case "npc_view_ids": document.NpcViewIds = ParseList(value); break;
                    case "required_animation_semantics": document.RequiredAnimationSemantics = ParseList(value); break;
                    case "required_prop_semantics": document.RequiredPropSemantics = ParseList(value); break;
                    case "facing_behavior_ids": document.FacingBehaviorIds = ParseList(value); break;
                    case "require_entrance_slot_reachability":
                        if (!bool.TryParse(value, out var required))
                        {
                            throw new InvalidOperationException("require_entrance_slot_reachability must be boolean.");
                        }
                        document.RequireEntranceSlotReachability = required;
                        break;
                    default: throw new InvalidOperationException($"Unknown M3 manifest field: {key}");
                }
            }

            document.ValidateDefinition();
            return document;
        }

        private static M3ObjectDefinition ParseObject(string content)
        {
            var fields = SplitTopLevel(content).Select(part =>
            {
                var separator = part.IndexOf(':');
                if (separator <= 0)
                {
                    throw new InvalidOperationException($"Invalid M3 object field: {part}");
                }
                return new KeyValuePair<string, string>(part.Substring(0, separator).Trim(), part.Substring(separator + 1).Trim());
            }).ToDictionary(item => item.Key, item => item.Value, StringComparer.Ordinal);

            var allowed = new HashSet<string>(new[]
            {
                "object_id", "object_type", "location_id", "capability_tags", "slot_count",
                "supported_animation_semantics", "assigned_agent_id"
            }, StringComparer.Ordinal);
            if (fields.Keys.Any(key => !allowed.Contains(key)))
            {
                throw new InvalidOperationException("Unknown M3 semantic object field.");
            }

            foreach (var required in allowed.Where(item => item != "assigned_agent_id"))
            {
                if (!fields.ContainsKey(required))
                {
                    throw new InvalidOperationException($"M3 semantic object is missing {required}.");
                }
            }

            if (!int.TryParse(fields["slot_count"], NumberStyles.None, CultureInfo.InvariantCulture, out var slotCount))
            {
                throw new InvalidOperationException("M3 semantic object slot_count must be an integer.");
            }

            return new M3ObjectDefinition
            {
                ObjectId = fields["object_id"],
                ObjectType = fields["object_type"],
                LocationId = fields["location_id"],
                CapabilityTags = ParseList(fields["capability_tags"]).ToArray(),
                SlotCount = slotCount,
                AnimationSemantics = ParseList(fields["supported_animation_semantics"]).ToArray(),
                AssignedAgentId = fields.TryGetValue("assigned_agent_id", out var assigned) ? assigned : null
            };
        }

        private static List<string> ParseList(string value)
        {
            if (value.Length < 2 || value[0] != '[' || value[value.Length - 1] != ']')
            {
                throw new InvalidOperationException($"Expected inline YAML list, received {value}.");
            }

            var content = value.Substring(1, value.Length - 2).Trim();
            return content.Length == 0
                ? new List<string>()
                : content.Split(',').Select(item => item.Trim()).ToList();
        }

        private static IEnumerable<string> SplitTopLevel(string content)
        {
            var start = 0;
            var depth = 0;
            for (var index = 0; index < content.Length; index++)
            {
                if (content[index] == '[') depth++;
                if (content[index] == ']') depth--;
                if (content[index] == ',' && depth == 0)
                {
                    yield return content.Substring(start, index - start).Trim();
                    start = index + 1;
                }
            }
            yield return content.Substring(start).Trim();
        }

        private static void RequireUnique(IEnumerable<string> values, string label)
        {
            var materialized = values.ToArray();
            if (materialized.Any(string.IsNullOrWhiteSpace)
                || materialized.Distinct(StringComparer.Ordinal).Count() != materialized.Length)
            {
                throw new InvalidOperationException($"M3 semantic manifest {label} must be non-empty and unique.");
            }
        }
    }

    internal static class M3PresentationLayout
    {
        public static M3LocationDefinition CreateLocation(string locationId, int index)
        {
            var column = index % 4;
            var row = index / 4;
            return new M3LocationDefinition
            {
                LocationId = locationId,
                LocationType = LocationType(locationId).ToString(),
                DisplayName = locationId,
                X = -18f + column * 12f,
                Z = row == 0 ? 8f : -8f
            };
        }

        private static SemanticLocationType LocationType(string locationId)
        {
            if (locationId.StartsWith("home_", StringComparison.Ordinal)) return SemanticLocationType.HOME;
            if (locationId == "cafe_bar") return SemanticLocationType.CAFE_BAR;
            if (locationId == "shop") return SemanticLocationType.SHOP;
            if (locationId == "workshop") return SemanticLocationType.WORKPLACE;
            if (locationId == "park") return SemanticLocationType.PARK;
            throw new InvalidOperationException($"Unknown M3 location ID {locationId}.");
        }
    }

    public sealed class M3LocationDefinition
    {
        public string LocationId { get; set; }
        public string LocationType { get; set; }
        public string DisplayName { get; set; }
        public float X { get; set; }
        public float Z { get; set; }
    }

    public sealed class M3NpcDefinition
    {
        public string AgentId { get; set; }
        public string HomeLocationId { get; set; }
    }

    public sealed class M3ObjectDefinition
    {
        public string ObjectId { get; set; }
        public string ObjectType { get; set; }
        public string LocationId { get; set; }
        public string[] CapabilityTags { get; set; } = Array.Empty<string>();
        public int SlotCount { get; set; }
        public string[] AnimationSemantics { get; set; } = Array.Empty<string>();
        public string AssignedAgentId { get; set; }
    }
}
