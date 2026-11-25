"""The `report` command's loader: read every Run under a directory into `RunScorings` (ADR 0008)."""

from pathlib import Path

from tech_debt_miner.report import RunScorings
from tech_debt_miner.run.artifacts import MANIFEST, SCORES
from tech_debt_miner.run.run_dir import RunDir


def load_runs(runs_dir: Path) -> list[RunScorings]:
    """Return every Run directory with a manifest, with all of its scorings. Others are ignored."""
    if not runs_dir.is_dir():
        return []
    runs: list[RunScorings] = []
    for path in sorted(runs_dir.iterdir()):
        run_dir = RunDir(path)
        if not (path.is_dir() and run_dir.exists(MANIFEST)):
            continue
        manifest = run_dir.read(MANIFEST)
        runs.append(
            RunScorings(
                run_id=run_dir.id,
                repo=manifest.target_repo,
                cutoff_date=manifest.cutoff_date,
                post_training=manifest.cutoff_minus_training_days > 0,
                scorings={key: run_dir.read(SCORES, key) for key in run_dir.keys(SCORES)},
            )
        )
    return runs
