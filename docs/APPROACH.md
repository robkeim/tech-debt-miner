# Approach

How this project is run, at a high level. Details live in the linked docs; this page only says why each step exists and where to look. Steps 3 to 6 are still in progress and the plan may change as the work does.

## 1. Define the question

Decide what the project is trying to learn before writing code. The question is in the [README](../README.md): can an LLM rank files by technical-debt risk better than churn × complexity? A null result is a valid outcome.

- State how the question will be scored before running anything, so the result can't be shaped to fit.
- Terms are fixed in [GLOSSARY.md](../GLOSSARY.md) so humans and agents mean the same thing.

## 2. Build a base agents can't quietly break

This is the main difference from vibe coding: the agent works inside checks it can't loosen, so quality doesn't depend on its good behavior.

- **One definition of green:** `uv run gate` runs in hooks and CI, and CI is authoritative. See [Gate and git hooks](../CONTRIBUTING.md#gate-and-git-hooks).
- **Limits on the agent:** it never merges, can't skip hooks or push to `main`, and needs approval to edit gate config. See [Limits on the agent](../CONTRIBUTING.md#limits-on-the-agent).
- **Tests that guard the science:** no network or LLM in tests ([ADR 0003](adr/0003-tests-never-touch-network-or-llm.md)), and a Leakage test proving nothing after the Cutoff date reaches a prompt. See [Testing](../CONTRIBUTING.md#testing).
- **Reproducibility by design:** every Run can be re-scored without calling the LLM again ([ADR 0001](adr/0001-reproducibility-means-replay.md)), and all LLM calls pass through one client ([ADR 0002](adr/0002-single-llm-client-choke-point.md)).
- **Security and CI:** see [Security checks](../CONTRIBUTING.md#security-checks) and [CI and merge rules](../CONTRIBUTING.md#ci-and-merge-rules).

## 3. Define the architecture and milestones

_Not started._ The method is not settled, so the README's "How it works" is still empty. Hard-to-reverse decisions become ADRs. Work is broken into issues, each small enough to review as one PR.

## 4. Build in small reviewed changes

Every change follows the same loop, written down in [Agent workflow](../CONTRIBUTING.md#agent-workflow):

1. An issue defines the change.
2. The agent implements it test-first, with the gate green.
3. The agent reviews its own branch with the `code-review` skill and fixes or lists each finding.
4. The human reviews and merges.

## 5. Experiment and iterate

_Not started._ Runs are recorded in a Manifest, so results can be traced to the exact model, prompts, repo SHA and cutoff.

## 6. Report findings

_Not started._ Report the result of the experiment, including a null one. Also report what the process caught and what it missed, since the process is part of what's being studied.
