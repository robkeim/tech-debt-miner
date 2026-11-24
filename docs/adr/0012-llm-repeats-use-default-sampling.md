# LLM repeats use the API's default sampling, not temperature 0

Accepted 2026-11-24. Decided in #62. Amends the Uncertainty row, the "Repeats at temperature 0" rationale and the matching Known limits of [ADR 0005](0005-scoring-pre-registration.md); everything else in ADR 0005 stands. Like ADR 0005, it is frozen when merged to `main`, which must happen before the first scored Run.

## Decision

- **Sampling.** The 3 LLM repeats per repo and Cutoff date are draws at the API's default sampling settings. Claude Sonnet 5.5 ([ADR 0006](0006-target-repos-and-cutoff-dates.md)) rejects non-default `temperature`, `top_p` and `top_k` with a 400, and every model does from 2026-10-21, so "at temperature 0" cannot be run. The Uncertainty row now reads: "3 LLM repeats per repo and Cutoff at default sampling, averaged per repo; bootstrap 95% CI over repos".
- **Repeat count stays 3.** Averaging 3 draws still cuts within-repo noise by about 40%. The count is a convention, as ADR 0005 already says.
- **Aggregation is unchanged.** Repeats are averaged per repo, then Cutoff dates within a repo, and the bootstrap resamples repos only. It does not resample repeats.
- **The spread is reported.** For each repo and Cutoff date the report shows the across-repeat standard deviation of nDCG@20 and the top-20 overlap between repeats. Both are report-only and cannot change an outcome in ADR 0005's table.
- **The ±0.05 null margin stays.** It does not depend on how the model is sampled, and changing it after learning this constraint but before any data would be arbitrary. The reported spread lets a reader judge it.
- **Scope.** Only the sampling and repeat wording changes. The thinking arm is settled separately by the pilot (#64) and its own amendment, if any.
- **Manifest.** Each scored Run's Manifest records this ADR's commit SHA beside ADR 0005's, and the policy test tracked in #57 fails a scored Run that lacks either. This adds one entry to the SHA list that [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md) describes.

## Why

- **Nothing else is runnable.** ADR 0005 says a change is "reported under both versions". The temperature-0 version cannot be executed, so this amendment is the only runnable design, and the report cites both ADRs.
- **The repeats still measure what they were for.** ADR 0005 used 3 repeats to measure the variation that remains once the output cannot be bit-reproducible. That is now larger, which is what the reported spread shows.
- **Replay is unaffected.** Scoring reads the logged responses, so it is deterministic whatever the sampling ([ADR 0001](0001-reproducibility-means-replay.md) does not mention temperature). The cache key already includes the repeat index, so the 3 identical requests are not collapsed into one response (ADR 0008).
- **Repo is the unit.** Between-repo variance dominates with about 8 repos, so more repeats would buy little of the CI's width.

## Alternatives rejected

- **A model that accepts temperature 0.** ADR 0006 chose Sonnet 5.5 for its training cutoff, which anchors the Cutoff dates.
- **Leave ADR 0005 as is and note the deviation in the report.** The pre-registration is the point of freezing, so a deviation needs an amendment.
- **5 repeats.** It adds about 67% to LLM cost, roughly $80 to $120 for the 32 Runs, for a small narrowing of the CI.
- **Resample repeats in the bootstrap.** The repo is the unit, and a two-level bootstrap adds machinery that about 8 repos cannot support.

## Known limits

- **Default sampling adds variation.** Repeats are not near-deterministic, so a single repeat's nDCG@20 can move enough to matter against the ±0.05 margin. The mean of 3 reduces this but does not remove it.
- **3 repeats is a sanity-level estimate** of the spread, not a precise one. A per-repo standard deviation from 3 draws is itself noisy.
- **The count and the margin remain conventions**, not taken from a source.
- **Results are not comparable to a temperature-0 design.** No such results will exist.
