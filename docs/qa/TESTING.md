# Test layout and markers

## Directory ownership

- `python/tests/qa/`: isolated tests for QA diagnostics, policies, and report
  formatting.
- `integration_tests/`: cross-boundary acceptance tests. At M0 this means
  repository structure, configuration loading, frozen catalogs, protocol
  presence, and sensitive-file checks.
- Future product-unit suites live under the owning subsystem's path, for
  example `python/tests/simulation/`. QA does not create those suites before
  their milestone exists.

## Markers

| Marker | Meaning |
| --- | --- |
| `qa` | QA-owned validation or regression coverage |
| `m0` | M0 acceptance coverage only |
| `integration` | Crosses a package, process, protocol, or repository boundary |
| `contract_pending` | Executable check waiting for an upstream M0 artifact |
| `slow` | Excluded from the default fast lane |

Markers are registered by the local `conftest.py` files so QA does not race the
CONTRACTS thread on `pyproject.toml`. The Orchestrator may later move the same
definitions into the central pytest configuration.

## Lanes

Fast QA-owned regression:

```bash
pytest --strict-config --strict-markers \
  -m "not contract_pending" python/tests/qa integration_tests
```

Full M0 readiness (expected to fail until upstream M0 inputs are integrated):

```bash
pytest --strict-config --strict-markers \
  -m "m0 and contract_pending" integration_tests
python tools/diagnostics/check_m0.py
```

An integrated upstream artifact must never be exempted merely to keep CI green.
Remove `contract_pending` once the dependency lands and the check passes.

## Test evidence

Every non-trivial failure report should include the command, repository commit,
seed when randomness exists, relevant run ID, and a path to redacted logs or a
machine-readable report. Tests must not mutate product state to manufacture a
pass.
