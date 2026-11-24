# The baseline is rank-product of 12-month commit churn and cyclomatic complexity

Accepted. Decided in #37. Like [ADR 0005](0005-scoring-pre-registration.md), it is frozen before any scored Run; a change needs a new dated amendment ADR.

The baseline ranks every eligible file by `churn_pct × complexity_pct`. Both inputs are computed from the Target repo as of the Cutoff date, using only the Python files that ADR 0004's path filters keep.

- **Scope.** Python only. Eligible files are `*.py` at the Pinned SHA (the commit at the Cutoff date), after ADR 0004's path filters (no tests, docs, generated or vendored files). Nothing is filtered by Label, and the baseline ranks all eligible files.
- **Churn.** The number of commits on the default branch that touch the file in the 12 months before the Cutoff date. Merge commits are excluded and renames are followed. This is Tornhill's "number of revisions": code-maat's `revisions` analysis and the hotspot ranking in *Your Code as a Crime Scene* both use it. Neither gives a hotspot window.
- **Churn window.** Fixed at 12 months. This is a stated convention, not a sourced optimum: [the research](../research/churn-window.md) found no empirically optimal window (Graves used 2 years, Hassan 6 months, Nagappan and Ball a release interval, Kamei all history). There is no churn-window sweep, no min-revs filter, no same-day collapsing and no decay. Each would be a tuning knob. This window is not ADR 0005's 6-month scoring window after the Cutoff date.
- **Complexity.** Cyclomatic complexity from `lizard`, summed over a file's functions and methods. Module-level code is not counted, because neither `lizard` nor `radon` reports it as a unit. A file with no functions, or one `lizard` cannot analyze, gets 0 and stays in the ranked set; the count of such files is reported per Run.
- **Tool pin.** The exact `lizard` version is pinned in `uv.lock` and recorded in the Manifest. Its counting rules are part of the baseline, so upgrading it needs an amendment ADR.
- **Score.** Percentile rank each signal (rank / N, ascending, average rank for ties) and multiply. Equal scores stay tied and are handled by ADR 0005's tie averaging. There is no path-name tie-break.

## Why

- **Rank-product, not the raw product.** Raw churn and complexity are heavy-tailed, and a raw product lets whichever signal has the wider spread dominate, so the weighting depends on the complexity tool's units. Percentile ranks weigh the two equally and need no scaling choice. The cost is a departure from the literal "churn × complexity" in the README.
- **Commit count.** It is simple and resists large mechanical edits. Evidence for it is mixed: Graves et al. found the number of changes (with age) the best predictor and found no gain from change size, while Madeyski and Jureczko found revision count added little over product metrics.
- **Cyclomatic.** It is the long-standing measure and deterministic, and ADR 0005 already needs it for its effort-proxy sensitivity check, so one tool serves both. It is the baseline's own feature, which is why ADR 0005 uses LOC, not complexity, as the effort proxy.
- **`lizard` over `radon`.**
  - `radon` is the more common Python-specific choice, but its last release was 6.0.1 on 2023-03-26. `lizard` released 1.26.1 on 2026-11-16.
  - Both parse Python 3.14 syntax (`type` aliases, generics, `match`, `except*`), but they count differently. In `radon` 6.0.1's `visitors.py`, a `match` does not count its wildcard `case _` (treated like `else`), and `except*` (`TryStar`) is not counted at all. `lizard` 1.26.1 counts both. On test functions, `radon` gave 1 and `lizard` 2 for a lone `except*` block, and `radon` 2 and `lizard` 3 for a `match` with one case and a wildcard. So the choice shifts the baseline's numbers.
  - `lizard` supports many languages, which fits the limitation below.
  - It is not a claim that either tool's counts are more correct. Neither is the textbook definition applied to every Python construct; the choice is fixed so the baseline can't change after the fact.
- **Snapshot.** Complexity is computed on the Pinned SHA tree, so nothing dated after the Cutoff date reaches the baseline. The Leakage test covers it.

## Known limits

- **Python only.** The complexity tool and the file filter are per language. Another language needs its own baseline spec. Exploring how much an LLM ranker lowers the work of adapting to a language is open, not decided here.
- The 12-month window is a judgment call. The churn evidence it rests on is mixed (see above).
- Summing over functions favors large files, and files with logic only at module level look trivially simple. ADR 0005's recall at 20% of LOC exposes the size bias.

## Alternatives rejected

- **Raw `churn × complexity`.** See above.
- **All-history churn.** It has no window parameter, but old commits dominate and young files are penalized for their age.
- **Cognitive complexity (`complexipy`).** Less research on defect prediction, and ADR 0005 names cyclomatic for the sensitivity check.
- **Maximum function complexity per file.** It ignores file size, so it is a different signal from the one the baseline is meant to capture.
- **`radon`.** See above.
