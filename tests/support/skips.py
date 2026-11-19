"""Rule that every skip, skipif and xfail marker carries a reason linking an issue."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

SKIP_MARKERS = ("skip", "skipif", "xfail")
ISSUE_REFERENCE = re.compile(r"#\d+\b|/issues/\d+\b")


@dataclass(frozen=True)
class SkipMarker:
    """A skip-like marker on a collected test, with the arguments it was given."""

    node_id: str
    name: str
    args: tuple[object, ...]
    kwargs: Mapping[str, object]


def _reason(marker: SkipMarker) -> object:
    reason = marker.kwargs.get("reason")
    # Only `skip` takes the reason positionally; for `skipif` and `xfail` it is the condition.
    if reason is None and marker.name == "skip" and marker.args:
        return marker.args[0]
    return reason


def skip_errors(markers: Iterable[SkipMarker]) -> list[str]:
    """Check each skip-like marker; return one message per violation."""
    errors: list[str] = []
    for marker in markers:
        reason = _reason(marker)
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{marker.node_id}: `{marker.name}` needs a reason that links an issue")
        elif not ISSUE_REFERENCE.search(reason):
            errors.append(
                f"{marker.node_id}: `{marker.name}` reason must link an issue "
                f"(#N or an issue URL), got {reason!r}"
            )
    return errors
