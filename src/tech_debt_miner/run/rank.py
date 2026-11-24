"""The `rank` stage. For now it writes only `rankings/baseline.json` and never calls the LLM."""

from tech_debt_miner.rankers.baseline import BASELINE, BaselineRanker
from tech_debt_miner.run.artifacts import RANKING, SNAPSHOT
from tech_debt_miner.run.run_dir import RunDir


def rank(run_dir: RunDir) -> None:
    """Rank the Snapshot with the Baseline and write `rankings/baseline.json`."""
    ranking = BaselineRanker().rank(run_dir.read(SNAPSHOT), repeat=0)
    run_dir.write(RANKING, ranking, (BASELINE, 0))
