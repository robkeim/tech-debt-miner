"""Replay: re-score a Run from its logged responses, with no client and no repo (ADR 0001)."""

from collections.abc import Callable

from tech_debt_miner.run import store
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import LoggedResponse, Ranking


def logged_responses(run_dir: RunDir) -> list[LoggedResponse]:
    """Every row of `responses.jsonl`, in log order. Reads the Run directory only."""
    return [store.logged_response_from_json(row) for row in run_dir.read_responses()]


def final_responses(run_dir: RunDir) -> dict[tuple[str, int], LoggedResponse]:
    """Return the reply that counts for each (ranker, repeat): its highest attempt.

    A row logged twice for the same attempt (a resume copies cache hits in again) is the same
    reply, so the later one wins.
    """
    final: dict[tuple[str, int], LoggedResponse] = {}
    for row in logged_responses(run_dir):
        current = final.get((row.ranker, row.repeat))
        if current is None or row.attempt >= current.attempt:
            final[row.ranker, row.repeat] = row
    return final


def replay_rankings(run_dir: RunDir, parse: Callable[[str], tuple[str, ...]]) -> list[Ranking]:
    """Rebuild every logged ranking by parsing its final reply.

    `parse` raises `ValueError` on unparsable text, which propagates: a repeat that cannot be
    parsed is never replayed as an empty ranking (ADR 0008).
    """
    return [
        Ranking(ranker=ranker, repeat=repeat, paths=parse(row.response.text))
        for (ranker, repeat), row in sorted(final_responses(run_dir).items())
    ]
