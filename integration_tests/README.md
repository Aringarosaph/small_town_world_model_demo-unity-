# Integration tests

This directory owns tests that cross a package, process, protocol, or repository
boundary. M0 contains only repository/configuration acceptance; service, Unity,
LLM, replay, model-switching, golden-chain, and soak coverage belongs to the
milestone that implements the corresponding capability.

Use `contract_pending` only when a test is executable but its authoritative M0
input has not yet landed. Do not use it to hide a regression in an integrated
artifact.
