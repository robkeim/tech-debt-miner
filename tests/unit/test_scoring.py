import itertools
import math

import numpy as np
import pytest
from hypothesis import given
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
        scoring.ideal_dcg_at_k({"a": 1}, 0)


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
    scores = np.array([[float(len(groups) - i) for i, g in enumerate(groups) for _ in g]])
    damped = np.array([[scoring.gain(labels.counts[p]) for p in flat]])
    if damped.max() == 0.0:
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
        scoring.dcg_at_k([["a"]], {"a": 1}, 0)
