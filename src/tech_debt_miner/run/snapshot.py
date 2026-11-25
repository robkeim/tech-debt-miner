"""The `snapshot` stage: eligible files with everything the rankers read, as of the Cutoff date."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tech_debt_miner.repo import git
from tech_debt_miner.repo.churn import commits_by_file, recent_subjects, window_start
from tech_debt_miner.repo.complexity import file_complexity
from tech_debt_miner.repo.eligibility import physical_loc
from tech_debt_miner.repo.git import CommitChange
from tech_debt_miner.repo.source import file_head, file_outline
from tech_debt_miner.repo.tree import read_eligible_files
from tech_debt_miner.run.artifacts import MANIFEST, SNAPSHOT
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import FileFacts, Snapshot


@dataclass(frozen=True)
class SnapshotDeps:
    """Injected collaborators."""

    repos_dir: Path  # a Target repo is read from `<repos_dir>/<name>`


def snapshot(run_dir: RunDir, deps: SnapshotDeps) -> None:
    """Write `snapshot.json`. The only stage that reads the Target repo.

    Files and complexity come from a `git archive` of the Pinned SHA, exported to a temporary
    directory that is deleted afterward. Churn and commit subjects come from non-merge commits
    in the Churn window before the Cutoff date. Each file also carries the head, outline and
    subjects the LLM prompts show (ADR 0010), so `rank` needs nothing else. Issues are not
    collected yet.
    """
    manifest = run_dir.read(MANIFEST)
    repo = deps.repos_dir / manifest.target_repo.rsplit("/", 1)[-1]
    cutoff = date.fromisoformat(manifest.cutoff_date)
    contents = read_eligible_files(repo, manifest.pinned_sha)
    paths = list(contents)
    history = commits_by_file(
        git.list_commits(repo, window_start(cutoff), cutoff, manifest.pinned_sha), paths
    )
    facts = tuple(_facts(path, contents[path], history[path]) for path in paths)
    zero = sum(1 for fact in facts if fact.complexity == 0)
    run_dir.write(SNAPSHOT, Snapshot(files=facts, issues=(), zero_complexity_files=zero))


def _facts(path: str, content: bytes, commits: Sequence[CommitChange]) -> FileFacts:
    head, truncated_lines = file_head(content)
    return FileFacts(
        path=path,
        loc=physical_loc(content),
        churn=len(commits),
        complexity=file_complexity(path, content),
        outline=file_outline(content),
        head=head,
        truncated_lines=truncated_lines,
        recent_commits=recent_subjects(commits),
    )
