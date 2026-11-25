"""Spend across resumes: `cost.json` accumulates, and each invocation logs its cap (ADR 0008).

`--max-usd` caps a Run's total spend, not one invocation's, and stays out of the Manifest. The
ledger seeds the client with what earlier invocations spent and persists after every client
record, so a crash loses at most the call in flight.
"""

from collections.abc import Callable

from tech_debt_miner.llm.client import CapExceededError, LLMClient, Transport
from tech_debt_miner.run.artifacts import COST
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Cost, CostAttempt, LoggedResponse


def open_client(
    run_dir: RunDir,
    transport: Transport,
    *,
    max_usd: float,
    on_response: Callable[[LoggedResponse], None],
) -> LLMClient:
    """Build a client capped at `max_usd` of total Run spend, and log this attempt.

    Raises `CapExceededError` before any call when earlier attempts already spent the cap, so
    the fix is a higher `--max-usd`.
    """
    prior = run_dir.read(COST) if run_dir.exists(COST) else Cost()
    before = prior.spent_usd
    if before >= max_usd:
        msg = (
            f"earlier attempts spent ${before:.2f}, which reaches the ${max_usd:.2f} cap; "
            "raise it with --max-usd"
        )
        raise CapExceededError(msg)

    def persist(spent_usd: float) -> None:
        attempt = CostAttempt(max_usd, spent_usd - before)
        run_dir.write(COST, Cost((*prior.attempts, attempt)))

    persist(before)  # the cap is logged even if no call is made
    return LLMClient(
        transport,
        max_usd=max_usd,
        spent_usd=before,
        on_response=on_response,
        log=lambda record: persist(float(str(record["spent_usd"]))),
    )
