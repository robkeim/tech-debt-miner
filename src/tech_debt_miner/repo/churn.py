"""Churn: commits touching a file in the Churn window, merges excluded, renames followed (ADR 0007).

Pure functions over the commits `git.list_commits` returns, so nothing here touches a repo.
"""

import calendar
from collections.abc import Collection, Sequence
from datetime import UTC, date

from tech_debt_miner.repo.git import CommitChange
from tech_debt_miner.types import CommitSubject

CHURN_WINDOW_MONTHS = 12
MAX_SUBJECTS = 5


def window_start(cutoff: date) -> date:
    """Return the first day of the Churn window: `CHURN_WINDOW_MONTHS` before the Cutoff date.

    The day is clamped to the month's length, so 12 months before 2024-02-29 is 2023-02-28.
    """
    month_index = cutoff.year * 12 + cutoff.month - 1 - CHURN_WINDOW_MONTHS
    year, month = divmod(month_index, 12)
    month += 1
    day = min(cutoff.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def commits_by_file(
    commits: Sequence[CommitChange], paths: Collection[str]
) -> dict[str, list[CommitChange]]:
    """Group the commits by the file they touch, newest first.

    `paths` are the file names at the Cutoff date.

    `commits` must be newest first and non-merge, as `git.list_commits` returns them. Walking
    back in time, a rename maps the file's older name onto its name at the Cutoff date, so
    commits before the rename still belong to the file.
    """
    grouped: dict[str, list[CommitChange]] = {path: [] for path in paths}
    current_name = {path: path for path in paths}
    for commit in commits:
        for change in commit.files:
            final = current_name.get(change.path)
            if final is None:
                continue
            grouped[final].append(commit)
            if change.old_path is not None:
                del current_name[change.path]
                current_name[change.old_path] = final
    return grouped


def recent_subjects(commits: Sequence[CommitChange]) -> tuple[CommitSubject, ...]:
    """Tag the newest `MAX_SUBJECTS` commits with their committer date in UTC (ADR 0010).

    Nothing else about a commit is kept: no author, hash, diff or count.
    """
    return tuple(
        CommitSubject(commit.committed_at.astimezone(UTC).date().isoformat(), commit.subject)
        for commit in commits[:MAX_SUBJECTS]
    )
