# Contributing

This file is the single home for the working agreement. Other docs link here instead of restating it.

## Where things live

| What | Where |
| --- | --- |
| Project overview, status, how to run | [README.md](README.md) |
| Working agreement (this file) | `CONTRIBUTING.md` |
| Domain vocabulary | `GLOSSARY.md` (created when terms are resolved) |
| Why a decision was made | `docs/adr/` |
| Agent skill configuration | [AGENTS.md](AGENTS.md) and `docs/agents/` |

## ADRs

Write an ADR only when a decision is hard to reverse, surprising without context, and the result of a real trade-off. Routine tooling choices belong in this file or the issue, not an ADR.

- Number ADRs sequentially: `docs/adr/NNNN-short-title.md`.
- Each ADR has a one-line status: `Accepted` or `Superseded by NNNN`.
- Never edit an accepted ADR except for typos. To reverse a decision, write a new ADR and mark the old one superseded.

## Docs check

A step in the gate verifies that relative links between docs resolve. There is no Markdown style linter. Spelling is covered by the prose checks (#6).

## Commits and PRs

To be decided in #5.

## Gate and git hooks

To be decided in #10.

## CI and merge rules

To be decided in #11.
