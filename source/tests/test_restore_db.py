"""DB 덤프 되살리기 테스트: 표 행 수 비교, 가장 새 덤프 고르기."""
from scripts.restore_db import compare, latest_dump

SNAP = {"tables": {"core.a": 3, "raw.b": 5}, "views": 2, "judgement": {"충족": 528, "미충족": 45, "보류": 65}}


def test_compare_same_is_empty():
    assert compare(SNAP, {**SNAP}) == []


def test_compare_lists_each_difference():
    got = {"tables": {"core.a": 3, "raw.b": 4, "raw.c": 1}, "views": 1, "judgement": SNAP["judgement"]}
    diffs = compare(SNAP, got)
    assert diffs == ["raw.b: 뽑을 때 5 → 되살린 뒤 4", "raw.c: 뽑을 때 None → 되살린 뒤 1", "views: 뽑을 때 2 → 되살린 뒤 1"]


def test_latest_dump_picks_newest_date(tmp_path):
    assert latest_dump(tmp_path) is None
    for name in ("onepick_20261029.dump", "onepick_20261102.dump", "other_20261231.dump"):
        (tmp_path / name).write_bytes(b"")
    assert latest_dump(tmp_path).name == "onepick_20261102.dump"
