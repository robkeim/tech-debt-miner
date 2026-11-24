"""The `Ranker` protocol (ADR 0010)."""

from typing import Protocol

from tech_debt_miner.types import Ranking, Snapshot


class Ranker(Protocol):
    """Orders a Snapshot's files, most risky first.

    Takes only a `Snapshot`, never a repo path or git handle, so a ranker cannot see past the
    Cutoff date. The Baseline ignores `repeat`.
    """

    def rank(self, snapshot: Snapshot, *, repeat: int) -> Ranking: ...
