import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from tech_debt_miner.repo import github
from tech_debt_miner.repo.github import GitHubError, fetch_issues, gh_graphql
from tech_debt_miner.repo.issues import build_issues

pytestmark = pytest.mark.unit

RECORDED = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "github_issues_page.json").read_text(encoding="utf-8")
)  # a trimmed real response for pallets/flask, recorded with `gh api graphql`
Variables = Mapping[str, str | int | None]


class Fake:
    """A GraphQL runner that serves canned pages and records the variables it was sent."""

    def __init__(self, *pages: Mapping[str, Any]) -> None:
        self.pages = list(pages)
        self.sent: list[Variables] = []

    def __call__(self, query: str, variables: Variables) -> Mapping[str, Any]:
        assert "userContentEdits" in query
        self.sent.append(variables)
        return self.pages.pop(0)


def page(nodes: list[Mapping[str, Any]], *, more: bool = False) -> dict[str, Any]:
    info = {"hasNextPage": more, "endCursor": "next" if more else None}
    return {"data": {"repository": {"issues": {"pageInfo": info, "nodes": nodes}}}}


def node(number: int, created: str) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"t{number}",
        "body": None,
        "createdAt": created,
        "lastEditedAt": None,
        "userContentEdits": {"totalCount": 0, "nodes": []},
        "timelineItems": {"totalCount": 0, "nodes": []},
    }


def test_a_recorded_response_parses_into_raw_issues() -> None:
    issues = fetch_issues("pallets/flask", date(2030, 1, 1), Fake(RECORDED))

    assert [issue.number for issue in issues] == [1, 6143, 6160, 6163]
    edited = issues[1]
    assert edited.last_edited_at == datetime(2026, 8, 28, 15, 28, 19, tzinfo=UTC)
    assert (edited.edit_count, len(edited.edit_times)) == (2, 2)
    renamed = issues[2]
    assert renamed.renames[0].previous_title == "bot tok test"
    assert renamed.rename_count == 1


def test_a_recorded_response_rebuilds_issue_state_as_of_a_cutoff() -> None:
    cutoff = date(2026, 9, 14)
    raw = fetch_issues("pallets/flask", cutoff, Fake(RECORDED))

    issues, excluded = build_issues(raw, cutoff)

    # #6143 was edited before the cutoff and #6160 renamed before it; #6163 does not exist yet.
    assert [(issue.number, issue.title) for issue in issues][-2:] == [
        (6143, "`add_url_rule` leaves a route registered even after an endpoint conflict"),
        (6160, "spam"),
    ]
    assert excluded == 0


def test_issues_created_on_or_after_the_cutoff_are_never_returned() -> None:
    fake = Fake(page([node(1, "2023-12-31T23:59:59Z"), node(2, "2024-01-01T00:00:00Z")], more=True))

    issues = fetch_issues("o/n", date(2024, 1, 1), fake)

    assert [issue.number for issue in issues] == [1]
    assert fake.pages == []  # it stopped at the first issue past the cutoff


def test_paging_stops_at_the_cutoff_on_a_later_page() -> None:
    fake = Fake(
        page([node(1, "2023-01-01T00:00:00Z")], more=True),
        page([node(2, "2024-02-01T00:00:00Z")], more=True),
        page([node(3, "2024-03-01T00:00:00Z")]),
    )

    issues = fetch_issues("o/n", date(2024, 1, 1), fake, page_size=1)

    assert [issue.number for issue in issues] == [1]
    assert len(fake.sent) == 2  # the third page is never requested


def test_paging_follows_the_cursor_until_the_last_page() -> None:
    fake = Fake(
        page([node(1, "2023-01-01T00:00:00Z")], more=True),
        page([node(2, "2023-02-01T00:00:00Z")]),
    )

    issues = fetch_issues("owner/name", date(2024, 1, 1), fake, page_size=1)

    assert [issue.number for issue in issues] == [1, 2]
    assert fake.sent == [
        {"owner": "owner", "name": "name", "after": None, "pageSize": 1},
        {"owner": "owner", "name": "name", "after": "next", "pageSize": 1},
    ]
    assert issues[0].body == ""


def test_graphql_errors_fail_loudly() -> None:
    with pytest.raises(GitHubError, match="boom"):
        fetch_issues("o/n", date(2024, 1, 1), Fake({"errors": [{"message": "boom"}]}))


def test_gh_graphql_passes_variables_and_decodes_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='{"data": {}}', stderr="")

    monkeypatch.setattr(github.subprocess, "run", run)

    assert gh_graphql("query", {"owner": "o", "after": None, "pageSize": 5}) == {"data": {}}
    assert calls == [
        [
            "gh",
            "api",
            "graphql",
            "--field",
            "query=query",
            "--raw-field",
            "owner=o",
            "--field",
            "pageSize=5",
        ]
    ]


def test_gh_graphql_reports_a_failed_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(github.subprocess, "run", run)

    with pytest.raises(GitHubError, match="not logged in"):
        gh_graphql("query", {})


def bug_page(
    nodes: list[tuple[int, str | None]],
    *,
    labels: dict[int, list[str]] | None = None,
    more: bool = False,
) -> dict[str, Any]:
    info = {"hasNextPage": more, "endCursor": "next" if more else None}
    by_number = labels or {}
    rows = [
        {
            "number": number,
            "issueType": None if kind is None else {"name": kind},
            "labels": {"nodes": [{"name": name} for name in by_number.get(number, [])]},
        }
        for number, kind in nodes
    ]
    return {"data": {"repository": {"issues": {"pageInfo": info, "nodes": rows}}}}


def test_closed_bugs_are_the_closed_issues_typed_bug_across_pages() -> None:
    pages = [bug_page([(1, "Bug"), (2, "Feature"), (3, None)], more=True), bug_page([(4, "bug")])]
    sent: list[Variables] = []

    def graphql(query: str, variables: Variables) -> Mapping[str, Any]:
        assert "CLOSED" in query
        sent.append(variables)
        return pages.pop(0)

    assert github.fetch_closed_bugs("o/r", graphql) == frozenset({1, 4})
    assert [variables["after"] for variables in sent] == [None, "next"]


def test_closed_bugs_include_issues_labeled_bug_without_a_type() -> None:
    page = bug_page(
        [(1, None), (2, None), (3, "Feature"), (4, "Bug")],
        labels={1: ["Bug"], 2: ["docs"], 3: ["bug", "x"], 4: ["bug"]},
    )

    def graphql(_query: str, _variables: Variables) -> Mapping[str, Any]:
        return page

    assert github.fetch_closed_bugs("o/r", graphql) == frozenset({1, 3, 4})


def test_closed_bugs_surface_graphql_errors() -> None:
    def graphql(_query: str, _variables: Variables) -> Mapping[str, Any]:
        return {"errors": [{"message": "boom"}]}

    with pytest.raises(GitHubError, match="boom"):
        github.fetch_closed_bugs("o/r", graphql)
