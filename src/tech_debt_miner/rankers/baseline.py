"""The Baseline: rank-product of churn and complexity percentile ranks (ADR 0007). Pure."""

from collections import defaultdict
from fractions import Fraction

from tech_debt_miner.types import BASELINE, Ranking, Snapshot


def percentile_ranks(values: list[float]) -> list[Fraction]:
    """Return `rank / N` per value: 1-based ascending ranks, tied values sharing their mean rank.

    Exact fractions keep equal scores exactly equal, so ties are never split by rounding.
    """
    count = len(values)
    order = sorted(range(count), key=values.__getitem__)
    ranks = [Fraction(0)] * count
    start = 0
    while start < count:
        end = start
        while end + 1 < count and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = Fraction(start + end + 2, 2)  # mean of the 1-based positions start+1..end+1
        for index in order[start : end + 1]:
            ranks[index] = average / count
        start = end + 1
    return ranks


def tie_groups(snapshot: Snapshot) -> list[tuple[str, ...]]:
    """Return the files grouped by equal score, most risky group first.

    Files in one group are tied (ADR 0007). Members are sorted by path only so the stored
    bytes are deterministic; that order carries no meaning and is not a tie-break, because
    ADR 0005's tie averaging treats the group as unordered (ADR 0019).
    """
    files = snapshot.files
    churn = percentile_ranks([float(f.churn) for f in files])
    complexity = percentile_ranks([f.complexity for f in files])
    by_score: dict[Fraction, list[str]] = defaultdict(list)
    for fact, churn_pct, complexity_pct in zip(files, churn, complexity, strict=True):
        by_score[churn_pct * complexity_pct].append(fact.path)
    return [tuple(sorted(by_score[score])) for score in sorted(by_score, reverse=True)]


class BaselineRanker:
    """Implements `Ranker`. `repeat` is ignored: the Baseline is deterministic."""

    def rank(self, snapshot: Snapshot, *, repeat: int) -> Ranking:  # noqa: ARG002 - protocol
        return Ranking(ranker=BASELINE, repeat=0, groups=tuple(tie_groups(snapshot)))
