using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace STWM.AITown.Bridge
{
    [DisallowMultipleComponent]
    public sealed class TownRecordedMessagePlayer : MonoBehaviour
    {
        [SerializeField] private TownBridgeClient bridgeClient;
        [SerializeField] private TextAsset recording;
        [SerializeField] private bool playOnStart;
        [SerializeField, Min(0f)] private float messageDelaySeconds = 0.05f;

        private void Start()
        {
            if (playOnStart)
            {
                Play();
            }
        }

        [ContextMenu("Play recorded envelopes")]
        public void Play()
        {
            if (bridgeClient == null || recording == null)
            {
                Debug.LogWarning("Recorded bridge playback requires a client and TextAsset.", this);
                return;
            }

            StartCoroutine(PlayRoutine(ReadMessages(recording.text)));
        }

        public static IReadOnlyList<string> ReadMessages(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
            {
                return Array.Empty<string>();
            }

            var trimmed = text.TrimStart();
            if (trimmed.StartsWith("[", StringComparison.Ordinal))
            {
                var array = JArray.Parse(text);
                var messages = new List<string>(array.Count);
                foreach (var item in array)
                {
                    messages.Add(item.ToString(Formatting.None));
                }

                return messages;
            }

            var lines = text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            var result = new List<string>();
            foreach (var line in lines)
            {
                JObject.Parse(line);
                result.Add(line);
            }

            return result;
        }

        private IEnumerator PlayRoutine(IReadOnlyList<string> messages)
        {
            bridgeClient.BeginRecordedReplaySession();
            foreach (var message in messages)
            {
                bridgeClient.InjectInboundForReplay(message);
                if (messageDelaySeconds > 0f)
                {
                    yield return new WaitForSecondsRealtime(messageDelaySeconds);
                }
                else
                {
                    yield return null;
                }
            }
        }
    }
}
