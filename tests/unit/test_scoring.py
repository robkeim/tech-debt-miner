import itertools
import math
from fractions import Fraction

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from sklearn.metrics import ndcg_score  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]  # scikit-learn ships no stubs; dev-only oracle

from tech_debt_miner import scoring
from tech_debt_miner.types import Labels

pytestmark = pytest.mark.unit

PATHS = [f"f{i}.py" for i in range(6)]


def _brute_force_ndcg(groups: list[list[str]], labels: Labels, k: int) -> float:
    """Average strict nDCG over every ordering of every tie group."""
    orderings = [list(itertools.permutations(g)) for g in groups]
    scores = [
        scoring.ndcg_at_k_strict([p for g in combo for p in g], labels, k)
        for combo in itertools.product(*orderings)
    ]
    return math.fsum(scores) / len(scores)


@st.composite
def _case(draw: st.DrawFn) -> tuple[list[list[str]], Labels, int]:
    n = draw(st.integers(2, 6))
    order = draw(st.permutations(PATHS[:n]))
    sizes = draw(st.lists(st.integers(1, 3), min_size=1, max_size=n))
    groups: list[list[str]] = []
    start = 0
    for size in sizes:
        if start >= n:
            break
        groups.append(list(order[start : start + size]))
        start += size
    if start < n:
        groups.append(list(order[start:]))
    counts = {p: draw(st.integers(0, 40)) for p in PATHS[:n]}
    return groups, Labels(counts=counts), draw(st.integers(1, 8))


def test_gain_is_damped_and_zero_for_label_zero() -> None:
    assert scoring.gain(0) == 0.0
    assert scoring.gain(1) == 1.0
    assert scoring.gain(8) == 4.0


def test_gain_rejects_negative_label() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        scoring.gain(-1)


def test_discount_uses_one_based_log2_position() -> None:
    assert scoring.discount(1) == 1.0
    assert scoring.discount(3) == 0.5
    with pytest.raises(ValueError, match="at least 1"):
        scoring.discount(0)


def test_k_must_be_positive() -> None:
    labels = Labels(counts={"a": 1})
    with pytest.raises(ValueError, match="k must"):
        scoring.ndcg_at_k_strict(["a"], labels, 0)
    with pytest.raises(ValueError, match="k must"):
        scoring.ideal_dcg_at_k(labels, 0)


def test_perfect_ranking_scores_one() -> None:
    labels = Labels(counts={"a": 8, "b": 3, "c": 1, "d": 0})
    assert scoring.ndcg_at_k_strict(["a", "b", "c", "d"], labels, 20) == pytest.approx(1.0)


def test_worked_example() -> None:
    labels = Labels(counts={"a": 8, "b": 1})
    # Worked by hand: the gains are 4 and 1, and slot 2 has discount 1 / log2(3).
    expected = (1.0 + 4.0 / math.log2(3)) / (4.0 + 1.0 / math.log2(3))
    assert scoring.ndcg_at_k_strict(["b", "a"], labels, 20) == pytest.approx(expected)


def test_no_relevant_files_scores_zero() -> None:
    assert scoring.ndcg_at_k_strict(["a"], Labels(counts={"a": 0}), 5) == 0.0
    assert scoring.ndcg_at_k_strict(["a"], Labels(counts={}), 5) == 0.0


def test_duplicate_counts_once_at_first_position_and_keeps_its_slot() -> None:
    labels = Labels(counts={"a": 8, "b": 8})
    # "a" repeated takes slot 2 for nothing, so "b" lands in slot 3.
    got = scoring.ndcg_at_k_strict(["a", "a", "b"], labels, 20)
    expected = (4.0 + 4.0 * scoring.discount(3)) / (4.0 + 4.0 * scoring.discount(2))
    assert got == pytest.approx(expected)


def test_missing_file_scores_zero_and_keeps_its_slot() -> None:
    labels = Labels(counts={"a": 8})
    got = scoring.ndcg_at_k_strict(["ghost", "a"], labels, 20)
    assert got == pytest.approx(scoring.discount(2))


def test_only_the_top_k_positions_count() -> None:
    labels = Labels(counts={"a": 8})
    assert scoring.ndcg_at_k_strict(["x", "y", "a"], labels, 2) == 0.0


def test_tie_group_spanning_k_averages_the_discounts_inside_k() -> None:
    labels = Labels(counts={"a": 8})
    # a is equally likely in slot 1 or 2; k = 1 keeps only slot 1.
    assert scoring.ndcg_at_k([["a", "b"]], labels, 1) == pytest.approx(0.5)


def test_tie_score_ignores_member_order() -> None:
    labels = Labels(counts={"a": 8, "b": 2, "c": 5})
    assert scoring.ndcg_at_k([["a", "b", "c"]], labels, 3) == scoring.ndcg_at_k(
        [["c", "a", "b"]], labels, 3
    )


@given(_case())
def test_tie_averaging_matches_brute_force_over_orderings(
    case: tuple[list[list[str]], Labels, int],
) -> None:
    groups, labels, k = case
    assert scoring.ndcg_at_k(groups, labels, k) == pytest.approx(
        _brute_force_ndcg(groups, labels, k), abs=1e-9
    )


@given(_case())
def test_ndcg_is_within_unit_interval(case: tuple[list[list[str]], Labels, int]) -> None:
    groups, labels, k = case
    assert 0.0 <= scoring.ndcg_at_k(groups, labels, k) <= 1.0 + 1e-9


@given(_case())
def test_member_order_within_a_group_never_matters(
    case: tuple[list[list[str]], Labels, int],
) -> None:
    groups, labels, k = case
    reversed_groups = [list(reversed(g)) for g in groups]
    assert scoring.ndcg_at_k(groups, labels, k) == pytest.approx(
        scoring.ndcg_at_k(reversed_groups, labels, k)
    )


@given(_case())
def test_sorting_by_label_descending_is_optimal(case: tuple[list[list[str]], Labels, int]) -> None:
    groups, labels, k = case
    flat = [p for g in groups for p in g]
    best = sorted(flat, key=lambda p: -labels.counts[p])
    assert scoring.ndcg_at_k_strict(best, labels, k) >= scoring.ndcg_at_k(groups, labels, k) - 1e-9


@given(_case())
def test_matches_scikit_learn_ndcg_score_on_complete_rankings(
    case: tuple[list[list[str]], Labels, int],
) -> None:
    # The oracle agrees where every file is ranked: same discount, tie averaging by default.
    groups, labels, k = case
    flat = [p for g in groups for p in g]
    scores = [[float(len(groups) - i) for i, g in enumerate(groups) for _ in g]]
    damped = [[scoring.gain(labels.counts[p]) for p in flat]]
    if max(damped[0]) == 0.0:
        assert scoring.ndcg_at_k(groups, labels, k) == 0.0
        return
    expected = float(ndcg_score(damped, scores, k=k, ignore_ties=False))
    assert scoring.ndcg_at_k(groups, labels, k) == pytest.approx(expected, abs=1e-9)


@given(_case(), st.data())
def test_a_repeated_file_scores_like_a_missing_one_in_the_same_slot(
    case: tuple[list[list[str]], Labels, int], data: st.DataObject
) -> None:
    groups, labels, k = case
    flat = [p for g in groups for p in g]
    at = data.draw(st.integers(1, len(flat)))
    repeated = [*flat[:at], flat[0], *flat[at:]]
    ghosted = [*flat[:at], "ghost.py", *flat[at:]]
    assert scoring.ndcg_at_k_strict(repeated, labels, k) == pytest.approx(
        scoring.ndcg_at_k_strict(ghosted, labels, k)
    )


def test_a_repeat_inside_a_tie_group_keeps_its_slot() -> None:
    labels = Labels(counts={"a": 8})
    # The group spans slots 1 and 2 and "a" counts once; the ideal is a alone in slot 1.
    expected = (scoring.discount(1) + scoring.discount(2)) / 2
    assert scoring.ndcg_at_k([["a", "a"]], labels, 20) == pytest.approx(expected)


def test_a_repeat_in_a_later_tie_group_scores_zero() -> None:
    labels = Labels(counts={"a": 8, "b": 8})
    got = scoring.ndcg_at_k([["a"], ["a", "b"]], labels, 20)
    expected = (4.0 + 4.0 * (scoring.discount(2) + scoring.discount(3)) / 2) / (
        4.0 + 4.0 * scoring.discount(2)
    )
    assert got == pytest.approx(expected)


def test_an_empty_group_takes_no_slot() -> None:
    labels = Labels(counts={"a": 8})
    assert scoring.ndcg_at_k([[], ["a"]], labels, 20) == pytest.approx(1.0)


def test_dcg_rejects_a_non_positive_k() -> None:
    with pytest.raises(ValueError, match="k must"):
        scoring.dcg_at_k([["a"]], Labels(counts={"a": 1}), 0)


# Recall at a budget, precision@k, Spearman and the sensitivity gains (ADR 0014).


def _brute_force_recall(
    groups: list[list[str]], labels: Labels, effort: dict[str, int], budget: int
) -> float:
    """Average skip-and-continue recall over every ordering of every tie group."""
    total = sum(labels.counts.values())
    scores: list[float] = []
    for combo in itertools.product(*(itertools.permutations(g) for g in groups)):
        left, found = budget, 0
        for path in (p for g in combo for p in g):
            if effort[path] <= left:
                left -= effort[path]
                found += labels.counts[path]
        scores.append(found / total)
    return math.fsum(scores) / len(scores)


@st.composite
def _recall_case(draw: st.DrawFn) -> tuple[list[list[str]], Labels, dict[str, int]]:
    groups, labels, _ = draw(_case())
    effort = {p: draw(st.integers(0, 30)) for g in groups for p in g}
    return groups, labels, effort


def test_recall_walk_skips_a_file_that_overflows_and_continues() -> None:
    labels = Labels(counts={"big": 5, "a": 2, "b": 3})
    effort = {"big": 5, "a": 3, "b": 2}  # total 10, so half is a budget of 5
    half = Fraction(1, 2)
    # "big" takes the whole budget.
    assert scoring.recall_at_budget([["big"], ["a"], ["b"]], labels, effort, half) == 0.5
    # "a" takes 3, "big" is skipped, and "b" fits exactly in the 2 that are left.
    assert scoring.recall_at_budget([["a"], ["big"], ["b"]], labels, effort, half) == 0.5


def test_recall_unused_budget_finds_nothing() -> None:
    labels = Labels(counts={"a": 4, "b": 4})
    effort = {"a": 1, "b": 99}
    assert scoring.recall_at_budget([["a"]], labels, effort) == pytest.approx(0.5)


def test_recall_default_budget_is_twenty_percent_of_total_effort() -> None:
    labels = Labels(counts={"a": 1, "b": 1})
    assert scoring.recall_at_budget([["a"]], labels, {"a": 20, "b": 80}) == pytest.approx(0.5)
    assert scoring.recall_at_budget([["a"]], labels, {"a": 21, "b": 79}) == 0.0


def test_recall_file_exactly_on_the_budget_fits() -> None:
    labels = Labels(counts={"a": 1})
    assert scoring.recall_at_budget([["a"]], labels, {"a": 1, "b": 4}) == 1.0


def test_recall_ignores_files_outside_the_effort_map_and_repeats() -> None:
    labels = Labels(counts={"a": 2, "b": 2})
    effort = {"a": 1, "b": 9}
    groups = [["ghost"], ["a"], ["a"], ["b"]]
    assert scoring.recall_at_budget(groups, labels, effort) == pytest.approx(0.5)


def test_recall_denominator_includes_labels_of_unranked_files() -> None:
    labels = Labels(counts={"a": 1, "deleted": 3})
    assert scoring.recall_at_budget([["a"]], labels, {"a": 1, "pad": 9}) == pytest.approx(0.25)


def test_recall_is_zero_without_any_label() -> None:
    assert scoring.recall_at_budget([["a"]], Labels(counts={"a": 0}), {"a": 1}) == 0.0


def test_recall_rejects_a_bad_fraction() -> None:
    with pytest.raises(ValueError, match="fraction"):
        scoring.recall_at_budget([], Labels(counts={}), {}, Fraction(0))
    with pytest.raises(ValueError, match="fraction"):
        scoring.recall_at_budget([], Labels(counts={}), {}, Fraction(3, 2))


def test_recall_tie_group_averages_over_orderings() -> None:
    labels = Labels(counts={"a": 6, "b": 2})
    effort = {"a": 3, "b": 2}
    # Total 5, budget 3: a first takes 3 and b no longer fits; b first takes 2 and a is out.
    got = scoring.recall_at_budget([["a", "b"]], labels, effort, Fraction(3, 5))
    assert got == pytest.approx((6 / 8 + 2 / 8) / 2)


def test_recall_leftover_budget_after_a_tie_group_reaches_later_groups() -> None:
    labels = Labels(counts={"a": 1, "b": 1, "c": 8})
    effort = {"a": 3, "b": 2, "c": 2}
    # Total 7, budget 3. After {a, b} c (cost 2) fits only if b went first alone... it never
    # does: b leaves 1 and a leaves 0.
    got = scoring.recall_at_budget([["a", "b"], ["c"]], labels, effort, Fraction(3, 7))
    assert got == pytest.approx(0.1)
    # With budget 4, b first leaves 2 so c fits; a first leaves 1 so it does not.
    got = scoring.recall_at_budget([["a", "b"], ["c"]], labels, effort, Fraction(4, 7))
    assert got == pytest.approx(((1 + 8) / 10 + 1 / 10) / 2)


@given(_recall_case())
def test_recall_matches_brute_force_over_orderings(
    case: tuple[list[list[str]], Labels, dict[str, int]],
) -> None:
    groups, labels, effort = case
    assume(sum(labels.counts.values()) > 0)
    budget = sum(effort.values()) // 5
    assert scoring.recall_at_budget(groups, labels, effort) == pytest.approx(
        _brute_force_recall(groups, labels, effort, budget), abs=1e-9
    )


@given(_recall_case())
def test_recall_ignores_member_order_and_stays_in_unit_interval(
    case: tuple[list[list[str]], Labels, dict[str, int]],
) -> None:
    groups, labels, effort = case
    got = scoring.recall_at_budget(groups, labels, effort)
    flipped = scoring.recall_at_budget([list(reversed(g)) for g in groups], labels, effort)
    assert got == pytest.approx(flipped)
    assert 0.0 <= got <= 1.0 + 1e-9


def test_recall_sampling_is_deterministic_and_close_to_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = Labels(counts={f"f{i}": i + 1 for i in range(5)})
    effort = {f"f{i}": 2 + i for i in range(5)}
    group = [f"f{i}" for i in range(5)]
    half = Fraction(1, 2)
    exact = scoring.recall_at_budget([group], labels, effort, half)
    monkeypatch.setattr(scoring, "_EXACT_GROUP_LIMIT", 0)
    first = scoring.recall_at_budget([group], labels, effort, half)
    again = scoring.recall_at_budget([list(reversed(group))], labels, effort, half)
    assert first == again
    assert first == pytest.approx(exact, abs=0.03)


def test_recall_sampling_stops_once_the_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scoring, "_EXACT_GROUP_LIMIT", 0)
    labels = Labels(counts={"a": 1, "b": 1, "c": 1})
    effort = {"a": 2, "b": 2, "c": 2}
    # Total 6, budget 3: one of a and b is taken, leaving 1, and c never fits.
    got = scoring.recall_at_budget([["a", "b"], ["c"]], labels, effort, Fraction(1, 2))
    assert got == pytest.approx(1 / 3)


def test_recall_falls_back_to_sampling_when_leftover_states_multiply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scoring, "_EXACT_STATE_LIMIT", 0)
    labels = Labels(counts={"a": 1, "b": 1})
    effort = {"a": 2, "b": 2}
    got = scoring.recall_at_budget([["a", "b"]], labels, effort, Fraction(1, 2))
    assert got == pytest.approx(0.5)


def test_cyclomatic_complexity_works_as_the_effort_map() -> None:
    labels = Labels(counts={"a": 1, "b": 1})
    loc = {"a": 10, "b": 90}
    complexity = {"a": 90, "b": 30}  # total 120, budget 24: neither file fits
    groups = [["a"], ["b"]]
    assert scoring.recall_at_budget(groups, labels, loc) == pytest.approx(0.5)
    assert scoring.recall_at_budget(groups, labels, complexity) == 0.0


def test_binary_and_raw_gains() -> None:
    assert [scoring.binary_gain(n) for n in (0, 1, 7)] == [0.0, 1.0, 1.0]
    assert [scoring.raw_gain(n) for n in (0, 1, 7)] == [0.0, 1.0, 7.0]
    for fn in (scoring.binary_gain, scoring.raw_gain):
        with pytest.raises(ValueError, match="non-negative"):
            fn(-1)


def test_raw_gain_lets_a_heavy_file_dominate_where_damped_gain_does_not() -> None:
    labels = Labels(counts={"a": 64, "b": 1})
    damped = scoring.ndcg_at_k_strict(["b", "a"], labels, 20)
    raw = scoring.ndcg_at_k_strict(["b", "a"], labels, 20, scoring.raw_gain)
    assert raw < damped


def test_binary_gain_ndcg_ignores_label_size() -> None:
    labels = Labels(counts={"a": 64, "b": 1})
    got = scoring.ndcg_at_k_strict(["b", "a"], labels, 20, scoring.binary_gain)
    assert got == pytest.approx(1.0)


def test_precision_at_k_counts_labelled_files_over_k() -> None:
    labels = Labels(counts={"a": 3, "b": 0, "c": 1})
    groups = [["a"], ["b"], ["c"]]
    assert scoring.precision_at_k(groups, labels, 3) == pytest.approx(2 / 3)
    assert scoring.precision_at_k(groups, labels, 2) == pytest.approx(1 / 2)
    assert scoring.precision_at_k([["a"]], labels, 5) == pytest.approx(1 / 5)


def test_precision_at_k_averages_ties_and_counts_repeats_once() -> None:
    labels = Labels(counts={"a": 3, "b": 0})
    assert scoring.precision_at_k([["a", "b"]], labels, 1) == pytest.approx(0.5)
    assert scoring.precision_at_k([["a"], ["a"]], labels, 2) == pytest.approx(0.5)
    assert scoring.precision_at_k([[], ["a"]], labels, 1) == 1.0


def test_precision_rejects_a_non_positive_k() -> None:
    with pytest.raises(ValueError, match="k must"):
        scoring.precision_at_k([["a"]], Labels(counts={"a": 1}), 0)


@given(_case())
def test_precision_at_k_matches_brute_force_over_orderings(
    case: tuple[list[list[str]], Labels, int],
) -> None:
    groups, labels, k = case
    runs = [
        [p for g in combo for p in g]
        for combo in itertools.product(*(itertools.permutations(g) for g in groups))
    ]
    expected = math.fsum(sum(labels.counts[p] > 0 for p in run[:k]) / k for run in runs)
    assert scoring.precision_at_k(groups, labels, k) == pytest.approx(
        expected / len(runs), abs=1e-9
    )


def test_spearman_perfect_and_reversed_orderings() -> None:
    labels = Labels(counts={"a": 3, "b": 2, "c": 1})
    assert scoring.spearman([["a"], ["b"], ["c"]], labels) == pytest.approx(1.0)
    assert scoring.spearman([["c"], ["b"], ["a"]], labels) == pytest.approx(-1.0)


def test_spearman_is_only_defined_for_full_orderings() -> None:
    labels = Labels(counts={"a": 3, "b": 2, "c": 1})
    assert scoring.spearman([["a"], ["b"]], labels) is None  # shortlist
    assert scoring.spearman([["a"], ["b"], ["c"], ["d"]], labels) is None  # extra file
    assert scoring.spearman([["a"], ["a"], ["b"], ["c"]], labels) is None  # repeat


def test_spearman_is_undefined_when_a_side_is_constant() -> None:
    assert scoring.spearman([["a", "b"]], Labels(counts={"a": 3, "b": 1})) is None
    assert scoring.spearman([["a"], ["b"]], Labels(counts={"a": 2, "b": 2})) is None


@given(_case())
def test_spearman_flips_sign_when_the_ranking_is_reversed(
    case: tuple[list[list[str]], Labels, int],
) -> None:
    groups, labels, _ = case
    got = scoring.spearman(groups, labels)
    if got is None:
        return
    assert -1.0 - 1e-9 <= got <= 1.0 + 1e-9
    assert scoring.spearman(groups[::-1], labels) == pytest.approx(-got)


def test_score_ranking_reports_every_metric() -> None:
    labels = Labels(counts={"a": 8, "b": 1, "c": 0})
    loc = {"a": 1, "b": 2, "c": 7}
    scores = scoring.score_ranking([["a"], ["b"], ["c"]], labels, loc)
    assert scores.metrics["ndcg@20"] == pytest.approx(1.0)
    # Total 10, budget 2: a (1) fits, b (2) overflows.
    assert scores.metrics["recall@20%loc"] == pytest.approx(8 / 9)
    assert scores.metrics.keys() >= {
        "ndcg@5",
        "ndcg@10",
        "ndcg@50",
        "precision@5",
        "precision@10",
        "precision@20",
        "precision@50",
        "ndcg@20:binary",
        "ndcg@20:raw",
        "spearman",
    }
    assert "spearman" not in scoring.score_ranking([["a"]], labels, loc).metrics
