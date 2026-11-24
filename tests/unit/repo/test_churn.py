from datetime import UTC, date, datetime

import pytest

from tech_debt_miner.repo.churn import count_churn, window_start
from tech_debt_miner.repo.git import CommitChange, FileChange

pytestmark = pytest.mark.unit

WHEN = datetime(2023, 6, 1, tzinfo=UTC)


def commit(*changes: FileChange) -> CommitChange:
    return CommitChange("sha", WHEN, changes)


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
