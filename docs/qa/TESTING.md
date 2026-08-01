# Test layout and markers

## Directory ownership

- `python/tests/qa/`: isolated tests for QA diagnostics, policies, and report
  formatting.
- `integration_tests/`: cross-boundary acceptance tests. M0 covers repository,
  frozen catalogs/protocol and sensitive files; M1 adds the external Headless
  authority and replay adapter.
- Future product-unit suites live under the owning subsystem's path, for
  example `python/tests/simulation/`. QA does not create those suites before
  their milestone exists.

## Markers

| Marker | Meaning |
| --- | --- |
| `qa` | QA-owned validation or regression coverage |
| `m0` | M0 acceptance coverage only |
| `m1` | M1 one-NPC Headless authority acceptance |
| `integration` | Crosses a package, process, protocol, or repository boundary |
| `contract_pending` | Executable check waiting for an upstream M0 artifact |
| `sim_pending` | May skip only while the complete M1 SIM runtime is absent |
| `headless` | Executes or validates the Headless authority runtime |
| `determinism` | Same-seed and tick-chunk equivalence checks |
| `replay` | Snapshot plus committed-transaction authority replay |
| `invariant` | Illegal authority-state rejection and safety invariants |
| `slow` | Excluded from the default fast lane |

M0 markers are registered centrally in `pyproject.toml`. QA registers the
additive M1 markers in its local `conftest.py` files so this branch does not edit
the shared/frozen project configuration. Orchestrator should centralize the
same names during integration.

`sim_pending` is not an `xfail`. It permits one explicit skip only while none of
the SIM runtime packages is present. Partial integration, adapter failure, or
invalid evidence fails normally.

## Lanes

Fast QA-owned regression:

```bash
pytest --strict-config --strict-markers \
  -m "not contract_pending and not m1" python/tests/qa integration_tests
```

Full M0 readiness:

```bash
uv run --no-editable pytest --strict-config --strict-markers \
  -m "not m1" python/tests integration_tests
uv run --no-editable python tools/diagnostics/check_m0.py
```

M1 black-box selection:

```bash
pytest --strict-config --strict-markers -m m1 integration_tests
```

An integrated upstream artifact must never be exempted merely to keep CI green.
The M0 repository acceptance test has no `contract_pending` marker after
integration and therefore gates every M0 test run. M1 becomes strict through
adapter capability detection and the final `check_m1.py --require-sim` command.

## Test evidence

Every non-trivial failure report should include the command, repository commit,
seed when randomness exists, relevant run ID, and a path to redacted logs or a
machine-readable report. Tests must not mutate product state to manufacture a
pass.
