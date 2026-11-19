"""Rules that keep every test in exactly one tier, in the matching directory."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TIERS = ("unit", "integration", "policy")


@dataclass(frozen=True)
class CollectedTest:
    """A collected test: its node id, its file and the names of its markers."""

    node_id: str
    path: Path
    markers: frozenset[str]


def tier_errors(tests: Iterable[CollectedTest], tests_root: Path) -> list[str]:
    """Check each collected test; return one message per violation."""
    errors: list[str] = []
    for test in tests:
        tiers = sorted(test.markers & set(TIERS))
        if len(tiers) != 1:
            found = ", ".join(tiers) if tiers else "none"
            errors.append(
                f"{test.node_id}: needs exactly one of {', '.join(TIERS)} (found {found})"
            )
            continue
        directory = test.path.relative_to(tests_root).parts[0]
        if directory != tiers[0]:
            errors.append(f"{test.node_id}: marked `{tiers[0]}` but lives under tests/{directory}/")
    return errors
