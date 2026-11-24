import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx2
import pytest

from tech_debt_miner.llm.client import (
    AnthropicTransport,
    CapExceededError,
    DryRunError,
    DryRunTransport,
    LLMClient,
    MissingKeyError,
    ProviderError,
    UnknownModelError,
    load_api_key,
    redact,
)
from tech_debt_miner.types import Request, Response

pytestmark = pytest.mark.unit

KEY = "sk-ant-api03-SECRET_123"

MESSAGE: Mapping[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5-20261001",
    "content": [
        {"type": "thinking", "thinking": "hmm", "signature": "s"},
        {"type": "text", "text": '{"a":'},
        {"type": "text", "text": "1}"},
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 11, "output_tokens": 7},
}


def request(**overrides: Any) -> Request:  # noqa: ANN401 - test helper forwarding field overrides
    fields: dict[str, Any] = {
        "ranker": "llm",
        "repeat": 0,
        "attempt": 0,
        "model": "claude-sonnet-5-5",
        "system": "sys",
        "prompt": "hello",
        "max_tokens": 100,
    }
    return Request(**{**fields, **overrides})


def response(input_tokens: int = 1000, output_tokens: int = 500) -> Response:
    return Response("ok", input_tokens, output_tokens, "end_turn", "req_1", "claude-sonnet-5-5")


class FakeTransport:
    def __init__(self, reply: Response | Exception) -> None:
        self.reply = reply
        self.calls: list[tuple[Request, Mapping[str, object] | None]] = []

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:
        self.calls.append((request, schema))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeHTTP:
    """A fake HTTP transport: the real SDK parses a canned reply and nothing hits the network."""

    def __init__(self, status: int = 200, body: Mapping[str, object] = MESSAGE) -> None:
        self.status = status
        self.body = body
        self.sent: list[dict[str, Any]] = []

    def transport(self, **options: Any) -> AnthropicTransport:  # noqa: ANN401 - forwarded options
        def handle(http_request: httpx2.Request) -> httpx2.Response:
            self.sent.append(json.loads(http_request.content))
            return httpx2.Response(self.status, json=self.body, headers={"request-id": "req_abc"})

        http_client = httpx2.Client(transport=httpx2.MockTransport(handle))
        return AnthropicTransport(KEY, http_client=http_client, **options)


def test_client_returns_the_response_and_tracks_spend() -> None:
    client = LLMClient(FakeTransport(response()), max_usd=1.0)
    assert client.complete(request()) == response()
    assert client.spent_usd == pytest.approx(1000 * 2 / 1e6 + 500 * 10 / 1e6)


def test_client_passes_the_schema_to_the_transport() -> None:
    transport = FakeTransport(response())
    LLMClient(transport, max_usd=1.0).complete(request(), {"type": "object"})
    assert transport.calls[0][1] == {"type": "object"}


def test_cap_stops_a_call_before_it_is_sent() -> None:
    transport = FakeTransport(response())
    client = LLMClient(transport, max_usd=0.001)
    with pytest.raises(CapExceededError, match="--max-usd"):
        client.complete(request(max_tokens=1000))
    assert transport.calls == []


def test_cap_accounts_for_earlier_spend_and_resume_seed() -> None:
    client = LLMClient(FakeTransport(response()), max_usd=0.01, spent_usd=0.0095)
    with pytest.raises(CapExceededError):
        client.complete(request())


def test_cap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        LLMClient(FakeTransport(response()), max_usd=0)


def test_unknown_model_is_refused_before_sending() -> None:
    transport = FakeTransport(response())
    with pytest.raises(UnknownModelError):
        LLMClient(transport, max_usd=1.0).complete(request(model="mystery"))
    assert transport.calls == []


def test_dry_run_transport_raises_on_send() -> None:
    client = LLMClient(DryRunTransport(), max_usd=1.0)
    with pytest.raises(DryRunError):
        client.complete(request())
    assert client.spent_usd == 0


def test_every_call_is_logged_with_cost_and_request_id() -> None:
    log: list[Mapping[str, object]] = []
    LLMClient(FakeTransport(response()), max_usd=1.0, log=log.append).complete(request())
    assert log[0]["request_id"] == "req_1"
    assert log[0]["resolved_model"] == "claude-sonnet-5-5"
    assert log[0]["input_tokens"] == 1000
    assert log[0]["cost_usd"] == pytest.approx(0.007)


def test_logs_redact_secrets_in_text_and_errors() -> None:
    log: list[Mapping[str, object]] = []
    leaky = Response(f"key {KEY}", 1, 1, "end_turn", "r", "claude-sonnet-5-5")
    LLMClient(FakeTransport(leaky), max_usd=1.0, log=log.append, secrets=(KEY,)).complete(request())
    assert KEY not in str(log)
    failing = FakeTransport(ProviderError(f"bad {KEY}"))
    with pytest.raises(ProviderError):
        LLMClient(failing, max_usd=1.0, log=log.append, secrets=(KEY,)).complete(request())
    assert KEY not in str(log)
    assert log[-1]["error"] == "bad [REDACTED]"


def test_redact_catches_key_shaped_strings_without_being_told() -> None:
    assert redact(f"x {KEY} y") == "x [REDACTED] y"
    assert redact("plain", ("",)) == "plain"


def test_anthropic_transport_maps_the_message_to_a_neutral_response() -> None:
    result = FakeHTTP().transport().send(request(), None)
    assert result == Response('{"a":1}', 11, 7, "end_turn", "req_abc", "claude-sonnet-5-5-20261001")


def test_anthropic_transport_request_shape() -> None:
    fake = FakeHTTP()
    fake.transport().send(request(), {"type": "object"})
    sent = fake.sent[0]
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["max_tokens"] == 100
    assert sent["thinking"] == {"type": "between_tools"}
    assert sent["output_config"] == {
        "effort": "high",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    for sampling in ("temperature", "top_p", "top_k"):
        assert sampling not in sent


def test_anthropic_transport_adaptive_thinking_and_no_schema() -> None:
    fake = FakeHTTP()
    fake.transport(thinking="adaptive", effort="medium").send(request(), None)
    assert fake.sent[0]["thinking"] == {"type": "adaptive"}
    assert fake.sent[0]["output_config"] == {"effort": "medium"}


def test_provider_errors_become_redacted_provider_errors() -> None:
    error = {"type": "error", "error": {"type": "authentication_error", "message": f"bad {KEY}"}}
    with pytest.raises(ProviderError) as caught:
        FakeHTTP(401, error).transport().send(request(), None)
    assert KEY not in str(caught.value)
    assert "AuthenticationError" in str(caught.value)


def test_key_comes_from_the_environment_first(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    assert load_api_key({"ANTHROPIC_API_KEY": "from-env"}, dotenv) == "from-env"


def test_key_falls_back_to_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("OTHER=1\nexport ANTHROPIC_API_KEY='quoted'\n", encoding="utf-8")
    assert load_api_key({}, dotenv) == "quoted"


def test_missing_key_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(MissingKeyError):
        load_api_key({}, tmp_path / "absent.env")
    with pytest.raises(MissingKeyError):
        load_api_key({}, None)


WORST_CASE = (((len("sys") + len("hello")) // 3 + 1) * 2 + 100 * 10) / 1e6  # for `request()`


class Script:
    """A transport that replays a list of replies, one per send."""

    def __init__(self, *replies: Response | Exception) -> None:
        self.replies = list(replies)
        self.sent = 0

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:  # noqa: ARG002 - Transport signature
        self.sent += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_transient_errors_are_retried_with_backoff_and_every_try_is_logged() -> None:
    log: list[Mapping[str, object]] = []
    sleeps: list[float] = []
    script = Script(
        ProviderError("429", transient=True), ProviderError("503", transient=True), response()
    )
    client = LLMClient(script, max_usd=1.0, log=log.append, sleep=sleeps.append)
    assert client.complete(request()) == response()
    assert sleeps == [1.0, 2.0]
    assert [record["try"] for record in log] == [1, 2, 3]
    assert [record["cost_usd"] for record in log[:2]] == [WORST_CASE, WORST_CASE]
    assert client.spent_usd == pytest.approx(2 * WORST_CASE + 0.007)


def test_backoff_is_capped() -> None:
    sleeps: list[float] = []
    errors = [ProviderError("5xx", transient=True) for _ in range(6)]
    client = LLMClient(Script(*errors), max_usd=1.0, max_attempts=6, sleep=sleeps.append)
    with pytest.raises(ProviderError):
        client.complete(request())
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 8.0]


def test_client_gives_up_after_max_attempts_and_charges_each_reserved_cost() -> None:
    script = Script(*[ProviderError("down", transient=True) for _ in range(3)])
    client = LLMClient(script, max_usd=1.0, sleep=lambda _seconds: None)
    with pytest.raises(ProviderError):
        client.complete(request())
    assert script.sent == 3
    assert client.spent_usd == pytest.approx(3 * WORST_CASE)


def test_permanent_errors_are_not_retried() -> None:
    script = Script(ProviderError("billed but permanent"))
    client = LLMClient(script, max_usd=1.0, sleep=lambda _seconds: None)
    with pytest.raises(ProviderError):
        client.complete(request())
    assert script.sent == 1
    assert client.spent_usd == pytest.approx(WORST_CASE)


def test_an_error_that_proves_nothing_was_billed_costs_nothing() -> None:
    client = LLMClient(Script(ProviderError("400", billed=False)), max_usd=1.0)
    with pytest.raises(ProviderError):
        client.complete(request())
    assert client.spent_usd == 0


def test_a_retry_that_would_cross_the_cap_is_refused() -> None:
    script = Script(ProviderError("down", transient=True), response())
    client = LLMClient(script, max_usd=1.5 * WORST_CASE, sleep=lambda _seconds: None)
    with pytest.raises(CapExceededError):
        client.complete(request())
    assert script.sent == 1
    assert client.spent_usd <= 1.5 * WORST_CASE


def test_dry_run_failure_is_logged_but_costs_nothing_and_is_not_retried() -> None:
    log: list[Mapping[str, object]] = []
    client = LLMClient(DryRunTransport(), max_usd=1.0, log=log.append)
    with pytest.raises(DryRunError):
        client.complete(request())
    assert len(log) == 1
    assert client.spent_usd == 0


@pytest.mark.parametrize(
    ("status", "transient", "billed"),
    [(429, True, True), (500, True, True), (529, True, True), (400, False, False)],
)
def test_http_statuses_map_to_retry_and_billing_flags(
    status: int, *, transient: bool, billed: bool
) -> None:
    fake = FakeHTTP(status, {"type": "error", "error": {"type": "x", "message": "m"}})
    with pytest.raises(ProviderError) as caught:
        fake.transport().send(request(), None)
    assert (caught.value.transient, caught.value.billed) == (transient, billed)
    assert len(fake.sent) == 1  # the SDK does not retry on its own


def test_connection_errors_are_transient_and_possibly_billed() -> None:
    def refuse(_request: httpx2.Request) -> httpx2.Response:
        msg = "refused"
        raise httpx2.ConnectError(msg)

    http_client = httpx2.Client(transport=httpx2.MockTransport(refuse))
    with pytest.raises(ProviderError) as caught:
        AnthropicTransport(KEY, http_client=http_client).send(request(), None)
    assert (caught.value.transient, caught.value.billed) == (True, True)
