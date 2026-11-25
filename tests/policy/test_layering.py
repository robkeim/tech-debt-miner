"""ADR 0009: leaf modules import only `types` and the pure `repo` modules.

Leaves are pure functions over plain data. They may use `types` and the `repo` modules that run
no subprocess, never `repo/git.py` or anything else that does. The scan covers the leaf modules
that exist and conform today; add a module here when it becomes a leaf.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "tech_debt_miner"
SRC = ROOT / "src" / PACKAGE
LEAF_MODULES = (
    SRC / "labels.py",
    SRC / "scoring.py",
    SRC / "report.py",
    SRC / "rankers" / "prompts.py",
    SRC / "llm" / "cache.py",
)
ALLOWED = frozenset(
    {
        f"{PACKAGE}.types",
        f"{PACKAGE}.jsonio",
        f"{PACKAGE}.repo.history",
        f"{PACKAGE}.repo.cutoff",
        f"{PACKAGE}.repo.eligibility",
        f"{PACKAGE}.repo.source",
    }
)


def package_imports(source: str) -> set[str]:
    """Modules of this package imported anywhere in `source`, as dotted names."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.split(".")[0] == PACKAGE)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] != PACKAGE:
                continue
            # `from tech_debt_miner.repo import git` imports the module `repo.git`.
            found.update(
                f"{node.module}.{a.name}"
                if node.module in {PACKAGE, f"{PACKAGE}.repo"}
                else node.module
                for a in node.names
            )
    return found


def violations(files: list[Path], root: Path = ROOT) -> list[str]:
    return [
        f"{path.relative_to(root)} imports {module}"
        for path in files
        for module in sorted(package_imports(path.read_text(encoding="utf-8")) - ALLOWED)
    ]


def test_leaf_modules_import_only_types_and_pure_repo_modules() -> None:
    assert all(path.exists() for path in LEAF_MODULES)
    assert violations(list(LEAF_MODULES)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from tech_debt_miner.types import Labels", ("tech_debt_miner.types",)),
        ("from tech_debt_miner.repo.git import list_commits", ("tech_debt_miner.repo.git",)),
        ("from tech_debt_miner.repo import git", ("tech_debt_miner.repo.git",)),
        ("import tech_debt_miner.run.store", ("tech_debt_miner.run.store",)),
        ("def f():\n    from tech_debt_miner.llm import cache\n", ("tech_debt_miner.llm",)),
        ("import math\nfrom pathlib import Path", ()),
    ],
)
def test_package_imports_finds_every_import_form(source: str, expected: tuple[str, ...]) -> None:
    assert sorted(package_imports(source)) == list(expected)


def test_violations_flag_a_forbidden_import(tmp_path: Path) -> None:
    leaf = tmp_path / "leaf.py"
    leaf.write_text("from tech_debt_miner.repo.git import head_sha\n", encoding="utf-8")
    assert violations([leaf], root=tmp_path) == ["leaf.py imports tech_debt_miner.repo.git"]
