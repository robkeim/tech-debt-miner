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
    FileFacts,
    Issue,
    Labels,
    Manifest,
    Ranking,
    Request,
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


def snapshot_from_json(data: Mapping[str, Any]) -> Snapshot:
    return Snapshot(
        files=tuple(FileFacts(**file) for file in data["files"]),
        issues=tuple(Issue(**issue) for issue in data["issues"]),
    )


def request_from_json(data: Mapping[str, Any]) -> Request:
    return Request(**data)


def ranking_from_json(data: Mapping[str, Any]) -> Ranking:
    return Ranking(ranker=data["ranker"], repeat=data["repeat"], paths=tuple(data["paths"]))


def labels_from_json(data: Mapping[str, Any]) -> Labels:
    return Labels(counts=dict(data["counts"]))


def scores_from_json(data: Mapping[str, Any]) -> Scores:
    return Scores(metrics=dict(data["metrics"]))
