"""The `label` stage: count Fix commits per file in the closed Label window (ADR 0004, ADR 0008)."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from tech_debt_miner import labels
from tech_debt_miner.repo import git
from tech_debt_miner.repo.history import GitError
from tech_debt_miner.run.artifacts import LABELS, MANIFEST
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Labels


class WindowOpenError(RuntimeError):
    """The Label window has not closed yet, so the Label would be incomplete (ADR 0005)."""


class CloneUpdateError(RuntimeError):
    """The Target repo clone could not be fast-forwarded, e.g. upstream history was rewritten."""


@dataclass(frozen=True)
class LabelDeps:
    """Injected collaborators."""

    repos_dir: Path
    clock: Callable[[], datetime]
    # Brings the clone up to date, fast-forward only; None skips the update (`--no-fetch`).
    update_clone: Callable[[Path], None] | None
    max_files: int | None = None  # the fix-size cap N; None is uncapped


def label(run_dir: RunDir, deps: LabelDeps) -> Labels:
    """Write `labels.json` for the Run, or raise `WindowOpenError` while the window is open.

    The window is `(Cutoff date, Cutoff date + 6 months]` by date. It starts the day after the
    Cutoff date and ends after its last day, so it can never include a commit the as-of
    functions return, and the Cutoff day itself is in neither. Labels are scoring input only and
    never reach a prompt. The clone is fast-forwarded first unless `update_clone` is None, and
    `labels.json` records the clone's HEAD, its newest commit date and whether an update ran.
    """
    if run_dir.exists(LABELS):
        msg = f"{LABELS.path(None)} already exists; N is fixed before any scored Run"
        raise FileExistsError(msg)
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
    result = labels.build_labels(
        commits, git.list_files(clone, manifest.pinned_sha), deps.max_files
    )
    result = replace(
        result,
        clone_head=git.head_sha(clone),
        clone_newest_commit=git.head_committed_at(clone).isoformat(),
        fetched=deps.update_clone is not None,
    )
    run_dir.write(LABELS, result)
    return result
