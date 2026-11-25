from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner.llm.cache import ResponseCache
from tech_debt_miner.llm.client import DryRunTransport, LLMClient
from tech_debt_miner.run.artifacts import RESPONSES
from tech_debt_miner.run.replay import final_responses, logged_responses, replay_rankings
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import LoggedResponse, Manifest, Ranking, Request, Response

pytestmark = pytest.mark.unit

MANIFEST = Manifest("o/r", "a" * 40, "2025-01-31", "m", "2024-06-01", 244, 2, {}, "1", {}, "c" * 40)
REQUEST = Request("llm", 0, 0, "claude-sonnet-5-5", "sys", "prompt", 100)


class Sequence:
    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)

    def send(self, request: Request, schema: object) -> Response:  # noqa: ARG002 - Transport signature
        return Response(self.texts.pop(0), 10, 5, "end_turn", "req", "claude-sonnet-5-5")


def make_run(tmp_path: Path) -> RunDir:
    return RunDir.create(tmp_path / "runs", MANIFEST, lambda: datetime(2026, 1, 1, tzinfo=UTC))


def sink(run: RunDir) -> Callable[[LoggedResponse], None]:
    return lambda row: run.append(RESPONSES, row)


def parse_paths(text: str) -> tuple[str, ...]:
    if not text.strip():
        msg = "empty"
        raise ValueError(msg)
    return tuple(text.split(","))


def test_replay_scores_from_the_run_directory_alone(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    cache = ResponseCache(tmp_path / "cache", {})
    client = LLMClient(
        Sequence("a.py,b.py", "b.py,a.py"),
        max_usd=1.0,
        cache=cache,
        on_response=sink(run),
    )
    client.complete(REQUEST)
    client.complete(replace(REQUEST, repeat=1))
    # Delete the cache; Replay must not need it, a client, or a repo.
    for entry in (tmp_path / "cache").glob("*/*.json"):
        entry.unlink()
    assert replay_rankings(run, parse_paths) == [
        Ranking("llm", 0, (("a.py",), ("b.py",))),
        Ranking("llm", 1, (("b.py",), ("a.py",))),
    ]


def test_cache_hits_are_copied_into_the_run_log(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache", {})
    LLMClient(Sequence("a.py"), max_usd=1.0, cache=cache).complete(REQUEST)
    run = make_run(tmp_path)
    client = LLMClient(DryRunTransport(), max_usd=1.0, cache=cache, on_response=sink(run))
    client.complete(REQUEST)
    (row,) = logged_responses(run)
    assert row.cache_hit
    assert row.response.text == "a.py"


def test_the_highest_attempt_wins(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    client = LLMClient(Sequence("", "a.py"), max_usd=1.0, on_response=sink(run))
    assert client.complete_parsed(REQUEST, parse_paths) == ("a.py",)
    assert [row.attempt for row in logged_responses(run)] == [0, 1]
    assert final_responses(run)["llm", 0].response.text == "a.py"
    assert replay_rankings(run, parse_paths) == [Ranking("llm", 0, (("a.py",),))]


def test_a_resume_that_logs_the_same_attempt_twice_collapses(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    cache = ResponseCache(tmp_path / "cache", {})
    for _ in range(2):
        LLMClient(Sequence("a.py"), max_usd=1.0, cache=cache, on_response=sink(run)).complete(
            REQUEST
        )
    assert len(logged_responses(run)) == 2
    assert len(final_responses(run)) == 1


def test_an_unparsable_final_reply_fails_instead_of_scoring_empty(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    LLMClient(Sequence(""), max_usd=1.0, on_response=sink(run)).complete(REQUEST)
    with pytest.raises(ValueError, match="empty"):
        replay_rankings(run, parse_paths)
