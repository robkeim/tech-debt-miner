"""The `resolve` stage: pin the SHA at the Cutoff date and create the Run directory."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from tech_debt_miner.rankers.prompts import (
    DIGEST_MAX_SUBJECTS,
    TRIAGE_SET_SIZE,
    template_hashes,
)
from tech_debt_miner.repo import git
from tech_debt_miner.repo.source import HEAD_LINES
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest

ADR_FILES = {
    "0005": "docs/adr/0005-scoring-pre-registration.md",
    "0007": "docs/adr/0007-heuristic-baseline-definition.md",
    "0012": "docs/adr/0012-llm-repeats-use-default-sampling.md",
}


@dataclass(frozen=True)
class ResolveInputs:
    """The experiment inputs, all explicit arguments (ADR 0009)."""

    repo: str  # "owner/name"
    cutoff: date
    model: str
    training_cutoff: date  # K
    repeats: int


@dataclass(frozen=True)
class ResolveDeps:
    """Injected collaborators."""

    repos_dir: Path  # a Target repo is cloned to `<repos_dir>/<name>`
    runs_dir: Path
    tool_root: Path  # the tool's own git checkout
    lizard_version: str
    clock: Callable[[], datetime]


def clone_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def prompt_hashes() -> dict[str, str]:
    """Return the template hashes and the digest and truncation parameters (ADR 0010)."""
    return {
        **template_hashes(),
        "digest_max_subjects": str(DIGEST_MAX_SUBJECTS),
        "head_lines": str(HEAD_LINES),
        "triage_set_size": str(TRIAGE_SET_SIZE),
    }


def resolve(inputs: ResolveInputs, deps: ResolveDeps) -> RunDir:
    """Clone the Target repo if needed, pin the SHA, and write `manifest.json` once."""
    if inputs.repeats < 1:
        msg = "repeats must be at least 1"
        raise ValueError(msg)
    clone = git.clone_repo(clone_url(inputs.repo), deps.repos_dir / inputs.repo.rsplit("/", 1)[-1])
    manifest = Manifest(
        target_repo=inputs.repo,
        pinned_sha=git.resolve_pinned_sha(clone, inputs.cutoff),
        cutoff_date=inputs.cutoff.isoformat(),
        model=inputs.model,
        model_training_cutoff=inputs.training_cutoff.isoformat(),
        cutoff_minus_training_days=(inputs.cutoff - inputs.training_cutoff).days,
        repeats=inputs.repeats,
        prompt_hashes=prompt_hashes(),
        lizard_version=deps.lizard_version,
        adr_shas={
            adr: git.last_commit_touching(deps.tool_root, path) for adr, path in ADR_FILES.items()
        },
        tool_sha=git.head_sha(deps.tool_root),
    )
    return RunDir.create(deps.runs_dir, manifest, deps.clock)
