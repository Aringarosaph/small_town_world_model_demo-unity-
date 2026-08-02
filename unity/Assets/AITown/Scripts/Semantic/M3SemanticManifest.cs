using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace STWM.AITown.Semantic
{
    [Serializable]
    public sealed class M3SemanticManifestDocument
    {
        public const string ExpectedSchema = "stwm.unity.m3-functional-graybox-manifest/v1";
        public const string ResourcePath = "M3FunctionalGrayboxManifest";

        [JsonProperty("schema", Required = Required.Always)]
        public string Schema { get; set; }

        [JsonProperty("baseline_commit", Required = Required.Always)]
        public string BaselineCommit { get; set; }

        [JsonProperty("shared_contract_manifest_status", Required = Required.Always)]
        public string SharedContractManifestStatus { get; set; }

        [JsonProperty("locations", Required = Required.Always)]
        public List<M3LocationDefinition> Locations { get; set; } = new List<M3LocationDefinition>();

        [JsonProperty("npcs", Required = Required.Always)]
        public List<M3NpcDefinition> Npcs { get; set; } = new List<M3NpcDefinition>();

        [JsonProperty("object_groups", Required = Required.Always)]
        public List<M3ObjectGroupDefinition> ObjectGroups { get; set; } = new List<M3ObjectGroupDefinition>();

        [JsonProperty("required_animation_semantics", Required = Required.Always)]
        public List<string> RequiredAnimationSemantics { get; set; } = new List<string>();

        [JsonProperty("required_prop_semantics", Required = Required.Always)]
        public List<string> RequiredPropSemantics { get; set; } = new List<string>();

        [JsonProperty("facing_behavior_ids", Required = Required.Always)]
        public List<string> FacingBehaviorIds { get; set; } = new List<string>();

        public IReadOnlyList<M3ObjectDefinition> ExpandObjects()
        {
            var result = new List<M3ObjectDefinition>();
            foreach (var group in ObjectGroups)
            {
                for (var offset = 0; offset < group.Count; offset++)
                {
                    result.Add(new M3ObjectDefinition
                    {
                        ObjectId = $"{group.IdPrefix}{group.FirstIndex + offset:00}",
                        ObjectType = group.ObjectType,
                        LocationId = group.LocationId,
                        CapabilityTags = group.CapabilityTags.ToArray(),
                        SlotCount = group.SlotCount,
                        AnimationSemantics = group.AnimationSemantics.ToArray()
                    });
                }
            }

            return result.OrderBy(item => item.ObjectId, StringComparer.Ordinal).ToArray();
        }

        public void ValidateDefinition()
        {
            if (!string.Equals(Schema, ExpectedSchema, StringComparison.Ordinal))
            {
                throw new InvalidOperationException($"M3 semantic manifest schema must be {ExpectedSchema}; received {Schema}.");
            }

            if (!string.Equals(BaselineCommit, "2a51615", StringComparison.Ordinal))
            {
                throw new InvalidOperationException("M3 semantic manifest must identify frozen baseline 2a51615.");
            }

            if (Locations.Count != 8 || Npcs.Count != 10)
            {
                throw new InvalidOperationException("M3 semantic manifest requires exactly 8 locations and 10 NPCs.");
            }

            RequireUnique(Locations.Select(item => item.LocationId), "location IDs");
            RequireUnique(Npcs.Select(item => item.AgentId), "NPC IDs");
            var objects = ExpandObjects();
            RequireUnique(objects.Select(item => item.ObjectId), "object IDs");
            if (objects.Select(item => item.ObjectType).Distinct(StringComparer.Ordinal).Count() != 15)
            {
                throw new InvalidOperationException("M3 semantic manifest must cover exactly 15 object types.");
            }

            if (ObjectGroups.Any(item => item.Count <= 0 || item.FirstIndex <= 0 || item.SlotCount <= 0))
            {
                throw new InvalidOperationException("M3 object groups require positive counts, indices, and slot counts.");
            }

            var locationIds = new HashSet<string>(Locations.Select(item => item.LocationId), StringComparer.Ordinal);
            if (Npcs.Any(item => !locationIds.Contains(item.HomeLocationId))
                || objects.Any(item => !locationIds.Contains(item.LocationId)))
            {
                throw new InvalidOperationException("M3 manifest NPCs and objects must reference registered locations.");
            }

            RequireUnique(RequiredAnimationSemantics, "required animation semantics");
            RequireUnique(RequiredPropSemantics, "required prop semantics");
            RequireUnique(FacingBehaviorIds, "facing behavior IDs");
        }

        public static M3SemanticManifestDocument LoadDefault()
        {
            var asset = Resources.Load<TextAsset>(ResourcePath);
            if (asset == null)
            {
                throw new InvalidOperationException($"Missing Resources/{ResourcePath}.json.");
            }

            return Parse(asset.text);
        }

        public static M3SemanticManifestDocument Parse(string json)
        {
            var manifest = JsonConvert.DeserializeObject<M3SemanticManifestDocument>(json)
                           ?? throw new InvalidOperationException("Could not deserialize M3 semantic manifest.");
            manifest.ValidateDefinition();
            return manifest;
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

    [Serializable]
    public sealed class M3LocationDefinition
    {
        [JsonProperty("location_id", Required = Required.Always)]
        public string LocationId { get; set; }

        [JsonProperty("location_type", Required = Required.Always)]
        public string LocationType { get; set; }

        [JsonProperty("display_name", Required = Required.Always)]
        public string DisplayName { get; set; }

        [JsonProperty("x", Required = Required.Always)]
        public float X { get; set; }

        [JsonProperty("z", Required = Required.Always)]
        public float Z { get; set; }
    }

    [Serializable]
    public sealed class M3NpcDefinition
    {
        [JsonProperty("agent_id", Required = Required.Always)]
        public string AgentId { get; set; }

        [JsonProperty("home_location_id", Required = Required.Always)]
        public string HomeLocationId { get; set; }
    }

    [Serializable]
    public sealed class M3ObjectGroupDefinition
    {
        [JsonProperty("id_prefix", Required = Required.Always)]
        public string IdPrefix { get; set; }

        [JsonProperty("first_index", Required = Required.Always)]
        public int FirstIndex { get; set; }

        [JsonProperty("count", Required = Required.Always)]
        public int Count { get; set; }

        [JsonProperty("object_type", Required = Required.Always)]
        public string ObjectType { get; set; }

        [JsonProperty("location_id", Required = Required.Always)]
        public string LocationId { get; set; }

        [JsonProperty("capability_tags", Required = Required.Always)]
        public List<string> CapabilityTags { get; set; } = new List<string>();

        [JsonProperty("slot_count", Required = Required.Always)]
        public int SlotCount { get; set; }

        [JsonProperty("animation_semantics", Required = Required.Always)]
        public List<string> AnimationSemantics { get; set; } = new List<string>();
    }

    public sealed class M3ObjectDefinition
    {
        public string ObjectId { get; set; }
        public string ObjectType { get; set; }
        public string LocationId { get; set; }
        public string[] CapabilityTags { get; set; }
        public int SlotCount { get; set; }
        public string[] AnimationSemantics { get; set; }
    }
}
