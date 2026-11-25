"""Core types: frozen, plain data. This module imports nothing else from the package."""

from collections.abc import Mapping
from dataclasses import dataclass, field

BASELINE = "baseline"  # the Baseline ranker's id and the name of its ranking file


@dataclass(frozen=True)
class Manifest:
    """Everything that identifies a Run. Inputs only, written once by `resolve`."""

    target_repo: str
    pinned_sha: str
    cutoff_date: str  # ISO 8601 date, e.g. "2025-01-31"
    model: str  # model snapshot id
    model_training_cutoff: str  # ISO 8601 date, K
    cutoff_minus_training_days: int  # C - K in days; negative when the Cutoff date precedes K
    repeats: int
    prompt_hashes: Mapping[str, str]  # template name -> hash
    lizard_version: str
    adr_shas: Mapping[str, str]  # ADR id -> commit SHA, e.g. "0005" -> "..."
    tool_sha: str


@dataclass(frozen=True)
class OutlineEntry:
    """A class or function definition. `depth` is 0 at the top level and 1 for a method."""

    kind: str  # "class" or "function"
    name: str
    line: int  # 1-based
    depth: int


@dataclass(frozen=True)
class CommitSubject:
    """One non-merge commit subject from the Churn window. No author, hash, diff or count."""

    date: str  # committer date in UTC, `YYYY-MM-DD`
    subject: str


@dataclass(frozen=True)
class FileFacts:
    path: str
    loc: int
    churn: int
    complexity: float
    outline: tuple[OutlineEntry, ...]  # empty when the file does not parse
    head: str  # the first `HEAD_LINES` lines, undecodable bytes replaced
    truncated_lines: int  # lines after the head
    recent_commits: tuple[CommitSubject, ...]  # newest first, at most `MAX_SUBJECTS`

    @property
    def top_level_names(self) -> tuple[str, ...]:
        """The top-level class and function names, in file order."""
        return tuple(entry.name for entry in self.outline if entry.depth == 0)


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str


@dataclass(frozen=True)
class Snapshot:
    files: tuple[FileFacts, ...]
    issues: tuple[Issue, ...]
    zero_complexity_files: int  # files scored 0: no functions, or lizard could not analyze
    # Issues that existed at the Cutoff date but were dropped because their history cannot be
    # proven clean (ADR 0008), and whether issues were collected at all (`--no-issues` skips).
    excluded_issues: int = 0
    issues_collected: bool = False


@dataclass(frozen=True)
class Request:
    """One LLM call, holding everything the cache key needs."""

    ranker: str
    repeat: int  # part of the cache key, never sent to the API
    attempt: int  # 0 for the first try, 1 for the retry after unparsable output
    model: str
    system: str
    prompt: str
    max_tokens: int


@dataclass(frozen=True)
class Ranking:
    ranker: str  # "baseline" or "llm"
    repeat: int  # 0-based; always 0 for the baseline
    # Tie groups, most risky group first. Files in one group are tied with each other; an LLM
    # ranking is all singleton groups. Members are stored sorted by path only so the artifact
    # bytes are deterministic: that order carries no meaning and is not a tie-break (ADR 0019).
    groups: tuple[tuple[str, ...], ...]


def singleton_groups(paths: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return a strict order as tie groups of one file each."""
    return tuple((path,) for path in paths)


@dataclass(frozen=True)
class Labels:
    # Cutoff-date path -> number of tracker-confirmed Fix commits after the Cutoff date. This is
    # the primary Label that `score` reads (ADR 0004).
    counts: Mapping[str, int]
    # The same count for the keyword-only sensitivity set; never scored as the headline.
    keyword_counts: Mapping[str, int] = field(default_factory=dict[str, int])
    stats: Mapping[str, float] = field(
        default_factory=dict[str, float]
    )  # ADR 0004 reporting figures
    # Where the counts came from: the clone's HEAD, its newest commit date (ISO 8601) and
    # whether the clone was fast-forwarded first.
    clone_head: str = ""
    clone_newest_commit: str = ""
    fetched: bool = False
    # The closed bugs the primary set linked, and when the tracker was read (ISO 8601). Issue
    # state is read at scoring time (ADR 0006), so this records what that read saw.
    linked_closed_bugs: tuple[int, ...] = ()
    issues_read_at: str = ""


@dataclass(frozen=True)
class CapResult:
    """The Label's outcome under one fix-size cap; `max_files` None is uncapped."""

    max_files: int | None
    fix_commits_dropped: int
    files_labeled: int  # files with a Label of 1 or more
    label_total: int  # sum of every file's Label


@dataclass(frozen=True)
class ReviewItem:
    """One row of the review sheet: a sampled Fix commit as a reviewer needs to see it."""

    sha: str
    message: str
    issue_references: tuple[str, ...]  # `#N` or `/issues/N` found in the message, PR suffix aside
    files: tuple[str, ...]  # Eligible files the commit touches
    diff_stat: str  # `git show --stat` output


@dataclass(frozen=True)
class Validation:
    """The ADR 0004 pre-run checks: the fix-size cap N, its sensitivity, the review sample."""

    cap_n: int | None  # 90th percentile of fix sizes; None when no Fix commit touches a source file
    fix_commits_sized: int  # Fix commits that touch at least one Eligible file
    cap_report: tuple[CapResult, ...]  # N first (when set), then N = 5, 10, 20 and uncapped
    sample_seed: int
    sample: tuple[ReviewItem, ...]
    clone_head: str
    fetched: bool


@dataclass(frozen=True)
class Scores:
    metrics: Mapping[str, float]  # metric name -> value


@dataclass(frozen=True)
class RunScores:
    """What `scores-<scoring-date>.json` holds: every ranking's Scores for one Run (ADR 0008)."""

    labeled_files: int  # files with a Label of 1 or more
    min_labeled_files: int  # the minimum-data rule in force (ADR 0005)
    excluded: str  # why the Run is excluded from aggregation; empty when it is not
    rankings: Mapping[
        str, Scores
    ]  # ranking name ("baseline", "llm-0") -> Scores; empty if excluded


@dataclass(frozen=True)
class Response:
    """One LLM reply in provider-neutral form. No SDK object ever leaves `llm/client.py`."""

    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    request_id: str
    model: str  # the model snapshot the provider says it served


@dataclass(frozen=True)
class Probe:
    """The behavioral canary probe's result for one Run (ADR 0006). Never part of the verdict."""

    commit: str  # the post-Cutoff Fix commit whose message was sent
    expected_path: str  # the one eligible file that commit changed
    answer: str  # the path the model named; empty when the reply was unusable
    hit: bool  # the answer is exactly the expected path


@dataclass(frozen=True)
class CostAttempt:
    """One invocation's slice of a Run's spend, with the `--max-usd` cap it ran under."""

    max_usd: float
    spent_usd: float  # spent by this invocation alone


@dataclass(frozen=True)
class Cost:
    """A Run's `cost.json`: the attempts, oldest first. Their sum is the Run's actual spend."""

    attempts: tuple[CostAttempt, ...] = ()

    @property
    def spent_usd(self) -> float:
        return sum(attempt.spent_usd for attempt in self.attempts)


@dataclass(frozen=True)
class LoggedResponse:
    """One row of a Run's `responses.jsonl`: a Response and the request identity it answers."""

    ranker: str
    repeat: int
    attempt: int
    cache_hit: bool  # True when served from the Response cache, False when the API was called
    response: Response
