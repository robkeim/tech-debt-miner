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

- **Locally:** a `commit-msg` hook validates every commit message (see [Gate and git hooks](#gate-and-git-hooks)).
- **In CI:** the PR title is validated. Branch commits are not, since they are squashed away.
- **Tool:** `commitizen`'s parser plus the repo's extra rules, in the gate package, so the repo needs no Node dependency. The hook and the CI title check call the same function.

### Merge requirements

Requirements this convention places on the repo settings (set up in #11):

- The PR title check is a required status check on `main`, with no admin bypass.
- The title workflow also runs on the `edited` PR event, so fixing a title re-runs the check.
- Squash-merge only, with the default commit message set to "Pull request title". GitHub appends `(#N)`, so the commit on `main` is exactly the title CI validated and links back to the PR.

### Branches, issues, and PRs

- **Branch names:** `<github-user>/<slug>`, for example `robkeim/commit-and-pr-conventions`. Convention only; not enforced, since the name is gone after the squash.
- **Issue links:** put `Closes #N` in the PR body. Commit footers need no issue reference; the `(#N)` suffix links the commit to the PR.
- **Keeping history:** the PR body stays on GitHub, reachable from the `(#N)` link. Put lasting rationale in an ADR or the relevant doc, not only the PR body, and edit the squash message at merge time when a change needs commit-level context.
- **PR template:** `.github/pull_request_template.md` has Summary, Linked issue, Test plan, and Tradeoffs to check.
- **Issue templates:** `.github/ISSUE_TEMPLATE/` has bug and feature forms that apply `needs-triage`. Blank issues stay enabled for wayfinder tickets.
- **Changelog and releases:** none for now. The commit history keeps that option open.

## Security checks

Most checks run on GitHub's side and add no gate runtime. [SECURITY.md](SECURITY.md) covers reporting.

| Check | Where it runs | Blocking |
| --- | --- | --- |
| Secret scanning and push protection (validity checks on, non-provider patterns off) | GitHub | Push protection blocks the push |
| CodeQL (Python, default setup, PRs plus weekly) | GitHub | No |
| Dependabot alerts and security updates | GitHub | No |
| `pip-audit` against `uv.lock` | CI only | PR runs report only; the weekly scheduled run fails |
| `actionlint` and `zizmor` (offline, no token) | CI always; locally only when workflows change | Yes, part of the gate |

Left out as redundant:

- **gitleaks:** push protection covers provider-pattern secrets, and gitleaks is in maintenance mode.
- **bandit:** ruff `ALL` includes the `S` rules.
- **Semgrep:** overlaps CodeQL, sees one file at a time, and `semgrep ci` needs a login.
- **OpenSSF Scorecard:** zizmor and the ruleset cover its useful checks.

## Testing

Runs with `pytest`; config lives in `pyproject.toml`. Rationale for the network and LLM rules is in [ADR 0003](docs/adr/0003-tests-never-touch-network-or-llm.md).

- **Tiers:** every test carries one marker, enforced by a conftest hook and `--strict-markers`. Tests live under the matching directory, mirroring `src/tech_debt_miner/`.
  - `unit` (`tests/unit/`): pure and in-memory.
  - `integration` (`tests/integration/`): tiny fixture repo, real git, fake LLM, including the Dry-run end-to-end test.
  - `policy` (`tests/policy/`): architecture rules such as "only the client imports the SDK" (ADR 0002) and the Leakage test.
- **No network:** `pytest-socket` blocks all sockets in every test, with no localhost exception and no opt-out marker until a test truly needs one.
- **LLM in tests:** a hand-written fake client for logic, plus a few committed recorded responses for parse and Replay fidelity. Recordings come from a manual script with the real key, never CI. A test fails if a recording lacks its Manifest metadata (model snapshot, request ID).
- **Leakage test:** a fixture repo with commits before and after a Cutoff date; post-cutoff commits carry a poison marker. It runs through the Dry-run path and asserts the marker never appears in any prompt, feature, or churn and complexity input. It also checks it fails when the cutoff filter is disabled.
- **Fixture repo:** generated in `tmp_path` by a shared helper with fixed author, committer and dates. No committed `.git` or bundle. The Dry-run test asserts zero LLM calls and a written Manifest.
- **Property-based:** `hypothesis` only for scoring and ranking metrics, cutoff and date handling, and cache key stability. CI uses a derandomized profile.
- **Order and clock:** `pytest-randomly` is always on and the seed is printed. An autouse fixture freezes the clock with `time-machine`; tests can override it.
- **Coverage:** branch coverage with a global floor of 90% (`fail_under`) and a 90% diff-coverage gate on changed lines in CI (`diff-cover` against `origin/main`). `# pragma: no cover` needs a reason. The `--fast` gate skips both. 90 is a starting point to adapt; tests exist to catch regressions, so lower the number before writing a test just to hit it.
- **Skips and flakes:** `skip` and `xfail` need a reason that links an issue, with `xfail_strict = true`. A flaky test is fixed or deleted; no retry plugins.
- **Config:** `filterwarnings = ["error"]` and `--durations=10` always on. No time limit; add a `slow` marker only if the suite gets slow.
- **Writing tests:** every `feat` ships with tests and every `fix` with a regression test that fails before the fix. Review and the PR template's Test plan check this; there is no automation. `tdd` is the recommended default for agents, not mandatory.
- **Not adopted:** mutation testing, for now.

## Gate and git hooks

`uv run gate` is the single definition of green. Hooks call it fast, CI calls it in full, and CI is authoritative.

| Mode | Where it runs | What it runs |
| --- | --- | --- |
| `uv run gate --fast` | `pre-commit` hook | `ruff format --check`, `ruff check`, `pyright` (whole project); `cspell` on staged files; `actionlint` and `zizmor` only when workflow files are staged |
| `uv run gate` | `pre-push` hook, CI | Everything in fast, plus `pytest` with coverage, `diff-cover`, full `cspell`, `lychee` |
| `uv run gate commit-msg <file>` | `commit-msg` hook | Commit message rules from [Commits and PRs](#commits-and-prs) |
| `uv run gate pr-title` | CI | The same function, applied to the PR title |

`pip-audit` is CI only (see [Security checks](#security-checks)).

- **Hooks:** `pre-commit` with three stages (`pre-commit`, `commit-msg`, `pre-push`). Install once with `uv run gate install`; nothing enforces it, since CI catches whatever a missing hook would have.
- **Report only:** the gate never changes files. Humans run `uv run gate --fix` (`ruff format` and `ruff check --fix`).
- **Output:** every step runs even after a failure. A pass/fail summary prints at the end and the exit code is nonzero if any step failed.
- **`diff-cover` locally:** compares against the existing `origin/main` ref with no fetch. A stale ref is fine because CI recomputes it. A missing ref is a failure, not a skip.
- **Non-Python tools:** `cspell`, `lychee` and `actionlint` are not in the `uv` environment and the repo has no `package.json`. They are pinned in `.tool-versions` (mise); run `mise install`. CI installs from the same file. The gate fails loudly when one is missing and never skips silently. `zizmor` and `pip-audit` are in the `dev` group.
- **Tool freshness:** Dependabot can't read `.tool-versions`, so a weekly scheduled workflow (specified in #11) runs `mise outdated` and keeps one open issue labeled `tool-versions` up to date. It never fails the run. Bumps are manual PRs. GitHub pauses scheduled workflows after 60 days of repo inactivity; re-enable them in the Actions tab.

### Gate integrity

- CI runs the full gate from the workflow on `main`, so `--no-verify` only delays a failure.
- Every ignore needs a rule code and reason (`PGH003`, `ANN401`, `reportUnnecessaryTypeIgnoreComment`).
- A CI step labels any PR that edits gate config (ruff, pyright, pytest and coverage sections of `pyproject.toml`, the cspell config but not its words list, the gate package, workflows) with `gate-config` and comments on it. It never fails the run; it makes weakening visible in review.
- The agent-side deny list for `--no-verify` and config edits is decided in #12.

## CI and merge rules

To be decided in #11.
