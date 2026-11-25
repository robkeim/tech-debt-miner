"""The ordered stage list and `resume` (ADR 0008, ADR 0009).

Stages are plain functions over `(run_dir, deps)`. `resume` runs the stages that are not done
and skips the rest. A stage is done when its final artifact exists, and artifacts are written
by rename, so a crashed stage leaves nothing for the next `resume` to trust.
"""

from collections.abc import Callable
from dataclasses import dataclass

from tech_debt_miner.run.label import ClosedBugs, LabelDeps, label
from tech_debt_miner.run.plan import PlanDeps, plan
from tech_debt_miner.run.rank import rank
from tech_debt_miner.run.run_dir import RunDir, Stage
from tech_debt_miner.run.score import ScoreDeps, score
from tech_debt_miner.run.snapshot import SnapshotDeps, snapshot


@dataclass(frozen=True)
class StageDeps:
    """Injected collaborators for every stage `resume` can run."""

    snapshot: SnapshotDeps
    plan: PlanDeps
    label: LabelDeps
    closed_bugs: ClosedBugs
    score: ScoreDeps


# `resolve` is not here: it creates the Run directory, so a Run being resumed already has it.
STAGES: tuple[tuple[Stage, Callable[[RunDir, StageDeps], object]], ...] = (
    (Stage.SNAPSHOT, lambda run_dir, deps: snapshot(run_dir, deps.snapshot)),
    (Stage.PLAN, lambda run_dir, deps: plan(run_dir, deps.plan)),
    (Stage.RANK, lambda run_dir, _deps: rank(run_dir)),
    (Stage.LABEL, lambda run_dir, deps: label(run_dir, deps.label, deps.closed_bugs)),
    (Stage.SCORE, lambda run_dir, deps: score(run_dir, deps.score)),
)

PLAN_STAGES = frozenset({Stage.SNAPSHOT, Stage.PLAN})  # a Dry-run: snapshot, plan, stop


def resume(run_dir: RunDir, deps: StageDeps, *, run: bool) -> list[Stage]:
    """Run every stage that is not done and return the ones that ran, in order.

    Without `run` it stops after the planning stages, which makes the Run a Dry-run. With `run`
    it continues the same directory through the rest. A stage that raises stops the resume
    there; the stages before it stay done.
    """
    ran: list[Stage] = []
    for stage, function in STAGES:
        if not run and stage not in PLAN_STAGES:
            break
        if not run_dir.is_done(stage):
            function(run_dir, deps)
            ran.append(stage)
    return ran
