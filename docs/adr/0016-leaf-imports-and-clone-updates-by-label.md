# Leaf modules may import pure repo modules, and `label` fast-forwards the clone

Accepted. Decided in #72. Relaxes two rules of [ADR 0009](0009-code-layout-and-core-types.md).

## Decisions

- **Leaf imports.** A leaf module (pure functions over plain data, such as `labels.py` and `scoring.py`) may import `types` and the pure `repo` modules: `repo/history.py`, `repo/cutoff.py` and `repo/eligibility.py`. It never imports `repo/git.py` or anything else that runs a subprocess. `tests/policy/test_layering.py` enforces this for the leaf modules that conform today; add a module to its list when it becomes a leaf.
- **Clone updates.** ADR 0009 treats a Target repo clone as read-only after the first clone. The `label` stage now fast-forwards the clone before reading it: `git fetch`, then `git merge --ff-only` on the upstream branch, through an injected runner. If that fails, for example because upstream history was rewritten, the stage refuses and writes nothing. `--no-fetch` skips the update for offline use. `labels.json` records the clone's HEAD SHA, its newest commit date and whether an update ran, so the source of every Label is visible.

## Why

- **Leaf imports.** `labels.py` needs `CommitChange` and `is_eligible`, which are plain data and pure rules. Moving them into `types.py` would split the repo reading code in two, while the rule's purpose, keeping leaves testable without a repo, a subprocess or a client, holds with the pure modules.
- **Clone updates.** A clone made at `resolve` time is older than the Label window, so reading it as it is gives a silently incomplete Label. Fast-forward only keeps history from being rewritten under a Run, and recording the HEAD makes a stale or updated clone visible after the fact.

## Known limits

- Only `label` updates a clone. `snapshot` and `rank` still read it as it is, and the Pinned SHA keeps them stable under new commits.
- A fetch needs the network, so `label` is not offline unless `--no-fetch` is passed. A clone that was never updated misses fixes, and `fetched: false` in `labels.json` is the only signal.
- The policy test lists its leaf modules by hand, so a new leaf is unchecked until someone adds it.
- Layering stays a convention for modules outside that list. Open PRs can still add imports the test does not see.

## Alternatives rejected

- **Move `CommitChange`, `FileChange` and `is_eligible` into `types.py`.** It keeps the rule literal and scatters the repo reading code.
- **Never update the clone; tell people to pull.** The Label then depends on a manual step that nothing checks.
- **A plain `git pull`.** It can create merge commits or rewrite the working tree when upstream diverged, so a rewritten history would pass silently.
