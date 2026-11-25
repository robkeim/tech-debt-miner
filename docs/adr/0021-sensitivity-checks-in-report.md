# Sensitivity checks are stored by `label` and `score`, and compared by `report`

Accepted 2026-11-25. Decided in #81. Implements the "Required sensitivity checks" of [ADR 0005](0005-scoring-pre-registration.md).

## Decision

- **Where each check comes from.** `report` reads only `scores-*.json`, so every check is a metric key that `score` writes: `ndcg@20:binary`, `ndcg@20:raw`, `ndcg@5`, `ndcg@10`, `ndcg@50`, `recall@20%cc` (cyclomatic complexity as effort), and `ndcg@20[<variant>]` for the keyword-only set and each Label variant.
- **Label variants.** `label` stores tracker-confirmed counts per variant in `labels.json`: `cap-5`, `cap-10`, `cap-20`, `cap-none` (6-month window) and `window-3m`, `window-12m` (primary N). The keyword-only set is the existing `keyword_counts`.
- **Complexity effort.** Each file's summed cyclomatic complexity, rounded and at least 1, so a file with no functions still costs something instead of being found for free.
- **Comparison.** Each check re-aggregates the headline repos the same way as the primary (repeats, then windows, then repos) at the primary scoring, and takes the mean paired difference. A check flips when its sign is opposite to the primary's for the same metric: nDCG@20 for all but complexity, which is compared with the recall@20%-LOC difference. A primary difference of exactly 0 has no direction to flip.
- **Reporting.** Flipped checks are named in a line before everything else. All checks are listed in a table. None changes the outcome, CI or evidence floor.
- **Missing data is shown, not hidden.** A repo whose scores lack a metric counts under "lack it" and stays out of that check's mean.

## Why

Keeping `report` a pure function of score files preserves the rule that the same files always give the same report (ADR 0020). It also keeps git and the tracker out of `report`.

## Known limits

- The 12-month window closes six months after the 6-month one, and `label` writes once. A Run labeled as soon as the primary window closes never gets `window-12m`, and the report shows that check as n/a for it. Filling it in needs a Run labeled after the 12-month window closes.
- Scores written before this change have none of the new keys; those checks show as n/a.
