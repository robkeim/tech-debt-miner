from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tech_debt_miner.llm.cache import ResponseCache, cache_key
from tech_debt_miner.types import Request, Response

pytestmark = pytest.mark.unit

REQUESTS = st.builds(
    Request,
    ranker=st.sampled_from(["baseline", "llm"]),
    repeat=st.integers(0, 5),
    attempt=st.integers(0, 2),
    model=st.sampled_from(["m1", "m2"]),
    system=st.text(),
    prompt=st.text(),
    max_tokens=st.integers(1, 10_000),
)
SCHEMAS = st.one_of(st.none(), st.dictionaries(st.text(max_size=5), st.integers(), max_size=3))

RESPONSE = Response("ok", 10, 5, "end_turn", "req_1", "m1-snapshot")


@given(REQUESTS, SCHEMAS)
def test_key_is_stable_and_ignores_the_ranker_label(
    request: Request, schema: dict[str, int] | None
) -> None:
    assert cache_key(request, schema) == cache_key(replace(request, ranker="other"), schema)
    assert cache_key(request, schema) == cache_key(replace(request), schema)


@given(REQUESTS, SCHEMAS, st.integers(1, 3))
def test_key_changes_with_repeat_and_attempt(
    request: Request, schema: dict[str, int] | None, step: int
) -> None:
    key = cache_key(request, schema)
    assert key != cache_key(replace(request, repeat=request.repeat + step), schema)
    assert key != cache_key(replace(request, attempt=request.attempt + step), schema)


@given(REQUESTS, SCHEMAS, st.text(min_size=1))
def test_key_changes_with_every_field_the_api_sees(
    request: Request, schema: dict[str, int] | None, extra: str
) -> None:
    key = cache_key(request, schema)
    assert key != cache_key(replace(request, prompt=request.prompt + extra), schema)
    assert key != cache_key(replace(request, system=request.system + extra), schema)
    assert key != cache_key(replace(request, model=request.model + extra), schema)
    assert key != cache_key(replace(request, max_tokens=request.max_tokens + 1), schema)
    assert key != cache_key(request, {**(schema or {}), extra: 1})


SETTINGS = st.fixed_dictionaries(
    {"thinking": st.sampled_from(["off", "adaptive"]), "effort": st.sampled_from(["low", "high"])}
)


@given(REQUESTS, SCHEMAS, SETTINGS)
def test_key_is_stable_for_identical_settings_and_changes_with_each(
    request: Request, schema: dict[str, int] | None, settings: dict[str, str]
) -> None:
    key = cache_key(request, schema, settings)
    assert key == cache_key(request, schema, dict(reversed(settings.items())))
    assert key != cache_key(request, schema, {**settings, "thinking": settings["thinking"] + "x"})
    assert key != cache_key(request, schema, {**settings, "effort": settings["effort"] + "x"})


def test_a_cache_with_other_settings_misses(tmp_path: Path) -> None:
    request = Request("llm", 0, 0, "m1", "s", "p", 10)
    ResponseCache(tmp_path, {"thinking": "off", "effort": "high"}).put(request, RESPONSE)
    assert ResponseCache(tmp_path, {"thinking": "off", "effort": "high"}).get(request) == RESPONSE
    assert ResponseCache(tmp_path, {"thinking": "adaptive", "effort": "high"}).get(request) is None
    assert ResponseCache(tmp_path, {"thinking": "off", "effort": "low"}).get(request) is None


@given(st.dictionaries(st.text(max_size=3), st.integers(), min_size=2, max_size=4))
def test_key_ignores_schema_key_order(schema: dict[str, int]) -> None:
    request = Request("llm", 0, 0, "m1", "s", "p", 10)
    flipped = dict(reversed(schema.items()))
    assert cache_key(request, schema) == cache_key(request, flipped)


def test_put_then_get_round_trips(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "responses")
    request = Request("llm", 0, 0, "m1", "s", "p", 10)
    assert cache.get(request) is None
    cache.put(request, RESPONSE)
    assert cache.get(request) == RESPONSE
    assert cache.get(replace(request, repeat=1)) is None


def test_a_corrupt_entry_is_a_miss_and_is_replaced(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    request = Request("llm", 0, 0, "m1", "s", "p", 10)
    cache.put(request, RESPONSE)
    (entry,) = tmp_path.glob("*/*.json")
    entry.write_text("{not json", encoding="utf-8")
    assert cache.get(request) is None
    cache.put(request, RESPONSE)
    assert cache.get(request) == RESPONSE
