"""The `label` stage: count Fix commits per file in the closed Label window (ADR 0004, ADR 0008)."""

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from tech_debt_miner import labels
from tech_debt_miner.repo import git
from tech_debt_miner.repo.history import CommitChange, GitError
from tech_debt_miner.run.artifacts import LABELS, LABELS_12M, MANIFEST, VALIDATION
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Labels, LateLabels


class WindowOpenError(RuntimeError):
    """The Label window has not closed yet, so the Label would be incomplete (ADR 0005)."""


class LabelMissingError(RuntimeError):
    """`label` has not run, so there is nothing to score against or add to."""


class CloneUpdateError(RuntimeError):
    """The Target repo clone could not be fast-forwarded, e.g. upstream history was rewritten."""


class CapMismatchError(ValueError):
    """`--max-files` differs from the N that `validate` fixed for the Run."""


# `owner/name` -> the numbers of its issues that are closed and typed Bug right now.
ClosedBugs = Callable[[str], Collection[int]]


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
    later_commits: list[CommitChange]  # after the 6-month window, up to 12 months
    long_window_closed: bool  # the 12-month window has closed, so an empty `later_commits` is real


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
    long_window_closed = labels.window_is_closed(cutoff, today, labels.LONG_WINDOW_MONTHS)
    later = (
        git.list_commits(
            clone,
            labels.window_end(cutoff) + timedelta(days=1),
            labels.window_end(cutoff, labels.LONG_WINDOW_MONTHS) + timedelta(days=1),
        )
        if long_window_closed
        else []
    )
    return LabelWindow(
        clone, commits, git.list_files(clone, manifest.pinned_sha), later, long_window_closed
    )


def _check_cap(run_dir: RunDir, deps: LabelDeps) -> None:
    """Raise `CapMismatchError` unless `--max-files` is the N that `validate` fixed, if it ran."""
    if run_dir.exists(VALIDATION) and run_dir.read(VALIDATION).cap_n != deps.max_files:
        msg = (
            f"--max-files must be the N in validation.json ({run_dir.read(VALIDATION).cap_n}); "
            "N is fixed before any scored Run"
        )
        raise CapMismatchError(msg)


def label(run_dir: RunDir, deps: LabelDeps, closed_bugs: ClosedBugs) -> Labels:
    """Write `labels.json` for the Run, or raise `WindowOpenError` while the window is open.

    Labels are scoring input only and never reach a prompt. `labels.json` records the clone's
    HEAD, its newest commit date and whether an update ran (see `read_window`). `closed_bugs`
    is read after the window check, so a refused Run makes no tracker call. A Fix commit
    counts whenever its issue closed, since the state is read now (ADR 0006).
    """
    if run_dir.exists(LABELS):
        msg = f"{LABELS.path(None)} already exists; N is fixed before any scored Run"
        raise FileExistsError(msg)
    _check_cap(run_dir, deps)
    window = read_window(run_dir, deps)
    repo = run_dir.read(MANIFEST).target_repo
    bugs = frozenset(closed_bugs(repo))
    read_at = deps.clock()
    result = labels.build_labels(window.commits, window.cutoff_files, deps.max_files, bugs)
    linked = {n for commit in window.commits for n in labels.linked_issues(commit)}
    variants = labels.build_variants(
        window.commits,
        window.later_commits,
        window.cutoff_files,
        max_files=deps.max_files,
        closed_bugs=bugs,
        cutoff=date.fromisoformat(run_dir.read(MANIFEST).cutoff_date),
        long_window_closed=window.long_window_closed,
    )
    result = replace(
        result,
        variants=variants,
        linked_closed_bugs=tuple(sorted(linked & bugs)),
        issues_read_at=read_at.isoformat(),
        clone_head=git.head_sha(window.clone),
        clone_newest_commit=git.head_committed_at(window.clone).isoformat(),
        fetched=deps.update_clone is not None,
    )
    run_dir.write(LABELS, result)
    return result


def label_later(run_dir: RunDir, deps: LabelDeps, closed_bugs: ClosedBugs) -> LateLabels:
    """Write `labels-12m.json` once the 12-month window has closed, leaving `labels.json` alone.

    It holds the primary Label over `(Cutoff date, Cutoff date + 12 months]` at the same N, which
    `score` reads as the `window-12m` variant (ADR 0022). Raises `LabelMissingError` before
    `label` has run, `WindowOpenError` while the 12-month window is open and `FileExistsError`
    when `labels.json` already has the variant or this file exists. The tracker is read now, so
    `issues_read_at` is later than the one in `labels.json`.
    """
    if not run_dir.exists(LABELS):
        msg = "no labels.json; run `label` first"
        raise LabelMissingError(msg)
    if "window-12m" in run_dir.read(LABELS).variants:
        msg = "labels.json already has window-12m; there is nothing to add"
        raise FileExistsError(msg)
    if run_dir.exists(LABELS_12M):
        msg = f"{LABELS_12M.path(None)} already exists; it is never overwritten"
        raise FileExistsError(msg)
    manifest = run_dir.read(MANIFEST)
    cutoff = date.fromisoformat(manifest.cutoff_date)
    today = deps.clock().date()
    if not labels.window_is_closed(cutoff, today, labels.LONG_WINDOW_MONTHS):
        end = labels.window_end(cutoff, labels.LONG_WINDOW_MONTHS)
        msg = f"the 12-month window closes after {end}; today is {today}"
        raise WindowOpenError(msg)
    _check_cap(run_dir, deps)
    window = read_window(run_dir, deps)
    bugs = frozenset(closed_bugs(manifest.target_repo))
    read_at = deps.clock()
    result = LateLabels(
        counts=labels.window_counts(
            window.commits,
            window.later_commits,
            window.cutoff_files,
            months=labels.LONG_WINDOW_MONTHS,
            max_files=deps.max_files,
            closed_bugs=bugs,
            cutoff=cutoff,
        ),
        max_files=deps.max_files,
        issues_read_at=read_at.isoformat(),
        clone_head=git.head_sha(window.clone),
        clone_newest_commit=git.head_committed_at(window.clone).isoformat(),
        fetched=deps.update_clone is not None,
    )
    run_dir.write(LABELS_12M, result)
    return result
