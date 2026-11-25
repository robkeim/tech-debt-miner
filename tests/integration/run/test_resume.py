from datetime import UTC, date, datetime, tzinfo
from pathlib import Path

import pytest

from support.fixture_repo import Commit, build_fixture_repo
from tech_debt_miner import cli
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.repo import github
from tech_debt_miner.run import snapshot as snapshot_module
from tech_debt_miner.run.artifacts import LABELS, RANKING, SNAPSHOT
from tech_debt_miner.run.label import LabelDeps, WindowOpenError
from tech_debt_miner.run.run_dir import RunDir, RunState, Stage
from tech_debt_miner.run.score import ScoreDeps
from tech_debt_miner.run.snapshot import SnapshotDeps
from tech_debt_miner.run.stages import StageDeps, resume
from tech_debt_miner.types import Manifest

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
BRANCHY = "def f(x):\n    if x:\n        return 1\n    return 0\n"
AFTER_WINDOW = datetime(2024, 8, 1, tzinfo=UTC)
INSIDE_WINDOW = datetime(2024, 2, 1, tzinfo=UTC)


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit("a", {"a.py": BRANCHY}, at(2023, 3, 1)),
            Commit("b", {"b.py": BRANCHY}, at(2023, 4, 1)),
            Commit("fix a", {"a.py": BRANCHY + "\n"}, at(2024, 3, 1)),
        ],
    )
    return tmp_path / "repos"


def new_run(tmp_path: Path, repos_dir: Path) -> RunDir:
    manifest = Manifest(
        target_repo="owner/target",
        pinned_sha=repo_git.resolve_pinned_sha(repos_dir / "target", CUTOFF),
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


def no_bugs(_repo: str) -> set[int]:
    return set()


def deps_for(repos_dir: Path, today: datetime = AFTER_WINDOW) -> StageDeps:
    return StageDeps(
        snapshot=SnapshotDeps(repos_dir=repos_dir, issues=None),
        label=LabelDeps(repos_dir=repos_dir, clock=lambda: today, update_clone=None),
        closed_bugs=no_bugs,
        score=ScoreDeps(clock=lambda: today),
    )


def leftovers(run_dir: RunDir) -> list[str]:
    return sorted(p.name for p in run_dir.path.rglob("*.tmp"))


def test_a_dry_run_is_a_planned_run_that_stops_after_snapshot(
    tmp_path: Path, repos_dir: Path
) -> None:
    run_dir = new_run(tmp_path, repos_dir)

    ran = resume(run_dir, deps_for(repos_dir), run=False)

    assert ran == [Stage.SNAPSHOT]
    assert run_dir.state() is RunState.PLANNED
    assert not run_dir.exists(RANKING, ("baseline", 0))
    assert not run_dir.exists(LABELS)


def test_resume_run_continues_the_same_directory_and_keeps_done_artifacts(
    tmp_path: Path, repos_dir: Path
) -> None:
    run_dir = new_run(tmp_path, repos_dir)
    resume(run_dir, deps_for(repos_dir), run=False)
    planned = (run_dir.path / "snapshot.json").read_bytes()

    ran = resume(run_dir, deps_for(repos_dir), run=True)

    assert ran == [Stage.RANK, Stage.LABEL, Stage.SCORE]
    assert (run_dir.path / "snapshot.json").read_bytes() == planned
    assert run_dir.state() is RunState.SCORED
    assert run_dir.next_stage() is None


def test_resume_of_a_finished_run_does_nothing(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = new_run(tmp_path, repos_dir)
    resume(run_dir, deps_for(repos_dir), run=True)

    assert resume(run_dir, deps_for(repos_dir), run=True) == []


def test_a_stage_that_stops_the_run_leaves_the_earlier_stages_done(
    tmp_path: Path, repos_dir: Path
) -> None:
    run_dir = new_run(tmp_path, repos_dir)

    with pytest.raises(WindowOpenError):
        resume(run_dir, deps_for(repos_dir, today=INSIDE_WINDOW), run=True)

    assert run_dir.is_done(Stage.RANK)
    assert not run_dir.exists(LABELS)
    assert resume(run_dir, deps_for(repos_dir), run=True) == [Stage.LABEL, Stage.SCORE]


def test_a_stage_killed_midway_leaves_no_partial_artifact(
    tmp_path: Path, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = new_run(tmp_path, repos_dir)
    real = snapshot_module.file_complexity
    calls: list[str] = []

    def killed_on_second_file(path: str, content: bytes) -> int:
        calls.append(path)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(path, content)

    monkeypatch.setattr(snapshot_module, "file_complexity", killed_on_second_file)
    with pytest.raises(KeyboardInterrupt):
        resume(run_dir, deps_for(repos_dir), run=False)

    assert not run_dir.exists(SNAPSHOT)
    assert leftovers(run_dir) == []
    assert run_dir.next_stage() is Stage.SNAPSHOT

    monkeypatch.undo()
    assert resume(run_dir, deps_for(repos_dir), run=False) == [Stage.SNAPSHOT]


def test_a_kill_during_the_final_rename_leaves_no_artifact(
    tmp_path: Path, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = new_run(tmp_path, repos_dir)

    def killed(_self: Path, _target: Path) -> Path:
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", killed)
        with pytest.raises(KeyboardInterrupt):
            resume(run_dir, deps_for(repos_dir), run=False)

    assert not run_dir.exists(SNAPSHOT)
    assert leftovers(run_dir) == []
    assert resume(run_dir, deps_for(repos_dir), run=False) == [Stage.SNAPSHOT]


def test_the_resume_command_plans_then_stops_at_the_open_label_window(
    tmp_path: Path, repos_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = new_run(tmp_path, repos_dir)
    common = [
        "resume",
        run_dir.id,
        "--no-issues",
        "--no-fetch",
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]

    assert cli.main(common) == 0
    assert capsys.readouterr().out.strip() == "ran: snapshot; state: planned"
    # The suite's frozen clock is 2024-01-15, inside the Label window.
    assert cli.main([*common, "--run"]) == 1
    assert "the Label window closes after 2024-07-01" in capsys.readouterr().err
    assert run_dir.is_done(Stage.RANK)


def test_the_resume_command_rejects_an_unknown_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["resume", "nope", "--runs-dir", str(tmp_path / "runs")]) == 2
    assert "no such Run" in capsys.readouterr().err


def test_a_tracker_failure_in_label_reports_without_the_snapshot_hint(
    tmp_path: Path,
    repos_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = new_run(tmp_path, repos_dir)

    def down(_repo: str) -> set[int]:
        msg = "gh is down"
        raise github.GitHubError(msg)

    monkeypatch.setattr(github, "fetch_closed_bugs", down)
    # The suite's frozen clock is inside the Label window, so label would refuse first. Move it.
    monkeypatch.setattr(cli, "datetime", _AfterWindow)
    args = ["resume", run_dir.id, "--run", "--no-issues", "--no-fetch"]
    args += ["--repos-dir", str(repos_dir), "--runs-dir", str(tmp_path / "runs")]

    assert cli.main(args) == 1
    err = capsys.readouterr().err
    assert "gh is down" in err
    assert "--no-issues" not in err


class _AfterWindow(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _AfterWindow:
        return cls(2024, 8, 1, tzinfo=tz)
