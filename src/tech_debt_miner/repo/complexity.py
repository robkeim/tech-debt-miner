"""Cyclomatic complexity from `lizard`, summed over a file's functions (ADR 0007).

Module-level code is not counted. A file with no functions, or one `lizard` cannot analyze,
gets 0.
"""

import importlib
from collections.abc import Iterable
from typing import Protocol, cast


class _Function(Protocol):
    cyclomatic_complexity: int


class _FileInformation(Protocol):
    function_list: Iterable[_Function]


class _AnalyzeFile(Protocol):
    @staticmethod
    def analyze_source_code(filename: str, code: str) -> _FileInformation: ...


# `lizard` ships no type stubs, so import it dynamically and type only the part used here.
_analyze_file = cast("_AnalyzeFile", importlib.import_module("lizard").analyze_file)


def file_complexity(path: str, content: bytes) -> int:
    """Return the summed cyclomatic complexity of the functions in `content`.

    0 means no functions, or a file `lizard` could not analyze.
    """
    try:
        source = content.decode("utf-8")
        functions = _analyze_file.analyze_source_code(path, source).function_list
    except Exception:  # noqa: BLE001 - lizard's failures on odd input are unspecified; 0 is the rule
        return 0
    return sum(function.cyclomatic_complexity for function in functions)
