from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import time_machine

from support.fixture_repo import Commit, build_fixture_repo
from tech_debt_miner import cli
from tech_debt_miner.llm.client import LLMClient
from tech_debt_miner.repo.git import resolve_pinned_sha
from tech_debt_miner.run.artifacts import PROBE, RESPONSES
from tech_debt_miner.run.label import WindowOpenError
from tech_debt_miner.run.probe import NoProbeCommitError, ProbeDeps, run_probe
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest, Request, Response

pytestmark = pytest.mark.integration

CUTOFF = date(2024, 1, 1)
AFTER_WINDOW = date(2024, 8, 1)
POISON = "POISON_BEFORE_THE_WINDOW"
BODY = "def f():\n    return 1\n"


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)


class FakeTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[Request, Mapping[str, object] | None]] = []

    def send(self, request: Request, schema: Mapping[str, object] | None) -> Response:
        self.calls.append((request, schema))
        return Response(self.text, 100, 10, "end_turn", "req_1", request.model)


def make_run(tmp_path: Path, commits: list[Commit]) -> RunDir:
    repo = build_fixture_repo(tmp_path / "repos" / "target", commits)
    manifest = Manifest(
        target_repo="owner/target",
        pinned_sha=resolve_pinned_sha(repo, CUTOFF),
        cutoff_date=CUTOFF.isoformat(),
        model="claude-sonnet-5-5",
        model_training_cutoff="2023-06-30",
        cutoff_minus_training_days=185,
        repeats=1,
        prompt_hashes={},
        lizard_version="1.17.0",
        adr_shas={},
        tool_sha="c" * 40,
    )
    return RunDir.create(tmp_path / "runs", manifest, lambda: at(2024, 8, 1))


def deps_for(run_dir: RunDir, transport: FakeTransport, today: date = AFTER_WINDOW) -> ProbeDeps:
    client = LLMClient(transport, max_usd=1.0, log=lambda row: run_dir.append(RESPONSES, row))
    return ProbeDeps(repos_dir=run_dir.path.parents[1] / "repos", client=client, today=today)


@pytest.fixture
def run_dir(tmp_path: Path) -> RunDir:
    return make_run(
        tmp_path,
        [
            Commit("base", {"a.py": BODY, "pkg/b.py": BODY}, at(2023, 6, 1)),
            Commit(f"fix {POISON}", {"a.py": BODY + "# 1\n"}, at(2023, 12, 31)),
            Commit("add feature", {"a.py": BODY + "# 2\n"}, at(2024, 2, 1)),
            Commit("fix crash on empty input", {"pkg/b.py": BODY + "# 3\n"}, at(2024, 3, 1)),
            Commit("fix another thing", {"a.py": BODY + "# 4\n"}, at(2024, 4, 1)),
        ],
    )


def test_probe_asks_about_the_earliest_post_cutoff_fix_and_logs_through_the_client(
    run_dir: RunDir,
) -> None:
    transport = FakeTransport('{"path": "pkg/b.py"}')

    result = run_probe(run_dir, deps_for(run_dir, transport))

    assert (result.expected_path, result.answer, result.hit) == ("pkg/b.py", "pkg/b.py", True)
    assert run_dir.read(PROBE) == result
    [(request, schema)] = transport.calls
    assert "fix crash on empty input" in request.prompt
    assert schema is not None
    [row] = run_dir.read_all(RESPONSES)
    assert (row["ranker"], row["request_id"]) == ("probe", "req_1")


def test_probe_prompt_carries_no_repo_context(run_dir: RunDir) -> None:
    transport = FakeTransport("{}")

    run_probe(run_dir, deps_for(run_dir, transport))

    prompt = transport.calls[0][0].prompt
    assert not any(word in prompt for word in ("owner", "target", "pkg", "a.py", POISON))
    assert "fix another thing" not in prompt  # one commit, not the window


def test_probe_records_a_miss_for_an_unusable_answer(run_dir: RunDir) -> None:
    result = run_probe(run_dir, deps_for(run_dir, FakeTransport("sorry")))

    assert (result.answer, result.hit) == ("", False)


def test_probe_runs_once(run_dir: RunDir) -> None:
    transport = FakeTransport("{}")
    run_probe(run_dir, deps_for(run_dir, transport))

    with pytest.raises(FileExistsError):
        run_probe(run_dir, deps_for(run_dir, transport))

    assert len(transport.calls) == 1


def test_probe_refuses_until_the_window_has_closed(run_dir: RunDir) -> None:
    transport = FakeTransport("{}")

    with pytest.raises(WindowOpenError):
        run_probe(run_dir, deps_for(run_dir, transport, today=date(2024, 7, 1)))

    assert transport.calls == []


def test_probe_fails_clearly_when_no_commit_is_usable(tmp_path: Path) -> None:
    run_dir = make_run(
        tmp_path,
        [
            Commit("base", {"a.py": BODY}, at(2023, 6, 1)),
            Commit("add feature", {"a.py": BODY + "# 1\n"}, at(2024, 2, 1)),
        ],
    )
    transport = FakeTransport("{}")

    with pytest.raises(NoProbeCommitError, match="label"):
        run_probe(run_dir, deps_for(run_dir, transport))

    assert transport.calls == []


def test_cli_probe_is_a_dry_run_without_the_run_flag(
    run_dir: RunDir, capsys: pytest.CaptureFixture[str], frozen_clock: time_machine.Traveller
) -> None:
    frozen_clock.move_to(datetime(2024, 8, 1, tzinfo=UTC))
    argv = ["probe", run_dir.id, "--runs-dir", str(run_dir.path.parent)]
    argv += ["--repos-dir", str(run_dir.path.parents[1] / "repos")]

    assert cli.main(argv) == 0

    assert "Dry-run" in capsys.readouterr().out
    assert not run_dir.exists(PROBE)
    assert not run_dir.exists(RESPONSES)


def test_cli_probe_reports_an_open_window_and_fails(
    run_dir: RunDir, capsys: pytest.CaptureFixture[str], frozen_clock: time_machine.Traveller
) -> None:
    frozen_clock.move_to(datetime(2024, 3, 1, tzinfo=UTC))
    argv = ["probe", run_dir.id, "--runs-dir", str(run_dir.path.parent)]
    argv += ["--repos-dir", str(run_dir.path.parents[1] / "repos")]

    assert cli.main(argv) == 1

    assert "window closes" in capsys.readouterr().err
