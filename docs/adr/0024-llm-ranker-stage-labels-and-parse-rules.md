# The LLM ranker labels its stages apart and validates the Triage set

Accepted 2026-11-25. Decided in #88. Fills gaps in [ADR 0010](0010-llm-ranker-design.md) and [ADR 0017](0017-response-cache-key-response-log-and-replay.md).

## Decision

- **Stage labels.** Stage 1 requests carry `ranker = "llm-triage"`; stage 2 requests carry `ranker = "llm"`, and the `Ranking` has `ranker = "llm"`. Replay keeps the highest attempt per (ranker, repeat), so one shared label would let a stage 1 retry hide stage 2's reply. The cache key is unaffected, since `ranker` is not in it.
- **Replay.** `replay_rankings` must skip `llm-triage` rows and parse `llm` rows with `rankers.llm.parse_ranking`. That wiring belongs to the `rank` stage issue, not this one.
- **Triage validation.** A stage 1 reply must hold exactly `min(100, eligible)` distinct paths that all exist in the Snapshot, or it counts as malformed and takes the one retry. A made-up path would otherwise crash the stage 2 prompt builder.
- **Ranking validation.** A stage 2 reply must be a non-empty list of at most 50 entries, each with a string `path`. Duplicates and nonexistent paths are kept for scoring ([ADR 0005](0005-scoring-pre-registration.md), [ADR 0013](0013-duplicate-files-keep-their-slot.md)).
- **Output limits.** 4,096 tokens for stage 1 and 8,192 for stage 2, plus a constructor-set `thinking_headroom` that is 0 by default and is how a pilot arm with thinking affords its reasoning.
- **Errors.** The client's `UnparsableOutputError` becomes `RankFailed` in the ranker, so callers handle the ADR 0010 name and never see the client's.

## Why

- A bad stage 1 reply is cheap to retry and expensive to repair later, so it is checked as strictly as the prompt builder needs.
- Counting ADR 0005's duplicate and unknown-path rules as scoring concerns keeps one definition of them.

## Known limits

- Requiring exactly `count` paths may reject a model that returns a few too many or too few; the retry message states the number. If the pilot shows this fails often, relaxing it needs an amendment.
