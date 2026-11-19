"""The pass/fail summary printed after the last step."""

from collections.abc import Callable, Sequence

from gate.models import Result


def print_summary(results: Sequence[Result], out: Callable[[str], None] = print) -> None:
    out("\nSummary")
    for result in results:
        suffix = f" ({result.detail})" if result.detail else ""
        out(f"  {result.status.upper():4}  {result.name}{suffix}")
