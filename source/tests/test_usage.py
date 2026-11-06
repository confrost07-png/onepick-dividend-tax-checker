"""이용 통계(횟수만 세기) 테스트: 정해 둔 사건만 세는지. 시연판 서버에는 아직 연결하지 않음."""
import pytest

from core import usage


def test_counts_only_known_events():
    c = usage.UsageCounter()
    c.record(usage.START)
    c.record(usage.START)
    c.record(usage.CONSULT)
    assert c.snapshot() == {usage.START: 2, usage.COMPLETE: 0, usage.CONSULT: 1}
    with pytest.raises(ValueError):
        c.record("C사 300주")  # 입력값 같은 것은 세지 않는다


def test_snapshot_is_a_copy_and_reset_clears():
    c = usage.UsageCounter()
    c.record(usage.COMPLETE)
    snap = c.snapshot()
    snap[usage.COMPLETE] = 99
    assert c.snapshot()[usage.COMPLETE] == 1
    c.reset()
    assert set(c.snapshot().values()) == {0}
