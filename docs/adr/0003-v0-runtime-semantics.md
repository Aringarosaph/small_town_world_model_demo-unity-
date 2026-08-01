# ADR-0003: V0 runtime semantics

- Status: Accepted
- Date: 2026-08-02

## Decisions

1. Joint activities use one central `JointAction` aggregate with participant state and shared reservations.
2. V0 authority perception is based on high-level location. Private social events default to participants only; explicitly public events may be witnessed by eligible co-located agents. Unity room geometry does not change authority results in V0.
3. `game_minute` is the sole authority clock. Unity Live exposes `0x`, `1x`, `2x`, and `4x`; faster simulation belongs to headless mode. Action duration starts after confirmed arrival.
4. Work attendance is a session distinct from the current action, so breaks and bounded interactions can coexist with accumulated effective work time.
5. Action creation reserves resources. One-shot hard effects commit atomically during resolution; pre-resolution failure releases reservations. Continuous effects commit only the portion already elapsed.
6. The V0 learned relationship head predicts `Target -> Actor`. Actor-side changes remain deterministic behavior effects until a later evaluated ADR.

