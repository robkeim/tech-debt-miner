"""The `snapshot` stage: eligible files with LOC, churn and complexity as of the Cutoff date."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tech_debt_miner.repo import git
from tech_debt_miner.repo.churn import count_churn, window_start
from tech_debt_miner.repo.complexity import file_complexity
from tech_debt_miner.repo.eligibility import physical_loc
from tech_debt_miner.repo.tree import read_eligible_files
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import FileFacts, Snapshot


@dataclass(frozen=True)
class SnapshotDeps:
    """Injected collaborators."""

    repos_dir: Path  # a Target repo is read from `<repos_dir>/<name>`


def snapshot(run_dir: RunDir, deps: SnapshotDeps) -> None:
    """Write `snapshot.json`. The only stage that reads the Target repo.

    Files and complexity come from a `git archive` of the Pinned SHA, exported to a temporary
    directory that is deleted afterward. Churn comes from non-merge commits before the Cutoff date.
    Issues are not collected yet.
    """
    manifest = run_dir.read_manifest()
    repo = deps.repos_dir / manifest.target_repo.rsplit("/", 1)[-1]
    cutoff = date.fromisoformat(manifest.cutoff_date)
    contents = read_eligible_files(repo, manifest.pinned_sha)
    paths = list(contents)
    churn = count_churn(git.list_commits(repo, window_start(cutoff), cutoff), paths)
    facts = tuple(
        FileFacts(
            path,
            physical_loc(contents[path]),
            churn[path],
            file_complexity(path, contents[path]),
        )
        for path in paths
    )
    zero = sum(1 for fact in facts if fact.complexity == 0)
    run_dir.write_snapshot(Snapshot(files=facts, issues=(), zero_complexity_files=zero))
