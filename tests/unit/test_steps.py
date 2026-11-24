from pathlib import Path

import pytest

from gate.models import Skipped, Step
from gate.repo import MAIN_REF
from gate.steps import DIFF_COVER_FLOOR, WorkflowLint, fast_steps, full_steps
from support.steps import step_names

pytestmark = pytest.mark.unit


def skipped(steps: list[Step | Skipped]) -> list[str]:
    return [step.name for step in steps if isinstance(step, Skipped)]


def test_workflow_lint_when_maps_a_condition_to_a_mode() -> None:
    assert WorkflowLint.when(True) is WorkflowLint.RUN  # noqa: FBT003
    assert WorkflowLint.when(False) is WorkflowLint.SKIP  # noqa: FBT003


def test_fast_runs_the_python_checks_and_skips_the_rest(tmp_path: Path) -> None:
    steps = fast_steps([], tmp_path)
    assert step_names(steps) == [
        "ruff format",
        "ruff check",
        "pyright",
        "adr numbers",
        "cspell",
        "actionlint",
        "zizmor",
    ]
    assert skipped(steps) == ["cspell", "actionlint", "zizmor"]


def test_fast_spellchecks_only_staged_text_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.md").write_text("")
    (tmp_path / "image.png").write_text("")
    steps = fast_steps(["a.py", "b.md", "image.png", "gone.md"], tmp_path)
    cspell = next(step for step in steps if step.name == "cspell")
    assert isinstance(cspell, Step)
    assert cspell.argv == ("cspell", "--no-progress", "a.py", "b.md")


def test_fast_runs_workflow_linters_when_a_workflow_is_staged(tmp_path: Path) -> None:
    steps = fast_steps([".github/workflows/ci.yml"], tmp_path)
    assert skipped(steps) == ["cspell"]


def test_full_runs_everything_when_workflow_linters_run() -> None:
    steps = full_steps(WorkflowLint.RUN)
    assert step_names(steps) == [
        "ruff format",
        "ruff check",
        "pyright",
        "pytest",
        "diff-cover",
        "cspell",
        "lychee",
        "actionlint",
        "zizmor",
    ]
    assert skipped(steps) == []


def test_full_skips_workflow_linters_when_told_to() -> None:
    assert skipped(full_steps(WorkflowLint.SKIP)) == ["actionlint", "zizmor"]


def test_actionlint_requires_shellcheck() -> None:
    steps = full_steps(WorkflowLint.RUN)
    actionlint = next(s for s in steps if s.name == "actionlint")
    assert isinstance(actionlint, Step)
    assert actionlint.requires == ("shellcheck",)


def test_diff_cover_requires_the_main_ref() -> None:
    diff_cover = next(s for s in full_steps(WorkflowLint.RUN) if s.name == "diff-cover")
    assert isinstance(diff_cover, Step)
    assert diff_cover.needs_ref == MAIN_REF
    assert f"--fail-under={DIFF_COVER_FLOOR}" in diff_cover.argv
