from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tech_debt_miner.repo.churn import commits_by_file, recent_subjects, window_start
from tech_debt_miner.repo.git import CommitChange, FileChange
from tech_debt_miner.types import CommitSubject

pytestmark = pytest.mark.unit

WHEN = datetime(2023, 6, 1, tzinfo=UTC)


def count_churn(commits: list[CommitChange], paths: list[str]) -> dict[str, int]:
    return {path: len(found) for path, found in commits_by_file(commits, paths).items()}


def commit(*changes: FileChange) -> CommitChange:
    return CommitChange("sha", WHEN, changes, message="subject")


@pytest.mark.parametrize(
    ("cutoff", "expected"),
    [
        (date(2024, 1, 1), date(2023, 1, 1)),
        (date(2024, 3, 15), date(2023, 3, 15)),
        (date(2024, 2, 29), date(2023, 2, 28)),
    ],
)
def test_window_starts_twelve_months_before_the_cutoff(cutoff: date, expected: date) -> None:
    assert window_start(cutoff) == expected


def test_counts_commits_per_file_and_zero_for_untouched_files() -> None:
    commits = [
        commit(FileChange("a.py"), FileChange("b.py")),
        commit(FileChange("a.py")),
    ]
    assert count_churn(commits, ["a.py", "b.py", "c.py"]) == {"a.py": 2, "b.py": 1, "c.py": 0}


def test_ignores_files_that_are_not_asked_for() -> None:
    assert count_churn([commit(FileChange("other.py"))], ["a.py"]) == {"a.py": 0}


def test_follows_a_rename_back_to_the_old_name() -> None:
    commits = [  # newest first
        commit(FileChange("new.py")),
        commit(FileChange("new.py", old_path="old.py")),
        commit(FileChange("old.py")),
        commit(FileChange("old.py")),
    ]
    assert count_churn(commits, ["new.py"]) == {"new.py": 4}


def test_follows_a_chain_of_renames() -> None:
    commits = [
        commit(FileChange("c.py", old_path="b.py")),
        commit(FileChange("b.py", old_path="a.py")),
        commit(FileChange("a.py")),
    ]
    assert count_churn(commits, ["c.py"]) == {"c.py": 3}


def test_groups_commits_per_file_newest_first_through_renames() -> None:
    newest = commit(FileChange("new.py"))
    rename = commit(FileChange("new.py", old_path="old.py"))
    oldest = commit(FileChange("old.py"))

    grouped = commits_by_file([newest, rename, oldest], ["new.py", "other.py"])

    assert grouped == {"new.py": [newest, rename, oldest], "other.py": []}


def test_recent_subjects_keep_the_newest_five_tagged_with_the_utc_date() -> None:
    west = timezone(timedelta(hours=-5))
    commits = [
        CommitChange("s", datetime(2023, 6, day, 23, 30, tzinfo=west), (), message=f"c{day}")
        for day in range(7, 0, -1)
    ]

    # 23:30 at UTC-5 is 04:30 UTC on the next day.
    assert recent_subjects(commits) == tuple(
        CommitSubject(f"2023-06-{day + 1:02d}", f"c{day}") for day in range(7, 2, -1)
    )


def test_recent_subjects_of_a_quiet_file_are_all_kept() -> None:
    assert recent_subjects([commit()]) == (CommitSubject("2023-06-01", "subject"),)
    assert recent_subjects([]) == ()
