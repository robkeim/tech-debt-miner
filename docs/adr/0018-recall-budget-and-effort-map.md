# Recall at 20% of LOC: what the budget counts and how ties are averaged

Accepted 2026-11-24. Decided in #76. Clarifies the "Co-primary", "Budget rule", "Reported, not decisive" and "Ties" rows of [ADR 0005](0005-scoring-pre-registration.md); everything else in ADR 0005 stands. Like ADR 0005, it is frozen when merged to `main`, which must happen before the first scored Run.

## Decision

- **Effort map.** The effort map holds the physical LOC at the Pinned SHA of every eligible file ([ADR 0004](0004-label-is-future-fix-proneness.md)). Total LOC is the sum over that map, and the budget is 20% of it, rounded down to a whole line. A file fits when the lines taken so far plus its own do not exceed the budget, so a file that lands exactly on the budget fits.
- **Files outside the map.** A ranked file that is not in the effort map (ineligible, or absent at the Pinned SHA) costs no budget and finds nothing. It does not shrink the denominator either.
- **Numerator and denominator.** The numerator is the sum of the Labels of the files taken. The denominator is the sum of all Labels, including files deleted after the Cutoff date, which keep their Label (ADR 0004) but cannot be ranked. A repo whose Labels sum to 0 scores 0.0.
- **Repeats.** A file named again after its first occurrence is ignored, so it neither costs budget nor finds anything twice. This matches [ADR 0013](0013-duplicate-files-keep-their-slot.md): the repeat earns nothing. There is no slot to keep, since recall is measured in LOC and not positions.
- **Tie averaging.** The score is the expectation over every ordering of each tie group, with skip-and-continue applied to each ordering. A group that fits whole, or none of whose members fit, needs no averaging. Otherwise the scorer enumerates the walk exactly when the straddling group has at most 10 files that still fit and at most 256 leftover-budget states are alive; beyond that it averages 2,000 random orderings from a fixed seed, with members sorted by path first so that input order cannot change the result. Both paths give the same number for the same tie sets on every machine.
- **Effort proxy.** The scorer takes any path-to-cost map. The cyclomatic-complexity sensitivity check passes complexity per eligible file instead of LOC; nothing else changes.
- **Gain variants.** The binary gain (1 for a Label of 1 or more) and the raw gain (the Label itself) are the sensitivity gains; the primary stays damped.
- **precision@k.** The share of the first k slots held by a file with a Label of 1 or more, averaged over ties, with k as the denominator even when the ranking is shorter than k. Repeats follow the nDCG rule. Reported at k = 5, 10, 20 and 50.
- **Spearman.** Reported only when the ranking names every file in the Label map exactly once and nothing else. Ties take the mean position. It is left out when the correlation is undefined (all files tied, or all Labels equal).
- Each scored Run's Manifest records this ADR's commit SHA beside ADR 0005's and ADR 0013's.

## Why

- **Eligible-only map.** The ranked set and the Label both use only eligible files (ADR 0004), so the files that can hold a Label are exactly the eligible ones. Taking LOC over all files would shrink the budget to a fraction of the countable code and reward rankers that name large ineligible files. Charging a ranker for ineligible files would need an effort for files the map deliberately omits.
- **Free skips.** A file outside the map can never carry a Label, so giving it a cost would only make the score depend on how big an irrelevant file is. Free and fruitless leaves the ranker where nDCG already puts it: no gain from such a file.
- **Exact when cheap, sampled when not.** The walk is order-dependent, so the exact mean over `n!` orderings has no closed form like nDCG's. Exact enumeration is cheap for small groups, and a strictly ordered ranking is always exact. The baseline can tie thousands of files (zero churn), where enumeration is impossible; a fixed seed keeps Replay deterministic. A path-name tie-break is still never used.
- **Label mass, not file count.** Recall counts Fix commits found, the PofB20 convention (ADR 0005).

## Alternatives rejected

- **Sample always.** It would make small cases approximate for no reason and weaken the property test against brute force.
- **Approximate tie averaging with expected-LOC fractions.** It misstates skip-and-continue, which is the budget rule ADR 0005 fixed.
- **Total LOC over every file in the repo.** See above.

## Known limits

- The sampled path has standard error up to about 0.011 on the recall fraction, so a very large tie group blurs recall by about that much. The baseline's zero-churn tie sits at the bottom of its ranking and rarely straddles the budget.
- Recall@20%-LOC still favors rankers that fill the budget (ADR 0005, Known limits).
