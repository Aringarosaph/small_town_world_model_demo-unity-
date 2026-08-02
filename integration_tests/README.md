# Integration tests

This directory owns tests that cross a package, process, protocol, or repository
boundary. M0 contains only repository/configuration acceptance; service, Unity,
LLM, replay, model-switching, golden-chain, and soak coverage belongs to the
milestone that implements the corresponding capability.

Use `contract_pending` only when a test is executable but its authoritative M0
input has not yet landed. Do not use it to hide a regression in an integrated
artifact.

M3 uses `test_m3_acceptance.py` as an external-evidence adapter. With wholly
absent CONTRACTS/SIM/UNITY inputs it skips once and prints the exact pending
owners. Any partially integrated or malformed input fails. The final
`check_m3.py --require-m3` command accepts no pending/skip/not-run state and
requires the fixed release matrix. QA fixtures define expected shape and
thresholds only; they never impersonate a SIM or Unity producer result.
