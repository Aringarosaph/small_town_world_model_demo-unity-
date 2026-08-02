# Known issues

## Open after M2 acceptance

- The neural training environment will be audited when the M4 cloud host is available.
- The implementation specification contains both prefixed and unprefixed
  behavior-ID examples. M0 freezes the broadly used unprefixed form such as
  `sleep`, `work_shift`, and `apologize`; changing it requires migration review.
- Repository-local editable Python installs are unreliable in the present iCloud
  path because macOS hidden flags cause Python 3.12.11 to skip `.pth` files.
  Local commands use uv's verified `--no-editable` mode; a non-iCloud virtual
  environment is an equally valid workaround.
- A remote licensed Unity lane is not provisioned by design. The producer chose
  reproducible local zero-skipped batchmode plus live interoperability evidence
  as the M2 release gate. A macOS ARM64 runner may be added later as optional
  infrastructure, without reopening M2.

## Open for M3

- Protocol `0.3.0`, the full semantic-instance manifest, and the M3 contract
  re-freeze are authorized by ADR-0011 but not yet implemented.
- The existing M1 engine is intentionally single-agent. M3 will add a separate
  society profile instead of silently changing accepted M1 hashes.
- Full 22-behavior and 30-day evidence remains pending until the M3 runtime,
  QA adapter, and Unity full-town surface are integrated.

## Explicitly deferred

- Neural training and generated datasets: M4.
- Real DeepSeek calls: M5.
- Claim/Belief, Commitment, graph models, institutions, and other roadmap stages: post-V0.
