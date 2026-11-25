# Prompt templates ship in the package, and the digest has a token budget

Accepted 2026-11-25. Decided in #87. Fills two gaps in [ADR 0010](0010-llm-ranker-design.md): where the templates live, and what "the digest overflows" means.

## Decision

- **Templates.** `triage.txt` and `rank.txt` live in `src/tech_debt_miner/prompts/` and use `string.Template` placeholders (`$count`, `$digest`, `$files`), so braces in code never need escaping and substituted code is never re-parsed. Each Manifest hash is the SHA-256 of the template file.
- **Manifest entries.** `prompt_hashes` holds the two hashes plus `digest_max_subjects`, `head_lines` and `triage_set_size` as strings, so the existing `Mapping[str, str]` type needs no change.
- **Digest budget.** The digest overflows when its estimated size exceeds 800,000 tokens, at a conservative 3 characters per token. The budget leaves a fifth of Sonnet 5.5's 1M-token context for the template, the output and error in the estimate. The 3 characters per token is the same ratio the Dry-run uses for its estimates.
- **Shrink order.** Uniform for every file: 5 subjects, 4, 3, 2, 1, 0, then no names, then path and LOC alone. Past that the builder raises and the Dry-run fails, as ADR 0010 says.
- **Stage 2 order.** The Triage set is shown in path order, not the order the model chose it in, so stage 1's order cannot bias stage 2.
- **Stage 2 shows no LOC.** The truncation marker already says how much was cut, and a line count is a complexity proxy.

## Why

- A package-relative path works from any working directory and ships in the wheel, which a repo-root `prompts/` would not.
- The budget is a convention, like the 150 lines and 5 subjects. The largest planned repo is about 175k tokens, so it matters only for a repo outside ADR 0006's bounds.

## Known limits

- The budget and the 3 characters per token are not measured. The first Dry-run and the pilot replace them, by an amendment.
