# AITOWN-SIM Python Authority Handoff

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

### Protocol 0.3 M3_FULL bridge

The additive `town_core.bridge.m3_runtime`, `m3_session`, and `m3_server`
entry points negotiate only active protocol `0.3.0`; catalog provenance remains
`0.1.0`, and the accepted M2 `0.2.0` runtime is unchanged. The M3 registry is a
blocking exact-ID/slot/capability/animation check over the shared 74-instance
manifest. Because the frozen registry envelope has no component booleans, the
complete NpcView set is the Unity-side local attestation for prop, facing,
controller, and NavMesh checks.

Each connection has a monotonically increasing generation. Registry acceptance
emits a fresh full snapshot containing one `active_presentation` per active
action; authority advancement remains gated until that generation applies the
snapshot and sends `client_ready`. Reconnect invalidates the old generation.
Output includes all affected agent field-mask deltas (including explicit null
clears), household deltas, directed relationship deltas, events, Chinese
background dialogue, and at most 12 Top-K rows with at most two Resolver
attempts. Participant presentations contain stable roles, object/slot bindings,
social facing targets, animation/prop semantics, and conversation identity.
The WebSocket serializer keeps complete non-delta envelopes/snapshots, but
serializes agent and household delta payloads from `model_fields_set`: masked
explicit null clears stay on the wire and unmasked optional defaults do not.
This preserves the frozen 0.3 field-mask presence contract without relaxing
Unity validation.

In `UNITY_LIVE`, every moving participant must report arrival. A JointAction
leaves `TRAVELING` only after the complete participant barrier; a failure,
typed cancellation, or bounded timeout terminates the whole action and releases
all participant/location/object/resource reservations in one transaction.
Same-message duplicates are no-ops, conflicting reuse is a protocol error, and
rejected stale/future/obsolete inputs only diagnose/resync. A real local RFC
6455 protocol-0.3 handshake test passed.

### M3 readiness evidence and CLI

The additive CLI commands are:

```text
python -m town_core.cli run-society --config config/v0 --days 1 --seed 12345 --chunk-minutes 60
python -m town_core.cli replay-society --run <m3-run> --output-root <external-root>
python -m town_core.society.m3_qa_adapter --config config/v0 --output-root <external-root> --evidence <external-root>/m3-simulation-readiness-evidence.json
```

The adapter writes UTF-8 `stwm.simulation.m3-readiness-evidence/v1` evidence
outside the repository. This rich document is SIM-owned production-run
evidence; it is intentionally distinct from QA's exact
`stwm.qa.m3-readiness/v1` repository-integration report emitted by
`check_m3 --json-output`, and it never copies or synthesizes QA findings or
summary fields. It invokes production run/replay/Bridge paths for the canonical
one-day baseline/repeat/chunk-7/chunk-60 matrix, checkpoint-360 resume, exact
four-household economy reconstruction, pathology/performance metrics, fresh
snapshot/ready/reconnect observations, and machine-readable CLI failures. It
records the fixed 7/30-day seed plan but deliberately does not claim or launch
the ORCH/QA-scheduled slow soak.

The accepted adapter run on the same Apple arm64 host passed. The four final
state/checkpoint/transaction-chain/authority-log hashes matched; replay and
checkpoint resume matched; all household equations matched. Its baseline wall
time was `7.543836` seconds with peak process RSS `57,688,064` bytes, tick p99
`12.412417` ms, and decision-batch p95 `0.451833` ms. A 30x wall-time projection
is `226.31508` seconds (`3m46.3s`); this remains a projection, not slow-soak
evidence.

### M3 release soak producer

The sole SIM-owned slow-release entry point is:

```text
python -m town_core.society.m3_release_producer --config config/v0 --output-root <external-root> --source-commit <full-40-character-sha> --reference-machine "producer Apple-silicon MacBook Air"
```

It never writes a run below the repository. It executes one child
`run-society` process at a time, preserving a stable `producer-state.json`
after every attempt. A failed attempt is retained and the next invocation uses
a new numbered attempt directory. A same-host dead PID lock is recovered; a
live or foreign-host lock is never stolen. `--max-new-runs N` stops cleanly
after N additional jobs, and `--plan-only` freezes/validates the exact plan
without running the slow matrix. Re-running a completed root verifies every
artifact byte count, SHA-256, and content schema before returning success.
The declared source commit must be the current full `git rev-parse HEAD`, and
the release checkout must be clean, so a bundle cannot claim provenance for
uncommitted runtime code.

The fixed plan contains the eight required soak cases in frozen order (five
7-day seeds and three 30-day seeds), plus canonical seed `12345` repeat,
chunk-1, and chunk-7 runs. The soak 7-day/chunk-60 run is reused as canonical
chunk-60, for eleven production simulations total. Every completed job is
immediately streamed through production checkpoint-patch replay. That replay
checks final public state, the SIM ledger projection, ordered authority log,
invariants, source immutability, and every persisted six-hour checkpoint in a
single pass without duplicating the run directory.

The external layout is:

```text
<external-root>/
  producer-state.json
  bundle-manifest.json
  artifacts/
    authority-evidence.json
    behavior-matrix-report.json
    soak-7-day-report.json
    soak-30-day-report.json
    replay-report.json
    pathology-report.json
    performance-report.json
  runs/<stable-job-id>/attempt_0001/
    summary.json
    initial_checkpoint.json
    final_checkpoint.json
    checkpoints/checkpoint_*.json
    authority.jsonl
    transactions.jsonl
    decisions.jsonl
    actions.jsonl
    events.jsonl
    dialogues.jsonl
```

The seven report schemas are, respectively,
`stwm.simulation.m3-authority-evidence/v1`,
`stwm.simulation.m3-behavior-coverage/v1`, two instances of
`stwm.simulation.m3-soak-report/v1`,
`stwm.simulation.m3-replay-report/v1`,
`stwm.simulation.m3-pathology-report/v1`, and
`stwm.simulation.m3-performance-report/v1`. The manifest records relative
paths, UTF-8 byte counts, SHA-256 digests, redaction, and schemas for direct QA
descriptor consumption. `authority-evidence.json` exposes a
`qa_matrix_projection` for SIM-complete matrices and separate evidence refs;
it does not create QA gates/findings/summary.

The producer explicitly does **not** emit
`stwm.qa.m3-acceptance-evidence/v1` or Unity registry, presentation, debug,
EditMode, PlayMode, live-smoke, or batchmode facts. In particular,
`behavior_coverage[].unity_presentation` remains null and Unity-owned. QA
combines those owner artifacts; SIM never fills the Unity gap with a constant.

### M3 exact targeted authority projection

The release aggregation step now runs the production-backed
`m3_targeted_evidence` fixture lane before writing the same seven SIM artifacts.
For each of the 22 ordered behaviors it independently executes all eight frozen
SIM probes: legal and illegal candidate enumeration, hard-cost preview,
Resolver acceptance and rejection, reservation/lifecycle, allowed effects, and
authoritative transaction replay. Each emitted PASS has a distinct executable
pytest node ID and a positive count of assertions actually evaluated; a failed
assertion aborts artifact generation. Release-soak occurrence remains a
separate positive count and is not substituted for targeted coverage.

The four `qa_probe_evidence` records are likewise real deterministic authority
operations. Unknown-event sharing is rejected by the production Resolver with
zero transactions and identical before/after checkpoint hash and version. A
two-participant central JointAction is then independently driven through
explicit cancellation, failure, and bounded movement timeout. These paths use
production creation/commit/terminal transactions, prove both participant
reservations share the central action owner, prove terminal release from action,
JointAction, object, participant, and reservation authority, run invariants,
and replay to the exact checkpoint/authority hashes. The supporting observations
remain in `targeted_probe_observations`; the QA-facing record itself keeps the
exact three keys `status`, `test_ids`, and `assertion_count`.

`authority-evidence.json.qa_matrix_projection` now carries the exact
`knowledge_permissions` and `joint_action` matrices. Positive direct,
witnessed, told, accepted-invite, and rejected-invite coverage still comes from
the canonical production soak; forced negative/terminal booleans cross-check
the targeted records above. The invitation list is imported from the shared
CONTRACTS allowlist, `player_told_record_count` and out-of-scope epistemic graph
count remain zero, and Unity fields are neither generated nor copied.

### M3 closed-location idle fallback correction

The first external 7-day seed-`12345`, chunk-`60` release attempt stopped at
the uncommitted minute-5340 tick after its last persisted minute-5280
transaction. Exact resume from `checkpoint_00005040.json` showed that
`npc_07` completed `action_00001092` at the shop, then lost its first
`eat_at_cafe` proposal to the same-snapshot batch winner with
`OBJECT_SLOT_CONFLICT`. Its mandatory idle fallback was at its current shop,
whose interval ends at minute-of-day 1020, and the Resolver incorrectly applied
the business-entry gate to that zero-travel fallback and returned
`LOCATION_CLOSED`.

The Resolver now exempts only a single-actor `idle` whose destination exactly
equals the actor's current authoritative location. It does not exempt other
co-located behavior: targeted tests keep `eat_at_cafe`, `buy_groceries`, and
`work_shift` rejected at closed businesses, and a synthetic cross-location
idle remains subject to the same closed-location gate. Local idle creates no
`LOCATION` reservation. This implements the specification's always-available
idle invariant without allowing after-hours business actions.

A new external production run at
`/tmp/stwm-m3-seed12345-chunk60-idle-fix-20260803` completed all 10,080 ticks
with zero invariant violations. It reported `245.034862s` engine wall time and
`62,685,184` bytes peak RSS. Production replay checked all 29 persisted
checkpoints with zero mismatch and matched final state
`920529fca3828415a1104a9495bf15a97a849ad0a83f5cf50858a72d2e0909b4`, final
checkpoint `90660de4be8cb086e3aae9651310ab3965bff84914d32511fc07725579696e14`,
ledger `d8d4650f921a6f3d4fd6406a0d9de9a9dd9d6313c7686c7c874212051e2aef28`,
and ordered authority log
`df4375d3baee98ca09dea9de58a9d090d4778e94da8d8a8d09ad96b6307f4db7`.
The original failed release attempt remains unchanged. The release producer
also now preserves the child CLI's machine-readable error detail in its own
failed-attempt record rather than retaining only the exception type.

The pre-optimization 7-day result linearly projected to about `17m30s` for 30
days, exposing a performance risk against the `<15m` single-run gate that the
earlier one-day projection did not reveal. The following authority-neutral
performance correction addresses that risk without relabeling this historical
run as a 30-day result.

### M3 checkpoint commit performance correction

Early and late six-hour checkpoint windows were profiled against the preserved
7-day run. The early window (minute 0-360) took `1.899901s`; the late window
(minute 9360-9720, starting with 556 events and 920 knowledge records) took
`8.473803s`. In the late window, `_commit` consumed `7.980s`. Its dominant cost
was two complete checkpoint `model_dump`/`model_validate` round trips per tick:
serialization accumulated `3.194s` and validation `3.067s`, repeatedly walking
immutable ledger history. Transaction diffing/equality (`0.600s`) and both
invariant passes (`0.675s`) were the next growth-sensitive costs.

The engine retains the first complete round trip before transaction/authority
hash derivation, so normalized authority bytes are unchanged. It removes only
the second round trip after internally generating the non-negative authority
record count and SHA-256 cursor. Both per-tick society invariant calls remain;
the immutable M3 catalog hash is computed once per engine and supplied to each
invariant comparison rather than serializing the same catalog twice per tick.
No decision, transaction, event, knowledge, checkpoint, replay, or evidence
content changed.

With the correction, the profiled early window took `1.013114s` and the late
window `5.432073s`; both reproduced the preserved checkpoint and authority hash
exactly. A fresh seed-`12345`, chunk-`60` 7-day production run completed in
`110.850422s`, down from `245.034862s` (`54.8%` faster). Its final state,
checkpoint, ledger, transaction chain, ordered authority log, record counts,
behavior counts, events, and economy are identical to the pre-optimization
success. Production replay again matched all hashes and all 29 checkpoints
with zero source mutation or invariant violation.

The observed 7-day result gives a simple 30-day projection of `475.073237s`
(`7m55.1s`), leaving `47.2%` below the frozen 900-second gate. Peak RSS was
`67,895,296` bytes; performance acceptance should therefore use the measured
wall improvement rather than claiming a memory reduction. This remains a
projection until the ORCH-scheduled 30-day matrix runs.

### M3 streaming authority serialization follow-up

The integrated RC release run exposed a second growth-sensitive path at 30
days. `SocietyRunWriter.append` canonicalized every authority envelope three
times: once for its resumable hash, once for `authority.jsonl`, and once for the
kind-specific JSONL. The writer now canonicalizes each envelope exactly once,
advances the hash from those exact UTF-8 bytes, and writes the same byte object
plus LF to both files. Per-append binary streams are owned by an `ExitStack`, so
normal and exceptional exits close every opened authority/kind stream. The
existing `StreamingAuthorityHasher.append(record)` API remains compatible.

Same-checkpoint profiling showed that writer-only reuse was necessary but not
sufficient: minute 33840-34560 improved from `22.539669s` to `20.919113s`.
After that change the writer occupied only `0.395s` in the 12-hour profile;
complete historical checkpoint `model_dump` and `model_validate` consumed
`8.375s` and `7.945s`. The engine had been serializing and reconstructing every
unchanged event/knowledge/work/conversation record each tick solely to validate
the outer checkpoint.

The engine now validates the complete `AuthorityCheckpoint` outer schema,
containers, scalar cursors, hashes, and newly introduced values while retaining
the already-validated frozen nested `ContractModel` instances. Both per-tick
society invariant passes and transition invariant remain unchanged. Unit tests
compare this reference-preserving result against the prior full JSON
normalization, including the complete JSON projection and checkpoint hash, and
prove that an invalid outer authority cursor is still rejected. The same late
12-hour window then completed in `4.167428s` with identical final/checkpoint,
ledger, transaction-chain, and authority-log hashes.

The final seed-`12345`, chunk-`60` 7-day production benchmark completed in
`16.620429s`, versus the preserved RC baseline `60.994849s` (`72.75%` faster),
with the same 27,363 authority records. All six JSONL byte counts and SHA-256
digests match the RC files exactly; initial/final checkpoint files and every
periodic checkpoint are also byte-identical. Production replay matched all 29
checkpoints with zero mismatch or source mutation. A linear 30-day projection
is `71.23041s`. A deliberately conservative bound scales the measured day-24
late-window rate by `30/24` and applies that projected maximum rate to all 30
days: `312.5571s`, leaving `65.27%` below 900 seconds. This remains a projection;
the ORCH release producer owns the final full 30-day measurement.

### M3 truthful current-RSS evidence

The integrated 30-day seed-`12345` RC completed authority simulation in
`517.039836s` with peak RSS `137,592,832` bytes, but its reported
`2,710,872.21891 B/day` slope was a regression over `ru_maxrss` high-water
samples rather than live process memory. The checkpoint authority itself grows
far more slowly: a recursive stdlib diagnostic measured approximately 174 KB
initially, 2.22 MB at day 7, and 7.61 MB at day 30; the two exact-percentile
timing arrays add approximately 0.09 MB/day.

Peak RSS remains `resource.getrusage(RUSAGE_SELF).ru_maxrss`. Daily slope now
uses a stdlib/`ctypes` current-process sampler: Darwin calls
`libproc.proc_pidinfo(PROC_PIDTASKINFO).pti_resident_size`, while Linux reads
the resident-page field from `/proc/self/statm` and multiplies by
`SC_PAGE_SIZE`. Samples retain both `current_rss_bytes` and
`peak_rss_bytes`. The exact method string also records the fixed sampling point:
after the committed daily authority transaction and before checkpoint
persistence. The post-warmup filter remains `game_day >= 1`, and the frozen
1 MiB/day threshold is unchanged.

Current-RSS sampling confirmed real allocator growth rather than hiding it: the
first 7-day run still measured 3.18 MiB/day, and a day-7-to-30 continuation
without the persistence fix measured 7.64 MiB/day. `gc.collect`, Darwin malloc
pressure relief, `PYTHONMALLOC=malloc`, and disabling the nano allocator did not
release the growth, so none is used by production or evidence.

The retained pages came from periodic checkpoint persistence building one
complete, ever-growing `json.dumps` string and then writing it. Checkpoints now
use `json.dump` directly into the same atomic temporary file with the same
indentation, key ordering, Unicode, LF, and replace semantics. Headless
persistence also reads the already schema-validated and invariant-checked
authority checkpoint directly; the public `export_checkpoint` API still
returns a detached deep authority copy, and a test proves callers cannot mutate
the engine through it.

The corrected fresh 7-day run preserved every authority hash and measured peak
RSS `63,881,216` bytes. Its short-window slope was `1,320,082.285714 B/day`;
short-run allocator warmup therefore is not relabeled as a 30-day pass. A real
continuation from the exact day-7 checkpoint through day 30 completed in
`205.967729s`, peak RSS `92,897,280` bytes, and current-RSS slope
`820,268.521739 B/day`, below the frozen threshold. Combining fresh day 1-7
samples with continuation day 8-30 samples gives a conservative projected
full-run slope of `877,282.100111 B/day`. Its final checkpoint SHA-256 matches
the completed ORCH 30-day run exactly; its 2.22 GB authority log is byte-equal
to the corresponding ORCH authority suffix, and production replay matched all
93 resumed checkpoints with zero mismatch or source mutation. ORCH still owns
the final uninterrupted 30-day evidence rerun.

The independent one-day production observation for this increment completed
in `7.682316s`, peaked at `51,593,216` bytes RSS, used `38 MiB` on disk, and
passed all five persisted-checkpoint, final-state, ledger, authority-log, and
source-mutation replay checks. A linear 146 simulated-day projection for the
eleven serial runs is about `18m42s` of simulation; allowing streaming replay,
analysis, process startup, and filesystem variance gives a practical MacBook
Air estimate of `25-30 minutes`. The same disk sample projects roughly
`5.5 GiB`; reserve `7 GiB` externally. These are scheduling estimates, not a
claim that the unrun full matrix passed.

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
