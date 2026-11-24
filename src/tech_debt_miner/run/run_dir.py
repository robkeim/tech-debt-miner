"""The Run directory: the only code that touches Run files, over the table in `artifacts`."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from tech_debt_miner.run import store
from tech_debt_miner.run.artifacts import (
    BASELINE,
    LABELS,
    MANIFEST,
    RANKING,
    REQUESTS,
    SCORES,
    SNAPSHOT,
    Artifact,
    Policy,
)
from tech_debt_miner.types import Manifest

LLM = "llm"


class Stage(StrEnum):
    RESOLVE = "resolve"
    SNAPSHOT = "snapshot"
    RANK = "rank"
    LABEL = "label"
    SCORE = "score"


class RunState(StrEnum):
    PLANNED = "planned"
    RANKED = "ranked"
    SCORED = "scored"


def run_id(manifest: Manifest, now: datetime) -> str:
    """Return `<UTC-timestamp>-<8 hex of sha256 over the canonical manifest.json>`."""
    if now.tzinfo is None:
        msg = "the clock must return a timezone-aware datetime"
        raise ValueError(msg)
    digest = hashlib.sha256(_manifest_text(manifest).encode("utf-8")).hexdigest()[:8]
    return f"{now.astimezone(UTC):%Y%m%dT%H%M%SZ}-{digest}"


def _manifest_text(manifest: Manifest) -> str:
    return store.canonical_json(MANIFEST.encode(manifest))


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
        run_dir.write(MANIFEST, manifest)
        return run_dir

    @property
    def id(self) -> str:
        return self.path.name

    # Reads and writes, over the definitions in `artifacts`

    def exists(self, artifact: Artifact[Any, Any], key: Any = None) -> bool:  # noqa: ANN401 - key type follows the artifact
        return self._path(artifact, key).exists()

    def read[T, K](self, artifact: Artifact[T, K], key: K | None = None) -> T:
        self._require(artifact, Policy.REPLACE, Policy.CREATE_ONCE, op="read")
        return artifact.decode(store.read_json(self._path(artifact, key)))

    def write[T, K](self, artifact: Artifact[T, K], value: T, key: K | None = None) -> None:
        """Write `value`. A `CREATE_ONCE` artifact (scores) never overwrites an earlier file."""
        self._require(artifact, Policy.REPLACE, Policy.CREATE_ONCE, op="write")
        path = self._path(artifact, self._key_for(artifact, value, key))
        if artifact.policy is Policy.CREATE_ONCE and path.exists():
            msg = f"{path.name} already exists; it is never overwritten"
            raise FileExistsError(msg)
        store.write_json(path, artifact.encode(value))

    def append[T](self, artifact: Artifact[T, None], value: T) -> None:
        self._require(artifact, Policy.APPEND, op="append to")
        store.append_jsonl(self._path(artifact, None), artifact.encode(value))

    def read_all[T](self, artifact: Artifact[T, None]) -> list[T]:
        self._require(artifact, Policy.APPEND, op="read all rows of")
        return [artifact.decode(row) for row in store.read_jsonl(self._path(artifact, None))]

    def keys[K](self, artifact: Artifact[Any, K]) -> list[K]:
        """Return the keys of a keyed artifact's existing files, sorted."""
        if artifact.glob is None or artifact.parse_key is None:
            msg = f"{artifact.name} cannot be enumerated"
            raise TypeError(msg)
        parsed = (artifact.parse_key(p.name) for p in self.path.glob(artifact.glob))
        return sorted(parsed, key=str)

    def _path(self, artifact: Artifact[Any, Any], key: object) -> Path:
        if artifact.keyed and key is None:
            msg = f"{artifact.name} needs a key"
            raise TypeError(msg)
        return self.path / artifact.path(key)

    @staticmethod
    def _key_for[T, K](artifact: Artifact[T, K], value: T, key: K | None) -> K | None:
        if key is None and artifact.key_of is not None:
            return artifact.key_of(value)
        return key

    @staticmethod
    def _require(artifact: Artifact[Any, Any], *policies: Policy, op: str) -> None:
        if artifact.policy not in policies:
            msg = f"cannot {op} {artifact.name}: it is a {artifact.policy} artifact"
            raise TypeError(msg)

    # Stage and state checks

    def is_done(self, stage: Stage) -> bool:
        """Return whether the stage's final artifact exists."""
        match stage:
            case Stage.RESOLVE:
                return self.exists(MANIFEST)
            case Stage.SNAPSHOT:
                return self.exists(SNAPSHOT)
            case Stage.RANK:
                return self.is_done(Stage.RESOLVE) and self._all_rankings_exist()
            case Stage.LABEL:
                return self.exists(LABELS)
            case Stage.SCORE:
                return bool(self.keys(SCORES))

    def _all_rankings_exist(self) -> bool:
        repeats = self.read(MANIFEST).repeats
        return self.exists(RANKING, (BASELINE, 0)) and all(
            self.exists(RANKING, (LLM, repeat)) for repeat in range(repeats)
        )

    def state(self) -> RunState | None:
        """Derive the Run's state from its artifacts, or None before it is planned."""
        planned = (
            self.is_done(Stage.RESOLVE) and self.is_done(Stage.SNAPSHOT) and self.exists(REQUESTS)
        )
        if not planned:
            return None
        if not self.is_done(Stage.RANK):
            return RunState.PLANNED
        if self.is_done(Stage.LABEL) and self.is_done(Stage.SCORE):
            return RunState.SCORED
        return RunState.RANKED
