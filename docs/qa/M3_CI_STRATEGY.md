# M3 QA CI strategy

## Pull-request fast shutter

The repository Python workflow adds `m3-qa-readiness` after the accepted M2
lane. It runs on Python 3.12 with a 15-minute job timeout:

1. strict Mypy and Ruff remain in the shared QA baseline;
2. focused M2/M3 diagnostic regressions prove additive protocol compatibility;
3. `check_m3.py` emits `stwm.qa.m3-readiness/v1` and allows only precise
   owner-attributed `PENDING` while upstream components are wholly absent;
4. `pytest -m "m3 and m3_fast"` runs the external-evidence adapter without
   launching any soak;
5. the readiness JSON is uploaded even when a later step fails.

The fast profile is budgeted for 2 vCPU and 4 GiB, targets 10 minutes and has a
15-minute hard stop. Existing broad M0/QA selections exclude `m3` so the M3
adapter is not accidentally run in multiple jobs.

## Release-slow shutter

The Orchestrator starts the release matrix only after CONTRACTS 0.3, SIM and
UNITY are integrated. Fixed Python work is at most four shards, each 2 vCPU/4
GiB with a 60-minute hard timeout. The required work is exactly five 7-day
seeds, three 30-day seeds, chunks 1/7/60, checkpoint/resume/replay and reference
performance. Sharding changes scheduling only; it may not change seeds,
authority order, hashes or thresholds.

On the producer MacBook Air, all slow Python and Unity work is serialized to one
process. This prevents parallel soak/replay/batchmode runs from distorting RSS,
latency or wall-time evidence. The QA branch intentionally does not start the
slow shutter.

## Unity lane

A licensed macOS ARM64 Unity batchmode job is optional remote infrastructure.
If present, it pins Editor `6000.4.2f1`, runs EditMode, PlayMode and the live
protocol `0.3.0` smoke, and exports all results outside the checkout. A remote
lane may shorten operator work but may not turn unavailable Unity execution
into a passing or skipped release fact.

## Artifact handling

Use a repository-external result directory. Authority `runs/`, Unity
`Library/`, `Logs/`, `TestResults/`, caches, credentials and license material
are never staged. Before upload, the producer generates redacted JSON, JSONL,
XML and log files; QA records their relative paths, lowercase SHA-256, byte
counts and schema names. The strict validator rejects absolute/machine-local
paths, repository-resident artifacts, secrets, malformed text and mismatched
hashes.

Only the readiness report is produced on ordinary pull requests. The complete
`stwm.qa.m3-acceptance-evidence/v1` bundle is retained and uploaded only for an
Orchestrator-ordered candidate release.
