from datetime import UTC, datetime
from pathlib import Path

import pytest

from gate import repo as gate_repo
from support.fixture_repo import Commit, build_fixture_repo, git, head_sha

pytestmark = pytest.mark.integration

WHEN = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = build_fixture_repo(tmp_path / "repo", [Commit("base", {"a.py": "x = 1\n"}, WHEN)])
    git(path, "update-ref", "refs/remotes/origin/main", head_sha(path))
    return path


def test_staged_files_lists_added_and_modified(repo: Path) -> None:
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "new.md").write_text("# new\n", encoding="utf-8")
    git(repo, "add", "a.py", "new.md")
    assert sorted(gate_repo.staged_files(repo)) == ["a.py", "new.md"]


def test_staged_files_ignores_unstaged_changes(repo: Path) -> None:
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert gate_repo.staged_files(repo) == []


def test_ref_exists(repo: Path) -> None:
    assert gate_repo.ref_exists("origin/main", repo)
    assert not gate_repo.ref_exists("origin/nope", repo)


def test_workflows_unchanged_when_branch_touches_other_files(repo: Path) -> None:
    git(repo, "switch", "--quiet", "--create", "feature")
    (repo / "b.py").write_text("y = 1\n", encoding="utf-8")
    git(repo, "add", "b.py")
    git(repo, "commit", "--quiet", "--message", "feature")
    assert not gate_repo.workflows_changed_since("origin/main", repo)


def test_workflows_changed_when_branch_edits_one(repo: Path) -> None:
    git(repo, "switch", "--quiet", "--create", "feature")
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--message", "feature")
    assert gate_repo.workflows_changed_since("origin/main", repo)


def test_missing_ref_counts_as_workflows_changed(repo: Path) -> None:
    assert gate_repo.workflows_changed_since("origin/nope", repo)
