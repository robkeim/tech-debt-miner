"""Core types: frozen, plain data. This module imports nothing else from the package."""

from collections.abc import Mapping
from dataclasses import dataclass, field


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
class FileFacts:
    path: str
    loc: int
    churn: int
    complexity: float


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
    paths: tuple[str, ...]  # most risky first


@dataclass(frozen=True)
class Labels:
    counts: Mapping[str, int]  # Cutoff-date path -> number of Fix commits after the Cutoff date
    stats: Mapping[str, float] = field(
        default_factory=dict[str, float]
    )  # ADR 0004 reporting figures
    # Where the counts came from: the clone's HEAD, its newest commit date (ISO 8601) and
    # whether the clone was fast-forwarded first.
    clone_head: str = ""
    clone_newest_commit: str = ""
    fetched: bool = False


@dataclass(frozen=True)
class Scores:
    metrics: Mapping[str, float]  # metric name -> value


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
