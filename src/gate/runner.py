"""Run gate steps, keep going after failures, and print a summary."""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Status = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class Step:
    """One command in the gate.

    `argv[0]` is looked up with `resolve_tool`. `needs_ref` names a git ref that must
    exist locally; a missing ref fails the step instead of skipping it. `stdin` is piped
    to the command when set. `requires` lists helper tools the command shells out to
    (actionlint skips shell linting without shellcheck), so a missing one fails loudly
    instead of weakening the step.
    """

    name: str
    argv: tuple[str, ...]
    needs_ref: str | None = None
    requires: tuple[str, ...] = ()
    stdin: str | None = None


@dataclass(frozen=True)
class Skipped:
    """A step that does not apply, with the reason shown in the summary."""

    name: str
    reason: str


@dataclass(frozen=True)
class Result:
    name: str
    status: Status
    detail: str = ""


def resolve_tool(
    tool: str,
    *,
    which: Callable[[str], str | None] = shutil.which,
    venv_bin: Path | None = None,
) -> str | None:
    """Find an executable: the project venv first, then PATH, then `mise which`.

    Non-Python tools are pinned in `.tool-versions`, and a hook may run without mise
    activated, so ask mise before giving up.
    """
    bin_dir = venv_bin if venv_bin is not None else Path(sys.executable).parent
    candidate = bin_dir / tool
    if candidate.is_file():
        return str(candidate)
    found = which(tool)
    if found:
        return found
    mise = which("mise")
    if mise is None:
        return None
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [mise, "which", tool],
        capture_output=True,
        text=True,
        check=False,
    )
    path = result.stdout.strip()
    return path if result.returncode == 0 and path else None


Runner = Callable[[Sequence[str], str | None], int]
Resolver = Callable[[str], str | None]
RefCheck = Callable[[str], bool]


def mise_bin_paths(which: Callable[[str], str | None] = shutil.which) -> list[str]:
    """Bin directories of the tools pinned in `.tool-versions`, or none without mise.

    Tools such as actionlint look up helpers (shellcheck) on PATH, so the gate must
    expose the pinned tools the way CI's mise-action does, even when mise is not
    activated in the shell that launched the hook.
    """
    mise = which("mise")
    if mise is None:
        return []
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [mise, "bin-paths"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.split() if result.returncode == 0 else []


def run_argv(argv: Sequence[str], stdin: str | None = None) -> int:
    path = os.pathsep.join([*mise_bin_paths(), os.environ.get("PATH", "")])
    env = {**os.environ, "PATH": path}
    return subprocess.run(  # noqa: S603 - argv comes from Step
        argv, check=False, env=env, input=stdin, text=True
    ).returncode


def run_step(
    step: Step,
    *,
    run: Runner = run_argv,
    resolve: Resolver = resolve_tool,
    ref_exists: RefCheck,
) -> Result:
    """Run one step. A missing tool or ref fails loudly; nothing is skipped silently."""
    if step.needs_ref is not None and not ref_exists(step.needs_ref):
        return Result(
            step.name,
            "fail",
            f"{step.needs_ref} not found locally; run `git fetch origin main`",
        )
    resolved = {tool: resolve(tool) for tool in (step.argv[0], *step.requires)}
    for tool, path in resolved.items():
        if path is None:
            return Result(
                step.name,
                "fail",
                f"`{tool}` is not installed; run `mise install` or `uv sync`",
            )
    executable = resolved[step.argv[0]]
    assert executable is not None  # noqa: S101 - narrowed by the loop above
    code = run([executable, *step.argv[1:]], step.stdin)
    return Result(step.name, "pass" if code == 0 else "fail", f"exit {code}" if code else "")


def run_steps(
    steps: Sequence[Step | Skipped],
    *,
    ref_exists: RefCheck,
    run: Runner = run_argv,
    resolve: Resolver = resolve_tool,
    out: Callable[[str], None] = print,
) -> list[Result]:
    """Run every step even after a failure, then print a pass/fail summary."""
    results: list[Result] = []
    for step in steps:
        if isinstance(step, Skipped):
            results.append(Result(step.name, "skip", step.reason))
            continue
        out(f"\n==> {step.name}")
        results.append(run_step(step, run=run, resolve=resolve, ref_exists=ref_exists))
        if results[-1].status == "fail" and results[-1].detail:
            out(results[-1].detail)

    out("\nSummary")
    for result in results:
        suffix = f" ({result.detail})" if result.detail else ""
        out(f"  {result.status.upper():4}  {result.name}{suffix}")
    return results


def exit_code(results: Sequence[Result]) -> int:
    """Nonzero when any step failed."""
    return 1 if any(result.status == "fail" for result in results) else 0
