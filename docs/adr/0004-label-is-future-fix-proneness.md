# The Label is future fix-proneness, built from Fix commits

Accepted. Decided in #34 from the research in #33.

A file's Label is the number of distinct Fix commits that touch it after the Cutoff date. We do not run SZZ trace-back, so a Fix commit may repair a bug introduced after the Cutoff date. That is intended: the target is "which files will need bug fixes later", which is what technical-debt risk predicts, not "which files already hid a bug". Published labeling methods are noisy (about half of the commits SZZ identifies are not real fixes, per [Herbold et al. 2022](https://arxiv.org/abs/1911.08938)), and trace-back adds a noisy step without answering the question we ask.

SZZ is the family of algorithms that finds bug-introducing commits by taking a bug-fixing commit and blaming the lines it changed. To learn more, start with the original paper, [Sliwerski et al. 2005](https://www.st.cs.uni-saarland.de/papers/msr2005/msr2005.pdf), then [Rosa et al. 2021](https://arxiv.org/abs/2102.03300) for how accurate its variants are.

**Fix commit identification.** Two label sets, reported separately. The primary set is tracker-confirmed: the commit links a closed issue typed bug. The sensitivity set is keyword-only: a word-boundary match on `fix|fixes|fixed|bug|defect|patch`. Bare numbers never count as issue links, and a `(#N)` suffix is a PR number, not an issue ID.

**Exclusions.**
- Only the default branch is read. Merge commits, reverts and bot-authored commits are never Fix commits.
- A Fix commit is dropped if its message matches `refactor|cleanup|rename|merge|bump|revert`, or if it touches more than N source files after path filtering. N is the 90th percentile of source files per fix in the Target repo, computed from fix sizes only and fixed before any scored Run. Results are also reported at N = 5, 10, 20 and uncapped; the sensitivity set is never used to choose N.
- Files are filtered by path only: tests, docs, generated and vendored files, and non-source files are excluded from both the Label and the ranked set. Diff-level filtering (pure additions, comment-only changes) is not done.

**Attribution.** Paths in a Fix commit are mapped back to Cutoff-date paths by following renames. Files deleted after the Cutoff date keep their Label. Files created after the Cutoff date are ignored, since the ranker cannot see them. The Label stage emits per-file counts; the metric decides how to use them.

**Squash merges.** Commits are read as they appear on the default branch, with no GitHub API expansion to PR commits. Each Target repo's squash share and the share of fix messages carrying only a PR number are recorded. Target repos are chosen for good issue, commit and PR hygiene, and repos whose squashed commits have title-only messages with no keyword or issue link are excluded. The cost is that results generalize only to well-maintained repos.

**Validation.** Before the first scored Run, one reviewer checks a random sample of 30 Fix commits per Target repo from a generated review sheet (message, linked issue, filtered files, diff stat). The rule fails if more than 20% are not real fixes; it is then fixed and re-sampled without looking at scores. This is a smoke test, not a measurement of label accuracy. The ground truth never depends on an LLM.

**Reporting.** Results state the limitations: no trace-back, the squash share, fixes dropped by the cap, and the validated precision with its interval.

The numeric parameters (N, exclusion globs, window length) belong to the pre-registration in #32.

## Amendments

- 2026-11-25: `validate` (#79) fixes how N and the review sheet are computed ([GLOSSARY.md](../../GLOSSARY.md): Fix size, Fix-size cap N, Review sheet).
  - **Source of N:** the Fix commits in the closed Label window, the same set `label` counts, so `validate` needs the window closed. Pre-Cutoff fixes were not used because their size distribution may differ from the commits N is applied to. N still uses sizes only.
  - **Percentile:** nearest rank, 90th. Fix commits touching no Eligible file are left out of it, since they never count toward a Label and would pull N down.
  - **Review sheet:** samples only Fix commits that count under N (1 to N Eligible files), so the reviewer does not see fixes the cap drops. "Linked issue" means `#N` references found in the message, not tracker-confirmed.
  - **Enforcement:** `validation.json` is create-once, and `label --max-files` must equal its N when the file exists. It is not required, so Runs without it behave as before.
- 2026-11-25: `label` (#74) counts the primary set ([GLOSSARY.md](../../GLOSSARY.md): Label, Tracker-confirmed Fix commit). `labels.json` holds both sets: `counts` is the primary, tracker-confirmed Label that `score` reads, and `keyword_counts` is the keyword-only sensitivity set.
  - **Linked:** the message names the issue as `#N` or a `/issues/N` URL, apart from a trailing `(#N)`. A URL is matched by its number alone, so a link to another repository's issue can match. Any linked issue that is closed and typed Bug (case-insensitive) is enough.
  - **Same exclusions:** bots, the message words and the cap N apply to both sets. The primary set does not need a keyword.
  - **Tracker read:** `label` reads every closed issue's type once, after the window check, so the state is that of the scoring date ([ADR 0006](0006-target-repos-and-cutoff-dates.md)). `labels.json` records `issues_read_at` and the `linked_closed_bugs` it saw, and a re-score needs a new Run.
  - **N:** still computed from keyword fix sizes only, as before.
- 2026-11-25: `labels.json` also holds tracker-confirmed counts per sensitivity variant (caps and the 3- and 12-month windows), see [ADR 0021](0021-sensitivity-checks-in-report.md).
- 2026-11-25: A linked issue counts as a bug when it is closed and typed Bug **or** carries the `bug` label (case-insensitive), replacing "typed Bug" in the `label` (#74) entry above (#140).
  - **Why:** [ADR 0006](0006-target-repos-and-cutoff-dates.md) measured the frozen repos' counts with "typed or labeled". `mypy` and `sentry-python` have no issue types at all, so the typed-only code gave a primary Label of 0 and every Run would be excluded.
  - **Not changed:** the keyword set, the cap N, and the exclusions. The code change and the 2026-12-31 recount are tracked in #140.
