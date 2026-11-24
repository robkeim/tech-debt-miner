"""Churn: commits touching a file in the Churn window, merges excluded, renames followed (ADR 0007).

Pure functions over the commits `git.list_commits` returns, so nothing here touches a repo.
"""

import calendar
from collections.abc import Collection, Sequence
from datetime import date

from tech_debt_miner.repo.git import CommitChange

CHURN_WINDOW_MONTHS = 12


def window_start(cutoff: date) -> date:
    """Return the first day of the Churn window: `CHURN_WINDOW_MONTHS` before the Cutoff date.

    The day is clamped to the month's length, so 12 months before 2024-02-29 is 2023-02-28.
    """
    month_index = cutoff.year * 12 + cutoff.month - 1 - CHURN_WINDOW_MONTHS
    year, month = divmod(month_index, 12)
    month += 1
    day = min(cutoff.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def count_churn(commits: Sequence[CommitChange], paths: Collection[str]) -> dict[str, int]:
    """Count the commits touching each of `paths`, which are the file names at the Cutoff date.

    `commits` must be newest first and non-merge, as `git.list_commits` returns them. Walking
    back in time, a rename maps the file's older name onto its name at the Cutoff date, so
    commits before the rename still count for the file.
    """
    counts = dict.fromkeys(paths, 0)
    current_name = {path: path for path in paths}
    for commit in commits:
        for change in commit.files:
            final = current_name.get(change.path)
            if final is None:
                continue
            counts[final] += 1
            if change.old_path is not None:
                del current_name[change.path]
                current_name[change.old_path] = final
    return counts
