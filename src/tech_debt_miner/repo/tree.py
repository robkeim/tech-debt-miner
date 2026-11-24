"""The eligible files of a Target repo at one commit, read through `git archive` (ADR 0009)."""

from pathlib import Path

from tech_debt_miner.repo import git
from tech_debt_miner.repo.eligibility import eligible_paths


def read_eligible_files(repo: Path, sha: str) -> dict[str, bytes]:
    """Return path -> content for the eligible files at `sha`, sorted by path.

    The tree is exported to a temporary directory that is deleted before this returns.
    Symlinks are skipped.
    """
    with git.export_tree(repo, sha) as tree:
        files = (f for f in tree.rglob("*") if f.is_file() and not f.is_symlink())
        by_path = {f.relative_to(tree).as_posix(): f for f in files}
        return {path: by_path[path].read_bytes() for path in eligible_paths(by_path)}
