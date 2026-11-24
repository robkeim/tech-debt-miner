import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from support.fixture_repo import Commit, build_fixture_repo, git
from tech_debt_miner import cli
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.run.artifacts import SNAPSHOT
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.run.snapshot import SnapshotDeps, snapshot
from tech_debt_miner.types import FileFacts, Manifest

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
BRANCHY = "def f(x):\n    if x:\n        return 1\n    return 0\n"


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)


def new_run(tmp_path: Path, repo: Path, pinned_sha: str | None = None) -> RunDir:
    manifest = Manifest(
        target_repo="owner/target",
        pinned_sha=pinned_sha or repo_git.resolve_pinned_sha(repo, CUTOFF),
        cutoff_date=CUTOFF.isoformat(),
        model="m",
        model_training_cutoff="2023-06-30",
        cutoff_minus_training_days=0,
        repeats=1,
        prompt_hashes={},
        lizard_version="1",
        adr_shas={},
        tool_sha="t",
    )
    return RunDir.create(tmp_path / "runs", manifest, lambda: at(2026, 11, 24))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit("too old", {"old_only.py": "x = 1\n"}, at(2022, 6, 1)),
            Commit("a", {"a.py": BRANCHY, "tests/test_a.py": BRANCHY}, at(2023, 3, 1)),
            Commit("b", {"b.py": "y = 1\n", "doc.md": "# d\n"}, at(2023, 4, 1)),
            Commit("a again", {"a.py": BRANCHY + "\n"}, at(2023, 5, 1)),
            Commit("rename", {"b.py": None, "c.py": "y = 1\n"}, at(2023, 6, 1)),
            Commit("c again", {"c.py": "y = 2\n"}, at(2023, 7, 1)),
            Commit("after", {"a.py": BRANCHY * 3, "late.py": BRANCHY}, at(2024, 2, 1)),
        ],
    )


def run_snapshot(tmp_path: Path, repo: Path) -> RunDir:
    run_dir = new_run(tmp_path, repo)
    snapshot(run_dir, SnapshotDeps(repos_dir=tmp_path / "repos"))
    return run_dir


def test_snapshot_holds_eligible_files_with_loc_churn_and_complexity(
    tmp_path: Path, repo: Path
) -> None:
    facts = run_snapshot(tmp_path, repo).read(SNAPSHOT).files

    assert facts == (
        FileFacts("a.py", loc=5, churn=2, complexity=2),
        FileFacts("c.py", loc=1, churn=3, complexity=0),  # b.py's commits follow the rename
        FileFacts("old_only.py", loc=1, churn=0, complexity=0),  # outside the Churn window
    )


def test_snapshot_reports_the_files_scored_zero_complexity(tmp_path: Path, repo: Path) -> None:
    assert run_snapshot(tmp_path, repo).read(SNAPSHOT).zero_complexity_files == 2


def test_churn_counts_only_ancestors_of_the_pinned_sha(tmp_path: Path, repo: Path) -> None:
    pinned = git(repo, "rev-list", "--reverse", "HEAD").split()[2]  # the "b" commit
    run_dir = new_run(tmp_path, repo, pinned_sha=pinned)
    snapshot(run_dir, SnapshotDeps(repos_dir=tmp_path / "repos"))

    churn = {f.path: f.churn for f in run_dir.read(SNAPSHOT).files}

    # "a again", the rename and "c again" are dated before the Cutoff but are not ancestors.
    assert churn == {"a.py": 1, "b.py": 1, "old_only.py": 0}


def test_merge_commits_are_not_churn(tmp_path: Path) -> None:
    repo = build_fixture_repo(
        tmp_path / "repos" / "target",
        [Commit("a", {"a.py": BRANCHY}, at(2023, 3, 1))],
    )
    stamp = "2023-04-01T12:00:00+00:00"
    env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    commit = ("-c", "commit.gpgsign=false")
    git(repo, "checkout", "--quiet", "-b", "side")
    (repo / "a.py").write_text(BRANCHY + "\n", encoding="utf-8")
    git(repo, *commit, "commit", "--quiet", "--all", "--message", "side", env=env)
    git(repo, "checkout", "--quiet", "main")
    git(repo, *commit, "merge", "--quiet", "--no-ff", "--message", "merge", "side", env=env)

    facts = run_snapshot(tmp_path, repo).read(SNAPSHOT).files

    assert [(f.path, f.churn) for f in facts] == [("a.py", 2)]


def test_the_exported_tree_is_deleted_afterward(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    run_snapshot(tmp_path, repo)

    assert list(scratch.iterdir()) == []


def test_cli_snapshot_writes_the_artifact(tmp_path: Path, repo: Path) -> None:
    run_dir = new_run(tmp_path, repo)
    argv = [
        "snapshot",
        run_dir.id,
        "--repos-dir",
        str(tmp_path / "repos"),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]

    assert cli.main(argv) == 0
    assert (run_dir.path / "snapshot.json").exists()


def test_cli_snapshot_rejects_an_unknown_run(tmp_path: Path) -> None:
    assert cli.main(["snapshot", "nope", "--runs-dir", str(tmp_path)]) == 2
