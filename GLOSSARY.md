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
