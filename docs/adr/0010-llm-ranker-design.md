# The LLM ranker is a two-stage listwise ranker that never sees the baseline

Accepted. Decided in #38. It supplies the `Ranker` protocol that ADR 0009 (PR #61) leaves open, and closes the "provisional until #38" note on the file-count bounds in [ADR 0006](0006-target-repos-and-cutoff-dates.md). Scoring is [ADR 0005](0005-scoring-pre-registration.md); the LLM client's rules are [ADR 0002](0002-single-llm-client-choke-point.md).

The ranker asks the model for one ordered list of files, in two calls: a triage over a digest of every eligible file, then a ranking of the resulting Shortlist with code and history. Everything it sees is read from the Pinned SHA and from history before the Cutoff date.

## Decisions

| Item | Decision |
| --- | --- |
| Shape | Listwise: one ordered list of at most 50 paths, each with a one-line rationale that is logged and never scored. Per-file scoring and pairwise comparison are not used. |
| Stages | Stage 1 (triage) sees a digest of every eligible file and returns a Shortlist. Stage 2 (rank) sees truncated code and history for the Shortlist and returns the ordered list. |
| Shortlist | `min(100, eligible files)`. The same two stages run for every repo size. The 100 to 1,500 file bounds in ADR 0006 stay. |
| Digest (stage 1) | Per file: path, LOC, top-level class and function names, and up to 5 recent commit subjects. Every eligible file is included, in path order. If the digest overflows, detail shrinks uniformly (fewer subjects, then no names). Files are never dropped. |
| Code (stage 2) | The first 150 lines of each Shortlist file, then an outline (class and function names with line numbers) of the rest and a `[truncated N lines]` marker. Files of 150 lines or fewer are shown whole. |
| History | Up to 5 non-merge commit subjects per file from the Churn window, each tagged `YYYY-MM-DD`, renames followed. Dates are committer dates in UTC, the same field the Cutoff filter uses. No authors, hashes, diffs or counts. |
| Issues | Not shown in v1. Showing them needs issue state as of the Cutoff date, a leakage risk and a Replay hazard. Changing this needs an amendment ADR. |
| Baseline-blind | No churn count, complexity number or Baseline ranking reaches a prompt. |
| Input type | `rank` takes only a `Snapshot`, never a repo path or git handle, so it cannot reach data after the Cutoff date. |
| Protocol | `rank(snapshot, *, repeat) -> Ranking`. The Baseline implements it and ignores `repeat`. The LLM ranker gets the client injected at construction. Rationales and the Shortlist go to the client's per-call log, not into `Ranking`. A failed schema retry raises `RankFailed`. |
| Run | One Run is one ranking: one repo, one Cutoff date and one repeat, with both stages. The per-run cap applies to it and defaults to $2, raised via `--max-usd`. |
| Cap behavior | A Run whose Dry-run estimate exceeds the cap aborts before any call. A Run that crosses the cap mid-way stops, is marked failed and is not scored. |
| Malformed output | One retry with the validation error appended; both calls are logged and billed, and each has its own cache key. A second failure fails the Run, which is reported as an exclusion, never scored as zero. Duplicates and nonexistent paths are left to ADR 0005's rules. |
| Cache key | Includes the repeat index. Otherwise the three repeats would hit the Response cache and return one response. |
| Model parameters | `temperature` is omitted, structured output uses `output_config.format`, and the rationale field stays. Stage 1 may emit up to 4k tokens and stage 2 up to 8k, plus whatever thinking needs. |
| Thinking | Default off (`thinking: {type: "between_tools"}`, effort `high`). The pilot below can change it before any scored Run. |
| Prompts | Two plain-text templates, `prompts/triage.txt` and `prompts/rank.txt`. Their hashes go in the Manifest with the digest and truncation parameters (5 subjects, 150 lines, Shortlist of 100). |
| Dry-run | Uses the same prompt builder as a real Run, makes no completion calls, and prints per-stage token counts (via `count_tokens`) and the cost estimate against the cap. |
| Leakage test | The ADR 0003 test covers both stage prompts, with the poison marker in post-Cutoff commit messages and file contents. |

## Pilot

The thinking choice is open, so it is decided by a small pilot before any scored Run. The pilot needs the client and ranker, so it is tracked in #64 and runs after this ADR merges.

- **Repo:** one Python repo that is not on ADR 0006's list, with 300 to 600 source files and the same hygiene criteria. Cutoff date 2025-07-01, so the window has closed and Labels exist. The model may have memorized it; that contamination is the same in every arm.
- **Arms:** thinking off, adaptive at effort `medium`, adaptive at effort `high`. Three repeats each, nine Runs, about $5 to $7.
- **Rule, frozen here:** pick the cheapest arm whose mean nDCG@20 is within one across-repeat standard deviation of the best arm's mean. Ties go to the lower cost.
- **Also reported:** top-20 overlap between repeats, and actual thinking tokens per arm.
- **Recording:** if the pilot picks an arm other than the default, a dated addendum records it before any scored Run, and the Manifest records the final choice.
- **Limit:** three repeats per arm is a sanity filter, not a significance test.

## Cost

Estimates from token counts I reasoned out, not measured, at Sonnet 5.5's list prices of $2 and $10 per million input and output tokens (the claude-api skill's pricing table, 2026-11-03). Dry-run replaces them.

| Item | Typical repo (about 600 files) | Largest repo (1,500 files) |
| --- | --- | --- |
| Stage 1 input (about 115 tokens per file) | 70k tokens | 175k tokens |
| Stage 2 input (100 files, about 1.6k tokens each) | 160k tokens | 160k tokens |
| Output without thinking | about 4k tokens | about 4k tokens |
| Per Run | about $0.50 | about $0.75 |

With thinking at `medium` a Run costs about $0.10 more, and at `high` about $0.30 more. The full experiment of 96 Runs is about $35 to $95. The $2 cap leaves about 2x headroom over the largest repo, and a retry can double a Run's cost.

## Why

- **Listwise.** ADR 0005 already scores a shortlist of at most 50 files at k = 20 and averages unranked files as ties. One call gives an ordered list without the N calls of per-file scoring or the O(N log N) calls of pairwise comparison.
- **Two stages.** A 1,500-file repo does not fit with code for every file. A digest of every file fits at about 175k tokens, and it lets the model choose where to spend code tokens. Inclusion is by path order and shrinks uniformly, never by churn or complexity, because that would rebuild the Baseline inside the prompt.
- **Baseline-blind.** The question is whether an LLM beats churn × complexity. Telling it the Baseline's signals makes it an echo.
- **Commit subjects with days.** With only 5 subjects, month tags often all read the same. Days show bursts and how close the last change is to the Cutoff date, the only recency signal the ranker gets. They cost about 3 tokens per commit. The cost is a small overlap with churn density and a time-zone decision, which the committer-date-in-UTC rule settles.
- **No issues.** ADR 0005 says the ranker may use them. Reconstructing their state as of the Cutoff date needs edit history, and live issue data would make the cache key and Replay depend on the API.
- **Thinking off by default.** It cuts variance and cost. Sonnet 5.5 does not accept `temperature`, so thinking is the one sampling-variance lever left. The model's reasoning might still improve stage 2, so the pilot decides rather than assuming.

## Known limits

- **Sonnet 5.5 rejects non-default `temperature`**, so ADR 0005's "3 repeats at temperature 0" cannot be run as written. The amendment is #62. The repeats still measure the remaining variance, and Replay does not depend on temperature ([ADR 0001](0001-reproducibility-means-replay.md)).
- **Thinking off may handicap the ranker.** The error is conservative: it can turn a Win into a Null or Loss, never the reverse. Results state the arm used.
- **The digest and truncation parameters are conventions**, not tuned values: 5 subjects, 150 lines, a Shortlist of 100. Changing them needs an amendment, since they shape every prompt.
- **A 150-line head** shows less of a long file than the baseline's whole-file complexity sees, and module-level logic late in a file is outline only.
- **The paths-only ablation** (the "neither" arm) is not designed here. If run, it is reported and never decisive.
- **Costs are estimates** from reasoned token counts, and thinking tokens are guesses until the pilot measures them.

## Alternatives rejected

- **Per-file scoring.** One call per file, up to 1,500 calls per Run, and scores from separate calls are not calibrated against each other.
- **Pairwise comparison.** O(N log N) calls and no cheaper than per-file scoring.
- **One call with everything.** Does not fit large repos, and truncating files to fit would drop them silently.
- **Chunked map-reduce.** More calls, and each chunk is ranked without seeing the others.
- **Showing the ranker the Baseline's scores.** See Baseline-blind above.
- **Showing issue text.** See No issues above.
- **Month-only dates.** See Commit subjects with days above.
- **Thinking on by default.** About $10 to $30 more over 96 Runs, which is minor, but it adds variance and there is no evidence yet that it helps. The pilot decides.
