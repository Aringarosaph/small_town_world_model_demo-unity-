# ADR-0013: M4 reviewed social-anchor ledger

- Status: Accepted
- Date: 2026-08-04

## Context

M4 has a validated 499,978-row rule-teacher dataset. The remaining training
input gate requires at least 300 independently reviewed social anchors. The
existing `stwm.model.social-anchor/v1` object is not sufficient for that gate:

- it embeds review into the producer object and cannot prove the draft was not
  overwritten;
- its `expected_label` is an `OutcomeLabel` whose provider is correctly frozen
  to `stwm.heuristic.m3/v1`, so using it for a Codex-adjusted judgment would
  falsify provenance;
- it has no batch, issue, approval, coverage, partition, or hash-chain contract.

Changing raw label v0.1 would invalidate the accepted dataset boundary. M4
therefore needs additive, Python-private anchor artifacts rather than a public
protocol or raw-dataset migration.

## Decision

### Immutable inputs and authority

- Raw feature/label v0.1, dataset manifest v1, protocol `0.3.0`, public world
  schema `v0.1`, and M3 authority remain unchanged.
- `stwm.model.social-anchor/v1` remains a valid historical contract but is not
  release approval evidence and is not used to claim Codex-reviewed labels.
- Anchor tasks may only reference complete `CandidateFeatureRow` and heuristic
  baseline `OutcomeLabel` objects extracted from a checksum-validated dataset,
  or produced through the same production Rulebook and feature encoder.
- A producer never edits feature values, hard cost previews, masks, candidate
  legality, behavior IDs, grouping, or split ownership.
- Reviewed judgments can affect only the existing bounded `OutcomePrediction`
  soft heads. Runtime authority and catalog postprocessing remain unchanged.

### Additive private schemas

M4 adds these schema identities:

- `stwm.model.social-anchor-task/v1`;
- `stwm.model.social-anchor-judgment/v1`;
- `stwm.model.social-anchor-review-issue/v1`;
- `stwm.model.social-anchor-approval-manifest/v1`;
- `stwm.model.social-anchor-coverage-policy/v1`.

An anchor task stores the immutable source feature, heuristic baseline label,
source dataset/row hashes, behavior, family, batch, coverage signature, and
preassigned partition. A judgment separately stores producer identity,
task/draft hash, a proposed `OutcomePrediction`, rationale tags, and typed
assertions. It uses provider identity `stwm.codex.anchor-producer/v1`; it never
reuses or rewrites `OutcomeLabel.teacher_provider_id`.

A reviewer writes only issue records and an approval manifest. Producer task
and judgment artifacts remain immutable. A revision creates a new judgment and
hash; it does not overwrite the previous artifact.

### Frozen 300-anchor matrix

The first release target is exactly 300 approved anchors in seven independent
behavior batches:

| Behavior | Approved target | TRAIN | VALIDATION | ANCHOR_HOLDOUT |
|---|---:|---:|---:|---:|
| greet | 40 | 28 | 4 | 8 |
| chat | 40 | 28 | 4 | 8 |
| joke | 40 | 28 | 4 | 8 |
| compliment | 40 | 28 | 4 | 8 |
| invite_join | 40 | 28 | 4 | 8 |
| apologize | 50 | 35 | 5 | 10 |
| confront | 50 | 35 | 5 | 10 |
| **Total** | **300** | **210** | **30** | **60** |

Each behavior is one batch of 40-50 anchors. Producer output may exceed the
approved target to replace rejected/disputed entries, but a release approval
manifest selects exactly the frozen count. `TRAIN`, `VALIDATION`, and
`ANCHOR_HOLDOUT` tasks must originate from raw train, validation, and test rows
respectively. Families and augmented descendants never cross that partition.
Holdout labels are unavailable to training, early stopping, calibration, and
hyperparameter selection and are evaluated once after package/config freeze.

### Coverage policy and selection

The task selector uses deterministic, behavior-local greedy pairwise coverage.
It maximizes newly covered feasible pairs and resolves ties by SHA-256 of the
dataset manifest plus `row_id`. It limits repeated actor-target pairs and exact
coverage signatures. Only combinations observed among legal source candidates
belong to the feasible universe; the selector records structurally absent
cells instead of fabricating features.

Frozen bins:

- familiarity, affinity, trust, tension: low `[0, 1/3)`, middle `[1/3, 2/3)`,
  high `[2/3, 1]`;
- target stress: low `<0.5`, high `>=0.5`;
- actor sociability: low `<=0.50`, high `>=0.55`;
- actor irritability: low `<=0.25`, high `>=0.30`;
- privacy: `HOME` is private; all other V0 location types are public;
- event context: none, light with maximum importance `<0.60`, heavy `>=0.60`;
- social identity: same household, else coworker, else acquaintance.

Values in the small personality gaps remain valid source rows but do not
satisfy either bin. Event pairs are applicability-aware: a behavior with no
legal observed event-context candidates is not forced to synthesize them.

### Independent review

- Producer and reviewer IDs must differ. Review context contains only
  hash-fixed specs, ADRs, catalog/schema/policy, task/judgment artifacts, and a
  prior conflict index; producer chat memory is not review evidence.
- Batches contain 25-50 proposed judgments. Canonical JSON/JSONL artifacts and
  SHA-256 descriptors form a chain to the previous approval manifest.
- Checks cover identity, seven-behavior allowlist, Target-to-Actor direction,
  finite values, `[0,1]` probabilities, target presence, masks, required heads,
  per-behavior bounds, event allowlists/mutual exclusion, typed assertions,
  leakage, duplicate inputs, and cross-anchor conflicts.
- Approval may not depend on the runtime postprocessor repairing a judgment.
  Masked or out-of-bound producer values are rejected before training.
- Exact input with different proposed labels is blocking. For the same
  behavior and coverage signature, normalized input L-infinity distance at
  most `0.10` is a near neighbor. An unexplained acceptance difference over
  `0.20`, or an allowed delta difference over `max(0.04, 0.5 * catalog bound
  span)`, is disputed.
- Personality monotonicity is checked only for explicitly paired typed
  assertions; reviewers do not invent universal sociability/irritability laws.
- `APPROVED` requires all machine gates, no blocking/disputed issue, and explicit
  acknowledgment of advisory issues. `REJECTED` covers objective contract,
  bounds, mask, or leakage failure. `DISPUTED` covers unresolved semantic or
  near-neighbor conflict. Rejected/disputed entries never enter training.
- AITOWN-ORCH samples `max(3, ceil(10% of batch))` entries plus every high-risk
  assertion. Any sampled direction disagreement escalates the entire batch.

### Training overlay

Approval does not mutate the raw Parquet dataset. The frozen training-input
manifest joins approved task features with proposed judgments by task/row hash.
Reviewed TRAIN/VALIDATION judgments override the corresponding soft target for
their named suite without duplicating a raw row. ANCHOR_HOLDOUT rows remain
evaluation-only. Auxiliary raw teacher ranking labels retain heuristic
provenance and are never relabeled as Codex judgment.

## Consequences

The anchor ledger can be produced and reviewed independently without changing
M3, protocol 0.3, or the accepted raw dataset. It costs additional schema,
selection, review, and evidence work before training, but removes ambiguous
provider provenance and makes every approved judgment auditable and reversible.
