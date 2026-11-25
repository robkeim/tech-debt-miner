from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner import cli
from tech_debt_miner.run.artifacts import RANKING, REQUESTS, SNAPSHOT
from tech_debt_miner.run.rank import rank
from tech_debt_miner.run.run_dir import RunDir, RunState
from tech_debt_miner.types import FileFacts, Manifest, Ranking, Snapshot

pytestmark = pytest.mark.unit

MANIFEST = Manifest(
    target_repo="owner/repo",
    pinned_sha="a" * 40,
    cutoff_date="2025-01-31",
    model="model-1",
    model_training_cutoff="2024-06-01",
    cutoff_minus_training_days=244,
    repeats=2,
    prompt_hashes={},
    lizard_version="1.17",
    adr_shas={},
    tool_sha="c" * 40,
)
SNAPSHOT_VALUE = Snapshot(
    files=(
        FileFacts("low.py", loc=5, churn=1, complexity=1.0),
        FileFacts("hot.py", loc=50, churn=9, complexity=20.0),
        FileFacts("mid.py", loc=20, churn=4, complexity=5.0),
    ),
    issues=(),
    zero_complexity_files=0,
)


def new_run(tmp_path: Path) -> RunDir:
    return RunDir.create(tmp_path, MANIFEST, lambda: datetime(2026, 1, 1, tzinfo=UTC))


def test_rank_writes_only_the_baseline_ranking(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path)
    run_dir.write(SNAPSHOT, SNAPSHOT_VALUE)

    rank(run_dir)

    assert run_dir.read(RANKING, ("baseline", 0)) == Ranking(
        "baseline", 0, (("hot.py",), ("mid.py",), ("low.py",))
    )
    assert sorted(p.name for p in (run_dir.path / "rankings").iterdir()) == ["baseline.json"]
    assert not run_dir.exists(REQUESTS)


def test_the_run_still_needs_the_llm_rankings_after_rank(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path)
    run_dir.write(SNAPSHOT, SNAPSHOT_VALUE)

    rank(run_dir)

    assert run_dir.missing_rankings() == [("llm", 0), ("llm", 1)]
    assert run_dir.state() is RunState.RESOLVED


def test_rank_twice_gives_the_same_file(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path)
    run_dir.write(SNAPSHOT, SNAPSHOT_VALUE)
    rank(run_dir)
    first = (run_dir.path / "rankings" / "baseline.json").read_bytes()

    rank(run_dir)

    assert (run_dir.path / "rankings" / "baseline.json").read_bytes() == first


def test_cli_rank_writes_the_baseline(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path)
    run_dir.write(SNAPSHOT, SNAPSHOT_VALUE)

    assert cli.main(["rank", run_dir.id, "--runs-dir", str(tmp_path)]) == 0
    assert run_dir.exists(RANKING, ("baseline", 0))


def test_cli_rank_without_a_snapshot_fails_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = new_run(tmp_path)

    assert cli.main(["rank", run_dir.id, "--runs-dir", str(tmp_path)]) == 2
    assert "snapshot" in capsys.readouterr().err
    assert not run_dir.exists(RANKING, ("baseline", 0))


def test_cli_rank_of_an_unknown_run_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["rank", "nope", "--runs-dir", str(tmp_path)]) == 2
    assert "no such Run" in capsys.readouterr().err


def test_rank_persists_a_tie_group_and_reads_it_back(tmp_path: Path) -> None:
    run_dir = new_run(tmp_path)
    tied = Snapshot(
        files=(
            FileFacts("z.py", loc=5, churn=1, complexity=2.0),
            FileFacts("a.py", loc=5, churn=2, complexity=1.0),
            FileFacts("top.py", loc=5, churn=3, complexity=3.0),
        ),
        issues=(),
        zero_complexity_files=0,
    )
    run_dir.write(SNAPSHOT, tied)

    rank(run_dir)

    assert run_dir.read(RANKING, ("baseline", 0)).groups == (("top.py",), ("a.py", "z.py"))
