"""Scoring: nDCG@k, recall at an effort budget and the reported metrics (ADR 0005, 0013, 0018).

Pure functions. A ranking is a sequence of tie groups, most risky group first; files in one
group are tied and every metric averages over all orderings of each group.
"""

import math
import random
import statistics
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from fractions import Fraction

from tech_debt_miner.types import Labels, Scores

type GainFn = Callable[[int], float]
type _Item = tuple[str, int, int]  # (path, effort, Label)

PRIMARY_K = 20
REPORTED_KS = (5, 10, 50)
LOC_BUDGET = Fraction(1, 5)
COMPLEXITY_SUFFIX = "cc"  # `recall@20%cc`: recall with cyclomatic complexity as the effort
MIN_LABELED_FILES = 10  # minimum data: files with a Label of 1 or more (ADR 0005)

_EXACT_GROUP_LIMIT = 10  # largest tie group enumerated exactly (ADR 0018)
_EXACT_STATE_LIMIT = 256  # most leftover-budget states carried while enumerating exactly
_SAMPLES = 2000
_SEED = 20_260_101


def _check_label(label: int) -> None:
    if label < 0:
        msg = f"label must be non-negative, got {label}"
        raise ValueError(msg)


def _check_k(k: int) -> None:
    if k < 1:
        msg = f"k must be at least 1, got {k}"
        raise ValueError(msg)


def gain(label: int) -> float:
    """Damped gain: `1 + log2(label)`, and 0 for a Label of 0."""
    _check_label(label)
    return 0.0 if label == 0 else 1.0 + math.log2(label)


def binary_gain(label: int) -> float:
    """Sensitivity gain: 1 for a Label above 0, else 0."""
    _check_label(label)
    return 1.0 if label > 0 else 0.0


def raw_gain(label: int) -> float:
    """Sensitivity gain: the Label itself."""
    _check_label(label)
    return float(label)


def discount(position: int) -> float:
    """Discount for a 1-based position: `1 / log2(position + 1)`."""
    if position < 1:
        msg = f"position must be at least 1, got {position}"
        raise ValueError(msg)
    return 1.0 / math.log2(position + 1)


def dcg_at_k(
    groups: Sequence[Collection[str]], labels: Labels, k: int, gain_fn: GainFn = gain
) -> float:
    """DCG@k of a ranking given as tie groups, most risky group first.

    Files in one group are tied. The score is the expectation over every ordering of each
    group, which has a closed form: each member earns its gain times the mean discount of
    the positions the group spans (positions past k have discount 0). Within a group the
    result does not depend on member order, so no path-name tie-break exists.

    A file named more than once counts once, at its first position; the later slot is kept
    and earns 0. A file absent from `labels` has a Label of 0 and keeps its slot.
    """
    _check_k(k)
    seen: set[str] = set()
    position = 1
    total = 0.0
    for group in groups:
        size = len(group)
        if size == 0:
            continue
        group_gain = 0.0
        for path in group:
            if path not in seen:
                seen.add(path)
                group_gain += gain_fn(labels.counts.get(path, 0))
        last = min(position + size - 1, k)
        slot_discounts = math.fsum(discount(p) for p in range(position, last + 1))
        total += group_gain * slot_discounts / size
        position += size
        if position > k:
            break
    return total


def ideal_dcg_at_k(labels: Labels, k: int, gain_fn: GainFn = gain) -> float:
    """DCG@k of the best possible ranking: gains sorted from largest to smallest."""
    _check_k(k)
    gains = sorted((gain_fn(label) for label in labels.counts.values()), reverse=True)[:k]
    return math.fsum(g * discount(i) for i, g in enumerate(gains, start=1))


def ndcg_at_k(
    groups: Sequence[Collection[str]], labels: Labels, k: int, gain_fn: GainFn = gain
) -> float:
    """nDCG@k of a ranking given as tie groups; 0.0 when the ideal DCG is 0.

    `gain_fn` defaults to the damped primary gain; pass `binary_gain` or `raw_gain` for the
    sensitivity checks.
    """
    ideal = ideal_dcg_at_k(labels, k, gain_fn)
    if ideal == 0.0:
        return 0.0
    return dcg_at_k(groups, labels, k, gain_fn) / ideal


def ndcg_at_k_strict(paths: Sequence[str], labels: Labels, k: int, gain_fn: GainFn = gain) -> float:
    """nDCG@k of a strictly ordered ranking (no ties), most risky first."""
    return ndcg_at_k([[path] for path in paths], labels, k, gain_fn)


def precision_at_k(groups: Sequence[Collection[str]], labels: Labels, k: int) -> float:
    """Return the expected share of the first k slots held by a file with a Label above 0.

    Ties and repeated files follow the rules of `dcg_at_k`. The denominator is always k, so a
    ranking shorter than k leaves its empty slots at 0.
    """
    _check_k(k)
    seen: set[str] = set()
    position = 1
    hits = 0.0
    for group in groups:
        size = len(group)
        if size == 0:
            continue
        relevant = 0
        for path in group:
            if path not in seen:
                seen.add(path)
                relevant += labels.counts.get(path, 0) > 0
        slots_in_k = min(position + size - 1, k) - position + 1
        hits += relevant * slots_in_k / size
        position += size
        if position > k:
            break
    return hits / k


def spearman(groups: Sequence[Collection[str]], labels: Labels) -> float | None:
    """Spearman correlation between rank and Label, for a full ordering only.

    A full ordering names every path in `labels.counts` exactly once and nothing else; ties are
    allowed and take the mean of the positions they span. Returns None for any other ranking,
    and when either side is constant, since the correlation is then undefined.
    """
    paths = [path for group in groups for path in group]
    if len(paths) != len(set(paths)) or set(paths) != set(labels.counts):
        return None
    xs: list[float] = []
    ys: list[float] = []
    position = 1
    for group in groups:
        size = len(group)
        mean_position = position + (size - 1) / 2
        for path in group:
            xs.append(-mean_position)  # earlier means riskier
            ys.append(float(labels.counts[path]))
        position += size
    try:
        return statistics.correlation(xs, ys, method="ranked")
    except statistics.StatisticsError:
        return None


class _TooBigError(Exception):
    """An exact tie-group enumeration would be too large; fall back to sampling."""


def recall_at_budget(
    groups: Sequence[Collection[str]],
    labels: Labels,
    effort: Mapping[str, int],
    fraction: Fraction = LOC_BUDGET,
) -> float:
    """Share of all Label mass found within `fraction` of the total effort (ADR 0018).

    `effort` maps a path to its cost: physical LOC for the co-primary metric, cyclomatic
    complexity for the sensitivity check. The budget is `fraction` of the sum over `effort`.
    Walk the ranking, take a file that fits, skip one that would overflow and continue; unused
    budget finds nothing. A file absent from `effort` costs nothing and finds nothing, and a
    file named again after its first occurrence is ignored. The score is the Label mass of the
    taken files over the Label mass of every file in `labels`, 0.0 when that is 0.

    Tie groups are averaged over all orderings. That is exact when every group that matters is
    small; otherwise it is a fixed-seed sample, still a pure function of the tie sets.
    """
    if not 0 < fraction <= 1:
        msg = f"fraction must be in (0, 1], got {fraction}"
        raise ValueError(msg)
    total_label = sum(labels.counts.values())
    if total_label == 0:
        return 0.0
    budget = sum(effort.values()) * fraction.numerator // fraction.denominator
    seen: set[str] = set()
    items: list[list[_Item]] = []
    for group in groups:
        members = sorted(path for path in set(group) if path not in seen and path in effort)
        seen.update(group)
        if members:
            items.append([(p, effort[p], labels.counts.get(p, 0)) for p in members])
    try:
        found = _exact_found(items, budget)
    except _TooBigError:
        found = _sampled_found(items, budget)
    return found / total_label


def _exact_found(items: Sequence[Sequence[_Item]], budget: int) -> float:
    """Return the expected Label mass found, carrying leftover-budget odds between groups."""
    states = {budget: 1.0}
    expected = 0.0
    for members in items:
        next_states: dict[int, float] = {}
        for remaining, probability in states.items():
            for used, found, weight in _group_outcomes(members, remaining):
                expected += probability * weight * found
                key = remaining - used
                next_states[key] = next_states.get(key, 0.0) + probability * weight
        if len(next_states) > _EXACT_STATE_LIMIT:
            raise _TooBigError
        states = next_states
    return expected


def _group_outcomes(members: Sequence[_Item], remaining: int) -> list[tuple[int, int, float]]:
    """Distribution of (effort used, Label found) for one tie group walked in random order."""
    fitting = [(cost, label) for _, cost, label in members if cost <= remaining]
    if not fitting:
        return [(0, 0, 1.0)]
    if sum(cost for cost, _ in fitting) <= remaining:
        return [(sum(c for c, _ in fitting), sum(lab for _, lab in fitting), 1.0)]
    if len(fitting) > _EXACT_GROUP_LIMIT:
        raise _TooBigError
    # Picking the next file uniformly among those that still fit equals walking a uniformly
    # random permutation, because a file that does not fit now never fits later.
    n = len(fitting)
    reach: dict[int, float] = {0: 1.0}
    outcomes: dict[tuple[int, int], float] = {}
    for mask in range(1 << n):
        probability = reach.get(mask, 0.0)
        if probability == 0.0:
            continue
        taken = [i for i in range(n) if mask >> i & 1]
        used = sum(fitting[i][0] for i in taken)
        options = [i for i in range(n) if not mask >> i & 1 and used + fitting[i][0] <= remaining]
        if not options:
            key = (used, sum(fitting[i][1] for i in taken))
            outcomes[key] = outcomes.get(key, 0.0) + probability
            continue
        for i in options:
            reach[mask | 1 << i] = reach.get(mask | 1 << i, 0.0) + probability / len(options)
    return [(used, found, p) for (used, found), p in outcomes.items()]


def _sampled_found(items: Sequence[Sequence[_Item]], budget: int) -> float:
    """Mean Label mass over fixed-seed random orderings of every tie group."""
    rng = random.Random(_SEED)  # noqa: S311  # a reproducible sample, not a secret
    cheapest_from = [sys.maxsize] * (len(items) + 1)
    for i in range(len(items) - 1, -1, -1):
        cheapest_from[i] = min(*(cost for _, cost, _ in items[i]), cheapest_from[i + 1])
    total = 0
    for _ in range(_SAMPLES):
        remaining = budget
        for i, members in enumerate(items):
            if remaining < cheapest_from[i]:
                break
            order = list(members)
            rng.shuffle(order)
            for _, cost, label in order:
                if cost <= remaining:
                    remaining -= cost
                    total += label
    return total / _SAMPLES


def score_ranking(
    groups: Sequence[Collection[str]],
    labels: Labels,
    loc: Mapping[str, int],
    complexity: Mapping[str, int] | None = None,
) -> Scores:
    """Every metric ADR 0005 names for one ranking, keyed by metric name.

    The primary nDCG@20 and the co-primary recall come first; the rest are reported only. The
    `spearman` key is present only for a full ordering. Cyclomatic-complexity recall needs a
    second effort map, so it is scored only when `complexity` is given. Each Label variant
    (keyword-only, window and cap) adds an `ndcg@20[<name>]` key, scored against that count set.
    """
    metrics: dict[str, float] = {
        f"ndcg@{PRIMARY_K}": ndcg_at_k(groups, labels, PRIMARY_K),
        "recall@20%loc": recall_at_budget(groups, labels, loc),
    }
    for k in (*REPORTED_KS, PRIMARY_K):
        metrics[f"precision@{k}"] = precision_at_k(groups, labels, k)
    for k in REPORTED_KS:
        metrics[f"ndcg@{k}"] = ndcg_at_k(groups, labels, k)
    metrics[f"ndcg@{PRIMARY_K}:binary"] = ndcg_at_k(groups, labels, PRIMARY_K, binary_gain)
    metrics[f"ndcg@{PRIMARY_K}:raw"] = ndcg_at_k(groups, labels, PRIMARY_K, raw_gain)
    if complexity is not None:
        metrics[f"recall@20%{COMPLEXITY_SUFFIX}"] = recall_at_budget(groups, labels, complexity)
    variants = {"keyword": labels.keyword_counts, **labels.variants}
    for name, counts in variants.items():
        metrics[f"ndcg@{PRIMARY_K}[{name}]"] = ndcg_at_k(
            groups, replace(labels, counts=counts), PRIMARY_K
        )
    rho = spearman(groups, labels)
    if rho is not None:
        metrics["spearman"] = rho
    return Scores(metrics=metrics)
