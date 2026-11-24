"""The Leakage test: nothing dated after the Cutoff date reaches the snapshot (ADR 0007).

Post-cutoff commits carry a poison marker in file names and change a tracked file. The snapshot
covers the baseline's churn and complexity inputs; later slices extend this test to prompts.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from support.fixture_repo import Commit, build_fixture_repo, head_sha
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.run.artifacts import SNAPSHOT
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.run.snapshot import SnapshotDeps, snapshot
from tech_debt_miner.types import FileFacts, Manifest

pytestmark = pytest.mark.policy

CUTOFF = date(2024, 1, 1)
POISON = "poison_after_cutoff"
BEFORE = "def f(x):\n    if x:\n        return 1\n    return 0\n"


def at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit("before", {"a.py": BEFORE}, at(2023, 6, 1)),
            Commit("on cutoff", {f"{POISON}_edge.py": BEFORE}, at(2024, 1, 1, 0)),
            Commit("after", {"a.py": BEFORE * 4, f"{POISON}.py": BEFORE}, at(2024, 3, 1)),
        ],
    )


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
    snapshot(run_dir, SnapshotDeps(repos_dir=repo.parent))
    return run_dir


def test_the_snapshot_never_carries_post_cutoff_history(tmp_path: Path, repo: Path) -> None:
    pinned = repo_git.resolve_pinned_sha(repo, CUTOFF)

    run_dir = run_snapshot(tmp_path, repo, pinned_sha=pinned, cutoff=CUTOFF)

    assert POISON not in (run_dir.path / "snapshot.json").read_text(encoding="utf-8")
    assert run_dir.read(SNAPSHOT).files == (FileFacts("a.py", loc=4, churn=1, complexity=2),)


def test_the_test_fails_when_the_cutoff_filter_is_disabled(tmp_path: Path, repo: Path) -> None:
    run_dir = run_snapshot(tmp_path, repo, pinned_sha=head_sha(repo), cutoff=date(2099, 1, 1))

    assert POISON in (run_dir.path / "snapshot.json").read_text(encoding="utf-8")
