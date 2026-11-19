from datetime import UTC, datetime
from pathlib import Path

import pytest

from support.fixture_repo import AUTHOR, COMMITTER, Commit, build_fixture_repo, git, head_sha

pytestmark = pytest.mark.integration

FIRST = datetime(2020, 1, 1, tzinfo=UTC)
SECOND = datetime(2021, 6, 1, tzinfo=UTC)
COMMITS = (
    Commit("first", {"a.py": "x = 1\n", "docs/b.md": "# b\n"}, FIRST),
    Commit("second", {"a.py": "x = 2\n", "docs/b.md": None}, SECOND),
)


def test_same_commits_give_the_same_shas(tmp_path: Path) -> None:
    one = build_fixture_repo(tmp_path / "one", COMMITS)
    two = build_fixture_repo(tmp_path / "two", COMMITS)
    assert head_sha(one) == head_sha(two)


def test_identities_and_dates_are_fixed(tmp_path: Path) -> None:
    repo = build_fixture_repo(tmp_path / "repo", COMMITS)
    log = git(repo, "log", "--reverse", "--format=%an <%ae>|%cn <%ce>|%at|%ct|%s").splitlines()
    author = f"{AUTHOR[0]} <{AUTHOR[1]}>"
    committer = f"{COMMITTER[0]} <{COMMITTER[1]}>"
    assert log == [
        f"{author}|{committer}|1577836800|1577836800|first",
        f"{author}|{committer}|1622505600|1622505600|second",
    ]


def test_files_are_written_and_deleted(tmp_path: Path) -> None:
    repo = build_fixture_repo(tmp_path / "repo", COMMITS)
    assert (repo / "a.py").read_text(encoding="utf-8") == "x = 2\n"
    assert not (repo / "docs" / "b.md").exists()


def test_different_content_gives_a_different_sha(tmp_path: Path) -> None:
    other = (Commit("first", {"a.py": "x = 9\n"}, FIRST),)
    one = build_fixture_repo(tmp_path / "one", COMMITS)
    two = build_fixture_repo(tmp_path / "two", other)
    assert head_sha(one) != head_sha(two)


def test_inherited_git_environment_does_not_leak_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks export GIT_DIR and GIT_INDEX_FILE; the fixture must not touch what they name."""
    outer = tmp_path / "outer"
    outer.mkdir()
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(outer / "index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(outer))
    repo = build_fixture_repo(tmp_path / "repo", COMMITS)
    assert (repo / ".git").is_dir()
    assert list(outer.iterdir()) == []


def test_naive_dates_are_rejected(tmp_path: Path) -> None:
    naive = (Commit("first", {"a.py": ""}, datetime(2020, 1, 1)),)  # noqa: DTZ001 - the case under test
    with pytest.raises(ValueError, match="timezone-aware"):
        build_fixture_repo(tmp_path / "repo", naive)
