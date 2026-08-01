# AITOWN-QA handoff

## Current responsibility

Long-lived QA/observability owner for **Small Town World Model（STWM）**. The
`AITOWN-QA` name remains an internal task compatibility identifier.

M0 is accepted and frozen. This increment adds only the M1 black-box QA/CI,
evidence, marker, run/log, and acceptance baseline for the one-NPC Headless
authority slice. It does not implement simulation product logic or modify
frozen config, protocol, domain DTOs, hashes, or `pyproject.toml`.

## M1 QA delivered

- Added a pending-capable SIM adapter gate in `tools/diagnostics/check_m1.py`.
  Complete SIM absence is reported as `PENDING`; partial integration, command
  failure, malformed evidence, or invariant failure is fatal.
- Added validator regression tests and a marked repository integration test.
- Added the `m1`, `sim_pending`, `headless`, `determinism`, `replay`, and
  `invariant` marker conventions without editing shared project configuration.
- Added a Python 3.12 `m1-qa-readiness` CI lane after the strict M0 lane.
- Specified the SIM-owned additive evidence port and documented M1 acceptance,
  run layout, transaction logs, canonical ordered-log hashing, and replay
  non-mutation.
- Reused the frozen catalog loader for `fixed_shift_wage` and the M0 sensitive/
  generated-file guard. QA contains no wage, decay, resolver, event, or replay
  rule implementation.

## Coverage

The evidence verifier covers:

- exactly 4,320 clock ticks with no skips/duplicates;
- exact five needs, range extrema, isolated negative-decay observations, and
  mood/resource invariants;
- only `idle`, `sleep`, `eat_at_home`, and `work_shift`, all exercised;
- action lifecycle, primary-action/slot exclusivity, state versions, stable IDs,
  append-only events, and complete decision traces;
- completed/late/missed work probes plus catalog-valued exactly-once wages;
- same-seed repeat equality, chunk sizes 1/7/60 equality, and canonical ordered
  authority-log equality;
- snapshot plus ordered-transaction replay, final-hash equality, a separate
  replay run, and unchanged source-run tree hash;
- rejection without mutation for stale version, negative money/food,
  out-of-range needs, overlapping primary action, and event mutation;
- no tracked runs, generated datasets, model artifacts, caches, or credentials.

M1+ product behavior, Unity runtime/transport, all-10-NPC execution, social
updates, language/model calls, training data, and long-term architecture remain
out of scope.

## Exact SIM interface required

SIM must add this module outside the M0-frozen surface:

```text
python/town_core/simulation/qa_adapter.py
```

It must accept:

```bash
python -m town_core.simulation.qa_adapter \
  --config <absolute-config-v0> \
  --output-root <absolute-temporary-directory> \
  --evidence <absolute-output-root>/m1_qa_evidence.json \
  --agent npc_01 --days 3 --seed 12345 \
  --chunk-minutes 1,7,60
```

The module drives the production authority runtime and the required
`run-headless`/`replay` CLI; it emits
`stwm.qa.m1-evidence/v1`. The complete field/probe contract is in
`docs/qa/M1_SIM_QA_INTERFACE.md`. `STWM_M1_QA_ADAPTER_CMD` may temporarily
replace only the executable/module prefix.

SIM must keep all referenced run/replay directories below the requested output
root and outside the worktree. Its adapter must not reproduce a second ruleset.

## Orchestrator integration steps

1. Integrate AITOWN-SIM first, then this QA commit, without replaying the old M0
   QA branch history.
2. Confirm SIM provides all four runtime package directories plus
   `simulation/qa_adapter.py`; once any appears, missing pieces are a hard gate.
3. Add the six M1 marker declarations from the QA `conftest.py` files to
   `pyproject.toml` as an integration-only centralization change. QA deliberately
   did not touch that shared file.
4. Run the ordinary M0 lanes and verify the M0 freeze manifest remains clean.
5. Run the final strict command below with a fresh temporary output root. Zero
   pending findings are permitted.
6. Retain only the redacted diagnostic/evidence JSON as CI artifacts. Do not
   commit `runs/` or upload raw runtime payloads without separate review.

Final strict command:

```bash
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json \
  --require-sim
```

## Current expected result before SIM integration

On this QA-only branch, validator unit tests and all M0 gates pass. The M1
repository adapter skips with `M1_SIM_NOT_INTEGRATED`, and the default diagnostic
returns zero with one explicit `PENDING`. `--require-sim` intentionally fails.

Verified with Python 3.12.11:

- Ruff lint and format: passed;
- Mypy: 26 source files passed;
- Pytest: 36 passed, one SIM-pending integration test skipped;
- strict M0 diagnostics: 58 passed, zero pending/failures;
- default M1 diagnostics: one pass, one pending, zero failures;
- strict M1 diagnostics: exit 1 on the sole missing-SIM condition, as intended.

This pending state is actionable, not permanent: after SIM integration the
checker cannot downgrade adapter/evidence/runtime failures to pending.

## Files changed

- `.github/workflows/python-ci.yml`
- `integration_tests/conftest.py`
- `integration_tests/test_m1_acceptance.py`
- `python/tests/qa/conftest.py`
- `python/tests/qa/test_m1_diagnostics.py`
- `tools/diagnostics/check_m1.py`
- `tools/diagnostics/README.md`
- `docs/qa/M1_ACCEPTANCE.md`
- `docs/qa/M1_SIM_QA_INTERFACE.md`
- `docs/qa/TESTING.md`
- `docs/qa/RUNS_CONTRACT.md`
- `docs/qa/LOG_FORMAT.md`
- `docs/handoffs/AITOWN-QA.md`

## Validation commands

```bash
ruff check .
ruff format --check .
mypy python/town_core
mypy --strict --explicit-package-bases \
  tools/diagnostics python/tests/qa integration_tests
pytest --strict-config --strict-markers -m "not m1" \
  python/tests integration_tests
pytest --strict-config --strict-markers \
  python/tests/qa/test_m1_diagnostics.py integration_tests/test_m1_acceptance.py
python tools/diagnostics/check_m0.py
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json
```
