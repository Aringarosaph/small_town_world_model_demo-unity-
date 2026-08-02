# M2 Unity CI strategy

The Python workflow validates repository policy, QA fixtures and exported
evidence without requiring a Unity license. The reproducible Unity project and
local batchmode gate are implemented and locally accepted. Remote Unity
execution belongs in a separate macOS ARM64 lane after the repository/CI owner
provisions a runner and a supported license activation method.

## Lanes

1. **Python/static**: Python 3.12 runs Ruff, Mypy, pytest, the scoped registry
   diagnostic and the pending-capable M2 adapter. It uploads only
   `m2-diagnostics.json`.
2. **Unity EditMode**: validates semantic components, duplicate/missing IDs,
   registry export, protocol parsing, message directions, dedupe/conflict, the
   processable exact-match stale branch, rejected terminal/nonmatching stale
   branch, and obsolete generations against deterministic mocks.
3. **Unity PlayMode**: drives the no-art `home_a -> cafe_bar -> home_a` fixture,
   arrival/failure/timeout/cancel/disconnect/reconnect paths, animation fallback,
   and non-authority assertions.
4. **Evidence gate**: exports the redacted JSON/XML/log bundle outside the
   checkout, then runs `check_m2.py --require-m2 --evidence ...` against the
   integrated Python/Unity result.

Ordinary Unity lanes use mock/recorded bridge fixtures. Final evidence must also
enable the environment-gated live local Python WebSocket smoke, which wraps the
production authority runtime and may not introduce a test-only simulation loop.

## Batchmode commands

The runner supplies the exact Editor executable in `STWM_UNITY_EDITOR` and an
external temporary directory in `STWM_M2_RESULTS`. The commands are:

```bash
"$STWM_UNITY_EDITOR" -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform EditMode \
  -testResults "$STWM_M2_RESULTS/editmode-results.xml" \
  -logFile "$STWM_M2_RESULTS/editmode.log"

STWM_M2_LIVE_BRIDGE=1 \
STWM_M2_LIVE_BRIDGE_URL=ws://127.0.0.1:8765/town \
"$STWM_UNITY_EDITOR" -batchmode -nographics \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform PlayMode \
  -testResults "$STWM_M2_RESULTS/playmode-results.xml" \
  -logFile "$STWM_M2_RESULTS/playmode.log"
```

UNITY provides
`STWM.AITown.Editor.M2AcceptanceEvidenceExporter.ExportBatch`. Its output is the
evidence JSON plus `asset-registry.json`, `registry-report.json`, a redacted
handshake/navigation transcript, sanitized Unity XML/logs, and the validated
SIM authority evidence pair. It returns nonzero when any evidence gate fails.
Exact arguments and reproduction commands are in `docs/unity/README.md`.

## Artifact and cache policy

- Put `Library/`, `Temp/`, `Obj/`, `Logs/`, `UserSettings/`, `TestResults/`,
  builds and all result files outside the committed source set or in ignored
  Unity locations.
- Never upload `Library/`, raw player preferences, license material, machine
  identifiers, authorization headers, `.env`, or unrestricted payload dumps.
- Upload only sanitized XML, JSON and bounded logs. Replace machine paths,
  tokens and environment values before artifact publication.
- The evidence JSON references artifacts by paths relative to its external
  directory. No evidence artifact may resolve inside the repository.
- A CI cache, if later approved, is disposable presentation/build state and
  must never satisfy a handshake, snapshot or authority assertion.

The QA repository guard fails tracked or unignored Unity generated output. A
missing remote Unity runtime remains readable `PENDING` in the integration-aware
GitHub Python lane, but a partially integrated project or failed test is a hard
failure. Local final strict acceptance allows no pending result and has passed;
the remote licensed lane remains a repository-owner provisioning decision.
