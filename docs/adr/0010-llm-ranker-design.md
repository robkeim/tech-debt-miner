# The LLM ranker is a two-stage listwise ranker that never sees the baseline

Accepted. Decided in #38. It supplies the `Ranker` protocol that [ADR 0009](0009-code-layout-and-core-types.md) leaves open, and re-checks the file-count bounds that [ADR 0006](0006-target-repos-and-cutoff-dates.md) marks "provisional until #38": they stand (see the Triage set row). Scoring is [ADR 0005](0005-scoring-pre-registration.md); the LLM client's rules are [ADR 0002](0002-single-llm-client-choke-point.md).

The ranker asks the model for one ordered list of files, in two calls: a triage over a digest of every eligible file, then a ranking of the resulting Triage set with code and history. Everything it sees is read from the Pinned SHA and from history before the Cutoff date.

## Freeze

Like ADR 0005 and ADR 0007, this ADR is frozen before any scored Run, and a change needs a new dated amendment ADR. The one open item is the thinking arm, which the pilot settles by the same route before the first scored Run.

## Decisions

| Item | Decision |
| --- | --- |
| Shape | Listwise: one ordered list of at most 50 paths, each with a one-line rationale that is logged and never scored. Per-file scoring and pairwise comparison are not used. |
| Stages | Stage 1 (triage) sees a digest of every eligible file and returns a Triage set. Stage 2 (rank) sees truncated code and history for the Triage set and returns the ordered list. |
| Triage set | `min(100, eligible files)`. Eligible files are the ones ADR 0007 ranks: `*.py` at the Pinned SHA after ADR 0004's path filters. The same two stages run for every repo size. The 100 to 1,500 file bounds in ADR 0006 stay: the largest digest is about 175k tokens, well inside the 1M-token context of Sonnet 5.5. ADR 0005 calls the ranked output of at most 50 files a "shortlist"; that is the ranking, not this set. |
| Digest (stage 1) | Per file: path, LOC, top-level class and function names, and up to 5 recent commit subjects. Every eligible file is included, in path order. If the digest overflows, detail shrinks uniformly (fewer subjects, then no names). Files are never dropped. If it still overflows at path and LOC only, the Dry-run fails and the repo is excluded and reported. |
| Code (stage 2) | The first 150 lines of each Triage set file, then an outline (class and function names with line numbers) of the rest and a `[truncated N lines]` marker. Files of 150 lines or fewer are shown whole. |
| History | Up to 5 non-merge commit subjects per file from the Churn window, each tagged `YYYY-MM-DD`, renames followed. Dates are committer dates in UTC, the same field the Cutoff filter uses. No authors, hashes, diffs or counts. |
| Issues | Not shown in v1. Showing them needs issue state as of the Cutoff date, a leakage risk and a Replay hazard. ADR 0005 says the rankers "work from the raw repo and issues"; that is permission, not a requirement, so this narrows it without contradicting it. Changing this needs an amendment ADR. |
| Baseline-blind | No churn count, complexity number or Baseline ranking reaches a prompt. |
| Input type | `rank` takes only a `Snapshot`, never a repo path or git handle, so it cannot reach data after the Cutoff date. |
| Protocol | `rank(snapshot, *, repeat) -> Ranking`. The Baseline implements it and ignores `repeat`. The LLM ranker gets the client injected at construction. Rationales and the Triage set go to the client's per-call log, not into `Ranking`. A failed schema retry raises `RankFailed`. |
| Run and cap | A Run is [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md)'s unit: one (Target repo, Cutoff date) pair with the Baseline and 3 LLM repeats, each repeat running both stages. `--max-usd` caps the Run's total spend and defaults to $4, which is about 1.8x the estimated cost of the largest repo. It is raised only via `--max-usd`. |
| Cap behavior | A Run whose Dry-run estimate exceeds the cap does not start. A Run that crosses the cap mid-way stops and stays resumable with a higher `--max-usd` (ADR 0008). |
| Malformed output | One retry with the validation error appended, as ADR 0008 specifies; both calls are logged and billed, and the `attempt` index keeps them apart in the cache. A second failure makes `rank` fail loudly and the Run stays resumable. A failed ranking is never scored as zero. Duplicates and nonexistent paths are left to ADR 0005's rules. |
| Cache key | ADR 0008 already keys the Response cache on the request, the repeat and the attempt, so the three repeats are not collapsed into one response. Nothing changes here. |
| Model parameters | `temperature` is omitted, structured output uses `output_config.format`, and the rationale field stays. Stage 1 may emit up to 4k tokens and stage 2 up to 8k, plus whatever thinking needs. |
| Thinking | Default off: Sonnet 5.5 rejects `thinking: {type: "disabled"}`, and `{type: "between_tools"}`, accepted only at effort `high` or below, is how it turns thinking off. The default is effort `high`. The pilot below can change it before any scored Run, by an amendment ADR. |
| Prompts | Two plain-text templates, `prompts/triage.txt` and `prompts/rank.txt`. Their hashes go in the Manifest with the digest and truncation parameters (5 subjects, 150 lines, Triage set of 100). |
| Dry-run | Uses the same prompt builder as a real Run and makes no API call, so it stays key-free ([ADR 0002](0002-single-llm-client-choke-point.md)). It prints per-stage token estimates from a local, conservative characters-per-token ratio and the cost estimate against the cap. Real usage is read from each response's `usage` and logged. |
| Leakage test | The ADR 0003 test covers both stage prompts, with the poison marker in post-Cutoff commit messages and file contents. |

## Pilot

The thinking choice is open, so it is decided by a small pilot before any scored Run. The pilot needs the client and ranker, so it is tracked in #64 and runs after this ADR merges.

- **Repo:** one Python repo that is not on ADR 0006's list, with 300 to 600 source files and the same hygiene criteria. Cutoff date 2025-07-01, so the window has closed and Labels exist. The model may have memorized it; that contamination is the same in every arm.
- **Arms:** thinking off, adaptive at effort `medium`, adaptive at effort `high`. Each arm is one Run of 3 repeats, so three Runs and nine rankings, about $5 to $7.
- **Rule, frozen here:** pick the cheapest arm whose mean nDCG@20 is within one across-repeat standard deviation of the best arm's mean. Ties go to the lower cost.
- **Also reported:** top-20 overlap between repeats, and actual thinking tokens per arm.
- **Recording:** if the pilot picks an arm other than the default, an amendment ADR records it before any scored Run, and the Manifest records the final choice.
- **Limit:** three repeats per arm is a sanity filter, not a significance test.

## Cost

Estimates from token counts reasoned out, not measured, at Sonnet 5.5's list prices of $2 and $10 per million input and output tokens as of 2026-11-03. Check them against Anthropic's pricing page. The first Dry-run and the pilot replace the estimates, and the $4 default cap is revisited then.

| Item | Typical repo (about 600 files) | Largest repo (1,500 files) |
| --- | --- | --- |
| Stage 1 input (about 115 tokens per file) | 70k tokens | 175k tokens |
| Stage 2 input (100 files, about 1.6k tokens each) | 160k tokens | 160k tokens |
| Output without thinking | about 4k tokens | about 4k tokens |
| Per ranking | about $0.50 | about $0.75 |
| Per Run (3 repeats) | about $1.50 | about $2.25 |

With thinking at `medium` a ranking costs about $0.10 more, and at `high` about $0.30 more. The full experiment is 32 Runs (8 repos, 4 Cutoff dates) and 96 rankings: about $48 to $72 without thinking and up to about $100 at `high`. The $4 cap leaves about 1.8x headroom over the largest repo; a retry can double a ranking's cost.

## Why

- **Listwise.** ADR 0005 already scores a ranked output of at most 50 files at k = 20 and averages unranked files as ties. One call gives an ordered list without the N calls of per-file scoring or the O(N log N) calls of pairwise comparison.
- **Two stages.** A 1,500-file repo does not fit with code for every file. A digest of every file fits at about 175k tokens, and it lets the model choose where to spend code tokens. Inclusion is by path order and shrinks uniformly, never by churn or complexity, because that would rebuild the Baseline inside the prompt.
- **Stage 1 is not a pre-filter in ADR 0005's sense.** ADR 0005 forbids narrowing what both rankers are scored on, and lets each order files "however they choose". The Triage set is the LLM's own choice, scored against the same Labels as the Baseline, which still ranks everything.
- **Baseline-blind.** The question is whether an LLM beats churn × complexity. Telling it the Baseline's signals makes it an echo.
- **Commit subjects with days.** With only 5 subjects, month tags often all read the same. Days show bursts and how close the last change is to the Cutoff date, the only recency signal the ranker gets. They cost about 3 tokens per commit. The cost is a small overlap with churn density and a time-zone decision, which the committer-date-in-UTC rule settles.
- **No issues.** ADR 0005 says the ranker may use them. Reconstructing their state as of the Cutoff date needs edit history, and live issue data would make the cache key and Replay depend on the API.
- **Thinking off by default.** It cuts variance and cost. Sonnet 5.5 does not accept `temperature`, so sampling stays at the default; turning thinking off removes one source of divergence between repeats. The model's reasoning might still improve stage 2, so the pilot decides rather than assuming.

## Known limits

- **Sonnet 5.5 rejects non-default `temperature`** (per the claude-api skill's Thinking and Effort table; the pilot's first call confirms it), so ADR 0005's "3 repeats at temperature 0" cannot be run as written. [ADR 0012](0012-llm-repeats-use-default-sampling.md) amends ADR 0005 on this point. The repeats still measure the remaining variance, and Replay does not depend on temperature ([ADR 0001](0001-reproducibility-means-replay.md)).
- **Thinking off may handicap the ranker.** A weaker ranker biases results toward the Baseline: it can turn a Win into a Null, Mixed or Inconclusive result. Results state the arm used.
- **The digest and truncation parameters are conventions**, not tuned values: 5 subjects, 150 lines, a Triage set of 100. Changing them needs an amendment, since they shape every prompt.
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
- **Thinking on by default.** About $10 to $30 more over 96 rankings, which is minor, but it adds variance and there is no evidence yet that it helps. The pilot decides.

## Amendments

- 2026-11-25: [ADR 0023](0023-prompt-templates-and-digest-budget.md) fixes where the prompt templates live, defines the digest overflow budget, and adds the digest and truncation parameters to the Manifest's `prompt_hashes` as strings.
