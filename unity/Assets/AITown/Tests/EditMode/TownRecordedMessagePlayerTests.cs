using NUnit.Framework;
using STWM.AITown.Bridge;
using UnityEditor;
using UnityEngine;

namespace STWM.AITown.Tests.EditMode
{
    public sealed class TownRecordedMessagePlayerTests
    {
        [Test]
        public void ReadsJsonArrayAndJsonLinesRecordings()
        {
            const string first = "{\"message_id\":\"msg_1\"}";
            const string second = "{\"message_id\":\"msg_2\"}";

            Assert.That(TownRecordedMessagePlayer.ReadMessages($"[{first},{second}]").Count, Is.EqualTo(2));
            Assert.That(TownRecordedMessagePlayer.ReadMessages($"{first}\n{second}").Count, Is.EqualTo(2));
        }

        [Test]
        public void FrozenM2RecordingUsesValidInboundEnvelopesAndRegistryCorrelation()
        {
            var recording = AssetDatabase.LoadAssetAtPath<TextAsset>(
                "Assets/AITown/Tests/Fixtures/m2-handshake-replay.json");

            Assert.That(recording, Is.Not.Null);
            var messages = TownRecordedMessagePlayer.ReadMessages(recording.text);
            Assert.That(messages, Has.Count.EqualTo(3));
            Assert.That(TownRecordedMessagePlayer.FindRecordedClientHelloMessageId(messages), Is.EqualTo("msg_000001"));
            Assert.That(TownRecordedMessagePlayer.FindRecordedRegistryMessageId(messages), Is.EqualTo("msg_000004"));

            foreach (var message in messages)
            {
                Assert.That(
                    TownEnvelope.TryParse(message, TownProtocol.DefaultWorldId, out var envelope, out var error),
                    Is.True,
                    error);
                Assert.That(envelope.MessageType, Is.Not.Empty);
            }
        }
    }
}
