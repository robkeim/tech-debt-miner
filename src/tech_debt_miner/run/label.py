"""The `label` stage: count Fix commits per file in the closed Label window (ADR 0004, ADR 0008)."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from tech_debt_miner import labels
from tech_debt_miner.repo import git
from tech_debt_miner.repo.history import CommitChange, GitError
from tech_debt_miner.run.artifacts import LABELS, MANIFEST, VALIDATION
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Labels


class WindowOpenError(RuntimeError):
    """The Label window has not closed yet, so the Label would be incomplete (ADR 0005)."""


class CloneUpdateError(RuntimeError):
    """The Target repo clone could not be fast-forwarded, e.g. upstream history was rewritten."""


class CapMismatchError(ValueError):
    """`--max-files` differs from the N that `validate` fixed for the Run."""


@dataclass(frozen=True)
class LabelDeps:
    """Injected collaborators."""

    repos_dir: Path
    clock: Callable[[], datetime]
    # Brings the clone up to date, fast-forward only; None skips the update (`--no-fetch`).
    update_clone: Callable[[Path], None] | None
    max_files: int | None = None  # the fix-size cap N; None is uncapped


@dataclass(frozen=True)
class LabelWindow:
    """What the Label window holds: the clone and its non-merge commits, newest first."""

    clone: Path
    commits: list[CommitChange]
    cutoff_files: list[str]  # every path in the tree at the Pinned SHA


def read_window(run_dir: RunDir, deps: LabelDeps) -> LabelWindow:
    """Read the closed Label window, fast-forwarding the clone first unless told not to.

    The window is `(Cutoff date, Cutoff date + 6 months]` by date. It starts the day after the
    Cutoff date and ends after its last day, so it can never include a commit the as-of
    functions return, and the Cutoff day itself is in neither. Raises `WindowOpenError` while
    the window is open and `CloneUpdateError` when the clone cannot be fast-forwarded.
    """
    manifest = run_dir.read(MANIFEST)
    cutoff = date.fromisoformat(manifest.cutoff_date)
    today = deps.clock().date()
    if not labels.window_is_closed(cutoff, today):
        msg = f"the Label window closes after {labels.window_end(cutoff)}; today is {today}"
        raise WindowOpenError(msg)
    clone = deps.repos_dir / manifest.target_repo.rsplit("/", 1)[-1]
    if deps.update_clone is not None:
        try:
            deps.update_clone(clone)
        except GitError as error:
            msg = f"cannot fast-forward the clone (pass --no-fetch to skip the update): {error}"
            raise CloneUpdateError(msg) from error
    commits = git.list_commits(
        clone, labels.window_start(cutoff), labels.window_end(cutoff) + timedelta(days=1)
    )
    return LabelWindow(clone, commits, git.list_files(clone, manifest.pinned_sha))


def label(run_dir: RunDir, deps: LabelDeps) -> Labels:
    """Write `labels.json` for the Run, or raise `WindowOpenError` while the window is open.

    Labels are scoring input only and never reach a prompt. `labels.json` records the clone's
    HEAD, its newest commit date and whether an update ran (see `read_window`).
    """
    if run_dir.exists(LABELS):
        msg = f"{LABELS.path(None)} already exists; N is fixed before any scored Run"
        raise FileExistsError(msg)
    if run_dir.exists(VALIDATION) and run_dir.read(VALIDATION).cap_n != deps.max_files:
        msg = (
            f"--max-files must be the N in validation.json ({run_dir.read(VALIDATION).cap_n}); "
            "N is fixed before any scored Run"
        )
        raise CapMismatchError(msg)
    window = read_window(run_dir, deps)
    result = labels.build_labels(window.commits, window.cutoff_files, deps.max_files)
    result = replace(
        result,
        clone_head=git.head_sha(window.clone),
        clone_newest_commit=git.head_committed_at(window.clone).isoformat(),
        fetched=deps.update_clone is not None,
    )
    run_dir.write(LABELS, result)
    return result
