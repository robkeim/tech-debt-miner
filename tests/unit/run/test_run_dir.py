from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tech_debt_miner.run import run_dir as run_dir_module
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
from tech_debt_miner.run.run_dir import RunDir, RunNotFoundError, RunState, Stage, run_id
from tech_debt_miner.types import (
    CapResult,
    CommitSubject,
    Cost,
    CostAttempt,
    FileFacts,
    Issue,
    Labels,
    LateLabels,
    LoggedResponse,
    Manifest,
    OutlineEntry,
    Probe,
    Ranking,
    Request,
    Response,
    ReviewItem,
    RunScores,
    Scores,
    Snapshot,
    Validation,
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
            files=(
                FileFacts(
                    path="a.py",
                    loc=10,
                    churn=3,
                    complexity=2.5,
                    outline=(OutlineEntry("class", "A", 1, 0),),
                    head="class A: ...",
                    truncated_lines=0,
                    recent_commits=(CommitSubject("2023-06-01", "s"),),
                ),
            ),
            issues=(Issue(number=1, title="t", body="b"),),
            zero_complexity_files=4,
            excluded_issues=2,
            issues_collected=True,
        ),
        None,
    ),
    "requests": (Request("llm", 0, 0, "m", "s", "p", 10), None),
    "responses": (
        LoggedResponse(
            "llm", 0, 0, cache_hit=False, response=Response("hi", 1, 2, "end_turn", "req", "m")
        ),
        None,
    ),
    "cost": (Cost((CostAttempt(4.0, 1.5), CostAttempt(6.0, 0.5))), None),
    "labels": (Labels({"a.py": 1}), None),
    "labels-12m": (
        LateLabels({"a.py": 2}, 3, "2027-07-01T00:00:00+00:00", "h" * 40, "d", fetched=True),
        None,
    ),
    "validation": (
        Validation(
            cap_n=3,
            fix_commits_sized=10,
            cap_report=(CapResult(3, 1, 4, 9), CapResult(None, 0, 5, 12)),
            sample_seed=7,
            sample=(ReviewItem("s" * 40, "fix a", ("#1",), ("a.py",), " a.py | 1 +"),),
            clone_head="h" * 40,
            fetched=True,
        ),
        None,
    ),
    "probe": (Probe("c" * 40, "a.py", "b.py", hit=False), None),
    "ranking": (Ranking("llm", 1, (("a.py",),)), ("llm", 1)),
    "scores": (RunScores(1, 10, "", {"baseline": Scores({"m": 0.1})}), "2027-01-31"),
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
    run.write(RANKING, Ranking("llm", 2, (("a.py",),)))
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
        run.write(SCORES, RunScores(0, 10, "x", {}))
    with pytest.raises(TypeError, match="scores needs a key"):
        run.read(SCORES)
    assert not list(run.path.glob("scores-*"))


def test_scores_are_listed_by_date(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(SCORES, RunScores(1, 10, "", {"baseline": Scores({"m": 0.1})}), "2027-03-01")
    run.write(SCORES, RunScores(1, 10, "", {"baseline": Scores({"m": 0.1})}), "2027-01-31")
    assert run.keys(SCORES) == ["2027-01-31", "2027-03-01"]


REQUEST = Request("llm", 0, 0, "m", "s", "p", 10)
SNAPSHOT_VALUE = Snapshot(files=(), issues=(), zero_complexity_files=0)


def test_open_finds_an_existing_run(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert RunDir.open(tmp_path, run.id).path == run.path


def test_open_refuses_a_directory_without_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "stray").mkdir()
    with pytest.raises(RunNotFoundError, match="no such Run: stray"):
        RunDir.open(tmp_path, "stray")
    with pytest.raises(RunNotFoundError, match="no such Run: nope"):
        RunDir.open(tmp_path, "nope")


def test_a_fresh_run_is_resolved_and_needs_a_snapshot(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.state() is RunState.RESOLVED
    assert run.next_stage() is Stage.SNAPSHOT


def test_a_snapshot_makes_the_run_planned_in_the_heuristic_loop(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(SNAPSHOT, SNAPSHOT_VALUE)
    assert run.state() is RunState.PLANNED
    assert run.next_stage() is Stage.RANK


def test_a_snapshot_without_requests_is_resolved_once_llm_ranking_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_dir_module, "LLM_RANKING", True)
    run = make_run(tmp_path)
    run.write(SNAPSHOT, SNAPSHOT_VALUE)
    assert run.state() is RunState.RESOLVED
    run.append(REQUESTS, REQUEST)
    assert run.state() is RunState.PLANNED


def test_rank_resumes_per_ranking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_dir_module, "LLM_RANKING", True)
    run = make_run(tmp_path)
    run.write(SNAPSHOT, SNAPSHOT_VALUE)
    run.append(REQUESTS, REQUEST)
    assert run.missing_rankings() == [("baseline", 0), ("llm", 0), ("llm", 1)]
    run.write(RANKING, Ranking("baseline", 0, ()))
    run.write(RANKING, Ranking("llm", 0, ()))
    assert run.missing_rankings() == [("llm", 1)]
    assert run.state() is RunState.PLANNED
    assert run.next_stage() is Stage.RANK
    run.write(RANKING, Ranking("llm", 1, ()))
    assert run.missing_rankings() == []


def test_a_ranked_run_resumes_at_label_then_score(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.write(SNAPSHOT, SNAPSHOT_VALUE)
    run.write(RANKING, Ranking("baseline", 0, ()))
    assert run.state() is RunState.RANKED
    assert run.next_stage() is Stage.LABEL
    run.write(LABELS, Labels({}))
    assert run.state() is RunState.RANKED
    assert run.next_stage() is Stage.SCORE
    run.write(SCORES, RunScores(0, 10, "x", {}), "2027-01-31")
    assert run.state() is RunState.SCORED
    assert run.next_stage() is None
