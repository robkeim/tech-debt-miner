"""Each scored Run's Manifest records the commit SHA of every pre-registration ADR (ADR 0005)."""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from tech_debt_miner.run.artifacts import MANIFEST as MANIFEST_ARTIFACT
from tech_debt_miner.run.resolve import ADR_FILES
from tech_debt_miner.run.run_dir import RunDir, RunState
from tech_debt_miner.types import Manifest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"
# ADR 0005 is the pre-registration; ADR 0012 amends it (#62).
REQUIRED_ADR_IDS = ("0005", "0012")
SHA = re.compile(r"^[0-9a-f]{40}$")

MANIFEST = Manifest(
    target_repo="owner/repo",
    pinned_sha="a" * 40,
    cutoff_date="2025-01-31",
    model="m",
    model_training_cutoff="2024-06-01",
    cutoff_minus_training_days=244,
    repeats=3,
    prompt_hashes={},
    lizard_version="1",
    adr_shas={"0005": "b" * 40, "0012": "c" * 40},
    tool_sha="d" * 40,
)


def violations(manifest: Manifest) -> list[str]:
    """Pre-registration ADRs whose commit SHA the Manifest lacks or records malformed."""
    return [
        f"adr_shas lacks a commit SHA for ADR {adr}"
        for adr in REQUIRED_ADR_IDS
        if not SHA.match(manifest.adr_shas.get(adr, ""))
    ]


def scored_runs() -> list[RunDir]:
    """Every Run under `runs/` that reached the scored state. Dry-runs never do."""
    if not RUNS_DIR.is_dir():
        return []
    runs = (
        RunDir.open(RUNS_DIR, path.name) for path in sorted(RUNS_DIR.iterdir()) if path.is_dir()
    )
    return [run for run in runs if run.state() is RunState.SCORED]


def test_scored_runs_record_the_pre_registration_shas() -> None:
    problems = {
        run.id: found for run in scored_runs() if (found := violations(run.read(MANIFEST_ARTIFACT)))
    }
    assert not problems, f"scored Runs missing pre-registration SHAs: {problems}"


def test_complete_manifest_passes() -> None:
    assert violations(MANIFEST) == []


@pytest.mark.parametrize("adr", REQUIRED_ADR_IDS)
def test_manifest_missing_a_required_adr_fails(adr: str) -> None:
    shas = {k: v for k, v in MANIFEST.adr_shas.items() if k != adr}
    assert violations(replace(MANIFEST, adr_shas=shas)) == [
        f"adr_shas lacks a commit SHA for ADR {adr}"
    ]


def test_manifest_with_a_malformed_sha_fails() -> None:
    assert violations(replace(MANIFEST, adr_shas={"0005": "", "0012": "xyz"})) != []


def test_empty_adr_shas_fails_both() -> None:
    assert len(violations(replace(MANIFEST, adr_shas={}))) == 2


def test_resolve_records_every_required_adr() -> None:
    """`runs/` is gitignored, so CI checks the writer: `resolve` records each required ADR."""
    assert set(REQUIRED_ADR_IDS) <= set(ADR_FILES)
