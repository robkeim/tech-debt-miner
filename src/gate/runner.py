"""Run gate steps and keep going after failures. Tool discovery lives in `gate.tools`."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from gate import repo
from gate.models import Result, Skipped, Step
from gate.summary import print_summary
from gate.tools import resolve_tool, run_argv

Runner = Callable[[Sequence[str], str | None], int]
Resolver = Callable[[str], str | None]
RefCheck = Callable[[str, Path], bool]


@dataclass(frozen=True)
class Environment:
    """What steps run against: the repo `root` and how to launch, find and check things.

    The defaults are the real implementations; tests swap in fakes.
    """

    root: Path
    run: Runner = run_argv
    resolve: Resolver = resolve_tool
    ref_exists: RefCheck = repo.ref_exists


def run_step(step: Step, env: Environment) -> Result:
    """Run one step. A missing tool or ref fails loudly; nothing is skipped silently."""
    if step.needs_ref is not None and not env.ref_exists(step.needs_ref, env.root):
        return Result(
            step.name,
            "fail",
            f"{step.needs_ref} not found locally; run `git fetch origin main`",
        )
    resolved = {tool: env.resolve(tool) for tool in (step.argv[0], *step.requires)}
    for tool, path in resolved.items():
        if path is None:
            return Result(
                step.name,
                "fail",
                f"`{tool}` is not installed; run `mise install` or `uv sync`",
            )
    executable = resolved[step.argv[0]]
    assert executable is not None  # noqa: S101 - narrowed by the loop above
    code = env.run([executable, *step.argv[1:]], step.stdin)
    return Result(step.name, "pass" if code == 0 else "fail", f"exit {code}" if code else "")


def run_steps(
    steps: Sequence[Step | Skipped],
    env: Environment,
    out: Callable[[str], None] = print,
) -> list[Result]:
    """Run every step even after a failure, then print a pass/fail summary."""
    results: list[Result] = []
    for step in steps:
        if isinstance(step, Skipped):
            results.append(Result(step.name, "skip", step.reason))
            continue
        out(f"\n==> {step.name}")
        results.append(run_step(step, env))
        if results[-1].status == "fail" and results[-1].detail:
            out(results[-1].detail)
    print_summary(results, out)
    return results


def exit_code(results: Sequence[Result]) -> int:
    """Nonzero when any step failed."""
    return 1 if any(result.status == "fail" for result in results) else 0
