# Known issues

## Open after M2 local acceptance

- The neural training environment will be audited when the M4 cloud host is available.
- The implementation specification contains both prefixed and unprefixed
  behavior-ID examples. M0 freezes the broadly used unprefixed form such as
  `sleep`, `work_shift`, and `apologize`; changing it requires migration review.
- Repository-local editable Python installs are unreliable in the present iCloud
  path because macOS hidden flags cause Python 3.12.11 to skip `.pth` files.
  Local commands use uv's verified `--no-editable` mode; a non-iCloud virtual
  environment is an equally valid workaround.
- Remote strict Unity execution is not yet provisioned. It needs a macOS ARM64
  runner, Unity `6000.4.2f1`, and a repository-owner-approved Personal-license
  activation method. Local batchmode evidence is complete and reproducible.

## Explicitly deferred

- Full 22-behavior society: M3.
- Neural training and generated datasets: M4.
- Real DeepSeek calls: M5.
- Claim/Belief, Commitment, graph models, institutions, and other roadmap stages: post-V0.
