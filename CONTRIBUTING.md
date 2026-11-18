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

PRs are squash-merged, so the PR title becomes the commit on `main`.

### Format

`<type>(<scope>)<!>: <subject>`

- **Types:** `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. There is no `style`; formatting is handled by tooling.
- **Scope:** optional, a short lowercase noun for the area (`agents`, `docs`, `ci`, a module name). No allowlist.
- **Subject:** imperative, lowercase after the prefix, no trailing period, at most 72 characters.
- **Body:** optional, wrapped at 72. Trailer lines such as `Co-Authored-By:` are exempt from the wrap.
- **Breaking changes:** put `!` after the type or scope (`feat(rank)!: ...`). Add a `BREAKING CHANGE:` footer when the change needs a migration note.
- **AI attribution:** keep the `Co-Authored-By:` trailer on commits and the `Generated with Claude Code` line at the end of PR bodies.

### Checks

- **Locally:** a `commit-msg` hook validates every commit message (wiring in #10).
- **In CI:** the PR title is validated. Branch commits are not, since they are squashed away.
- **Tool:** a Python-native checker (for example `commitizen`), so the repo needs no Node dependency. Exact tool and wiring are decided in #4, #10 and #11.

### Merge requirements

Requirements this convention places on the repo settings (set up in #11):

- The PR title check is a required status check on `main`, with no admin bypass.
- The title workflow also runs on the `edited` PR event, so fixing a title re-runs the check.
- Squash-merge only, with the default commit message set to "PR title + PR body". The commit on `main` is then the one CI validated.

### Branches, issues, and PRs

- **Branch names:** `<github-user>/<slug>`, for example `robkeim/commit-and-pr-conventions`. Convention only; not enforced, since the name is gone after the squash.
- **Issue links:** put `Closes #N` in the PR body. Commit footers need no issue reference, because the squash commit carries the PR body.
- **PR template:** `.github/pull_request_template.md` has Summary, Linked issue, Test plan, and Tradeoffs to check.
- **Issue templates:** `.github/ISSUE_TEMPLATE/` has bug and feature forms that apply `needs-triage`. Blank issues stay enabled for wayfinder tickets.
- **Changelog and releases:** none for now. The commit history keeps that option open.

## Gate and git hooks

To be decided in #10.

## CI and merge rules

To be decided in #11.
