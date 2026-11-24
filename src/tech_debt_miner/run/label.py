"""The `label` stage: count Fix commits per file in the closed Label window (ADR 0004, ADR 0008)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from tech_debt_miner import labels
from tech_debt_miner.repo import git
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Labels


class WindowOpenError(RuntimeError):
    """The Label window has not closed yet, so the Label would be incomplete (ADR 0005)."""


@dataclass(frozen=True)
class LabelDeps:
    """Injected collaborators."""

    repos_dir: Path
    clock: Callable[[], datetime]
    max_files: int | None = None  # the fix-size cap N; None is uncapped


def label(run_dir: RunDir, deps: LabelDeps) -> Labels:
    """Write `labels.json` for the Run, or raise `WindowOpenError` while the window is open.

    The window is `(Cutoff date, Cutoff date + 6 months]` by date. It starts the day after the
    Cutoff date and ends after its last day, so it can never include a commit the as-of
    functions return. Labels are scoring input only and never reach a prompt.
    """
    manifest = run_dir.read_manifest()
    cutoff = date.fromisoformat(manifest.cutoff_date)
    today = deps.clock().date()
    if not labels.window_is_closed(cutoff, today):
        msg = f"the Label window closes after {labels.window_end(cutoff)}; today is {today}"
        raise WindowOpenError(msg)
    clone = deps.repos_dir / manifest.target_repo.rsplit("/", 1)[-1]
    commits = git.list_commits(
        clone, labels.window_start(cutoff), labels.window_end(cutoff) + timedelta(days=1)
    )
    result = labels.build_labels(
        commits, git.list_files(clone, manifest.pinned_sha), deps.max_files
    )
    run_dir.write_labels(result)
    return result
