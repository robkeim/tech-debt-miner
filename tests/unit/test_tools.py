from pathlib import Path

import pytest

from gate.tools import resolve_tool

pytestmark = pytest.mark.unit


def test_resolve_prefers_the_venv(tmp_path: Path) -> None:
    (tmp_path / "ruff").write_text("")
    assert resolve_tool("ruff", which=lambda _t: "/elsewhere/ruff", venv_bin=tmp_path) == str(
        tmp_path / "ruff"
    )


def test_resolve_falls_back_to_path(tmp_path: Path) -> None:
    assert resolve_tool("cspell", which=lambda t: f"/usr/bin/{t}", venv_bin=tmp_path) == (
        "/usr/bin/cspell"
    )


def test_resolve_returns_none_without_mise(tmp_path: Path) -> None:
    assert resolve_tool("cspell", which=lambda _t: None, venv_bin=tmp_path) is None
