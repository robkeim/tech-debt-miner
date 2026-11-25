from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner import cli, report
from tech_debt_miner.run.artifacts import SCORES
from tech_debt_miner.run.report import load_runs
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest, RunScores, Scores

pytestmark = pytest.mark.unit


def manifest(repo: str, cutoff: str = "2026-07-01", days: int = 1) -> Manifest:
    return Manifest(
        target_repo=repo,
        pinned_sha="a" * 40,
        cutoff_date=cutoff,
        model="m",
        model_training_cutoff="2026-06-30",
        cutoff_minus_training_days=days,
        repeats=1,
        prompt_hashes={},
        lizard_version="1",
        adr_shas={},
        tool_sha="c" * 40,
    )


def scored(ndcg: float) -> RunScores:
    metrics = {report.NDCG_METRIC: ndcg, report.RECALL_METRIC: ndcg}
    return RunScores(12, 10, "", {"baseline": Scores(metrics), "llm-0": Scores(metrics)})


def make(root: Path, repo: str, days: int = 1, *, with_scores: bool = True) -> RunDir:
    run = RunDir.create(root, manifest(repo, days=days), lambda: datetime(2027, 1, 1, tzinfo=UTC))
    if with_scores:
        run.write(SCORES, scored(0.5), "2027-02-01")
    return run


def test_load_runs_reads_manifest_and_scorings(tmp_path: Path) -> None:
    make(tmp_path, "o/a")
    make(tmp_path, "o/b", days=-30, with_scores=False)
    (tmp_path / "stray").mkdir()
    (tmp_path / "note.txt").write_text("x")
    loaded = {r.repo: r for r in load_runs(tmp_path)}
    assert set(loaded) == {"o/a", "o/b"}
    assert loaded["o/a"].post_training
    assert not loaded["o/b"].post_training
    assert set(loaded["o/a"].scorings) == {"2027-02-01"}
    assert loaded["o/b"].scorings == {}


def test_load_runs_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert load_runs(tmp_path / "nope") == []


def test_report_command_prints_and_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs"
    for i in range(5):
        make(runs, f"o/r{i}")
    out = tmp_path / "report.md"
    code = cli.main(
        ["report", "--treatment", "baseline", "--runs-dir", str(runs), "--out", str(out)]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "**Outcome: Null**" in printed
    assert out.read_text() == printed


def test_report_command_fails_on_duplicate_windows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs"
    make(runs, "o/a")
    again = RunDir.create(runs, manifest("o/a"), lambda: datetime(2027, 1, 2, tzinfo=UTC))
    again.write(SCORES, scored(0.5), "2027-02-01")
    assert cli.main(["report", "--runs-dir", str(runs)]) == 1
    assert "both cover o/a" in capsys.readouterr().err
