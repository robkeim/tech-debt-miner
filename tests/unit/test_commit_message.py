import pytest

from gate.commit_message import strip_comments, validate_message, validate_title

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "title",
    [
        "feat: add ranking",
        "fix(rank): handle empty input",
        "feat(rank)!: drop the legacy scorer",
        "chore(deps): bump actions/checkout from 6 to 7",
        "docs: record agent workflow decisions (#12)",
        "ci: 2x faster cache",
        "revert: undo the cutoff change",
        "fix: " + "a" * 72,
    ],
)
def test_valid_titles(title: str) -> None:
    assert validate_title(title) == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("add ranking", "header must look like"),
        ("Feat: add ranking", "header must look like"),
        ("feat add ranking", "header must look like"),
        ("style: reformat", "type `style` is not one of"),
        ("wip: later", "type `wip` is not one of"),
        ("feat(Rank): add ranking", "scope `Rank` must be a short lowercase noun"),
        ("feat(): add ranking", "scope `` must be a short lowercase noun"),
        ("feat: Add ranking", "lowercase after the prefix"),
        ("feat: add ranking.", "must not end with a period"),
        ("feat:  add ranking", "leading or trailing whitespace"),
        ("feat: ", "subject must not be empty"),
        ("fix: " + "a" * 73, "subject is 73 characters; the limit is 72"),
        ("feat: add\nranking", "single line"),
    ],
)
def test_invalid_titles(title: str, expected: str) -> None:
    errors = validate_title(title)
    assert any(expected in error for error in errors), errors


def test_message_with_body_and_trailer_is_valid() -> None:
    message = (
        "fix(rank): handle empty input\n"
        "\n"
        "An empty file list used to raise. Return an empty ranking instead.\n"
        "\n"
        "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n"
    )
    assert validate_message(message) == []


def test_long_trailer_is_exempt_from_the_wrap() -> None:
    trailer = "BREAKING CHANGE: " + "word " * 30
    assert validate_message(f"feat!: change it\n\n{trailer}") == []


def test_prose_that_looks_like_a_label_is_not_a_trailer() -> None:
    errors = validate_message("fix: x\n\nNote: " + "a" * 70)
    assert errors == ["body line 3 is 76 characters; wrap at 72"]


def test_long_body_line_is_reported() -> None:
    errors = validate_message("fix: x\n\n" + "a" * 73)
    assert errors == ["body line 3 is 73 characters; wrap at 72"]


def test_missing_blank_line_is_reported() -> None:
    errors = validate_message("fix: x\nbody starts too early")
    assert errors == ["leave a blank line between the header and the body"]


def test_header_errors_surface_through_validate_message() -> None:
    assert validate_message("nonsense") != []


def test_empty_message_is_reported() -> None:
    assert validate_message("# only a comment\n") == ["message is empty"]


def test_git_comments_and_scissors_are_ignored() -> None:
    message = (
        "fix: x\n"
        "# Please enter the commit message\n"
        "# ------------------------ >8 ------------------------\n"
        "# " + "a" * 200 + "\n"
        "diff --git a/f b/f\n"
    )
    assert strip_comments(message) == "fix: x"
    assert validate_message(message) == []
