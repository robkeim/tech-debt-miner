"""Property-based tests for Cutoff date and window handling (CONTRIBUTING, Testing)."""

from datetime import date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tech_debt_miner.labels import window_end, window_is_closed
from tech_debt_miner.labels import window_start as label_window_start
from tech_debt_miner.repo.churn import CHURN_WINDOW_MONTHS
from tech_debt_miner.repo.churn import window_start as churn_window_start
from tech_debt_miner.repo.cutoff import commits_in_range, midnight_utc, pick_pinned_sha
from tech_debt_miner.repo.history import CommitChange, GitError, LogEntry

pytestmark = pytest.mark.unit

DAYS = st.dates(min_value=date(1971, 1, 1), max_value=date(2100, 12, 31))
EPOCH_NEAR = st.integers(min_value=-3 * 86_400, max_value=3 * 86_400)


def _commit(index: int, committed_at: datetime) -> CommitChange:
    return CommitChange(f"c{index}", committed_at, ())


@st.composite
def _commits(draw: st.DrawFn, around: date) -> list[CommitChange]:
    base = midnight_utc(around)
    offsets = draw(st.lists(EPOCH_NEAR, max_size=12))
    return [_commit(i, base + timedelta(seconds=offset)) for i, offset in enumerate(offsets)]


@given(DAYS, st.integers(0, 40), st.integers(0, 40), st.data())
def test_range_keeps_exactly_the_commits_in_the_half_open_window(
    since: date, width: int, extra: int, data: st.DataObject
) -> None:
    until = since + timedelta(days=width)
    commits = data.draw(_commits(since + timedelta(days=width // 2)))
    kept = commits_in_range(commits, since, until)
    inside = [c for c in commits if midnight_utc(since) <= c.committed_at < midnight_utc(until)]
    assert kept == inside  # same members, same order
    wider = commits_in_range(commits, since, until + timedelta(days=extra))
    assert all(c in wider for c in kept)  # a later `until` never drops a commit


@given(DAYS, st.data())
def test_range_never_returns_a_commit_on_or_after_until(cutoff: date, data: st.DataObject) -> None:
    commits = data.draw(_commits(cutoff))
    kept = commits_in_range(commits, cutoff - timedelta(days=400), cutoff)
    assert all(c.committed_at < midnight_utc(cutoff) for c in kept)


@st.composite
def _graphs(draw: st.DrawFn, around: date) -> list[LogEntry]:
    """Draw a DAG in `git log` order: every parent comes after its children."""
    base = int(midnight_utc(around).timestamp())
    size = draw(st.integers(0, 8))
    entries: list[LogEntry] = []
    for i in range(size):
        later = [f"c{j}" for j in range(i + 1, size)]
        parents = draw(st.lists(st.sampled_from(later), unique=True, max_size=2)) if later else []
        entries.append(LogEntry(f"c{i}", base + draw(EPOCH_NEAR), tuple(parents)))
    return entries


def _qualifies(entry: LogEntry, by_sha: dict[str, LogEntry], limit: float) -> bool:
    seen: set[str] = set()
    stack = [entry.sha]
    while stack:
        sha = stack.pop()
        if sha in seen:
            continue
        seen.add(sha)
        if by_sha[sha].committed >= limit:
            return False
        stack.extend(by_sha[sha].parents)
    return True


@given(DAYS, st.data())
def test_pinned_sha_is_the_newest_first_parent_commit_with_only_earlier_history(
    cutoff: date, data: st.DataObject
) -> None:
    entries = data.draw(_graphs(cutoff))
    limit = midnight_utc(cutoff).timestamp()
    by_sha = {e.sha: e for e in entries}
    line: list[LogEntry] = []
    current = entries[0] if entries else None
    while current is not None:
        line.append(current)
        current = by_sha.get(current.parents[0]) if current.parents else None
    expected = next((e.sha for e in line if _qualifies(e, by_sha, limit)), None)
    if expected is None:
        with pytest.raises(GitError):
            pick_pinned_sha(entries, cutoff)
    else:
        assert pick_pinned_sha(entries, cutoff) == expected


@given(DAYS, st.data())
def test_pinned_sha_never_sees_a_post_cutoff_commit(cutoff: date, data: st.DataObject) -> None:
    entries = data.draw(_graphs(cutoff))
    try:
        sha = pick_pinned_sha(entries, cutoff)
    except GitError:
        return
    by_sha = {e.sha: e for e in entries}
    assert _qualifies(by_sha[sha], by_sha, midnight_utc(cutoff).timestamp())


@given(DAYS)
def test_churn_window_starts_twelve_months_back_clamped_to_month_end(cutoff: date) -> None:
    start = churn_window_start(cutoff)
    assert start < cutoff
    months = (cutoff.year - start.year) * 12 + cutoff.month - start.month
    assert months == CHURN_WINDOW_MONTHS
    assert start.day <= cutoff.day
    assert start.day == cutoff.day or (start + timedelta(days=1)).month != start.month


@given(DAYS)
def test_label_window_runs_from_the_day_after_the_cutoff_to_six_months_on(cutoff: date) -> None:
    assert label_window_start(cutoff) == cutoff + timedelta(days=1)
    end = window_end(cutoff)
    assert end > cutoff
    assert 181 <= (end - cutoff).days <= 184
    assert end.day <= cutoff.day


@given(DAYS, DAYS, st.integers(0, 400))
def test_window_closes_once_and_stays_closed(cutoff: date, today: date, later: int) -> None:
    if window_is_closed(cutoff, today):
        assert window_is_closed(cutoff, today + timedelta(days=later))
    assert not window_is_closed(cutoff, cutoff)
