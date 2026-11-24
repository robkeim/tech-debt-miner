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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path


class GitError(RuntimeError):
    """A git command failed or the repo has no history as of the requested date."""


@dataclass(frozen=True)
class FileChange:
    """One path touched by a commit. `old_path` is set only when the file was renamed."""

    path: str
    old_path: str | None = None
    deleted: bool = False


@dataclass(frozen=True)
class CommitChange:
    """A non-merge commit with its committer time, author, message and the paths it touched."""

    sha: str
    committed_at: datetime
    files: tuple[FileChange, ...]
    author_name: str = ""
    author_email: str = ""
    message: str = ""


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


def _midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


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
    """Return the newest first-parent commit before the Cutoff date whose history is all earlier.

    A candidate is committed before the Cutoff date and has no ancestor committed on or after it
    (for example a late-dated side-branch commit that was merged in, or clock skew). If a
    candidate fails that check, step back along the first-parent line to the next earlier
    candidate and check again. This walks the full ancestry of each candidate tried.
    """
    limit = _midnight_utc(cutoff).timestamp()
    out = _git("log", "--first-parent", "--format=%H %ct", "HEAD", cwd=repo).decode()
    for line in out.splitlines():
        sha, stamp = line.split()
        if int(stamp) < limit and _newest_commit_time(repo, sha) < limit:
            return sha
    msg = f"no commit before {cutoff.isoformat()} with only earlier history"
    raise GitError(msg)


def _newest_commit_time(repo: Path, sha: str) -> int:
    """Return the latest committer time among `sha` and all its ancestors."""
    out = _git("log", "--format=%ct", sha, cwd=repo).decode()
    return max(int(stamp) for stamp in out.split())


def list_commits(repo: Path, since: date, until: date) -> list[CommitChange]:
    """Non-merge commits on the default branch committed in `[since, until)`, newest first.

    Renames are detected, so a renamed file carries its `old_path`. Pass the Cutoff date as
    `until` for as-of history. Nothing here clamps `until`: the caller owns keeping a window off
    post-Cutoff commits.
    """
    start = _midnight_utc(since).timestamp()
    end = _midnight_utc(until).timestamp()
    out = _git(
        "log",
        "--no-merges",
        "-M",
        "--name-status",
        "--format=%x00%H%x01%ct%x01%an%x01%ae%x01%B%x01",
        "HEAD",
        cwd=repo,
    ).decode()
    commits: list[CommitChange] = []
    for block in out.split("\0")[1:]:
        sha, stamp, name, email, message, status = block.split("\x01")
        if not start <= int(stamp) < end:
            continue
        files = tuple(_file_change(line) for line in status.splitlines() if line)
        commits.append(
            CommitChange(
                sha,
                datetime.fromtimestamp(int(stamp), UTC),
                files,
                author_name=name,
                author_email=email,
                message=message.strip(),
            )
        )
    return commits


def _file_change(line: str) -> FileChange:
    status, *paths = line.split("\t")
    if status.startswith("R"):
        return FileChange(path=paths[1], old_path=paths[0])
    if status == "D":
        return FileChange(path=paths[0], deleted=True)
    return FileChange(path=paths[0])


def list_files(repo: Path, sha: str) -> list[str]:
    """Return every file path in the tree at `sha`."""
    out = _git("ls-tree", "-r", "--name-only", "-z", sha, cwd=repo).decode()
    return [path for path in out.split("\0") if path]


@contextmanager
def export_tree(repo: Path, sha: str) -> Generator[Path]:
    """Export the tree at `sha` with `git archive` into a temporary directory, removed on exit."""
    archive = _git("archive", "--format=tar", sha, cwd=repo)
    with tempfile.TemporaryDirectory(prefix="tdm-tree-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        yield Path(tmp)
