"""The only code that shells out to `git` (ADR 0009).

A Target repo is cloned once and then only read. Every as-of function treats the Cutoff date as
midnight UTC and uses committer dates, so a commit dated on or after the Cutoff date is never
returned.
"""

import io
import os
import subprocess
import tarfile
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from tech_debt_miner.repo.cutoff import commits_in_range, pick_pinned_sha
from tech_debt_miner.repo.history import (
    CommitChange,
    FileChange,
    GitError,
    parse_commit_log,
    parse_graph_log,
)

__all__ = ["CommitChange", "FileChange", "GitError"]


def _git(*args: str, cwd: Path | None = None) -> bytes:
    """Run git with the user's and system's config ignored; return stdout."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-c", "core.quotepath=off", *args],  # noqa: S607 - git is resolved from PATH
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        msg = f"git {' '.join(args)} failed: {stderr}"
        raise GitError(msg)
    return result.stdout


def clone_repo(url: str, dest: Path) -> Path:
    """Clone `url` into `dest` unless it already holds a clone. Never fetches an existing one."""
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", "--", url, str(dest))
    return dest


def head_sha(repo: Path) -> str:
    """Return the commit SHA of `HEAD`."""
    return _git("rev-parse", "HEAD", cwd=repo).decode().strip()


def last_commit_touching(repo: Path, path: str) -> str:
    """Return the SHA of the newest commit that changed `path`."""
    sha = _git("log", "-1", "--format=%H", "--", path, cwd=repo).decode().strip()
    if not sha:
        msg = f"no commit touches {path}"
        raise GitError(msg)
    return sha


def resolve_pinned_sha(repo: Path, cutoff: date) -> str:
    """Return the newest first-parent commit before the Cutoff date whose history is all earlier."""
    out = _git("log", "--format=%H %ct %P", "HEAD", cwd=repo).decode()
    return pick_pinned_sha(parse_graph_log(out), cutoff)


def list_commits(repo: Path, since: date, until: date) -> list[CommitChange]:
    """Non-merge commits on the default branch committed in `[since, until)`, newest first.

    Renames are detected, so a renamed file carries its `old_path`. Pass the Cutoff date as
    `until` for as-of history.
    """
    out = _git(
        "log", "--no-merges", "-M", "--name-status", "--format=%x00%H %ct", "HEAD", cwd=repo
    ).decode()
    return commits_in_range(parse_commit_log(out), since, until)


@contextmanager
def export_tree(repo: Path, sha: str) -> Generator[Path]:
    """Export the tree at `sha` with `git archive` into a temporary directory, removed on exit."""
    archive = _git("archive", "--format=tar", sha, cwd=repo)
    with tempfile.TemporaryDirectory(prefix="tdm-tree-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        yield Path(tmp)
