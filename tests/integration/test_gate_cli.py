import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def gate(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "gate.cli", *args],
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def test_commit_msg_exit_codes(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.write_text("fix: handle empty input\n", encoding="utf-8")
    bad = tmp_path / "bad"
    bad.write_text("Fixed it.\n", encoding="utf-8")
    assert gate("commit-msg", str(good)).returncode == 0
    assert gate("commit-msg", str(bad)).returncode == 1


def test_pr_title_exit_codes() -> None:
    assert gate("pr-title", env={"PR_TITLE": "feat: add ranking"}).returncode == 0
    assert gate("pr-title", env={"PR_TITLE": "Add ranking"}).returncode == 1
