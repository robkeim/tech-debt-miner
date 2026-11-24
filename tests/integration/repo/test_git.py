from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from support.fixture_repo import Commit, build_fixture_repo, git, head_sha
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.repo.git import FileChange, GitError

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
POISON = "POISON_AFTER_CUTOFF"
BODY = "def f():\n    return 1\n"


def at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_fixture_repo(
        tmp_path / "repo",
        [
            Commit("first", {"a.py": "x = 1\n", "old.py": BODY}, at(2023, 3, 1)),
            Commit("second", {"a.py": "x = 2\n"}, at(2023, 6, 1)),
            Commit("rename", {"old.py": None, "new.py": BODY}, at(2023, 9, 1)),
            Commit("last before", {"a.py": "x = 3\n"}, at(2023, 12, 31, 23)),
            Commit("on cutoff", {"a.py": f"x = '{POISON}'\n"}, at(2024, 1, 1, 0)),
            Commit("after", {"leak.py": f"y = '{POISON}'\n"}, at(2024, 3, 1)),
        ],
    )


def shas(repo: Path) -> list[str]:
    return git(repo, "log", "--reverse", "--format=%H").split()


def test_clone_once_and_never_refetch(tmp_path: Path, repo: Path) -> None:
    dest = tmp_path / "repos" / "target"
    assert repo_git.clone_repo(str(repo), dest) == dest
    assert head_sha(dest) == head_sha(repo)
    git(repo, "commit", "--quiet", "--allow-empty", "--message", "later")
    repo_git.clone_repo(str(repo), dest)
    assert head_sha(dest) != head_sha(repo)


def test_pinned_sha_is_last_commit_before_cutoff(repo: Path) -> None:
    assert repo_git.resolve_pinned_sha(repo, CUTOFF) == shas(repo)[3]


def test_pinned_sha_is_stable_when_history_grows(repo: Path) -> None:
    before = repo_git.resolve_pinned_sha(repo, CUTOFF)
    git(repo, "commit", "--quiet", "--allow-empty", "--message", "later")
    assert repo_git.resolve_pinned_sha(repo, CUTOFF) == before


def test_pinned_sha_fails_with_no_earlier_history(repo: Path) -> None:
    with pytest.raises(GitError, match="no commit before 2020-01-01"):
        repo_git.resolve_pinned_sha(repo, date(2020, 1, 1))


def test_pinned_sha_steps_back_over_clock_skew(tmp_path: Path) -> None:
    skewed = build_fixture_repo(
        tmp_path / "skewed",
        [
            Commit("base", {"a.py": "x = 1\n"}, at(2023, 6, 1)),
            Commit("skewed", {"a.py": f"x = '{POISON}'\n"}, at(2024, 2, 1)),
            Commit("looks early", {"b.py": "y = 1\n"}, at(2023, 12, 1)),
        ],
    )
    pinned = repo_git.resolve_pinned_sha(skewed, CUTOFF)
    assert pinned == git(skewed, "rev-parse", "HEAD~2").strip()


def test_pinned_tree_excludes_late_dated_merged_side_branch(tmp_path: Path) -> None:
    merged = build_fixture_repo(
        tmp_path / "merged", [Commit("base", {"a.py": "x = 1\n"}, at(2023, 6, 1))]
    )
    late = {
        "GIT_AUTHOR_DATE": at(2024, 2, 1).isoformat(),
        "GIT_COMMITTER_DATE": at(2024, 2, 1).isoformat(),
    }
    merge_day = {
        "GIT_AUTHOR_DATE": at(2023, 12, 15).isoformat(),
        "GIT_COMMITTER_DATE": at(2023, 12, 15).isoformat(),
    }
    git(merged, "switch", "--quiet", "--create", "feature")
    (merged / "leak.py").write_text(f"y = '{POISON}'\n", encoding="utf-8")
    git(merged, "add", "leak.py")
    git(merged, "commit", "--quiet", "--message", "late side work", env=late)
    git(merged, "switch", "--quiet", "main")
    (merged / "a.py").write_text("x = 2\n", encoding="utf-8")
    git(merged, "commit", "--quiet", "--all", "--message", "main work", env=merge_day)
    before_merge = head_sha(merged)
    git(merged, "merge", "--quiet", "--no-ff", "--no-edit", "feature", env=merge_day)
    pinned = repo_git.resolve_pinned_sha(merged, CUTOFF)
    assert pinned == before_merge != head_sha(merged)
    with repo_git.export_tree(merged, pinned) as tree:
        assert not (tree / "leak.py").exists()


def test_pinned_sha_fails_when_every_candidate_has_late_ancestry(tmp_path: Path) -> None:
    skewed = build_fixture_repo(
        tmp_path / "skewed",
        [
            Commit("skewed root", {"a.py": "x = 1\n"}, at(2024, 2, 1)),
            Commit("looks early", {"a.py": "x = 2\n"}, at(2023, 12, 1)),
        ],
    )
    with pytest.raises(GitError, match="only earlier history"):
        repo_git.resolve_pinned_sha(skewed, CUTOFF)


def test_git_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(GitError, match="failed"):
        repo_git.resolve_pinned_sha(tmp_path, CUTOFF)


def test_list_commits_respects_range_and_lists_paths(repo: Path) -> None:
    commits = repo_git.list_commits(repo, date(2023, 5, 1), CUTOFF)
    assert [(c.sha, sorted(f.path for f in c.files)) for c in commits] == [
        (shas(repo)[3], ["a.py"]),
        (shas(repo)[2], ["new.py"]),
        (shas(repo)[1], ["a.py"]),
    ]
    assert commits[0].committed_at == at(2023, 12, 31, 23)


def test_list_commits_follows_renames(repo: Path) -> None:
    rename = repo_git.list_commits(repo, date(2023, 8, 1), date(2023, 10, 1))[0]
    assert rename.files == (FileChange("new.py", "old.py"),)


def test_list_commits_excludes_merges(repo: Path) -> None:
    git(repo, "switch", "--quiet", "--create", "feature", shas(repo)[0])
    (repo / "f.py").write_text("z = 1\n", encoding="utf-8")
    git(repo, "add", "f.py")
    git(repo, "commit", "--quiet", "--message", "feature work")
    git(repo, "switch", "--quiet", "main")
    git(repo, "merge", "--quiet", "--no-ff", "--no-edit", "feature")
    commits = repo_git.list_commits(repo, date(2020, 1, 1), date(2100, 1, 1))
    messages = {git(repo, "log", "-1", "--format=%s", c.sha).strip() for c in commits}
    assert "feature work" in messages
    assert not any(m.startswith("Merge") for m in messages)


def test_export_tree_writes_the_tree_and_cleans_up(repo: Path) -> None:
    pinned = repo_git.resolve_pinned_sha(repo, CUTOFF)
    with repo_git.export_tree(repo, pinned) as tree:
        assert (tree / "a.py").read_text(encoding="utf-8") == "x = 3\n"
        assert not (tree / "leak.py").exists()
        assert not (tree / ".git").exists()
    assert not tree.exists()


def test_nothing_after_the_cutoff_date_is_returned(repo: Path) -> None:
    """Git-level slice of the Leakage test: the poison marker never appears in as-of output.

    The policy-tier Leakage test (Dry-run path, filter-disabled check) comes with later slices.
    """
    pinned = repo_git.resolve_pinned_sha(repo, CUTOFF)
    commits = repo_git.list_commits(repo, date(2000, 1, 1), CUTOFF)
    assert all(c.committed_at.date() < CUTOFF for c in commits)
    assert {c.sha for c in commits}.isdisjoint(shas(repo)[4:])
    assert all(f.path != "leak.py" for c in commits for f in c.files)
    with repo_git.export_tree(repo, pinned) as tree:
        contents = "".join(p.read_text(encoding="utf-8") for p in tree.rglob("*.py"))
    assert POISON not in contents


def test_head_sha_and_last_commit_touching(repo: Path) -> None:
    assert repo_git.head_sha(repo) == shas(repo)[-1]
    assert repo_git.last_commit_touching(repo, "a.py") == shas(repo)[4]
    assert repo_git.last_commit_touching(repo, "old.py") == shas(repo)[2]


def test_last_commit_touching_an_unknown_path_fails(repo: Path) -> None:
    with pytest.raises(GitError, match="no commit touches"):
        repo_git.last_commit_touching(repo, "nope.py")
