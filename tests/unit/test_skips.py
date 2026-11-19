import pytest

from support.skips import SKIP_MARKERS, SkipMarker, skip_errors

pytestmark = pytest.mark.unit


def errors_for(name: str, *args: object, **kwargs: object) -> list[str]:
    return skip_errors([SkipMarker("t::x", name, args, kwargs)])


@pytest.mark.parametrize("name", SKIP_MARKERS)
def test_bare_marker_is_reported(name: str) -> None:
    assert "needs a reason" in errors_for(name)[0]


@pytest.mark.parametrize("name", SKIP_MARKERS)
def test_empty_reason_is_reported(name: str) -> None:
    assert "needs a reason" in errors_for(name, reason="  ")[0]


@pytest.mark.parametrize("name", SKIP_MARKERS)
def test_reason_without_issue_is_reported(name: str) -> None:
    assert "must link an issue" in errors_for(name, reason="flaky on CI")[0]


@pytest.mark.parametrize("name", SKIP_MARKERS)
def test_issue_number_passes(name: str) -> None:
    assert errors_for(name, reason="blocked by #44") == []


def test_issue_url_passes() -> None:
    reason = "see https://github.com/robkeim/tech-debt-miner/issues/44"
    assert errors_for("skip", reason=reason) == []


def test_skip_takes_reason_positionally() -> None:
    assert errors_for("skip", "blocked by #44") == []
    assert "must link an issue" in errors_for("skip", "later")[0]


def test_skipif_condition_is_not_a_reason() -> None:
    assert "needs a reason" in errors_for("skipif", "sys.platform == 'win32'")[0]
    assert errors_for("skipif", True, reason="windows only, #44") == []  # noqa: FBT003 - mirrors the marker's call shape


def test_xfail_condition_is_not_a_reason() -> None:
    assert "needs a reason" in errors_for("xfail", "must link #44")[0]


def test_hash_without_digits_is_not_an_issue() -> None:
    assert "must link an issue" in errors_for("skip", reason="see #abc")[0]


def test_each_violation_is_reported() -> None:
    markers = [SkipMarker("a", "skip", (), {}), SkipMarker("b", "xfail", (), {"reason": "#1"})]
    assert len(skip_errors(markers)) == 1
