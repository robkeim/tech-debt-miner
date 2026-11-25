"""What the LLM prompts show of a file's source: a head and an outline (ADR 0010).

Pure functions over file bytes. Line numbers split on LF, CRLF and CR, like `physical_loc`.
"""

import ast
import warnings

from tech_debt_miner.types import OutlineEntry

HEAD_LINES = 150


def file_head(content: bytes) -> tuple[str, int]:
    """Return the first `HEAD_LINES` lines and the number of lines after them.

    Lines are joined with LF; undecodable bytes are replaced.
    """
    lines = content.splitlines()
    head = b"\n".join(lines[:HEAD_LINES]).decode("utf-8", errors="replace")
    return head, max(0, len(lines) - HEAD_LINES)


def file_outline(content: bytes) -> tuple[OutlineEntry, ...]:
    """Return the classes and functions of a file, with methods one level under their class.

    Functions nested inside functions, and definitions under `if` or `try`, are left out. A file
    that does not parse gets an empty outline.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # old code trips SyntaxWarning on odd escapes
            tree = ast.parse(content.decode("utf-8", errors="replace"))
    except SyntaxError, ValueError, RecursionError:
        return ()
    entries: list[OutlineEntry] = []
    for node in tree.body:
        _add(entries, node, depth=0)
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                _add(entries, member, depth=1)
    return tuple(entries)


def _add(entries: list[OutlineEntry], node: ast.stmt, *, depth: int) -> None:
    if isinstance(node, ast.ClassDef):
        entries.append(OutlineEntry("class", node.name, node.lineno, depth))
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        entries.append(OutlineEntry("function", node.name, node.lineno, depth))
