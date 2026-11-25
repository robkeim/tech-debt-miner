"""The `plan` stage: build the stage 1 requests, estimate the Run's cost, and check the cap.

It is what makes a Run planned (ADR 0008, ADR 0024). It reads only `manifest.json` and
`snapshot.json`, makes no LLM call, and needs no key. A Run whose estimate exceeds the cap is
not planned, so `resume --run` cannot start it.
"""

from dataclasses import dataclass

from tech_debt_miner.llm.client import PRICES, UnknownModelError, cost_usd
from tech_debt_miner.rankers.prompts import (
    RANK_MAX_TOKENS,
    SYSTEM,
    TRIAGE_MAX_TOKENS,
    build_rank_prompt,
    build_triage_prompt,
    estimate_tokens,
    largest_triage_set,
)
from tech_debt_miner.run.artifacts import ESTIMATE, MANIFEST, REQUESTS, SNAPSHOT
from tech_debt_miner.run.run_dir import LLM, RunDir
from tech_debt_miner.types import Estimate, Request


class EstimateExceedsCapError(Exception):
    """The Dry-run's cost estimate is above `--max-usd`, so the Run does not start."""


@dataclass(frozen=True)
class PlanDeps:
    """Injected collaborators."""

    max_usd: float


def _input_tokens(prompt: str) -> int:
    return estimate_tokens(SYSTEM) + estimate_tokens(prompt)


def plan(run_dir: RunDir, deps: PlanDeps) -> Estimate:
    """Write `estimate.json`, then `requests.jsonl` unless the estimate exceeds the cap.

    `requests.jsonl` holds the stage 1 request of every repeat: exactly what a real Run sends
    first. Stage 2's prompt depends on the model's stage 1 reply, so it is estimated at its
    worst case and built at send time. Raises `DigestOverflowError` when the digest overflows at
    path and LOC only (the repo is excluded), `UnknownModelError` for a model with no price, and
    `EstimateExceedsCapError` when the estimate is above the cap.
    """
    manifest = run_dir.read(MANIFEST)
    snapshot = run_dir.read(SNAPSHOT)
    price = PRICES.get(manifest.model)
    if price is None:
        msg = f"no price for model {manifest.model!r}; add it to PRICES"
        raise UnknownModelError(msg)
    triage_prompt = build_triage_prompt(snapshot)
    rank_prompt = build_rank_prompt(snapshot, largest_triage_set(snapshot))
    triage_tokens, rank_tokens = _input_tokens(triage_prompt), _input_tokens(rank_prompt)
    per_repeat = cost_usd(price, triage_tokens, TRIAGE_MAX_TOKENS) + cost_usd(
        price, rank_tokens, RANK_MAX_TOKENS
    )
    estimate = Estimate(
        model=manifest.model,
        repeats=manifest.repeats,
        triage_input_tokens=triage_tokens,
        triage_output_tokens=TRIAGE_MAX_TOKENS,
        rank_input_tokens=rank_tokens,
        rank_output_tokens=RANK_MAX_TOKENS,
        total_usd=per_repeat * manifest.repeats,
    )
    run_dir.write(ESTIMATE, estimate)
    if estimate.total_usd > deps.max_usd:
        msg = (
            f"estimated ${estimate.total_usd:.2f} exceeds the ${deps.max_usd:g} cap; "
            "raise it with --max-usd"
        )
        raise EstimateExceedsCapError(msg)
    # A crash can leave some rows; the plan is done only when every repeat has one.
    written: set[int] = set()
    if run_dir.exists(REQUESTS):
        written = {row.repeat for row in run_dir.read_all(REQUESTS)}
    for repeat in sorted(set(range(manifest.repeats)) - written):
        run_dir.append(
            REQUESTS,
            Request(
                ranker=LLM,
                repeat=repeat,
                attempt=0,
                model=manifest.model,
                system=SYSTEM,
                prompt=triage_prompt,
                max_tokens=TRIAGE_MAX_TOKENS,
            ),
        )
    return estimate


def render(estimate: Estimate, max_usd: float) -> str:
    """Return the per-stage token estimates and the cost against the cap, for the CLI."""
    return (
        f"stage 1 (triage): ~{estimate.triage_input_tokens:,} input tokens, "
        f"up to {estimate.triage_output_tokens:,} output, per repeat\n"
        f"stage 2 (rank):   ~{estimate.rank_input_tokens:,} input tokens (worst case), "
        f"up to {estimate.rank_output_tokens:,} output, per repeat\n"
        f"estimated cost for {estimate.repeats} repeats: ${estimate.total_usd:.2f} "
        f"of the ${max_usd:g} cap\n"
    )
