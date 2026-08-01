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

Markers are registered centrally in `pyproject.toml`; the local `conftest.py`
files retain equivalent registration for isolated path execution.

## Lanes

Fast QA-owned regression:

```bash
pytest --strict-config --strict-markers \
  -m "not contract_pending" python/tests/qa integration_tests
```

Full M0 readiness:

```bash
uv run --no-editable pytest --strict-config --strict-markers \
  python/tests integration_tests
uv run --no-editable python tools/diagnostics/check_m0.py
```

An integrated upstream artifact must never be exempted merely to keep CI green.
The M0 repository acceptance test has no `contract_pending` marker after
integration and therefore gates every full test run.

## Test evidence

Every non-trivial failure report should include the command, repository commit,
seed when randomness exists, relevant run ID, and a path to redacted logs or a
machine-readable report. Tests must not mutate product state to manufacture a
pass.
