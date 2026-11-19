from pathlib import Path

import pytest

from support.tiers import CollectedTest, tier_errors

pytestmark = pytest.mark.unit

ROOT = Path("/repo/tests")


def errors_for(directory: str, markers: set[str]) -> list[str]:
    test = CollectedTest("t::x", ROOT / directory / "test_x.py", frozenset(markers))
    return tier_errors([test], ROOT)


def test_matching_tier_passes() -> None:
    assert errors_for("unit", {"unit"}) == []


def test_other_markers_are_ignored() -> None:
    assert errors_for("policy", {"policy", "parametrize"}) == []


def test_missing_tier_is_reported() -> None:
    assert "found none" in errors_for("unit", {"parametrize"})[0]


def test_two_tiers_are_reported() -> None:
    assert "found integration, unit" in errors_for("unit", {"unit", "integration"})[0]


def test_tier_in_wrong_directory_is_reported() -> None:
    assert "lives under tests/integration/" in errors_for("integration", {"unit"})[0]
