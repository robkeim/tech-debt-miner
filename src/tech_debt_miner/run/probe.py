"""The `probe` stage: one canary call per Run, reported beside results (ADR 0006).

It sits outside the five stages of ADR 0008: it adds no state, and nothing waits on it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from tech_debt_miner import labels, probe
from tech_debt_miner.llm.client import LLMClient
from tech_debt_miner.repo import git
from tech_debt_miner.run.artifacts import MANIFEST, PROBE
from tech_debt_miner.run.label import WindowOpenError
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Probe


class NoProbeCommitError(RuntimeError):
    """The Label window holds no Fix commit the probe can use."""


@dataclass(frozen=True)
class ProbeDeps:
    """Injected collaborators."""

    repos_dir: Path
    client: LLMClient  # its log callback writes `responses.jsonl`; Dry-run injects a raiser
    today: date


def run_probe(run_dir: RunDir, deps: ProbeDeps) -> Probe:
    """Write `probe.json`: ask the model to name the file changed by one post-Cutoff Fix commit.

    The commit comes from the closed Label window of the clone as it is now, so run `label`
    first: it fast-forwards the clone. The call goes through the client, which logs it.
    """
    if run_dir.exists(PROBE):
        msg = f"{PROBE.path(None)} already exists; the probe runs once"
        raise FileExistsError(msg)
    manifest = run_dir.read(MANIFEST)
    cutoff = date.fromisoformat(manifest.cutoff_date)
    if not labels.window_is_closed(cutoff, deps.today):
        msg = f"the Label window closes after {labels.window_end(cutoff)}; today is {deps.today}"
        raise WindowOpenError(msg)
    clone = deps.repos_dir / manifest.target_repo.rsplit("/", 1)[-1]
    commits = git.list_commits(
        clone, labels.window_start(cutoff), labels.window_end(cutoff) + timedelta(days=1)
    )
    selected = probe.select_commit(commits)
    if selected is None:
        msg = "no Fix commit in the window changes exactly one eligible file; run `label` first"
        raise NoProbeCommitError(msg)
    commit, expected = selected
    request = probe.build_request(commit.message, manifest.model)
    response = deps.client.complete(request, probe.SCHEMA)
    result = probe.grade(commit.sha, expected, probe.parse_answer(response.text))
    run_dir.write(PROBE, result)
    return result
