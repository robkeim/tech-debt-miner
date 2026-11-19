"""Rules that keep every test in exactly one tier, in the matching directory."""

from collections.abc import Iterable
from pathlib import Path

TIERS = ("unit", "integration", "policy")


def tier_errors(items: Iterable[tuple[str, Path, set[str]]], tests_root: Path) -> list[str]:
    """Check `(node id, file, marker names)` triples; return one message per violation."""
    errors: list[str] = []
    for node_id, path, markers in items:
        tiers = sorted(markers & set(TIERS))
        if len(tiers) != 1:
            found = ", ".join(tiers) if tiers else "none"
            errors.append(f"{node_id}: needs exactly one of {', '.join(TIERS)} (found {found})")
            continue
        directory = path.relative_to(tests_root).parts[0]
        if directory != tiers[0]:
            errors.append(f"{node_id}: marked `{tiers[0]}` but lives under tests/{directory}/")
    return errors
