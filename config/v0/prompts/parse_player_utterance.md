# parse_player_utterance / v0.1

Return only a JSON object that conforms to `PlayerSpeechParse` schema v0.1.
Do not invent agent IDs, event IDs, facts, or world-state changes. An event may
only be referenced when its ID appears in the provided candidate list. When the
utterance is ambiguous, set `requires_clarification` instead of guessing.

Player utterance:
{{utterance}}

Allowed agent IDs:
{{candidate_agent_ids}}

Allowed event IDs:
{{candidate_event_ids}}
