# tech-debt-miner

A backtest of whether an LLM can rank files by technical-debt risk better than churn × complexity.

## Language

**Run**:
One execution of an experiment against a target repo, producing rankings and scores.
_Avoid_: Job, execution, trial

**Manifest**:
The immutable record of everything needed to identify and re-score a Run: model, prompts, target repo SHA, cutoff date and cost.
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
Re-scoring a Run from its logged LLM responses without calling the LLM again.
_Avoid_: Rerun (a rerun calls the LLM again)

**Response cache**:
A local store of LLM responses keyed by the exact request, so identical requests are never paid for twice.
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
The per-file ground truth: the number of distinct Fix commits touching the file after the Cutoff date.
_Avoid_: Ground truth (as a noun for one file's value), tag

**Baseline**:
The churn × complexity ranker the LLM is compared against, defined by [ADR 0007](docs/adr/0007-heuristic-baseline-definition.md).
_Avoid_: Heuristic (as a noun), control

**Churn**:
A file's number of commits on the default branch in the Churn window, with merge commits excluded and renames followed.
_Avoid_: Revisions, change count

**Churn window**:
The 12 months before the Cutoff date over which Churn is counted. Not the scoring window after the Cutoff date.
_Avoid_: Window (unqualified), lookback

**Shortlist**:
The at most 100 files the LLM ranker's triage stage selects from a digest of every eligible file, and the only files the rank stage sees code for. Not the ranked output, which holds at most 50.
_Avoid_: Candidate set (ADR 0005 rejects a candidate set shared by both rankers)
