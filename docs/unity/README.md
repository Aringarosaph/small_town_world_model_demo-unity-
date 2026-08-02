# Unity M2 One-NPC Bridge

This directory documents the Small Town World Model（STWM）M2 functional
greybox. The slice binds only `npc_01`, `home_a`, `cafe_bar`, the M1 home
objects, and the `CAFE_MORNING` workstation. Python Town Core remains the sole
authority; Unity owns presentation, NavMesh navigation, animation semantics,
diagnostics, and presentation reports.

## Frozen toolchain

- macOS ARM64 Unity Editor `6000.4.2f1`
- `com.unity.ai.navigation` `2.0.12`
- `com.unity.nuget.newtonsoft-json` `3.2.2`
- `com.unity.test-framework` `1.6.0`
- only the built-in Unity modules recorded in `Packages/manifest.json`

The package resolver output is committed in `Packages/packages-lock.json`.
Do not upgrade packages or open the project in another Editor version without
an explicit compatibility review.

## Controlled import

From the repository root:

```bash
STWM_UNITY_EDITOR="/Applications/Unity/Hub/Editor/6000.4.2f1/Unity.app/Contents/MacOS/Unity"
"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -quit \
  -logFile /tmp/stwm-m2-import.log
```

The first import needs access to Unity's official package registry and the
machine's valid Unity Personal entitlement. Never commit `Library/`, `Logs/`,
`Temp/`, `UserSettings/`, or machine-local license data.

## Rebuild the functional greybox

The committed scene is
`Assets/AITown/Scenes/M2FunctionalGraybox.unity`. Rebuild and validate it from
the Editor with `AITown > Create M2 Functional Graybox`, or in batchmode:

```bash
"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -executeMethod STWM.AITown.Editor.M2GrayboxFixtureBuilder.BuildAndValidateBatch \
  -quit \
  -logFile /tmp/stwm-m2-graybox.log
```

The builder uses Unity primitives only, bakes a standalone NavMesh asset, and
requires complete `home_a -> cafe_bar` and `cafe_bar -> home_a` paths plus a
complete path to every M2 interaction slot. It replaces only the Codex-owned
fixture scene and never edits user or third-party assets.

The generated blocking inventory is:

- `npc_01` with `NpcView`, `NpcNavigationController`, and
  `NpcAnimationDriver`;
- `home_a_bed_01`, `home_a_fridge_01`, and
  `home_a_dining_seat_01` with usable interaction slots;
- `cafe_bar_workstation_01` with `WORK`, `CAFE_MORNING`, and a usable slot;
- stable `home_a` and `cafe_bar` semantic locations and entrance anchors.

## Editor diagnostics

The `AITown` menu provides:

- `Validate Current Scene`: scans the blocking M2 profile and prints stable
  issue codes;
- `Export Asset Registry`: exports the current scene's deterministic registry
  and diagnostics as JSON;
- `Run Bridge Diagnostics`: checks the Editor version, registry counts, and
  all errors/warnings;
- `Create M2 Functional Graybox`: recreates the no-art fixture and NavMesh.

Missing or duplicate M2 inventory is an `ERROR` and blocks `client_ready`.
Missing full-V0 locations and objects are still emitted as `WARNING` during M2.

## Bridge operation

`TownBridgeClient` defaults to `ws://127.0.0.1:8765/town`, exactly matching the
production Python `BridgeWebSocketServer --path /town`, and M2 protocol `0.2.0`.
The committed demo fixture has `connectOnStart` enabled. Pressing Play therefore
attempts the complete live handshake automatically; when no server is running,
the debug panel shows the bounded reconnect/error state instead of inventing
local authority.

Each live connection performs:

```text
client_hello -> server_hello -> asset_registry -> asset_registry_result
             -> full world_snapshot -> client_ready
```

Reconnect creates a new connection generation and repeats the entire sequence.
No state message is applied before the fresh snapshot, a reconnect snapshot
older than the previously applied authority version is rejected, and frames
from obsolete generations are ignored. WebSocket ping/pong provides liveness;
there is no heartbeat JSON message.

Unity reports `movement_arrived`, `movement_failed`,
`movement_cancelled`, and `presentation_completed`. A
`movement_cancelled` report says only that local navigation stopped. It never
terminates the action or releases authority state; only Python may commit that
transaction and return `action_cancelled`.

The `TownDebugPanel` shows connection state, authority version, clock, NPC
location/action/phase, registry findings, and recent errors. The graybox's
animation driver uses semantic timed fallbacks, maps all three frozen
`work_shift` choices (`WORK_DESK`, `WORK_STANDING`, `WORK_WORKSHOP`) onto the
functional placeholder, and does not make hard-state settlement depend on
animation success.

The panel also exposes `0x`, `1x`, `2x`, `4x`, and Pause/Resume requests while
the Bridge is `Ready`. The public client API enforces the same ready gate and
exact allowlist; these controls request Python authority clock policy and never
set a Unity-owned simulation clock.

## Tests and fixtures

Run EditMode and PlayMode without `-quit`; Unity Test Framework exits the
batch process after writing the XML result:

```bash
"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform EditMode \
  -testResults /tmp/stwm-m2-editmode.xml \
  -logFile /tmp/stwm-m2-editmode.log

"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform PlayMode \
  -testResults /tmp/stwm-m2-playmode.xml \
  -logFile /tmp/stwm-m2-playmode.log
```

EditMode covers protocol/correlation, registry validation, navigation arrival,
`NO_PATH`, `SLOT_BLOCKED`, timeout, explicit cancellation, and recording
parsing. PlayMode uses an in-memory mock WebSocket transport to cover full
handshake/readiness, cancellation reporting, duplicate/conflicting message IDs,
disconnect, reconnect snapshot regression, fresh readiness, and obsolete
connection generations.

One additional PlayMode smoke uses the real `ClientWebSocket` transport and is
ignored by default. After starting the production Python server, enable it with:

```bash
STWM_M2_LIVE_BRIDGE=1 \
STWM_M2_LIVE_BRIDGE_URL=ws://127.0.0.1:8765/town \
"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform PlayMode \
  -testFilter STWM.AITown.Tests.PlayMode.TownBridgeClientPlayModeTests.LivePythonBridgeCompletesProductionHandshakeWhenEnabled \
  -testResults /tmp/stwm-m2-live-playmode.xml \
  -logFile /tmp/stwm-m2-live-playmode.log
```

This live smoke proves `/town` production transport/handshake interoperability;
the default Mock PlayMode suite proves only the Unity client state machine.

## External M2 acceptance evidence

Final evidence is a composition of Unity-owned observations and SIM-owned
authority observations. Unity never fabricates Python transaction counts or
zero-mutation claims. First run the production SIM adapter on the integrated
ORCH branch:

```bash
STWM_M2_AUTHORITY=/tmp/stwm-m2-authority
uv run --no-editable python -m town_core.bridge.qa_adapter \
  --config config/v0 \
  --output-root "$STWM_M2_AUTHORITY" \
  --agent npc_01 \
  --seed 12345
```

Generate raw Unity XML outside the checkout. Final PlayMode must run with the
real server and may have no skipped test:

```bash
STWM_M2_RESULTS=/tmp/stwm-m2-results

"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform EditMode \
  -testResults "$STWM_M2_RESULTS/editmode-raw.xml" \
  -logFile "$STWM_M2_RESULTS/editmode-raw.log"

STWM_M2_LIVE_BRIDGE=1 \
STWM_M2_LIVE_BRIDGE_URL=ws://127.0.0.1:8765/town \
"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform PlayMode \
  -testResults "$STWM_M2_RESULTS/playmode-raw.xml" \
  -logFile "$STWM_M2_RESULTS/playmode-raw.log"
```

Then export the external redacted bundle:

```bash
STWM_M2_EVIDENCE=/tmp/stwm-m2-acceptance
STWM_M2_SOURCE_COMMIT="$(git rev-parse HEAD)"

"$STWM_UNITY_EDITOR" \
  -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -executeMethod STWM.AITown.Editor.M2AcceptanceEvidenceExporter.ExportBatch \
  -m2EvidenceOutput "$STWM_M2_EVIDENCE" \
  -m2SourceCommit "$STWM_M2_SOURCE_COMMIT" \
  -m2EditModeResults "$STWM_M2_RESULTS/editmode-raw.xml" \
  -m2PlayModeResults "$STWM_M2_RESULTS/playmode-raw.xml" \
  -m2AuthorityEvidence "$STWM_M2_AUTHORITY/m2-authority-evidence.json" \
  -m2AuthorityTranscript "$STWM_M2_AUTHORITY/bridge-authority-transcript.jsonl" \
  -quit \
  -logFile "$STWM_M2_RESULTS/evidence-export-raw.log"
```

The exporter requires `stwm.bridge.m2-authority-evidence/v1`, `passed=true`,
the exact project/version/scenario, valid AuthorityPoints/probes, both frozen
stale-cancellation branches, and a transcript whose relative path, record count,
SHA-256, schemas, generations, directions, outcomes, and mutation counts match.
It rejects repository-local inputs/output, machine paths, sensitive fields,
failed or skipped Unity tests, a PlayMode XML without the explicitly passed
real `ClientWebSocket` `/town` smoke case, and any unsupported authority claim.

The QA summary keeps the two stale-cancellation branches explicit. The exact
current-action stale branch is represented by the SIM-owned
`python_authority_cancel_transaction_count=1`; the nonmatching/terminal branch
is derived from its named probe as zero authority transactions, zero authority
mutations, and `DIAGNOSTIC_RESYNC=true`. Broad legacy stale fields are not
copied into the final QA summary.

The bundle contains `m2-evidence.json`, sanitized XML/log, an actual scoped
`asset-registry.json`, `registry-report.json`, a combined continuous-sequence
`handshake-transcript.jsonl`, and the validated original SIM evidence/transcript
pair with its reference intact. Validate it using QA's strict `check_m2.py`
command on the integrated branch.

`Assets/AITown/Tests/Fixtures/m2-handshake-replay.json` is built from the frozen
protocol `0.2.0` examples. `TownRecordedMessagePlayer` preserves the recorded
asset-registry message ID so strict correlation remains valid during replay.

## Current cross-thread dependency

SIM owns the production bridge server and the atomic authority transaction
triggered by a valid `movement_cancelled` input. Consume that surface only
through the AITOWN-ORCH integration branch; do not duplicate its rules in Unity.
