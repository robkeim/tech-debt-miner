import statistics

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tech_debt_miner import report, scoring
from tech_debt_miner.report import (
    DuplicateWindowError,
    Outcome,
    RunScorings,
    bootstrap_ci,
    build_report,
    classify,
    render,
)
from tech_debt_miner.types import Labels, RunScores, Scores

pytestmark = pytest.mark.unit

PRIMARY = "2027-01-31"
LATER = "2027-03-01"


def scores(ndcg: float, recall: float) -> Scores:
    return Scores(metrics={report.NDCG_METRIC: ndcg, report.RECALL_METRIC: recall})


def run_scores(
    *, base: tuple[float, float] = (0.5, 0.5), llm: tuple[tuple[float, float], ...] = ()
) -> RunScores:
    rankings = {"baseline": scores(*base)}
    rankings.update({f"llm-{i}": scores(*pair) for i, pair in enumerate(llm)})
    return RunScores(labeled_files=12, min_labeled_files=10, excluded="", rankings=rankings)


def run(  # noqa: PLR0913 - a test builder; every field is optional but one
    repo: str,
    scored: RunScores,
    *,
    cutoff: str = "2026-07-01",
    post: bool = True,
    date: str = PRIMARY,
    run_id: str | None = None,
) -> RunScorings:
    return RunScorings(run_id or f"{repo}-{cutoff}", repo, cutoff, post, {date: scored})


def gain_runs(count: int, diff: float, recall: float = 0.0) -> list[RunScorings]:
    return [run(f"o/r{i}", run_scores(llm=((0.5 + diff, 0.5 + recall),) * 3)) for i in range(count)]


def test_metric_keys_match_the_scorer() -> None:
    result = scoring.score_ranking([("a.py",)], Labels(counts={"a.py": 1}), {"a.py": 1})
    assert {report.NDCG_METRIC, report.RECALL_METRIC} <= set(result.metrics)


@pytest.mark.parametrize(
    ("ci", "recall", "expected"),
    [
        ((-0.05, 0.05), 0.3, Outcome.NULL),  # the co-primary cannot change Null
        ((0.01, 0.04), -0.3, Outcome.NULL),  # positive but too small to matter
        ((0.06, 0.2), -0.1, Outcome.MIXED),
        ((-0.2, -0.06), 0.1, Outcome.MIXED),
        ((0.06, 0.2), 0.0, Outcome.WIN),  # a recall difference of exactly 0 is never Mixed
        ((0.06, 0.2), 0.1, Outcome.WIN),
        ((-0.2, -0.06), 0.0, Outcome.LOSS),
        ((-0.2, -0.06), -0.1, Outcome.LOSS),
        ((-0.1, 0.2), 0.1, Outcome.INCONCLUSIVE),
        ((-0.2, 0.04), 0.1, Outcome.INCONCLUSIVE),
        ((0.0, 0.2), 0.1, Outcome.INCONCLUSIVE),  # touching 0 is not entirely above it
    ],
)
def test_classify_follows_the_adr_order(
    ci: tuple[float, float], recall: float, expected: Outcome
) -> None:
    assert classify(ci, recall) is expected


def test_bootstrap_is_seeded_and_brackets_the_mean() -> None:
    values = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert bootstrap_ci(values) == bootstrap_ci(values)
    low, high = bootstrap_ci(values)
    assert low <= statistics.fmean(values) <= high
    # Too few draws for two seeds to agree
    one = bootstrap_ci(values, seed=1, resamples=5, confidence=0.5)
    assert one != bootstrap_ci(values, seed=2, resamples=5, confidence=0.5)


def test_bootstrap_of_one_value_has_no_width_and_empty_fails() -> None:
    assert bootstrap_ci([0.3]) == (0.3, 0.3)
    with pytest.raises(ValueError, match="empty"):
        bootstrap_ci([])


@given(st.lists(st.floats(-1, 1), min_size=1, max_size=8))
def test_bootstrap_stays_within_the_sample_range(values: list[float]) -> None:
    low, high = bootstrap_ci(values, resamples=200)
    assert min(values) - 1e-9 <= low <= high <= max(values) + 1e-9


def test_a_clear_win_over_enough_repos() -> None:
    result = build_report(gain_runs(5, 0.2, recall=0.1))
    assert result.primary.outcome is Outcome.WIN
    assert result.primary.mean_ndcg_diff == pytest.approx(0.2)
    assert result.primary.mean_recall_diff == pytest.approx(0.1)
    assert result.sensitivity is None


def test_baseline_against_itself_is_null() -> None:
    result = build_report(gain_runs(5, 0.0), treatment="baseline")
    assert result.primary.outcome is Outcome.NULL
    assert result.primary.mean_ndcg_diff == 0.0


def test_below_the_evidence_floor_there_is_no_outcome() -> None:
    result = build_report(gain_runs(4, 0.3))
    assert result.primary.outcome is None
    assert result.primary.ci is not None
    assert "No verdict" in render(result)


def test_repeats_then_cutoffs_then_repos_each_weigh_equally() -> None:
    uneven = [
        # repo a: two post-K windows, repeats average to 0.6 and 0.2, so the repo is 0.4 - 0.5
        run("o/a", run_scores(llm=((0.9, 0.5), (0.3, 0.5))), cutoff="2026-07-01"),
        run("o/a", run_scores(llm=((0.7, 0.5),)), cutoff="2026-08-01"),
        run("o/b", run_scores(llm=((0.5, 0.5),))),  # one window, difference 0
    ]
    result = build_report(uneven).primary
    by_repo = {r.repo: r for r in result.repos}
    assert by_repo["o/a"].ndcg_diff == pytest.approx((0.1 + 0.2) / 2)
    assert by_repo["o/a"].windows == 2
    assert result.mean_ndcg_diff == pytest.approx((0.15 + 0.0) / 2)


def test_exploratory_windows_never_feed_the_headline() -> None:
    runs = [
        run("o/a", run_scores(llm=((0.5, 0.5),))),
        run("o/a", run_scores(llm=((0.9, 0.9),)), cutoff="2025-01-01", post=False),
        run("o/pre", run_scores(llm=((0.9, 0.9),)), cutoff="2025-01-01", post=False),
    ]
    result = build_report(runs).primary
    assert [r.repo for r in result.repos] == ["o/a"]
    assert result.mean_ndcg_diff == 0.0
    assert len(result.windows) == 3  # still listed
    assert "exploratory" in render(build_report(runs))


def test_excluded_early_and_unranked_runs_are_listed_not_dropped() -> None:
    excluded = RunScores(3, 10, "3 files with a Label of 1 or more, fewer than 10", {})
    runs = [
        run("o/ex", excluded),
        run("o/early", run_scores(llm=((0.9, 0.9),)), date="2027-01-30"),
        run("o/unranked", run_scores()),
        run("o/ok", run_scores(llm=((0.6, 0.5),))),
    ]
    result = build_report(runs).primary
    reasons = {s.repo: s.reason for s in result.left_out}
    assert "fewer than 10" in reasons["o/ex"]
    assert "no scoring on or after 2027-01-31" in reasons["o/early"]
    assert "no llm ranking" in reasons["o/unranked"]
    assert [r.repo for r in result.repos] == ["o/ok"]
    assert "## Left out" in render(build_report(runs))


def test_earliest_scoring_is_primary_and_a_later_one_is_the_sensitivity_check() -> None:
    runs = [
        RunScorings(
            f"r{i}",
            f"o/r{i}",
            "2026-07-01",
            post_training=True,
            scorings={
                PRIMARY: run_scores(llm=((0.5, 0.5),)),
                LATER: run_scores(llm=((0.9, 0.9),)),
            },
        )
        for i in range(5)
    ]
    result = build_report(runs)
    assert result.primary.outcome is Outcome.NULL
    assert result.sensitivity is not None
    assert result.sensitivity.outcome is Outcome.WIN
    assert result.flipped
    assert render(result).index("Sensitivity flip") < render(result).index("Headline")


def test_a_later_scoring_that_agrees_is_not_a_flip() -> None:
    runs = [
        RunScorings(
            f"r{i}",
            f"o/r{i}",
            "2026-07-01",
            post_training=True,
            scorings={
                PRIMARY: run_scores(llm=((0.5, 0.5),)),
                LATER: run_scores(llm=((0.52, 0.5),)),
            },
        )
        for i in range(5)
    ]
    result = build_report(runs)
    assert result.sensitivity is not None
    assert not result.flipped
    assert "Sensitivity flip" not in render(result)


def test_two_runs_for_one_window_fail() -> None:
    twice = [run("o/a", run_scores(), run_id="r1"), run("o/a", run_scores(), run_id="r2")]
    with pytest.raises(DuplicateWindowError, match="r1 and r2"):
        build_report(twice)


def test_no_runs_gives_an_empty_report() -> None:
    result = build_report([])
    assert result.primary.outcome is None
    assert result.primary.mean_ndcg_diff is None
    assert "n/a" in render(result)


def test_every_headline_repo_is_shown_with_its_own_difference() -> None:
    text = render(build_report(gain_runs(2, 0.1)))
    assert "| o/r0 | 1 | +0.1000 | +0.0000 |" in text
    assert "| o/r1 | 1 | +0.1000 | +0.0000 |" in text


def test_a_duplicate_without_scores_is_left_out_not_fatal() -> None:
    bare = RunScorings("r2", "o/a", "2026-07-01", post_training=True, scorings={})
    result = build_report([run("o/a", run_scores(llm=((0.6, 0.5),)), run_id="r1"), bare])
    assert [r.repo for r in result.primary.repos] == ["o/a"]
    assert [s.run_id for s in result.primary.left_out] == ["r2"]


def with_metrics(base: float, llm: float, **extra: tuple[float, float]) -> RunScores:
    """Build a Run where each extra metric is given as (baseline, llm)."""
    keyed = {"ndcg@20": (base, llm), "recall@20%loc": (0.5, 0.5), **extra}
    return RunScores(
        labeled_files=12,
        min_labeled_files=10,
        excluded="",
        rankings={
            "baseline": Scores(metrics={k: v[0] for k, v in keyed.items()}),
            "llm-0": Scores(metrics={k: v[1] for k, v in keyed.items()}),
        },
    )


def checks_by_name(runs: list[RunScorings]) -> dict[str, report.CheckResult]:
    return {c.check.name: c for c in build_report(runs).primary.checks}


def test_a_check_that_reverses_the_direction_is_reported_first() -> None:
    runs = [run(f"o/r{i}", with_metrics(0.5, 0.6, **{"ndcg@5": (0.5, 0.4)})) for i in range(5)]
    result = build_report(runs)
    assert result.primary.outcome is not None  # the verdict is untouched by the check
    text = render(result)
    assert text.splitlines()[2].startswith("**Sensitivity flip:** k = 5")
    assert checks_by_name(runs)["k = 5"].flipped


def test_a_check_in_the_same_direction_does_not_flip() -> None:
    runs = [run(f"o/r{i}", with_metrics(0.5, 0.6, **{"ndcg@5": (0.5, 0.7)})) for i in range(5)]
    assert not checks_by_name(runs)["k = 5"].flipped
    assert "Sensitivity flip" not in render(build_report(runs))


def test_a_check_missing_from_older_scores_is_not_computed_not_failed() -> None:
    runs = [run(f"o/r{i}", run_scores(llm=((0.6, 0.5),))) for i in range(5)]
    got = checks_by_name(runs)["Binary gain"]
    assert got.mean_diff is None
    assert got.missing == 5
    assert not got.flipped
    assert "n/a, 5 repos lack it" in render(build_report(runs))


def test_complexity_effort_is_compared_with_the_recall_direction() -> None:
    runs = [
        run(f"o/r{i}", with_metrics(0.5, 0.6, **{"recall@20%cc": (0.5, 0.4)})) for i in range(5)
    ]
    # Primary recall difference is 0, so there is no direction to flip.
    assert not checks_by_name(runs)["Cyclomatic complexity as effort"].flipped


def test_checks_use_headline_repos_only() -> None:
    exploratory = run("o/x", with_metrics(0.5, 0.9, **{"ndcg@5": (0.5, 0.9)}), post=False)
    headline = [run(f"o/r{i}", with_metrics(0.5, 0.6, **{"ndcg@5": (0.5, 0.6)})) for i in range(5)]
    got = checks_by_name([exploratory, *headline])["k = 5"]
    assert got.repos == 5
    assert got.mean_diff == pytest.approx(0.1)
