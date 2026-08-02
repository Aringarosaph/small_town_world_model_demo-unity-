using System;
using System.Collections.Generic;
using System.Linq;
using STWM.AITown.Animation;
using STWM.AITown.Bridge;
using STWM.AITown.Debugging;
using STWM.AITown.NPC;
using STWM.AITown.Semantic;
using Unity.AI.Navigation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.SceneManagement;

namespace STWM.AITown.Editor
{
    public static class M3FunctionalGrayboxBuilder
    {
        public const string ScenePath = "Assets/AITown/Scenes/M3FunctionalGraybox.unity";
        public const string NavMeshDataPath = "Assets/AITown/Scenes/M3FunctionalGrayboxNavMesh.asset";

        [MenuItem("AITown/M3/Create Functional Graybox")]
        public static void CreateFromMenu()
        {
            BuildAndSave();
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<SceneAsset>(ScenePath);
        }

        public static void BuildAndValidateBatch()
        {
            BuildAndSave();
            TownAssetRegistryEditor.ValidateM3Batch();
        }

        public static void BuildAndSave()
        {
            RequireEditorVersion();
            var surface = BuildInMemory(true);
            PersistNavMeshData(surface);
            var scan = TownSceneAssetRegistry.ScanFullV0(true);
            if (scan.HasErrors)
            {
                throw new InvalidOperationException(
                    "M3 functional graybox failed strict validation:\n"
                    + string.Join("\n", scan.Issues.Where(item => item.Severity == "ERROR")
                        .Select(item => $"{item.Code}: {item.EntityId}")));
            }

            EnsureFolder("Assets/AITown/Scenes");
            var scene = SceneManager.GetActiveScene();
            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene, ScenePath, true))
            {
                throw new InvalidOperationException($"Failed to save M3 fixture scene at {ScenePath}.");
            }

            EnsureSceneInBuildSettings();
            AssetDatabase.SaveAssets();
            AssetDatabase.ForceReserializeAssets(
                new[] { ScenePath },
                ForceReserializeAssetsOptions.ReserializeAssetsAndMetadata);
            AssetDatabase.Refresh();
            Debug.Log($"[STWM] Created M3 functional graybox: {ScenePath}");
        }

        public static NavMeshSurface BuildInMemory(bool buildNavMesh)
        {
            RequireEditorVersion();
            EditorSettings.serializationMode = SerializationMode.ForceText;
            var manifest = M3SemanticManifestDocument.LoadDefault();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            scene.name = "M3FunctionalGraybox";

            var root = new GameObject("STWM_M3_FunctionalGraybox");
            CreateFloor(root.transform);
            CreateLightingAndCamera(root.transform);
            var locations = CreateLocations(root.transform, manifest);
            CreateObjects(locations, manifest);
            CreateNpcs(root.transform, locations, manifest);
            CreateBridgeAndDebug(root.transform, manifest);

            var surface = root.AddComponent<NavMeshSurface>();
            if (buildNavMesh)
            {
                surface.BuildNavMesh();
                if (surface.navMeshData == null)
                {
                    throw new InvalidOperationException("M3 graybox NavMesh build returned no data.");
                }
            }

            return surface;
        }

        private static Dictionary<string, GameObject> CreateLocations(
            Transform parent,
            M3SemanticManifestDocument manifest)
        {
            var result = new Dictionary<string, GameObject>(StringComparer.Ordinal);
            foreach (var definition in manifest.Locations)
            {
                if (!Enum.TryParse(definition.LocationType, out SemanticLocationType locationType))
                {
                    throw new InvalidOperationException($"Unknown M3 location type {definition.LocationType}.");
                }

                var center = new Vector3(definition.X, 0f, definition.Z);
                var location = new GameObject(definition.LocationId);
                location.transform.SetParent(parent);
                location.transform.position = center;
                var entrance = new GameObject("EntranceAnchor");
                entrance.transform.SetParent(location.transform);
                entrance.transform.position = center + new Vector3(0f, 0f, -4f);
                location.AddComponent<SemanticLocation>().Configure(
                    definition.LocationId,
                    locationType,
                    definition.DisplayName,
                    entrance.transform);

                var marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
                marker.name = "LocationMarker";
                marker.transform.SetParent(location.transform);
                marker.transform.position = center + new Vector3(0f, 0.025f, 0f);
                marker.transform.localScale = new Vector3(10f, 0.05f, 8f);
                UnityEngine.Object.DestroyImmediate(marker.GetComponent<Collider>());
                result.Add(definition.LocationId, location);
            }

            return result;
        }

        private static void CreateObjects(
            IReadOnlyDictionary<string, GameObject> locations,
            M3SemanticManifestDocument manifest)
        {
            foreach (var locationGroup in manifest.ExpandObjects().GroupBy(item => item.LocationId))
            {
                var definitions = locationGroup.OrderBy(item => item.ObjectId, StringComparer.Ordinal).ToArray();
                for (var index = 0; index < definitions.Length; index++)
                {
                    var definition = definitions[index];
                    var center = locations[definition.LocationId].transform.position;
                    var row = index / 4;
                    var column = index % 4;
                    var position = center + new Vector3(-2.55f + column * 1.7f, 0.4f, -2.55f + row * 1.7f);
                    CreateSemanticObject(locations[definition.LocationId].transform, definition, position);
                }
            }
        }

        private static SemanticObject CreateSemanticObject(
            Transform parent,
            M3ObjectDefinition definition,
            Vector3 position)
        {
            if (!Enum.TryParse(definition.ObjectType, out SemanticObjectType objectType))
            {
                throw new InvalidOperationException($"Unknown M3 object type {definition.ObjectType}.");
            }

            var capabilities = definition.CapabilityTags
                .Select(item => Enum.TryParse(item, out SemanticCapability value)
                    ? value
                    : throw new InvalidOperationException($"Unknown M3 capability {item}."))
                .ToArray();
            var semantics = definition.AnimationSemantics
                .Select(item => Enum.TryParse(item, out AnimationSemantic value)
                    ? value
                    : throw new InvalidOperationException($"Unknown M3 animation semantic {item}."))
                .ToArray();

            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.name = definition.ObjectId;
            visual.transform.SetParent(parent);
            visual.transform.position = position;
            visual.transform.localScale = ObjectScale(objectType);
            UnityEngine.Object.DestroyImmediate(visual.GetComponent<Collider>());

            var slots = new List<InteractionSlot>();
            for (var index = 0; index < definition.SlotCount; index++)
            {
                var angle = definition.SlotCount == 1
                    ? 0f
                    : index * Mathf.PI * 2f / definition.SlotCount;
                var offset = new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle)) * 0.62f;
                var slotObject = new GameObject($"InteractionSlot_{index}");
                slotObject.transform.SetParent(visual.transform);
                slotObject.transform.position = new Vector3(position.x + offset.x, 0f, position.z + offset.z);
                var slot = slotObject.AddComponent<InteractionSlot>();
                slot.Configure(index, slotObject.transform, visual.transform, semantics);
                slots.Add(slot);
            }

            var semanticObject = visual.AddComponent<SemanticObject>();
            semanticObject.Configure(
                definition.ObjectId,
                objectType,
                definition.LocationId,
                true,
                capabilities,
                slots.ToArray());
            return semanticObject;
        }

        private static void CreateNpcs(
            Transform parent,
            IReadOnlyDictionary<string, GameObject> locations,
            M3SemanticManifestDocument manifest)
        {
            var requiredAnimations = manifest.RequiredAnimationSemantics
                .Select(item => (AnimationSemantic)Enum.Parse(typeof(AnimationSemantic), item))
                .ToArray();
            var requiredProps = manifest.RequiredPropSemantics
                .Select(item => (PropSemantic)Enum.Parse(typeof(PropSemantic), item))
                .ToArray();

            foreach (var homeGroup in manifest.Npcs.GroupBy(item => item.HomeLocationId))
            {
                var members = homeGroup.OrderBy(item => item.AgentId, StringComparer.Ordinal).ToArray();
                for (var index = 0; index < members.Length; index++)
                {
                    var definition = members[index];
                    var center = locations[definition.HomeLocationId].transform.position;
                    var position = center + new Vector3(-1f + index, 1f, 3.1f);
                    CreateNpc(parent, definition.AgentId, position, requiredAnimations, requiredProps, manifest.FacingBehaviorIds);
                }
            }
        }

        private static void CreateNpc(
            Transform parent,
            string agentId,
            Vector3 position,
            AnimationSemantic[] animations,
            PropSemantic[] props,
            IEnumerable<string> facingBehaviors)
        {
            var npc = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            npc.name = agentId;
            npc.transform.SetParent(parent);
            npc.transform.position = position;
            UnityEngine.Object.DestroyImmediate(npc.GetComponent<Collider>());

            var agent = npc.AddComponent<NavMeshAgent>();
            agent.radius = 0.3f;
            agent.height = 1.8f;
            agent.speed = 3.5f;
            agent.angularSpeed = 720f;
            agent.acceleration = 12f;
            agent.stoppingDistance = 0.12f;

            var navigation = npc.AddComponent<NpcNavigationController>();
            navigation.Configure(agent, 30f);
            var animation = npc.AddComponent<NpcAnimationDriver>();
            animation.ConfigureFallbackMappings(animations);
            var propPresenter = npc.AddComponent<NpcPropPresenter>();
            propPresenter.ConfigureMappings(props.Select(item => new PropSemanticMapping
            {
                semantic = item,
                presentationObject = CreatePropPlaceholder(npc.transform, item)
            }).ToArray());
            var facing = npc.AddComponent<SocialFacingController>();
            facing.ConfigureSupportedBehaviors(facingBehaviors);
            var view = npc.AddComponent<NpcView>();
            view.Configure(agentId, navigation, animation, null, propPresenter, facing);
        }

        private static GameObject CreatePropPlaceholder(Transform parent, PropSemantic semantic)
        {
            var primitive = semantic == PropSemantic.EVENT_ICON ? PrimitiveType.Sphere : PrimitiveType.Cube;
            var value = GameObject.CreatePrimitive(primitive);
            value.name = $"Prop_{semantic}";
            value.transform.SetParent(parent);
            value.transform.localPosition = semantic == PropSemantic.EVENT_ICON
                ? new Vector3(0f, 1.45f, 0f)
                : new Vector3(0.35f, 0.65f, 0.25f);
            value.transform.localScale = semantic == PropSemantic.EVENT_ICON
                ? Vector3.one * 0.22f
                : Vector3.one * 0.25f;
            UnityEngine.Object.DestroyImmediate(value.GetComponent<Collider>());
            value.SetActive(false);
            return value;
        }

        private static void CreateBridgeAndDebug(Transform parent, M3SemanticManifestDocument manifest)
        {
            var bridgeObject = new GameObject("TownBridge_M3_PendingProtocol030");
            bridgeObject.transform.SetParent(parent);
            var panel = bridgeObject.AddComponent<TownDebugPanel>();
            panel.SetAvailableAgents(manifest.Npcs.Select(item => item.AgentId));
            var bridge = bridgeObject.AddComponent<TownBridgeClient>();
            bridge.Configure(TownBridgeClient.DefaultEndpointUrl, TownProtocol.DefaultWorldId, false);
            bridge.BindDebugPanel(panel);
            panel.RecordInfo("M3 protocol 0.3/SIM surface: PENDING; auto-connect intentionally disabled.");
        }

        private static Vector3 ObjectScale(SemanticObjectType objectType)
        {
            switch (objectType)
            {
                case SemanticObjectType.BED:
                    return new Vector3(1.2f, 0.35f, 0.7f);
                case SemanticObjectType.WORKSTATION:
                case SemanticObjectType.CAFE_COUNTER:
                case SemanticObjectType.BAR_COUNTER:
                case SemanticObjectType.CHECKOUT_COUNTER:
                    return new Vector3(1.1f, 0.8f, 0.45f);
                case SemanticObjectType.PARK_ROUTE:
                    return new Vector3(1.2f, 0.05f, 1.2f);
                default:
                    return new Vector3(0.65f, 0.7f, 0.65f);
            }
        }

        private static void CreateFloor(Transform parent)
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "NavigationFloor";
            floor.transform.SetParent(parent);
            floor.transform.position = new Vector3(0f, -0.1f, 0f);
            floor.transform.localScale = new Vector3(52f, 0.2f, 36f);
        }

        private static void CreateLightingAndCamera(Transform parent)
        {
            var lightObject = new GameObject("Directional Light");
            lightObject.transform.SetParent(parent);
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.1f;

            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            cameraObject.transform.SetParent(parent);
            cameraObject.transform.position = new Vector3(0f, 34f, -34f);
            cameraObject.transform.rotation = Quaternion.Euler(45f, 0f, 0f);
            cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
        }

        private static void PersistNavMeshData(NavMeshSurface surface)
        {
            EnsureFolder("Assets/AITown/Scenes");
            AssetDatabase.DeleteAsset(NavMeshDataPath);
            AssetDatabase.CreateAsset(surface.navMeshData, NavMeshDataPath);
            EditorUtility.SetDirty(surface);
        }

        private static void EnsureSceneInBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes.ToList();
            if (scenes.All(item => !string.Equals(item.path, ScenePath, StringComparison.Ordinal)))
            {
                scenes.Add(new EditorBuildSettingsScene(ScenePath, true));
                EditorBuildSettings.scenes = scenes.ToArray();
            }
        }

        private static void RequireEditorVersion()
        {
            if (Application.unityVersion != TownProtocol.UnityEditorVersion)
            {
                throw new InvalidOperationException($"M3 requires Unity {TownProtocol.UnityEditorVersion}; running {Application.unityVersion}.");
            }
        }

        private static void EnsureFolder(string path)
        {
            var segments = path.Split('/');
            var current = segments[0];
            for (var index = 1; index < segments.Length; index++)
            {
                var next = $"{current}/{segments[index]}";
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, segments[index]);
                }

                current = next;
            }
        }
    }
}
