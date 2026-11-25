# Scoring is pre-registered: nDCG@20 with a recall@20%-LOC check

Accepted. This ADR is the pre-registration for the experiment.

## How it is frozen

- It is merged to `main` before any scored Run. Until then only Dry-runs are allowed, and the numbers below (including the ±0.05 margin) can still change.
- Each scored Run's Manifest records this ADR's commit SHA, and a policy test should fail a scored Run whose Manifest lacks it. That test does not exist yet; it is tracked in #57.
- After the merge, a change needs a new dated amendment ADR, and results are reported under both versions.
- The Label (what counts as a Fix commit) is decided in [ADR 0004](0004-label-is-future-fix-proneness.md) and the Target repos and Cutoff dates in #36. This ADR fixes everything downstream of them, plus the numeric parameters ADR 0004 leaves to it. The model and its training cutoff are chosen there too and recorded in the Manifest.

## What is scored

Both rankers (churn × complexity and the LLM) work from the raw repo and issues as of the Cutoff date and order files however they choose. The LLM may output up to 50 files; the baseline may rank everything. Neither is pre-filtered, so what one ignores never changes what the other is scored on. A slot spent on a file with a Label of 0 scores 0 for the ranker that used it. A file named twice counts once, at its first position, and a file that does not exist at the Pinned SHA scores 0 and still uses its slot. The ground truth is each file's Label (ADR 0004), shared by both.

| Item | Decision |
| --- | --- |
| Primary metric | nDCG@20 with damped gain `1 + log2(Label)` (0 for files with a Label of 0) and discount `1 / log2(position + 1)` |
| Co-primary | Recall at 20% of total LOC (the PofB20 convention), effort = physical LOC at the Pinned SHA |
| Budget rule | Walk the ranking, skip a file that would overflow the budget and continue; unused budget finds nothing |
| Reported, not decisive | precision@k, nDCG at k = 5, 10 and 50, Spearman for full orderings only |
| Ties | Average over all tied orderings; never a path-name tie-break |
| Window | Fixes in `(Cutoff date, Cutoff date + 6 months]`; a Run is not scored until its window has closed |
| Minimum data | At least 10 files with a Label of 1 or more per repo and window; exclusions are reported, never dropped silently |
| Aggregation | The unit is the repo: repeats are averaged, then Cutoff dates within a repo are averaged. The verdict uses the mean paired difference (LLM minus baseline) with equal weight per repo; every repo is shown |
| Uncertainty | 3 LLM repeats per repo and Cutoff at temperature 0, averaged per repo; bootstrap 95% CI over repos |
| Evidence floor | At least 5 scoreable repos for a verdict; the headline claim uses only windows starting after the model's training cutoff, earlier windows are exploratory |

## Outcomes

Computed on the mean nDCG@20 difference with its 95% CI, using only windows that start after the model's training cutoff. The ±0.05 margin is our starting point, a judgment call with no source behind it. Rules are checked in this order, so each result has exactly one outcome:

| Outcome | Rule |
| --- | --- |
| Null | CI entirely within ±0.05; the co-primary cannot change this |
| Mixed | CI entirely above or below 0, and the recall@20%-LOC difference has the strictly opposite sign |
| Win | CI entirely above 0, and the recall difference is not negative |
| Loss | CI entirely below 0, and the recall difference is not positive |
| Inconclusive | Anything else |

A CI such as [0.01, 0.04] is therefore Null: positive, but too small to matter. A recall difference of exactly 0 never makes a result Mixed.

## Required sensitivity checks

Report-only; none can change the verdict. If one flips the direction, the report says so first.

- Binary and raw-Label gains
- 3-month and 12-month windows
- Cyclomatic complexity as the effort proxy
- k = 5, 10 and 50
- Keyword-only versus tracker-confirmed Fix commits (the primary Label is tracker-confirmed, ADR 0004)
- Fix-size cap N at 5, 10, 20 and uncapped (the primary N is the 90th percentile, fixed before any scored Run, ADR 0004)

## Why

- **nDCG@k as primary.** nDCG is the standard for ranked lists in information retrieval (Järvelin and Kekäläinen, 2002). It rewards putting the worst files first, reads only the top k so a shortlist ranker is not penalized for files it never ranked, and uses bug counts. Precision@k ignores order and severity; Spearman needs a full ordering, and a shortlist ranker's unranked files become one large tie.
- **Discount form.** The `log2(position + 1)` form is the common modern variant, as in scikit-learn's `ndcg_score`. Secondary descriptions say the original paper sets the log base differently, so cite scikit-learn for this exact formula, not the paper.
- **Damped gain.** Bug fixes are lumpy. In a worked six-file case, raw counts let one 50-fix file nearly decide nDCG while precision@3 and Spearman disagreed with it (ranking metrics research, #31). Damping keeps a 5-fix file above a 1-fix file without letting one file dominate.
- **Recall@20%-LOC as co-primary.** Effort-aware metrics are the convention in defect prediction (PofB20 and Popt, Mende and Koschke, 2010), and the 20% line comes from Ostrand, Weyuker and Bell (2005), who found the top 20% of files by predicted faults held 71% to 85% of faults across releases. It exposes size bias that nDCG ignores, so a ranker cannot win only by liking small files.
- **LOC as effort.** LOC is the standard proxy. A 2025 critique argues such metrics are size-aware rather than effort-aware, since they assume effort scales with size, but no accepted alternative exists. Complexity is not the primary proxy because it is the baseline's own feature, so using it would partly score the baseline against its own input. It stays as a sensitivity check.
- **Tie averaging.** Averaging over all tied orderings is the reference approach (McSherry and Najork, 2008), and scikit-learn averages ties by default. A fixed tie-break would make the score depend on file names, and without a stated rule results depend on sort order, which breaks Replay.
- **Fixed k = 20, no output restriction.** A ranking sorted by risk is prefix-consistent, so one ranking is read at several depths with no extra LLM calls. The 50-file cap exists only for cost and context and is at least the largest reported k. The primary k is named in advance so a depth cannot be chosen after seeing results.
- **Six-month window.** Six months is a chosen convention, not a sourced value: fix labels appear late, so a shorter primary window would miss fixes. Herbold et al. found six-month release assignment unreliable, but that concerns assigning bugs to releases, not a post-Cutoff scoring window, so it doesn't settle the length. The window is therefore also reported at 3 and 12 months (labeling research, #33). Memorization research (#35) says only windows starting after the model's training cutoff are free of leaked answers, hence the headline restriction.
- **Repeats at temperature 0.** Claude's API has no seed ([ADR 0001](0001-reproducibility-means-replay.md)), so output cannot be bit-reproducible. Temperature 0 reduces variation and 3 repeats measure what remains. Replay of the logged responses makes scoring itself deterministic.

## Alternatives rejected

- **Spearman, precision@k or Popt as primary.** See above; Popt is harder to explain and rests on the same size assumption as recall@20%-LOC.
- **A shared candidate set or shortlist for both rankers.** It would constrain one ranker to make the other comparable. Scoring both at the same k over the same Labels achieves the comparison without it.
- **Pooling files across repos.** One large repo would dominate the score.
- **A p-value from a sign or rank test.** With the few repos we expect, these cannot reach small p-values (five repos cannot go below 0.0625 two-sided on a sign test).

## Known limits

- The ±0.05 null margin, the skip-and-continue budget rule and the 3-repeat count are conventions chosen here, not taken from a source.
- The LLM names at most 50 files, so on a large repo it may not fill the 20% LOC budget while the baseline, which ranks everything, does. Recall@20%-LOC may therefore favor the baseline structurally. Read it with that in mind.
- Recall uses only the sign of its difference, with no interval, so noise can turn a Win into Mixed.
- A bootstrap CI over about five repos is wide and unreliable. Few repos mean mostly Inconclusive results, and that is reported as such.
- Ties and the skip-and-continue walk interact. Recall@20%-LOC also averages over tied orderings, and the scoring implementation must do so deterministically. The details belong to the scoring issue.
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
- Research findings are in issues #31 (ranking metrics), #33 (bug-fix labeling) and #35 (memorization).

## Amendments

- 2026-11-24: The "3 repeats at temperature 0" wording is amended by [ADR 0012](0012-llm-repeats-use-default-sampling.md).
- 2026-11-24: The duplicate-file rule is clarified by [ADR 0013](0013-duplicate-files-keep-their-slot.md).
- 2026-11-25: The recall budget and tie averaging are specified by [ADR 0018](0018-recall-budget-and-effort-map.md).
