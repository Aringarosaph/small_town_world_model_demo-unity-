# AITOWN-SIM M2 Python Bridge Handoff

## M3 society authority increment (2026-08-03)

The scoped M3 branch starts from frozen entry `2a51615` and consumes the
CONTRACTS commits `3fe06f6` and `ca8944b` without editing their frozen
protocol/config/domain paths. The additive society runtime lives under
`python/town_core/society/`; the accepted M1 one-NPC and M2 protocol `0.2.0`
entry points remain separate.

The authority increment currently provides ten enabled NPCs, same-snapshot
due-agent proposals, global deterministic IDs, the complete catalog-backed
22-behavior rulebook, central batch resolution with one reselection, shared
object/location/participant/household reservations, family economy, all-NPC
work sessions and exactly-once wages, directed Target-to-Actor relationships,
finite direct/witnessed/told knowledge, conversations, and central
JointActions. Cancellation/failure releases the complete action reservation
set. No neural model, training, DeepSeek call, or post-V0 graph was added.

`AuthorityCheckpoint` remains SIM-owned and records the public world, private
work/reservation/knowledge/conversation/JointAction ledgers, global counters,
the M3 additive catalog hash, transaction-chain hash, and a persistable ordered
authority-log cursor. Runs write a checkpoint every 360 game minutes.
Checkpoint patch replay does not recompute policy, and a real one-day baseline,
replay, and resume from minute 360 matched final state, final checkpoint,
transaction chain, and the full ordered authority-log hash.

The production object source is now only the CONTRACTS-owned shared
`M3_FULL` 74-instance manifest loaded by `load_m3_catalogs`. The SIM runtime has
no competing instance list. `SocietyCandidate` consumes `M3CandidateAction` and
there is no duplicate invitation allowlist. Background dialogue consumes the
CONTRACTS-owned Chinese `BackgroundDialogueCatalog` and selector; SIM adds only
deterministic action/seed context and the speaker knowledge-permission check.

### Current single-process performance evidence

On Apple arm64, macOS 26.5.2, Python 3.12.11, seed `12345`, shared 74-instance
manifest, `chunk_minutes=60`, a fresh production `run_society` execution from
minute 0 through 1440 reported:

- wall time: `8.884081` seconds;
- peak RSS: `51,691,520` bytes via `resource.getrusage(RUSAGE_SELF).ru_maxrss`;
- tick p99: `14.23525` ms;
- decision-batch p95: `0.5765` ms;
- 196 decisions, 187 actions, 86 events, and 2,707 ordered authority records.

A deliberately simple 30x linear projection is `266.52243` seconds, or about
`4m26.5s`, leaving about `10m33s` beneath the M3 15-minute single-run hard gate
before separately scheduled replay/evidence work. This is a projection, not a
substitute for the ORCH/QA-coordinated fixed 30-day soak; no long soak was run
concurrently on the MacBook Air.

The remaining M3 SIM work after this authority increment is protocol `0.3.0`
Bridge presentation/gating plus the external readiness/evidence adapter.

## Current responsibility

AITOWN-SIM owns the Python authority and local runtime-adapter side of the M2
functional-greybox slice for **Small Town World Model（STWM）**. The active route
is `npc_01: home_a -> cafe_bar -> home_a`; the behavior allowlist remains
`idle`, `sleep`, `eat_at_home`, and `work_shift`. The `AITOWN-*` name is an
internal compatibility identifier only.

The implementation was checked against `AGENTS.md`, both files in `docs/specs/`,
all accepted `docs/adr/` records, `docs/handoffs/AITOWN-CONTRACTS.md`, the frozen
`config/v0`, `protocol/`, existing domain DTOs, and
`docs/orchestration/M1_EXECUTION_BASELINE.md`, ADR-0009, and
`docs/orchestration/M2_EXECUTION_BASELINE.md`. The M2 baseline commit `0a4caa1`
was cherry-picked onto the M2 SIM branch. The CONTRACTS-owned ADR-0010 and
protocol `0.2.0` implementation from commit `392f941` were then consumed without
SIM editing or locally guessing frozen domain/protocol DTOs. Its additive
formatting follow-up `247711a` was also cherry-picked before the final focused
gate, followed by the CONTRACTS final re-freeze manifest `38e11ae` (57 strict
paths; manifest SHA-256
`cb5edafca43373a549a238038f03581734b31729b18b085234fe0e7b38366c6e`).

## M2 completed on the Python side

- Added a real loopback-only WebSocket server using the versioned flat JSON
  envelope, bounded message size, ping/pong liveness, readable protocol close
  reasons, and machine-readable startup/error output.
- Added the ordered handshake state machine and message idempotency. Repeating
  the same `message_id` with identical content is safe; reusing it for different
  content is a protocol error.
- The catalog remains frozen with source protocol `0.1.0`, while every active M2
  online session negotiates `0.2.0`. Runtime session evidence records
  `catalog_protocol_version` and `negotiated_protocol_version` separately so a
  catalog validation result cannot be mistaken for a live negotiation result.
- Live ingress and egress are checked against the normative direction schemas.
  A Python→Unity message on Unity ingress, or a Unity→Python message on Python
  egress, is rejected rather than accepted through a broader compatibility
  union.
- Each socket obtains a monotonically increasing connection generation. A new
  connection immediately makes all older transports obsolete. Old-generation
  and late inputs cannot mutate authority.
- Successful reconnect repeats hello and registry, creates new server message
  IDs, sends a fresh full `world_snapshot` from the current Python state, and
  keeps the simulation gated until that generation acknowledges the snapshot
  with `client_ready`.
- Added ADR-0009 scoped registry validation for `home_a`, `cafe_bar`, the exact
  active `npc_01` bed/fridge/dining-seat/workstation bindings and slots,
  `CAFE_MORNING`, `NpcView`, and the four required animation semantics. Missing
  or duplicate M2 entries are deterministic ERRORs; incomplete full-V0
  locations/object types/NPC views remain deterministic WARNINGs.
- A registered M2 location/NPC entry is the Unity scanner's attestation that its
  required navigation anchor/controller/animation adapter passed local component
  validation; the frozen registry payload has no coordinate or component fields,
  and Python never accepts scene coordinates as authority IDs.
- Added snapshot, clock, action-start, phase-change, active-agent delta, event,
  and selected-decision trace presentation output. Messages use committed
  `state_version`, stable authority IDs, and action correlation IDs.
- Added `UNITY_LIVE` movement transactions around the accepted M1 engine. A
  valid arrival controls the authoritative transition out of `TRAVELING`, sets
  the high-level destination, restarts the planned behavior duration from the
  confirmed arrival/alignment time, increments `state_version`, and does not
  advance `game_minute`.
- A valid navigation failure records `FAILED`, releases every slot/resource
  reservation owned by that action, restores the authoritative origin location,
  increments `state_version`, and never settles needs, money, wages, or events.
  Python also has a deterministic bounded `TIMEOUT` fallback.
- A valid typed `movement_cancelled` report is checked against world, action,
  agent, current connection generation, `TRAVELING` phase, and authority version.
  Python records the cancellation at its own current `game_minute`, commits one
  `CANCELLED` transaction, releases only that Action's reservations, restores
  its origin location, increments `state_version`, and emits `action_cancelled`.
  A stale version is accepted only while all current action identity and phase
  checks still match; a future version is rejected.
- Repeating the same cancellation message and content is a no-op. Reusing its
  message ID with different content is a protocol error. Unknown, terminal,
  or otherwise invalid current-generation reports produce a diagnostic and
  fresh snapshot without mutating authority or any other Action. An obsolete
  generation produces a resync-required protocol diagnostic and is closed so it
  cannot receive or mutate authority; the client must reconnect for the fresh
  handshake/registry/snapshot sequence.
- Added a SIM-owned M2 authority evidence adapter that drives the production
  `BridgeRuntime`, `BridgeSession`, and `SimulationEngine` rather than copying
  cancellation or reconnect rules. It writes only to an empty external
  directory and emits redaction-checked UTF-8 JSON/JSONL.
- The adapter records both ADR-0010 stale cases without conflating them: an
  older version for the exact current generation/world/action/agent/TRAVELING
  context commits one cancellation transaction, while a stale report for the
  now-terminal action records a diagnostic/resync and zero mutation. The QA
  `stale_state_message_authority_mutation_count` maps only to the latter.
- `presentation_completed` is diagnostic only. Missing animation completion
  never blocks hard-state settlement; this is the bounded presentation fallback
  frozen by Orchestrator.
- Python wall time exists only in the outer server clock adapter. Town Core still
  receives an already-advanced integer game minute, and Unity Live accepts only
  `0x`, `1x`, `2x`, or `4x`.

## M2 runtime interface

```bash
python -m town_core.bridge.server \
  --config config/v0 --agent npc_01 --seed 12345 \
  --host 127.0.0.1 --port 8765 --path /town
```

The default endpoint is `ws://127.0.0.1:8765/town`. Non-loopback binds are
rejected in M2.

Authority evidence test port:

```bash
python -m town_core.bridge.qa_adapter \
  --config config/v0 \
  --output-root /absolute/path/outside/repository/stwm-m2-authority \
  --agent npc_01 --seed 12345
```

This creates `m2-authority-evidence.json` with schema
`stwm.bridge.m2-authority-evidence/v1` and
`bridge-authority-transcript.jsonl` with schema
`stwm.bridge.m2-authority-transcript/v1`. Transcript event types are exactly
`unity_message_received`, `python_message_emitted`, and
`authority_probe_evaluated`. Every line contains the probe/generation,
direction, message identity, full redacted envelope when applicable,
before/after authority point, mutation/transaction count, outcome, error code,
and trigger sequence.

The evidence exports the QA cancellation/reconnect observation names plus an
explicit `evidence_refs` map to their supporting probe/session. It records one
real Python cancellation transaction; duplicate, conflicting-ID,
wrong-direction, future-version, stale-terminal, late-terminal, and
obsolete-generation probes all show zero authority mutation. Two generation
records prove new message IDs, fresh full snapshot, the pre-ready gate, and
resume only after the new `client_ready`. This artifact is not the Unity-owned
`stwm.qa.m2-acceptance-evidence/v1` and contains no fabricated Unity test result.

## Completed

- Added an absolute game-minute authority clock. The core receives only an
  already-advanced integer game minute and never reads wall-clock time. Driver
  chunks are decomposed into consecutive one-minute authority transactions.
- Builds a persistable `WorldState` from `CatalogBundle`. Exactly `npc_01` is
  enabled; the other nine NPC records and complete household memberships remain
  present but cannot decide, decay, act, earn, witness, or emit.
- Deterministically materializes all 90 directed relationship edges from the
  catalog ranges and seed. Relationships are static in M1.
- Added an explicit 34-object headless semantic fixture: household fridges,
  per-NPC beds/dining seats, and assigned workstations. These are catalog-typed
  semantic objects and do not claim Unity asset identity.
- Added four-behavior candidate enumeration, catalog-bounded heuristic outcome
  previews, decomposed Utility scoring, deterministic seed/state/candidate tie
  breaking, and a version/resource/location/slot-validating central Resolver.
- Added exclusive action lifecycle and reservations, atomic hard-effect/event
  transactions, passive need decay, continuous sleep/work effects, meal effects,
  and non-negative household food/money authority.
- Added work occurrence state, actual start/effective-minute tracking,
  completed/late/missed events, and exactly-once fixed wage settlement in the
  same authority transaction as `WORK_COMPLETED`.
- Added an append-only ordered event ledger and only the direct/witness knowledge
  records required by M1. Disabled NPCs never become witnesses.
- Added run evidence with initial/final snapshots, config snapshot, four JSONL
  logs, summary, stable state hashes, and a canonical authority-log hash covering
  ordered decisions, actions, transactions, and events.
- Added non-recomputing replay from initial snapshot plus ordered committed
  patches. Replay verifies every transaction/state hash, all four authority logs,
  the final snapshot, invariants, and source immutability, and writes a new
  sibling run. Source-descendant output is rejected.
- Added the production headless/replay CLI and the SIM-owned QA adapter for
  `stwm.qa.m1-evidence/v1`. CLI success and failure output is machine-readable
  JSON; damaged replay `KeyError`/`RuntimeError` boundaries return non-zero.

## Runtime interfaces

```bash
python -m town_core.cli run-headless \
  --config config/v0 --agent npc_01 --days 3 --seed 12345

python -m town_core.cli replay \
  --run runs/<source-run>

python -m town_core.simulation.qa_adapter \
  --config <absolute-config-v0> \
  --output-root <absolute-temporary-directory> \
  --evidence <absolute-output-root>/m1_qa_evidence.json \
  --agent npc_01 --days 3 --seed 12345 \
  --chunk-minutes 1,7,60
```

The QA adapter calls the production CLI for baseline, repeat, chunk-7,
chunk-60, replay, and a damaged-replay rejection. It reconstructs committed
states from real transaction logs to observe clock/version continuity, need
extrema and isolated decay, inactive-NPC activity, action lifecycle, resources,
event order, and wage settlement. It does not contain a second simulation.

## Frozen M1 work semantics

- The recurring catalog schedule defines the session start/end, 15-minute grace,
  and fixed shift wage.
- Any `actual_start > scheduled_start` emits `WORK_LATE` exactly once.
- Arrival no later than `scheduled_start + grace_minutes` may complete when
  `effective_work_minutes >= scheduled_minutes - grace_minutes`.
- Arrival after grace, or insufficient effective minutes, emits `WORK_MISSED`
  and pays nothing.
- Completion emits `WORK_COMPLETED` and one fixed wage effect atomically. A paid
  session cannot be settled again.
- Work sessions are materialized only when their schedule occurrence enters the
  60-minute M1 decision horizon or reaches finalization. They represent an
  in-scope schedule occurrence, not a future attendance record; a day-3 session
  is therefore absent from the minute-4320 final snapshot.

Controlled production probes observe: normal start at minute 360 with 480
effective minutes; late start at minute 366 with 474 effective minutes and one
wage; and disabled workstations with `WORK_MISSED` and zero wage.

## Files owned by this delivery

- `python/town_core/bridge/`
- `python/tests/bridge/`
- `python/town_core/simulation/`
- `python/town_core/decision/`
- `python/town_core/events/`
- `python/town_core/replay/`
- `python/tests/simulation/`
- `integration_tests/test_m1_headless.py`
- `python/town_core/cli.py` (additive M1 commands)
- `README.md` (actual M1 CLI)
- `pyproject.toml` / `uv.lock` (local WebSocket runtime dependency)
- `docs/handoffs/AITOWN-SIM.md`

## Validation and run evidence

The accepted scenario is seed `12345`, `npc_01`, minute `0 -> 4320`, exactly
4320 committed ticks. Baseline/repeat/chunk-7/chunk-60 produce the same:

- initial state hash:
  `b260148029c70cc77beff9262b844b48ed691e5bf080e46cb072d44a5b03cbf7`;
- final state hash:
  `dda5aae504b65700c2a6e2da4386ee6dab022ee8792917887c7bf905960e3cbd`;
- four-log authority hash:
  `a0268e4f88b1b861959fa26137d73c656b8c3d1ab5d4b1590b124844d7487297`;
- behavior decisions: `idle=8`, `sleep=11`, `eat_at_home=8`,
  `work_shift=12`;
- three completed sessions, 480 effective minutes each, exactly three wage
  settlements totaling 36000 catalog minor units.

The final gate uses Python 3.12, full Pytest, Ruff lint/format, strict Mypy, M0
freeze diagnostics, the production three-day CLI/replay, and the QA-owned
`check_m1.py --require-sim` contract.

M2 adds 21 deterministic bridge unit/integration tests for registry
success/failure, `0.2.0` negotiation, direction enforcement, handshake ordering,
message-ID idempotency, the `client_ready` gate, authoritative
arrival/failure/cancellation and TIMEOUT, reservation/resource boundaries, fresh
reconnect snapshots, obsolete generations, evidence version separation, and a
real loopback WebSocket handshake. The two additive evidence tests also lock the
external output boundary, exact JSON/JSONL fields, transaction-backed
cancellation count, stale semantic split, and reconnect observations. The
consumed CONTRACTS change adds 21 focused protocol `0.2.0` and artifact tests.

The additive authority-evidence focused gate passes with 21/21 Bridge tests,
21/21 protocol `0.2.0`/artifact tests, Ruff format check over 103 files, Ruff
lint, and strict Mypy over 64 source files. Two independent CLI runs produced
byte-identical evidence and 1,093-line transcripts with final state hash
`f0859d472a8ca7bbdd34393f75c342cfe16f84cb04deab38674bc92e9300aa6c`.

## Known limitations and forbidden scope

- Only `npc_01` is active. The other nine records and their relationship edges
  exist solely to preserve the world boundary; this is not the M3 ten-NPC
  society simulation.
- Headless semantic objects remain Python authority objects; Unity registry
  instances must bind the exact M2 semantic IDs and never replace them.
- Python Bridge does not implement Unity components, scene navigation, greybox
  rendering, or Editor tests. Those remain AITOWN-UNITY M2 ownership.
- The outcome provider is a deterministic catalog-bounded heuristic. It is not
  an ML model and cannot mutate authority outside the Resolver/transaction path.
- Relationship updates, dialogue/social behavior, Claim/Belief graphs,
  Commitments, GNN/RSSM/RL training, DeepSeek/LLM calls, dynamic pricing, route
  planning, and long-term roadmap features are not implemented.
- Replay intentionally applies recorded authoritative patches rather than
  re-running policy. Integrity is protected by per-transaction hashes, final
  state equality, and the decisions/actions/transactions/events canonical hash.

## Integration sequencing

There is no remaining SIM-side cancellation contract blocker. The typed
`movement_cancelled` authority path consumes ADR-0010/protocol `0.2.0` as
implemented by CONTRACTS. Its additive formatting follow-up has been consumed;
the final re-freeze manifest has also been consumed, and SIM did not rewrite the
frozen generator or artifacts. Per Orchestrator scheduling, the
resource-intensive full M1 strict/three-day hash regression runs sequentially in
the final integration gate rather than in parallel with the focused SIM gate.
