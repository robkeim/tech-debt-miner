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

The gate runs two prose checks. Both report only; neither can autofix.

- **Spelling:** `cspell` with the `en-US` dictionary, a `flagWords` list of British spellings, and one alphabetized project words list. It covers Python source, Markdown, YAML and TOML config, and commit messages. Add a word to the list in the PR that needs it; use inline `cspell:disable` only for one-offs like hashes.
- **Links:** `lychee --offline --include-fragments` verifies that relative links and heading anchors in docs resolve. External URLs are not checked.

There is no Markdown style linter. The local hook runs `cspell` on staged files; the gate and CI run both checks in full.

## Commits and PRs

To be decided in #5.

## Gate and git hooks

To be decided in #10.

## CI and merge rules

To be decided in #11.
