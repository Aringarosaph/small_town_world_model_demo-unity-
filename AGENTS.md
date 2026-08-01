# AI Town repository instructions

## Authority

- `docs/specs/AI_Town_V0_Orchestrator_Implementation_Spec.md` is the active implementation source of truth.
- `docs/specs/AI_Town_Long_Term_Architecture_Roadmap.md` is a constraint and roadmap, not a V0 backlog.
- Accepted ADRs in `docs/adr/` refine ambiguities. A later accepted ADR supersedes an earlier conflicting implementation detail.
- `AITOWN-ORCH` owns cross-thread contracts and milestone acceptance.

## Scope discipline

- Work only inside the assigned milestone and path ownership.
- Do not introduce Claim/Belief graphs, Commitments, GNNs, RSSMs, RL, free behavior generation, or other post-V0 roadmap features.
- Do not let learned or language systems mutate authority fields.
- Do not modify user or third-party Unity art assets unless the task explicitly includes them.
- Cross-thread schema or protocol changes require an ADR and Orchestrator review.

## Repository safety

- Never commit `.env`, API keys, Unity generated directories, runs, generated datasets, caches, or model weights.
- Preserve unrelated user changes and use scoped commits.
- Keep IDs, time units, numeric directions, relation direction, and protocol versions explicit.
- Every deliverable includes tests or executable validation plus an updated handoff.

## Milestone boundary

M0 is accepted and frozen. Product simulation logic begins in M1 only after an
explicit M1 task. Changes to M0-frozen files require an ADR, version review, new
hash manifest, and Orchestrator acceptance.
