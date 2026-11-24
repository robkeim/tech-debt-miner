"""The one LLM client: the only module that imports the provider SDK (ADR 0002, ADR 0014).

Callers build a `Request` and get a provider-neutral `Response`. Everything provider-specific
lives here: structured output, thinking settings, omitting non-default sampling parameters
(ADR 0012), the price table behind the USD cap, and error handling. Dry-run is a transport that
raises on send, not a flag.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import anthropic
import httpx2

from tech_debt_miner.types import Request, Response

DEFAULT_MAX_USD = 4.0  # ADR 0010; raised only via `--max-usd`
KEY_VARIABLE = "ANTHROPIC_API_KEY"
CHARS_PER_TOKEN = 3  # conservative: overestimates tokens, so the cap check errs toward stopping
REDACTED = "[REDACTED]"
_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Price:
    input_per_mtok: float  # USD per million input tokens
    output_per_mtok: float  # USD per million output tokens


# List prices as of 2026-11-03 (ADR 0010). Models absent here are refused, so the cap can't be
# bypassed by a model whose price is unknown.
PRICES: Mapping[str, Price] = {"claude-sonnet-5-5": Price(2.0, 10.0)}


class LLMError(Exception):
    """Base class for every error the client raises."""


class DryRunError(LLMError):
    """Raised by the Dry-run transport on send."""


class CapExceededError(LLMError):
    """The next call could push spend over the per-run USD cap."""


class UnknownModelError(LLMError):
    """The model has no entry in `PRICES`."""


class MissingKeyError(LLMError):
    """No API key in the environment or `.env`."""


class ProviderError(LLMError):
    """The provider call failed. The message is already redacted."""


class Transport(Protocol):
    """Sends one request. The seam where tests inject a fake and Dry-run injects a raiser."""

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response: ...


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Replace the given secrets and anything shaped like an Anthropic key."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return _KEY_PATTERN.sub(REDACTED, text)


def load_api_key(env: Mapping[str, str], dotenv: Path | None = None) -> str:
    """Read the key from `env`, then from a `.env` file. Nowhere else."""
    if key := env.get(KEY_VARIABLE):
        return key
    if dotenv is not None and dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() == KEY_VARIABLE and (key := value.strip().strip("\"'")):
                return key
    msg = f"{KEY_VARIABLE} is not set in the environment or .env"
    raise MissingKeyError(msg)


class DryRunTransport:
    """Sends nothing: any call that reaches it is a bug in the Dry-run path."""

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:  # noqa: ARG002 - Transport signature
        msg = "Dry-run makes no LLM calls"
        raise DryRunError(msg)


class AnthropicTransport:
    """The Anthropic Messages API behind the `Transport` seam.

    Tests inject an `http_client` with a fake HTTP transport, so the real SDK parses canned
    replies and nothing touches the network (ADR 0003).
    """

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx2.Client | None = None,
        thinking: Literal["off", "adaptive"] = "off",
        effort: Literal["low", "medium", "high"] = "high",
        max_retries: int = 2,
    ) -> None:
        self._sdk = anthropic.Anthropic(
            api_key=api_key, http_client=http_client, max_retries=max_retries
        )
        self._thinking = thinking
        self._effort: Literal["low", "medium", "high"] = effort
        self._secrets = (api_key,)

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:
        # temperature, top_p and top_k are never sent: the model rejects non-default values
        # (ADR 0012).
        output_config: anthropic.types.OutputConfigParam = {"effort": self._effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": dict(schema)}
        # Sonnet 5.5 rejects `{"type": "disabled"}`; `between_tools` is how thinking is off
        # (ADR 0010).
        thinking: anthropic.types.ThinkingConfigParam = (
            {"type": "adaptive"} if self._thinking == "adaptive" else {"type": "between_tools"}
        )
        try:
            message = self._sdk.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.prompt}],
                thinking=thinking,
                output_config=output_config,
            )
        except anthropic.APIError as error:
            raise ProviderError(redact(f"{type(error).__name__}: {error}", self._secrets)) from None
        return Response(
            text="".join(block.text for block in message.content if block.type == "text"),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason or "unknown",
            request_id=getattr(message, "_request_id", None) or message.id,  # set by the SDK
            model=message.model,
        )


class LLMClient:
    """Enforces the USD cap and logs every call around a `Transport`."""

    def __init__(
        self,
        transport: Transport,
        *,
        max_usd: float,
        log: Callable[[Mapping[str, object]], None] = lambda _record: None,
        secrets: tuple[str, ...] = (),
        spent_usd: float = 0.0,
    ) -> None:
        if max_usd <= 0:
            msg = "max_usd must be positive"
            raise ValueError(msg)
        self._transport = transport
        self._max_usd = max_usd
        self._log = log
        self._secrets = secrets
        self.spent_usd = spent_usd  # seed from cost.json when resuming a Run

    def complete(self, request: Request, schema: Mapping[str, object] | None = None) -> Response:
        price = PRICES.get(request.model)
        if price is None:
            msg = f"no price for model {request.model!r}; add it to PRICES"
            raise UnknownModelError(msg)
        worst_case = _cost(
            price,
            (len(request.system) + len(request.prompt)) // CHARS_PER_TOKEN + 1,
            request.max_tokens,
        )
        if self.spent_usd + worst_case > self._max_usd:
            msg = (
                f"spent ${self.spent_usd:.2f} plus worst case ${worst_case:.2f} "
                f"exceeds the ${self._max_usd:.2f} cap; raise it with --max-usd"
            )
            raise CapExceededError(msg)
        try:
            response = self._transport.send(request, schema)
        except LLMError as error:
            self._record(request, error=redact(str(error), self._secrets))
            raise
        cost = _cost(price, response.input_tokens, response.output_tokens)
        self.spent_usd += cost
        self._record(request, response=response, cost=cost)
        return response

    def _record(
        self,
        request: Request,
        *,
        response: Response | None = None,
        cost: float = 0.0,
        error: str | None = None,
    ) -> None:
        record: dict[str, object] = {
            "ranker": request.ranker,
            "repeat": request.repeat,
            "attempt": request.attempt,
            "model": request.model,
            "cost_usd": cost,
            "spent_usd": self.spent_usd,
        }
        if response is not None:
            record |= {
                "text": redact(response.text, self._secrets),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "stop_reason": response.stop_reason,
                "request_id": response.request_id,
                "resolved_model": response.model,
            }
        if error is not None:
            record["error"] = error
        self._log(record)


def _cost(price: Price, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
