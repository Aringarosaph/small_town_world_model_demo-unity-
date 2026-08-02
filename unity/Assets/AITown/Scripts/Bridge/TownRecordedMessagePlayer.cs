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

        public void Configure(TownBridgeClient client, TextAsset messageRecording, bool shouldPlayOnStart)
        {
            bridgeClient = client;
            recording = messageRecording;
            playOnStart = shouldPlayOnStart;
        }

        [ContextMenu("Play recorded envelopes")]
        public void Play()
        {
            if (bridgeClient == null || recording == null)
            {
                Debug.LogWarning("Recorded bridge playback requires a client and TextAsset.", this);
                return;
            }

            var messages = ReadMessages(recording.text);
            StartCoroutine(PlayRoutine(messages));
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

        public static string FindRecordedRegistryMessageId(IReadOnlyList<string> messages)
        {
            foreach (var message in messages)
            {
                var envelope = JObject.Parse(message);
                if (string.Equals(envelope.Value<string>("message_type"), "asset_registry_result", StringComparison.Ordinal))
                {
                    return envelope.Value<string>("correlation_id");
                }
            }

            return null;
        }

        public static string FindRecordedClientHelloMessageId(IReadOnlyList<string> messages)
        {
            foreach (var message in messages)
            {
                var envelope = JObject.Parse(message);
                if (string.Equals(envelope.Value<string>("message_type"), "server_hello", StringComparison.Ordinal))
                {
                    return envelope.Value<string>("correlation_id");
                }
            }

            return null;
        }

        private IEnumerator PlayRoutine(IReadOnlyList<string> messages)
        {
            bridgeClient.BeginRecordedReplaySession(
                FindRecordedClientHelloMessageId(messages),
                FindRecordedRegistryMessageId(messages));
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
