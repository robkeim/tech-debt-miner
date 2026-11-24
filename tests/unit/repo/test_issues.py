from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from tech_debt_miner.repo.issues import RawIssue, Rename, build_issues
from tech_debt_miner.types import Issue

pytestmark = pytest.mark.unit

CUTOFF = date(2024, 1, 1)
LIMIT = datetime(2024, 1, 1, tzinfo=UTC)
BEFORE = LIMIT - timedelta(days=30)
AFTER = LIMIT + timedelta(days=30)


def raw(number: int = 1, **fields: Any) -> RawIssue:  # noqa: ANN401 - RawIssue field overrides
    """Build a clean issue from before the cutoff; counts follow the histories unless given."""
    edits = fields.get("edit_times", ())
    renames = fields.get("renames", ())
    base = RawIssue(
        number=number,
        title="title",
        body="body",
        created_at=BEFORE,
        last_edited_at=None,
        edit_times=(),
        edit_count=len(edits),
        renames=(),
        rename_count=len(renames),
    )
    return replace(base, **fields)


def test_an_untouched_issue_is_kept_as_it_is() -> None:
    assert build_issues([raw(7, title="t", body="b")], CUTOFF) == ((Issue(7, "t", "b"),), 0)


def test_issues_come_back_in_number_order() -> None:
    issues, _ = build_issues([raw(9), raw(2), raw(5)], CUTOFF)

    assert [issue.number for issue in issues] == [2, 5, 9]


@pytest.mark.parametrize("created", [LIMIT, AFTER])
def test_an_issue_created_on_or_after_the_cutoff_does_not_exist_and_is_not_counted(
    created: datetime,
) -> None:
    assert build_issues([raw(created_at=created)], CUTOFF) == ((), 0)


def test_an_issue_created_just_before_the_cutoff_exists() -> None:
    created = LIMIT - timedelta(seconds=1)

    assert build_issues([raw(created_at=created)], CUTOFF)[1] == 0
    assert len(build_issues([raw(created_at=created)], CUTOFF)[0]) == 1


def test_an_edit_before_the_cutoff_is_harmless() -> None:
    edited = BEFORE + timedelta(days=1)

    assert build_issues([raw(last_edited_at=edited, edit_times=(edited,))], CUTOFF)[1] == 0


@pytest.mark.parametrize("when", [LIMIT, AFTER])
def test_a_body_edit_on_or_after_the_cutoff_excludes_the_issue(when: datetime) -> None:
    issue = raw(last_edited_at=when, edit_times=(BEFORE, when))

    assert build_issues([issue], CUTOFF) == ((), 1)


def test_an_edit_in_the_history_alone_excludes_the_issue() -> None:
    assert build_issues([raw(edit_times=(AFTER,))], CUTOFF) == ((), 1)


def test_a_last_edit_time_alone_excludes_the_issue_even_with_no_history() -> None:
    # The history may have had revisions deleted; the tracker's own last-edit time still counts.
    assert build_issues([raw(last_edited_at=AFTER)], CUTOFF) == ((), 1)


def test_a_truncated_edit_history_cannot_be_proven_clean() -> None:
    assert build_issues([raw(edit_times=(BEFORE,), edit_count=2)], CUTOFF) == ((), 1)


def test_a_truncated_rename_history_cannot_be_proven_clean() -> None:
    assert build_issues([raw(rename_count=1)], CUTOFF) == ((), 1)


def test_the_title_is_the_one_before_the_first_rename_on_or_after_the_cutoff() -> None:
    renames = (
        Rename(AFTER + timedelta(days=5), "middle"),
        Rename(LIMIT, "the title at the cutoff"),
        Rename(AFTER, "middle"),
    )

    issues, _ = build_issues([raw(title="final", renames=renames)], CUTOFF)

    assert issues[0].title == "the title at the cutoff"


def test_a_rename_before_the_cutoff_is_already_in_the_title() -> None:
    renames = (Rename(BEFORE, "older"),)

    issues, _ = build_issues([raw(title="renamed before", renames=renames)], CUTOFF)

    assert issues[0].title == "renamed before"
