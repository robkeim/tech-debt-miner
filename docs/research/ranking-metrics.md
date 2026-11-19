# Ranking metrics for file-level defect ranking

Research for issue #31 (part of the architecture map, #30). Written for a reader who is new to ranking metrics. Date of research: 2026-11-19.

## The question

A **Run** rewinds a **Target repo** to a **Cutoff date**, asks a ranker to order files by technical-debt risk, then scores that order against the bug fixes that landed after the cutoff. Which score should we use? This note explains Spearman correlation, precision@k, nDCG and the effort-aware family in plain English, shows each on one small example, and says what each rewards and hides.

## Short answer

- No single metric is right. Each answers a different question.
- **nDCG@k** and an **effort-aware recall (share of bugs found in the top 20% of code)** fit this project best. Both ask "if a reviewer works down the list, how much of the real trouble do they hit early?"
- **Precision@k** is easy to read and worth reporting next to them.
- **Spearman** judges the whole list. It is a weak fit when only the top of the list matters, and it can mislead with many zero-bug files and tied scores.
- The owner must settle several choices (listed at the end) before any code can fix a metric.

## The running example

Six files, in the order the ranker put them (riskiest first). After the cutoff, the repo had 6 bug fixes touching these files.

| Rank | File | Size (LOC) | Bug fixes after cutoff |
| ---- | ---- | ---------- | ---------------------- |
| 1    | A    | 100        | 0                      |
| 2    | B    | 100        | 3                      |
| 3    | C    | 400        | 0                      |
| 4    | D    | 100        | 1                      |
| 5    | E    | 100        | 0                      |
| 6    | F    | 200        | 2                      |

The "truth" is the right-hand column, the number of later bug fixes per file. A perfect ranker would order files by it: B (3), F (2), D (1), then A, C, E (0). This ranker is mediocre: it put a zero-bug file on top and the worst offender second.

All numbers below were computed with a short script that follows the definitions in the cited sources (nothing is rounded before the last step).

## 1. Spearman rank correlation

**What it does.** Replace each file's score with its position (1st, 2nd, ...), do the same for the bug counts, then ask how closely the two position lists move together. It is a "nonparametric measure of the monotonicity of the relationship between two datasets" and runs from -1 (exactly reversed) to +1 (identical order), with 0 meaning no relationship ([SciPy `spearmanr`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html)).

**Worked example.** The ranker's order and the bug-count order are compared across all six files. Tied bug counts (A, C and E all have 0) share the average of the positions they occupy, which is the standard treatment. Result: **-0.15**, meaning the order is essentially unrelated to where bugs landed, slightly backwards.

**Rewards.** Getting the entire list roughly in order, including the bottom.

**Hides.**

- Every position counts equally. Swapping files ranked 1 and 2 costs the same as swapping files ranked 99 and 100, but a reviewer only reads the top.
- It rewards correctly ordering the many zero-bug files at the bottom, which carries no value for finding debt.
- It says nothing about effort or file size.
- If either list is constant (for example, no file had a bug fix), the coefficient is undefined; SciPy returns `nan` and warns ([SciPy `spearmanr`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html)).
- Its p-value is "only accurate for very large samples (>500 observations)" (same page), so do not lean on it for small repos.

## 2. Precision@k

**What it does.** Take the top k files the ranker proposes and compute the fraction that were truly buggy (had at least one later fix). Precision at a fixed cut-off is a standard measure for ranked results where users look only at the top few ([Manning, Raghavan and Schütze, *Introduction to Information Retrieval*, ch. 8](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html); the page was unreachable from this session, so the description here rests on the book's well-known definition and is not quoted. Re-check before citing).

**Worked example.** "Buggy" means at least 1 later fix (B, D, F).

- k = 1: A is not buggy. Precision@1 = 0/1 = **0.00**
- k = 2: A, B. One buggy. Precision@2 = **0.50**
- k = 3: A, B, C. One buggy. Precision@3 = **0.33**

**Rewards.** Filling the shortlist with files that really had bugs. It is the easiest metric to explain to a reviewer.

**Hides.**

- Order inside the top k does not matter. B first or B third scores the same.
- A file with 1 fix counts the same as a file with 50 fixes.
- The score depends on k, and the best possible value is capped when fewer than k files are buggy (with 3 buggy files, precision@5 can never exceed 0.60).
- It ignores everything past k.

## 3. nDCG (normalized discounted cumulative gain)

**What it does.** Each file earns a **gain** equal to how much it deserves to be found (here, its later bug count). Gains are added up down the list, but a gain at position 1 counts fully and later positions count for less (a logarithmic discount). The total (DCG) is divided by the best total possible with a perfect order (the "ideal DCG"), giving a score from 0 to 1 ([Järvelin and Kekäläinen, 2002, ACM TOIS 20(4)](https://doi.org/10.1145/582415.582418); scikit-learn describes the same recipe: "Sum the true scores ranked in the order induced by the predicted scores, after applying a logarithmic discount. Then divide by the best possible score", [`ndcg_score`](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html)).

The formula used here is the common one, a gain divided by log2(position + 1). Note the scikit-learn page does not spell the formula out and the paper PDF could not be read in this session, so the exact discount and gain form should be confirmed against the paper before they are written into an ADR. Variants exist (for example, using `2^gain - 1` as the gain), and the choice matters when counts are skewed.

**Worked example.**

- Ranker's order, gains: 0, 3, 0, 1, 0, 2.
  DCG = 0 + 3/log2(3) + 0 + 1/log2(5) + 0 + 2/log2(7) = 1.89 + 0.43 + 0.71 = **3.04**
- Perfect order, gains: 3, 2, 1, 0, 0, 0.
  Ideal DCG = 3 + 2/log2(3) + 1/log2(4) = 3 + 1.26 + 0.50 = **4.76**
- nDCG = 3.04 / 4.76 = **0.64**

**nDCG@k** only looks at the first k positions, and normalizes against the ideal first k positions. For k = 3: DCG@3 = 1.89, ideal DCG@3 = 4.76, so nDCG@3 = **0.40**. scikit-learn confirms that with `k` set, "the normalization takes k into account so a perfect answer would still get 1.0."

**Rewards.** Putting the files with the most bugs at the very top. Position matters and bug count matters.

**Hides.**

- The size of a file is ignored, so a 10,000-line file and a 50-line file with the same bugs score the same.
- One monster file with 50 fixes can dominate the score of a whole repo (see "Skewed bug counts" below). Using binary or damped gains (such as log of the count) reduces this, at the price of treating a 1-fix file and a 5-fix file more alike.
- Averaging nDCG across repos is only meaningful when the label scale is comparable; the normalization removes absolute size but not skew.
- If no file has a later bug, the ideal DCG is 0 and nDCG is undefined. Such a Run must be excluded or scored as a special case (the same hazard as Spearman's constant input).

## 4. Effort-aware metrics (bugs found within a size budget)

**What they do.** Reading a 4,000-line file costs more than reading a 40-line file, so these metrics ask how many bugs a reviewer finds given a fixed amount of reading. The common version: walk down the ranked list until you have used a budget, usually 20% of the repo's total lines, and report the share of all later bug fixes inside the files you covered. Names in the literature include **PofB20** (percentage of bugs found at 20% effort), recall at 20% effort, and **Popt**, which measures the area between the model's cumulative curve and the best possible curve so no single budget is chosen ([Mende and Koschke, "Effort-Aware Defect Prediction Models", CSMR 2010](https://bibtex.github.io/CSMR-2010-MendeK.html); definitions summarized in [a 2025 critique, arXiv 2504.19181](https://arxiv.org/html/2504.19181v1), which says the curve plots effort on the x-axis against the fraction detected on the y-axis, PofB_X reads one point on it, and Popt uses the area).

The classic motivation for the 20% line is the finding that a small share of files hold most faults: in [Ostrand, Weyuker and Bell, "Predicting the location and number of faults in large software systems", IEEE TSE 2005](https://www.cs.virginia.edu/woda/papers/ostrand.pdf), the 20% of files with the highest predicted fault counts held between 71% and 92% of actual faults across releases. (That range comes from a search-result summary of the abstract, not from reading the paper; confirm before quoting.)

**Worked example.** Total size is 1,000 LOC, so the 20% budget is 200 LOC. Walk the list in ranked order: A (100 LOC, 0 bugs) then B (100 LOC, 3 bugs) fills the budget exactly. Bugs found = 3 of 6, so PofB20 = **50%**. The best possible order under the same budget picks B and D (100 + 100 LOC, 3 + 1 bugs) for **67%**. Note the best choice favors bug density, bugs per line, which is why the literature also scores rankers by density.

The rule when the next file does not fit the budget (skip it, stop, or count part of it) is a convention and must be fixed up front. Here C (400 LOC) would bust the budget if A or B had been skipped.

**Rewards.** Finding bugs cheaply, and not wasting reading time on huge files that turn out clean. It matches how a team would use a debt ranking.

**Hides.**

- Effort is assumed proportional to size. The 2025 critique argues "the vast majority of the proposed EAMs assumes that analysis effort needed for a module is proportional to the size of the module," so the metrics can be "size-aware, rather than effort-aware" ([arXiv 2504.19181](https://arxiv.org/html/2504.19181v1)). Changing the effort proxy (LOC versus complexity) changes the scores.
- A ranker that simply prefers small files can look good. This matters here, because the churn x complexity baseline and an LLM may differ in size bias.
- The 20% line is a convention, not a law. Popt avoids choosing a point but is harder to explain.
- Needs file sizes at the Pinned SHA, which the pipeline would have to carry as a feature.

## How the choice interacts with the project's three concerns

### A ranker that only orders a shortlist

An LLM may only be asked to order, say, its 20 riskiest candidates, while churn x complexity can order every file. Files the LLM never mentions have no rank.

- **Spearman** needs a full ordering. Giving every unranked file the same score creates a huge tie group, and the coefficient then mostly measures the tie, not skill. Worked example: with only A, B, C scored (3, 2, 1) and D, E, F tied at 0, Spearman is **-0.10**.
- **Top-k metrics** (precision@k, nDCG@k) only read the first k positions, so they are unaffected by what happens below the shortlist as long as k is at most the shortlist length. In the same example nDCG@3 stays **0.40**, identical to the full-order value.
- **Effort-aware recall** needs a decision for the unranked tail. If the shortlist alone fills less than the 20% budget, what fills the rest (random, size order, nothing) changes the answer.
- To compare rankers fairly, score both on the same candidate set and the same k.

### Ties

Heuristics such as churn produce many equal scores (a file touched 0 times).

- scikit-learn averages over tied scores by default: its documented example gets 0.75 with ties averaged and 0.5 with `ignore_ties=True`, and it warns the latter gives "wrong results" when ties exist ([`ndcg_score`](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html)).
- [McSherry and Najork (ECIR 2008)](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ecir2008.pdf) show how to adjust precision, recall, F1, average precision, reciprocal rank and nDCG for tied scores so the result equals the average over all possible orderings of the tied items. A secondary summary of the abstract supplied this claim; the paper itself was not read in full.
- Spearman uses average ranks for ties; its value is undefined if all scores tie.
- Effort-aware walks need a tie-break rule. The 2025 critique's own experiment broke ties "by decreasing LOC," which shows a tie-break can quietly favor one kind of file.
- Without a stated tie rule, results depend on sort order, which breaks Replay.

### Skewed bug counts

Bug fixes are lumpy: most files get 0, a few get many.

Worked example, same six files but with bugs of 0, 50, 1, 1, 0, 0 for A to F. Ranker X orders A to F (hot file B second). Ranker Y orders B, F, E, D, C, A (hot file first, small-bug files poorly placed).

| Metric                    | X    | Y    |
| ------------------------- | ---- | ---- |
| Spearman                  | 0.37 | 0.31 |
| Precision@3 (any bug)     | 0.67 | 0.33 |
| nDCG (raw counts)         | 0.64 | 0.99 |
| nDCG (buggy = 1, else 0)  | 0.73 | 0.85 |

The metrics disagree about the winner. Precision@3 prefers X (two of its top three had bugs). Raw-count nDCG prefers Y overwhelmingly because it found the 50-fix file first, and that single file is almost the whole score. Spearman barely separates them. This is not a bug in any metric; they answer different questions, and the label choice (raw count, binary, damped) matters as much as the metric choice.

Also consider: one noisy mega-commit that "fixes" many files at once can create fake skew. Which commits count as bug fixes is the label ticket's problem, but it feeds straight into this choice.

## Comparison

| Metric             | Plain-English question                                     | Position-aware | Uses bug counts | Uses file size | Ties and unranked tail                                    | Main risk                                         |
| ------------------ | ---------------------------------------------------------- | -------------- | --------------- | -------------- | --------------------------------------------------------- | ------------------------------------------------- |
| Spearman           | Is the whole order roughly right?                          | No, all equal  | Yes (as ranks)  | No             | Average ranks; big tail tie dilutes it; undefined if flat | Rewards sorting the clean bottom; weak on top     |
| Precision@k        | Of the k files flagged, how many had bugs?                 | No (inside k)  | No (any bug)    | No             | Safe if k is within the shortlist; ties at the cut-off matter | Ignores order and severity; depends on k          |
| nDCG@k             | Did the buggiest files come first?                         | Yes            | Yes (as gain)   | No             | Safe within shortlist; tie handling needed (average)      | One huge file dominates; undefined with no bugs   |
| Recall at 20% LOC  | With a fixed reading budget, what share of bugs did I hit? | Yes (cumulative) | Yes (total)   | Yes            | Needs tie-break and a rule for the tail                   | Assumes effort equals size; rewards small files   |
| Popt (area)        | Same, across every budget at once                          | Yes            | Yes             | Yes            | Same as above                                             | Harder to explain; same size assumption           |

## Which metrics fit

- **Primary: nDCG@k.** It rewards putting the worst files first, handles shortlists cleanly, and uses bug counts. Fix k and the gain form up front.
- **Co-primary or key secondary: recall at 20% of LOC.** It matches how a team would act on the list and exposes size bias in either ranker. Report it next to nDCG so a ranker cannot win only by liking small files.
- **Report: precision@k.** Cheap, understandable, and shows the hit rate in plain terms. Do not use alone.
- **Diagnostic only: Spearman**, and only for rankers that order every file. It is a poor primary metric here because of the clean-file bottom and tie sensitivity.
- Any choice needs a paired comparison of the LLM against churn x complexity on the same files, plus some measure of uncertainty. Choosing that is a separate question from the metric.

## Decisions for the owner

1. **Gain form.** Raw bug counts, binary (buggy or not), or damped (log of count)? This changes who wins when counts are skewed.
2. **Which metric is primary**, and is a second one (recall at 20% LOC) required to agree before calling a win?
3. **Value of k** (and the shortlist length asked of the LLM). Should both rankers be scored on the same candidate set?
4. **Effort proxy**: lines of code, complexity, or none (skip effort-aware metrics)?
5. **Budget and edge rule** for effort-aware scoring: 20% or another share, and what to do when the next file overflows the budget.
6. **Tie rule**: average over tied orderings (recommended in the literature) or a fixed deterministic tie-break such as path name? Whichever is chosen must be deterministic for Replay.
7. **Unranked tail**: for a shortlist-only ranker, are unranked files treated as tied at the bottom, excluded, or filled by a baseline?
8. **No-bug repos or windows**: skip, report as undefined, or require a minimum bug count?
9. **Aggregation**: one pooled score across repos, or per-repo scores averaged, and how to report uncertainty?

These overlap with the label, window and target decision tickets in the architecture map (#30); the metric should be fixed together with them.

## Source reliability notes

- Read directly this session: SciPy `spearmanr` docs, scikit-learn `ndcg_score` docs, the 2025 critique on arXiv (2504.19181).
- Identified by bibliographic record only, full text not read: Järvelin and Kekäläinen 2002 (the PDF fetched was unreadable), Mende and Koschke 2010, Ostrand et al. 2005, McSherry and Najork 2008, and Manning et al. (the IR book site refused the connection). Claims attributed to them above are stated as summaries and should be verified before they go into an ADR.
- Not covered: the Kamei et al. just-in-time work that popularized PofB20 and Arisholm et al.'s cost-effectiveness curve, which the sources above cite but this note did not read. Rank-biased overlap, Kendall's tau and average precision were left out as outside the question.

## Sources

- Järvelin, K. and Kekäläinen, J. (2002). Cumulated gain-based evaluation of IR techniques. ACM TOIS 20(4), 422-446. https://doi.org/10.1145/582415.582418
- SciPy documentation, `scipy.stats.spearmanr`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html
- scikit-learn documentation, `sklearn.metrics.ndcg_score`. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html
- Manning, C., Raghavan, P. and Schütze, H. (2008). Introduction to Information Retrieval, ch. 8. https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html
- McSherry, F. and Najork, M. (2008). Computing information retrieval performance measures efficiently in the presence of tied scores. ECIR 2008. https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ecir2008.pdf
- Mende, T. and Koschke, R. (2010). Effort-aware defect prediction models. CSMR 2010. https://bibtex.github.io/CSMR-2010-MendeK.html
- Ostrand, T., Weyuker, E. and Bell, R. (2005). Predicting the location and number of faults in large software systems. IEEE TSE. https://www.cs.virginia.edu/woda/papers/ostrand.pdf
- Critical considerations on effort-aware software defect prediction metrics (2025). https://arxiv.org/html/2504.19181v1
