"""Scoring: nDCG@k with damped gain and tie averaging (ADR 0005). Pure functions."""

import math
from collections.abc import Collection, Sequence

from tech_debt_miner.types import Labels


def gain(label: int) -> float:
    """Damped gain: `1 + log2(label)`, and 0 for a Label of 0."""
    if label < 0:
        msg = f"label must be non-negative, got {label}"
        raise ValueError(msg)
    return 0.0 if label == 0 else 1.0 + math.log2(label)


def discount(position: int) -> float:
    """Discount for a 1-based position: `1 / log2(position + 1)`."""
    if position < 1:
        msg = f"position must be at least 1, got {position}"
        raise ValueError(msg)
    return 1.0 / math.log2(position + 1)


def dcg_at_k(groups: Sequence[Collection[str]], labels: Labels, k: int) -> float:
    """DCG@k of a ranking given as tie groups, most risky group first.

    Files in one group are tied. The score is the expectation over every ordering of each
    group, which has a closed form: each member earns its gain times the mean discount of
    the positions the group spans (positions past k have discount 0). Within a group the
    result does not depend on member order, so no path-name tie-break exists.

    A file named more than once counts once, at its first position; the later slot is kept
    and earns 0. A file absent from `labels` has a Label of 0 and keeps its slot.
    """
    if k < 1:
        msg = f"k must be at least 1, got {k}"
        raise ValueError(msg)
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
                group_gain += gain(labels.counts.get(path, 0))
        last = min(position + size - 1, k)
        slot_discounts = math.fsum(discount(p) for p in range(position, last + 1))
        total += group_gain * slot_discounts / size
        position += size
        if position > k:
            break
    return total


def ideal_dcg_at_k(labels: Labels, k: int) -> float:
    """DCG@k of the best possible ranking: gains sorted from largest to smallest."""
    if k < 1:
        msg = f"k must be at least 1, got {k}"
        raise ValueError(msg)
    gains = sorted((gain(label) for label in labels.counts.values()), reverse=True)[:k]
    return math.fsum(g * discount(i) for i, g in enumerate(gains, start=1))


def ndcg_at_k(groups: Sequence[Collection[str]], labels: Labels, k: int) -> float:
    """nDCG@k of a ranking given as tie groups; 0.0 when no file has a Label above 0."""
    ideal = ideal_dcg_at_k(labels, k)
    if ideal == 0.0:
        return 0.0
    return dcg_at_k(groups, labels, k) / ideal


def ndcg_at_k_strict(paths: Sequence[str], labels: Labels, k: int) -> float:
    """nDCG@k of a strictly ordered ranking (no ties), most risky first."""
    return ndcg_at_k([[path] for path in paths], labels, k)
