using NUnit.Framework;
using STWM.AITown.Bridge;

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
    }
}
