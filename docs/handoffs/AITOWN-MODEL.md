# AITOWN-MODEL handoff

## State

M4 was activated by the producer on 2026-08-04 from public
`main@02b9e53b8ec11b06235be704dec7d5fcd7495945`.

The logical `AITOWN-MODEL` responsibility is active under `AITOWN-ORCH`. A
separate long-running Codex task was intentionally not created at entry because
the producer reported only about 10% weekly Codex quota remaining. This does not
change path or contract ownership; it creates a clean handoff for a dedicated
task after quota reset if useful.

## Frozen inputs

- M3 accepted implementation:
  `cc7f581da0548cb5aebd3d215db3e7bd93575d11`;
- M3 release record: `docs/orchestration/M3_ACCEPTANCE_RECORD.md`;
- M4 baseline: `docs/orchestration/M4_EXECUTION_BASELINE.md`;
- model boundary: ADR-0005 and ADR-0012;
- active feature/label versions: `v0.1` / `v0.1`;
- active online protocol remains `0.3.0`;
- DeepSeek and all language work remain M5.

## Cloud target

- SSH alias: `stwm-autodl`;
- repository: `/root/autodl-tmp/STWM`;
- active work: `/root/autodl-tmp/stwm-m4-work`;
- durable root: `/root/autodl-fs/STWM/m4`;
- RTX 4090 24GB, 16 CPU, 120GB RAM;
- Python 3.12.3, PyTorch 2.5.1+cu124, CUDA 12.4;
- 30GB system, 50GB local data, 200GB mounted file storage.

Do not place credentials in the repository or handoff. Source AutoDL's official
`/etc/network_turbo` only for outbound dependency/GitHub access.

## First implementation package

The next coherent increment owns only:

1. internal M4 Pydantic contracts and generated JSON Schemas;
2. `OutcomeModel` batch Protocol;
3. `RecordedOutcomeModel` and a heuristic adapter that reproduces M3 exactly;
4. catalog mask/bounds postprocessing;
5. focused contracts/provider tests and an updated handoff.

Do not start dataset generation or PyTorch architecture work before that commit
passes. Do not change public protocol or accepted M3 behavior.

## Pause/resume

At each safe point update the durable
`/root/autodl-fs/STWM/m4/control/m4-progress.json` descriptor and this handoff.
Generated data/model artifacts are external and referenced by relative path,
SHA-256, byte size, schema, source commit, and parent artifact hashes.

Current entry stage: `M4_ACTIVATION_BASELINE`.
