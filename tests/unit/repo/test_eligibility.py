import pytest

from tech_debt_miner.repo.eligibility import eligible_paths, is_eligible, loc_by_path, physical_loc

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path",
    [
        "setup.py",
        "pkg/mod.py",
        "src/pkg/sub/mod.py",
        "src/pkg/__init__.py",
        "pkg/contest.py",
        "pkg/latest.py",
        "pkg/testing_utils.py",
        "pkg/attestation.py",
        "pkg/Tests_helpers.py",
        "pkg/docstrings.py",
        "pkg/vendor_utils.py",
    ],
)
def test_source_files_are_eligible(path: str) -> None:
    assert is_eligible(path)


@pytest.mark.parametrize(
    "path",
    [
        # not Python source
        "README.md",
        "pkg/mod.pyi",
        "pkg/mod.pyc",
        "pkg/mod.py.orig",
        "pkg/mod",
        "pkg/mod.PY",
        ".py",
        # tests
        "tests/helper.py",
        "test/helper.py",
        "testing/helper.py",
        "pkg/tests/unit/helper.py",
        "pkg/test_mod.py",
        "pkg/mod_test.py",
        "conftest.py",
        "pkg/conftest.py",
        # docs
        "docs/conf.py",
        "doc/conf.py",
        "pkg/docs/examples/demo.py",
        # generated
        "pkg/api_pb2.py",
        "pkg/api_pb2_grpc.py",
        "pkg/schema_generated.py",
        "pkg/schema.generated.py",
        "pkg/generated/mod.py",
        "pkg/__generated__/mod.py",
        # vendored
        "vendor/lib.py",
        "pkg/vendored/lib.py",
        "pkg/_vendor/lib.py",
        "third_party/lib.py",
        "third-party/lib.py",
        "venv/lib/site-packages/lib.py",
        "node_modules/pkg/tool.py",
    ],
)
def test_other_files_are_excluded(path: str) -> None:
    assert not is_eligible(path)


def test_directory_names_match_whole_components_only() -> None:
    assert is_eligible("contests/mod.py")
    assert is_eligible("pkg/tests_support/mod.py")
    assert is_eligible("vendors/mod.py")


def test_eligible_paths_filters_sorts_and_deduplicates() -> None:
    paths = ["b.py", "tests/a.py", "a.py", "docs/x.py", "b.py", "c.txt"]
    assert eligible_paths(paths) == ["a.py", "b.py"]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", 0),
        (b"\n", 1),
        (b"x = 1", 1),
        (b"x = 1\n", 1),
        (b"x = 1\ny = 2\n", 2),
        (b"x = 1\n\n\n", 3),
        (b"# comment\n\n    \nx = 1\n", 4),
        (b"a\r\nb\r\n", 2),
        (b"a\rb\r", 2),
        (b"a\x0cb\n", 1),
    ],
)
def test_physical_loc_counts_every_line(content: bytes, expected: int) -> None:
    assert physical_loc(content) == expected


def test_loc_by_path_covers_only_eligible_paths() -> None:
    contents = {
        "pkg/mod.py": b"a\nb\nc\n",
        "tests/test_mod.py": b"assert True\n",
        "README.md": b"hello\n",
        "pkg/empty.py": b"",
    }
    assert loc_by_path(contents) == {"pkg/empty.py": 0, "pkg/mod.py": 3}
