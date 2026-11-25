import dataclasses
from datetime import UTC, date, datetime, timedelta

import pytest

from tech_debt_miner import labels
from tech_debt_miner.repo.git import CommitChange, FileChange

pytestmark = pytest.mark.unit

START = datetime(2024, 2, 1, tzinfo=UTC)


def commit(
    message: str,
    *files: FileChange | str,
    day: int = 0,
    name: str = "Dev",
    email: str = "dev@example.com",
) -> CommitChange:
    changes = tuple(f if isinstance(f, FileChange) else FileChange(f) for f in files)
    return CommitChange(
        sha=f"sha-{message}-{day}",
        committed_at=START + timedelta(days=day),
        files=changes,
        author_name=name,
        author_email=email,
        message=message,
    )


def counts(
    commits: list[CommitChange], files: list[str], max_files: int | None = None
) -> dict[str, int]:
    return dict(labels.build_labels(commits, files, max_files).keyword_counts)


@pytest.mark.parametrize(
    "message",
    ["fix crash", "Fixes the parser", "fixed it", "Bug in loop", "defect report", "apply patch"],
)
def test_keyword_matches_whole_words_ignoring_case(message: str) -> None:
    assert labels.is_keyword_fix(commit(message))


@pytest.mark.parametrize(
    "message", ["prefix", "bugs everywhere", "debugger", "patching", "add feature", "fixture"]
)
def test_keyword_needs_a_word_boundary(message: str) -> None:
    assert not labels.is_keyword_fix(commit(message))


@pytest.mark.parametrize(
    "message",
    [
        "fix and refactor",
        "fix cleanup",
        "fix: renamed var",
        "fix merge conflict",
        "bump to fix",
        'Revert "fix x"',
        "fix\n\nlong body mentions Refactoring",
    ],
)
def test_excluded_messages_are_not_fix_commits(message: str) -> None:
    assert not labels.is_keyword_fix(commit(message))


def test_bot_authors_are_not_fix_commits() -> None:
    assert not labels.is_keyword_fix(commit("fix deps", name="dependabot[bot]"))
    assert not labels.is_keyword_fix(
        commit("fix deps", email="49699333+dependabot[bot]@users.noreply.github.com")
    )
    assert not labels.is_keyword_fix(commit("fix deps", name="Renovate"))
    assert not labels.is_keyword_fix(commit("fix deps", name="release-bot"))
    assert labels.is_keyword_fix(commit("fix deps", name="Abbott"))


def test_a_commit_counts_once_per_file() -> None:
    commits = [commit("fix a", "a.py", "a.py"), commit("fix again", "a.py", day=1)]
    assert counts(commits, ["a.py", "b.py"]) == {"a.py": 2, "b.py": 0}


def test_non_fix_commits_do_not_count() -> None:
    assert counts([commit("add feature", "a.py")], ["a.py"]) == {"a.py": 0}


def test_only_eligible_cutoff_files_are_counted() -> None:
    commits = [commit("fix", "a.py", "tests/test_a.py", "README.md")]
    assert counts(commits, ["a.py", "tests/test_a.py", "README.md"]) == {"a.py": 1}


def test_renames_map_back_to_the_cutoff_path() -> None:
    commits = [
        commit("fix one", "a.py", day=0),
        commit("move", FileChange("b.py", "a.py"), day=1),
        commit("fix two", "b.py", day=2),
        commit("move again", FileChange("c.py", "b.py"), day=3),
        commit("fix three", FileChange("c.py"), day=4),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 3}


def test_a_fix_that_renames_counts_for_the_old_file() -> None:
    commits = [commit("fix and move", FileChange("b.py", "a.py"))]
    assert counts(commits, ["a.py"]) == {"a.py": 1}


def test_deleted_files_keep_their_label() -> None:
    commits = [
        commit("fix a", "a.py", day=0),
        commit("fix by delete", FileChange("a.py", deleted=True), day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 2}


def test_files_created_later_are_ignored_even_after_renames() -> None:
    commits = [
        commit("fix new", "new.py", day=0),
        commit("fix moved", FileChange("newer.py", "new.py"), day=1),
        commit("fix newer", "newer.py", day=2),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 0}


def test_a_path_recreated_after_deletion_is_a_new_file() -> None:
    commits = [
        commit("drop", FileChange("a.py", deleted=True), day=0),
        commit("fix recreated", "a.py", day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 0}


def test_commits_are_replayed_by_time_whatever_the_input_order() -> None:
    commits = [
        commit("fix two", "b.py", day=2),
        commit("move", FileChange("b.py", "a.py"), day=1),
    ]
    assert counts(commits, ["a.py"]) == {"a.py": 1}


def test_commits_with_equal_timestamps_replay_in_git_order() -> None:
    newest_first = [
        commit("fix after move", "b.py", day=0),
        commit("move", FileChange("b.py", "a.py"), day=0),
    ]
    assert counts(newest_first, ["a.py"]) == {"a.py": 1}


def test_fix_size_cap_drops_large_fixes() -> None:
    commits = [commit("fix wide", "a.py", "b.py", "c.py"), commit("fix narrow", "a.py", day=1)]
    capped = labels.build_labels(commits, ["a.py", "b.py", "c.py"], max_files=2)
    assert dict(capped.keyword_counts) == {"a.py": 1, "b.py": 0, "c.py": 0}
    assert capped.stats["fix_commits_dropped_by_cap"] == 1
    uncapped = labels.build_labels(commits, ["a.py", "b.py", "c.py"])
    assert dict(uncapped.keyword_counts) == {"a.py": 2, "b.py": 1, "c.py": 1}
    assert uncapped.stats["fix_commits_dropped_by_cap"] == 0


def test_fix_size_cap_counts_eligible_files_only() -> None:
    commits = [commit("fix", "a.py", "tests/test_a.py", "docs/x.py", "notes.md")]
    assert counts(commits, ["a.py"], max_files=1) == {"a.py": 1}


def test_renames_still_apply_when_a_commit_is_dropped_by_the_cap() -> None:
    commits = [
        commit("fix wide", FileChange("b.py", "a.py"), "c.py", day=0),
        commit("fix b", "b.py", day=1),
    ]
    assert counts(commits, ["a.py", "c.py"], max_files=1) == {"a.py": 1, "c.py": 0}


def test_stats_report_squash_and_pr_number_only_shares() -> None:
    commits = [
        commit("fix crash (#12)"),
        commit("fix parser (#13)\n\nCloses #4"),
        commit("fix loop"),
        commit("add feature (#14)"),
    ]
    stats = labels.build_labels(commits, []).stats
    assert stats["commits_in_window"] == 4
    assert stats["squash_share"] == 0.75
    assert stats["fix_commits"] == 3
    assert stats["pr_number_only_share"] == pytest.approx(1 / 3)


def test_stats_are_zero_without_commits() -> None:
    stats = labels.build_labels([], []).stats
    assert stats["squash_share"] == 0.0
    assert stats["pr_number_only_share"] == 0.0


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("fix it (#7)", True),
        ("fix it (#7) ", True),
        ("fix it", False),
        ("fix #3 (#7)", False),
        ("fix it (#7)\n\nsee https://github.com/o/r/issues/3", False),
        ("fix it (#7)\n\nbody without references", True),
    ],
)
def test_carries_only_pr_number(message: str, expected: bool) -> None:  # noqa: FBT001
    assert labels.carries_only_pr_number(commit(message)) is expected


@pytest.mark.parametrize(
    ("cutoff", "end"),
    [
        (date(2025, 1, 31), date(2025, 7, 31)),
        (date(2025, 8, 31), date(2026, 2, 28)),
        (date(2023, 8, 31), date(2024, 2, 29)),
        (date(2024, 6, 15), date(2024, 12, 15)),
    ],
)
def test_window_end_adds_six_months_clamped_to_month_end(cutoff: date, end: date) -> None:
    assert labels.window_end(cutoff) == end


def test_window_starts_the_day_after_the_cutoff_and_closes_after_its_last_day() -> None:
    cutoff = date(2024, 1, 31)
    assert labels.window_start(cutoff) == date(2024, 2, 1)
    assert not labels.window_is_closed(cutoff, date(2024, 7, 31))
    assert labels.window_is_closed(cutoff, date(2024, 8, 1))


def fix_of_size(size: int, day: int = 0) -> CommitChange:
    return commit(f"fix {size}", *(f"f{day}_{i}.py" for i in range(size)), day=day)


def test_fix_sizes_count_eligible_files_of_keyword_fixes_only() -> None:
    commits = [
        commit("fix a", "a.py", "tests/test_a.py", "notes.md"),
        commit("fix docs only", "README.md"),
        commit("add feature", "a.py", "b.py"),
        commit("fix and refactor", "a.py"),
        commit("fix bot", "a.py", name="renovate[bot]"),
    ]
    assert labels.fix_sizes(commits) == [1]


@pytest.mark.parametrize(
    ("sizes", "expected"),
    [
        ([], None),
        ([7], 7),
        (list(range(1, 11)), 9),  # ceil(0.9 * 10) = 9th smallest
        (list(range(1, 12)), 10),  # ceil(0.9 * 11) = 10th smallest
        ([1] * 9 + [50], 1),
        ([50, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 1),  # unsorted input
        ([1] * 8 + [50, 50], 50),
    ],
)
def test_percentile_cap_is_the_nearest_rank_90th(sizes: list[int], expected: int | None) -> None:
    assert labels.percentile_cap(sizes) == expected


def test_percentile_cap_keeps_at_least_the_percentile_of_fixes() -> None:
    sizes = [1, 1, 2, 3, 3, 4, 8, 9, 30, 40, 41, 100, 2, 2, 5, 6, 7, 1, 1, 12]
    cap = labels.percentile_cap(sizes)
    assert cap is not None
    assert sum(size <= cap for size in sizes) >= 0.9 * len(sizes)


def test_cap_report_runs_each_cap_in_order() -> None:
    commits = [fix_of_size(1, 0), fix_of_size(2, 1), fix_of_size(3, 2)]
    files = [f"f{day}_{i}.py" for day in range(3) for i in range(day + 1)]
    report = labels.cap_report(commits, files, [2, None])
    assert [
        (r.max_files, r.fix_commits_dropped, r.files_labeled, r.label_total) for r in report
    ] == [
        (2, 1, 3, 3),
        (None, 0, 6, 6),
    ]


def test_sample_is_seeded_and_ignores_input_order() -> None:
    commits = [fix_of_size(1, day) for day in range(40)]
    first = labels.sample_fixes(commits, 5)
    assert len(first) == labels.SAMPLE_SIZE
    assert len({c.sha for c in first}) == labels.SAMPLE_SIZE
    assert labels.sample_fixes(list(reversed(commits)), 5) == first
    assert labels.sample_fixes(commits, 5, seed=1) != first


def test_sample_draws_only_fixes_that_count_under_the_cap() -> None:
    commits = [
        fix_of_size(1, 0),
        fix_of_size(3, 1),
        commit("add feature", "a.py", day=2),
        commit("fix docs", "README.md", day=3),
    ]
    assert labels.sample_fixes(commits, 2) == [commits[0]]


def test_a_small_pool_is_sampled_whole() -> None:
    commits = [fix_of_size(1, day) for day in range(3)]
    assert sorted(c.sha for c in labels.sample_fixes(commits, 1)) == sorted(c.sha for c in commits)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("fix it (#7)", ()),
        ("fix #3 (#7)", ("#3",)),
        ("fix it\n\nCloses #4 and #4, see #5", ("#4", "#5")),
        ("fix it\n\nhttps://github.com/o/r/issues/9", ("/issues/9",)),
        ("fix it", ()),
    ],
)
def test_issue_references_leave_out_the_pr_suffix(message: str, expected: tuple[str, ...]) -> None:
    assert labels.issue_references(commit(message)) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("handle it (#7)", ()),
        ("handle it, closes #3 (#7)", (3,)),
        ("handle it\n\nSee https://github.com/o/r/issues/9 and #12", (9, 12)),
        ("handle it, bug 15", ()),
    ],
)
def test_linked_issues_are_numbers_never_bare_or_the_pr_suffix(
    message: str, expected: tuple[int, ...]
) -> None:
    assert labels.linked_issues(commit(message)) == expected


def test_a_tracker_fix_links_a_closed_bug_whatever_the_wording() -> None:
    assert labels.is_tracker_fix(commit("handle empty input, closes #7"), {7})
    assert not labels.is_tracker_fix(commit("handle empty input, closes #8"), {7})
    assert not labels.is_tracker_fix(commit("handle empty input (#7)"), {7})
    assert not labels.is_tracker_fix(commit("handle empty input, bug 7"), {7})


@pytest.mark.parametrize("message", ["refactor parser, closes #7", 'Revert "x", closes #7'])
def test_a_tracker_fix_keeps_the_message_exclusions(message: str) -> None:
    assert not labels.is_tracker_fix(commit(message), {7})


def test_a_bot_is_never_a_tracker_fix() -> None:
    assert not labels.is_tracker_fix(commit("handle it, closes #7", name="renovate[bot]"), {7})


def test_the_primary_label_counts_tracker_fixes_apart_from_the_keyword_set() -> None:
    commits = [
        commit("fix a crash", "a.py", day=0),
        commit("handle empty input, closes #7", "b.py", day=1),
        commit("fix it, closes #7", "a.py", "b.py", day=2),
    ]

    built = labels.build_labels(commits, ["a.py", "b.py"], closed_bugs={7})

    assert dict(built.counts) == {"a.py": 1, "b.py": 2}
    assert dict(built.keyword_counts) == {"a.py": 2, "b.py": 1}
    assert built.stats["tracker_fix_commits"] == 2


def test_without_closed_bugs_the_primary_label_is_all_zero() -> None:
    built = labels.build_labels([commit("fix a crash", "a.py")], ["a.py"])

    assert dict(built.counts) == {"a.py": 0}
    assert dict(built.keyword_counts) == {"a.py": 1}


def test_the_cap_drops_wide_tracker_fixes_and_reports_them_separately() -> None:
    commits = [commit("handle it, closes #7", "a.py", "b.py", "c.py")]

    built = labels.build_labels(commits, ["a.py", "b.py", "c.py"], max_files=2, closed_bugs={7})

    assert sum(built.counts.values()) == 0
    assert built.stats["tracker_fix_commits_dropped_by_cap"] == 1
    assert built.stats["fix_commits_dropped_by_cap"] == 0


def test_tracker_fixes_follow_renames_like_keyword_fixes() -> None:
    commits = [
        commit("move a", FileChange("b.py", old_path="a.py"), day=0),
        commit("handle it, closes #7", "b.py", day=1),
    ]

    assert dict(labels.build_labels(commits, ["a.py"], closed_bugs={7}).counts) == {"a.py": 1}


def test_variants_cover_every_cap_and_both_windows() -> None:
    fixes = [commit("fix a", "a.py", day=10), commit("fix b", "a.py", day=100)]
    later = [commit("fix c", "a.py", day=250)]
    got = labels.build_variants(
        fixes,
        later,
        ["a.py"],
        max_files=None,
        closed_bugs=set(),
        cutoff=date(2024, 1, 31),
        long_window_closed=True,
    )
    assert set(got) == {"cap-5", "cap-10", "cap-20", "cap-none", "window-3m", "window-12m"}


def test_variants_use_a_shorter_and_a_longer_window_than_the_primary() -> None:
    # START is 2024-02-01 and the Cutoff date is 2024-01-31, so day 10 is inside 3 months,
    # day 100 is after them, and day 250 is after the 6-month window.
    fixes = [commit("fix a", "a.py", day=10), commit("fix b", "a.py", day=100)]
    later = [commit("fix c", "a.py", day=250)]
    got = labels.build_variants(
        [replace_message(c) for c in fixes],
        [replace_message(c) for c in later],
        ["a.py"],
        max_files=None,
        closed_bugs={7},
        cutoff=date(2024, 1, 31),
        long_window_closed=True,
    )
    assert got["window-3m"] == {"a.py": 1}
    assert got["window-12m"] == {"a.py": 3}
    assert got["cap-none"] == {"a.py": 2}


def replace_message(c: CommitChange) -> CommitChange:
    return dataclasses.replace(c, message=f"{c.message} (fixes #7)")


def test_the_twelve_month_variant_is_left_out_while_that_window_is_open() -> None:
    got = labels.build_variants(
        [],
        [],
        ["a.py"],
        max_files=None,
        closed_bugs=set(),
        cutoff=date(2024, 1, 31),
        long_window_closed=False,
    )
    assert "window-12m" not in got
    assert "window-3m" in got


def test_a_closed_twelve_month_window_with_no_later_commits_equals_the_six_month_counts() -> None:
    fixes = [replace_message(commit("fix a", "a.py", day=10))]
    got = labels.build_variants(
        fixes,
        [],
        ["a.py"],
        max_files=None,
        closed_bugs={7},
        cutoff=date(2024, 1, 31),
        long_window_closed=True,
    )
    assert got["window-12m"] == {"a.py": 1}


def test_a_cap_variant_drops_the_wide_fix() -> None:
    wide = commit("fix wide (fixes #7)", "a.py", "b.py", "c.py", day=5)
    got = labels.build_variants(
        [wide],
        [],
        ["a.py", "b.py", "c.py"],
        max_files=None,
        closed_bugs={7},
        cutoff=date(2024, 1, 31),
        long_window_closed=True,
    )
    assert got["cap-none"]["a.py"] == 1
    assert got["cap-5"]["a.py"] == 1
    narrow = labels.build_variants(
        [wide],
        [],
        ["a.py", "b.py", "c.py"],
        max_files=2,
        closed_bugs={7},
        cutoff=date(2024, 1, 31),
        long_window_closed=True,
    )
    assert narrow["window-3m"]["a.py"] == 0
