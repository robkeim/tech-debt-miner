# The client returns a provider-neutral Response, and `anthropic` is a dependency

Accepted. Decided in #82. It fills in how [ADR 0002](0002-single-llm-client-choke-point.md) is built, at the path [ADR 0009](0009-code-layout-and-core-types.md) names, `src/tech_debt_miner/llm/client.py`.

## Decision

- **Dependency.** `anthropic` is a runtime dependency, declared as a range (`anthropic>=2.14.0`) and pinned exactly by `uv.lock`. The range lets `uv lock --upgrade-package anthropic` move it deliberately; the lockfile is what a Run uses, and CI installs from it.
- **SDK confinement.** `llm/client.py` is the only module that imports `anthropic`. `tests/policy/test_sdk_imports.py` enforces it with `CLIENT_MODULE` set to that path and `SDKS = {"anthropic"}` (this settles #46).
- **Provider-neutral `Response`.** The client returns a frozen stdlib dataclass in `types.py`: `text`, `input_tokens`, `output_tokens`, `stop_reason`, `request_id` and the resolved `model`. The cache, the per-call log and the rankers never see an SDK object.
- **Injected transport.** `LLMClient` wraps a `Transport` with one method, `send(request, schema) -> Response`. The client owns the USD cap, logging and redaction. Real runs inject `AnthropicTransport`, Dry-run injects `DryRunTransport`, which raises on send, and tests inject either a fake `Transport` or `AnthropicTransport` over a fake HTTP transport, so the real SDK parses canned replies and nothing touches the network ([ADR 0003](0003-tests-never-touch-network-or-llm.md)).
- **Provider details stay in `client.py`.** Structured output via `output_config.format`, the thinking and effort settings from [ADR 0010](0010-llm-ranker-design.md), omitting `temperature`, `top_p` and `top_k` ([ADR 0012](0012-llm-repeats-use-default-sampling.md)), and the per-model price table behind the cap.
- **The cap.** A call is refused before it is sent when spend so far plus its worst case (a conservative input estimate plus `max_tokens` of output) would exceed `--max-usd`; the default is $4 ([ADR 0010](0010-llm-ranker-design.md)). A model with no price entry is refused, so an unpriced model can't slip past the cap.
- **Reservation.** Before every attempt, retries included, the client reserves the call's worst case (a conservative input estimate plus `max_tokens` of output, at the model's price) and refuses to send if spend plus that reservation would pass the cap. A successful attempt is accounted at its actual cost. A failed attempt is accounted at its reserved cost unless the error proves nothing was billed, so a billed failure can never push spend past the cap.
- **Retries.** The SDK's own retries are off (`max_retries=0`), so every attempt passes the cap check and is logged. The client retries only transient errors, up to 3 attempts, with a doubling backoff of 1 s, 2 s, ... capped at 8 s. Sleeping is injected so tests never wait. Transient means HTTP 408, 409, 429, any 5xx, and connection errors or timeouts. Any other 4xx is permanent: it is rejected before generation, so it is retried never and accounted at $0. A connection error may have been generated and billed, so it is accounted at its reserved cost.
- **Per-attempt log.** Each attempt writes one log record with its try number, cost and, on failure, the redacted error.
- **The key.** Read from `ANTHROPIC_API_KEY` in the environment, then from a gitignored `.env`. Logs and errors pass through redaction of the key and of anything shaped like an Anthropic key.

## Why

- **One boundary, narrow in what it exposes.** Cache keys, logs and Replay ([ADR 0001](0001-reproducibility-means-replay.md)) depend on what `Response` holds, not on an SDK version's object shapes, so an SDK upgrade can't change the on-disk format.
- **Fake transports test more than a fake client.** Injecting at the HTTP layer runs the real SDK's parsing and error mapping with no network.
- **A range with a lockfile** keeps upgrades deliberate without hand-editing a pin.

## Known limits

- **pydantic arrives transitively.** `anthropic` depends on pydantic and others. [ADR 0009](0009-code-layout-and-core-types.md)'s "no pydantic dependency" is about our core types, which stay stdlib dataclasses; it does not forbid a dependency's own dependencies.
- **Tests import `httpx2`**, the HTTP library the SDK uses, to build the fake transport. It is a transitive dependency and not on the SDK list; if the SDK changes its HTTP library, the fake in `tests/unit/llm/test_client.py` changes with it.
- **Swapping provider is a rewrite of `client.py`**, its price table and `SDKS`, and nothing else, which is the point of the boundary. It is not free in meaning: the study design is anchored on the model ([ADR 0006](0006-target-repos-and-cutoff-dates.md) chose it for its training cutoff), so a different model is a different experiment, not a drop-in.
- **The Manifest does not record the SDK version.** The model snapshot and request IDs are logged; adding an SDK version field is a possible follow-up.
- **The Response cache and the thinking pilot** are separate work (`llm/cache.py`, #64).
- **The cap over-counts.** A call is refused when its worst case would not fit, even if the real reply would have, and a failed attempt that may have been billed is charged its full reservation although the provider probably billed less or nothing. Spend tracked here is therefore an upper bound on the invoice, never below it. We accept that so the cap is a hard ceiling, and `cost.json` should be read as "at most".
- **The cap check is not thread-safe**; the client is used from one thread.
- **A 4xx other than 408, 409 and 429 is assumed not billed.** If the provider ever bills a rejected request, spend can be under-counted by those calls.

## Alternatives rejected

- **Returning the SDK's `Message`.** It leaks provider shapes into the cache and rankers and makes the on-disk format depend on the SDK version.
- **A second provider now.** Nothing needs it, and an abstraction built for one provider is a guess.
- **An exact pin in `pyproject.toml`.** The lockfile already pins; an exact pin adds a manual edit for every upgrade.
- **Raw HTTP with no SDK.** Reimplements retries, error mapping and structured-output parameters for no gain.
