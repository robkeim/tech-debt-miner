from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from support.fixture_repo import Commit, build_fixture_repo, git, head_sha
from tech_debt_miner import cli
from tech_debt_miner.run.artifacts import MANIFEST
from tech_debt_miner.run.resolve import ADR_FILES, ResolveDeps, ResolveInputs, resolve
from tech_debt_miner.run.run_dir import RunDir

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 24, 8, 30, tzinfo=UTC)
CUTOFF = date(2024, 1, 1)


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    """Make a clone, so `resolve` never touches the network."""
    build_fixture_repo(
        tmp_path / "repos" / "target",
        [
            Commit("before", {"a.py": "x = 1\n"}, at(2023, 6, 1)),
            Commit("after", {"a.py": "x = 2\n"}, at(2024, 3, 1)),
        ],
    )
    return tmp_path / "repos"


@pytest.fixture
def tool_root(tmp_path: Path) -> Path:
    return build_fixture_repo(
        tmp_path / "tool",
        [
            Commit(
                "adr 5",
                {
                    ADR_FILES["0005"]: "five\n",
                    ADR_FILES["0007"]: "seven\n",
                    ADR_FILES["0012"]: "twelve\n",
                },
                at(2023, 1, 1),
            ),
            Commit("edit adr 5", {ADR_FILES["0005"]: "five!\n"}, at(2023, 2, 1)),
        ],
    )


def deps_for(tmp_path: Path, tool_root: Path) -> ResolveDeps:
    return ResolveDeps(
        repos_dir=tmp_path / "repos",
        runs_dir=tmp_path / "runs",
        tool_root=tool_root,
        lizard_version="1.17.0",
        clock=lambda: NOW,
    )


def inputs(repeats: int = 3) -> ResolveInputs:
    return ResolveInputs(
        repo="owner/target",
        cutoff=CUTOFF,
        model="model-1",
        training_cutoff=date(2023, 6, 30),
        repeats=repeats,
    )


@pytest.mark.usefixtures("repos_dir")
def test_resolve_writes_the_manifest_and_creates_the_run_dir(
    tmp_path: Path, tool_root: Path
) -> None:
    run_dir = resolve(inputs(), deps_for(tmp_path, tool_root))

    manifest = run_dir.read(MANIFEST)
    assert run_dir.path.parent == tmp_path / "runs"
    assert manifest.target_repo == "owner/target"
    assert manifest.cutoff_date == "2024-01-01"
    assert manifest.model == "model-1"
    assert manifest.model_training_cutoff == "2023-06-30"
    assert manifest.cutoff_minus_training_days == 185
    assert manifest.repeats == 3
    assert manifest.prompt_hashes == {}
    assert manifest.lizard_version == "1.17.0"
    assert manifest.tool_sha == head_sha(tool_root)
    assert set(manifest.adr_shas) == {"0005", "0007", "0012"}


@pytest.mark.usefixtures("repos_dir")
def test_pinned_sha_is_the_last_commit_before_the_cutoff(tmp_path: Path, tool_root: Path) -> None:
    run_dir = resolve(inputs(), deps_for(tmp_path, tool_root))

    before = git(tmp_path / "repos" / "target", "rev-list", "--max-parents=0", "HEAD").strip()
    assert run_dir.read(MANIFEST).pinned_sha == before


@pytest.mark.usefixtures("repos_dir")
def test_adr_shas_are_the_last_commit_touching_each_adr(tmp_path: Path, tool_root: Path) -> None:
    manifest = resolve(inputs(), deps_for(tmp_path, tool_root)).read(MANIFEST)

    assert manifest.adr_shas["0005"] == head_sha(tool_root)
    assert manifest.adr_shas["0007"] != head_sha(tool_root)


@pytest.mark.usefixtures("repos_dir")
def test_resolve_rejects_zero_repeats(tmp_path: Path, tool_root: Path) -> None:
    with pytest.raises(ValueError, match="repeats"):
        resolve(inputs(repeats=0), deps_for(tmp_path, tool_root))


@pytest.mark.usefixtures("repos_dir")
def test_cli_resolve_then_status(
    tmp_path: Path, repos_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs_dir = tmp_path / "runs"
    argv = [
        "resolve",
        "--repo",
        "owner/target",
        "--cutoff",
        "2024-01-01",
        "--repos-dir",
        str(repos_dir),
        "--runs-dir",
        str(runs_dir),
    ]

    assert cli.main(argv) == 0
    run_id = capsys.readouterr().out.strip()
    assert RunDir(runs_dir / run_id).read(MANIFEST).repeats == 3

    assert cli.main(["status", run_id, "--runs-dir", str(runs_dir)]) == 0
    assert capsys.readouterr().out.strip() == "resolved"
