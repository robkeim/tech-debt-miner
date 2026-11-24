from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tech_debt_miner.run.run_dir import RunDir, RunNotFoundError, RunState, Stage, run_id
from tech_debt_miner.types import Labels, Manifest, Ranking, Request, Scores, Snapshot

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 24, 8, 30, 15, tzinfo=UTC)

MANIFEST = Manifest(
    target_repo="owner/repo",
    pinned_sha="a" * 40,
    cutoff_date="2025-01-31",
    model="model-1",
    model_training_cutoff="2024-06-01",
    cutoff_minus_training_days=244,
    repeats=2,
    prompt_hashes={"triage": "h1", "rank": "h2"},
    lizard_version="1.17",
    adr_shas={"0005": "b" * 40},
    tool_sha="c" * 40,
)


def make_run(tmp_path: Path) -> RunDir:
    return RunDir.create(tmp_path, MANIFEST, lambda: NOW)


def test_run_id_has_timestamp_and_manifest_hash() -> None:
    assert run_id(MANIFEST, NOW).startswith("20261124T083015Z-")
    assert len(run_id(MANIFEST, NOW)) == len("20261124T083015Z-") + 8


def test_run_id_hash_depends_on_manifest_not_key_order() -> None:
    reordered = replace(MANIFEST, prompt_hashes={"rank": "h2", "triage": "h1"})
    assert run_id(reordered, NOW) == run_id(MANIFEST, NOW)
    assert run_id(replace(MANIFEST, model="other"), NOW) != run_id(MANIFEST, NOW)


def test_run_id_rejects_a_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        run_id(MANIFEST, datetime(2026, 11, 24, 8, 30, 15))  # noqa: DTZ001 - the point of the test


def test_run_id_uses_utc() -> None:
    local = datetime(2026, 11, 24, 3, 30, 15, tzinfo=UTC).astimezone()
    assert run_id(MANIFEST, local) == run_id(MANIFEST, NOW).replace("083015", "033015")


def test_create_writes_manifest_that_reads_back(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.path == tmp_path / run_id(MANIFEST, NOW)
    assert run.read_manifest() == MANIFEST


def test_create_refuses_an_existing_run(tmp_path: Path) -> None:
    make_run(tmp_path)
    with pytest.raises(FileExistsError):
        make_run(tmp_path)


def test_open_finds_an_existing_run(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert RunDir.open(tmp_path, run.id).path == run.path


def test_open_refuses_a_directory_without_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "stray").mkdir()
    with pytest.raises(RunNotFoundError, match="no such Run: stray"):
        RunDir.open(tmp_path, "stray")
    with pytest.raises(RunNotFoundError, match="no such Run: nope"):
        RunDir.open(tmp_path, "nope")


def test_artifacts_round_trip(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    snapshot = Snapshot(files=(), issues=())
    request = Request("llm", 0, 0, "m", "s", "p", 10)
    ranking = Ranking("llm", 1, ("a.py",))
    run.write_snapshot(snapshot)
    run.append_request(request)
    run.append_response({"text": "hi"})
    run.write_ranking(ranking)
    run.write_cost({"usd": 1.5})
    run.write_labels(Labels({"a.py": 1}))
    run.write_scores("2027-01-31", Scores({"m": 0.1}))
    assert run.read_snapshot() == snapshot
    assert run.read_requests() == [request]
    assert run.read_responses() == [{"text": "hi"}]
    assert run.read_ranking("llm", 1) == ranking
    assert run.read_cost() == {"usd": 1.5}
    assert run.read_labels() == Labels({"a.py": 1})
    assert run.read_scores("2027-01-31") == Scores({"m": 0.1})


def test_scores_are_never_overwritten(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write_scores("2027-01-31", Scores({"m": 0.1}))
    with pytest.raises(FileExistsError):
        run.write_scores("2027-01-31", Scores({"m": 0.2}))
    run.write_scores("2027-03-01", Scores({"m": 0.3}))
    assert run.scoring_dates() == ["2027-01-31", "2027-03-01"]


REQUEST = Request("llm", 0, 0, "m", "s", "p", 10)
SNAPSHOT = Snapshot(files=(), issues=())


def test_a_fresh_run_is_resolved_and_needs_a_snapshot(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.state() is RunState.RESOLVED
    assert run.next_stage() is Stage.SNAPSHOT


def test_a_snapshot_without_requests_is_still_resolved(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write_snapshot(SNAPSHOT)
    assert run.state() is RunState.RESOLVED
    assert run.next_stage() is Stage.RANK


def test_a_planned_run_resumes_at_rank(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write_snapshot(SNAPSHOT)
    run.append_request(REQUEST)
    assert run.state() is RunState.PLANNED
    assert run.next_stage() is Stage.RANK


def test_rank_resumes_per_ranking(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write_snapshot(SNAPSHOT)
    run.append_request(REQUEST)
    assert run.missing_rankings() == [("baseline", 0), ("llm", 0), ("llm", 1)]
    run.write_ranking(Ranking("baseline", 0, ()))
    run.write_ranking(Ranking("llm", 0, ()))
    assert run.missing_rankings() == [("llm", 1)]
    assert run.state() is RunState.PLANNED
    assert run.next_stage() is Stage.RANK
    run.write_ranking(Ranking("llm", 1, ()))
    assert run.missing_rankings() == []


def test_a_ranked_run_resumes_at_label_then_score(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write_snapshot(SNAPSHOT)
    run.append_request(REQUEST)
    for ranking in (Ranking("baseline", 0, ()), Ranking("llm", 0, ()), Ranking("llm", 1, ())):
        run.write_ranking(ranking)
    assert run.state() is RunState.RANKED
    assert run.next_stage() is Stage.LABEL
    run.write_labels(Labels({}))
    assert run.state() is RunState.RANKED
    assert run.next_stage() is Stage.SCORE
    run.write_scores("2027-01-31", Scores({}))
    assert run.state() is RunState.SCORED
    assert run.next_stage() is None
