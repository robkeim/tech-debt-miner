from collections.abc import Mapping
from pathlib import Path

import pytest

from tech_debt_miner.llm.client import CapExceededError, LLMClient
from tech_debt_miner.run.artifacts import COST
from tech_debt_miner.run.cost import open_client
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Cost, CostAttempt, Request, Response

pytestmark = pytest.mark.unit

CALL_USD = 1000 * 2 / 1e6 + 500 * 10 / 1e6  # one reply: 1000 in, 500 out at $2 and $10 per Mtok


class FakeTransport:
    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:  # noqa: ARG002 - protocol
        return Response("ok", 1000, 500, "end_turn", "req_1", request.model)


def request(repeat: int = 0) -> Request:
    return Request("llm", repeat, 0, "claude-sonnet-5-5", "s", "p", 10)


def open_for(run: RunDir, max_usd: float) -> LLMClient:
    return open_client(run, FakeTransport(), max_usd=max_usd, on_response=lambda _row: None)


def test_a_first_attempt_logs_its_cap_before_any_call(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")

    open_for(run, 4.0)

    assert run.read(COST) == Cost((CostAttempt(4.0, 0.0),))


def test_each_call_is_persisted_as_it_happens(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")
    client = open_for(run, 4.0)

    client.complete(request(0))
    client.complete(request(1))

    cost = run.read(COST)
    assert [a.max_usd for a in cost.attempts] == [4.0]
    assert cost.spent_usd == pytest.approx(2 * CALL_USD)


def test_spend_accumulates_across_resumes_and_each_attempt_keeps_its_cap(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")
    open_for(run, 1.0).complete(request(0))

    open_for(run, 2.0).complete(request(1))

    cost = run.read(COST)
    assert [a.max_usd for a in cost.attempts] == [1.0, 2.0]
    assert [a.spent_usd for a in cost.attempts] == [pytest.approx(CALL_USD)] * 2
    assert cost.spent_usd == pytest.approx(2 * CALL_USD)


def test_the_cap_covers_the_run_total_not_one_attempt(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")
    cap = CALL_USD + 5e-5  # under one more call's worst case
    open_for(run, cap).complete(request(0))

    with pytest.raises(CapExceededError, match="--max-usd"):
        open_for(run, cap).complete(request(1))


def test_resuming_with_a_spent_cap_fails_before_logging_a_new_attempt(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")
    open_for(run, 1.0).complete(request(0))

    with pytest.raises(CapExceededError, match=r"raise it with --max-usd"):
        open_for(run, CALL_USD)

    assert len(run.read(COST).attempts) == 1


def test_a_higher_cap_resumes_past_the_old_one(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "run")
    cap = CALL_USD + 5e-5  # under one more call's worst case
    open_for(run, cap).complete(request(0))

    open_for(run, cap * 4).complete(request(1))

    assert run.read(COST).spent_usd == pytest.approx(2 * CALL_USD)
