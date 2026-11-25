from datetime import UTC, datetime, timedelta

import pytest

from tech_debt_miner import probe
from tech_debt_miner.repo.history import CommitChange, FileChange
from tech_debt_miner.types import Probe

pytestmark = pytest.mark.unit

START = datetime(2024, 2, 1, tzinfo=UTC)


def commit(
    sha: str,
    message: str,
    *paths: str,
    day: int = 0,
    deleted: bool = False,
    author: str = "Dev",
) -> CommitChange:
    return CommitChange(
        sha,
        START + timedelta(days=day),
        tuple(FileChange(path, deleted=deleted) for path in paths),
        author_name=author,
        message=message,
    )


def test_select_commit_picks_the_earliest_usable_fix_commit() -> None:
    commits = [  # newest first, as `list_commits` returns them
        commit("c3", "fix crash on empty input", "pkg/c.py", day=3),
        commit("c2", "fix off by one", "pkg/b.py", day=2),
        commit("c1", "add feature", "pkg/a.py", day=1),
    ]

    chosen = probe.select_commit(commits)

    assert chosen is not None
    assert (chosen[0].sha, chosen[1]) == ("c2", "pkg/b.py")


@pytest.mark.parametrize(
    "unusable",
    [
        commit("x", "add feature", "pkg/a.py"),  # not a fix
        commit("x", "fix bug", "pkg/a.py", author="renovate[bot]"),  # bot
        commit("x", "fix bug", "pkg/a.py", "pkg/b.py"),  # two eligible files
        commit("x", "fix bug", "README.md"),  # no eligible file
        commit("x", "fix bug", "tests/test_a.py"),  # a test, so not eligible
        commit("x", "fix bug", "pkg/a.py", deleted=True),  # the file is gone
        commit("x", "fix bug in a.py", "pkg/a.py"),  # the message gives the answer away
        commit("x", "fix bug in A.PY", "pkg/a.py"),  # case-insensitively
    ],
)
def test_select_commit_skips_commits_the_probe_cannot_use(unusable: CommitChange) -> None:
    assert probe.select_commit([unusable]) is None


def test_select_commit_allows_other_non_eligible_files_in_the_commit() -> None:
    chosen = probe.select_commit([commit("c", "fix bug", "pkg/a.py", "CHANGES.md")])

    assert chosen is not None
    assert chosen[1] == "pkg/a.py"


def test_select_commit_is_none_without_commits() -> None:
    assert probe.select_commit([]) is None


def test_build_request_holds_only_the_commit_message() -> None:
    request = probe.build_request("fix the thing\n\nbody", "model-1")

    assert request.ranker == "probe"
    assert request.model == "model-1"
    assert "fix the thing\n\nbody" in request.prompt


def test_build_request_truncates_a_long_message() -> None:
    request = probe.build_request("~" * 10_000, "m")

    assert request.prompt.count("~") == probe.MAX_MESSAGE_CHARS


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ('{"path": "pkg/a.py"}', "pkg/a.py"),
        ('{"path": " ./pkg/a.py "}', "pkg/a.py"),
        ('{"path": "`pkg/a.py`"}', "pkg/a.py"),
        ("not json", ""),
        ('["pkg/a.py"]', ""),
        ('{"path": 3}', ""),
        ("{}", ""),
    ],
)
def test_parse_answer(text: str, answer: str) -> None:
    assert probe.parse_answer(text) == answer


def test_grade_requires_the_exact_path() -> None:
    assert probe.grade("c", "pkg/a.py", "pkg/a.py") == Probe("c", "pkg/a.py", "pkg/a.py", hit=True)
    assert not probe.grade("c", "pkg/a.py", "a.py").hit
    assert not probe.grade("c", "pkg/a.py", "").hit
