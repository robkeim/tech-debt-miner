from datetime import UTC, date, datetime, timedelta

import pytest

from tech_debt_miner import labels
from tech_debt_miner.repo.git import CommitChange, FileChange

pytestmark = pytest.mark.unit

START = datetime(2024, 2, 1, tzinfo=UTC)


def commit(
    message: str,
    *files: FileChange | str,
    day: int = 0,
    name: str = "Dev",
    email: str = "dev@example.com",
) -> CommitChange:
    changes = tuple(f if isinstance(f, FileChange) else FileChange(f) for f in files)
    return CommitChange(
        sha=f"sha-{message}-{day}",
        committed_at=START + timedelta(days=day),
        files=changes,
        author_name=name,
        author_email=email,
        message=message,
    )


def counts(
    commits: list[CommitChange], files: list[str], max_files: int | None = None
) -> dict[str, int]:
    return dict(labels.build_labels(commits, files, max_files).counts)


@pytest.mark.parametrize(
    "message",
    ["fix crash", "Fixes the parser", "fixed it", "Bug in loop", "defect report", "apply patch"],
)
def test_keyword_matches_whole_words_ignoring_case(message: str) -> None:
    assert labels.is_keyword_fix(commit(message))


@pytest.mark.parametrize(
    "message", ["prefix", "bugs everywhere", "debugger", "patching", "add feature", "fixture"]
)
def test_keyword_needs_a_word_boundary(message: str) -> None:
    assert not labels.is_keyword_fix(commit(message))


@pytest.mark.parametrize(
    "message",
    [
        "fix and refactor",
        "fix cleanup",
        "fix: renamed var",
        "fix merge conflict",
        "bump to fix",
        'Revert "fix x"',
        "fix\n\nlong body mentions Refactoring",
    ],
)
def test_excluded_messages_are_not_fix_commits(message: str) -> None:
    assert not labels.is_keyword_fix(commit(message))


def test_bot_authors_are_not_fix_commits() -> None:
    assert not labels.is_keyword_fix(commit("fix deps", name="dependabot[bot]"))
    assert not labels.is_keyword_fix(
        commit("fix deps", email="49699333+dependabot[bot]@users.noreply.github.com")
    )
    assert not labels.is_keyword_fix(commit("fix deps", name="Renovate"))
    assert not labels.is_keyword_fix(commit("fix deps", name="release-bot"))
    assert labels.is_keyword_fix(commit("fix deps", name="Abbott"))


def test_a_commit_counts_once_per_file() -> None:
    commits = [commit("fix a", "a.py", "a.py"), commit("fix again", "a.py", day=1)]
    assert counts(commits, ["a.py", "b.py"]) == {"a.py": 2, "b.py": 0}


def test_non_fix_commits_do_not_count() -> None:
    assert counts([commit("add feature", "a.py")], ["a.py"]) == {"a.py": 0}


def test_only_eligible_cutoff_files_are_counted() -> None:
    commits = [commit("fix", "a.py", "tests/test_a.py", "README.md")]
    assert counts(commits, ["a.py", "tests/test_a.py", "README.md"]) == {"a.py": 1}


def test_renames_map_back_to_the_cutoff_path() -> None:
    commits = [
        commit("fix one", "a.py", day=0),
        commit("move", FileChange("b.py", "a.py"), day=1),
        commit("fix two", "b.py", day=2),
        commit("move again", FileChange("c.py", "b.py"), day=3),
        commit("fix three", FileChange("c.py"), day=4),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 3}


def test_a_fix_that_renames_counts_for_the_old_file() -> None:
    commits = [commit("fix and move", FileChange("b.py", "a.py"))]
    assert counts(commits, ["a.py"]) == {"a.py": 1}


def test_deleted_files_keep_their_label() -> None:
    commits = [
        commit("fix a", "a.py", day=0),
        commit("fix by delete", FileChange("a.py", deleted=True), day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 2}


def test_files_created_later_are_ignored_even_after_renames() -> None:
    commits = [
        commit("fix new", "new.py", day=0),
        commit("fix moved", FileChange("newer.py", "new.py"), day=1),
        commit("fix newer", "newer.py", day=2),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 0}


def test_a_path_recreated_after_deletion_is_a_new_file() -> None:
    commits = [
        commit("drop", FileChange("a.py", deleted=True), day=0),
        commit("fix recreated", "a.py", day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 0}


def test_commit_order_in_the_input_does_not_matter() -> None:
    commits = [
        commit("fix two", "b.py", day=2),
        commit("move", FileChange("b.py", "a.py"), day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 1}


def test_fix_size_cap_drops_large_fixes() -> None:
    commits = [commit("fix wide", "a.py", "b.py", "c.py"), commit("fix narrow", "a.py", day=1)]
    capped = labels.build_labels(commits, ["a.py", "b.py", "c.py"], max_files=2)
    assert dict(capped.counts) == {"a.py": 1, "b.py": 0, "c.py": 0}
    assert capped.stats["fix_commits_dropped_by_cap"] == 1
    uncapped = labels.build_labels(commits, ["a.py", "b.py", "c.py"])
    assert dict(uncapped.counts) == {"a.py": 2, "b.py": 1, "c.py": 1}
    assert uncapped.stats["fix_commits_dropped_by_cap"] == 0


def test_fix_size_cap_counts_eligible_files_only() -> None:
    commits = [commit("fix", "a.py", "tests/test_a.py", "docs/x.py", "notes.md")]
    assert counts(commits, ["a.py"], max_files=1) == {"a.py": 1}


def test_renames_still_apply_when_a_commit_is_dropped_by_the_cap() -> None:
    commits = [
        commit("fix wide", FileChange("b.py", "a.py"), "c.py", day=0),
        commit("fix b", "b.py", day=1),
    ]
    assert counts(commits, ["a.py", "c.py"], max_files=1) == {"a.py": 1, "c.py": 0}


def test_stats_report_squash_and_pr_number_only_shares() -> None:
    commits = [
        commit("fix crash (#12)"),
        commit("fix parser (#13)\n\nCloses #4"),
        commit("fix loop"),
        commit("add feature (#14)"),
    ]
    stats = labels.build_labels(commits, []).stats
    assert stats["commits_in_window"] == 4
    assert stats["squash_share"] == 0.75
    assert stats["fix_commits"] == 3
    assert stats["pr_number_only_share"] == pytest.approx(1 / 3)


def test_stats_are_zero_without_commits() -> None:
    stats = labels.build_labels([], []).stats
    assert stats["squash_share"] == 0.0
    assert stats["pr_number_only_share"] == 0.0


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("fix it (#7)", True),
        ("fix it (#7) ", True),
        ("fix it", False),
        ("fix #3 (#7)", False),
        ("fix it (#7)\n\nsee https://github.com/o/r/issues/3", False),
        ("fix it (#7)\n\nbody without references", True),
    ],
)
def test_carries_only_pr_number(message: str, expected: bool) -> None:  # noqa: FBT001
    assert labels.carries_only_pr_number(commit(message)) is expected


@pytest.mark.parametrize(
    ("cutoff", "end"),
    [
        (date(2025, 1, 31), date(2025, 7, 31)),
        (date(2025, 8, 31), date(2026, 2, 28)),
        (date(2023, 8, 31), date(2024, 2, 29)),
        (date(2024, 6, 15), date(2024, 12, 15)),
    ],
)
def test_window_end_adds_six_months_clamped_to_month_end(cutoff: date, end: date) -> None:
    assert labels.window_end(cutoff) == end


def test_window_starts_the_day_after_the_cutoff_and_closes_after_its_last_day() -> None:
    cutoff = date(2024, 1, 31)
    assert labels.window_start(cutoff) == date(2024, 2, 1)
    assert not labels.window_is_closed(cutoff, date(2024, 7, 31))
    assert labels.window_is_closed(cutoff, date(2024, 8, 1))
