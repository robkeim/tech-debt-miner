"""Git history types and parsers for `git log` output. Nothing here runs `git`."""

from dataclasses import dataclass
from datetime import UTC, datetime


class GitError(RuntimeError):
    """A git command failed or the repo has no history as of the requested date."""


@dataclass(frozen=True)
class FileChange:
    """One path touched by a commit. `old_path` is set only when the file was renamed."""

    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class CommitChange:
    """A non-merge commit with its committer time and the paths it touched."""

    sha: str
    committed_at: datetime
    files: tuple[FileChange, ...]


@dataclass(frozen=True)
class LogEntry:
    """One commit of the full graph: its committer time (epoch seconds) and parent SHAs."""

    sha: str
    committed: int
    parents: tuple[str, ...]


def parse_graph_log(out: str) -> list[LogEntry]:
    """Parse `git log --format="%H %ct %P"` output."""
    entries: list[LogEntry] = []
    for line in out.splitlines():
        sha, stamp, *parents = line.split()
        entries.append(LogEntry(sha, int(stamp), tuple(parents)))
    return entries


def parse_commit_log(out: str) -> list[CommitChange]:
    """Parse `git log --name-status --format=%x00%H %ct` output."""
    commits: list[CommitChange] = []
    for block in out.split("\0")[1:]:
        header, *lines = block.splitlines()
        sha, stamp = header.split()
        files = tuple(_file_change(line) for line in lines if line)
        commits.append(CommitChange(sha, datetime.fromtimestamp(int(stamp), UTC), files))
    return commits


def _file_change(line: str) -> FileChange:
    status, *paths = line.split("\t")
    if status.startswith("R"):
        return FileChange(path=paths[1], old_path=paths[0])
    return FileChange(path=paths[0])
