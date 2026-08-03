# ADR-0012: M4 distilled outcome model contract

- Status: Accepted
- Date: 2026-08-04

## Context

M3 freezes a complete deterministic ten-NPC society. Its existing
`OutcomePrediction` DTO already represents the bounded soft outputs required by
M4, but M3 has no versioned feature row, dataset, model package, provider
interface, compatibility check, or neural fallback policy.

The M4 model is a distillation target, not a new authority owner. It must learn
reviewed and teacher-generated social reactions without changing the frozen
candidate set, hard costs, reservations, economy, event visibility, or state
transaction rules.

## Decision

### Compatibility and authority

- Protocol `0.3.0`, public `WorldState` schema `v0.1`, and the accepted M3
  checkpoint remain unchanged.
- M4 adds Python-private, additive data/model contracts. No protocol version is
  bumped solely for training or local inference.
- Candidate generation, hard legality, Resolver arbitration, resource
  settlement, event type/visibility, knowledge permissions, and final state
  clamping remain rule-owned.
- The neural provider may return only an existing `OutcomePrediction`. A
  catalog-derived postprocessor applies masks, per-behavior bounds, target
  presence checks, event allowlists, and finite-value checks before the result
  can be scored or committed.
- Need deltas and event probabilities are auxiliary/preview outputs in M4.
  Accepted-path mood and Target-to-Actor relationship deltas plus social
  acceptance may affect the runtime only after postprocessing. A rejected
  social action retains the frozen rule rejection effect.

### Internal contracts

M4 freezes these schema identities:

- `stwm.model.candidate-feature-row/v1`;
- `stwm.model.outcome-label/v1`;
- `stwm.model.social-anchor/v1`;
- `stwm.model.dataset-manifest/v1`;
- `stwm.model.outcome-package/v1`;
- `stwm.model.evaluation-report/v1`;
- `stwm.qa.m4-acceptance-evidence/v1`.

The catalog value `feature_version: v0.1` remains the active feature version.
The label version is `v0.1`. A model package records both values plus source
commit, Python/PyTorch versions, architecture, vocabulary, normalization,
config/catalog hashes, split manifest hash, checkpoint hash, and evaluation
hash.

### Provider boundary

The runtime uses one batch interface:

```python
class OutcomeModel(Protocol):
    provider_id: str
    model_version: str | None

    def predict_batch(
        self,
        rows: Sequence[CandidateFeatureRow],
    ) -> Sequence[OutcomePrediction]: ...
```

Required implementations are `HeuristicOutcomeModel`, `TorchOutcomeModel`, and
`RecordedOutcomeModel`. Missing packages, hash/version mismatch, non-finite
output, invalid shape, or inference failure selects the heuristic provider and
records a structured fallback reason. Silent partial neural output is forbidden.

M3 heuristic runs retain their accepted deterministic sampling material. M4
neural sampling additionally includes state version and model version so a
package change is explicit and replayable.

### Data and artifacts

- Rows are split by complete `scenario_group_id`/episode groups, never randomly
  by row.
- Augmented descendants stay in the same split as their source anchor or
  episode.
- Actor IDs remain trace metadata and are not neural input features.
- Reviewed anchors retain separate producer and reviewer records; the reviewer
  does not overwrite the producer draft.
- Generated datasets, runs, checkpoints, reports, and weights remain outside
  Git. Git stores code, schemas, small reviewed source anchors, templates, and
  artifact descriptors/hashes only.

## Consequences

M4 can change behavior ranking and bounded social soft outcomes while leaving
hard authority and all M1-M3 compatibility profiles intact. The heuristic
provider remains a complete product path and the release is not accepted until
model switching, fallback, calibration, CPU inference, and 30-day neural soak
all pass.

Any later request for learned need commits, learned event creation/visibility,
new output fields, or a changed public snapshot requires a separate ADR and
version review.
