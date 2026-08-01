# Known issues

## Open after M0

- Unity package versions beyond the editor version are not frozen until the first M2 project import proves the minimal package set.
- The neural training environment will be audited when the M4 cloud host is available.
- The implementation specification contains both prefixed and unprefixed
  behavior-ID examples. M0 freezes the broadly used unprefixed form such as
  `sleep`, `work_shift`, and `apologize`; changing it requires migration review.
- Concrete Unity object instances and package versions remain an M2 asset-registry
  responsibility; M0 freezes only semantic types and editor `6000.4.2f1`.
- Repository-local editable Python installs are unreliable in the present iCloud
  path because macOS hidden flags cause Python 3.12.11 to skip `.pth` files.
  Local commands use uv's verified `--no-editable` mode; a non-iCloud virtual
  environment is an equally valid workaround.

## Explicitly deferred

- Runtime simulation logic: M1.
- Unity bridge behavior: M2.
- Full 22-behavior society: M3.
- Neural training and generated datasets: M4.
- Real DeepSeek calls: M5.
- Claim/Belief, Commitment, graph models, institutions, and other roadmap stages: post-V0.
