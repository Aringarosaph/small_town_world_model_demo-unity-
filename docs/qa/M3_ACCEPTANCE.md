# M3 acceptance

M3 for **Small Town World Model（STWM）** accepts the complete deterministic V0
heuristic society. It is additive to accepted M0–M2 behavior and does not
accept neural inference, player/DeepSeek dialogue, golden-chain release work,
Claim/Belief graphs, or any M4/M5/M6 feature.

## Frozen inputs and compatibility

- entry commit: `2a516159ab41f88c90ea2932bbc117b595c569c3`;
- accepted M2 baseline: `7b2618de09bd87eb49716ac40f1d0ba697f00351`;
- M3 execution baseline and accepted ADR-0011;
- catalog provenance `0.1.0`, repository current and M3 negotiation `0.3.0`;
- retained M2 acceptance profile and artifacts `0.2.0`;
- Unity Editor `6000.4.2f1`;
- authority checkpoint `stwm.simulation.m3-authority-checkpoint/v1`.

`protocol/version.json` must set current protocol to `0.3.0`, declare exactly
`active_m3_acceptance_versions=["0.3.0"]` and retain
`active_m2_acceptance_versions=["0.2.0"]`. Bootstrap preference begins with
`0.3.0`, then `0.2.0`. M2 fixtures and evidence still negotiate `0.2.0`; the M2
gate validates their schemas, examples, direction permissions, correlation and
ADR-0010 behavior without requiring repository current to remain `0.2.0`.

## Evidence contracts

`stwm.qa.m3-readiness/v1` is the fast, integration-aware repository report.
Before an owner has integrated its surface, it records a named `PENDING` with
owner, path and remediation. A partially integrated or malformed surface is
`FAIL`, not `PENDING`. `--require-m3` converts every remaining `PENDING` to
`FAIL`.

`stwm.qa.m3-acceptance-evidence/v1` is the strict release document. Its exact
JSON Schema and starting template are:

- `M3_ACCEPTANCE_EVIDENCE.schema.json`;
- `M3_ACCEPTANCE_EVIDENCE.template.json`.

Release evidence permits only `PASS` gates with non-empty details. It cannot
contain `PENDING`, `SKIP`, `NOT_RUN`, null matrices, missing artifacts, or
hand-edited claims in place of producer evidence. QA consumes CONTRACTS, SIM
and UNITY facts; it does not reproduce their authority rules.

## Blocking acceptance matrix

### Contract and catalog surface

1. The catalog surface is exactly 10 NPCs, 4 households, 8 locations, 22
   behaviors, 15 semantic object types and all 90 non-self directed
   relationship edges. Needs/personality/mood/relationship dimensions remain
   5/4/2/4 and the outcome model remains heuristic.
2. CONTRACTS publishes one versioned full-town semantic-instance manifest.
   Headless and Unity use that same manifest. Profile `M3_FULL` treats every
   missing location, NPC view, object type, capability, required slot,
   animation semantic, prop semantic or facing mapping as blocking.
3. The exact capacity profile is executable in
   `integration_tests/fixtures/m3/full-registry-profile.json`; QA does not
   maintain a competing instance list.
4. Protocol `0.3.0` provides version-aware message unions, schemas and examples
   for structured participants, snapshot presentation bindings, explicit
   field-mask/null clearing, household deltas and read-only decision traces.
   Retained 0.2 artifacts and M2 direction tests remain green.

### Behavior, society and authority

5. Every one of the 22 frozen behavior IDs has one stable targeted fixture and
   real probes for legal/illegal candidate generation, hard-cost preview,
   Resolver accept/reject, reservation/lifecycle, allowed effects,
   authoritative replay and Unity presentation. Every behavior also has a
   positive occurrence count across the complete release soak set.
6. Every one of the 10 agents is enabled and scheduled, makes decisions and
   settles actions. A legal non-idle alternative may not coexist with
   idle-only behavior for more than 1,440 game minutes. Work actions do not
   exceed their frozen bound.
7. Every household records money and food conservation. Money equals initial
   money plus unique wages minus grocery/cafe/bar charges. Food equals initial
   food plus eight units per completed grocery purchase minus completed home
   meals. No failed/cancelled charge, duplicate settlement, negative minimum,
   or missed workweek recovery is allowed.
8. Relationship evidence covers 90 target-to-actor directed edges, bounded
   values and traced deltas. Wrong-direction or untraced changes fail.
9. Knowledge covers direct participation, witnessed and told acquisition.
   Sharing an unknown event is rejected and background speech references only
   speaker-known events. Player-told records and epistemic graphs are zero in
   M3.
10. JointAction uses the central Resolver and the exact invitation allowlist
    `watch_tv`, `eat_at_cafe`, `drink_at_bar`, `walk_in_park`, `sit_in_park`.
    Acceptance/rejection, participant exclusivity, atomic reservations and
    cancel/fail/timeout release are covered. Split actions and reservation
    remnants are zero; replay matches.

### Determinism, replay and soak

11. The canonical seed is `12345`; driver chunks are exactly 1, 7 and 60 game
    minutes. Repeated execution and every chunk produce identical final-state
    and authority-log hashes.
12. Checkpoints occur at least every 360 game minutes and at finalization.
    Resume and authoritative replay have zero final/checkpoint/log mismatch and
    never mutate the source run.
13. The release seed matrix is exactly:

    - seven days: `12345`, `24680`, `97531`, `314159`, `271828`;
    - thirty days: `12345`, `24680`, `97531`.

    Each of the eight entries is `PASS`, has zero invariant violations, and
    matches final-state, ledger and authority-log replay hashes. These are release-slow facts and are never
    fabricated by a QA fixture.

### Pathology and performance

14. Per-agent candidates are at most 12 and one decision batch at most 120.
    Terminal/missing/expired reservation leaks, double-owned slots, permanent
    idle, and work-bound violations are all zero.
15. A recoverable need may remain at zero for at most 360 game minutes.
    Household recovery occurs within a workweek; all four households may not
    remain money-low for 7 days.
16. More than 80% of relation edges within 0.01 of a boundary may not persist
    for 7 days. The validator consumes the producer's resulting violation
    count, which must be zero.
17. Events are typed, semantically exactly once, edge-triggered and grow
    linearly. The maximum is 1,000 events per game day.
18. Reference metadata must identify the producer Apple-silicon MacBook Air,
    OS, Python 3.12 and RSS collection method. A 30-day run is strictly under
    900 seconds, peak RSS strictly under 1 GiB, post-warmup RSS slope at most
    1 MiB/game-day, decision-batch p95 strictly under 50 ms and tick p99
    strictly under 100 ms.

### Unity semantics and explainability

19. Unity presents all 10 NPCs, 8 locations, 15 object types and every behavior
    semantic. Required animation/prop/facing mappings and NavMesh-reachable
    slots are complete.
20. A fresh snapshot fully replaces presentation state; explicit null clears;
    active actions rebind; stale versions are rejected; duplicate slot claims
    are zero. Joint start/phase/cancel/fail/reconnect presentation is covered.
21. The debug UI is read-only and shows the complete decision trace required by
    ADR-0011. It cannot submit authority input.
22. The live smoke negotiates `0.3.0`. EditMode and PlayMode have zero failures
    and zero skipped tests. Remote licensed Unity CI is optional; release
    evidence is still mandatory.

## External artifact contract

The release JSON and all referenced files live outside the repository. Each
descriptor contains exactly `path`, `sha256`, `bytes`, `redacted`, and `schema`.
Paths are relative to the evidence directory and may not escape it or resolve
inside the checkout. Hash and byte count must match; text must be non-empty
UTF-8, sanitized of secrets and machine-local paths, and parse as its declared
JSON/JSONL/XML form.

Required producer artifacts are authority evidence, behavior coverage,
`M3_FULL` registry and report, 7-day and 30-day soak reports, replay, pathology,
performance, Unity semantic coverage, debug trace, zero-skipped EditMode and
PlayMode XML, batchmode log and repository guard report. Expected schema names
are frozen in `tools/diagnostics/check_m3.py`. The `full_registry` descriptor
must resolve to the same file supplied to `check_m3.py --registry`.

## Fast and slow shutters

The fast shutter targets 10 minutes and has a 15-minute hard limit using 2
vCPU/4 GiB. It runs static checks, QA validator tests, repository readiness and
the integration-aware adapter. It does not execute a 7-day or 30-day soak.

The release-slow shutter uses at most four Python shards of 2 vCPU/4 GiB, each
with a 60-minute hard limit. On the producer MacBook Air it is always one local
process at a time. Remote Unity is an optional separate lane and may not replace
the real sanitized batchmode artifacts. Full soak execution is explicitly an
Orchestrator-ordered release action.

## Commands

Fast integration-aware readiness:

```bash
python tools/diagnostics/check_m3.py \
  --json-output /absolute/external/m3-readiness.json
pytest --strict-config --strict-markers \
  python/tests/qa/test_m2_diagnostics.py python/tests/qa/test_m3_diagnostics.py
pytest --strict-config --strict-markers -m "m3 and m3_fast" integration_tests
```

Final release after CONTRACTS/SIM/UNITY integration and the ordered soak:

```bash
STWM_M3_FULL_REGISTRY=/absolute/external/m3/full-registry.json \
STWM_M3_QA_EVIDENCE=/absolute/external/m3/m3-acceptance-evidence.json \
pytest --strict-config --strict-markers -m "m3 and m3_fast" integration_tests
python tools/diagnostics/check_m3.py \
  --require-m3 \
  --registry /absolute/external/m3/full-registry.json \
  --evidence /absolute/external/m3/m3-acceptance-evidence.json \
  --json-output /absolute/external/m3/m3-readiness.json
```

Final acceptance requires exit code zero, zero `FAIL`, zero `PENDING`, zero
Unity skips, and evidence for every fixed soak entry. A missing upstream owner
is expected to be readable during parallel development, never acceptable in
the release command.
