"""The gate's steps, per mode. See CONTRIBUTING.md#gate-and-git-hooks."""

from collections.abc import Sequence
from pathlib import Path

from gate.repo import MAIN_REF, WORKFLOWS
from gate.runner import Skipped, Step

SPELLCHECKED = (".py", ".md", ".yml", ".yaml", ".toml", ".json")
SPELLCHECK_GLOBS = tuple(f"**/*{suffix}" for suffix in SPELLCHECKED)
DIFF_COVER_FLOOR = "90"

_FORMAT = Step("ruff format", ("ruff", "format", "--check", "."))
_LINT = Step("ruff check", ("ruff", "check", "."))
_TYPES = Step("pyright", ("pyright",))
_TESTS = Step("pytest", ("pytest", "--cov", "--cov-report=xml"))
_DIFF_COVER = Step(
    "diff-cover",
    (
        "diff-cover",
        "coverage.xml",
        f"--compare-branch={MAIN_REF}",
        f"--fail-under={DIFF_COVER_FLOOR}",
    ),
    needs_ref=MAIN_REF,
)
_CSPELL_ALL = Step("cspell", ("cspell", "--no-progress", "--no-must-find-files", *SPELLCHECK_GLOBS))
_LYCHEE = Step("lychee", ("lychee", "--offline", "--include-fragments", "--no-progress", "**/*.md"))
_ACTIONLINT = Step("actionlint", ("actionlint",))
_ZIZMOR = Step("zizmor", ("zizmor", "--offline", WORKFLOWS))

FIX_STEPS = (
    Step("ruff format", ("ruff", "format", ".")),
    Step("ruff check --fix", ("ruff", "check", "--fix", ".")),
)
INSTALL_STEPS = (
    Step(
        "pre-commit install",
        (
            "pre-commit",
            "install",
            "--hook-type",
            "pre-commit",
            "--hook-type",
            "commit-msg",
            "--hook-type",
            "pre-push",
        ),
    ),
)


def _is_workflow(path: str) -> bool:
    return path.startswith(f"{WORKFLOWS}/")


def fast_steps(staged: Sequence[str], root: Path) -> list[Step | Skipped]:
    """Return the pre-commit hook steps. Spelling covers staged files only."""
    spellable = [path for path in staged if path.endswith(SPELLCHECKED) and (root / path).is_file()]
    steps: list[Step | Skipped] = [_FORMAT, _LINT, _TYPES]
    if spellable:
        steps.append(Step("cspell", ("cspell", "--no-progress", *spellable)))
    else:
        steps.append(Skipped("cspell", "no staged files to check"))
    steps.extend(_workflow_steps(run=any(_is_workflow(path) for path in staged)))
    return steps


def full_steps(*, workflows_changed: bool, in_ci: bool) -> list[Step | Skipped]:
    """Return the pre-push and CI steps. Workflow linters run in CI or when relevant."""
    return [
        _FORMAT,
        _LINT,
        _TYPES,
        _TESTS,
        _DIFF_COVER,
        _CSPELL_ALL,
        _LYCHEE,
        *_workflow_steps(run=in_ci or workflows_changed),
    ]


def _workflow_steps(*, run: bool) -> list[Step | Skipped]:
    if run:
        return [_ACTIONLINT, _ZIZMOR]
    return [
        Skipped("actionlint", "no workflow changes"),
        Skipped("zizmor", "no workflow changes"),
    ]
