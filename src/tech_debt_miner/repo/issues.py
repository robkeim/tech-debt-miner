"""Issues as of the Cutoff date, with edit-history exclusion (ADR 0008). Nothing here does I/O.

GitHub gives only an issue's current title and body. The body is rebuilt as "never edited": an
issue is kept only when its edit history is complete and shows no edit on or after the Cutoff
date, because a later edit such as "root cause was `parse.py`" would leak the answer. The title is
rebuilt from the rename events. `repo/github.py` fetches the raw data behind `IssueSource`.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from tech_debt_miner.repo.cutoff import midnight_utc
from tech_debt_miner.types import Issue


@dataclass(frozen=True)
class Rename:
    """A title change: when it happened and the title before it."""

    at: datetime
    previous_title: str


@dataclass(frozen=True)
class RawIssue:
    """An issue as the tracker reports it today, with the history needed to rebuild it."""

    number: int
    title: str  # the current title
    body: str  # the current body
    created_at: datetime
    last_edited_at: datetime | None  # None when the body was never edited
    edit_times: tuple[datetime, ...]  # the fetched edit-history entries
    edit_count: int  # how many entries the tracker holds; more than `edit_times` if truncated
    renames: tuple[Rename, ...]
    rename_count: int  # how many rename events the tracker holds


# `(owner/name, cutoff)` -> every issue created before the Cutoff date, with its history.
IssueSource = Callable[[str, date], Sequence[RawIssue]]


def build_issues(raw: Sequence[RawIssue], cutoff: date) -> tuple[tuple[Issue, ...], int]:
    """Return the issues as of the Cutoff date, and how many were excluded.

    Issues created on or after the Cutoff date are dropped without being counted: they do not
    exist yet. An existing issue is excluded when it cannot be proven clean: its body was edited
    on or after the Cutoff date, its edit history is incomplete, or its rename history is.
    """
    limit = midnight_utc(cutoff)
    kept: list[Issue] = []
    excluded = 0
    for issue in sorted(raw, key=lambda item: item.number):
        if issue.created_at >= limit:
            continue
        if not _is_clean(issue, limit):
            excluded += 1
            continue
        kept.append(Issue(issue.number, _title_at(issue, limit), issue.body))
    return tuple(kept), excluded


def _is_clean(issue: RawIssue, limit: datetime) -> bool:
    if issue.last_edited_at is not None and issue.last_edited_at >= limit:
        return False
    if len(issue.edit_times) < issue.edit_count or len(issue.renames) < issue.rename_count:
        return False
    return all(edited < limit for edited in issue.edit_times)


def _title_at(issue: RawIssue, limit: datetime) -> str:
    """Return the title before the first rename on or after the Cutoff date, else the current."""
    later = [rename for rename in issue.renames if rename.at >= limit]
    return min(later, key=lambda rename: rename.at).previous_title if later else issue.title
