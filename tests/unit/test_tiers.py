from pathlib import Path

import pytest

from support.tiers import tier_errors

pytestmark = pytest.mark.unit

ROOT = Path("/repo/tests")


def check(directory: str, markers: set[str]) -> list[str]:
    return tier_errors([("t::x", ROOT / directory / "test_x.py", markers)], ROOT)


def test_matching_tier_passes() -> None:
    assert check("unit", {"unit"}) == []


def test_other_markers_are_ignored() -> None:
    assert check("policy", {"policy", "parametrize"}) == []


def test_missing_tier_is_reported() -> None:
    assert "found none" in check("unit", {"parametrize"})[0]


def test_two_tiers_are_reported() -> None:
    assert "found integration, unit" in check("unit", {"unit", "integration"})[0]


def test_tier_in_wrong_directory_is_reported() -> None:
    assert "lives under tests/integration/" in check("integration", {"unit"})[0]
