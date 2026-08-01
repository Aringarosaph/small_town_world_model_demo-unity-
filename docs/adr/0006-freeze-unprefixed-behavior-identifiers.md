# ADR-0006: Freeze unprefixed V0 behavior identifiers

## Status

Accepted for M0.

## Context

The implementation specification contains an isolated generic example using a
`behavior_` prefix, while the behavior catalog, schedules, candidate examples,
payloads, and most normative references use identifiers such as `sleep`,
`work_shift`, and `apologize`.

## Decision

V0 uses the unprefixed identifiers enumerated by `BehaviorId` and
`config/v0/behaviors.yaml`. The 22 values are frozen by the M0 manifest and are
the serialized values used by configuration, Python DTOs, JSON Schema, and the
Unity/Python protocol.

Any later rename requires an ADR, a configuration and protocol compatibility
review, regenerated Schema/examples, and a new approved freeze manifest.

## Consequences

- Downstream M1+ code must not introduce aliases such as `behavior_sleep`.
- Display labels remain separate and may be localized without changing IDs.
- The ambiguity is resolved once at the contract boundary instead of being
  handled independently by each consumer.
