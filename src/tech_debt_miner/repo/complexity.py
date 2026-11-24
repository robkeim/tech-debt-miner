"""Cyclomatic complexity from `lizard`, summed over a file's functions (ADR 0007).

Module-level code is not counted. A file with no functions, or one `lizard` cannot analyze,
gets 0.
"""

import importlib
from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Complexity:
    value: int
    zero: bool  # True when the 0 stands for "no functions" or "could not analyze"


def file_complexity(path: str, content: bytes) -> Complexity:
    """Return the summed cyclomatic complexity of the functions in `content`."""
    try:
        source = content.decode("utf-8")
        functions = _analyze_file.analyze_source_code(path, source).function_list
    except Exception:  # noqa: BLE001 - lizard's failures on odd input are unspecified; 0 is the rule
        return Complexity(0, zero=True)
    total = sum(function.cyclomatic_complexity for function in functions)
    return Complexity(total, zero=total == 0)
