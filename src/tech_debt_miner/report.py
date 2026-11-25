"""Report: aggregate many Runs' scores into one verdict (ADR 0005, 0006, 0008, 0020).

Pure functions over `RunScores`. The unit is the repo: repeats are averaged, then Cutoff dates
within a repo, and every repo weighs the same in the mean paired difference (treatment minus
control) and its seeded bootstrap CI.
"""

import math
import random
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from tech_debt_miner.types import BASELINE, RunScores

NDCG_METRIC = "ndcg@20"  # keys of `scoring.score_ranking`; a unit test keeps them in sync
RECALL_METRIC = "recall@20%loc"
NULL_MARGIN = 0.05  # ADR 0005: a judgment call, not sourced
EVIDENCE_FLOOR = 5  # scoreable repos needed for a verdict (ADR 0005)
PRIMARY_SCORING_DATE = "2027-01-31"  # earliest scoring on or after this is primary (ADR 0006)
RESAMPLES = 10_000
SEED = 20_270_131  # fixed so the same score files always give the same CI (ADR 0020)
CONFIDENCE = 0.95


class Outcome(StrEnum):
    NULL = "Null"
    MIXED = "Mixed"
    WIN = "Win"
    LOSS = "Loss"
    INCONCLUSIVE = "Inconclusive"


class DuplicateWindowError(ValueError):
    """Two Runs cover the same repo and Cutoff date, so averaging them would double count."""


@dataclass(frozen=True)
class RunScorings:
    """One Run's identity and every scoring it has, keyed by scoring date."""

    run_id: str
    repo: str
    cutoff_date: str
    post_training: bool  # the window starts after the model's training cutoff
    scorings: Mapping[str, RunScores]


@dataclass(frozen=True)
class WindowResult:
    """One Run's paired difference at its chosen scoring, repeats already averaged."""

    repo: str
    cutoff_date: str
    post_training: bool
    scoring_date: str
    ndcg_diff: float
    recall_diff: float


@dataclass(frozen=True)
class LeftOut:
    """A Run left out of the aggregate, with the reason; nothing drops silently."""

    run_id: str
    repo: str
    cutoff_date: str
    reason: str


@dataclass(frozen=True)
class RepoDiff:
    """A repo's headline difference: its post-training windows averaged with equal weight."""

    repo: str
    windows: int
    ndcg_diff: float
    recall_diff: float


@dataclass(frozen=True)
class Analysis:
    windows: tuple[WindowResult, ...]  # every scored window, exploratory ones included
    left_out: tuple[LeftOut, ...]
    repos: tuple[RepoDiff, ...]  # headline repos only
    mean_ndcg_diff: float | None
    ci: tuple[float, float] | None
    mean_recall_diff: float | None
    outcome: Outcome | None  # None below the evidence floor

    @property
    def direction(self) -> int:
        """Sign of the mean nDCG difference: -1, 0 or 1 (0 when there is no headline)."""
        return _sign(self.mean_ndcg_diff or 0.0)


@dataclass(frozen=True)
class Report:
    treatment: str
    control: str
    primary: Analysis
    sensitivity: Analysis | None  # the latest scoring, only when it differs from the primary

    @property
    def flipped(self) -> bool:
        """Whether the sensitivity scoring changes the outcome or reverses the direction."""
        later = self.sensitivity
        if later is None:
            return False
        return later.outcome != self.primary.outcome or later.direction * self.primary.direction < 0


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def bootstrap_ci(
    values: Sequence[float],
    *,
    resamples: int = RESAMPLES,
    seed: int = SEED,
    confidence: float = CONFIDENCE,
) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean, resampling `values` (one per repo) with replacement."""
    if not values:
        msg = "cannot bootstrap an empty sample"
        raise ValueError(msg)
    rng = random.Random(seed)  # noqa: S311  # a reproducible resample, not a secret
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    tail = (1 - confidence) / 2
    low = means[math.floor(tail * resamples)]
    high = means[max(math.ceil((1 - tail) * resamples) - 1, 0)]
    return (low, high)


def classify(ci: tuple[float, float], recall_diff: float) -> Outcome:
    """Apply ADR 0005's outcome rules in its order, so each result has exactly one outcome."""
    low, high = ci
    if low >= -NULL_MARGIN and high <= NULL_MARGIN:
        return Outcome.NULL
    if (low > 0 and recall_diff < 0) or (high < 0 and recall_diff > 0):
        return Outcome.MIXED
    if low > 0 and recall_diff >= 0:
        return Outcome.WIN
    if high < 0 and recall_diff <= 0:
        return Outcome.LOSS
    return Outcome.INCONCLUSIVE


def _is_ranking_of(name: str, ranker: str) -> bool:
    """Match `baseline` exactly, and `llm` against `llm-0`, `llm-1` and so on."""
    return name == ranker or re.fullmatch(rf"{re.escape(ranker)}-\d+", name) is not None


def _mean_metric(scores: RunScores, ranker: str, metric: str) -> float | None:
    values = [
        s.metrics[metric] for name, s in scores.rankings.items() if _is_ranking_of(name, ranker)
    ]
    return statistics.fmean(values) if values else None


def _eligible_dates(scorings: Mapping[str, RunScores]) -> list[str]:
    """Scoring dates (ISO, so string order is date order) on or after the primary date."""
    return sorted(date for date in scorings if date >= PRIMARY_SCORING_DATE)


def _choose_scoring(scorings: Mapping[str, RunScores], *, latest: bool) -> str | None:
    dates = _eligible_dates(scorings)
    if not dates:
        return None
    return dates[-1] if latest else dates[0]


def _window(
    run: RunScorings, scoring_date: str, treatment: str, control: str
) -> WindowResult | str:
    """Return the Run's paired difference, or the reason it cannot be computed."""
    scores = run.scorings[scoring_date]
    if scores.excluded:
        return scores.excluded
    diffs: list[float] = []
    for metric in (NDCG_METRIC, RECALL_METRIC):
        treated = _mean_metric(scores, treatment, metric)
        base = _mean_metric(scores, control, metric)
        if treated is None or base is None:
            missing = treatment if treated is None else control
            return f"no {missing} ranking in scores-{scoring_date}.json"
        diffs.append(treated - base)
    return WindowResult(
        run.repo, run.cutoff_date, run.post_training, scoring_date, diffs[0], diffs[1]
    )


def _check_unique(runs: Sequence[RunScorings]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for run in runs:
        key = (run.repo, run.cutoff_date)
        if key in seen:
            msg = (
                f"runs {seen[key]} and {run.run_id} both cover {run.repo} at {run.cutoff_date}; "
                "move one out of the runs directory"
            )
            raise DuplicateWindowError(msg)
        seen[key] = run.run_id


def _repo_diffs(windows: Sequence[WindowResult]) -> tuple[RepoDiff, ...]:
    by_repo: dict[str, list[WindowResult]] = {}
    for window in windows:
        if window.post_training:
            by_repo.setdefault(window.repo, []).append(window)
    return tuple(
        RepoDiff(
            repo,
            len(group),
            statistics.fmean(w.ndcg_diff for w in group),
            statistics.fmean(w.recall_diff for w in group),
        )
        for repo, group in sorted(by_repo.items())
    )


def _analyze(
    runs: Sequence[RunScorings], treatment: str, control: str, *, latest: bool, seed: int
) -> Analysis:
    windows: list[WindowResult] = []
    left_out: list[LeftOut] = []
    for run in sorted(runs, key=lambda r: (r.repo, r.cutoff_date)):
        scoring_date = _choose_scoring(run.scorings, latest=latest)
        result = (
            f"no scoring on or after {PRIMARY_SCORING_DATE}"
            if scoring_date is None
            else _window(run, scoring_date, treatment, control)
        )
        if isinstance(result, str):
            left_out.append(LeftOut(run.run_id, run.repo, run.cutoff_date, result))
        else:
            windows.append(result)
    repos = _repo_diffs(windows)
    if not repos:
        return Analysis(tuple(windows), tuple(left_out), repos, None, None, None, None)
    mean_ndcg = statistics.fmean(r.ndcg_diff for r in repos)
    mean_recall = statistics.fmean(r.recall_diff for r in repos)
    ci = bootstrap_ci([r.ndcg_diff for r in repos], seed=seed)
    outcome = classify(ci, mean_recall) if len(repos) >= EVIDENCE_FLOOR else None
    return Analysis(tuple(windows), tuple(left_out), repos, mean_ndcg, ci, mean_recall, outcome)


def build_report(
    runs: Sequence[RunScorings],
    *,
    treatment: str = "llm",
    control: str = BASELINE,
    seed: int = SEED,
) -> Report:
    """Aggregate `runs` into the primary analysis, plus the later-scoring sensitivity check."""
    _check_unique(runs)
    primary = _analyze(runs, treatment, control, latest=False, seed=seed)
    later = _analyze(runs, treatment, control, latest=True, seed=seed)
    differs = any(len(_eligible_dates(run.scorings)) > 1 for run in runs)
    return Report(treatment, control, primary, later if differs else None)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.4f}"


def _render_analysis(analysis: Analysis, treatment: str, control: str) -> list[str]:
    repo_count = len(analysis.repos)
    lines: list[str] = []
    if analysis.outcome is None:
        lines.append(
            f"**No verdict:** {repo_count} scoreable repos, {EVIDENCE_FLOOR} required (ADR 0005)."
        )
    else:
        lines.append(f"**Outcome: {analysis.outcome}**")
    ci = "n/a" if analysis.ci is None else f"[{analysis.ci[0]:+.4f}, {analysis.ci[1]:+.4f}]"
    mean = f"{_fmt(analysis.mean_ndcg_diff)}, 95% CI {ci}"
    lines += [
        "",
        f"- Mean nDCG@20 difference ({treatment} minus {control}): {mean}",
        f"- Mean recall@20%-LOC difference: {_fmt(analysis.mean_recall_diff)}",
        f"- Repos in the headline (windows after the training cutoff): {repo_count}",
    ]
    return lines


def render(report: Report) -> str:
    """Render the report as Markdown. A flipped sensitivity check comes first."""
    lines = [f"# Report: {report.treatment} against {report.control}", ""]
    if report.flipped and report.sensitivity is not None:
        later = report.sensitivity
        now, before = later.outcome or "no verdict", report.primary.outcome or "no verdict"
        lines += [
            f"**Sensitivity flip:** re-scoring later gives {now}, not {before} (ADR 0006).",
            "",
        ]
    lines += ["## Headline (primary scoring)", ""]
    lines += _render_analysis(report.primary, report.treatment, report.control)
    if report.primary.repos:
        lines += [
            "",
            "| Repo | Headline windows | nDCG@20 diff | Recall diff |",
            "| --- | ---: | ---: | ---: |",
        ]
        lines += [
            f"| {r.repo} | {r.windows} | {_fmt(r.ndcg_diff)} | {_fmt(r.recall_diff)} |"
            for r in report.primary.repos
        ]
    lines += ["", "## Windows", ""]
    lines += [
        "| Repo | Cutoff | Scoring | Counts | nDCG@20 diff | Recall diff |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    lines += [
        f"| {w.repo} | {w.cutoff_date} | {w.scoring_date} | "
        f"{'headline' if w.post_training else 'exploratory'} | "
        f"{_fmt(w.ndcg_diff)} | {_fmt(w.recall_diff)} |"
        for w in report.primary.windows
    ]
    if report.primary.left_out:
        lines += ["", "## Left out", ""]
        lines += [
            f"- {s.repo} at {s.cutoff_date} ({s.run_id}): {s.reason}"
            for s in report.primary.left_out
        ]
    if report.sensitivity is not None:
        lines += ["", "## Sensitivity (latest scoring)", ""]
        lines += _render_analysis(report.sensitivity, report.treatment, report.control)
    return "\n".join(lines) + "\n"
