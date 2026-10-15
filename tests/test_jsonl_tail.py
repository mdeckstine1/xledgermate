"""Bounded JSONL tail must not slurp the whole file."""

from __future__ import annotations

from pathlib import Path

from utils.jsonl_tail import tail_json_objects, tail_lines


def test_tail_lines_returns_last_n(tmp_path: Path) -> None:
    path = tmp_path / "big.jsonl"
    path.write_text("\n".join(f'{{"n":{i}}}' for i in range(50)) + "\n", encoding="utf-8")
    lines = tail_lines(path, 5)
    assert len(lines) == 5
    assert lines[-1] == '{"n":49}'
    assert lines[0] == '{"n":45}'


def test_tail_json_objects(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"a":1}\nnot json\n{"a":2}\n', encoding="utf-8")
    rows = tail_json_objects(path, 10)
    assert rows == [{"a": 1}, {"a": 2}]


def test_tail_empty(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    assert tail_json_objects(path, 10) == []
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert tail_lines(empty, 3) == []
