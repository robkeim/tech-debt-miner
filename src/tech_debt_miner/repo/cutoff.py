"""Pure Cutoff date rules over parsed git history (ADR 0009). Nothing here runs `git`.

The Cutoff date is midnight UTC and commits are judged by committer time, so a commit dated on or
after the Cutoff date is never returned.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime

from tech_debt_miner.repo.history import CommitChange, GitError, LogEntry


def midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def pick_pinned_sha(entries: Iterable[LogEntry], cutoff: date) -> str:
    """Return the newest first-parent commit before the Cutoff date whose history is all earlier.

    `entries` is the whole graph reachable from `HEAD`, children before parents (the order of
    `git log`). A candidate is committed before the Cutoff date and has no ancestor committed on
    or after it (for example a late-dated side-branch commit that was merged in, or clock skew).
    If a candidate fails that check, step back along the first-parent line to the next earlier
    candidate.
    """
    limit = midnight_utc(cutoff).timestamp()
    ordered = list(entries)
    by_sha = {entry.sha: entry for entry in ordered}
    newest: dict[str, int] = {}
    for entry in reversed(ordered):  # parents first
        newest[entry.sha] = max(
            (newest[parent] for parent in entry.parents if parent in newest),
            default=entry.committed,
        )
        newest[entry.sha] = max(newest[entry.sha], entry.committed)
    current = ordered[0] if ordered else None
    while current is not None:
        if current.committed < limit and newest[current.sha] < limit:
            return current.sha
        current = by_sha.get(current.parents[0]) if current.parents else None
    msg = f"no commit before {cutoff.isoformat()} with only earlier history"
    raise GitError(msg)


def commits_in_range(
    commits: Iterable[CommitChange], since: date, until: date
) -> list[CommitChange]:
    """Keep the commits committed in `[since, until)`, preserving order."""
    start = midnight_utc(since)
    end = midnight_utc(until)
    return [commit for commit in commits if start <= commit.committed_at < end]
