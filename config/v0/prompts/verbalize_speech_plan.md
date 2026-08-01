# verbalize_speech_plan / v0.1

Produce one short player-visible line from the supplied SpeechPlan. Use only
facts and IDs explicitly allowed by the plan. Do not expose internal IDs, claim
that authority state changed, or add facts the speaker does not know. If the
plan contains insufficient information, say that the speaker does not know.

SpeechPlan:
{{speech_plan}}
