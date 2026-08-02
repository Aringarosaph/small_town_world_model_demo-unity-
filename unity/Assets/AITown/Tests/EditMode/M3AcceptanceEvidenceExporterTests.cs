using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using STWM.AITown.Editor;
using System.Xml;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class M3AcceptanceEvidenceExporterTests
    {
        private string tempDirectory;

        [SetUp]
        public void SetUp()
        {
            tempDirectory = Path.Combine(Path.GetTempPath(), "stwm-m3-exporter-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDirectory);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(tempDirectory))
            {
                Directory.Delete(tempDirectory, true);
            }
        }

        [Test]
        public void RealAdapterShapeIsAcceptedButExplicitlyHasNoSlowSoak()
        {
            var document = MinimalSimReadiness();

            Assert.DoesNotThrow(() => M3AcceptanceEvidenceExporter.ValidateSimReadiness(document));
            Assert.That(document["soak_plan"]["full_slow_soak_executed"].Value<bool>(), Is.False);
        }

        [Test]
        public void FailedOrShapeDriftedAdapterEvidenceIsRejected()
        {
            var failed = MinimalSimReadiness();
            failed["passed"] = false;
            Assert.Throws<InvalidDataException>(() => M3AcceptanceEvidenceExporter.ValidateSimReadiness(failed));

            var drifted = MinimalSimReadiness();
            drifted["synthetic_claim"] = true;
            Assert.Throws<InvalidDataException>(() => M3AcceptanceEvidenceExporter.ValidateSimReadiness(drifted));

            var obsoleteQaSchema = MinimalSimReadiness();
            obsoleteQaSchema["schema"] = "stwm.qa.m3-readiness/v1";
            Assert.Throws<InvalidDataException>(() => M3AcceptanceEvidenceExporter.ValidateSimReadiness(obsoleteQaSchema));
        }

        [Test]
        public void ZeroSkipXmlRequiresEveryNamedLiveAndPresentationCase()
        {
            var path = WriteXml(
                3,
                3,
                0,
                0,
                0,
                "Live030PythonBridgeCompletesFullRegistrySnapshotTopKAndReconnectWhenEnabled",
                "ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing",
                "Recorded030HandshakeRebindsSnapshotThenClearsAndReleasesJointPresentation");

            var summary = M3AcceptanceEvidenceExporter.ValidateTestResults(path, new[]
            {
                "Live030PythonBridgeCompletesFullRegistrySnapshotTopKAndReconnectWhenEnabled",
                "ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing",
                "Recorded030HandshakeRebindsSnapshotThenClearsAndReleasesJointPresentation"
            });

            Assert.That(summary.Passed, Is.EqualTo(3));
            Assert.That(summary.RequiredCases, Has.Count.EqualTo(3));
        }

        [Test]
        public void AnySkippedTestBlocksPartialEvidenceExport()
        {
            var path = WriteXml(2, 1, 0, 1, 0, "passed_case", "ignored_case");

            Assert.Throws<InvalidDataException>(() =>
                M3AcceptanceEvidenceExporter.ValidateTestResults(path, Array.Empty<string>()));
        }

        [Test]
        public void MachineLocalXmlAttributePathUsesMarkupSafePlaceholderAndRevalidates()
        {
            var source = WriteXml(1, 1, 0, 0, 0, "live_case");
            var sourceText = File.ReadAllText(source)
                .Replace("STWM.Tests.live_case", "/Users/producer/project/live_case.dll");
            File.WriteAllText(source, sourceText);
            var destination = Path.Combine(tempDirectory, "sanitized.xml");

            var summary = M3AcceptanceEvidenceExporter.CopySanitizedXmlTestResults(
                source,
                destination,
                Array.Empty<string>());

            var sanitized = File.ReadAllText(destination);
            Assert.That(summary.Passed, Is.EqualTo(1));
            Assert.That(sanitized, Does.Contain("USER_HOME/project/live_case.dll"));
            Assert.That(sanitized, Does.Not.Contain("/Users/"));
            Assert.That(sanitized, Does.Not.Contain("<USER_HOME>"));
            Assert.DoesNotThrow(() => new XmlDocument().Load(destination));
        }

        [Test]
        public void LiteralAngleBracketPlaceholderInsideAttributeIsRejectedAsMalformedXml()
        {
            var source = WriteXml(1, 1, 0, 0, 0, "live_case");
            var malformed = File.ReadAllText(source)
                .Replace("STWM.Tests.live_case", "<REPOSITORY_ROOT>/live_case.dll");
            File.WriteAllText(source, malformed);
            var destination = Path.Combine(tempDirectory, "must-not-exist.xml");

            Assert.Throws<XmlException>(() =>
                M3AcceptanceEvidenceExporter.CopySanitizedXmlTestResults(
                    source,
                    destination,
                    Array.Empty<string>()));
            Assert.That(File.Exists(destination), Is.False);
        }

        [Test]
        public void QaProjectionUsesExactPassedCasesForFrozenUnityAndBehaviorMatrices()
        {
            var editCases = ProjectionEditCases();
            var playCases = ProjectionPlayCases();
            var editPath = WriteXml(editCases.Length, editCases.Length, 0, 0, 0, editCases);
            var playPath = WriteXml(playCases.Length, playCases.Length, 0, 0, 0, playCases);
            var editSummary = M3AcceptanceEvidenceExporter.ValidateTestResults(editPath, Array.Empty<string>());
            var playSummary = M3AcceptanceEvidenceExporter.ValidateTestResults(playPath, Array.Empty<string>());

            var projection = M3AcceptanceEvidenceExporter.CreateQaMatrixProjection(
                MinimalSemanticCoverage(),
                editPath,
                playPath,
                editSummary,
                playSummary);

            CollectionAssert.AreEquivalent(
                new[] { "unity", "behavior_presentation" },
                projection.Properties().Select(item => item.Name));
            var unity = (JObject)projection["unity"];
            Assert.That(unity.Properties().Count(), Is.EqualTo(18));
            Assert.That(unity.Value<int>("npc_views"), Is.EqualTo(10));
            Assert.That(unity.Value<int>("duplicate_slot_claim_count"), Is.Zero);
            Assert.That(unity.Value<string>("live_smoke_protocol_version"), Is.EqualTo("0.3.0"));
            var rows = (JArray)projection["behavior_presentation"];
            CollectionAssert.AreEqual(BehaviorIds, rows.Select(item => item.Value<string>("behavior_id")));
            foreach (var row in rows.Children<JObject>())
            {
                CollectionAssert.AreEquivalent(
                    new[] { "behavior_id", "fixture_id", "unity_presentation" },
                    row.Properties().Select(item => item.Name));
                var behaviorId = row.Value<string>("behavior_id");
                Assert.That(row.Value<string>("fixture_id"), Is.EqualTo("m3_behavior_" + behaviorId));
                var probe = (JObject)row["unity_presentation"];
                CollectionAssert.AreEquivalent(
                    new[] { "status", "test_ids", "assertion_count" },
                    probe.Properties().Select(item => item.Name));
                Assert.That(probe.Value<string>("status"), Is.EqualTo("PASS"));
                Assert.That(probe.Value<int>("assertion_count"), Is.GreaterThan(0));
                Assert.That(
                    probe["test_ids"].Single().Value<string>(),
                    Does.EndWith("BehaviorPresentation_" + behaviorId));
            }
        }

        [Test]
        public void QaProjectionRejectsMissingPerBehaviorPresentationResult()
        {
            var editCases = ProjectionEditCases()
                .Where(item => item != "BehaviorPresentation_confront")
                .ToArray();
            var playCases = ProjectionPlayCases();
            var editPath = WriteXml(editCases.Length, editCases.Length, 0, 0, 0, editCases);
            var playPath = WriteXml(playCases.Length, playCases.Length, 0, 0, 0, playCases);

            Assert.Throws<InvalidDataException>(() => M3AcceptanceEvidenceExporter.CreateQaMatrixProjection(
                MinimalSemanticCoverage(),
                editPath,
                playPath,
                M3AcceptanceEvidenceExporter.ValidateTestResults(editPath, Array.Empty<string>()),
                M3AcceptanceEvidenceExporter.ValidateTestResults(playPath, Array.Empty<string>())));
        }

        private static readonly string[] BehaviorIds =
        {
            "idle", "sleep", "eat_at_home", "shower", "watch_tv", "relax_at_home",
            "work_shift", "take_break", "buy_groceries", "eat_at_cafe", "drink_at_bar",
            "walk_in_park", "sit_in_park", "greet", "chat", "joke", "compliment",
            "share_event", "invite_join", "apologize", "confront", "end_conversation"
        };

        private static string[] ProjectionEditCases()
        {
            return new[]
            {
                "ExplicitNullDeltaClearsEveryNullableNpcPresentationCache",
                "FrozenStructuredActionAndReconnectExamplesValidate",
                "FrozenTopKExampleEnforcesSelectedAcceptedTuple",
                "PropPresenterAndTenNpcSelectorRemainReadOnlyPresentationState",
                "ActionPresentationGroupSortsParticipantsAndClaimsDistinctSlotsAtomically",
                "ConflictingParticipantBindingRollsBackWholeLocalClaimSet"
            }.Concat(BehaviorIds.Select(item => "BehaviorPresentation_" + item)).ToArray();
        }

        private static string[] ProjectionPlayCases()
        {
            return new[]
            {
                "Live030PythonBridgeCompletesFullRegistrySnapshotTopKAndReconnectWhenEnabled",
                "ExplicitJointPresentationBindingsClaimStableDistinctSlotsAndFacing",
                "Recorded030HandshakeRebindsSnapshotThenClearsAndReleasesJointPresentation",
                "Stale030DeltaIsRejectedWithoutPresentationMutation",
                "RecordedJointPresentationCancelAndFailReleaseClaims",
                "FullTownFixtureLoadsWithStrictSemanticAndRouteCoverage"
            };
        }

        private static JObject MinimalSemanticCoverage()
        {
            var animations = new JArray(
                "IDLE", "SLEEP", "EAT", "SHOWER_HIDDEN", "SIT", "WORK_DESK", "WORK_STANDING",
                "WORK_WORKSHOP", "DRINK", "WALK", "TALK_NEUTRAL", "TALK_POSITIVE", "TALK_NEGATIVE",
                "CARRY_GROCERY");
            var props = new JArray("MEAL", "GROCERY_BAG", "DRINK", "EVENT_ICON");
            var facing = new JArray(
                "greet", "chat", "joke", "compliment", "share_event", "invite_join", "apologize", "confront");
            return new JObject
            {
                ["schema"] = "stwm.unity.m3-semantic-coverage/v1",
                ["status"] = "PASS",
                ["profile"] = "M3_FULL",
                ["npc_views"] = 10,
                ["locations"] = 8,
                ["object_types"] = 15,
                ["interaction_slots"] = 105,
                ["required_animation_semantics"] = animations,
                ["mapped_animation_semantics"] = animations.DeepClone(),
                ["required_prop_semantics"] = props,
                ["mapped_prop_semantics"] = props.DeepClone(),
                ["facing_behavior_ids"] = facing,
                ["mapped_facing_behavior_ids"] = facing.DeepClone(),
                ["route_count"] = 840,
                ["route_errors"] = 0,
                ["structured_joint_clear_reconnect_covered_by_playmode"] = true
            };
        }

        private string WriteXml(
            int total,
            int passed,
            int failed,
            int skipped,
            int inconclusive,
            params string[] cases)
        {
            var root = new XElementBuilder("test-run")
                .Attribute("result", failed == 0 && skipped == 0 && inconclusive == 0 ? "Passed" : "Failed")
                .Attribute("total", total)
                .Attribute("passed", passed)
                .Attribute("failed", failed)
                .Attribute("skipped", skipped)
                .Attribute("inconclusive", inconclusive);
            for (var index = 0; index < cases.Length; index++)
            {
                root.Child(new XElementBuilder("test-case")
                    .Attribute("name", cases[index])
                    .Attribute("fullname", $"STWM.Tests.{cases[index]}")
                    .Attribute("result", index < passed ? "Passed" : "Skipped"));
            }

            var path = Path.Combine(tempDirectory, Guid.NewGuid().ToString("N") + ".xml");
            File.WriteAllText(path, root.ToString());
            return path;
        }

        private static JObject MinimalSimReadiness()
        {
            return new JObject
            {
                ["schema"] = "stwm.simulation.m3-readiness-evidence/v1",
                ["project_name"] = "Small Town World Model（STWM）",
                ["generated_at_utc"] = "2026-08-02T12:00:00Z",
                ["passed"] = true,
                ["scenario"] = new JObject
                {
                    ["days"] = 1,
                    ["enabled_agent_ids"] = new JArray(
                        "npc_01", "npc_02", "npc_03", "npc_04", "npc_05",
                        "npc_06", "npc_07", "npc_08", "npc_09", "npc_10"),
                    ["seed"] = 12345,
                    ["semantic_profile"] = "M3_FULL"
                },
                ["protocol"] = new JObject
                {
                    ["active_negotiated_protocol_version"] = "0.3.0",
                    ["catalog_protocol_version"] = "0.1.0",
                    ["checkpoint_schema"] = "stwm.simulation.m3-authority-checkpoint/v1"
                },
                ["runs"] = new JArray(),
                ["determinism"] = new JObject { ["all_hashes_match"] = true },
                ["checkpoint_resume"] = new JObject(),
                ["replay"] = new JObject { ["match"] = true },
                ["economy"] = new JObject
                {
                    ["all_equations_match"] = true,
                    ["resources_nonnegative"] = true,
                    ["settlement_keys_unique"] = true
                },
                ["bridge"] = new JObject
                {
                    ["catalog_protocol_version"] = "0.1.0",
                    ["client_ready_gate_observed"] = true,
                    ["first_generation_message_counts"] = new JObject
                    {
                        ["action_started"] = 1,
                        ["agent_state_delta"] = 1,
                        ["debug_decision_trace"] = 1
                    },
                    ["first_generation_ready"] = true,
                    ["fresh_snapshot_covers_all_active_actions"] = true,
                    ["fresh_snapshot_not_older_than_prior_generation"] = true,
                    ["fresh_snapshot_state_version"] = 1,
                    ["negotiated_protocol_version"] = "0.3.0",
                    ["new_generation_ready_before_ack"] = false,
                    ["obsolete_generation_rejected"] = true,
                    ["reconnect_generation"] = 2,
                    ["semantic_profile"] = "M3_FULL",
                    ["sessions"] = new JArray()
                },
                ["cli_contract"] = new JObject(),
                ["soak_plan"] = new JObject
                {
                    ["fixed_30_day_seeds"] = new JArray(12345, 24680, 97531),
                    ["fixed_7_day_seeds"] = new JArray(12345, 24680, 97531, 314159, 271828),
                    ["full_slow_soak_executed"] = false,
                    ["reason"] = "deferred to ORCH"
                }
            };
        }

        private sealed class XElementBuilder
        {
            private readonly string name;
            private readonly System.Collections.Generic.List<string> attributes = new System.Collections.Generic.List<string>();
            private readonly System.Collections.Generic.List<XElementBuilder> children = new System.Collections.Generic.List<XElementBuilder>();

            public XElementBuilder(string elementName)
            {
                name = elementName;
            }

            public XElementBuilder Attribute(string key, object value)
            {
                attributes.Add($"{key}=\"{value}\"");
                return this;
            }

            public XElementBuilder Child(XElementBuilder child)
            {
                children.Add(child);
                return this;
            }

            public override string ToString()
            {
                var prefix = $"<{name} {string.Join(" ", attributes)}";
                return children.Count == 0
                    ? prefix + " />"
                    : prefix + ">" + string.Join(string.Empty, children) + $"</{name}>";
            }
        }
    }
}
