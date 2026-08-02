# ADR-0011: M3 society authority, checkpoints, and protocol 0.3

- Status: Accepted
- Date: 2026-08-02
- Owners: AITOWN-ORCH, AITOWN-CONTRACTS
- Supersedes: M3-specific assumptions that protocol `0.2.0` is sufficient

## Context

M2 accepted a one-NPC Unity presentation slice on protocol `0.2.0`. M3 activates
ten authoritative NPCs, all twenty-two behaviors, shared household resources,
directed relationships, finite event knowledge, conversations, and central
JointActions. The M2 wire shape cannot unambiguously carry participant-to-slot
bindings, explicit nullable delta clearing, complete reconnect presentation, or
the Top-K decision explanation required by the M3 debug UI.

The accepted M1/M2 state and evidence formats must remain replayable. M3 also
needs authority data that does not belong in the public `WorldState`: work
sessions, reservations, complete knowledge records, conversations, JointAction
coordination, stable counters, and checkpoint cursors.

## Decision

### Compatibility profiles

- M1 keeps its one-agent `SimulationEngine`, `WorldState` `v0.1`, run schema,
  hashes, invariants, CLI, and replay behavior.
- M2 keeps protocol `0.2.0`, its scoped registry policy, bridge semantics, and
  accepted evidence unchanged.
- M3 uses a separate society runtime profile and requires negotiated protocol
  `0.3.0`. A client preference is `0.3.0`, then `0.2.0`; an M3 session may not
  silently fall back to `0.2.0`.
- Catalog provenance remains separately reported as `0.1.0` until an explicit
  catalog-version decision changes it.

### M3 protocol additions

Protocol `0.3.0` is additive and has its own version-aware Python and C# DTOs,
JSON Schemas, examples, direction unions, and compatibility tests.

`action_started` carries structured participants. Each participant declares an
agent ID, the role `ACTOR`, `TARGET`, or `PARTICIPANT`, zero or more authoritative
object/slot bindings, and an optional facing target. The payload also identifies
whether the action is joint and its optional conversation ID. One central
`action_id` owns the shared lifecycle.

The `world_snapshot` M3 payload contains the unchanged public `WorldState` plus
the active action-presentation bindings needed to restore Unity after a full
reconnect. Unity replaces its cache and slot claims from this payload; it never
reconstructs authority rules.

`agent_state_delta` uses an explicit field mask. A field present in the mask with
a null value means clear; a field absent from the mask means unchanged. The M3
shape covers location, action, needs, mood, and known-event IDs.

Protocol `0.3.0` adds `household_state_delta` for authoritative money and food
updates. Existing relationship and event messages remain directional authority
outputs.

`debug_decision_trace` carries one complete decision: trigger, source state
version, Top-K candidate rows, hard preview, heuristic prediction, decomposed
utility terms, total score, selected candidate, proposal/Resolver result, and
conflict code. Debug information is read-only and cannot be submitted as input.

### Authority checkpoint

M3 introduces `stwm.simulation.m3-authority-checkpoint/v1`, stored outside the
wire contract and written with run evidence. It contains:

- the public `WorldState`;
- per-agent/day work sessions and exactly-once settlement keys;
- object, household-resource, participant, and location reservations;
- the versioned `KnowledgeLedger` records;
- the versioned `ConversationLedger` records;
- JointAction coordination and presentation bindings;
- deterministic counters, ledger cursors, and hashes.

Checkpoints are written at least every six game hours and at finalization. M3
resume and authoritative replay use them without recomputing policy. Knowledge
permission remains represented publicly by `AgentState.known_event_ids`; the
ledger retains acquisition type, source, confidence, and reinforcement time.

### Candidate and JointAction semantics

The M3 society candidate shape adds typed optional `selected_context_event_id`,
`target_conversation_id`, and `invited_activity_id`. The invitation allowlist is
exactly `watch_tv`, `eat_at_cafe`, `drink_at_bar`, `walk_in_park`, and
`sit_in_park`.

All due agents propose from the same read-only source version. The central
Resolver orders accepted joint actions, schedule-critical work, existing valid
reservations, total score, deterministic tie break, then stable IDs. A rejected
actor may retry one remaining candidate; a second rejection falls back to idle.
Shared funds, food, locations, agents, and slots are reserved and committed
atomically. Any joint failure, cancellation, or timeout releases the whole
reservation set and cannot leave a split action.

### Semantic instances and background dialogue

CONTRACTS publishes a versioned full-town semantic-instance manifest consumed by
both the Headless fixture and the Unity builder. This is an intentional additive
catalog re-freeze; Python and Unity must not maintain competing instance lists.

Background NPC dialogue is a deterministic, versioned template provider. It
covers every social behavior and accepted/rejected result, always has a non-empty
fallback, may reference only events known by the speaker, and emits the existing
presentation message. It does not call DeepSeek and cannot mutate authority.

## Consequences

- CONTRACTS must implement and re-freeze protocol `0.3.0` while preserving all
  `0.2.0` artifacts and tests.
- SIM can implement M3 additively without changing accepted M1/M2 outputs.
- UNITY receives unambiguous multiplayer presentation and reconnect state.
- QA can validate explanation and explicit-clear behavior without inferring
  Python facts from C# nullable values.
- M4 neural inference, M5 player/DeepSeek dialogue, and M6 golden-chain release
  work remain out of scope.

