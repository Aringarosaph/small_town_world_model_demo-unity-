# M0 and M1 diagnostics

`check_m1.py` is the pending-capable black-box M1 adapter. It executes the
SIM-owned `town_core.simulation.qa_adapter` after integration and validates the
three-day run matrix, invariants, deterministic hashes, replay, work/wage and
rejection probes. It never implements simulation rules.

```bash
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json
```

Add `--require-sim` only for the final integrated M1 gate. Before SIM is present,
the default command reports one readable `PENDING`; partial or broken
integration always fails.

## M0 freeze diagnostics

`check_m0.py` provides four independent groups:

- `structure`: M0 repository artifacts and their owning thread;
- `sensitive`: tracked/unignored secret, runtime, model, dataset, and Unity
  generated-file detection;
- `scope`: frozen V0 catalog sets, dimensions, minimum events, and the
  authoritative configuration validator;
- `freeze`: reviewed SHA-256 coverage plus the Orchestrator's Appendix D
  checklist sign-off.

Strict acceptance:

```bash
python tools/diagnostics/check_m0.py
```

Parallel M0 development (only upstream-owned failures become `PENDING`):

```bash
python tools/diagnostics/check_m0.py --allow-pending-m0-inputs
```

The default authoritative validator command is:

```bash
python -m town_core.cli validate-config --config config/v0
```

If CONTRACTS exposes an equivalent entry point, set
`AITOWN_M0_CONFIG_VALIDATE_CMD` to that command in the integration workflow.
The diagnostic uses `PYTHONPATH=<repo>/python` and never defines product Schema.

After CONTRACTS integration, prepare the real candidate manifest:

```bash
python -m tools.diagnostics.prepare_m0_freeze \
  --source-commit <integrated-contracts-commit>
```

The script writes `m0_config_freeze.json`, refuses to overwrite it by default,
records every eligible hash, and leaves every checklist item false. An
Orchestrator must then manually review Appendix D, fill `approved_by` and
`approved_at_utc`, and mark each verified item true. The tooling deliberately
does not provide an auto-approve mode.
