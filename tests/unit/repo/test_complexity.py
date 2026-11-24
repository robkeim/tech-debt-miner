import pytest

from tech_debt_miner.repo.complexity import Complexity, file_complexity

pytestmark = pytest.mark.unit

TWO_FUNCTIONS = b"""
def a(x):
    if x:
        return 1
    return 2


class C:
    def m(self, y):
        for i in y:
            if i:
                return i
        return 0
"""


def test_sums_cyclomatic_complexity_over_functions_and_methods() -> None:
    assert file_complexity("a.py", TWO_FUNCTIONS) == Complexity(2 + 3, zero=False)


def test_a_file_with_no_functions_is_zero() -> None:
    assert file_complexity("a.py", b"if True:\n    x = 1\n") == Complexity(0, zero=True)


def test_an_empty_file_is_zero() -> None:
    assert file_complexity("a.py", b"") == Complexity(0, zero=True)


def test_undecodable_content_is_zero() -> None:
    assert file_complexity("a.py", b"\xff\xfe\x00def f(): pass") == Complexity(0, zero=True)
