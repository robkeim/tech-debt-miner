"""The `snapshot` stage: eligible files with LOC, churn and complexity as of the Cutoff date."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tech_debt_miner.repo import git
from tech_debt_miner.repo.churn import count_churn, window_start
from tech_debt_miner.repo.complexity import file_complexity
from tech_debt_miner.repo.eligibility import eligible_paths, physical_loc
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
    with git.export_tree(repo, manifest.pinned_sha) as tree:
        files = (f for f in tree.rglob("*") if f.is_file() and not f.is_symlink())
        by_path = {f.relative_to(tree).as_posix(): f for f in files}
        paths = eligible_paths(by_path)
        contents = {path: by_path[path].read_bytes() for path in paths}
    churn = count_churn(git.list_commits(repo, window_start(cutoff), cutoff), paths)
    facts: list[FileFacts] = []
    zero = 0
    for path in paths:
        complexity = file_complexity(path, contents[path])
        zero += complexity.zero
        facts.append(FileFacts(path, physical_loc(contents[path]), churn[path], complexity.value))
    run_dir.write_snapshot(Snapshot(files=tuple(facts), issues=(), zero_complexity_files=zero))
