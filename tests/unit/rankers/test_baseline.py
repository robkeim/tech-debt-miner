from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tech_debt_miner.rankers.base import Ranker
from tech_debt_miner.rankers.baseline import BaselineRanker, percentile_ranks, tie_groups
from tech_debt_miner.types import FileFacts, Snapshot

pytestmark = pytest.mark.unit


def snapshot_of(*rows: tuple[str, int, float]) -> Snapshot:
    files = tuple(
        FileFacts(
            path,
            loc=10,
            churn=churn,
            complexity=cx,
            outline=(),
            head="",
            truncated_lines=0,
            recent_commits=(),
        )
        for path, churn, cx in rows
    )
    return Snapshot(files=files, issues=(), zero_complexity_files=0)


def test_percentile_ranks_are_rank_over_n_ascending() -> None:
    assert percentile_ranks([30, 10, 20]) == [Fraction(3, 3), Fraction(1, 3), Fraction(2, 3)]


def test_tied_values_share_their_average_rank() -> None:
    # Positions 2 and 3 tie: both get (2 + 3) / 2 = 2.5, over N = 4.
    assert percentile_ranks([1, 2, 2, 3]) == [
        Fraction(1, 4),
        Fraction(5, 8),
        Fraction(5, 8),
        Fraction(1, 1),
    ]


def test_all_equal_values_share_one_rank() -> None:
    assert percentile_ranks([7, 7, 7]) == [Fraction(2, 3)] * 3


def test_no_values_gives_no_ranks() -> None:
    assert percentile_ranks([]) == []


def test_ranks_by_the_product_of_percentile_ranks_not_the_raw_product() -> None:
    # The raw product would rank "huge_churn" first (1000 vs 100 and 81). Percentile ranks
    # weigh both signals equally: 2/3 for "balanced", 1/3 for "huge_churn", 2/9 for "third".
    snapshot = snapshot_of(("huge_churn", 1000, 1.0), ("balanced", 10, 10.0), ("third", 9, 9.0))

    ranking = BaselineRanker().rank(snapshot, repeat=0)

    assert ranking.groups == (("balanced",), ("huge_churn",), ("third",))


def test_equal_scores_stay_tied_with_no_path_name_tie_break() -> None:
    # "z" and "a" are mirror images, so both score 2/9 and form one tie group. Members are
    # sorted by path only for deterministic bytes; the group is still unordered to the scorer.
    snapshot = snapshot_of(("z.py", 1, 2.0), ("a.py", 2, 1.0), ("top.py", 3, 3.0))

    assert tie_groups(snapshot) == [("top.py",), ("a.py", "z.py")]


def test_the_ranking_keeps_the_tie_group_whole() -> None:
    snapshot = snapshot_of(("z.py", 1, 2.0), ("a.py", 2, 1.0), ("top.py", 3, 3.0))

    ranking = BaselineRanker().rank(snapshot, repeat=0)

    assert ranking.groups == (("top.py",), ("a.py", "z.py"))


def test_tie_groups_do_not_depend_on_file_order() -> None:
    forward = snapshot_of(("z.py", 1, 2.0), ("a.py", 2, 1.0), ("top.py", 3, 3.0))
    backward = Snapshot(files=forward.files[::-1], issues=(), zero_complexity_files=0)

    assert tie_groups(forward) == tie_groups(backward)


def test_ranking_names_the_baseline_and_ignores_repeat() -> None:
    snapshot = snapshot_of(("a.py", 1, 1.0), ("b.py", 2, 2.0))

    first = BaselineRanker().rank(snapshot, repeat=0)
    later = BaselineRanker().rank(snapshot, repeat=5)

    assert first == later
    assert (first.ranker, first.repeat) == ("baseline", 0)


def test_a_snapshot_with_no_files_ranks_nothing() -> None:
    assert BaselineRanker().rank(snapshot_of(), repeat=0).groups == ()


def test_the_baseline_implements_the_ranker_protocol() -> None:
    ranker: Ranker = BaselineRanker()
    assert ranker.rank(snapshot_of(("a.py", 1, 1.0)), repeat=0).groups == (("a.py",),)


@given(
    st.lists(st.tuples(st.integers(0, 5), st.integers(0, 5)), max_size=30),
)
def test_every_file_appears_once_and_groups_are_ordered_by_score(
    pairs: list[tuple[int, int]],
) -> None:
    snapshot = snapshot_of(*((f"f{i}.py", churn, float(cx)) for i, (churn, cx) in enumerate(pairs)))

    groups = tie_groups(snapshot)

    flat = [path for group in groups for path in group]
    assert sorted(flat) == sorted(f.path for f in snapshot.files)
    assert all(group for group in groups)
    churn = percentile_ranks([float(f.churn) for f in snapshot.files])
    complexity = percentile_ranks([f.complexity for f in snapshot.files])
    score = {f.path: c * x for f, c, x in zip(snapshot.files, churn, complexity, strict=True)}
    for group in groups:
        assert len({score[path] for path in group}) == 1
    firsts = [score[group[0]] for group in groups]
    assert firsts == sorted(set(firsts), reverse=True)
