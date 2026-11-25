"""The two-stage LLM ranker (ADR 0010).

Stage 1 (triage) reads a digest of every eligible file and returns the Triage set. Stage 2 reads
code and history for that set and returns the ordered list. All traffic goes through the injected
`LLMClient`, so this module imports no SDK (ADR 0002). Rationales and the Triage set are never
copied into the `Ranking`: they stay in the client's logs, which hold each raw reply.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import cast

from tech_debt_miner.llm.client import LLMClient, UnparsableOutputError
from tech_debt_miner.rankers.prompts import (
    RANKING_SIZE,
    build_rank_prompt,
    build_triage_prompt,
    triage_set_size,
)
from tech_debt_miner.types import Ranking, Request, Snapshot, singleton_groups

LLM = "llm"  # the ranker id of stage 2, whose reply is the ranking
TRIAGE = "llm-triage"  # stage 1's label, so Replay's (ranker, repeat) key keeps the stages apart
TRIAGE_MAX_TOKENS = 4_096
RANK_MAX_TOKENS = 8_192
SYSTEM = "You are a careful reviewer of Python code. Answer only in the requested JSON format."

TRIAGE_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
    "required": ["paths"],
    "additionalProperties": False,
}
RANK_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "rationale": {"type": "string"}},
                "required": ["path", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ranking"],
    "additionalProperties": False,
}


class RankFailed(Exception):  # noqa: N818 - the name is fixed by ADR 0010
    """The model's output was malformed twice. The Run stays resumable; nothing is scored."""


def _load_list(text: str, key: str) -> list[object]:
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as error:
        msg = f"the reply is not valid JSON: {error}"
        raise ValueError(msg) from error
    items = cast("dict[str, object]", data).get(key) if isinstance(data, dict) else None
    if not isinstance(items, list):
        msg = f'the reply must be a JSON object with a "{key}" array'
        raise ValueError(msg)  # noqa: TRY004 - one error type feeds the retry
    return cast("list[object]", items)


def parse_triage(text: str, snapshot: Snapshot) -> tuple[str, ...]:
    """Return the Triage set from a stage 1 reply, or raise `ValueError` saying what is wrong."""
    paths = _load_list(text, "paths")
    if not all(isinstance(path, str) for path in paths):
        msg = '"paths" must hold only strings'
        raise ValueError(msg)
    chosen = cast("list[str]", paths)
    known = {file.path for file in snapshot.files}
    unknown = sorted(set(chosen) - known)
    if unknown:
        msg = f"these paths are not in the digest: {', '.join(unknown)}"
        raise ValueError(msg)
    expected = triage_set_size(len(snapshot.files))
    if len(set(chosen)) != len(chosen) or len(chosen) != expected:
        msg = f"expected exactly {expected} distinct paths, got {len(chosen)}"
        raise ValueError(msg)
    return tuple(chosen)


def parse_ranking(text: str) -> tuple[str, ...]:
    """Return the ranked paths, best first, from a stage 2 reply; rationales are dropped.

    Raises `ValueError` for a malformed, empty or over-long list, so a failed reply is never
    scored as an empty ranking. Duplicate and nonexistent paths are kept: ADR 0005 and ADR 0013
    decide how scoring treats them. Replay uses this same function (ADR 0017).
    """
    entries = _load_list(text, "ranking")
    paths: list[str] = []
    for entry in entries:
        path = cast("dict[str, object]", entry).get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            msg = 'every "ranking" entry must be an object with a string "path"'
            raise ValueError(msg)  # noqa: TRY004 - one error type feeds the retry
        paths.append(path)
    if not paths:
        msg = "the ranking is empty"
        raise ValueError(msg)
    if len(paths) > RANKING_SIZE:
        msg = f"the ranking has {len(paths)} files; at most {RANKING_SIZE} are allowed"
        raise ValueError(msg)
    return tuple(paths)


def _with_error(request: Request, error: str) -> Request:
    """Return the retry request: the original prompt plus what was wrong with the first reply."""
    note = f"\n\nYour previous reply was rejected: {error}\nReply again, fixing that."
    return replace(request, prompt=request.prompt + note)


class LLMRanker:
    """Implements `Ranker`. `thinking_headroom` is the extra output budget thinking needs."""

    def __init__(self, client: LLMClient, *, model: str, thinking_headroom: int = 0) -> None:
        self._client = client
        self._model = model
        self._headroom = thinking_headroom

    def rank(self, snapshot: Snapshot, *, repeat: int) -> Ranking:
        triage_request = Request(
            ranker=TRIAGE,
            repeat=repeat,
            attempt=0,
            model=self._model,
            system=SYSTEM,
            prompt=build_triage_prompt(snapshot),
            max_tokens=TRIAGE_MAX_TOKENS + self._headroom,
        )
        triage_set = self._complete(
            triage_request, lambda text: parse_triage(text, snapshot), TRIAGE_SCHEMA
        )
        rank_request = replace(
            triage_request,
            ranker=LLM,
            prompt=build_rank_prompt(snapshot, triage_set),
            max_tokens=RANK_MAX_TOKENS + self._headroom,
        )
        paths = self._complete(rank_request, parse_ranking, RANK_SCHEMA)
        return Ranking(ranker=LLM, repeat=repeat, groups=singleton_groups(paths))

    def _complete[T](
        self, request: Request, parse: Callable[[str], T], schema: Mapping[str, object]
    ) -> T:
        try:
            return self._client.complete_parsed(request, parse, schema, amend=_with_error)
        except UnparsableOutputError as error:
            raise RankFailed(str(error)) from error
