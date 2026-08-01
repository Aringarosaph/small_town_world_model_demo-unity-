# M1 SIM-to-QA interface

This is the additive testing port between AITOWN-SIM and AITOWN-QA. The public
project name is **Small Town World Model（STWM）**. The `AITOWN-*` names remain
internal task identifiers only.

QA owns the verifier and evidence shape. SIM owns every runtime observation and
probe implementation. This interface does not change or duplicate the frozen
M0 config, protocol, domain DTOs, hashing rules, or simulation rules.

## Adapter command

After SIM integration, this command must work on Python 3.12:

```bash
python -m town_core.simulation.qa_adapter \
  --config <absolute-config-v0> \
  --output-root <absolute-temporary-directory> \
  --evidence <absolute-output-root>/m1_qa_evidence.json \
  --agent npc_01 --days 3 --seed 12345 \
  --chunk-minutes 1,7,60
```

The adapter must use the production authority runtime and the production
`run-headless`/`replay` commands. It may expose thin observation hooks, but must
not contain a parallel resolver, decay calculator, action lifecycle, wage rule,
event store, or replay implementation.

The default module path is
`python/town_core/simulation/qa_adapter.py`. For an equivalent temporary
integration command, set `STWM_M1_QA_ADAPTER_CMD`. QA appends the arguments
shown above; the environment value therefore contains only the executable or
module prefix.

The adapter returns non-zero for execution/probe failure and writes exactly one
UTF-8 JSON document using schema `stwm.qa.m1-evidence/v1`. All referenced paths
are relative to the evidence file's parent and must remain outside the Git
worktree.

## Evidence contract

Top-level fields:

| Field | Required value |
| --- | --- |
| `schema` | `stwm.qa.m1-evidence/v1` |
| `project_name` | `Small Town World Model（STWM）` |
| `scenario` | Fixed M1 actor, seed, days, minutes, behavior allowlist and chunks |
| `runs` | `baseline`, `repeat`, `chunk_7`, and `chunk_60` |
| `work_probes` | `completed`, `late`, and `missed` |
| `negative_probes` | The six rejection probes below |
| `cli_contract` | Exit-code and machine-readable-summary observations |

The fixed scenario object is:

```json
{
  "agent_id": "npc_01",
  "seed": 12345,
  "days": 3,
  "start_minute": 0,
  "end_minute": 4320,
  "allowed_behavior_ids": ["idle", "sleep", "eat_at_home", "work_shift"],
  "chunk_minutes": [1, 7, 60]
}
```

Each run object must provide:

- `label`, `run_directory`, `seed`, `chunk_minutes`, `start_minute`,
  `end_minute`, `tick_count`, `skipped_tick_count`, and
  `duplicated_tick_count`;
- `active_agent_ids`, `inactive_actor_activity_count`, action/decision/event/
  committed-transaction counts, and authority state-version bounds;
- `initial_state_hash`, `final_state_hash`, and `authority_log_hash` as SHA-256;
- `illegal_state_count` and the boolean `invariants` named by the checker;
- exact five-axis `need_extrema` plus isolated `need_decay_observations` whose
  `behavior_effect_applied` is false;
- exact four-item `behavior_counts`, each positive in the three-day run.

The count/version field names are `action_count`, `decision_count`,
`event_count`, `committed_transaction_count`, `state_version_start`,
`state_version_end`, and `illegal_state_count`. Each extrema object contains
numeric `min`/`max`. Each decay observation contains numeric `before`/`after`,
integer `elapsed_minutes`, and boolean `behavior_effect_applied`.

`baseline.replay` additionally contains the output directory, transaction
count, expected/actual final hashes, match flag, and the source run's complete
tree hash before and after replay. The replay directory is a new sibling run;
it may never be the source run or its descendant.

The exact replay keys are `output_directory`, `transaction_count`,
`expected_final_state_hash`, `actual_final_state_hash`, `match`,
`source_tree_hash_before`, and `source_tree_hash_after`.

The authority-log hash covers the ordered authority-bearing projections of
`decisions.jsonl`, `actions.jsonl`, `transactions.jsonl`, and `events.jsonl`.
SIM uses the same canonical stable-JSON policy as authority state hashing and
excludes timestamps, run IDs, output paths, and other non-authority metadata.
This makes repeat and tick-chunk comparison independent of directory names.

## Required invariant keys

Every run reports these observations from the production authority state:

```text
needs_in_range
mood_in_range
resources_nonnegative
single_primary_action
exclusive_slots
action_lifecycle_valid
state_versions_monotonic
record_ids_monotonic
event_ledger_append_only
complete_decision_trace
wages_exactly_once
```

The verifier also requires zero illegal states, exact clock bounds, positive
evidence counts, identical repeat/chunk hashes, the complete run layout, and no
activity from inactive NPC records.

## Work probes

The production resolver is exercised with controlled schedule/start inputs:

| Probe | Required event | Completed | Wage settlements | Wage amount |
| --- | --- | ---: | ---: | ---: |
| `completed` | `WORK_COMPLETED` | true | 1 | catalog `fixed_shift_wage` |
| `late` | `WORK_LATE` | true | 1 | catalog `fixed_shift_wage` |
| `missed` | `WORK_MISSED` | false | 0 | 0 |

Paid probes also report `wage_after_completion: true`. QA loads the frozen
catalog value; it does not copy the wage constant.

## Rejection probes

The exact probe names are:

```text
stale_state_version
negative_money
negative_food
needs_out_of_range
overlapping_primary_action
event_mutation
```

Each probe contains `accepted: false`, a stable non-empty `rejection_code`, and
identical authority state hashes before and after. `event_mutation` additionally
contains identical ledger hashes before and after. The adapter must submit these
to the production validation/resolver/event-store boundary; constructing an
expected answer in QA is forbidden.

The exact common probe keys are `name`, `accepted`, `rejection_code`,
`state_hash_before`, and `state_hash_after`. The event-mutation probe also uses
`ledger_hash_before` and `ledger_hash_after`.

`cli_contract` contains integer `run_headless_exit_code` and
`replay_exit_code`, plus boolean `run_headless_summary_machine_readable`,
`replay_summary_machine_readable`, and `invalid_input_nonzero`.

## Pending-to-strict transition

- With no SIM runtime packages present, `check_m1.py` reports
  `M1_SIM_NOT_INTEGRATED` as `PENDING` and exits zero.
- If any SIM runtime package appears but the complete packages or adapter are
  missing, the result is `FAIL`.
- Once the adapter exists, command, evidence, invariant, or artifact failures
  are always `FAIL` and cannot downgrade to pending.
- `--require-sim` converts the pre-integration pending result to failure for the
  Orchestrator's final M1 gate.

Run the final gate with:

```bash
python tools/diagnostics/check_m1.py \
  --output-root /tmp/stwm-m1-qa \
  --json-output /tmp/stwm-m1-diagnostics.json \
  --require-sim
```
