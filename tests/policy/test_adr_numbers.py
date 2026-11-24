"""ADR numbers are unique, contiguous from 0001, and every filename is `NNNN-slug.md`."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
NAME = re.compile(r"^(?P<number>\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")


def violations(names: list[str]) -> list[str]:
    """Problems with a list of ADR filenames; empty when the numbering is sound."""
    problems: list[str] = []
    by_number: dict[int, list[str]] = {}
    for name in sorted(names):
        match = NAME.match(name)
        if match is None:
            problems.append(f"{name} does not match NNNN-slug.md")
            continue
        by_number.setdefault(int(match["number"]), []).append(name)
    problems.extend(
        f"ADR {number:04d} is used by {', '.join(files)}"
        for number, files in sorted(by_number.items())
        if len(files) > 1
    )
    problems.extend(
        f"ADR {number:04d} is missing"
        for number in range(1, max(by_number, default=0))
        if number not in by_number
    )
    return problems


def test_adr_numbers_are_unique_and_contiguous() -> None:
    names = [path.name for path in ADR_DIR.glob("*.md")]
    assert names, "found no ADRs"
    assert violations(names) == []


def test_a_sound_sequence_has_no_violations() -> None:
    assert violations(["0001-a.md", "0002-b-c.md"]) == []


def test_a_reused_number_names_both_files() -> None:
    assert violations(["0001-a.md", "0002-b.md", "0002-c.md"]) == [
        "ADR 0002 is used by 0002-b.md, 0002-c.md"
    ]


def test_a_gap_is_reported() -> None:
    assert violations(["0001-a.md", "0003-c.md"]) == ["ADR 0002 is missing"]


@pytest.mark.parametrize("name", ["1-a.md", "0001-A.md", "0001.md", "0001-a.txt", "0001-a_b.md"])
def test_a_malformed_name_is_reported(name: str) -> None:
    assert violations([name]) == [f"{name} does not match NNNN-slug.md"]
