"""The Run directory: the only code that knows artifact names and paths."""

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from tech_debt_miner.run import store
from tech_debt_miner.types import Labels, Manifest, Ranking, Request, Scores, Snapshot

BASELINE = "baseline"
LLM = "llm"


class Stage(StrEnum):
    RESOLVE = "resolve"
    SNAPSHOT = "snapshot"
    RANK = "rank"
    LABEL = "label"
    SCORE = "score"


class RunState(StrEnum):
    RESOLVED = "resolved"
    PLANNED = "planned"
    RANKED = "ranked"
    SCORED = "scored"


class RunNotFoundError(LookupError):
    """No Run directory with a manifest exists for the id."""


def run_id(manifest: Manifest, now: datetime) -> str:
    """Return `<UTC-timestamp>-<8 hex of sha256 over the canonical manifest.json>`."""
    if now.tzinfo is None:
        msg = "the clock must return a timezone-aware datetime"
        raise ValueError(msg)
    digest = hashlib.sha256(_manifest_text(manifest).encode("utf-8")).hexdigest()[:8]
    return f"{now.astimezone(UTC):%Y%m%dT%H%M%SZ}-{digest}"


def _manifest_text(manifest: Manifest) -> str:
    return store.canonical_json(store.to_json(manifest))


class RunDir:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(
        cls,
        runs_root: Path,
        manifest: Manifest,
        clock: Callable[[], datetime],
    ) -> Self:
        """Create the directory for `manifest` and write `manifest.json` into it."""
        run_dir = cls(runs_root / run_id(manifest, clock()))
        run_dir.path.mkdir(parents=True)
        store.write_atomic(run_dir._manifest_path, _manifest_text(manifest))
        return run_dir

    @classmethod
    def open(cls, runs_root: Path, run_id: str) -> Self:
        """Return the existing Run `run_id`, or raise RunNotFoundError."""
        run_dir = cls(runs_root / run_id)
        if not run_dir._manifest_path.exists():
            msg = f"no such Run: {run_id}"
            raise RunNotFoundError(msg)
        return run_dir

    @property
    def id(self) -> str:
        return self.path.name

    # Artifact paths

    @property
    def _manifest_path(self) -> Path:
        return self.path / "manifest.json"

    @property
    def _snapshot_path(self) -> Path:
        return self.path / "snapshot.json"

    @property
    def _requests_path(self) -> Path:
        return self.path / "requests.jsonl"

    @property
    def _responses_path(self) -> Path:
        return self.path / "responses.jsonl"

    @property
    def _cost_path(self) -> Path:
        return self.path / "cost.json"

    @property
    def _labels_path(self) -> Path:
        return self.path / "labels.json"

    def _ranking_path(self, ranker: str, repeat: int) -> Path:
        name = ranker if ranker == BASELINE else f"{ranker}-{repeat}"
        return self.path / "rankings" / f"{name}.json"

    def _scores_path(self, scoring_date: str) -> Path:
        return self.path / f"scores-{scoring_date}.json"

    # Reads and writes

    def read_manifest(self) -> Manifest:
        return store.manifest_from_json(store.read_json(self._manifest_path))

    def write_snapshot(self, snapshot: Snapshot) -> None:
        store.write_json(self._snapshot_path, store.to_json(snapshot))

    def read_snapshot(self) -> Snapshot:
        return store.snapshot_from_json(store.read_json(self._snapshot_path))

    def append_request(self, request: Request) -> None:
        store.append_jsonl(self._requests_path, store.to_json(request))

    def read_requests(self) -> list[Request]:
        return [store.request_from_json(row) for row in store.read_jsonl(self._requests_path)]

    def append_response(self, record: Mapping[str, Any]) -> None:
        store.append_jsonl(self._responses_path, record)

    def read_responses(self) -> list[Any]:
        return store.read_jsonl(self._responses_path)

    def write_ranking(self, ranking: Ranking) -> None:
        path = self._ranking_path(ranking.ranker, ranking.repeat)
        store.write_json(path, store.to_json(ranking))

    def read_ranking(self, ranker: str, repeat: int) -> Ranking:
        return store.ranking_from_json(store.read_json(self._ranking_path(ranker, repeat)))

    def _has_ranking(self, ranker: str, repeat: int) -> bool:
        return self._ranking_path(ranker, repeat).exists()

    def write_cost(self, cost: Mapping[str, float]) -> None:
        store.write_json(self._cost_path, cost)

    def read_cost(self) -> dict[str, float]:
        return dict(store.read_json(self._cost_path))

    def write_labels(self, labels: Labels) -> None:
        store.write_json(self._labels_path, store.to_json(labels))

    def read_labels(self) -> Labels:
        return store.labels_from_json(store.read_json(self._labels_path))

    def write_scores(self, scoring_date: str, scores: Scores) -> None:
        """Write a new scores file. A re-score never overwrites an earlier one."""
        path = self._scores_path(scoring_date)
        if path.exists():
            msg = f"{path.name} already exists; scores are never overwritten"
            raise FileExistsError(msg)
        store.write_json(path, store.to_json(scores))

    def read_scores(self, scoring_date: str) -> Scores:
        return store.scores_from_json(store.read_json(self._scores_path(scoring_date)))

    def scoring_dates(self) -> list[str]:
        prefix, suffix = "scores-", ".json"
        return sorted(
            p.name.removeprefix(prefix).removesuffix(suffix)
            for p in self.path.glob(f"{prefix}*{suffix}")
        )

    # Stage and state

    def state(self) -> RunState:
        """Derive the Run's state from its artifacts. There is no marker file."""
        planned = self._is_done(Stage.SNAPSHOT) and self._requests_path.exists()
        if not planned:
            return RunState.RESOLVED
        if not self._is_done(Stage.RANK):
            return RunState.PLANNED
        if self._is_done(Stage.LABEL) and self._is_done(Stage.SCORE):
            return RunState.SCORED
        return RunState.RANKED

    def next_stage(self) -> Stage | None:
        """Return the first stage that is not done, or None when all are (ADR 0008)."""
        return next((stage for stage in Stage if not self._is_done(stage)), None)

    def missing_rankings(self) -> list[tuple[str, int]]:
        """Return the (ranker, repeat) pairs `rank` still has to produce."""
        repeats = self.read_manifest().repeats
        wanted = [(BASELINE, 0), *((LLM, repeat) for repeat in range(repeats))]
        return [pair for pair in wanted if not self._has_ranking(*pair)]

    def _is_done(self, stage: Stage) -> bool:
        """Return whether the stage's final artifact exists."""
        match stage:
            case Stage.RESOLVE:
                return self._manifest_path.exists()
            case Stage.SNAPSHOT:
                return self._snapshot_path.exists()
            case Stage.RANK:
                return not self.missing_rankings()
            case Stage.LABEL:
                return self._labels_path.exists()
            case Stage.SCORE:
                return bool(self.scoring_dates())
