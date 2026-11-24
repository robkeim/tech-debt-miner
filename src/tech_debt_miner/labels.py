"""The Label: per-file counts of Fix commits after the Cutoff date (ADR 0004).

Only the keyword-only set exists so far. Everything here is pure: it takes commits already read
from the Target repo and never touches it.
"""

import calendar
import re
from collections.abc import Collection, Sequence
from datetime import date, timedelta

from tech_debt_miner.repo.eligibility import is_eligible
from tech_debt_miner.repo.history import CommitChange
from tech_debt_miner.types import Labels

WINDOW_MONTHS = 6  # ADR 0005

_KEYWORD = re.compile(r"\b(?:fix|fixes|fixed|bug|defect|patch)\b", re.IGNORECASE)
_EXCLUDED_MESSAGE = re.compile(r"refactor|cleanup|rename|merge|bump|revert", re.IGNORECASE)
_BOT_NAME = re.compile(r"\[bot\]|[-_ ]bot$|^(?:dependabot|renovate)$", re.IGNORECASE)
_PR_SUFFIX = re.compile(r"\s*\(#\d+\)\s*$")
_ISSUE_REFERENCE = re.compile(r"#\d+|/issues/\d+")


def window_start(cutoff: date) -> date:
    """First day of the Label window: the day after the Cutoff date."""
    return cutoff + timedelta(days=1)


def window_end(cutoff: date) -> date:
    """Last day of the Label window: the Cutoff date plus 6 months, clamped to month end."""
    month_index = cutoff.month - 1 + WINDOW_MONTHS
    year, month = cutoff.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(cutoff.day, calendar.monthrange(year, month)[1]))


def window_is_closed(cutoff: date, today: date) -> bool:
    """Whether every day of the window `(cutoff, cutoff + 6 months]` has passed."""
    return today > window_end(cutoff)


def is_bot(commit: CommitChange) -> bool:
    return bool(
        _BOT_NAME.search(commit.author_name) or _BOT_NAME.search(commit.author_email.split("@")[0])
    )


def is_keyword_fix(commit: CommitChange) -> bool:
    """Return whether the keyword-only rule with its exclusions holds, before the fix-size cap.

    Merge commits never reach here: `list_commits` drops them. Messages are matched in full
    (subject and body). The keywords match whole words; the exclusions match as substrings, so
    "refactoring" and "renamed" are excluded too.
    """
    return (
        not is_bot(commit)
        and _KEYWORD.search(commit.message) is not None
        and _EXCLUDED_MESSAGE.search(commit.message) is None
    )


def is_squash_merge(commit: CommitChange) -> bool:
    """Whether the subject ends in a `(#N)` PR number, GitHub's squash-merge default."""
    return _PR_SUFFIX.search(commit.message.split("\n", 1)[0]) is not None


def carries_only_pr_number(commit: CommitChange) -> bool:
    """Whether the message's only issue-like reference is the trailing `(#N)` PR number."""
    subject, _, body = commit.message.partition("\n")
    match = _PR_SUFFIX.search(subject)
    if match is None:
        return False
    return _ISSUE_REFERENCE.search(subject[: match.start()] + "\n" + body) is None


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _touched(commit: CommitChange, origin: dict[str, str]) -> set[str]:
    """Return the Cutoff-date paths `commit` touches, then apply its renames and deletes.

    `origin` maps each path currently in the tree to its Cutoff-date path, and is updated in
    place. Paths not in it were created after the Cutoff date.
    """
    hit: set[str] = set()
    for change in commit.files:
        if change.old_path is not None:
            if change.old_path in origin:
                origin[change.path] = origin.pop(change.old_path)
            else:
                origin.pop(change.path, None)  # created later, then renamed
        if change.path in origin:
            hit.add(origin[change.path])
        if change.deleted:
            origin.pop(change.path, None)  # a file recreated at this path is new
    return hit


def build_labels(
    commits: Sequence[CommitChange],
    cutoff_files: Collection[str],
    max_files: int | None = None,
) -> Labels:
    """Count Fix commits per Cutoff-date file.

    `commits` are the non-merge commits in the Label window, newest first as `list_commits`
    returns them; commits with equal times keep git order. `cutoff_files` are the
    paths in the tree at the Pinned SHA; only the eligible ones are counted, each with at least
    a zero. A commit counts once per file. A path is followed through renames back to its
    Cutoff-date path, files deleted later keep their count, and files created later are ignored.
    A Fix commit touching more than `max_files` eligible files is dropped; `None` means uncapped.
    """
    eligible = {path for path in cutoff_files if is_eligible(path)}
    counts = dict.fromkeys(sorted(eligible), 0)
    origin = {path: path for path in cutoff_files}
    fix_commits = [c for c in commits if is_keyword_fix(c)]
    fixes = {c.sha for c in fix_commits}
    dropped = 0
    oldest_first = list(
        reversed(commits)
    )  # the sort below is stable, so equal times stay in git order
    oldest_first.sort(key=lambda c: c.committed_at)
    for commit in oldest_first:
        touched = _touched(commit, origin)
        if commit.sha not in fixes:
            continue
        if max_files is not None and sum(is_eligible(f.path) for f in commit.files) > max_files:
            dropped += 1
            continue
        for path in touched & eligible:
            counts[path] += 1
    stats = {
        "commits_in_window": len(commits),
        "squash_share": _share(sum(map(is_squash_merge, commits)), len(commits)),
        "fix_commits": len(fix_commits),
        "fix_commits_dropped_by_cap": dropped,
        "pr_number_only_share": _share(
            sum(map(carries_only_pr_number, fix_commits)), len(fix_commits)
        ),
    }
    return Labels(counts=counts, stats=stats)
