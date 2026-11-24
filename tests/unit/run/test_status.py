from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner import cli
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest, Request, Snapshot

pytestmark = pytest.mark.unit

MANIFEST = Manifest(
    target_repo="owner/repo",
    pinned_sha="a" * 40,
    cutoff_date="2025-01-31",
    model="model-1",
    model_training_cutoff="2024-06-01",
    cutoff_minus_training_days=244,
    repeats=1,
    prompt_hashes={},
    lizard_version="1.17",
    adr_shas={},
    tool_sha="c" * 40,
)


def status(runs_dir: Path, run_id: str) -> int:
    return cli.main(["status", run_id, "--runs-dir", str(runs_dir)])


def test_status_of_a_resolved_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = RunDir.create(tmp_path, MANIFEST, lambda: datetime(2026, 1, 1, tzinfo=UTC))

    assert status(tmp_path, run_dir.id) == 0
    assert capsys.readouterr().out.strip() == "resolved"


def test_status_of_a_planned_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = RunDir.create(tmp_path, MANIFEST, lambda: datetime(2026, 1, 1, tzinfo=UTC))
    run_dir.write_snapshot(Snapshot(files=(), issues=()))
    run_dir.append_request(Request("llm", 0, 0, "m", "s", "p", 10))

    assert status(tmp_path, run_dir.id) == 0
    assert capsys.readouterr().out.strip() == "planned"


def test_status_of_an_unknown_run_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert status(tmp_path, "nope") == 2
    assert "no such Run" in capsys.readouterr().err
