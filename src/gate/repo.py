"""Read-only git queries the gate needs to decide which steps apply."""

import subprocess
from collections.abc import Mapping
from pathlib import Path

MAIN_REF = "origin/main"
WORKFLOWS = ".github/workflows"


def run_git(
    *args: str, cwd: Path, env: Mapping[str, str] | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run git in `cwd` and capture text output. `env` replaces the environment when set."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args],  # noqa: S607 - git is resolved from PATH on purpose
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def staged_files(cwd: Path) -> list[str]:
    """Paths added, copied, modified or renamed in the index."""
    result = run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", cwd=cwd)
    return result.stdout.splitlines()


def ref_exists(ref: str, cwd: Path) -> bool:
    """Whether `ref` resolves locally. Never fetches."""
    return run_git("rev-parse", "--verify", "--quiet", ref, cwd=cwd).returncode == 0


def workflows_changed_since(ref: str, cwd: Path) -> bool:
    """Whether the branch touches workflow files relative to `ref`.

    A missing ref counts as changed, so the workflow linters err toward running.
    """
    if not ref_exists(ref, cwd):
        return True
    result = run_git("diff", "--name-only", f"{ref}...HEAD", "--", WORKFLOWS, cwd=cwd)
    return bool(result.stdout.strip())
