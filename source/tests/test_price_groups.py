"""무리별 주가 비교 테스트: 시작일·확인일 고르기와 누적 수익률."""
from datetime import date

import pytest

from core import group_compare as gc
from core import price_groups as pg

D = date


def test_cumulative_uses_first_day_on_or_after_start_and_last_day_before_checkpoint():
    s = [(D(2025, 6, 30), 50.0), (D(2025, 7, 2), 100.0), (D(2025, 7, 31), 110.0), (D(2025, 8, 29), 90.0)]
    assert pg.cumulative(s, D(2025, 7, 1), [D(2025, 7, 31), D(2025, 8, 31), D(2025, 7, 1)]) == [
        pytest.approx(10), pytest.approx(-10), None]


def test_cumulative_no_data_after_start():
    assert pg.cumulative([(D(2025, 6, 30), 50.0)], D(2025, 7, 1), [D(2025, 7, 31)]) == [None]


def test_month_ends():
    assert pg.month_ends(D(2025, 11, 3), D(2026, 1, 20)) == [D(2025, 11, 30), D(2025, 12, 31), D(2026, 1, 20)]


def test_mean_diff():
    d = gc.mean_diff([1, 3], [0, 0], reps=20)
    assert d.diff == 2 and d.n_a == 2


def test_adjusted_diff_removes_control_effect():
    # y = 5×size, 무리 1은 size가 크다 → 단순 차이는 크지만 size가 같으면 차이 0
    size = [1, 2, 3, 4, 5, 6, 7, 8]
    group = [0, 0, 0, 0, 1, 1, 1, 1]
    y = [5 * s for s in size]
    est, lo, hi, n = gc.adjusted_diff(y, group, [[s] for s in size], reps=50)
    assert est == pytest.approx(0, abs=1e-9) and n == 8


def test_equal_weight_index():
    days = [D(2026, 1, 1), D(2026, 1, 2), D(2026, 1, 3)]
    idx = pg.equal_weight_index({"a": {days[0]: 100, days[1]: 110, days[2]: 110}, "b": {days[0]: 100, days[1]: 90}}, days)
    assert idx[days[1]] == pytest.approx(1.0) and idx[days[2]] == pytest.approx(1.0)


def test_abnormal_return():
    days = [D(2026, 1, d) for d in range(1, 8)]
    stock = {d: 100 + 10 * i for i, d in enumerate(days)}
    bench = {d: 1.0 for d in days}
    # 공시 1월 3일(0일) → 전날(1월 2일, 110)부터 2일 뒤(1월 5일, 140)
    assert pg.abnormal_return(stock, bench, days, D(2026, 1, 3), 2) == pytest.approx((140 / 110 - 1) * 100)
    assert pg.abnormal_return(stock, bench, days, D(2026, 1, 1), 2) is None
    assert pg.abnormal_return(stock, bench, days, D(2026, 1, 6), 5) is None


def test_cluster_mean_diff_wider_when_values_move_together_within_cluster():
    # 묶음 안 값이 똑같이 움직이면, 회사 따로 뽑을 때보다 묶음째 뽑을 때 오차 범위가 넓다
    a = [5.0] * 10 + [-5.0] * 10
    ca = ["d1"] * 10 + ["d2"] * 10
    plain = gc.mean_diff(a, [0.0], reps=500)
    clus = gc.cluster_mean_diff(a, [], ca, [], reps=500)
    assert clus.diff == pytest.approx(0) and clus.n_a == 20 and clus.n_b == 0
    assert clus.high - clus.low > plain.high - plain.low


def test_cluster_mean_diff_shared_clusters_cancel_common_shock():
    # 같은 날 두 무리가 함께 출렁이면 차이는 늘 2라서 오차 범위가 0
    a = [12.0, 2.0, -8.0]
    b = [10.0, 0.0, -10.0]
    c = ["d1", "d2", "d3"]
    d = gc.cluster_mean_diff(a, b, c, c, reps=200)
    assert d.diff == pytest.approx(2) and d.low == pytest.approx(2) and d.high == pytest.approx(2)


def test_cluster_mean_diff_skips_none():
    d = gc.cluster_mean_diff([1.0, None, 3.0], [], ["x", "y", "z"], [], reps=50)
    assert d.n_a == 2 and d.a == pytest.approx(2)
