"""The artifact table: every file in a Run directory, defined once.

Each `Artifact` holds its name, codec and write policy. `RunDir` reads, writes and
appends over these definitions. Decoding stays explicit per type (ADR 0009); the table
only points at the decoders in `store`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from tech_debt_miner import jsonio
from tech_debt_miner.run import store
from tech_debt_miner.types import (
    BASELINE,
    Cost,
    Labels,
    LoggedResponse,
    Manifest,
    Probe,
    Ranking,
    Request,
    RunScores,
    Snapshot,
    Validation,
)


class Policy(StrEnum):
    REPLACE = "replace"  # `write` overwrites atomically
    CREATE_ONCE = "create-once"  # `write` fails if the file exists
    APPEND = "append"  # `append` adds one JSONL row; `read_all` returns every row


@dataclass(frozen=True)
class Artifact[T, K]:
    """One kind of Run file. `K` is the key type for keyed artifacts and `None` otherwise."""

    name: str
    path: Callable[[K], str]  # relative to the Run directory
    encode: Callable[[T], Any]
    decode: Callable[[Any], T]
    policy: Policy
    keyed: bool = False  # the key is required; singletons use `None`
    key_of: Callable[[T], K] | None = None  # derive the key from a value, when it carries one
    glob: str | None = None  # matches every file of a keyed artifact
    parse_key: Callable[[str], K] | None = None  # file name -> key, the inverse of `path`


def _fixed(name: str) -> Callable[[None], str]:
    return lambda _key: name


MANIFEST = Artifact[Manifest, None](
    "manifest",
    _fixed("manifest.json"),
    jsonio.to_json,
    store.manifest_from_json,
    Policy.CREATE_ONCE,
)
SNAPSHOT = Artifact[Snapshot, None](
    "snapshot", _fixed("snapshot.json"), jsonio.to_json, store.snapshot_from_json, Policy.REPLACE
)
REQUESTS = Artifact[Request, None](
    "requests", _fixed("requests.jsonl"), jsonio.to_json, store.request_from_json, Policy.APPEND
)
RESPONSES = Artifact[LoggedResponse, None](
    "responses",
    _fixed("responses.jsonl"),
    store.logged_response_to_json,
    store.logged_response_from_json,
    Policy.APPEND,
)
COST = Artifact[Cost, None](
    "cost", _fixed("cost.json"), jsonio.to_json, store.cost_from_json, Policy.REPLACE
)
LABELS = Artifact[Labels, None](
    "labels", _fixed("labels.json"), jsonio.to_json, store.labels_from_json, Policy.REPLACE
)
VALIDATION = Artifact[Validation, None](
    "validation",
    _fixed("validation.json"),
    jsonio.to_json,
    store.validation_from_json,
    Policy.CREATE_ONCE,
)
PROBE = Artifact[Probe, None](
    "probe", _fixed("probe.json"), jsonio.to_json, store.probe_from_json, Policy.CREATE_ONCE
)


def ranking_name(ranker: str, repeat: int) -> str:
    """Return the name a ranking goes by in file names and scores: `baseline` or `llm-<n>`."""
    return ranker if ranker == BASELINE else f"{ranker}-{repeat}"


def _ranking_path(key: tuple[str, int]) -> str:
    return f"rankings/{ranking_name(*key)}.json"


def _parse_ranking_key(file_name: str) -> tuple[str, int]:
    stem = file_name.removesuffix(".json")
    ranker, _, repeat = stem.partition("-")
    if stem == BASELINE:
        return (BASELINE, 0)
    if ranker.isalpha() and ranker != BASELINE and repeat.isdecimal():
        return (ranker, int(repeat))
    msg = f"unexpected ranking file {file_name!r}; expected baseline.json or <ranker>-<n>.json"
    raise ValueError(msg)


RANKING = Artifact[Ranking, tuple[str, int]](
    "ranking",
    _ranking_path,
    jsonio.to_json,
    store.ranking_from_json,
    Policy.REPLACE,
    keyed=True,
    key_of=lambda ranking: (ranking.ranker, ranking.repeat),
    glob="rankings/*.json",
    parse_key=_parse_ranking_key,
)

_SCORES_PREFIX, _SCORES_SUFFIX = "scores-", ".json"

SCORES = Artifact[RunScores, str](
    "scores",
    lambda scoring_date: f"{_SCORES_PREFIX}{scoring_date}{_SCORES_SUFFIX}",
    jsonio.to_json,
    store.scores_from_json,
    Policy.CREATE_ONCE,
    keyed=True,
    glob=f"{_SCORES_PREFIX}*{_SCORES_SUFFIX}",
    parse_key=lambda file_name: file_name.removeprefix(_SCORES_PREFIX).removesuffix(_SCORES_SUFFIX),
)

# Every artifact, for tests that iterate the table.
ALL: tuple[Artifact[Any, Any], ...] = (
    MANIFEST,
    SNAPSHOT,
    REQUESTS,
    RESPONSES,
    COST,
    LABELS,
    VALIDATION,
    PROBE,
    RANKING,
    SCORES,
)
