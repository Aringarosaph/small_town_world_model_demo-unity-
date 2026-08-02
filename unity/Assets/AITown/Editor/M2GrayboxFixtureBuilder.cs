using System;
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
    public static class M2GrayboxFixtureBuilder
    {
        public const string ScenePath = "Assets/AITown/Scenes/M2FunctionalGraybox.unity";
        public const string NavMeshDataPath = "Assets/AITown/Scenes/M2FunctionalGrayboxNavMesh.asset";

        private static readonly AnimationSemantic[] FixtureSemantics =
        {
            AnimationSemantic.IDLE,
            AnimationSemantic.WALK,
            AnimationSemantic.SLEEP,
            AnimationSemantic.EAT,
            AnimationSemantic.WORK_STANDING
        };

        [MenuItem("AITown/Create M2 Functional Graybox")]
        public static void CreateFromMenu()
        {
            BuildAndSave();
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<SceneAsset>(ScenePath);
        }

        public static void BuildAndValidateBatch()
        {
            BuildAndSave();
            TownAssetRegistryEditor.ValidateM2Batch();
        }

        public static void BuildAndSave()
        {
            if (Application.unityVersion != TownProtocol.UnityEditorVersion)
            {
                throw new InvalidOperationException($"M2 requires Unity {TownProtocol.UnityEditorVersion}; running {Application.unityVersion}.");
            }

            EditorSettings.serializationMode = SerializationMode.ForceText;
            EnsureFolder("Assets/AITown/Scenes");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            scene.name = "M2FunctionalGraybox";

            var fixtureRoot = new GameObject("STWM_M2_FunctionalGraybox");
            CreateFloor(fixtureRoot.transform);
            CreateLightingAndCamera(fixtureRoot.transform);

            var home = CreateLocation(
                fixtureRoot.transform,
                "home_a",
                SemanticLocationType.HOME,
                "Home A",
                new Vector3(-9f, 0f, 0f),
                new Vector3(-4f, 0f, 0f));
            var cafe = CreateLocation(
                fixtureRoot.transform,
                "cafe_bar",
                SemanticLocationType.CAFE_BAR,
                "Cafe Bar",
                new Vector3(9f, 0f, 0f),
                new Vector3(4f, 0f, 0f));

            var bed = CreateSemanticObject(
                home.transform,
                "home_a_bed_01",
                SemanticObjectType.BED,
                "home_a",
                new[] { SemanticCapability.SLEEP },
                new[] { AnimationSemantic.SLEEP },
                new Vector3(-11f, 0.5f, -2.2f),
                new Vector3(-9.8f, 0f, -2.2f),
                new Vector3(2f, 1f, 1.2f));
            var fridge = CreateSemanticObject(
                home.transform,
                "home_a_fridge_01",
                SemanticObjectType.FRIDGE,
                "home_a",
                new[] { SemanticCapability.FOOD_SOURCE_HOME },
                new[] { AnimationSemantic.IDLE },
                new Vector3(-11f, 0.9f, 2.2f),
                new Vector3(-9.8f, 0f, 2.2f),
                new Vector3(1f, 1.8f, 1f));
            var diningSeat = CreateSemanticObject(
                home.transform,
                "home_a_dining_seat_01",
                SemanticObjectType.DINING_SEAT,
                "home_a",
                new[] { SemanticCapability.SIT, SemanticCapability.EAT },
                new[] { AnimationSemantic.EAT },
                new Vector3(-6.6f, 0.5f, 2.2f),
                new Vector3(-5.6f, 0f, 2.2f),
                new Vector3(0.8f, 1f, 0.8f));
            var workstation = CreateSemanticObject(
                cafe.transform,
                "cafe_bar_workstation_01",
                SemanticObjectType.WORKSTATION,
                "cafe_bar",
                new[] { SemanticCapability.WORK, SemanticCapability.CAFE_MORNING },
                new[] { AnimationSemantic.WORK_STANDING },
                new Vector3(10.5f, 0.6f, 0f),
                new Vector3(9f, 0f, 0f),
                new Vector3(1f, 1.2f, 3f));

            CreateNpc(fixtureRoot.transform);
            CreateBridgeObjects(fixtureRoot.transform);

            var surface = fixtureRoot.AddComponent<NavMeshSurface>();
            surface.BuildNavMesh();
            ValidateFixtureNavigation(
                home.GetComponent<SemanticLocation>(),
                cafe.GetComponent<SemanticLocation>(),
                bed,
                fridge,
                diningSeat,
                workstation);
            PersistNavMeshData(surface);

            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene, ScenePath, true))
            {
                throw new InvalidOperationException($"Failed to save M2 fixture scene at {ScenePath}.");
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.ForceReserializeAssets(
                new[] { ScenePath },
                ForceReserializeAssetsOptions.ReserializeAssetsAndMetadata);
            AssetDatabase.Refresh();
            Debug.Log($"[STWM] Created M2 functional graybox: {ScenePath}");
        }

        private static void PersistNavMeshData(NavMeshSurface surface)
        {
            if (surface.navMeshData == null)
            {
                throw new InvalidOperationException("M2 graybox NavMesh build returned no data.");
            }

            AssetDatabase.DeleteAsset(NavMeshDataPath);
            AssetDatabase.CreateAsset(surface.navMeshData, NavMeshDataPath);
            EditorUtility.SetDirty(surface);
        }

        private static void ValidateFixtureNavigation(
            SemanticLocation home,
            SemanticLocation cafe,
            params SemanticObject[] semanticObjects)
        {
            var homePoint = SampleNavigationPoint(home.PrimaryEntrance.position, home.LocationId);
            var cafePoint = SampleNavigationPoint(cafe.PrimaryEntrance.position, cafe.LocationId);
            RequireCompletePath(homePoint, cafePoint, "home_a -> cafe_bar");
            RequireCompletePath(cafePoint, homePoint, "cafe_bar -> home_a");

            foreach (var semanticObject in semanticObjects)
            {
                foreach (var slot in semanticObject.InteractionSlots)
                {
                    var slotPoint = SampleNavigationPoint(slot.Position, $"{semanticObject.ObjectId}/slot_{slot.SlotIndex}");
                    var locationPoint = semanticObject.LocationId == home.LocationId ? homePoint : cafePoint;
                    RequireCompletePath(
                        locationPoint,
                        slotPoint,
                        $"{semanticObject.LocationId} -> {semanticObject.ObjectId}/slot_{slot.SlotIndex}");
                }
            }
        }

        private static Vector3 SampleNavigationPoint(Vector3 desired, string entityId)
        {
            if (!NavMesh.SamplePosition(desired, out var hit, 2f, NavMesh.AllAreas))
            {
                throw new InvalidOperationException($"M2 navigation point is outside NavMesh: {entityId} at {desired}.");
            }

            return hit.position;
        }

        private static void RequireCompletePath(Vector3 from, Vector3 to, string route)
        {
            var path = new NavMeshPath();
            if (!NavMesh.CalculatePath(from, to, NavMesh.AllAreas, path)
                || path.status != NavMeshPathStatus.PathComplete)
            {
                throw new InvalidOperationException($"M2 graybox route is not fully reachable: {route} ({path.status}).");
            }
        }

        private static GameObject CreateLocation(
            Transform parent,
            string locationId,
            SemanticLocationType type,
            string displayName,
            Vector3 markerPosition,
            Vector3 entrancePosition)
        {
            var root = new GameObject(locationId);
            root.transform.SetParent(parent);
            root.transform.position = markerPosition;
            var entrance = new GameObject("EntranceAnchor");
            entrance.transform.SetParent(root.transform);
            entrance.transform.position = entrancePosition;
            root.AddComponent<SemanticLocation>().Configure(locationId, type, displayName, entrance.transform);

            var marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            marker.name = "LocationMarker";
            marker.transform.SetParent(root.transform);
            marker.transform.position = markerPosition + new Vector3(0f, 0.05f, 0f);
            marker.transform.localScale = new Vector3(5.5f, 0.1f, 5.5f);
            UnityEngine.Object.DestroyImmediate(marker.GetComponent<Collider>());
            return root;
        }

        private static SemanticObject CreateSemanticObject(
            Transform parent,
            string objectId,
            SemanticObjectType objectType,
            string locationId,
            SemanticCapability[] capabilities,
            AnimationSemantic[] semantics,
            Vector3 objectPosition,
            Vector3 slotPosition,
            Vector3 scale)
        {
            var visual = GameObject.CreatePrimitive(PrimitiveType.Cube);
            visual.name = objectId;
            visual.transform.SetParent(parent);
            visual.transform.position = objectPosition;
            visual.transform.localScale = scale;

            var slotObject = new GameObject("InteractionSlot_0");
            slotObject.transform.SetParent(visual.transform);
            slotObject.transform.position = slotPosition;
            slotObject.transform.rotation = Quaternion.LookRotation(objectPosition - slotPosition, Vector3.up);
            var slot = slotObject.AddComponent<InteractionSlot>();
            slot.Configure(0, slotObject.transform, visual.transform, semantics);

            var semanticObject = visual.AddComponent<SemanticObject>();
            semanticObject.Configure(objectId, objectType, locationId, true, capabilities, slot);
            return semanticObject;
        }

        private static void CreateNpc(Transform parent)
        {
            var npc = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            npc.name = "npc_01";
            npc.transform.SetParent(parent);
            npc.transform.position = new Vector3(-8f, 1f, 0f);
            UnityEngine.Object.DestroyImmediate(npc.GetComponent<Collider>());

            var agent = npc.AddComponent<NavMeshAgent>();
            agent.radius = 0.35f;
            agent.height = 1.8f;
            agent.speed = 3.5f;
            agent.angularSpeed = 720f;
            agent.acceleration = 12f;
            agent.stoppingDistance = 0.12f;

            var navigation = npc.AddComponent<NpcNavigationController>();
            navigation.Configure(agent, 20f);
            var animation = npc.AddComponent<NpcAnimationDriver>();
            animation.ConfigureFallbackMappings(FixtureSemantics);
            var view = npc.AddComponent<NpcView>();
            view.Configure("npc_01", navigation, animation);
        }

        private static void CreateBridgeObjects(Transform parent)
        {
            var bridgeObject = new GameObject("TownBridge");
            bridgeObject.transform.SetParent(parent);
            var panel = bridgeObject.AddComponent<TownDebugPanel>();
            var bridge = bridgeObject.AddComponent<TownBridgeClient>();
            bridge.Configure("ws://127.0.0.1:8765/ws", TownProtocol.DefaultWorldId, false);
            bridgeObject.AddComponent<TownRecordedMessagePlayer>();
            // TownBridgeClient discovers the panel in Awake. The local variable keeps
            // the component explicit in the generated scene hierarchy.
            _ = panel;
        }

        private static void CreateFloor(Transform parent)
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "NavigationFloor";
            floor.transform.SetParent(parent);
            floor.transform.position = new Vector3(0f, -0.1f, 0f);
            floor.transform.localScale = new Vector3(30f, 0.2f, 12f);
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
            cameraObject.transform.position = new Vector3(0f, 18f, -18f);
            cameraObject.transform.rotation = Quaternion.Euler(42f, 0f, 0f);
            cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
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
