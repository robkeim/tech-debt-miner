# tech-debt-miner

Can an LLM rank files by technical-debt risk better than churn × complexity?

This repo backtests that question. It rewinds a git repo to a past date, ranks its files, and scores the ranking against the bug fixes that followed. The baseline is churn × complexity.

## Status and scope

Research backtest, not a production tool. A null result is a valid outcome.

The process (agent workflow, quality gate, docs structure) is part of what's being studied, so it is documented alongside the code.

## How it works

_To be written once the method is settled. Decisions that shape it are recorded as ADRs in `docs/adr/`._

## Development

```sh
mise install          # cspell, lychee, actionlint (pinned in .tool-versions)
uv sync               # Python dependencies
uv run gate install   # git hooks (optional; CI runs the same gate)
uv run gate           # the full gate; `--fast` for the commit-time subset, `--fix` to autofix
```

## AI assistance

This project is built with AI assistance (Claude Code). I set the questions and design, make the decisions, and review every change before it merges. Per-change attribution is in the `Co-Authored-By` commit trailers and PR footers. See [CONTRIBUTING.md](CONTRIBUTING.md#agent-workflow).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
