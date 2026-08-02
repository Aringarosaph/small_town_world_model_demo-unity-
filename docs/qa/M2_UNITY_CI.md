# M2 Unity CI strategy

The Python workflow validates repository policy, QA fixtures and exported
evidence without requiring a Unity license. Unity execution belongs in a
separate macOS ARM64 lane after UNITY integrates a reproducible project and the
repository/CI owner provisions a license or supported activation method.

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

The first Unity lanes should use mock/recorded bridge fixtures. A live local
Python WebSocket lane is additive and must wrap the production authority
runtime; it cannot introduce a test-only simulation loop.

## Batchmode commands

The runner supplies the exact Editor executable in `STWM_UNITY_EDITOR` and an
external temporary directory in `STWM_M2_RESULTS`. The commands are:

```bash
"$STWM_UNITY_EDITOR" -batchmode -quit \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform EditMode \
  -testResults "$STWM_M2_RESULTS/editmode-results.xml" \
  -logFile "$STWM_M2_RESULTS/editmode.log"

"$STWM_UNITY_EDITOR" -batchmode -quit \
  -projectPath "$PWD/unity" \
  -runTests -testPlatform PlayMode \
  -testResults "$STWM_M2_RESULTS/playmode-results.xml" \
  -logFile "$STWM_M2_RESULTS/playmode.log"
```

UNITY must provide an Editor/batchmode evidence-export entry point agreed with
ORCH. Its output is the evidence JSON plus `asset-registry.json`,
`registry-report.json`, and a redacted handshake/navigation transcript. The
entry point must return nonzero when any evidence gate fails; QA does not define
Unity runtime code in order to create it.

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
missing Unity runtime is readable `PENDING` during parallel development, but a
partially integrated project or failed test is a hard failure. The final strict
gate allows no pending result.
