"""The only code that talks to GitHub: issues and their edit history over GraphQL (ADR 0008).

The spike behind this module found that `userContentEdits` and `lastEditedAt` are readable on
public repos with any authenticated token. `gh` supplies the token, so there is no auth code here.
The GraphQL runner is injected, so tests feed recorded responses and never touch the network.
"""

import json
import subprocess
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from tech_debt_miner.repo.cutoff import midnight_utc
from tech_debt_miner.repo.issues import RawIssue, Rename

PAGE_SIZE = 100

ISSUES_QUERY = """
query($owner: String!, $name: String!, $after: String, $pageSize: Int!) {
  repository(owner: $owner, name: $name) {
    issues(first: $pageSize, after: $after, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        createdAt
        lastEditedAt
        userContentEdits(first: 100) { totalCount nodes { editedAt } }
        timelineItems(first: 100, itemTypes: [RENAMED_TITLE_EVENT]) {
          totalCount
          nodes { ... on RenamedTitleEvent { createdAt previousTitle } }
        }
      }
    }
  }
}
"""

# Runs a GraphQL query with variables and returns the decoded response.
GraphQL = Callable[[str, Mapping[str, str | int | None]], Mapping[str, Any]]


class GitHubError(RuntimeError):
    """A GitHub request failed or returned errors."""


def gh_graphql(query: str, variables: Mapping[str, str | int | None]) -> Mapping[str, Any]:
    """Run `query` through the `gh` CLI, which holds the user's token."""
    args = ["gh", "api", "graphql", "--field", f"query={query}"]
    for key, value in variables.items():
        if value is not None:
            args += ["--raw-field" if isinstance(value, str) else "--field", f"{key}={value}"]
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        args,  # gh is resolved from PATH
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        msg = f"gh api graphql failed: {result.stderr.strip()}"
        raise GitHubError(msg)
    return json.loads(result.stdout)


def fetch_issues(
    repo: str, cutoff: date, graphql: GraphQL = gh_graphql, page_size: int = PAGE_SIZE
) -> list[RawIssue]:
    """Return every issue of `owner/name` created before the Cutoff date, oldest first.

    Issues arrive in creation order, so paging stops at the first one on or after the Cutoff
    date, and none of those is ever returned. Pull requests are not issues in this API.
    """
    owner, name = repo.split("/", 1)
    limit = midnight_utc(cutoff)
    issues: list[RawIssue] = []
    after: str | None = None
    while True:
        response = graphql(
            ISSUES_QUERY, {"owner": owner, "name": name, "after": after, "pageSize": page_size}
        )
        page = _page(response)
        parsed = [_parse_issue(node) for node in page["nodes"]]
        issues += [issue for issue in parsed if issue.created_at < limit]
        if len(issues) < len(parsed) or not page["pageInfo"]["hasNextPage"]:
            # The page held an issue created on or after the Cutoff date, or was the last one.
            return issues
        after = page["pageInfo"]["endCursor"]


def _page(response: Mapping[str, Any]) -> Mapping[str, Any]:
    if response.get("errors"):
        msg = f"GitHub returned errors: {response['errors']}"
        raise GitHubError(msg)
    return response["data"]["repository"]["issues"]


def _parse_issue(node: Mapping[str, Any]) -> RawIssue:
    edits = node["userContentEdits"]
    renames = node["timelineItems"]
    return RawIssue(
        number=node["number"],
        title=node["title"],
        body=node["body"] or "",
        created_at=_parse_time(node["createdAt"]),
        last_edited_at=_parse_time(node["lastEditedAt"]) if node["lastEditedAt"] else None,
        edit_times=tuple(_parse_time(edit["editedAt"]) for edit in edits["nodes"]),
        edit_count=edits["totalCount"],
        renames=tuple(
            Rename(_parse_time(rename["createdAt"]), rename["previousTitle"])
            for rename in renames["nodes"]
        ),
        rename_count=renames["totalCount"],
    )


def _parse_time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)
