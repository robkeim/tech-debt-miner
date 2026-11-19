from collections.abc import Sequence
from pathlib import Path

import pytest

from gate import cli
from gate.runner import Result, Skipped, Status, Step

pytestmark = pytest.mark.unit


class Recorder:
    """Stands in for `run_steps` so no real tool runs."""

    def __init__(self, status: Status = "pass") -> None:
        self.status: Status = status
        self.steps: list[Step | Skipped] = []
        self.kwargs: dict[str, object] = {}

    def __call__(self, steps: Sequence[Step | Skipped], **kwargs: object) -> list[Result]:
        self.steps = list(steps)
        self.kwargs = kwargs
        return [Result("x", self.status)]


def no_staged_files(_root: Path) -> list[str]:
    return []


def no_workflow_changes(_ref: str, _root: Path) -> bool:
    return False


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(cli, "run_steps", recorder)
    monkeypatch.setattr(cli.repo, "staged_files", no_staged_files)
    monkeypatch.setattr(cli.repo, "workflows_changed_since", no_workflow_changes)
    return recorder


def names(recorder: Recorder) -> list[str]:
    return [step.name for step in recorder.steps]


def test_commit_msg_accepts_a_valid_message(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: add ranking\n", encoding="utf-8")
    assert cli.main(["commit-msg", str(message)]) == 0


def test_commit_msg_rejects_an_invalid_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Added stuff.\n", encoding="utf-8")
    assert cli.main(["commit-msg", str(message)]) == 1
    assert "commit message is invalid" in capsys.readouterr().err


def test_pr_title_accepts_a_valid_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_TITLE", "ci: add workflows and dependabot config")
    assert cli.main(["pr-title"]) == 0


def test_pr_title_rejects_an_invalid_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PR_TITLE", "Fix the thing")
    assert cli.main(["pr-title"]) == 1
    assert "PR title is invalid" in capsys.readouterr().err


def test_pr_title_fails_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PR_TITLE", raising=False)
    assert cli.main(["pr-title"]) == 1
    assert "PR_TITLE is not set" in capsys.readouterr().err


def test_fast_runs_the_fast_steps(recorder: Recorder) -> None:
    assert cli.main(["--fast"]) == 0
    assert names(recorder)[:3] == ["ruff format", "ruff check", "pyright"]
    assert "pytest" not in names(recorder)


def test_default_runs_the_full_gate(recorder: Recorder) -> None:
    assert cli.main([]) == 0
    assert {"pytest", "diff-cover", "lychee"} <= set(names(recorder))


def test_ci_env_runs_the_workflow_linters(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    cli.main([])
    assert not any(isinstance(step, Skipped) for step in recorder.steps)


def test_failing_step_gives_a_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_steps", Recorder(status="fail"))
    monkeypatch.setattr(cli.repo, "workflows_changed_since", no_workflow_changes)
    assert cli.main([]) == 1


def test_ref_checks_query_the_working_directory(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[str, Path]] = []

    def ref_exists(ref: str, root: Path) -> bool:
        asked.append((ref, root))
        return True

    monkeypatch.setattr(cli.repo, "ref_exists", ref_exists)
    cli.main([])
    check = recorder.kwargs["ref_exists"]
    assert callable(check)
    assert check("origin/main") is True
    assert asked == [("origin/main", Path.cwd())]


def test_fix_applies_ruff_fixes(recorder: Recorder) -> None:
    assert cli.main(["--fix"]) == 0
    assert names(recorder) == ["ruff format", "ruff check --fix"]


def test_install_installs_all_three_hook_stages(recorder: Recorder) -> None:
    assert cli.main(["install"]) == 0
    (step,) = recorder.steps
    assert isinstance(step, Step)
    hook_types = [step.argv[i + 1] for i, arg in enumerate(step.argv) if arg == "--hook-type"]
    assert hook_types == ["pre-commit", "commit-msg", "pre-push"]


@pytest.mark.parametrize(
    "argv", [["--fast", "--fix"], ["--fast", "install"], ["--fix", "pr-title"]]
)
def test_conflicting_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2
