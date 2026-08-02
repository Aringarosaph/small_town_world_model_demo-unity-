# M2 acceptance

M2 for **Small Town World Model（STWM）** accepts a functional, no-art Unity
gray-box client for the already accepted M1 Python authority. It does not accept
the complete town, final art, additional NPCs or behaviors, or Unity-owned
business state.

## Frozen inputs

- accepted M1 baseline: `d014e709f50d7d59a6181ddb796ae00f11c264b8`;
- M2 execution baseline and ADR-0009;
- protocol target `0.2.0`, including Unity-to-Python `movement_cancelled` as
  decided for ADR-0010;
- Unity Editor `6000.4.2f1` on macOS ARM64;
- active slice: `npc_01`, `home_a`, `cafe_bar`, and only the accepted M1
  behavior allowlist.

The final gate must run after the CONTRACTS 0.2.0 artifacts, Python bridge,
Unity bridge, and Unity evidence exporter are integrated. It may contain no
`PENDING` result.

## Blocking gates

1. The handshake is exactly `client_hello`, `server_hello`, `asset_registry`,
   `asset_registry_result`, `world_snapshot`, `client_ready`, with the
   directions in `M2_GRAYBOX_INTERFACE.md`. A rejected registry or incompatible
   version prevents readiness.
2. `m2_slice_valid` registers only `home_a`, `cafe_bar`, `npc_01`, a home
   `BED`, `FRIDGE`, `DINING_SEAT`, and a cafe `WORKSTATION` with
   `CAFE_MORNING`. Its result is `accepted=true`.
3. Missing or duplicate slice IDs, illegal capabilities, missing slots, and
   missing required animation mappings are errors. Complete-V0 content outside
   this slice is a visible `WARNING`, never an M2 error. The full-V0 reference
   fixture is diagnostic comparison only and becomes a blocking profile in M3.
4. Deterministic tests cover navigation arrived, each frozen failure reason,
   timeout, cancellation, disconnect, reconnect and resynchronization.
5. `movement_arrived`, `movement_failed`, and `movement_cancelled` travel only
   Unity to Python. For cancellation, `correlation_id == action_id`; a repeated
   identical `message_id` is idempotent, while the same ID with different
   content is rejected with zero authority mutation.
6. Python performs exactly one authoritative cancellation transaction. Unity's
   cancellation message is a non-authoritative observation and may not directly
   change action state, location, needs, resources, events, wages, or
   `state_version`.
7. Reconnect uses a new connection generation and new message IDs, repeats the
   full hello and registry sequence, receives a fresh snapshot no older than the
   previous connection's last acknowledged authority version, and does not
   resume before the new `client_ready`. Stale versions, obsolete generations,
   and late messages are rejected with zero authority mutation.
8. EditMode, PlayMode, and batchmode evidence pass. Animation failure is not an
   authority settlement prerequisite, and Unity cache is never authority.
9. M0/M1 tests, M0 freeze, M1 replay hashes, lint and type checks remain green.
   Credentials, `runs/`, Unity caches, `Logs/`, and `TestResults/` remain
   untracked.

## Evidence

Copy `M2_ACCEPTANCE_EVIDENCE.template.json` to a directory outside the
repository and populate `stwm.qa.m2-acceptance-evidence/v1`. Every gate must be
`PASS` with non-empty details. All artifact paths are relative to the external
evidence directory and must resolve to existing, redacted files.

Required artifacts are the batchmode log, EditMode and PlayMode XML, handshake
transcript, and asset-registry report. The structured cancellation and
reconnect observations are independently validated; prose cannot substitute
for their exact fields. Evidence records catalog provenance as
`catalog_protocol_version=0.1.0` and the active Bridge session separately as
`negotiated_protocol_version=0.2.0`.

## Commands

Integration-aware checks, which may report a readable pending before upstream
integration:

```bash
python tools/diagnostics/check_m2.py \
  --registry integration_tests/fixtures/m2/m2-slice-valid.json \
  --json-output /tmp/stwm-m2-diagnostics.json
pytest --strict-config --strict-markers -m m2 integration_tests
```

Final strict acceptance:

```bash
STWM_M2_QA_EVIDENCE=/absolute/path/outside/repository/m2-evidence.json \
pytest --strict-config --strict-markers -m m2 integration_tests
python tools/diagnostics/check_m2.py \
  --require-m2 \
  --registry /absolute/path/outside/repository/asset-registry.json \
  --evidence /absolute/path/outside/repository/m2-evidence.json \
  --json-output /absolute/path/outside/repository/m2-diagnostics.json
```

Final acceptance requires exit code zero, zero `FAIL`, and zero `PENDING`.
Warnings for content outside the ADR-0009 slice are allowed only when the M2
registry itself is the scoped profile.
