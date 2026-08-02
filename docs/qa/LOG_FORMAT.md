# Log format

Machine-consumable streams use UTF-8 JSON Lines: exactly one JSON object per
line, terminated by `\n`. Human-only `errors.log` may be plain text, but errors
must also have a structured record when a JSONL writer is available.

## Common envelope

Every record has these fields:

| Field | Type | Rule |
| --- | --- | --- |
| `timestamp_utc` | string | RFC 3339 UTC with `Z` or explicit `+00:00` |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `event` | string | Stable `lower_snake_case` event name |
| `component` | string | Stable producer name |
| `run_id` | string | Matches `metadata.json` |
| `message` | string | Short operator-readable summary |
| `correlation_id` | string/null | Action, request, decision, or conversation ID |
| `state_version` | integer/null | Authority version when applicable |
| `game_minute` | integer/null | Authoritative game time when applicable |
| `context` | object | Bounded, event-specific structured fields |

Example:

```json
{"timestamp_utc":"2026-08-02T03:15:00Z","level":"INFO","event":"config_validation_completed","component":"town_core.config","run_id":"20260802T031500Z-headless-12345-a1b2c3d4-7f2a","message":"configuration accepted","correlation_id":null,"state_version":0,"game_minute":0,"context":{"config_hash":"sha256:...","schema_version":"v0.1"}}
```

## Stream-specific minimums

- `events.jsonl`: event ID/type, actor/affected/witness IDs, source action, and
  importance.
- `decisions.jsonl`: decision ID/trigger, candidate IDs, utility terms,
  prediction references, selection, resolver result, random draws, and model
  version.
- `actions.jsonl`: action ID, behavior/participants, lifecycle phase, reserved
  resources, result, and failure/cancellation reason.
- `transactions.jsonl`: transaction ID, expected/before/after authority version,
  accepted/rejected result, stable rejection code, and bounded state deltas.
- `llm_requests.jsonl`: backend/model/prompt version, request kind, deadline,
  latency, cache/fallback status, validation status, and redacted payload hashes.
- `metrics.jsonl`: metric name, numeric value, unit, tags, and aggregation
  window.

The product's authoritative DTO/Schema thread owns exact payload structures.
This document freezes only the operational envelope and evidence properties.

For M1, every selected action must be traceable across decisions, actions,
transactions, and emitted events by stable IDs. Authority-bearing records are
never sampled. `summary.json` is ordinary UTF-8 JSON rather than JSONL and
contains counts, invariant observations, and canonical state/ordered-log hashes
defined by `docs/qa/M1_SIM_QA_INTERFACE.md`.

For M2, a redacted bridge transcript is JSONL and adds these bounded fields in
`context`: `protocol_version`, `message_id`, `message_type`, `direction`,
`connection_generation`, `authority_mutation_count`, and a canonical payload
hash. `correlation_id` is the action ID for all movement reports. Do not retain
the unrestricted payload merely to prove hashing or deduplication.

Reconnect evidence records the old last-acknowledged authority version, new
snapshot version, new `client_ready`, and explicit rejection codes for late
obsolete-generation inputs. Cancellation evidence separates two stale cases:
an exact current-generation world/action/agent/`TRAVELING` match is processed
with `python_authority_cancel_transaction_count=1`; a terminal/nonmatching
stale report records the three explicit
`stale_nonmatching_or_terminal_*` transaction/mutation/resync fields. The broad
`stale_state_message_authority_mutation_count` is not a QA summary field. It
also records identical-duplicate idempotency and conflicting same-ID rejection.
Unity-originated reports always record zero *direct* authority mutation; this
does not prohibit Python from committing the valid cancellation transaction.

## Safety and quality rules

- Never log API keys, authorization headers, complete environment dumps, or
  unredacted personal data.
- Use stable codes in structured context; do not require parsing prose.
- Include exception type and bounded stack information, but sanitize paths and
  values before upload.
- Do not silently drop malformed records. Emit a writer error and increment a
  metric when possible.
- Log sampling may reduce repetitive success records, never authority commits,
  errors, external inputs, random draws required for replay, or resolver
  conflicts.

M0 acceptance checks the presence and freeze of this contract. Emitting these
runtime streams begins with the milestone that implements each producer.
