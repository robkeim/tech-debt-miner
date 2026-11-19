from collections.abc import Sequence
from pathlib import Path

import pytest

from gate.models import Result, Skipped, Step
from gate.runner import (
    Environment,
    RefCheck,
    Resolver,
    Runner,
    exit_code,
    run_step,
    run_steps,
)

pytestmark = pytest.mark.unit

ROOT = Path("/repo")


def no_ref(_ref: str, _root: Path) -> bool:
    return False


def any_ref(_ref: str, _root: Path) -> bool:
    return True


def found(tool: str) -> str:
    return f"/bin/{tool}"


def environment(
    *,
    run: Runner | None = None,
    resolve: Resolver = found,
    ref_exists: RefCheck = any_ref,
) -> Environment:
    return Environment(
        ROOT, run=run or (lambda _argv, _stdin: 0), resolve=resolve, ref_exists=ref_exists
    )


def test_passing_step() -> None:
    calls: list[Sequence[str]] = []

    def run(argv: Sequence[str], _stdin: str | None) -> int:
        calls.append(argv)
        return 0

    result = run_step(Step("t", ("tool", "--flag")), environment(run=run))
    assert result == Result("t", "pass")
    assert calls == [["/bin/tool", "--flag"]]


def test_failing_step_reports_the_exit_code() -> None:
    result = run_step(Step("t", ("tool",)), environment(run=lambda _argv, _stdin: 3))
    assert result == Result("t", "fail", "exit 3")


def test_missing_tool_fails_loudly() -> None:
    def run(_argv: Sequence[str], _stdin: str | None) -> int:
        pytest.fail("must not run a missing tool")

    result = run_step(Step("t", ("cspell",)), environment(run=run, resolve=lambda _tool: None))
    assert result.status == "fail"
    assert "`cspell` is not installed" in result.detail


def test_missing_helper_tool_fails_loudly() -> None:
    def resolve(tool: str) -> str | None:
        return None if tool == "shellcheck" else f"/bin/{tool}"

    step = Step("actionlint", ("actionlint",), requires=("shellcheck",))
    result = run_step(step, environment(resolve=resolve))
    assert result.status == "fail"
    assert "`shellcheck` is not installed" in result.detail


def test_missing_ref_fails_instead_of_skipping() -> None:
    step = Step("t", ("tool",), needs_ref="origin/main")
    result = run_step(step, environment(ref_exists=no_ref))
    assert result.status == "fail"
    assert "origin/main not found" in result.detail


def test_ref_checks_query_the_environment_root() -> None:
    asked: list[tuple[str, Path]] = []

    def ref_exists(ref: str, root: Path) -> bool:
        asked.append((ref, root))
        return True

    run_step(Step("t", ("tool",), needs_ref="origin/main"), environment(ref_exists=ref_exists))
    assert asked == [("origin/main", ROOT)]


def test_every_step_runs_after_a_failure_and_a_summary_prints() -> None:
    ran: list[str] = []

    def run(argv: Sequence[str], _stdin: str | None) -> int:
        ran.append(argv[0])
        return 1 if argv[0].endswith("first") else 0

    lines: list[str] = []
    results = run_steps(
        [Step("one", ("first",)), Skipped("two", "not needed"), Step("three", ("third",))],
        environment(run=run),
        out=lines.append,
    )
    assert ran == ["/bin/first", "/bin/third"]
    assert [result.status for result in results] == ["fail", "skip", "pass"]
    assert "  FAIL  one (exit 1)" in lines
    assert "  SKIP  two (not needed)" in lines
    assert "  PASS  three" in lines
    assert exit_code(results) == 1


def test_exit_code_is_zero_when_nothing_failed() -> None:
    assert exit_code([Result("a", "pass"), Result("b", "skip")]) == 0
