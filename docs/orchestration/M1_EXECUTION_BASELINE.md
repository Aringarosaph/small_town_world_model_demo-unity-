# M1 execution baseline

## Outcome

M1 proves that the frozen M0 contracts can support a deterministic authority
runtime before Unity, the complete society, a neural model, or DeepSeek exists.
One active NPC must complete ordinary life and work for three game days in
`HEADLESS_FAST`, then reach the identical final authority state through replay.

## Fixed slice

- Public project name: Small Town World Model（STWM）.
- Active agent: `npc_01`.
- World seed: `12345` unless a test explicitly supplies another seed.
- Start: game minute `0`, weekday `0` (Monday), at `home_a`.
- Duration: exactly `4320` one-minute game ticks for the three-day gate.
- Enabled behaviors: `idle`, `sleep`, `eat_at_home`, `work_shift` only.
- Work assignment: `cafe_bar`, 06:00-14:00, 15-minute grace period.
- Outcome provider: deterministic M1 heuristic bounded by the frozen behavior
  masks and output ranges.
- Other configured NPCs may exist as inactive state records but may not decide,
  act, decay, earn wages, or produce events in the M1 acceptance run.
- Directed relationship initialization must be deterministic and complete for
  every materialized agent pair; M1 does not update relationship values.

## Required implementation

1. Simulation clock independent of wall time and Unity frames.
2. Deterministic state initialization from `CatalogBundle` plus an explicit
   Headless semantic-object fixture.
3. Candidate enumeration with at least one valid `idle` fallback.
4. Heuristic outcome preview and decomposed Utility scoring using configured
   weights and deterministic seed-derived tie-breaks.
5. Proposal validation and central Resolver against one read-only state version.
6. One primary action per active NPC and exclusive interaction-slot reservation.
7. Minimal action phases from creation through travel, performance, resolution,
   completion, and recorded failure/cancellation paths.
8. Config-owned need decay and exact M1 behavior effects; values must remain in
   M0-declared output bounds and must not be scattered constants.
9. Work start, late, missed, completion, and exactly-once wage settlement per
   agent/shift/day session.
10. Append-only ordered events and monotonic authority state versions.
11. Structured run evidence and an authority replay that never writes into the
    source run directory.

## CLI contract

The final option spelling may be extended, but these commands must work:

```bash
python -m town_core.cli run-headless \
  --config config/v0 --agent npc_01 --days 3 --seed 12345

python -m town_core.cli replay --run runs/<run_id>
```

`run-headless` must print a machine-readable summary containing at least the run
ID/path, start/end minute, active agent, seed, event/action/decision counts,
initial/final state hashes, and invariant result. `replay` must print the source
run, replay output path, transaction count, expected/actual final hash, and a
boolean match result. Both commands return non-zero on invalid input or a failed
invariant/hash comparison.

## Run evidence

Each accepted run contains:

```text
runs/<run_id>/
  metadata.json
  config_snapshot/
  initial_snapshot.json
  decisions.jsonl
  actions.jsonl
  transactions.jsonl
  events.jsonl
  final_snapshot.json
  summary.json
```

Additional redacted metrics or periodic snapshots are allowed. Run output is
ignored by Git and must never contain credentials, LLM content, model weights,
or machine-specific secrets.

Canonical state hashing uses stable UTF-8 JSON with sorted object keys and no
non-authority metadata. Replay applies the ordered committed transaction record
to the initial snapshot and compares the resulting hash with the recorded final
authority hash.

## Acceptance gates

- Exactly one active NPC and only four allowed behavior IDs appear in decisions
  and actions.
- The clock reaches minute `4320` without skipped or duplicated authority ticks.
- Needs and mood stay within their declared ranges.
- Household money and food never become negative.
- At most one primary action and one owner per exclusive slot exist at a time.
- State versions, action IDs, decision IDs, transaction IDs, and event ordering
  are stable and monotonic.
- Wages are not paid before a valid completed work session and never settle more
  than once for the same session.
- The event ledger is append-only.
- Same config and seed produce the same final hash and ordered authority log.
- Different valid tick chunking produces the same authority result.
- Replay produces the recorded final hash without mutating the source run.
- Three-day logs contain a complete decision trace for every selected action.
- Unit, property, integration, Ruff, format, Mypy, M0 diagnostics, and the new M1
  strict gate all pass on Python 3.12.

## Forbidden scope

- WebSocket or live Unity behavior;
- enabling all 10 NPCs as simultaneous actors;
- any behavior outside the four-item M1 allowlist;
- social relationship updates, JointAction, dialogue, or player input;
- neural inference, training data generation, DeepSeek, or prompt execution;
- Claim, Belief, Commitment, Norm, GNN, RSSM, RL, or other long-term features;
- silent edits to M0-frozen config, protocol, domain DTO, or hash coverage.

## Stop conditions

Simulation work stops and reports to `AITOWN-ORCH` if the slice cannot be built
without changing an M0-frozen artifact, if two authoritative interpretations are
equally plausible and materially change replay semantics, or if a required
contract has no additive M1 representation outside the frozen surface.
