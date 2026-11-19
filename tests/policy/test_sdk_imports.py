"""ADR 0002: only the client module imports the provider SDK."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
SCANNED = (ROOT / "src", ROOT / "tests")
SDKS = frozenset({"anthropic"})
CLIENT_MODULE = ROOT / "src" / "tech_debt_miner" / "llm" / "client.py"


def sdk_imports(source: str) -> list[str]:
    """Top-level SDK packages imported anywhere in `source`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module.split(".")[0])
    return sorted(set(found) & SDKS)


def violations(files: list[Path], *, root: Path = ROOT, client: Path = CLIENT_MODULE) -> list[str]:
    return [
        f"{path.relative_to(root)} imports {', '.join(imports)}"
        for path in files
        if path != client
        if (imports := sdk_imports(path.read_text(encoding="utf-8")))
    ]


def test_only_the_client_module_imports_the_sdk() -> None:
    files = [path for base in SCANNED for path in sorted(base.rglob("*.py"))]
    assert files, "found no files to scan"
    assert violations(files) == []


@pytest.mark.parametrize(
    "source",
    [
        "import anthropic",
        "import anthropic.types",
        "from anthropic import Anthropic",
        "from anthropic.types import Message",
        "def f():\n    import anthropic\n",
    ],
)
def test_scanner_detects_every_import_form(source: str) -> None:
    assert sdk_imports(source) == ["anthropic"]


@pytest.mark.parametrize(
    "source", ["import os", "from . import anthropic", "x = 'anthropic'", "import anthropic_fake"]
)
def test_scanner_ignores_unrelated_code(source: str) -> None:
    assert sdk_imports(source) == []


def test_a_stray_import_is_reported_but_the_client_module_is_exempt(tmp_path: Path) -> None:
    stray = tmp_path / "stray.py"
    client = tmp_path / "client.py"
    for path in (stray, client):
        path.write_text("import anthropic\n", encoding="utf-8")
    assert violations([stray, client], root=tmp_path, client=client) == [
        "stray.py imports anthropic"
    ]
