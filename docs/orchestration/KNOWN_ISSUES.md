# Known issues

## Open during M4

- The M4 feature/label/package contracts and provider injection are frozen by
  baseline but not yet implemented.
- The isolated cloud data environment now contains locked `pyarrow==19.0.1`.
  Training-specific packages remain intentionally pending until the model
  architecture and training command are frozen; the base image is not mutated.
- Raw Parquet data and the exact 300-task social-anchor selection are validated.
  Codex judgments, independent anchor approval, trained weights, calibration,
  CPU inference, and neural rollout evidence remain pending M4 increments.
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

## Closed by M3 acceptance

- Protocol `0.3.0`, the full semantic-instance manifest, and the ADR-0011
  contract re-freeze are implemented and accepted.
- The ten-NPC society remains a separate compatibility profile, so accepted M1
  single-agent and M2 protocol `0.2.0` hashes and gates remain intact.
- The full 22-behavior matrix, fixed 5x7-day and 3x30-day soak, replay,
  pathology, performance, M3_FULL Unity registry, and zero-skipped Unity
  evidence pass at the accepted M3 commit.
- M3 raw run evidence is intentionally stored outside Git. The acceptance
  record preserves the external artifact paths, hashes, sizes, and final gate.

## Closed at M4 entry

- The AutoDL training host was audited: RTX 4090 24GB, 16 CPU, 120GB RAM,
  Python 3.12.3, PyTorch 2.5.1+cu124/CUDA 12.4, 30GB system disk, 50GB local
  data disk, and mounted 200GB file storage all pass.
- SSH key login, GitHub access through AutoDL network acceleration, the cloud
  repository clone, GPU compute smoke, and persistence across restart pass.

## Explicitly deferred beyond M4

- Real DeepSeek calls: M5.
- Golden-chain demo publication: M6.
- Claim/Belief, Commitment, graph models, institutions, and other roadmap stages: post-V0.
