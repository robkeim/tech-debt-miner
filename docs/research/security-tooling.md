# Security tooling coverage for a Python repo on public CI

Research note for issue #3, written as part of a learning experiment. Question: what does each tool cover for a Python-only repo, where do they overlap, and what do they cost in money, setup and CI time?

Method: official docs and READMEs only (fetched 2026-11-18). Where a source is silent, this note says so instead of guessing. No vendor publishes CI runtime figures, so runtime is a qualitative expectation, labeled as such, to be measured once the gate exists.

## Summary table

| Tool | Covers | Cost on a public repo | Setup effort | Runtime expectation (unmeasured) |
|---|---|---|---|---|
| GitHub secret scanning + push protection | Known-provider secrets in full history, issues, PRs; blocks pushes containing them | Free | None to low (on by default for public repos) | None in CI; runs server-side |
| CodeQL | Semantic SAST for Python (taint and dataflow) | Free (public) | Low (default setup) | Slowest here: builds a database, then queries |
| gitleaks | Regex/entropy secrets in git history or files | Free (MIT) | Low | Seconds for a small repo |
| bandit | Python AST checks for common insecure patterns | Free (Apache-2.0) | Low | Seconds |
| Semgrep (Community Edition) | Pattern-based SAST, single-function/file scope | Free for `semgrep scan`; `semgrep ci` needs login | Low to medium | Seconds to a minute |
| pip-audit | Known-vulnerable installed/locked dependencies | Free (Apache-2.0) | Low | Seconds (network call to advisory DB) |
| Dependabot alerts | Known-vulnerable dependencies via the GitHub Advisory Database | Free | Low (toggle) | None in CI |
| OpenSSF Scorecard | Repo/process hygiene score (branch protection, pinning, etc.) | Free (Apache-2.0) | Low to medium | Short scheduled job |
| actionlint | Workflow syntax, expressions, shell in `run:` | Free (MIT) | Low | Seconds |
| zizmor | Security audit of workflows (injection, permissions, pinning) | Free | Low | Seconds (offline); online audits need a token |

## Per-tool findings

### GitHub secret scanning and push protection
- Secret scanning runs automatically and free on public repos; it covers full git history on all branches plus issue/PR text, Discussions and wikis. [About secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)
- Push protection is "Available for public repositories by default". [GitHub security features](https://docs.github.com/en/code-security/getting-started/github-security-features)
- It blocks partner patterns, generic patterns, custom patterns and (public preview) AI-detected passwords. Anyone with write access can bypass with a reason; bypasses are audit-logged. User-level push protection is on by default for pushes to public repos. [About push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- Partner-pattern hits are reported to the provider rather than shown as repo alerts. [About secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)

### CodeQL
- Python is a supported language; default setup picks languages, query suite and triggers automatically and runs as GitHub Actions workflows. CodeQL builds a database from the code then runs queries. The page gives no timing figures. [About CodeQL code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql)
- Code scanning is "Available for public repositories by default"; private repos need a Code Security license. [Security features](https://docs.github.com/en/code-security/getting-started/github-security-features), [About code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning)

### gitleaks
- Detects passwords, API keys and tokens in git repos, files and stdin; MIT licensed. Scans history via `git log -p`. Supports a pre-commit hook and a separate GitHub Action project (licensing of the action is not stated on the README). [gitleaks README](https://github.com/gitleaks/gitleaks)
- The README says the project is feature complete: security patches only going forward, and the author is shifting to Betterleaks. Worth weighing for a long-lived dependency.

### bandit
- Finds common security issues in Python code by building an AST per file and running plugins; Apache-2.0. Python source only. [Bandit docs](https://bandit.readthedocs.io/en/latest/)
- Ships `.pre-commit-hooks.yaml` and a container image. [Bandit repo](https://github.com/PyCQA/bandit)

### Semgrep
- Community Edition engine is open source (LGPL-2.1 repo) and Python is supported. It "can only analyze code within the boundaries of a single function or file" and the docs warn it misses many true positives; Pro rules and cross-file analysis need login. [Semgrep repo](https://github.com/semgrep/semgrep)
- `semgrep scan` works without an account; `semgrep ci` fails if you are not signed in (use `--oss-only` for community analysis only). Install via `pipx` or `uv tool`. [Semgrep CLI docs](https://docs.semgrep.dev/getting-started/cli)
- The docs pages read did not state the license of registry rules; check before relying on them.

### pip-audit
- Scans environments, requirements files, `pyproject.toml` and `pylock.*.toml` for known vulnerabilities, using the Python Packaging Advisory Database via PyPI JSON API by default, or OSV. Exit code 1 on findings. Official action `pypa/gh-action-pip-audit` and a pre-commit hook exist. Not a static analyzer and not protection against malicious packages. Apache-2.0. [pip-audit README](https://github.com/pypa/pip-audit)

### Dependabot alerts
- Alerts fire when a reviewed advisory lands in the GitHub Advisory Database and matches a dependency; listed as available on all plans. [About Dependabot alerts](https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts), [Security features](https://docs.github.com/en/code-security/getting-started/github-security-features)
- Needs the dependency graph. For pip, `requirements.txt` or `Pipfile.lock` give the most complete transitive data; Poetry uses `poetry.lock`. The ecosystem page does not mention uv, so uv lockfile support is unconfirmed. [Dependency graph ecosystems](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/dependency-graph-supported-package-ecosystems)
- Alerts are distinct from Dependabot version updates (already settled in the map).

### OpenSSF Scorecard
- Scores heuristic checks 0 to 10 plus a weighted aggregate: Dangerous-Workflow, Branch-Protection, Code-Review, Dependency-Update-Tool, Pinned-Dependencies, Token-Permissions, Vulnerabilities, SAST, Security-Policy, and more. Apache-2.0. The GitHub Action posts results to the Security tab; `publish_results: true` enables badges. Most checks need a token; some Branch-Protection data needs a maintainer PAT. Checks are heuristics with false positives and negatives. [Scorecard README](https://github.com/ossf/scorecard)

### actionlint
- Static checker for workflow files: syntax, `${{ }}` type checking, action inputs/outputs, `needs:`, runner labels, cron, script-injection and hardcoded-credential hints; runs shellcheck and pyflakes on `run:` scripts if installed. MIT. Binary, Homebrew, Docker, pre-commit. [actionlint README](https://github.com/rhysd/actionlint)

### zizmor
- Static analysis of GitHub Actions, Dependabot config and pre-commit setups. Audits include template-injection, excessive-permissions, artipacked, unpinned and impostor commits, cache-poisoning, dependabot-cooldown. [zizmor docs](https://docs.zizmor.sh/), [Audits](https://docs.zizmor.sh/audits/)
- Offline by default (no token); setting `GH_TOKEN`/`GITHUB_TOKEN` enables online mode, needed for audits such as `known-vulnerable-actions`, `impostor-commit`, `ref-confusion`, `stale-action-refs`. Exit codes 11-14 encode finding severity; SARIF output suppresses them. Personas: regular, pedantic, auditor. [zizmor usage](https://docs.zizmor.sh/usage/)

## Overlap matrix

| Concern | Primary | Overlapping / complementary |
|---|---|---|
| Committed secrets | Secret scanning + push protection (server side, blocks at push) | gitleaks adds local pre-commit and custom rules; both scan history. Overlap is high; gitleaks is the only one that runs before a commit exists. |
| Python code vulnerabilities | CodeQL (semantic, dataflow) | bandit (AST patterns) and Semgrep CE (single-file patterns) overlap with each other and partly with CodeQL; CodeQL is deepest, bandit is fastest. |
| Vulnerable dependencies | Dependabot alerts (continuous, advisory DB) | pip-audit (CI gate, PyPA advisory DB or OSV) duplicates alerts but fails a build and works on a local environment. Scorecard's Vulnerabilities check also reflects this. |
| Workflow correctness | actionlint | zizmor overlaps on injection and credentials, but actionlint covers syntax/typing and zizmor covers security audits. Complementary. |
| Workflow security posture | zizmor | Scorecard (Dangerous-Workflow, Token-Permissions, Pinned-Dependencies) overlaps; Scorecard also scores repo settings neither linter sees. |
| Repo process (branch protection, review, policy) | Scorecard | None of the others. |

## Observations for the decision (not decisions)
- Everything here is free on a public repo; cost is CI minutes and maintenance, not money.
- Server-side features (secret scanning, push protection, Dependabot alerts, CodeQL default setup) need no workflow code, so they add no gate runtime.
- Likely redundancy to question: running all of bandit, Semgrep CE and CodeQL on a small Python repo. Semgrep `ci` needs an account; `scan` does not.
- gitleaks is in maintenance mode per its README.
- Runtime numbers should be measured on this repo and recorded once the gate exists.
