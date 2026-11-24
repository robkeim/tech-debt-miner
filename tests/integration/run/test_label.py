from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import time_machine

from support.fixture_repo import Commit, build_fixture_repo, git
from tech_debt_miner import cli
from tech_debt_miner.repo.git import resolve_pinned_sha
from tech_debt_miner.run.label import LabelDeps, WindowOpenError, label
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
POISON = "POISON_BEFORE_THE_WINDOW"
AFTER_WINDOW = datetime(2024, 8, 1, tzinfo=UTC)
BODY = "def f():\n    return 1\n"


def at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def add_commit(
    repo: Path, message: str, files: dict[str, str | None], when: datetime, author: str = "Dev"
) -> None:
    for name, content in files.items():
        if content is None:
            (repo / name).unlink()
        else:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", "--all")
    stamp = when.isoformat()
    env = {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_DATE": stamp,
    }
    git(repo, "commit", "--quiet", "--message", message, env=env)


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    repo = build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit(
                "base",
                {"a.py": BODY, "b.py": BODY, "c.py": BODY, "tests/test_a.py": BODY},
                at(2023, 6, 1),
            ),
            Commit("fix before the cutoff", {"a.py": BODY + "# 1\n"}, at(2023, 12, 31)),
            Commit("fix on the cutoff day", {"a.py": BODY + f"# {POISON}\n"}, at(2024, 1, 1)),
        ],
    )
    add_commit(repo, "fix a (#1)", {"a.py": BODY + "# 2\n"}, at(2024, 2, 1))
    add_commit(repo, "move b", {"b.py": None, "pkg/b2.py": BODY}, at(2024, 2, 5))
    add_commit(repo, "fix moved b", {"pkg/b2.py": BODY + "# 2\n"}, at(2024, 3, 1))
    add_commit(repo, "fix new file", {"new.py": BODY}, at(2024, 3, 2))
    add_commit(repo, "fix dropping c", {"c.py": None}, at(2024, 4, 1))
    add_commit(repo, "fix bot", {"a.py": BODY + "# 3\n"}, at(2024, 4, 2), author="renovate[bot]")
    add_commit(repo, "fix wide", {"a.py": BODY, "d.py": BODY, "e.py": BODY}, at(2024, 5, 1))
    add_commit(repo, "fix on the last day", {"a.py": BODY + "# 4\n"}, at(2024, 7, 1, 23))
    add_commit(repo, "fix after the window", {"a.py": BODY + "# 5\n"}, at(2024, 7, 2))
    return tmp_path / "repos"


def make_run(tmp_path: Path, repos_dir: Path) -> RunDir:
    manifest = Manifest(
        target_repo="owner/target",
        pinned_sha=resolve_pinned_sha(repos_dir / "target", CUTOFF),
        cutoff_date=CUTOFF.isoformat(),
        model="model-1",
        model_training_cutoff="2023-06-30",
        cutoff_minus_training_days=185,
        repeats=1,
        prompt_hashes={},
        lizard_version="1.17.0",
        adr_shas={},
        tool_sha="c" * 40,
    )
    return RunDir.create(tmp_path / "runs", manifest, lambda: AFTER_WINDOW)


def deps_for(repos_dir: Path, max_files: int | None = None) -> LabelDeps:
    return LabelDeps(repos_dir=repos_dir, clock=lambda: AFTER_WINDOW, max_files=max_files)


def test_label_counts_fix_commits_in_the_window_and_writes_labels_json(
    tmp_path: Path, repos_dir: Path
) -> None:
    run_dir = make_run(tmp_path, repos_dir)

    result = label(run_dir, deps_for(repos_dir))

    assert run_dir.read_labels() == result
    # a: "fix a" and the wide fix and the last-day fix. The bot, the cutoff-day and the
    # after-window commits do not count. b: moved, then fixed. c: deleted by a fix.
    assert dict(result.counts) == {"a.py": 3, "b.py": 1, "c.py": 1}
    assert result.stats["fix_commits_dropped_by_cap"] == 0


def test_label_applies_the_fix_size_cap(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)

    result = label(run_dir, deps_for(repos_dir, max_files=2))

    assert dict(result.counts) == {"a.py": 2, "b.py": 1, "c.py": 1}
    assert result.stats["fix_commits_dropped_by_cap"] == 1


def test_label_reports_squash_and_pr_number_shares(tmp_path: Path, repos_dir: Path) -> None:
    result = label(make_run(tmp_path, repos_dir), deps_for(repos_dir))

    assert result.stats["commits_in_window"] == 8
    assert result.stats["squash_share"] == pytest.approx(1 / 8)
    assert result.stats["fix_commits"] == 6
    assert result.stats["pr_number_only_share"] == pytest.approx(1 / 6)


def test_label_never_reads_the_cutoff_day_or_later_than_the_window(
    tmp_path: Path, repos_dir: Path
) -> None:
    """The window is bounded on both sides, so poison from before it never counts."""
    run_dir = make_run(tmp_path, repos_dir)

    label(run_dir, deps_for(repos_dir))

    assert POISON not in run_dir.labels_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("today", [date(2024, 1, 15), date(2024, 7, 1)])
def test_label_refuses_until_the_window_has_closed(
    tmp_path: Path, repos_dir: Path, today: date
) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    deps = LabelDeps(
        repos_dir=repos_dir, clock=lambda: datetime(today.year, today.month, today.day, tzinfo=UTC)
    )

    with pytest.raises(WindowOpenError, match="2024-07-01"):
        label(run_dir, deps)

    assert not run_dir.labels_path.exists()


def test_label_never_overwrites_an_existing_labels_file(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    label(run_dir, deps_for(repos_dir))

    with pytest.raises(FileExistsError, match="already exists"):
        label(run_dir, deps_for(repos_dir, max_files=2))


def test_label_runs_on_the_first_day_after_the_window(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    deps = LabelDeps(repos_dir=repos_dir, clock=lambda: datetime(2024, 7, 2, tzinfo=UTC))

    label(run_dir, deps)

    assert run_dir.labels_path.exists()


def test_cli_label_writes_labels_once_the_window_has_closed(
    tmp_path: Path, repos_dir: Path, frozen_clock: time_machine.Traveller
) -> None:
    frozen_clock.move_to(AFTER_WINDOW)
    run_dir = make_run(tmp_path, repos_dir)
    argv = [
        "label",
        run_dir.id,
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
        "--max-files",
        "2",
    ]

    assert cli.main(argv) == 0
    assert run_dir.read_labels().stats["fix_commits_dropped_by_cap"] == 1


def test_cli_label_refuses_while_the_window_is_open(
    tmp_path: Path, repos_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    argv = [
        "label",
        run_dir.id,
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]

    # The autouse clock is frozen at 2024-01-15, so the window is open.
    assert cli.main(argv) == 1
    assert "closes after 2024-07-01" in capsys.readouterr().err
    assert not run_dir.labels_path.exists()


def test_cli_label_of_an_unknown_run_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["label", "nope", "--runs-dir", str(tmp_path)]) == 2
    assert "no such Run" in capsys.readouterr().err
