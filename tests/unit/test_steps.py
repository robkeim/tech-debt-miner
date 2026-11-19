from pathlib import Path

import pytest

from gate.runner import Skipped, Step
from gate.steps import fast_steps, full_steps

pytestmark = pytest.mark.unit


def names(steps: list[Step | Skipped]) -> list[str]:
    return [step.name for step in steps]


def skipped(steps: list[Step | Skipped]) -> list[str]:
    return [step.name for step in steps if isinstance(step, Skipped)]


def test_fast_runs_the_python_checks_and_skips_the_rest(tmp_path: Path) -> None:
    steps = fast_steps([], tmp_path)
    assert names(steps) == [
        "ruff format",
        "ruff check",
        "pyright",
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


def test_full_runs_everything_in_ci() -> None:
    steps = full_steps(workflows_changed=False, in_ci=True)
    assert names(steps) == [
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


def test_full_skips_workflow_linters_locally_without_workflow_changes() -> None:
    steps = full_steps(workflows_changed=False, in_ci=False)
    assert skipped(steps) == ["actionlint", "zizmor"]


def test_full_runs_workflow_linters_locally_when_workflows_changed() -> None:
    assert skipped(full_steps(workflows_changed=True, in_ci=False)) == []


def test_diff_cover_requires_the_main_ref() -> None:
    diff_cover = next(
        s for s in full_steps(workflows_changed=False, in_ci=True) if s.name == "diff-cover"
    )
    assert isinstance(diff_cover, Step)
    assert diff_cover.needs_ref == "origin/main"
    assert "--fail-under=90" in diff_cover.argv
