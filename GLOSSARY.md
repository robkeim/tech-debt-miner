# tech-debt-miner

A backtest of whether an LLM can rank files by technical-debt risk better than churn × complexity.

## Language

**Run**:
One execution of an experiment against a target repo, producing rankings and scores.
_Avoid_: Job, execution, trial

**Manifest**:
The immutable record of everything needed to identify and re-score a Run: model, its training cutoff and the gap to the Cutoff date, prompt hashes, target repo SHA and cutoff date. Actual cost is recorded beside it in `cost.json`.
_Avoid_: Metadata, run config

**Target repo**:
The git repository a Run rewinds and ranks.
_Avoid_: Test repo, subject repo

**Pinned SHA**:
The exact commit of a Target repo that a Run uses, recorded in its Manifest.
_Avoid_: Version, ref

**Cutoff date**:
The past date a Target repo is rewound to; only history before it is visible to the ranker.
_Avoid_: As-of date, rewind date

**Replay**:
Re-scoring a Run from its logged LLM responses (`responses.jsonl`) without calling the LLM again, and without the Response cache or the Target repo.
_Avoid_: Rerun (a rerun calls the LLM again)

**Response cache**:
A local store of LLM responses keyed by the exact request, repeat index and attempt index ([ADR 0017](docs/adr/0017-response-cache-key-response-log-and-replay.md)), so identical requests are never paid for twice. Every reply, cache hit or not, is also copied into the Run's `responses.jsonl`.
_Avoid_: Prompt cache (that is the provider's feature)

**Dry-run**:
A Run that builds every prompt and estimates cost but makes no LLM calls.

**Leakage test**:
A test proving that nothing dated after the Cutoff date reaches a prompt or feature.
_Avoid_: Cutoff test

**Fix commit**:
A commit on the Target repo's default branch that is identified as a bug fix by the rule in [ADR 0004](docs/adr/0004-label-is-future-fix-proneness.md).
_Avoid_: Bug commit, fixing commit

**Label**:
The per-file ground truth: the number of distinct Fix commits touching the file after the Cutoff date, counted over the window `(Cutoff date, Cutoff date + 6 months]` by date. The Cutoff day itself is in neither the visible history nor the Label window.
_Avoid_: Ground truth (as a noun for one file's value), tag

**Fix size**:
The number of Eligible files a Fix commit touches, counted only for Fix commits that touch at least one. Computed on the keyword-only set, from sizes alone and never from Labels or scores.
_Avoid_: Commit size, diff size

**Fix-size cap N**:
The 90th percentile (nearest rank) of Fix sizes in the closed Label window of a Target repo. A Fix commit touching more than N Eligible files is dropped ([ADR 0004](docs/adr/0004-label-is-future-fix-proneness.md)). `validate` computes it once per Run, and it is fixed before any scored Run. The Label is also reported at N = 5, 10, 20 and uncapped.
_Avoid_: Threshold, max files (the CLI flag is `--max-files`)

**Review sheet**:
The `validate` output for the ADR 0004 smoke test: a random sample of 30 Fix commits that count under N, drawn with the fixed seed in `labels.py` from the pool ordered by SHA. Each row shows the message, the issue references found in it (candidates, not tracker-confirmed), the Eligible files and the diff stat. A pool smaller than 30 is shown whole.
_Avoid_: Validation set, audit sample

**Baseline**:
The churn × complexity ranker the LLM is compared against, defined by [ADR 0007](docs/adr/0007-heuristic-baseline-definition.md).
_Avoid_: Heuristic (as a noun), control

**Churn**:
A file's number of commits on the default branch in the Churn window, with merge commits excluded and renames followed.
_Avoid_: Revisions, change count

**Churn window**:
The 12 months before the Cutoff date over which Churn is counted. Not the scoring window after the Cutoff date.
_Avoid_: Window (unqualified), lookback

**Triage set**:
The at most 100 files the LLM ranker's triage stage selects from a digest of every eligible file, and the only files the rank stage sees code for. Not the ranked output, which holds at most 50.
_Avoid_: Shortlist (ADR 0005 uses that word for the ranked output)

**Eligible file**:
A `*.py` source file that is not a test, doc, generated or vendored file, decided by path alone, ignoring case ([ADR 0004](docs/adr/0004-label-is-future-fix-proneness.md)). The ranked set and the Label both use only eligible files.
_Avoid_: Source file (unqualified), candidate

**Response**:
One LLM reply in provider-neutral form (text, token counts, stop reason, request ID, resolved model), returned by the client in `src/tech_debt_miner/llm/client.py` ([ADR 0014](docs/adr/0014-provider-neutral-response-and-the-anthropic-dependency.md)). Not the Response cache, which stores many.
_Avoid_: Completion, message (that is the SDK's type)

**Snapshot**:
The `snapshot.json` artifact: each Eligible file's lines of code, Churn and complexity as of the Cutoff date, plus the count of files whose complexity is 0 because they have no functions or `lizard` could not analyze them, and the Target repo's issues as of the Cutoff date. An issue is kept only when its edit history proves it unedited on or after the Cutoff date; the rest are counted in `excluded_issues`, never listed. An issue's title is the one before its first rename on or after the Cutoff date. Churn counts only commits that are ancestors of the Pinned SHA, so it covers exactly the tree the complexity comes from. Each file also carries what the LLM prompts show ([ADR 0010](docs/adr/0010-llm-ranker-design.md)), so `rank` needs only the Snapshot: an outline of its classes, functions and methods with line numbers (top-level names are the depth-0 entries), its first 150 lines with the count of lines cut, and up to 5 recent commit subjects dated `YYYY-MM-DD`. The outline is empty when the file does not parse.
_Avoid_: Facts, features

**Canary probe**:
The once-per-Run check that asks the model to name the file changed by one post-Cutoff Fix commit, from its message alone with no repo context, written to `probe.json`. A hit suggests memorization. Reported beside results, never in the verdict ([ADR 0006](docs/adr/0006-target-repos-and-cutoff-dates.md)).
_Avoid_: Memorization test, contamination check

**Ranking**:
One ranker's output for one repeat: its ranker id, repeat index and an ordered tuple of Tie groups ([ADR 0019](docs/adr/0019-rankings-hold-tie-groups.md)). Not the scores.
_Avoid_: Result, ordering

**Tie group**:
Files a ranker ranks equally. Scoring averages every metric over all orderings of each tie group, never by path name ([ADR 0005](docs/adr/0005-scoring-pre-registration.md)). A Ranking is an ordered list of tie groups, most risky first; an LLM ranking is all singleton groups ([ADR 0019](docs/adr/0019-rankings-hold-tie-groups.md)).
_Avoid_: Bucket, tied set

**Effort map**:
The path-to-cost map recall at 20% of LOC is measured against: physical LOC of every eligible file at the Pinned SHA, or cyclomatic complexity for the sensitivity check ([ADR 0018](docs/adr/0018-recall-budget-and-effort-map.md)).
_Avoid_: LOC map, size map
