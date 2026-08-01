# Runtime `runs/` contract

This contract describes evidence layout; it does not implement simulation or
change domain Schema. Every executable world run, replay, soak test, or focused
reproduction writes to a new directory:

```text
runs/<run_id>/
  metadata.json
  config_snapshot/
  initial_snapshot.json
  events.jsonl
  decisions.jsonl
  actions.jsonl
  llm_requests.jsonl
  metrics.jsonl
  periodic_snapshots/
  errors.log
```

`runs/` is local/generated evidence and must never be committed. CI may upload a
redacted subset as an artifact, but the repository remains the source of code
and frozen contracts, not runtime output.

## Run ID

Use a filesystem-safe, collision-resistant ID that is stable for the lifetime
of the run. Recommended form:

```text
<UTC YYYYMMDDTHHMMSSZ>-<mode>-<seed>-<short commit>-<nonce>
```

Example: `20260802T031500Z-headless-12345-a1b2c3d4-7f2a`.

The same ID appears in `metadata.json` and every log record. A replay creates a
new run directory and names the source run in metadata; it never writes into the
source directory.

## Required metadata

`metadata.json` must include, once the corresponding contract exists:

- run ID, mode, start/end UTC, status, and producing commit;
- world seed and all deterministic sub-seed policy versions;
- configuration hash, Schema version, protocol version, and feature version;
- model/prompt/backend identifiers or explicit `null`/rule/template values;
- CLI arguments and sanitized external-input provenance;
- source run ID for replay or counterfactual runs.

`config_snapshot/` is the exact effective configuration used by the run, after
defaults are resolved. It must be hashable and must not contain environment
secrets.

## Atomicity and retention

- Create the directory with a temporary/in-progress status, then finalize
  metadata only after writers are flushed.
- JSONL streams are append-only. Corrections are new records, never in-place
  edits.
- A crash leaves enough metadata and flushed records to reproduce the last
  committed state.
- Retention is external policy. Deleting old local runs must never delete a
  source run still referenced by a retained replay report.

## Sensitive data

API keys, environment dumps, raw personal data, and unrestricted prompts are
forbidden. LLM request records must be redacted or stored separately with access
controls. QA artifacts should prefer IDs, hashes, status, latency, and bounded
error summaries over raw payloads.

M0 acceptance validates this documented contract and Git exclusion only. It
does not require a headless run, replay, golden chain, or soak output; those are
M1/M3/M6 capabilities.
