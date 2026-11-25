"""Atomic JSON and JSONL file IO, plus the (de)serialization of the core types.

The types stay pure data; everything about the on-disk format lives here.
"""

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from tech_debt_miner.types import (
    CommitSubject,
    FileFacts,
    Issue,
    Labels,
    LoggedResponse,
    Manifest,
    OutlineEntry,
    Ranking,
    Request,
    Response,
    Scores,
    Snapshot,
)


def canonical_json(data: object) -> str:
    """Return the one JSON text for `data`: sorted keys, no extra whitespace, final newline."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temporary file beside `path`, then rename it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path: Path, data: object) -> None:
    write_atomic(path, canonical_json(data))


def read_json(path: Path) -> Any:  # noqa: ANN401 - JSON has no static type; decoders narrow it
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, data: object) -> None:
    """Append one JSON object as one line, so a crash damages at most the last line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _drop_torn_tail(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(data))
        handle.flush()
        os.fsync(handle.fileno())


def _drop_torn_tail(path: Path) -> None:
    """Cut a partial last line left by a crash, so the next append starts a clean line."""
    if not path.exists():
        return
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        with path.open("r+b") as handle:
            handle.truncate(raw.rfind(b"\n") + 1)


def read_jsonl(path: Path) -> list[Any]:
    """Read every complete line; a torn final line from a crash is dropped."""
    lines = path.read_text(encoding="utf-8").split("\n")
    complete = lines[:-1]  # the text after the last newline is empty or torn
    return [json.loads(line) for line in complete if line]


def to_json(obj: DataclassInstance) -> dict[str, Any]:
    """Return the JSON-ready dict for any core type. Decoding stays explicit per type."""
    return asdict(obj)


def manifest_from_json(data: Mapping[str, Any]) -> Manifest:
    return Manifest(
        target_repo=data["target_repo"],
        pinned_sha=data["pinned_sha"],
        cutoff_date=data["cutoff_date"],
        model=data["model"],
        model_training_cutoff=data["model_training_cutoff"],
        cutoff_minus_training_days=data["cutoff_minus_training_days"],
        repeats=data["repeats"],
        prompt_hashes=dict(data["prompt_hashes"]),
        lizard_version=data["lizard_version"],
        adr_shas=dict(data["adr_shas"]),
        tool_sha=data["tool_sha"],
    )


def _file_facts_from_json(data: Mapping[str, Any]) -> FileFacts:
    return FileFacts(
        **{k: v for k, v in data.items() if k not in {"outline", "recent_commits"}},
        outline=tuple(OutlineEntry(**entry) for entry in data["outline"]),
        recent_commits=tuple(CommitSubject(**commit) for commit in data["recent_commits"]),
    )


def snapshot_from_json(data: Mapping[str, Any]) -> Snapshot:
    return Snapshot(
        files=tuple(_file_facts_from_json(file) for file in data["files"]),
        issues=tuple(Issue(**issue) for issue in data["issues"]),
        zero_complexity_files=data["zero_complexity_files"],
    )


def request_from_json(data: Mapping[str, Any]) -> Request:
    return Request(**data)


def ranking_from_json(data: Mapping[str, Any]) -> Ranking:
    return Ranking(
        ranker=data["ranker"],
        repeat=data["repeat"],
        groups=tuple(tuple(group) for group in data["groups"]),
    )


def labels_from_json(data: Mapping[str, Any]) -> Labels:
    return Labels(
        counts=dict(data["counts"]),
        stats=dict(data.get("stats", {})),
        clone_head=data.get("clone_head", ""),
        clone_newest_commit=data.get("clone_newest_commit", ""),
        fetched=data.get("fetched", False),
    )


def scores_from_json(data: Mapping[str, Any]) -> Scores:
    return Scores(metrics=dict(data["metrics"]))


def response_from_json(data: Mapping[str, Any]) -> Response:
    return Response(
        text=data["text"],
        input_tokens=data["input_tokens"],
        output_tokens=data["output_tokens"],
        stop_reason=data["stop_reason"],
        request_id=data["request_id"],
        model=data["model"],
    )


def logged_response_to_json(logged: LoggedResponse) -> dict[str, Any]:
    """Flatten to one `responses.jsonl` row: the request identity beside the Response fields."""
    return {
        "ranker": logged.ranker,
        "repeat": logged.repeat,
        "attempt": logged.attempt,
        "cache_hit": logged.cache_hit,
        **to_json(logged.response),
    }


def logged_response_from_json(data: Mapping[str, Any]) -> LoggedResponse:
    return LoggedResponse(
        ranker=data["ranker"],
        repeat=data["repeat"],
        attempt=data["attempt"],
        cache_hit=data["cache_hit"],
        response=response_from_json(data),
    )
