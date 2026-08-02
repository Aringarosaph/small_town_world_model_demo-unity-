# Small Town World Model repository instructions

## Authority

- `docs/specs/AI_Town_V0_Orchestrator_Implementation_Spec.md` is the active implementation source of truth.
- `docs/specs/AI_Town_Long_Term_Architecture_Roadmap.md` is a constraint and roadmap, not a V0 backlog.
- Accepted ADRs in `docs/adr/` refine ambiguities. A later accepted ADR supersedes an earlier conflicting implementation detail.
- Small Town World Model（STWM）is the public project name. Existing `ai-town`
  and `AITOWN-*` values are M0 compatibility identifiers, not competing public names.
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

M0 is accepted and frozen. M1 is implemented and accepted on public `main` as the
one-NPC Headless authority slice: clock, state initialization, candidates,
utility, resolver, action lifecycle, needs, work/wage settlement, append-only
events, run evidence, and authoritative replay for `idle`, `sleep`,
`eat_at_home`, and `work_shift`.

M2 is implemented and accepted as the one-NPC Unity functional-greybox slice:
loopback WebSocket bridge, protocol `0.2.0`, semantic registry,
navigation/presentation, cancellation, reconnect/resync, debug UI, and external
evidence. The producer accepted reproducible local Unity batchmode evidence as
the release gate; remote licensed Unity CI is optional. M3 is not active until
Orchestrator assigns it. Do not enable the complete 10-NPC society, implement neural
inference/training, call DeepSeek, or introduce any post-V0 roadmap feature.
Changes to frozen M0, accepted M1, or accepted M2 contracts require an
ADR, version review, regenerated evidence, and Orchestrator acceptance.
