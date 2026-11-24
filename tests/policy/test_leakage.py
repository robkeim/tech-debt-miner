"""The Leakage test: nothing dated after the Cutoff date reaches the snapshot (ADR 0007).

Post-cutoff commits carry a poison marker in file names and change a tracked file. Post-cutoff
issues carry it too: one created after the Cutoff date, one whose body was edited after it, and
one renamed after it. The snapshot covers the baseline's churn and complexity inputs, the LLM
prompt inputs (head, outline and commit subjects) and the issues; later slices extend this test
to the prompts themselves.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from support.fixture_repo import Commit, build_fixture_repo, head_sha
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.repo.github import fetch_issues
from tech_debt_miner.run.artifacts import SNAPSHOT
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.run.snapshot import SnapshotDeps, snapshot
from tech_debt_miner.types import Manifest

pytestmark = pytest.mark.policy

Node = dict[str, Any]

CUTOFF = date(2024, 1, 1)
POISON = "poison_after_cutoff"
BEFORE = "def f(x):\n    if x:\n        return 1\n    return 0\n"
AFTER = f"def {POISON}_function():\n    return '{POISON}'\n"


def at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit("before", {"a.py": BEFORE}, at(2023, 6, 1)),
            Commit(f"{POISON} on cutoff", {f"{POISON}_edge.py": BEFORE}, at(2024, 1, 1, 0)),
            Commit(
                f"{POISON} after",
                {"a.py": BEFORE + AFTER, f"{POISON}.py": BEFORE},
                at(2024, 3, 1),
            ),
        ],
    )


def issue_node(number: int, created: datetime, title: str = "plain", body: str = "plain") -> Node:
    return {
        "number": number,
        "title": title,
        "body": body,
        "createdAt": created.isoformat(),
        "lastEditedAt": None,
        "userContentEdits": {"totalCount": 0, "nodes": []},
        "timelineItems": {"totalCount": 0, "nodes": []},
    }


def edited(node: Node, when: datetime) -> Node:
    return node | {
        "lastEditedAt": when.isoformat(),
        "userContentEdits": {"totalCount": 1, "nodes": [{"editedAt": when.isoformat()}]},
    }


def renamed(node: Node, when: datetime) -> Node:
    rename = {"createdAt": when.isoformat(), "previousTitle": "title as of cutoff"}
    return node | {"timelineItems": {"totalCount": 1, "nodes": [rename]}}


def graphql(_query: str, _variables: Mapping[str, str | int | None]) -> Mapping[str, Any]:
    """Return a GraphQL response whose post-cutoff issues and edits all carry the poison."""
    later = at(2024, 3, 1)
    nodes = [
        issue_node(1, at(2023, 6, 1), body="kept body"),
        edited(issue_node(2, at(2023, 6, 2), body=f"{POISON} edited body"), later),
        renamed(issue_node(3, at(2023, 6, 3), title=f"{POISON} renamed"), later),
        issue_node(4, later, title=f"{POISON} created later"),
    ]
    info = {"hasNextPage": False, "endCursor": None}
    return {"data": {"repository": {"issues": {"pageInfo": info, "nodes": nodes}}}}


def run_snapshot(tmp_path: Path, repo: Path, *, pinned_sha: str, cutoff: date) -> RunDir:
    manifest = Manifest(
        target_repo="owner/target",
        pinned_sha=pinned_sha,
        cutoff_date=cutoff.isoformat(),
        model="m",
        model_training_cutoff="2023-06-30",
        cutoff_minus_training_days=0,
        repeats=1,
        prompt_hashes={},
        lizard_version="1",
        adr_shas={},
        tool_sha="t",
    )
    run_dir = RunDir.create(tmp_path / "runs", manifest, lambda: at(2026, 11, 24))
    deps = SnapshotDeps(
        repos_dir=repo.parent, issues=lambda name, day: fetch_issues(name, day, graphql)
    )
    snapshot(run_dir, deps)
    return run_dir


def test_the_snapshot_never_carries_post_cutoff_history(tmp_path: Path, repo: Path) -> None:
    pinned = repo_git.resolve_pinned_sha(repo, CUTOFF)

    run_dir = run_snapshot(tmp_path, repo, pinned_sha=pinned, cutoff=CUTOFF)

    assert POISON not in (run_dir.path / "snapshot.json").read_text(encoding="utf-8")
    (facts,) = result.files
    assert (facts.path, facts.loc, facts.churn, facts.complexity) == ("a.py", 4, 1, 2)
    # The prompt inputs: head, outline, names and subjects come only from before the Cutoff date.
    assert facts.head == BEFORE.rstrip("\n")
    assert facts.truncated_lines == 0
    assert [(e.name, e.line) for e in facts.outline] == [("f", 1)]
    assert facts.top_level_names == ("f",)
    assert [(c.date, c.subject) for c in facts.recent_commits] == [("2023-06-01", "before")]
    assert [(i.number, i.title, i.body) for i in result.issues] == [
        (1, "plain", "kept body"),
        (3, "title as of cutoff", "plain"),
    ]
    assert result.excluded_issues == 1  # the edited one; the later-created one never existed


def test_the_test_fails_when_the_cutoff_filter_is_disabled(tmp_path: Path, repo: Path) -> None:
    run_dir = run_snapshot(tmp_path, repo, pinned_sha=head_sha(repo), cutoff=date(2024, 6, 1))

    text = (run_dir.path / "snapshot.json").read_text(encoding="utf-8")
    assert POISON in text
    (facts,) = (f for f in run_dir.read(SNAPSHOT).files if f.path == "a.py")
    assert POISON in facts.head
    assert POISON in facts.recent_commits[0].subject
    assert POISON in facts.top_level_names[-1]
