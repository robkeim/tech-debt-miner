# The plan stage writes the estimate and the stage 1 requests

Accepted 2026-11-25. Decided in #90. Fills in the Dry-run row of [ADR 0010](0010-llm-ranker-design.md) and the "Dry-run is a planned Run" rule of [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md).

## Decision

- **A `plan` stage** runs after `snapshot`. It reads `manifest.json` and `snapshot.json`, makes no call and needs no key. It is done when `requests.jsonl` exists, and `resume` without `--run` stops after it.
- **`requests.jsonl` holds the stage 1 request of each repeat.** Those are exactly what a real Run sends first. Stage 2's prompt depends on the model's stage 1 reply, so it cannot be written in advance; it is built at send time from the same builder.
- **`estimate.json`** holds the per-repeat input tokens and the output ceiling of each stage, and the cost of the whole Run. Input tokens come from `estimate_tokens` (3 characters per token, [ADR 0023](0023-prompt-templates-and-digest-budget.md)). Output tokens are each stage's `max_tokens` (4,000 and 8,000), the same worst case the client reserves per call.
- **Stage 2 is estimated at its ceiling.** The stand-in Triage set is the `min(100, files)` files with the largest stage 2 blocks, so the real stage 2 input cannot exceed the estimate.
- **The cap check.** The estimate is written first, then compared with `--max-usd` (default $4, now a flag of `resume`). Above the cap, `plan` raises, `requests.jsonl` is not written, and the Run stays unplanned: `resume --run` cannot start it. A higher `--max-usd` plans it.
- **Overflow.** A digest that exceeds the budget at path and LOC only raises `DigestOverflowError` from `plan`. The CLI prints `excluded: <repo>: ...` and exits 1.
- **Prices** come from the client's `PRICES`. A model without one fails the plan, as it fails a call.

## Why

- A ceiling errs toward not starting a Run that might overspend, which is what the cap is for. The client's own reservation uses the same output ceiling, so a Run that passes the plan is not stopped by its first call.
- Writing only what is knowable keeps `requests.jsonl` honest: every row in it is sent as written.

## Known limits

- **Not a bound on spend.** A retry after unparsable output, or thinking tokens beyond `max_tokens`, can exceed the estimate. ADR 0010 notes a retry can double a ranking's cost; the client's cap still stops the Run mid-way.
- **The ceiling is loose.** Stage 2 at the largest blocks and output at `max_tokens` overstate a typical Run, which ADR 0010 puts well under the cap.
- **Old Runs.** A Run with `snapshot.json` but no `requests.jsonl` reads as resolved, and `resume` plans it.
- ADR 0010's cost table and ADR 0023's digest budget and 3 characters per token are still unmeasured. A real response's `usage` is the first measurement, so they are compared when the LLM rank stage (#89) has run.
