# ADR-0004: Development and training environments

- Status: Accepted
- Date: 2026-08-02

## Decision

The pinned iCloud workspace remains the development repository while it is used by one active machine and shows no synchronization conflicts. Source is backed by GitHub; generated caches and artifacts are excluded from Git. A local non-iCloud clone is the contingency if Unity import churn causes measurable failures.

The M2 MacBook Air handles development, Unity, headless simulation, testing, and CPU inference. Formal M4 training uses a cloud RTX 4090 24GB host with 50GB local work storage and 100GB artifact storage, audited at M4 entry.

## M0 environment observation

On this iCloud workspace, files created inside the repository's hidden `.venv`
inherit the macOS hidden flag. Python 3.12.11 skips hidden `.pth` files, so an
editable package install can become undiscoverable even though ordinary
dependencies still import. An equivalent temporary environment outside iCloud
was verified to work in editable mode.

Local repository commands therefore use `uv sync --no-editable` and
`uv run --no-editable`. This is a contained environment workaround, not evidence
of source or Git corruption, so it does not yet trigger repository migration.
If Unity import churn or source synchronization produces a real failure, move
the working clone to a non-iCloud path as already specified by this ADR.
