# ADR-0001: Authority and model boundaries

- Status: Accepted
- Date: 2026-08-02

## Decision

Python Town Core is the sole authority for time, identity, location, resources, ownership, occupancy, schedules, actions, committed events, and state versioning. Candidate actions come only from versioned catalogs and rule validation.

Outcome models may predict bounded soft deltas, acceptance, and event probabilities. Language backends may parse into whitelisted schemas and verbalize permission-filtered plans. Neither may create authority facts or new executable behavior.

Heuristic, recorded, neural, mock, and template implementations share stable interfaces and must remain replaceable.

## Consequences

The system remains runnable, testable, and replayable without a neural model or external API. Learned behavior is less free-form by design.

