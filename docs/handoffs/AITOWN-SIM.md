# AITOWN-SIM M1 Handoff

## Current responsibility

AITOWN-SIM owns the M1 headless authority slice for **Small Town World Model（STWM）**.
This delivery is limited to one runtime-enabled NPC (`npc_01`), three game days,
and `idle`, `sleep`, `eat_at_home`, and `work_shift`. The `AITOWN-*` name is an
internal task identifier only.

The implementation was checked against `AGENTS.md`, both files in `docs/specs/`,
all accepted `docs/adr/` records, `docs/handoffs/AITOWN-CONTRACTS.md`, the frozen
`config/v0`, `protocol/`, existing domain DTOs, and
`docs/orchestration/M1_EXECUTION_BASELINE.md`. No frozen M0 contract file was
changed.

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

- `python/town_core/simulation/`
- `python/town_core/decision/`
- `python/town_core/events/`
- `python/town_core/replay/`
- `python/tests/simulation/`
- `integration_tests/test_m1_headless.py`
- `python/town_core/cli.py` (additive M1 commands)
- `README.md` (actual M1 CLI)
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

## Known limitations and forbidden scope

- Only `npc_01` is active. The other nine records and their relationship edges
  exist solely to preserve the world boundary; this is not the M3 ten-NPC
  society simulation.
- Headless semantic objects are not Unity registry instances. Unity transport,
  presentation, animation, and asset binding remain outside M1.
- The outcome provider is a deterministic catalog-bounded heuristic. It is not
  an ML model and cannot mutate authority outside the Resolver/transaction path.
- Relationship updates, dialogue/social behavior, Claim/Belief graphs,
  Commitments, GNN/RSSM/RL training, DeepSeek/LLM calls, dynamic pricing, route
  planning, and long-term roadmap features are not implemented.
- Replay intentionally applies recorded authoritative patches rather than
  re-running policy. Integrity is protected by per-transaction hashes, final
  state equality, and the decisions/actions/transactions/events canonical hash.

## Blocking dependencies

No M1 SIM blocker remains. QA commit `99da4882be140d8130d3a3eb26d4ababa179e716`
must be integrated by AITOWN-ORCH before the repository-local strict M1 checker
is available on main; the SIM adapter already conforms to that final interface.
