# ADR-0002: Unity version freeze

- Status: Accepted
- Date: 2026-08-02

## Decision

The Unity project uses macOS ARM64 Unity Editor `6000.4.2f1` for the implementation cycle. No patch or stream upgrade is allowed merely because a newer editor exists.

An upgrade requires a confirmed blocking editor defect, no reasonable project-level workaround, a compatibility audit, an ADR, and explicit user approval.

