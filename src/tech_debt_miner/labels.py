"""The Label: per-file counts of Fix commits after the Cutoff date (ADR 0004).

Two sets are counted side by side: the primary, tracker-confirmed set and the keyword-only
sensitivity set. Everything here is pure: it takes commits already read from the Target repo, and
the numbers of the issues the tracker reports as closed bugs, and never touches either.
"""

import calendar
import random
import re
from collections.abc import Collection, Sequence
from datetime import date, timedelta

from tech_debt_miner.repo.eligibility import is_eligible
from tech_debt_miner.repo.history import CommitChange
from tech_debt_miner.types import CapResult, Labels

WINDOW_MONTHS = 6  # ADR 0005
CAP_PERCENTILE = 90  # N is this percentile of fix sizes (ADR 0004)
CAP_GRID: tuple[int | None, ...] = (5, 10, 20, None)  # the sensitivity caps; None is uncapped
SHORT_WINDOW_MONTHS = 3  # the sensitivity windows (ADR 0005)
LONG_WINDOW_MONTHS = 12
SAMPLE_SIZE = 30  # Fix commits per Target repo on the review sheet (ADR 0004)
SAMPLE_SEED = 20260711  # fixed, so the same commits always give the same sheet

_KEYWORD = re.compile(r"\b(?:fix|fixes|fixed|bug|defect|patch)\b", re.IGNORECASE)
_EXCLUDED_MESSAGE = re.compile(r"refactor|cleanup|rename|merge|bump|revert", re.IGNORECASE)
_BOT_NAME = re.compile(r"\[bot\]|[-_ ]bot$|^(?:dependabot|renovate)$", re.IGNORECASE)
_PR_SUFFIX = re.compile(r"\s*\(#\d+\)\s*$")
_ISSUE_REFERENCE = re.compile(r"#\d+|/issues/\d+")


def window_start(cutoff: date) -> date:
    """First day of the Label window: the day after the Cutoff date."""
    return cutoff + timedelta(days=1)


def window_end(cutoff: date, months: int = WINDOW_MONTHS) -> date:
    """Last day of a Label window: the Cutoff date plus `months`, clamped to month end."""
    month_index = cutoff.month - 1 + months
    year, month = cutoff.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(cutoff.day, calendar.monthrange(year, month)[1]))


def window_is_closed(cutoff: date, today: date, months: int = WINDOW_MONTHS) -> bool:
    """Whether every day of the window `(cutoff, cutoff + months]` has passed."""
    return today > window_end(cutoff, months)


def variant_name(cap: int | None) -> str:
    """Name of the fix-size-cap variant in `Labels.variants`."""
    return "cap-none" if cap is None else f"cap-{cap}"


WINDOW_VARIANTS = (
    (f"window-{SHORT_WINDOW_MONTHS}m", SHORT_WINDOW_MONTHS),
    (f"window-{LONG_WINDOW_MONTHS}m", LONG_WINDOW_MONTHS),
)


def is_bot(commit: CommitChange) -> bool:
    return bool(
        _BOT_NAME.search(commit.author_name) or _BOT_NAME.search(commit.author_email.split("@")[0])
    )


def _passes_exclusions(commit: CommitChange) -> bool:
    """Return whether the exclusions both label sets share hold: no bot, no excluded word."""
    return not is_bot(commit) and _EXCLUDED_MESSAGE.search(commit.message) is None


def is_keyword_fix(commit: CommitChange) -> bool:
    """Return whether the keyword-only rule with its exclusions holds, before the fix-size cap.

    Merge commits never reach here: `list_commits` drops them. Messages are matched in full
    (subject and body). The keywords match whole words; the exclusions match as substrings, so
    "refactoring" and "renamed" are excluded too.
    """
    return _passes_exclusions(commit) and _KEYWORD.search(commit.message) is not None


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


def linked_issues(commit: CommitChange) -> tuple[int, ...]:
    """Return the issue numbers the message links, in order of first mention.

    Only `#N` and `/issues/N` references count. A bare number never does, and neither does a
    trailing `(#N)`, which is a PR number (ADR 0004).
    """
    return tuple(int(re.sub(r"\D", "", ref)) for ref in issue_references(commit))


def is_tracker_fix(commit: CommitChange, closed_bugs: Collection[int]) -> bool:
    """Return whether the tracker-confirmed rule with its exclusions holds, before the cap.

    The commit must link an issue that is a closed bug. The bot and message exclusions are the
    same as for the keyword set; the keyword itself is not needed.
    """
    return _passes_exclusions(commit) and any(
        number in closed_bugs for number in linked_issues(commit)
    )


def eligible_files(commit: CommitChange) -> tuple[str, ...]:
    """Return the Eligible files `commit` touches, by their paths after the commit."""
    return tuple(f.path for f in commit.files if is_eligible(f.path))


def fix_sizes(commits: Sequence[CommitChange]) -> list[int]:
    """Return the Eligible-file count of each keyword Fix commit that touches at least one.

    Fix commits with no Eligible file are left out: the cap can never drop them and they put no
    file in the Label. Nothing here looks at Labels or scores (ADR 0004).
    """
    sizes = (len(eligible_files(c)) for c in commits if is_keyword_fix(c))
    return [size for size in sizes if size > 0]


def percentile_cap(sizes: Sequence[int], percent: int = CAP_PERCENTILE) -> int | None:
    """Return the nearest-rank percentile of `sizes`, or None when there are none.

    Nearest rank is the smallest size with at least `percent` percent of the sizes at or below
    it, so a cap of N keeps at least that share of the Fix commits.
    """
    if not sizes:
        return None
    rank = (percent * len(sizes) + 99) // 100
    return sorted(sizes)[rank - 1]


def cap_report(
    commits: Sequence[CommitChange],
    cutoff_files: Collection[str],
    caps: Sequence[int | None],
) -> tuple[CapResult, ...]:
    """Return the Label's outcome under each cap, in the order given."""
    results: list[CapResult] = []
    for cap in caps:
        built = build_labels(commits, cutoff_files, cap)
        counts = list(built.keyword_counts.values())
        results.append(
            CapResult(
                max_files=cap,
                fix_commits_dropped=int(built.stats["fix_commits_dropped_by_cap"]),
                files_labeled=sum(count > 0 for count in counts),
                label_total=sum(counts),
            )
        )
    return tuple(results)


def sample_fixes(
    commits: Sequence[CommitChange],
    max_files: int,
    count: int = SAMPLE_SIZE,
    seed: int = SAMPLE_SEED,
) -> list[CommitChange]:
    """Return a seeded random sample of the Fix commits that count under the cap.

    The pool is every keyword Fix commit with 1 to `max_files` Eligible files, ordered by SHA
    so the sample depends only on the seed and the pool. A smaller pool is returned whole.
    """
    pool = sorted(
        (c for c in commits if is_keyword_fix(c) and 0 < len(eligible_files(c)) <= max_files),
        key=lambda c: c.sha,
    )
    rng = random.Random(seed)  # noqa: S311 - a reproducible sample, not security
    return rng.sample(pool, min(count, len(pool)))


def issue_references(commit: CommitChange) -> tuple[str, ...]:
    """Return the `#N` and `/issues/N` references in the message, apart from a `(#N)` PR suffix.

    These are candidates for a linked issue, not tracker-confirmed ones.
    """
    subject, _, body = commit.message.partition("\n")
    match = _PR_SUFFIX.search(subject)
    text = (subject[: match.start()] if match else subject) + "\n" + body
    return tuple(dict.fromkeys(_ISSUE_REFERENCE.findall(text)))


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
    closed_bugs: Collection[int] = frozenset(),
) -> Labels:
    """Count Fix commits per Cutoff-date file, for both label sets.

    `commits` are the non-merge commits in the Label window, newest first as `list_commits`
    returns them; commits with equal times keep git order. `cutoff_files` are the
    paths in the tree at the Pinned SHA; only the eligible ones are counted, each with at least
    a zero. `closed_bugs` are the numbers of the issues the tracker reports as closed bugs when
    this is called; a commit is in the primary set when it links one (ADR 0004, ADR 0006). A
    commit counts once per file. A path is followed through renames back to its Cutoff-date
    path, files deleted later keep their count, and files created later are ignored. A Fix
    commit touching more than `max_files` eligible files is dropped; `None` means uncapped.
    """
    eligible = {path for path in cutoff_files if is_eligible(path)}
    keyword_counts = dict.fromkeys(sorted(eligible), 0)
    counts = dict(keyword_counts)
    origin = {path: path for path in cutoff_files}
    keyword_fixes = {c.sha for c in commits if is_keyword_fix(c)}
    tracker_fixes = {c.sha for c in commits if is_tracker_fix(c, closed_bugs)}
    dropped: dict[str, int] = {"keyword": 0, "tracker": 0}
    oldest_first = list(
        reversed(commits)
    )  # the sort below is stable, so equal times stay in git order
    oldest_first.sort(key=lambda c: c.committed_at)
    for commit in oldest_first:
        touched = _touched(commit, origin) & eligible
        too_wide = (
            max_files is not None and sum(is_eligible(f.path) for f in commit.files) > max_files
        )
        for name, fixes, target in (
            ("keyword", keyword_fixes, keyword_counts),
            ("tracker", tracker_fixes, counts),
        ):
            if commit.sha not in fixes:
                continue
            if too_wide:
                dropped[name] += 1
                continue
            for path in touched:
                target[path] += 1
    keyword_commits = [c for c in commits if c.sha in keyword_fixes]
    stats = {
        "commits_in_window": len(commits),
        "squash_share": _share(sum(map(is_squash_merge, commits)), len(commits)),
        "fix_commits": len(keyword_commits),
        "fix_commits_dropped_by_cap": dropped["keyword"],
        "pr_number_only_share": _share(
            sum(map(carries_only_pr_number, keyword_commits)), len(keyword_commits)
        ),
        "tracker_fix_commits": len(tracker_fixes),
        "tracker_fix_commits_dropped_by_cap": dropped["tracker"],
    }
    return Labels(counts=counts, keyword_counts=keyword_counts, stats=stats)


def build_variants(  # noqa: PLR0913 - one input per axis the variants vary
    commits: Sequence[CommitChange],
    later_commits: Sequence[CommitChange],
    cutoff_files: Collection[str],
    *,
    max_files: int | None,
    closed_bugs: Collection[int],
    cutoff: date,
) -> dict[str, dict[str, int]]:
    """Tracker-confirmed counts under each ADR 0005 sensitivity variant, keyed by variant name.

    `commits` are the 6-month window's and `later_commits` the ones after it, up to 12 months;
    pass no `later_commits` when that window is still open and the 12-month variant is left
    out. Windows keep the primary N; caps keep the 6-month window.
    """
    variants = {
        variant_name(cap): dict(build_labels(commits, cutoff_files, cap, closed_bugs).counts)
        for cap in CAP_GRID
    }
    for name, months in WINDOW_VARIANTS:
        if months > WINDOW_MONTHS and not later_commits:
            continue
        end = window_end(cutoff, months)
        within = [c for c in (*later_commits, *commits) if c.committed_at.date() <= end]
        variants[name] = dict(build_labels(within, cutoff_files, max_files, closed_bugs).counts)
    return variants
