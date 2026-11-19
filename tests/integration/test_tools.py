import stat
import sys
from pathlib import Path

import pytest

from gate.tools import mise_bin_paths, resolve_tool, run_argv

pytestmark = pytest.mark.integration


def fake_mise(directory: Path, *, body: str) -> Path:
    script = directory / "mise"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_mise_bin_paths_lists_the_pinned_tool_dirs(tmp_path: Path) -> None:
    mise = fake_mise(tmp_path, body='echo "/pinned/a /pinned/b"')
    assert mise_bin_paths({"mise": str(mise)}.get) == ["/pinned/a", "/pinned/b"]


def test_mise_bin_paths_is_empty_without_mise() -> None:
    assert mise_bin_paths(lambda _tool: None) == []


def test_mise_bin_paths_is_empty_when_mise_fails(tmp_path: Path) -> None:
    mise = fake_mise(tmp_path, body="exit 1")
    assert mise_bin_paths({"mise": str(mise)}.get) == []


def test_resolve_asks_mise_when_the_tool_is_not_on_path(tmp_path: Path) -> None:
    mise = fake_mise(tmp_path, body='echo "/mise/installs/$2"')
    which = {"mise": str(mise)}.get
    assert resolve_tool("lychee", which=which, venv_bin=tmp_path) == "/mise/installs/lychee"


def test_resolve_returns_none_when_mise_does_not_know_the_tool(tmp_path: Path) -> None:
    mise = fake_mise(tmp_path, body="exit 1")
    assert resolve_tool("nope", which={"mise": str(mise)}.get, venv_bin=tmp_path) is None


def test_default_runner_pipes_stdin() -> None:
    code = "import sys; raise SystemExit(int(sys.stdin.read()))"
    assert run_argv([sys.executable, "-c", code], "5") == 5


def test_default_runner_returns_the_process_exit_code() -> None:
    assert run_argv([sys.executable, "-c", "raise SystemExit(4)"]) == 4
