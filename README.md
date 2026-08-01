# AI Town

AI Town is a Unity and Python research demo for a small, deterministic, event-sourced social simulation enhanced by a compact learned social outcome model and a bounded language interface.

Milestone M0 is complete: the repository, configuration catalogs, domain DTOs,
Unity/Python protocol, generated JSON Schema, CI, and acceptance gates are frozen.

## Status

- Unity editor: `6000.4.2f1` (frozen for V0 implementation)
- Python: `3.12.x`, managed locally with `uv`
- Python authority core: contracts only; simulation runtime begins in M1
- Neural model training: deferred to M4 on a separate cloud environment
- Language backend: DeepSeek V4 Flash with mock and template fallbacks, deferred to M5

The authoritative implementation specifications are versioned under `docs/specs/`.

## M0 validation

```bash
uv sync --extra test --no-editable
uv run --no-editable python -m town_core.cli validate-config --config config/v0
uv run --no-editable pytest
uv run --no-editable ruff check .
uv run --no-editable ruff format --check .
uv run --no-editable mypy
uv run --no-editable python tools/diagnostics/check_m0.py
```

The accepted baseline has 28 passing tests and 58 passing M0 diagnostics. No
Unity runtime, model training, or live DeepSeek call is required for M0.

`--no-editable` is intentional for the current macOS iCloud workspace: files
inside its hidden `.venv` inherit the macOS hidden flag, and Python 3.12.11 then
skips editable-install `.pth` files. A virtual environment placed outside
iCloud may use uv's default editable mode.
