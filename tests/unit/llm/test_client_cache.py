from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from tech_debt_miner.llm.cache import ResponseCache
from tech_debt_miner.llm.client import LLMClient, ProviderError, UnparsableOutputError
from tech_debt_miner.types import LoggedResponse, Request, Response

pytestmark = pytest.mark.unit

KEY = "sk-ant-api03-SECRET_123"
OK = Response("ok", 1000, 500, "end_turn", "req_1", "claude-sonnet-5-5")


def request(**overrides: int | str) -> Request:
    fields: dict[str, int | str] = {
        "ranker": "llm",
        "repeat": 0,
        "attempt": 0,
        "model": "claude-sonnet-5-5",
        "system": "sys",
        "prompt": "hello",
        "max_tokens": 100,
    }
    return Request(**{**fields, **overrides})  # type: ignore[arg-type]


class Script:
    """A transport that replies with each text in turn and records its calls."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.calls: list[Request] = []

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:  # noqa: ARG002 - Transport signature
        self.calls.append(request)
        return replace(OK, text=self.texts.pop(0) if self.texts else "ok")


class Failing:
    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:  # noqa: ARG002 - Transport signature
        msg = "must not be called"
        raise ProviderError(msg)


def parse_int(text: str) -> int:
    return int(text)


def test_a_cache_hit_skips_the_transport_and_costs_nothing(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    LLMClient(Script(), max_usd=1.0, cache=cache).complete(request())
    client = LLMClient(Failing(), max_usd=0.0000001, cache=cache)
    assert client.complete(request()) == OK
    assert client.spent_usd == 0.0


def test_repeats_are_not_collapsed_by_the_cache(tmp_path: Path) -> None:
    transport = Script()
    client = LLMClient(transport, max_usd=1.0, cache=ResponseCache(tmp_path))
    for repeat in range(3):
        client.complete(request(repeat=repeat))
    assert len(transport.calls) == 3


def test_every_response_is_logged_whether_hit_or_miss(tmp_path: Path) -> None:
    rows: list[LoggedResponse] = []
    client = LLMClient(
        Script(), max_usd=1.0, cache=ResponseCache(tmp_path), on_response=rows.append
    )
    client.complete(request())
    client.complete(request())
    assert [row.cache_hit for row in rows] == [False, True]
    assert replace(rows[0], cache_hit=True) == rows[1]
    assert rows[0].response.text == "ok"
    assert rows[0].response.request_id == "req_1"


def test_the_per_attempt_log_marks_cache_hits(tmp_path: Path) -> None:
    log: list[Mapping[str, object]] = []
    client = LLMClient(Script(), max_usd=1.0, cache=ResponseCache(tmp_path), log=log.append)
    client.complete(request())
    client.complete(request())
    assert [(row["cache_hit"], row["cost_usd"]) for row in log] == [
        (False, pytest.approx(0.007)),
        (True, 0.0),
    ]


def test_logged_response_text_is_redacted() -> None:
    rows: list[LoggedResponse] = []
    client = LLMClient(Script(f"key {KEY}"), max_usd=1.0, on_response=rows.append, secrets=(KEY,))
    client.complete(request())
    assert KEY not in str(rows)


def test_unparsable_output_is_retried_once_with_the_next_attempt(tmp_path: Path) -> None:
    rows: list[LoggedResponse] = []
    transport = Script("garbage", "42")
    client = LLMClient(
        transport, max_usd=1.0, cache=ResponseCache(tmp_path), on_response=rows.append
    )
    assert client.complete_parsed(request(), parse_int) == 42
    assert [call.attempt for call in transport.calls] == [0, 1]
    assert [(row.attempt, row.response.text) for row in rows] == [(0, "garbage"), (1, "42")]


def test_a_cached_bad_reply_does_not_repeat_forever(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    first = LLMClient(Script("garbage", "42"), max_usd=1.0, cache=cache)
    first.complete_parsed(request(), parse_int)
    transport = Script()
    second = LLMClient(transport, max_usd=1.0, cache=cache)
    assert second.complete_parsed(request(), parse_int) == 42
    assert transport.calls == []


def test_amend_rewrites_the_retry() -> None:
    transport = Script("garbage", "42")

    def amend(original: Request, error: str) -> Request:
        return replace(original, prompt=f"{original.prompt} [{error}]")

    LLMClient(transport, max_usd=1.0).complete_parsed(request(), parse_int, amend=amend)
    assert "invalid literal" in transport.calls[1].prompt
    assert transport.calls[1].attempt == 1


def test_two_unparsable_replies_fail_loudly_with_both_logged() -> None:
    rows: list[LoggedResponse] = []
    client = LLMClient(Script("a", "b"), max_usd=1.0, on_response=rows.append)
    with pytest.raises(UnparsableOutputError):
        client.complete_parsed(request(), parse_int)
    assert [row.response.text for row in rows] == ["a", "b"]
