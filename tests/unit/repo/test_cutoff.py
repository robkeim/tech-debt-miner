from datetime import UTC, date, datetime

import pytest

from tech_debt_miner.repo.cutoff import commits_in_range, pick_pinned_sha
from tech_debt_miner.repo.history import (
    CommitChange,
    GitError,
    LogEntry,
    parse_commit_log,
    parse_graph_log,
)

pytestmark = pytest.mark.unit

CUTOFF = date(2024, 1, 1)
BEFORE = int(datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC).timestamp())
AT = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())


def test_commit_at_midnight_is_not_before_the_cutoff() -> None:
    entries = [LogEntry("b", AT, ("a",)), LogEntry("a", BEFORE, ())]
    assert pick_pinned_sha(entries, CUTOFF) == "a"


def test_steps_back_over_clock_skew() -> None:
    entries = [LogEntry("c", BEFORE, ("b",)), LogEntry("b", AT, ("a",)), LogEntry("a", BEFORE, ())]
    assert pick_pinned_sha(entries, CUTOFF) == "a"


def test_late_dated_merged_side_branch_disqualifies_the_merge() -> None:
    entries = [
        LogEntry("m", BEFORE, ("a", "s")),
        LogEntry("s", AT, ("a",)),
        LogEntry("a", BEFORE, ()),
    ]
    assert pick_pinned_sha(entries, CUTOFF) == "a"


def test_fails_when_every_candidate_has_late_ancestry() -> None:
    entries = [LogEntry("b", BEFORE, ("a",)), LogEntry("a", AT, ())]
    with pytest.raises(GitError, match="only earlier history"):
        pick_pinned_sha(entries, CUTOFF)


def test_fails_on_empty_history() -> None:
    with pytest.raises(GitError, match="no commit before 2024-01-01"):
        pick_pinned_sha([], CUTOFF)


def test_range_is_start_inclusive_end_exclusive() -> None:
    def commit(sha: str, stamp: int) -> CommitChange:
        return CommitChange(sha, datetime.fromtimestamp(stamp, UTC), ())

    commits = [commit("late", AT), commit("edge", AT - 1), commit("early", AT - 2)]
    kept = commits_in_range(commits, date(2023, 12, 31), CUTOFF)
    assert [c.sha for c in kept] == ["edge", "early"]
    assert commits_in_range(commits, CUTOFF, date(2024, 1, 2)) == [commits[0]]


def test_parse_graph_log_reads_parents() -> None:
    assert parse_graph_log("m 5 a s\na 4\n") == [LogEntry("m", 5, ("a", "s")), LogEntry("a", 4, ())]


def test_parse_commit_log_reads_renames() -> None:
    out = "\0c1 100\n\nM\tx.py\n\0c2 50\n\nR100\told.py\tnew.py\n"
    first, second = parse_commit_log(out)
    assert first.files[0].path == "x.py"
    assert (second.files[0].path, second.files[0].old_path) == ("new.py", "old.py")
