# Scoring is pre-registered: nDCG@20 with a recall@20%-LOC check

Accepted. This ADR is the pre-registration for the experiment. It is merged to `main` before any scored Run, each scored Run's Manifest records this ADR's commit SHA, and a policy test fails a scored Run whose Manifest lacks it. Before the merge only Dry-runs are allowed. A change afterward needs a new dated amendment ADR, and results are reported under both versions. The label rule (what counts as a bug fix) is decided in #34 and the Target repos and Cutoff dates in #36; this ADR fixes everything downstream of them.

## What is scored

Both rankers (churn × complexity and the LLM) work from the raw repo and issues as of the Cutoff date and order files however they choose. The LLM may output up to 50 files; the baseline may rank everything. Neither is pre-filtered, so what one ignores never changes what the other is scored on. A slot spent on a file with no later fixes scores 0 for the ranker that used it. Ground truth is the post-Cutoff bug-fix labels from #34, shared by both.

| Item | Decision |
| --- | --- |
| Primary metric | nDCG@20 with damped gain `1 + log2(count)` (0 for files with no fix) and discount `1 / log2(position + 1)` |
| Co-primary | Recall at 20% of total LOC (the PofB20 convention), effort = physical LOC at the Pinned SHA |
| Budget rule | Walk the ranking, skip a file that would overflow the budget and continue; unused budget finds nothing |
| Reported, not decisive | precision@k, nDCG at k = 5, 10 and 50, Spearman for full orderings only |
| Ties | Average over all tied orderings; never a path-name tie-break |
| Window | Fixes in `(Cutoff, Cutoff + 6 months]`; a Run is not scored until its window has closed |
| Minimum data | At least 10 files with a qualifying fix per repo and window; exclusions are reported, never dropped silently |
| Aggregation | Per-repo scores; the verdict uses the mean paired difference (LLM minus baseline) with equal weight per repo; every repo is shown |
| Uncertainty | 3 LLM repeats per repo and Cutoff at temperature 0, averaged per repo; bootstrap 95% CI over repos |
| Evidence floor | At least 5 scoreable repos for a verdict; the headline claim uses only windows starting after the model's training cutoff, earlier windows are exploratory |

## Outcomes

Computed on the mean nDCG@20 difference with its 95% CI. The ±0.05 margin is our starting point, a judgment call with no source behind it, and may be adjusted before the first scored Run.

| Outcome | Rule |
| --- | --- |
| Win | CI entirely above 0 and the recall@20%-LOC difference has the same sign |
| Loss | CI entirely below 0 and the recall difference has the same sign |
| Mixed | The nDCG outcome would be a win or loss but the recall difference has the opposite sign |
| Null | CI entirely within ±0.05; the co-primary cannot change this |
| Inconclusive | Anything else |

## Required sensitivity checks

Report-only; none can change the verdict. If one flips the direction, the report says so first.

- Binary and raw-count gains
- 3-month and 12-month windows
- Cyclomatic complexity as the effort proxy
- k = 5, 10 and 50
- Keyword-only versus tracker-confirmed labels, if #34 adopts both

## Why

- **nDCG@k as primary.** nDCG is the standard for ranked lists in information retrieval (Järvelin and Kekäläinen, 2002). It rewards putting the worst files first, reads only the top k so a shortlist ranker is not penalized for files it never ranked, and uses bug counts. Precision@k ignores order and severity; Spearman needs a full ordering, and a shortlist ranker's unranked files become one large tie.
- **Discount form.** The `log2(position + 1)` form is the common modern variant, as in scikit-learn's `ndcg_score`. Järvelin and Kekäläinen's original leaves the first ranks undiscounted, so it is not the same formula.
- **Damped gain.** Bug fixes are lumpy. In a worked six-file case, raw counts let one 50-fix file nearly decide nDCG while precision@3 and Spearman disagreed with it (see the research note). Damping keeps a 5-fix file above a 1-fix file without letting one file dominate.
- **Recall@20%-LOC as co-primary.** Effort-aware metrics are the convention in defect prediction (PofB20 and Popt, Mende and Koschke, 2010), and the 20% line comes from Ostrand, Weyuker and Bell (2005), who found the top 20% of files by predicted faults held 71% to 85% of faults across releases. It exposes size bias that nDCG ignores, so a ranker cannot win only by liking small files.
- **LOC as effort.** LOC is the standard proxy. A 2025 critique argues such metrics are size-aware rather than effort-aware, since they assume effort scales with size, but no accepted alternative exists. Complexity is not the primary proxy because it is the baseline's own feature, so using it would partly score the baseline against its own input. It stays as a sensitivity check.
- **Tie averaging.** Averaging over all tied orderings is the reference approach (McSherry and Najork, 2008), and scikit-learn averages ties by default. A fixed tie-break would make the score depend on file names, and without a stated rule results depend on sort order, which breaks Replay.
- **Fixed k = 20, no output restriction.** A ranking sorted by risk is prefix-consistent, so one ranking is read at several depths with no extra LLM calls. The 50-file cap exists only for cost and context and is at least the largest reported k. The primary k is named in advance so a depth cannot be chosen after seeing results.
- **Six-month window.** Fix labels appear late, and release-level labeling with a six-month window was found unreliable (Herbold et al., see the labeling research), so the window is reported at 3, 6 and 12 months. Memorization research (#35) says only windows starting after the model's training cutoff are free of leaked answers, hence the headline restriction.
- **Repeats at temperature 0.** Claude's API has no seed ([ADR 0001](0001-reproducibility-means-replay.md)), so output cannot be bit-reproducible. Temperature 0 reduces variation and 3 repeats measure what remains. Replay of the logged responses makes scoring itself deterministic.

## Alternatives rejected

- **Spearman, precision@k or Popt as primary.** See above; Popt is harder to explain and rests on the same size assumption as recall@20%-LOC.
- **A shared candidate set or shortlist for both rankers.** It would constrain one ranker to make the other comparable. Scoring both at the same k over the same ground truth achieves the comparison without it.
- **Pooling files across repos.** One large repo would dominate the score.
- **A p-value from a sign or rank test.** With the few repos we expect, these cannot reach small p-values (five repos cannot go below 0.0625 two-sided on a sign test).

## Known limits

- The ±0.05 null margin, the skip-and-continue budget rule and the 3-repeat count are conventions chosen here, not taken from a source.
- Label noise is large: roughly half of SZZ-identified fixes are reportedly not real bug fixes, and about 64% of file changes inside fixes are not part of the fix. Results are reported with that caveat.
- A verdict may wait for post-cutoff windows to close, since only about five months of post-cutoff data exist today.
- Several cited papers were read only as abstracts or secondary summaries (Järvelin and Kekäläinen, Mende and Koschke). Their claims are used for conventions, not for numbers.

## Sources

- Järvelin, K. and Kekäläinen, J. (2002). Cumulated gain-based evaluation of IR techniques. ACM TOIS 20(4), 422-446. https://doi.org/10.1145/582415.582418
- scikit-learn, `sklearn.metrics.ndcg_score`. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html
- McSherry, F. and Najork, M. (2008). Computing information retrieval performance measures efficiently in the presence of tied scores. ECIR 2008. https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ecir2008.pdf
- Mende, T. and Koschke, R. (2010). Effort-aware defect prediction models. CSMR 2010. https://bibtex.github.io/CSMR-2010-MendeK.html
- Ostrand, T., Weyuker, E. and Bell, R. (2005). Predicting the location and number of faults in large software systems. IEEE TSE. https://www.cs.virginia.edu/woda/papers/ostrand.pdf
- Critical considerations on effort-aware software defect prediction metrics (2025). https://arxiv.org/html/2504.19181v1
- Research notes on branches `research/ranking-metrics`, `research/bug-fix-labeling` and `research/llm-memorization` (issues #31, #33, #35).
