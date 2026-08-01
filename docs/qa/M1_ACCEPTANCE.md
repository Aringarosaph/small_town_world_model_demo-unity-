# M1 acceptance: one-NPC Headless authority

M1 for **Small Town World Model（STWM）** is accepted only after the frozen M0
contracts drive one active NPC through three deterministic game days and replay
reaches the identical final authority-state hash.

## In scope

- game-minute clock determinism for exactly 4,320 one-minute ticks;
- five needs within `[0, 1]`, config-owned negative decay, and mood bounds;
- only `idle`, `sleep`, `eat_at_home`, and `work_shift`;
- one primary action, exclusive slots, valid lifecycle, and monotonic authority
  versions;
- on-time/late/missed shifts and exactly-once post-completion wages;
- append-only ordered events and complete action/decision/transaction evidence;
- same-seed repeat equality, chunk sizes 1/7/60 equality, and replay equality;
- rejection without mutation for stale versions, negative resources,
  out-of-range needs, overlapping actions, and event mutation;
- repository exclusion of runs, generated data, model artifacts, caches, and
  credentials.

Unity transport, the full 10-NPC society, social behavior, language/model calls,
training data, and long-term architecture features are not M1 gates.

## Automated lanes

```bash
# M0 remains independently frozen and green
python tools/diagnostics/check_m0.py

# QA-owned validator regression tests
pytest --strict-config --strict-markers python/tests/qa/test_m1_diagnostics.py

# Pending-capable branch check; becomes strict as soon as SIM appears
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json

# Pytest black-box adapter
pytest --strict-config --strict-markers -m m1 integration_tests

# Final integrated acceptance; PENDING is not permitted
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json \
  --require-sim
```

The CI `m1-qa-readiness` job runs the pending-capable form so this QA branch can
land before SIM. The transition is fail-closed: a partial SIM integration is a
failure, and an available adapter must produce fully valid evidence.

## Acceptance checklist

- [ ] Python 3.12 Ruff lint and format checks pass.
- [ ] Strict Mypy and all M0 tests/diagnostics still pass.
- [ ] M1 validator unit tests pass.
- [ ] `check_m1.py --require-sim` has zero `FAIL` and zero `PENDING` findings.
- [ ] The four Headless runs have identical final-state and authority-log
      hashes.
- [ ] Replay applies every committed transaction, writes a new run, leaves the
      source tree unchanged, and matches the recorded final hash.
- [ ] All required behaviors, needs, work outcomes, safety rejections, and
      invariant observations are present.
- [ ] No run directory or sensitive/generated output is staged or tracked.
- [ ] The diagnostic JSON report is retained as the CI artifact; raw runs stay
      local unless separately reviewed and redacted.

## Failure ownership

- `QA`: verifier bugs, marker/CI regressions, or sensitive-file detector issues.
- `SIM`: runtime, adapter, evidence, deterministic/replay, and invariant issues.
- `ORCHESTRATOR`: cross-thread ambiguity, frozen-surface changes, or gate
  exceptions. Exceptions require an explicit decision; QA does not weaken a
  check locally.

The exact additive evidence port is documented in
`docs/qa/M1_SIM_QA_INTERFACE.md`.
