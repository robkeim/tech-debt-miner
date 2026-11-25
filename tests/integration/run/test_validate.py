from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import time_machine

from support.fixture_repo import Commit, build_fixture_repo
from tech_debt_miner import cli
from tech_debt_miner.repo import git as repo_git
from tech_debt_miner.repo.git import resolve_pinned_sha
from tech_debt_miner.run.artifacts import LABELS, MANIFEST, VALIDATION
from tech_debt_miner.run.label import CapMismatchError, LabelDeps, WindowOpenError, label
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.run.validate import render, validate
from tech_debt_miner.types import Manifest

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
AFTER_WINDOW = datetime(2024, 8, 1, tzinfo=UTC)
BODY = "def f():\n    return 1\n"
WIDE = {f"w{i}.py": BODY for i in range(12)}


def at(month: int, day: int) -> datetime:
    return datetime(2024, month, day, 12, tzinfo=UTC)


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    """Nine one-file fixes and one 12-file fix, so N is 1 and the wide fix is dropped by it."""
    commits = [Commit("base", {"a.py": BODY, **WIDE}, datetime(2023, 6, 1, tzinfo=UTC))]
    commits += [
        Commit(f"fix crash #{day}", {"a.py": BODY + f"# {day}\n"}, at(2, day))
        for day in range(1, 10)
    ]
    commits.append(Commit("fix wide change", dict.fromkeys(WIDE, BODY + "# 1\n"), at(3, 1)))
    commits.append(Commit("add feature", {"a.py": BODY + "# new\n"}, at(3, 2)))
    build_fixture_repo(tmp_path / "repos" / "target", commits)
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


def deps_for(repos_dir: Path) -> LabelDeps:
    return LabelDeps(repos_dir=repos_dir, clock=lambda: AFTER_WINDOW, update_clone=None)


def test_validate_computes_n_the_cap_report_and_the_sample(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)

    result = validate(run_dir, deps_for(repos_dir))

    assert run_dir.read(VALIDATION) == result
    assert result.cap_n == 1  # nine of ten fixes touch one file
    assert result.fix_commits_sized == 10
    assert [(r.max_files, r.fix_commits_dropped) for r in result.cap_report] == [
        (1, 1),
        (5, 1),
        (10, 1),
        (20, 0),
        (None, 0),
    ]
    assert len(result.sample) == 9
    assert {item.files for item in result.sample} == {("a.py",)}
    assert all("a.py" in item.diff_stat for item in result.sample)
    assert {ref for item in result.sample for ref in item.issue_references} == {
        f"#{day}" for day in range(1, 10)
    }
    assert result.fetched is False


def test_validate_does_not_write_labels(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    validate(run_dir, deps_for(repos_dir))
    assert not run_dir.exists(LABELS)


def test_validate_is_the_same_on_every_run(tmp_path: Path, repos_dir: Path) -> None:
    first = validate(make_run(tmp_path / "one", repos_dir), deps_for(repos_dir))
    second = validate(make_run(tmp_path / "two", repos_dir), deps_for(repos_dir))
    assert first == second


def test_validate_never_overwrites_n(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    validate(run_dir, deps_for(repos_dir))

    with pytest.raises(FileExistsError, match="N is fixed"):
        validate(run_dir, deps_for(repos_dir))


def test_validate_refuses_until_the_window_has_closed(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    deps = LabelDeps(
        repos_dir=repos_dir, clock=lambda: datetime(2024, 3, 1, tzinfo=UTC), update_clone=None
    )

    with pytest.raises(WindowOpenError):
        validate(run_dir, deps)

    assert not run_dir.exists(VALIDATION)


def test_validate_without_fixes_has_no_n_and_an_empty_sheet(tmp_path: Path) -> None:
    build_fixture_repo(
        tmp_path / "repos" / "target",
        [Commit("base", {"a.py": BODY}, datetime(2023, 6, 1, tzinfo=UTC))],
    )
    repos_dir = tmp_path / "repos"
    run_dir = make_run(tmp_path, repos_dir)

    result = validate(run_dir, deps_for(repos_dir))

    assert result.cap_n is None
    assert result.sample == ()
    assert [r.max_files for r in result.cap_report] == [5, 10, 20, None]
    assert "none, no Fix commit" in render(run_dir.read(MANIFEST), result)


def test_render_lists_n_the_cap_table_and_each_sampled_commit(
    tmp_path: Path, repos_dir: Path
) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    result = validate(run_dir, deps_for(repos_dir))

    text = render(run_dir.read(MANIFEST), result)

    assert "# Validation for owner/target at 2024-01-01" in text
    assert "(90th percentile of 10 fix sizes): 1" in text
    assert "| N = 1 | 1 | 1 | 9 |" in text
    assert "| uncapped | 0 | 13 | 21 |" in text
    assert text.count("- Real fix: yes / no") == 9
    assert "Issue references: #" in text
    assert "fix crash #" in text


def test_cli_validate_prints_the_sheet_and_writes_validation_json(
    tmp_path: Path,
    repos_dir: Path,
    frozen_clock: time_machine.Traveller,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frozen_clock.move_to(AFTER_WINDOW)
    run_dir = make_run(tmp_path, repos_dir)
    argv = [
        "validate",
        run_dir.id,
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
        "--no-fetch",
    ]

    assert cli.main(argv) == 0
    assert "## Review sheet (9 Fix commits" in capsys.readouterr().out
    assert run_dir.exists(VALIDATION)

    assert cli.main(argv) == 1
    assert "N is fixed" in capsys.readouterr().err


def test_cli_validate_refuses_while_the_window_is_open(
    tmp_path: Path, repos_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    argv = [
        "validate",
        run_dir.id,
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]

    assert cli.main(argv) == 1
    assert "closes after 2024-07-01" in capsys.readouterr().err
    assert not run_dir.exists(VALIDATION)


def test_cli_validate_of_an_unknown_run_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["validate", "nope", "--runs-dir", str(tmp_path)]) == 2
    assert "no such Run" in capsys.readouterr().err


def test_diff_stat_is_the_stat_without_the_message(repos_dir: Path) -> None:
    clone = repos_dir / "target"
    wide = next(c for c in repo_git.list_commits(clone, date(2024, 3, 1), date(2024, 3, 2)))

    stat = repo_git.diff_stat(clone, wide.sha)

    assert "w0.py" in stat
    assert "12 files changed" in stat
    assert "fix wide change" not in stat


def test_label_must_use_the_n_that_validate_fixed(tmp_path: Path, repos_dir: Path) -> None:
    run_dir = make_run(tmp_path, repos_dir)
    validate(run_dir, deps_for(repos_dir))

    for wrong in (None, 5):
        deps = LabelDeps(
            repos_dir=repos_dir, clock=lambda: AFTER_WINDOW, update_clone=None, max_files=wrong
        )
        with pytest.raises(CapMismatchError, match=r"validation.json \(1\)"):
            label(run_dir, deps)
    assert not run_dir.exists(LABELS)

    deps = LabelDeps(
        repos_dir=repos_dir, clock=lambda: AFTER_WINDOW, update_clone=None, max_files=1
    )
    assert label(run_dir, deps).stats["fix_commits_dropped_by_cap"] == 1


def test_cli_label_reports_a_wrong_n(
    tmp_path: Path,
    repos_dir: Path,
    frozen_clock: time_machine.Traveller,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frozen_clock.move_to(AFTER_WINDOW)
    run_dir = make_run(tmp_path, repos_dir)
    validate(run_dir, deps_for(repos_dir))
    argv = [
        "label",
        run_dir.id,
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]

    assert cli.main([*argv, "--no-fetch"]) == 1
    assert "must be the N" in capsys.readouterr().err
