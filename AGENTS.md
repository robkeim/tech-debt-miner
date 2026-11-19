## Working agreement

Rules for commits, PRs, the gate, and docs live in `CONTRIBUTING.md`. Follow it; this file only routes you to them and configures agent skills.

## Read first

| If you are... | Read |
| --- | --- |
| Starting any task | [Agent workflow](CONTRIBUTING.md#agent-workflow) (definition of done, review step, limits) |
| Using domain terms | `GLOSSARY.md` |
| Touching LLM calls or the SDK | [ADR 0002](docs/adr/0002-single-llm-client-choke-point.md) |
| Writing or changing tests | [Testing](CONTRIBUTING.md#testing) and [ADR 0003](docs/adr/0003-tests-never-touch-network-or-llm.md) |
| Committing or opening a PR | [Commits and PRs](CONTRIBUTING.md#commits-and-prs) |
| Running or changing the gate | [Gate and git hooks](CONTRIBUTING.md#gate-and-git-hooks) |
| Touching run reproducibility | [ADR 0001](docs/adr/0001-reproducibility-means-replay.md) |

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `robkeim/tech-debt-miner` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
