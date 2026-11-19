"""Find and launch the external tools the gate drives (venv, PATH, mise)."""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path


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
