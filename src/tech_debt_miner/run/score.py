"""The `score` stage: every ADR 0005 metric for each ranking of one Run (ADR 0008)."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from tech_debt_miner import scoring
from tech_debt_miner.run.artifacts import (
    LABELS,
    LABELS_12M,
    RANKING,
    SCORES,
    SNAPSHOT,
    ranking_name,
)
from tech_debt_miner.run.label import LabelMissingError
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import RunScores


class NoRankingsError(RuntimeError):
    """The Run has no ranking to score."""


@dataclass(frozen=True)
class ScoreDeps:
    """Injected collaborators."""

    clock: Callable[[], datetime]


def score(run_dir: RunDir, deps: ScoreDeps) -> RunScores:
    """Write `scores-<scoring-date>.json` for the Run, scoring every ranking it has.

    Rankings are read generically, so Baseline and LLM rankings need no special case. A Run with
    fewer than `MIN_LABELED_FILES` files at Label 1 or more is written as excluded, with its
    reason and count and no metrics, so `report` can count it and nothing drops silently. The
    scoring date is today by the injected clock. A second score on the same day fails, and an
    earlier file is never overwritten.
    """
    if not run_dir.exists(LABELS):
        msg = "no labels.json; run `label` first"
        raise LabelMissingError(msg)
    scoring_date = deps.clock().date().isoformat()
    if run_dir.exists(SCORES, scoring_date):
        msg = f"{SCORES.path(scoring_date)} already exists; it is never overwritten"
        raise FileExistsError(msg)
    keys = run_dir.keys(RANKING)
    if not keys:
        msg = "no rankings; run `rank` first"
        raise NoRankingsError(msg)

    labels = run_dir.read(LABELS)
    if run_dir.exists(LABELS_12M):  # written later by `label-later`, never into labels.json
        late = run_dir.read(LABELS_12M)
        labels = replace(labels, variants={**labels.variants, "window-12m": late.counts})
    labeled_files = sum(1 for count in labels.counts.values() if count >= 1)
    excluded = (
        f"{labeled_files} files with a Label of 1 or more, "
        f"fewer than the {scoring.MIN_LABELED_FILES} required"
        if labeled_files < scoring.MIN_LABELED_FILES
        else ""
    )
    files = () if excluded else run_dir.read(SNAPSHOT).files
    loc = {f.path: f.loc for f in files}
    complexity = {f.path: max(1, round(f.complexity)) for f in files}  # a file never costs 0
    result = RunScores(
        labeled_files=labeled_files,
        min_labeled_files=scoring.MIN_LABELED_FILES,
        excluded=excluded,
        rankings={}
        if excluded
        else {
            ranking_name(*key): scoring.score_ranking(
                run_dir.read(RANKING, key).groups, labels, loc, complexity
            )
            for key in keys
        },
    )
    run_dir.write(SCORES, result, scoring_date)
    return result
