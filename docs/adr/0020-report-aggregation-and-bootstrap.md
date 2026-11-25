# Report aggregates per repo and bootstraps with a fixed seed

Accepted 2026-11-25. Decided in #80. Specifies the aggregation and uncertainty rows of [ADR 0005](0005-scoring-pre-registration.md), which fixes the outcome rules and the margin.

## Decision

- **Unit and weights.** Repeats are averaged, then Cutoff dates within a repo. Each repo counts once in the mean paired difference (treatment minus Baseline).
- **Headline windows.** Only Runs whose Manifest has `C - K` above 0 feed the headline. Earlier windows are listed as exploratory and never counted.
- **Scoring file.** Per Run, the earliest `scores-<date>.json` on or after 2027-01-31 is primary. The latest is the sensitivity check, shown only when some Run has more than one eligible file. If it changes the outcome or the direction, the report says so first.
- **Bootstrap.** Percentile CI over the per-repo nDCG@20 differences: 10,000 resamples with replacement, seed 20270131, 95%. The same score files always give the same CI.
- **Outcome.** The recall@20%-LOC difference is the mean over the same repos. Rules apply in ADR 0005's order, with the margin check inclusive at ±0.05. Below 5 scoreable repos the report prints the CI and no outcome.
- **Left out, never dropped.** Runs excluded by the minimum-data rule, Runs with no eligible scoring and Runs missing a ranking are listed with the reason.
- **Duplicates fail.** Two Runs for one repo and Cutoff date make `report` stop, since averaging them would double count a window.

## Why

The resample count, seed and percentile method are choices ADR 0005 leaves open. Fixing them before any scored Run keeps them from being tuned to a result. A fixed seed makes the CI a pure function of the files.

## Known limits

- With 5 to 8 repos the percentile interval is narrow-biased; ADR 0005 already warns the CI is unreliable at this size.
- One repo in the headline gives a zero-width CI, so the evidence floor, not the CI, is what protects against it.
