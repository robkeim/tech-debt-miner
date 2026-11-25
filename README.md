# tech-debt-miner

Can an LLM rank files by technical-debt risk better than churn × complexity?

This repo backtests that question. It rewinds a git repo to a past date, ranks its files, and scores the ranking against the bug fixes that followed. The baseline is churn × complexity.

## Status and scope

Research backtest, not a production tool. A null result is a valid outcome.

The process (agent workflow, quality gate, docs structure) is part of what's being studied, so it is documented alongside the code.

## How it works

_To be written once the method is settled. Decisions that shape it are recorded as ADRs in `docs/adr/`._

## Running

```sh
uv run tdm resolve --repo owner/name --cutoff 2026-07-01   # clones into repos/, prints the Run id
uv run tdm snapshot <run-id>                                 # writes snapshot.json
uv run tdm rank <run-id>                                     # writes rankings/baseline.json (tie groups, no LLM yet)
uv run tdm status <run-id>                                  # resolved, planned, ranked or scored
uv run tdm validate <run-id> [--no-fetch]                   # computes N, prints the cap report and review sheet
uv run tdm label <run-id> [--max-files N] [--no-fetch]                   # writes labels.json once the 6-month window has closed; needs `gh` for issue types
uv run tdm score <run-id>                                    # writes scores-<today>.json; refuses until label is done
uv run tdm report [--treatment llm] [--out FILE]             # aggregates every Run under runs/ into a verdict
uv run tdm resume <run-id> [--run] [--max-usd N]                        # snapshot and plan (estimate vs cap); --run continues
uv run tdm probe <run-id> [--run] [--max-usd N]                         # canary probe; Dry-run unless --run
```

`resolve` writes `runs/<run-id>/manifest.json` once. `label` counts two Label sets, the tracker-confirmed primary (`counts`) and the keyword-only sensitivity set (`keyword_counts`), reading issue state from GitHub through `gh` at that moment. It fast-forwards the Target repo clone first (fast-forward only; it refuses if upstream history was rewritten) and records the clone's HEAD in `labels.json`; pass `--no-fetch` to skip that when offline. `scripts/m1_demo.sh [owner/name] [Cutoff]` walks one Run through every stage above and prints each artifact, using an exploratory Cutoff whose window has closed; output goes to `.demo/`. `probe` is the behavioral canary from [ADR 0006](docs/adr/0006-target-repos-and-cutoff-dates.md), run after `label` has updated the clone: it sends one post-Cutoff Fix commit message with no repo context and writes `probe.json`, recording whether the model named the file that commit changed. It is reported beside results and never enters the verdict, and the `--run` flag follows the Dry-run default of [ADR 0002](docs/adr/0002-single-llm-client-choke-point.md). `label-later` writes `labels-12m.json` once the 12-month window has closed, so the 12-month sensitivity check works for a Run labeled at the primary close ([ADR 0022](docs/adr/0022-label-later-writes-the-12-month-window.md)); pass the same `--max-files` as `label`. `validate` computes the fix-size cap N once the window has closed, writes `validation.json` and prints the Label at N, 5, 10, 20 and uncapped plus a seeded review sheet of 30 Fix commits; pass N to `label --max-files` before any scored Run. `score` scores every ranking in the Run, never overwrites an earlier `scores-*.json`, and writes a Run with fewer than 10 files at Label 1 or more as excluded, with the reason, instead of dropping it. `report` reads every `scores-*.json` under `runs/` and prints the outcome of [ADR 0020](docs/adr/0020-report-aggregation-and-bootstrap.md) and the report-only sensitivity checks of [ADR 0021](docs/adr/0021-sensitivity-checks-in-report.md), naming any that flip the direction first; until the LLM ranker lands, `--treatment baseline` compares the Baseline against itself to exercise the path. `resume <run-id>` stops after `plan`, which prints per-stage token estimates and the cost against `--max-usd` and writes `estimate.json` and the stage 1 `requests.jsonl` ([ADR 0024](docs/adr/0024-dry-run-plan-stage-and-estimate.md)). The other stages are not built yet ([ADR 0008](docs/adr/0008-pipeline-stages-artifacts-and-resume.md)).

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
