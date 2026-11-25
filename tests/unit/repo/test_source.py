import pytest

from tech_debt_miner.repo.source import HEAD_LINES, file_head, file_outline
from tech_debt_miner.types import OutlineEntry

pytestmark = pytest.mark.unit


def test_a_short_file_is_shown_whole() -> None:
    assert file_head(b"a = 1\nb = 2\n") == ("a = 1\nb = 2", 0)


def test_a_long_file_is_cut_at_the_head_and_the_rest_is_counted() -> None:
    content = b"x\n" * (HEAD_LINES + 7)

    head, truncated = file_head(content)

    assert len(head.splitlines()) == HEAD_LINES
    assert truncated == 7


def test_lines_split_on_crlf_and_cr_like_loc() -> None:
    assert file_head(b"a\r\nb\rc\n") == ("a\nb\nc", 0)


def test_a_file_of_exactly_the_head_size_is_not_truncated() -> None:
    assert file_head(b"x\n" * HEAD_LINES)[1] == 0


def test_undecodable_bytes_are_replaced() -> None:
    assert file_head(b"a = '\xff'\n")[0] == "a = '\N{REPLACEMENT CHARACTER}'"


def test_an_empty_file_has_an_empty_head() -> None:
    assert file_head(b"") == ("", 0)


def test_the_outline_lists_classes_functions_and_methods_with_line_numbers() -> None:
    source = (
        b"import os\n"
        b"\n"
        b"def top():\n"
        b"    def inner():\n"
        b"        pass\n"
        b"\n"
        b"@decorator\n"
        b"class A:\n"
        b"    x = 1\n"
        b"    def method(self): ...\n"
        b"    async def async_method(self): ...\n"
        b"    class Nested:\n"
        b"        def deep(self): ...\n"
        b"\n"
        b"async def atop(): ...\n"
    )

    assert file_outline(source) == (
        OutlineEntry("function", "top", 3, 0),
        OutlineEntry("class", "A", 8, 0),
        OutlineEntry("function", "method", 10, 1),
        OutlineEntry("function", "async_method", 11, 1),
        OutlineEntry("class", "Nested", 12, 1),
        OutlineEntry("function", "atop", 15, 0),
    )


@pytest.mark.parametrize("content", [b"def broken(:\n", b"x = 1\x00\n", b"", b"# only a comment\n"])
def test_a_file_that_does_not_parse_or_has_no_definitions_has_an_empty_outline(
    content: bytes,
) -> None:
    assert file_outline(content) == ()


def test_invalid_escapes_do_not_raise_warnings() -> None:
    assert file_outline(b"def f():\n    return '\\d'\n") == (OutlineEntry("function", "f", 1, 0),)
