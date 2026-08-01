# ADR-0004: Development and training environments

- Status: Accepted
- Date: 2026-08-02

## Decision

The pinned iCloud workspace remains the development repository while it is used by one active machine and shows no synchronization conflicts. Source is backed by GitHub; generated caches and artifacts are excluded from Git. A local non-iCloud clone is the contingency if Unity import churn causes measurable failures.

The M2 MacBook Air handles development, Unity, headless simulation, testing, and CPU inference. Formal M4 training uses a cloud RTX 4090 24GB host with 50GB local work storage and 100GB artifact storage, audited at M4 entry.

