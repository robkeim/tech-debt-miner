from pathlib import Path

import pytest

from tech_debt_miner import jsonio

pytestmark = pytest.mark.unit


def test_write_json_round_trips_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "a.json"
    jsonio.write_json(path, {"b": 1, "a": [1, 2]})
    assert path.read_text() == '{"a":[1,2],"b":1}\n'
    assert [p.name for p in path.parent.iterdir()] == ["a.json"]


def test_failed_write_keeps_old_file_and_cleans_up(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    jsonio.write_json(path, {"v": 1})
    with pytest.raises(TypeError):
        jsonio.write_json(path, {"v": object()})
    assert jsonio.read_json(path) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_jsonl_appends_lines(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    jsonio.append_jsonl(path, {"n": 1})
    jsonio.append_jsonl(path, {"n": 2})
    assert jsonio.read_jsonl(path) == [{"n": 1}, {"n": 2}]


def test_jsonl_drops_torn_last_line(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text('{"n":1}\n{"n":')
    assert jsonio.read_jsonl(path) == [{"n": 1}]


def test_append_after_a_crash_starts_a_clean_line(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text('{"n":1}\n{"n":')
    jsonio.append_jsonl(path, {"n": 2})
    assert jsonio.read_jsonl(path) == [{"n": 1}, {"n": 2}]
