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

## Explicitly deferred

- Full 22-behavior society: M3.
- Neural training and generated datasets: M4.
- Real DeepSeek calls: M5.
- Claim/Belief, Commitment, graph models, institutions, and other roadmap stages: post-V0.
