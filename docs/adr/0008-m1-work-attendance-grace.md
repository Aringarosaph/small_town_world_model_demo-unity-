# ADR-0008: Freeze M1 work attendance grace semantics

- Status: Accepted
- Date: 2026-08-02

## Context

M0 froze work attendance as a session separate from individual actions, but did
not fully define how the configured 15-minute grace period interacts with
`WORK_LATE`, completion, and wage settlement. M1 needs all three observable
outcomes—completed, late-but-completed, and missed—without allowing duplicate
wages.

## Decision

1. Any first effective work minute after the scheduled start emits
   `WORK_LATE` exactly once.
2. Arrival no later than `scheduled_start + grace_minutes` remains eligible for
   completion.
3. An eligible session completes when its effective work time reaches
   `scheduled_minutes - grace_minutes`.
4. Arrival after grace, or insufficient effective work time, emits
   `WORK_MISSED` and pays nothing.
5. `WORK_COMPLETED` and one fixed wage effect commit atomically for the session.
   A paid session cannot settle again.

## Consequences

- A normal 06:00 start completes with 480 effective minutes.
- A controlled 06:06 start records `WORK_LATE`, completes with 474 effective
  minutes, and receives one fixed wage.
- An unavailable workstation produces `WORK_MISSED` and zero wage.
- Later milestones may revise attendance policy only through a new ADR and
  regression update.
