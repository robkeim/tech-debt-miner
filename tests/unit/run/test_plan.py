from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner import cli
from tech_debt_miner.llm.client import PRICES, UnknownModelError, cost_usd
from tech_debt_miner.rankers.prompts import (
    RANK_MAX_TOKENS,
    SYSTEM,
    TRIAGE_MAX_TOKENS,
    DigestOverflowError,
    build_triage_prompt,
)
from tech_debt_miner.run.artifacts import ESTIMATE, MANIFEST, REQUESTS, SNAPSHOT
from tech_debt_miner.run.plan import EstimateExceedsCapError, PlanDeps, plan, render
from tech_debt_miner.run.run_dir import RunDir, RunState
from tech_debt_miner.types import FileFacts, Manifest, Request, Snapshot

pytestmark = pytest.mark.unit

MODEL = "claude-sonnet-5-5"
MANIFEST_VALUE = Manifest(
    target_repo="owner/repo",
    pinned_sha="a" * 40,
    cutoff_date="2025-01-31",
    model=MODEL,
    model_training_cutoff="2024-06-01",
    cutoff_minus_training_days=244,
    repeats=3,
    prompt_hashes={},
    lizard_version="1.17",
    adr_shas={},
    tool_sha="c" * 40,
)


def file(path: str, *, head: str = "x = 1") -> FileFacts:
    return FileFacts(path, 5, 1, 1.0, (), head, 0, ())


def new_run(tmp_path: Path, *files: FileFacts, manifest: Manifest = MANIFEST_VALUE) -> RunDir:
    run_dir = RunDir.create(tmp_path, manifest, lambda: datetime(2026, 1, 1, tzinfo=UTC))
    run_dir.write(SNAPSHOT, Snapshot(files=files, issues=(), zero_complexity_files=0))
    return run_dir


def test_plan_writes_the_stage_1_request_of_every_repeat_and_the_estimate(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a.py"), file("b.py"))

    estimate = plan(run_dir, PlanDeps(max_usd=4.0))

    prompt = build_triage_prompt(run_dir.read(SNAPSHOT))
    assert run_dir.read_all(REQUESTS) == [
        Request("llm", repeat, 0, MODEL, SYSTEM, prompt, TRIAGE_MAX_TOKENS) for repeat in range(3)
    ]
    assert run_dir.read(ESTIMATE) == estimate
    assert estimate.triage_output_tokens == TRIAGE_MAX_TOKENS
    assert estimate.rank_output_tokens == RANK_MAX_TOKENS
    assert run_dir.state() is RunState.PLANNED


def test_the_estimate_prices_both_stages_at_the_models_list_price(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a.py"))

    estimate = plan(run_dir, PlanDeps(max_usd=4.0))

    price = PRICES[MODEL]
    one_repeat = cost_usd(price, estimate.triage_input_tokens, TRIAGE_MAX_TOKENS) + cost_usd(
        price, estimate.rank_input_tokens, RANK_MAX_TOKENS
    )
    assert estimate.total_usd == pytest.approx(3 * one_repeat)


def test_stage_2_is_estimated_at_the_largest_triage_set(tmp_path: Path) -> None:
    small = [file(f"small_{n:03}.py") for n in range(100)]
    big = file("big.py", head="y = 2\n" * 400)
    with_big = new_run(tmp_path / "a", *small, big)
    without_big = new_run(tmp_path / "b", *small)

    assert (
        plan(with_big, PlanDeps(max_usd=4.0)).rank_input_tokens
        > plan(without_big, PlanDeps(max_usd=4.0)).rank_input_tokens
    )


def test_an_estimate_over_the_cap_is_recorded_but_the_run_is_not_planned(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a.py"))

    with pytest.raises(EstimateExceedsCapError, match="--max-usd"):
        plan(run_dir, PlanDeps(max_usd=0.0001))

    assert run_dir.exists(ESTIMATE)
    assert not run_dir.exists(REQUESTS)
    assert run_dir.state() is RunState.RESOLVED


def test_a_digest_that_overflows_at_path_and_loc_fails_the_plan(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a" * 3_000_000 + ".py"))

    with pytest.raises(DigestOverflowError):
        plan(run_dir, PlanDeps(max_usd=1_000.0))

    assert not run_dir.exists(REQUESTS)


def test_a_model_without_a_price_fails_before_anything_is_written(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a.py"), manifest=replace(MANIFEST_VALUE, model="unpriced"))

    with pytest.raises(UnknownModelError):
        plan(run_dir, PlanDeps(max_usd=4.0))

    assert not run_dir.exists(ESTIMATE)
    assert not run_dir.exists(REQUESTS)


def test_render_shows_per_stage_tokens_and_the_cost_against_the_cap(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path, file("a.py"))

    text = render(plan(run_dir, PlanDeps(max_usd=4.0)), 4.0)

    assert "stage 1 (triage)" in text
    assert "stage 2 (rank)" in text
    assert "of the $4 cap" in text


def test_the_resume_command_prints_the_estimate_and_needs_no_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run_dir = new_run(tmp_path, file("a.py"))
    args = ["resume", run_dir.id, "--runs-dir", str(tmp_path)]

    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert "estimated cost for 3 repeats" in out
    assert out.strip().endswith("ran: plan; state: planned")


def test_the_resume_command_refuses_an_estimate_over_the_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = new_run(tmp_path, file("a.py"))

    code = cli.main(["resume", run_dir.id, "--runs-dir", str(tmp_path), "--max-usd", "0.0001"])

    assert code == 1
    captured = capsys.readouterr()
    assert "estimated cost for 3 repeats" in captured.out
    assert "exceeds the $0.0001 cap" in captured.err
    assert run_dir.state() is RunState.RESOLVED


def test_the_resume_command_reports_an_overflowing_repo_as_excluded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = new_run(tmp_path, file("a" * 3_000_000 + ".py"))

    assert cli.main(["resume", run_dir.id, "--runs-dir", str(tmp_path)]) == 1
    assert "excluded: owner/repo:" in capsys.readouterr().err
    assert run_dir.read(MANIFEST).target_repo == "owner/repo"


def test_a_plan_interrupted_between_requests_is_not_done_and_resumes_cleanly(
    tmp_path: Path,
) -> None:
    run_dir = new_run(tmp_path, file("a.py"))
    plan(run_dir, PlanDeps(max_usd=4.0))
    rows = run_dir.read_all(REQUESTS)
    (run_dir.path / "requests.jsonl").write_text(
        (run_dir.path / "requests.jsonl").read_text().splitlines()[0] + "\n"
    )
    assert run_dir.state() is RunState.RESOLVED

    plan(run_dir, PlanDeps(max_usd=4.0))

    assert sorted(r.repeat for r in run_dir.read_all(REQUESTS)) == [r.repeat for r in rows]
    assert run_dir.state() is RunState.PLANNED
