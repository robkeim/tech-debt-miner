import json
from collections.abc import Mapping
from dataclasses import replace

import pytest

from tech_debt_miner.llm.client import LLMClient
from tech_debt_miner.rankers.llm import (
    LLM,
    RANK_MAX_TOKENS,
    TRIAGE,
    TRIAGE_MAX_TOKENS,
    LLMRanker,
    RankFailed,
    parse_ranking,
    parse_triage,
)
from tech_debt_miner.types import FileFacts, Request, Response, Snapshot

pytestmark = pytest.mark.unit

MODEL = "claude-sonnet-5-5"
OK = Response("", 100, 50, "end_turn", "req_1", MODEL)


def snapshot_of(count: int) -> Snapshot:
    files = tuple(
        FileFacts(
            path=f"m{n:03}.py",
            loc=10,
            churn=1,
            complexity=1.0,
            outline=(),
            head="x = 1",
            truncated_lines=0,
            recent_commits=(),
        )
        for n in range(count)
    )
    return Snapshot(files=files, issues=(), zero_complexity_files=0)


class Script:
    """A transport that replies with each text in turn and records its calls."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.calls: list[tuple[Request, Mapping[str, object] | None]] = []

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:
        self.calls.append((request, schema))
        return replace(OK, text=self.texts.pop(0))


def triage_reply(*paths: str) -> str:
    return json.dumps({"paths": list(paths)})


def rank_reply(*paths: str) -> str:
    return json.dumps({"ranking": [{"path": p, "rationale": f"why {p}"} for p in paths]})


def ranker_for(script: Script) -> LLMRanker:
    return LLMRanker(LLMClient(script, max_usd=10.0), model=MODEL)


def test_two_stages_return_the_stage_2_order_as_singleton_groups() -> None:
    snapshot = snapshot_of(3)
    script = Script(triage_reply("m002.py", "m000.py", "m001.py"), rank_reply("m001.py", "m000.py"))

    ranking = ranker_for(script).rank(snapshot, repeat=2)

    assert (ranking.ranker, ranking.repeat) == (LLM, 2)
    assert ranking.groups == (("m001.py",), ("m000.py",))
    (triage, triage_schema), (rank, rank_schema) = script.calls
    assert (triage.ranker, rank.ranker) == (TRIAGE, LLM)
    assert (triage.repeat, rank.repeat) == (2, 2)
    assert (triage.attempt, rank.attempt) == (0, 0)
    assert (triage.max_tokens, rank.max_tokens) == (TRIAGE_MAX_TOKENS, RANK_MAX_TOKENS)
    assert triage_schema is not None
    assert rank_schema is not None
    assert "paths" in triage_schema["properties"]  # type: ignore[operator]
    assert "ranking" in rank_schema["properties"]  # type: ignore[operator]


def test_rationales_and_the_triage_set_stay_out_of_the_ranking() -> None:
    script = Script(triage_reply("m000.py"), rank_reply("m000.py"))

    ranking = ranker_for(script).rank(snapshot_of(1), repeat=0)

    assert "why" not in repr(ranking)


def test_the_triage_set_is_capped_at_100_and_stage_2_sees_exactly_those_files() -> None:
    snapshot = snapshot_of(120)
    chosen = [f"m{n:03}.py" for n in range(100)]
    script = Script(triage_reply(*chosen), rank_reply("m000.py"))

    ranker_for(script).rank(snapshot, repeat=0)

    rank_prompt = script.calls[1][0].prompt
    assert "=== m099.py ===" in rank_prompt
    assert "=== m100.py ===" not in rank_prompt


def test_thinking_headroom_raises_both_output_limits() -> None:
    script = Script(triage_reply("m000.py"), rank_reply("m000.py"))

    LLMRanker(LLMClient(script, max_usd=10.0), model=MODEL, thinking_headroom=1000).rank(
        snapshot_of(1), repeat=0
    )

    assert [call[0].max_tokens for call in script.calls] == [
        TRIAGE_MAX_TOKENS + 1000,
        RANK_MAX_TOKENS + 1000,
    ]


def test_a_malformed_reply_is_retried_once_with_the_error_and_a_new_attempt() -> None:
    script = Script("not json", triage_reply("m000.py"), rank_reply("m000.py"))

    ranking = ranker_for(script).rank(snapshot_of(1), repeat=0)

    first, retry, _ = (call[0] for call in script.calls)
    assert (first.attempt, retry.attempt) == (0, 1)
    assert retry.prompt.startswith(first.prompt)
    assert "not valid JSON" in retry.prompt
    assert ranking.groups == (("m000.py",),)


def test_a_stage_2_retry_goes_through_the_same_path() -> None:
    script = Script(triage_reply("m000.py"), rank_reply(), rank_reply("m000.py"))

    ranker_for(script).rank(snapshot_of(1), repeat=0)

    assert [(c[0].ranker, c[0].attempt) for c in script.calls] == [(TRIAGE, 0), (LLM, 0), (LLM, 1)]
    assert "the ranking is empty" in script.calls[2][0].prompt


@pytest.mark.parametrize("bad", ["nope", rank_reply()])
def test_two_malformed_replies_raise_rank_failed_and_never_an_empty_ranking(bad: str) -> None:
    script = Script(triage_reply("m000.py"), bad, bad)

    with pytest.raises(RankFailed):
        ranker_for(script).rank(snapshot_of(1), repeat=0)
    assert len(script.calls) == 3


def test_a_failed_stage_1_stops_before_stage_2() -> None:
    script = Script("bad", "worse")

    with pytest.raises(RankFailed):
        ranker_for(script).rank(snapshot_of(1), repeat=0)
    assert len(script.calls) == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[]", 'a "paths" array'),
        ('{"paths": [1]}', "only strings"),
        (triage_reply("ghost.py", "m000.py"), "ghost.py"),
        (triage_reply("m000.py", "m000.py"), "exactly 2 distinct"),
        (triage_reply("m000.py"), "exactly 2 distinct"),
    ],
)
def test_parse_triage_rejects_what_would_break_stage_2(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_triage(text, snapshot_of(2))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{", "not valid JSON"),
        ('{"ranking": 3}', 'a "ranking" array'),
        ('{"ranking": ["a.py"]}', "string"),
        ('{"ranking": [{"path": 1}]}', "string"),
        (rank_reply(), "empty"),
        (rank_reply(*(f"f{n}.py" for n in range(51))), "at most 50"),
    ],
)
def test_parse_ranking_rejects_malformed_replies(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_ranking(text)


def test_parse_ranking_keeps_duplicates_and_unknown_paths_for_scoring_to_handle() -> None:
    assert parse_ranking(rank_reply("a.py", "a.py", "ghost.py")) == ("a.py", "a.py", "ghost.py")
