"""Generate a tiny git repo in a temp dir with fixed identities and dates.

Everything that feeds a commit hash is pinned, so the same commits always yield the
same SHAs. Nothing is committed to this repo as a `.git` directory or a bundle.
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gate.repo import run_git


@dataclass(frozen=True)
class Identity:
    name: str
    email: str


AUTHOR = Identity("Fixture Author", "author@example.com")
COMMITTER = Identity("Fixture Committer", "committer@example.com")
DEFAULT_DATE = datetime(2024, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Commit:
    """One commit: files to write (`None` deletes the file), a message and a date."""

    message: str
    files: Mapping[str, str | None]
    date: datetime


def git(repo: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    """Run git in `repo` with the user's and system's config ignored; return stdout.

    Ad hoc commits get the fixed identities and DEFAULT_DATE unless `env` overrides them.
    Inherited `GIT_*` variables are dropped: git hooks export `GIT_DIR` and `GIT_INDEX_FILE`,
    which would point these commands at the real repo instead of the fixture.
    """
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    isolated = {
        **inherited,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        **_commit_env(DEFAULT_DATE),
        **(env or {}),
    }
    return run_git(*args, cwd=repo, env=isolated, check=True).stdout


def _commit_env(date: datetime) -> dict[str, str]:
    if date.tzinfo is None:
        msg = "commit dates must be timezone-aware"
        raise ValueError(msg)
    stamp = date.isoformat()
    return {
        "GIT_AUTHOR_NAME": AUTHOR.name,
        "GIT_AUTHOR_EMAIL": AUTHOR.email,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_NAME": COMMITTER.name,
        "GIT_COMMITTER_EMAIL": COMMITTER.email,
        "GIT_COMMITTER_DATE": stamp,
    }


def build_fixture_repo(path: Path, commits: Sequence[Commit]) -> Path:
    """Create a repo at `path` (made if needed) holding `commits` in order."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet", "--initial-branch=main")
    for commit in commits:
        for name, content in commit.files.items():
            target = path / name
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(path, "add", "--all")
        git(
            path,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty",
            "--message",
            commit.message,
            env=_commit_env(commit.date),
        )
    return path


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()
