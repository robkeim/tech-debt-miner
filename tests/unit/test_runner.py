from collections.abc import Sequence
from pathlib import Path

import pytest

from gate.runner import Result, Skipped, Step, exit_code, resolve_tool, run_step, run_steps

pytestmark = pytest.mark.unit


def no_ref(_ref: str) -> bool:
    return False


def any_ref(_ref: str) -> bool:
    return True


def found(tool: str) -> str:
    return f"/bin/{tool}"


def test_passing_step() -> None:
    calls: list[Sequence[str]] = []

    def run(argv: Sequence[str]) -> int:
        calls.append(argv)
        return 0

    result = run_step(Step("t", ("tool", "--flag")), run=run, resolve=found, ref_exists=any_ref)
    assert result == Result("t", "pass")
    assert calls == [["/bin/tool", "--flag"]]


def test_failing_step_reports_the_exit_code() -> None:
    result = run_step(Step("t", ("tool",)), run=lambda _argv: 3, resolve=found, ref_exists=any_ref)
    assert result == Result("t", "fail", "exit 3")


def test_missing_tool_fails_loudly() -> None:
    def run(_argv: Sequence[str]) -> int:
        pytest.fail("must not run a missing tool")

    result = run_step(
        Step("t", ("cspell",)), run=run, resolve=lambda _tool: None, ref_exists=any_ref
    )
    assert result.status == "fail"
    assert "`cspell` is not installed" in result.detail


def test_missing_ref_fails_instead_of_skipping() -> None:
    step = Step("t", ("tool",), needs_ref="origin/main")
    result = run_step(step, run=lambda _argv: 0, resolve=found, ref_exists=no_ref)
    assert result.status == "fail"
    assert "origin/main not found" in result.detail


def test_every_step_runs_after_a_failure_and_a_summary_prints() -> None:
    ran: list[str] = []

    def run(argv: Sequence[str]) -> int:
        ran.append(argv[0])
        return 1 if argv[0].endswith("first") else 0

    lines: list[str] = []
    results = run_steps(
        [Step("one", ("first",)), Skipped("two", "not needed"), Step("three", ("third",))],
        ref_exists=any_ref,
        run=run,
        resolve=found,
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


def test_resolve_prefers_the_venv(tmp_path: Path) -> None:
    (tmp_path / "ruff").write_text("")
    assert resolve_tool("ruff", which=lambda _t: "/elsewhere/ruff", venv_bin=tmp_path) == str(
        tmp_path / "ruff"
    )


def test_resolve_falls_back_to_path(tmp_path: Path) -> None:
    assert resolve_tool("cspell", which=lambda t: f"/usr/bin/{t}", venv_bin=tmp_path) == (
        "/usr/bin/cspell"
    )


def test_resolve_returns_none_without_mise(tmp_path: Path) -> None:
    assert resolve_tool("cspell", which=lambda _t: None, venv_bin=tmp_path) is None
