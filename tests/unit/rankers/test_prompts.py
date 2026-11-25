import hashlib
from dataclasses import replace
from importlib import resources

import pytest

from tech_debt_miner.rankers.prompts import (
    DIGEST_MAX_SUBJECTS,
    DigestOverflowError,
    build_digest,
    build_rank_prompt,
    build_triage_prompt,
    estimate_tokens,
    template_hashes,
    triage_set_size,
)
from tech_debt_miner.repo.source import HEAD_LINES
from tech_debt_miner.types import CommitSubject, FileFacts, OutlineEntry, Snapshot

pytestmark = pytest.mark.unit

SUBJECTS = tuple(CommitSubject(f"2024-01-0{day}", f"subject {day}") for day in range(6, 0, -1))


def facts(path: str, *, loc: int = 10, **overrides: object) -> FileFacts:
    base = FileFacts(
        path=path,
        loc=loc,
        churn=7777,
        complexity=31.5,
        outline=(OutlineEntry("class", "Foo", 1, 0), OutlineEntry("function", "bar", 2, 1)),
        head="class Foo:\n    def bar(self): ...",
        truncated_lines=0,
        recent_commits=SUBJECTS[:DIGEST_MAX_SUBJECTS],
    )
    return replace(base, **overrides)


def snapshot_of(*files: FileFacts) -> Snapshot:
    return Snapshot(files=files, issues=(), zero_complexity_files=0)


def test_the_digest_lists_every_file_in_path_order_with_names_and_subjects() -> None:
    digest = build_digest([facts("b.py", loc=20), facts("a.py")])

    lines = digest.splitlines()
    assert lines[0] == "a.py (10 lines): Foo"
    assert lines[1] == "  2024-01-06 subject 6"
    assert digest.index("a.py") < digest.index("b.py (20 lines): Foo")
    assert len([line for line in lines if line.startswith("  ")]) == 2 * DIGEST_MAX_SUBJECTS


def _without_subjects(files: list[FileFacts]) -> str:
    return "\n".join(f"{f.path} ({f.loc} lines): Foo" for f in files)


def test_the_digest_shrinks_subjects_before_names_then_names_before_giving_up() -> None:
    files = [facts(f"pkg/module_{n:03}.py") for n in range(40)]
    full = build_digest(files)
    full_tokens = estimate_tokens(full)

    fewer = build_digest(files, max_tokens=full_tokens - 1)
    assert len(fewer.splitlines()) < len(full.splitlines())
    assert ": Foo" in fewer
    assert all(f"pkg/module_{n:03}.py" in fewer for n in range(40))  # never drops a file

    no_subjects = build_digest(files, max_tokens=estimate_tokens(_without_subjects(files)))
    assert no_subjects == _without_subjects(files)

    paths_only = "\n".join(f"{f.path} ({f.loc} lines)" for f in files)
    bare = build_digest(files, max_tokens=estimate_tokens(paths_only))
    assert bare == paths_only


def test_the_shrink_is_uniform_across_files() -> None:
    files = [facts(f"m{n:02}.py") for n in range(30)]
    full = build_digest(files)
    shrunk = build_digest(files, max_tokens=estimate_tokens(full) - 1)
    counts = {
        sum(1 for line in block if line.startswith("  "))
        for block in (shrunk.split("\nm")[i].splitlines() for i in range(len(files)))
    }
    assert len(counts) == 1


def test_the_digest_fails_when_path_and_loc_alone_overflow() -> None:
    with pytest.raises(DigestOverflowError, match="2 files"):
        build_digest([facts("a.py"), facts("b.py")], max_tokens=3)


def test_the_triage_prompt_asks_for_min_100_and_eligible_files() -> None:
    small = build_triage_prompt(snapshot_of(facts("a.py"), facts("b.py")))
    assert "exactly 2 distinct paths" in small
    assert "a.py (10 lines): Foo" in small
    assert triage_set_size(5000) == 100
    assert triage_set_size(7) == 7


def test_the_rank_prompt_shows_a_short_file_whole_with_dated_subjects() -> None:
    prompt = build_rank_prompt(snapshot_of(facts("a.py"), facts("b.py")), ["a.py"])

    assert "=== a.py ===" in prompt
    assert "2024-01-06 subject 6" in prompt
    assert "class Foo:\n    def bar(self): ..." in prompt
    assert "b.py" not in prompt
    assert "truncated" not in prompt
    assert "Outline" not in prompt


def test_the_rank_prompt_outlines_only_what_the_head_cuts_off() -> None:
    long_file = facts(
        "long.py",
        truncated_lines=40,
        outline=(
            OutlineEntry("class", "Early", 3, 0),
            OutlineEntry("class", "Late", HEAD_LINES + 5, 0),
            OutlineEntry("function", "method", HEAD_LINES + 9, 1),
        ),
    )

    prompt = build_rank_prompt(snapshot_of(long_file), ["long.py"])

    assert (
        f"Outline of the rest:\nclass Late (line {HEAD_LINES + 5})\n"
        f"  function method (line {HEAD_LINES + 9})\n[truncated 40 lines]"
    ) in prompt
    assert "Early" not in prompt


def test_the_rank_prompt_rejects_a_path_outside_the_snapshot() -> None:
    with pytest.raises(ValueError, match=r"nope\.py"):
        build_rank_prompt(snapshot_of(facts("a.py")), ["nope.py"])


def test_the_rank_prompt_order_ignores_the_order_of_the_triage_set() -> None:
    snapshot = snapshot_of(facts("a.py"), facts("b.py"))
    assert build_rank_prompt(snapshot, ["b.py", "a.py"]) == build_rank_prompt(
        snapshot, ["a.py", "b.py"]
    )


def test_neither_prompt_shows_churn_or_complexity() -> None:
    snapshot = snapshot_of(facts("a.py"), facts("b.py"))
    for prompt in (build_triage_prompt(snapshot), build_rank_prompt(snapshot, ["a.py", "b.py"])):
        assert "7777" not in prompt
        assert "31.5" not in prompt


def test_code_with_template_syntax_is_not_expanded() -> None:
    tricky = facts("a.py", head="x = '$count ${digest} {head_lines}'")
    prompt = build_rank_prompt(snapshot_of(tricky), ["a.py"])
    assert "x = '$count ${digest} {head_lines}'" in prompt


def test_template_hashes_are_stable_sha256_hex() -> None:
    hashes = template_hashes()
    assert set(hashes) == {"triage", "rank"}
    assert all(len(value) == 64 for value in hashes.values())
    assert hashes == template_hashes()


def test_a_cut_file_with_nothing_to_outline_has_no_empty_outline_header() -> None:
    cut = facts("a.py", truncated_lines=9, outline=())
    prompt = build_rank_prompt(snapshot_of(cut), ["a.py"])
    assert "Outline" not in prompt
    assert "[truncated 9 lines]" in prompt


def test_template_hashes_are_the_sha256_of_the_file_bytes() -> None:
    path = resources.files("tech_debt_miner") / "prompts" / "rank.txt"
    assert template_hashes()["rank"] == hashlib.sha256(path.read_bytes()).hexdigest()
