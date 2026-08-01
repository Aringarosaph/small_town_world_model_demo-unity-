# ADR-0007: Use Small Town World Model as the public project name

## Status

Accepted for M1 and future public documentation.

## Context

The repository is named `small_town_world_model_demo-unity-`, while early plans,
package metadata, protocol URNs, and long-lived Codex tasks use variants of
`AI Town`. Continuing to introduce both names would make public documentation,
build output, and future interfaces harder to understand.

## Decision

The public project name is **Small Town World Model**, abbreviated **STWM** and
described in Chinese as **小镇世界模型**.

Existing M0 compatibility identifiers remain unchanged for V0:

- distribution name `ai-town-core`;
- import package `town_core`;
- `ai-town` JSON Schema URNs;
- long-lived task names `AITOWN-*`.

New public documentation, UI copy, release notes, and project descriptions use
Small Town World Model / STWM. A later internal namespace migration requires a
separate ADR, compatibility plan, version changes, regenerated artifacts, and a
new approved freeze manifest.

## Consequences

- The README and future user-facing documentation have one stable name.
- M0 protocol and replay compatibility are preserved.
- Internal legacy identifiers are explicitly documented instead of silently
  becoming a second public name.
