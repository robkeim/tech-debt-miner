"""Which files are eligible, and how big they are (ADR 0004, ADR 0005).

One filter serves the ranked set and the Label, so both see the same files. Everything here is
pure: it takes paths and file contents and never touches a repo.

A path is eligible when it is a `*.py` source file that is not a test, doc, generated or vendored
file. Matching is by path only, on POSIX-style paths relative to the repo root. Directory names
and file-name globs are compared case-sensitively.
"""

from collections.abc import Iterable, Mapping
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

SOURCE_SUFFIX = ".py"

TEST_DIRS = frozenset({"test", "tests", "testing"})
TEST_FILE_GLOBS = ("test_*.py", "*_test.py", "conftest.py")

DOC_DIRS = frozenset({"doc", "docs"})

GENERATED_DIRS = frozenset({"generated", "__generated__"})
GENERATED_FILE_GLOBS = ("*_pb2.py", "*_pb2_grpc.py", "*_generated.py", "*.generated.py")

VENDORED_DIRS = frozenset(
    {
        "vendor",
        "vendored",
        "_vendor",
        "third_party",
        "third-party",
        "site-packages",
        "node_modules",
    },
)

_EXCLUDED_DIRS = TEST_DIRS | DOC_DIRS | GENERATED_DIRS | VENDORED_DIRS
_EXCLUDED_FILE_GLOBS = TEST_FILE_GLOBS + GENERATED_FILE_GLOBS


def is_eligible(path: str) -> bool:
    """Return whether `path` is a `*.py` source file outside the excluded categories."""
    pure = PurePosixPath(path)
    if pure.suffix != SOURCE_SUFFIX:
        return False
    *directories, name = pure.parts
    if any(part in _EXCLUDED_DIRS for part in directories):
        return False
    return not any(fnmatchcase(name, glob) for glob in _EXCLUDED_FILE_GLOBS)


def eligible_paths(paths: Iterable[str]) -> list[str]:
    """Return the eligible paths, sorted and de-duplicated."""
    return sorted({path for path in paths if is_eligible(path)})


def physical_loc(content: bytes) -> int:
    """Count physical lines: every line counts, blank and comment lines included.

    A final line without a newline still counts, and a trailing newline does not add a line.
    Lines end at LF, CRLF or CR.
    """
    return len(content.splitlines())


def loc_by_path(contents: Mapping[str, bytes]) -> dict[str, int]:
    """Return the physical LOC of each eligible path in `contents`."""
    return {path: physical_loc(contents[path]) for path in eligible_paths(contents)}
