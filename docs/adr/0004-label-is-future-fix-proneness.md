# The Label is future fix-proneness, built from Fix commits

Accepted. Decided in #34 from the research in #33.

A file's Label is the number of distinct Fix commits that touch it after the Cutoff date. We do not run SZZ trace-back, so a Fix commit may repair a bug introduced after the Cutoff date. That is intended: the target is "which files will need bug fixes later", which is what technical-debt risk predicts, not "which files already hid a bug". Published labeling methods are noisy (about half of SZZ-identified fixes are not real fixes), and trace-back adds a noisy step without answering the question we ask.

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
