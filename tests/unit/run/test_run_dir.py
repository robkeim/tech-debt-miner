from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tech_debt_miner.run.artifacts import (
    ALL,
    LABELS,
    RANKING,
    REQUESTS,
    SCORES,
    SNAPSHOT,
    Artifact,
    Policy,
)
from tech_debt_miner.run.artifacts import (
    MANIFEST as MANIFEST_FILE,
)
from tech_debt_miner.run.run_dir import RunDir, RunState, Stage, run_id
from tech_debt_miner.types import (
    FileFacts,
    Issue,
    Labels,
    Manifest,
    Ranking,
    Request,
    Scores,
    Snapshot,
)

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
    assert run.read(MANIFEST_FILE) == MANIFEST


def test_create_refuses_an_existing_run(tmp_path: Path) -> None:
    make_run(tmp_path)
    with pytest.raises(FileExistsError):
        make_run(tmp_path)


def test_keyed_artifact_paths() -> None:
    assert RANKING.path(("baseline", 0)) == "rankings/baseline.json"
    assert RANKING.path(("llm", 2)) == "rankings/llm-2.json"
    assert SCORES.path("2027-01-31") == "scores-2027-01-31.json"


# One sample value and key per artifact; the table test fails if one is missing.
SAMPLES: dict[str, tuple[Any, Any]] = {
    "manifest": (MANIFEST, None),
    "snapshot": (
        Snapshot(
            files=(FileFacts(path="a.py", loc=10, churn=3, complexity=2.5),),
            issues=(Issue(number=1, title="t", body="b"),),
        ),
        None,
    ),
    "requests": (Request("llm", 0, 0, "m", "s", "p", 10), None),
    "responses": ({"text": "hi"}, None),
    "cost": ({"usd": 1.5}, None),
    "labels": (Labels({"a.py": 1}), None),
    "ranking": (Ranking("llm", 1, ("a.py",)), ("llm", 1)),
    "scores": (Scores({"m": 0.1}), "2027-01-31"),
}


def test_every_artifact_has_a_sample() -> None:
    assert {artifact.name for artifact in ALL} == set(SAMPLES)


@pytest.mark.parametrize("artifact", ALL, ids=lambda artifact: artifact.name)
def test_artifacts_round_trip(tmp_path: Path, artifact: Artifact[Any, Any]) -> None:
    run = RunDir(tmp_path / "run")
    value, key = SAMPLES[artifact.name]
    if artifact.policy is Policy.APPEND:
        run.append(artifact, value)
        assert run.read_all(artifact) == [value]
    else:
        run.write(artifact, value, key)
        assert run.read(artifact, key) == value
    assert run.exists(artifact, key)


@pytest.mark.parametrize("artifact", [a for a in ALL if a.policy is Policy.CREATE_ONCE])
def test_create_once_artifacts_are_never_overwritten(
    tmp_path: Path, artifact: Artifact[Any, Any]
) -> None:
    run = RunDir(tmp_path / "run")
    value, key = SAMPLES[artifact.name]
    run.write(artifact, value, key)
    with pytest.raises(FileExistsError):
        run.write(artifact, value, key)


def test_ranking_key_is_derived_from_the_value(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(RANKING, Ranking("llm", 2, ("a.py",)))
    assert (run.path / "rankings" / "llm-2.json").exists()


def test_policy_mismatches_are_rejected(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with pytest.raises(TypeError, match="cannot append to snapshot"):
        run.append(SNAPSHOT, SAMPLES["snapshot"][0])
    with pytest.raises(TypeError, match="cannot write requests"):
        run.write(REQUESTS, SAMPLES["requests"][0])
    with pytest.raises(TypeError, match="cannot be enumerated"):
        run.keys(SNAPSHOT)
    with pytest.raises(TypeError, match="cannot read requests"):
        run.read(REQUESTS)
    with pytest.raises(TypeError, match="cannot read all rows of snapshot"):
        run.read_all(SNAPSHOT)


def test_a_keyed_artifact_needs_its_key(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with pytest.raises(TypeError, match="scores needs a key"):
        run.write(SCORES, Scores({}))
    with pytest.raises(TypeError, match="scores needs a key"):
        run.read(SCORES)
    assert not list(run.path.glob("scores-*"))


def test_scores_are_listed_by_date(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(SCORES, Scores({"m": 0.1}), "2027-03-01")
    run.write(SCORES, Scores({"m": 0.1}), "2027-01-31")
    assert run.keys(SCORES) == ["2027-01-31", "2027-03-01"]


def test_stage_done_means_final_artifact_exists(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.is_done(Stage.RESOLVE)
    assert not run.is_done(Stage.SNAPSHOT)
    run.write(SNAPSHOT, Snapshot(files=(), issues=()))
    assert run.is_done(Stage.SNAPSHOT)
    assert not run.is_done(Stage.LABEL)
    assert not run.is_done(Stage.SCORE)


def test_rank_is_done_only_when_every_ranking_exists(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(RANKING, Ranking("baseline", 0, ()))
    run.write(RANKING, Ranking("llm", 0, ()))
    assert not run.is_done(Stage.RANK)
    assert run.exists(RANKING, ("llm", 0))
    assert not run.exists(RANKING, ("llm", 1))
    run.write(RANKING, Ranking("llm", 1, ()))
    assert run.is_done(Stage.RANK)


def test_state_is_derived_from_artifacts(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.state() is None
    run.write(SNAPSHOT, Snapshot(files=(), issues=()))
    assert run.state() is None
    run.append(REQUESTS, Request("llm", 0, 0, "m", "s", "p", 10))
    assert run.state() is RunState.PLANNED
    for ranking in (Ranking("baseline", 0, ()), Ranking("llm", 0, ()), Ranking("llm", 1, ())):
        run.write(RANKING, ranking)
    assert run.state() is RunState.RANKED
    run.write(LABELS, Labels({}))
    assert run.state() is RunState.RANKED
    run.write(SCORES, Scores({}), "2027-01-31")
    assert run.state() is RunState.SCORED
