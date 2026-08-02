# Runtime `runs/` contract

This contract describes evidence layout; it does not implement simulation or
change domain Schema. Every executable world run, replay, soak test, or focused
reproduction writes to a new directory. The M1 accepted minimum is:

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

Redacted `metrics.jsonl`, `periodic_snapshots/`, and `errors.log` are optional.
`llm_requests.jsonl` begins only in a milestone that actually enables an LLM;
M1 must not call or log language/model services.

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
source directory or a descendant. QA-generated M1 runs use a temporary output
root outside the repository.

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
- `summary.json` is written after all JSONL streams and snapshots are flushed;
  its status may not claim success if an invariant or hash comparison failed.
- Canonical authority state and ordered-log hashes exclude timestamps, run IDs,
  output paths, and other non-authority metadata.

## Sensitive data

API keys, environment dumps, raw personal data, and unrestricted prompts are
forbidden. LLM request records must be redacted or stored separately with access
controls. QA artifacts should prefer IDs, hashes, status, latency, and bounded
error summaries over raw payloads.

M0 acceptance validates this documented contract and Git exclusion only. M1
requires the minimum layout, Headless run, and authority replay. M3 adds the
fixed heuristic-society soak/checkpoint evidence below; golden-chain release
output remains a later milestone capability.

## M2 bridge evidence

M2 Unity evidence is not written below an authority `runs/<run_id>/` directory
and is never committed. Use an external sibling tree such as:

```text
<external-qa-root>/m2/<evidence-id>/
  m2-evidence.json
  asset-registry.json
  registry-report.json
  handshake-transcript.jsonl
  editmode-results.xml
  playmode-results.xml
  batchmode.log
```

The evidence document uses `stwm.qa.m2-acceptance-evidence/v1` and references
artifacts relative to its own directory. Unity `Library/`, `Logs/`,
`TestResults/`, caches, license data, and machine-local settings are neither
authority runs nor acceptable evidence artifacts. The retained XML/JSON/log
subset must be redacted before upload.

## M3 authority and release evidence

M3 SIM continues to write each authority run below a repository-external
`runs/<run_id>/` root and adds `stwm.simulation.m3-authority-checkpoint/v1` at
least every 360 game minutes and at finalization. A checkpoint contains the
public world state plus work settlement keys, reservations, knowledge and
conversation ledgers, JointAction coordination/presentation bindings,
deterministic counters, cursors and hashes. Resume/replay creates a new run and
never rewrites its source.

The release bundle is a separate external tree:

```text
<external-qa-root>/m3/<evidence-id>/
  m3-acceptance-evidence.json
  authority-evidence.json
  behavior-matrix-report.json
  full-registry.json
  registry-report.json
  soak-7-day-report.json
  soak-30-day-report.json
  replay-report.json
  pathology-report.json
  performance-report.json
  unity-semantic-report.json
  debug-trace.jsonl
  editmode-results.xml
  playmode-results.xml
  batchmode.log
  repository-report.json
```

`stwm.qa.m3-acceptance-evidence/v1` references every file relative to its own
directory and records SHA-256, byte count, redaction and producer schema. The
fixed five 7-day plus three 30-day entries point to their aggregate soak report
and retain individual final-state/authority-log/replay hashes. None of this
tree, its Unity caches, or its underlying `runs/` directories may be committed.
