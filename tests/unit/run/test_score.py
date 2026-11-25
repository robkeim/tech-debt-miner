from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner import cli, scoring
from tech_debt_miner.run.artifacts import LABELS, RANKING, SCORES, SNAPSHOT, ranking_name
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.run.score import LabelMissingError, NoRankingsError, ScoreDeps, score
from tech_debt_miner.types import FileFacts, Labels, Manifest, Ranking, Snapshot

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
PATHS = tuple(f"f{i:02}.py" for i in range(12))
SNAPSHOT_VALUE = Snapshot(
    files=tuple(
        FileFacts(
            path,
            loc=10,
            churn=1,
            complexity=1.0,
            outline=(),
            head="",
            truncated_lines=0,
            recent_commits=(),
        )
        for path in PATHS
    ),
    issues=(),
    zero_complexity_files=0,
)


def deps(day: int = 1) -> ScoreDeps:
    return ScoreDeps(clock=lambda: datetime(2027, 2, day, tzinfo=UTC))


def make_run(tmp_path: Path, labeled: int = 12, *, ranked: bool = True) -> RunDir:
    run = RunDir.create(tmp_path / "runs", MANIFEST, lambda: datetime(2025, 1, 31, tzinfo=UTC))
    run.write(SNAPSHOT, SNAPSHOT_VALUE)
    if ranked:
        groups = tuple((path,) for path in PATHS)
        run.write(RANKING, Ranking(ranker="baseline", repeat=0, groups=groups))
    counts = {path: (1 if i < labeled else 0) for i, path in enumerate(PATHS)}
    run.write(LABELS, Labels(counts=counts))
    return run


def test_score_writes_every_ranking_it_finds(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(RANKING, Ranking(ranker="llm", repeat=1, groups=(PATHS,)))

    result = score(run, deps())

    assert run.read(SCORES, "2027-02-01") == result
    assert sorted(result.rankings) == ["baseline", "llm-1"]
    assert result.rankings["baseline"].metrics["ndcg@20"] == pytest.approx(1.0)
    assert result.labeled_files == 12
    assert result.excluded == ""
    assert run.keys(SCORES) == ["2027-02-01"]


def test_a_run_below_the_minimum_is_written_as_excluded_not_dropped(tmp_path: Path) -> None:
    run = make_run(tmp_path, labeled=scoring.MIN_LABELED_FILES - 1)

    result = score(run, deps())

    assert result.rankings == {}
    assert result.labeled_files == scoring.MIN_LABELED_FILES - 1
    assert "fewer than the 10 required" in result.excluded
    assert run.read(SCORES, "2027-02-01") == result


def test_exactly_the_minimum_is_scored(tmp_path: Path) -> None:
    result = score(make_run(tmp_path, labeled=scoring.MIN_LABELED_FILES), deps())
    assert result.excluded == ""
    assert "baseline" in result.rankings


def test_score_refuses_before_label(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    (run.path / "labels.json").unlink()
    with pytest.raises(LabelMissingError, match="label"):
        score(run, deps())
    assert run.keys(SCORES) == []


def test_score_refuses_without_rankings(tmp_path: Path) -> None:
    with pytest.raises(NoRankingsError, match="rank"):
        score(make_run(tmp_path, ranked=False), deps())


def test_a_rescore_writes_a_new_file_and_never_overwrites(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    score(run, deps(1))
    first = (run.path / "scores-2027-02-01.json").read_bytes()

    with pytest.raises(FileExistsError, match="never overwritten"):
        score(run, deps(1))
    score(run, deps(2))

    assert (run.path / "scores-2027-02-01.json").read_bytes() == first
    assert run.keys(SCORES) == ["2027-02-01", "2027-02-02"]


def test_ranking_keys_round_trip_through_file_names(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(RANKING, Ranking(ranker="llm", repeat=0, groups=(PATHS,)))
    assert run.keys(RANKING) == [("baseline", 0), ("llm", 0)]
    assert ranking_name("llm", 2) == "llm-2"


def test_cli_score_writes_the_file_and_reports_exclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = make_run(tmp_path, labeled=3)

    assert cli.main(["score", run.id, "--runs-dir", str(tmp_path / "runs")]) == 0

    assert "excluded:" in capsys.readouterr().out
    assert len(run.keys(SCORES)) == 1


def test_cli_score_before_label_fails_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = make_run(tmp_path)
    (run.path / "labels.json").unlink()

    assert cli.main(["score", run.id, "--runs-dir", str(tmp_path / "runs")]) == 1

    assert "label" in capsys.readouterr().err
    assert run.keys(SCORES) == []


def test_cli_score_unknown_run_fails(tmp_path: Path) -> None:
    assert cli.main(["score", "nope", "--runs-dir", str(tmp_path)]) == 2


@pytest.mark.parametrize("name", ["llm.json", "llm-x.json", "my-ranker-1.json", "baseline-1.json"])
def test_a_stray_ranking_file_fails_loudly(tmp_path: Path, name: str) -> None:
    run = make_run(tmp_path)
    (run.path / "rankings" / name).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected ranking file"):
        run.keys(RANKING)
