# Unity M0 baseline

The Unity editor version is frozen at `6000.4.2f1` on macOS ARM64.

M0 reserves the owned script and test paths but does not implement the bridge or create user assets. Package selection and the first editor-generated project settings are deferred until the M2 vertical slice.

Codex-owned paths live under `Assets/AITown/`. User and third-party art assets must not be modified by automation without explicit scope.

