"""KRX 주가·지수 사용 등급: 상한 초과 등락, 같은 가격 연속 구간의 경계값."""
import datetime as dt

import pandas as pd

from core import price_quality as pq


def wide(values: dict[str, list], start="2026-01-02") -> pd.DataFrame:
    n = len(next(iter(values.values())))
    days = pd.bdate_range(start, periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({k: [None if v is None else str(v) for v in vs] for k, vs in values.items()},
                        index=pd.Index(days, name="날짜"))


def test_jump_over_limit_is_excluded_but_limit_move_is_not():
    rows = pq.jump_flags(wide({"126380": [1000, 1300, 1000, 1700, 1000]}))
    # 1000→1300(+30%)·1300→1000(−23%)은 정상, 1000→1700(+70%)·1700→1000(−41%)은 제외
    assert [(r["trade_date"], r["grade"]) for r in rows] == [
        (dt.date(2026, 1, 7), pq.EXCLUDE), (dt.date(2026, 1, 8), pq.EXCLUDE)]
    assert rows[0]["corp_code"] == "00126380" and rows[0]["detail"].startswith("+70.0%")


def test_jump_is_measured_from_last_observed_price():
    rows = pq.jump_flags(wide({"00000001": [1000, None, None, 400]}))
    assert len(rows) == 1 and rows[0]["trade_date"] == dt.date(2026, 1, 7)


def test_tick_rounding_tolerance():
    assert pq.jump_flags(wide({"00000001": [10000, 13040]})) == []      # +30.4%
    assert len(pq.jump_flags(wide({"00000001": [10000, 13060]}))) == 1  # +30.6%


def test_stale_run_boundaries():
    def flags(n):
        return pq.stale_flags(wide({"00000001": [900] + [1000] * n + [1100]}))

    assert flags(4) == []
    assert {r["grade"] for r in flags(5)} == {pq.CAUTION} and len(flags(5)) == 5
    assert {r["grade"] for r in flags(19)} == {pq.CAUTION}
    assert {r["grade"] for r in flags(20)} == {pq.EXCLUDE} and len(flags(20)) == 20
    assert "20거래일 연속" in flags(20)[0]["detail"]


def test_stale_run_counts_observed_days_across_blanks():
    rows = pq.stale_flags(wide({"00000001": [1000, 1000, None, 1000, 1000, 1000]}))
    assert len(rows) == 5  # 빈칸(거래정지)은 건너뛰고 관측일만 센다


def test_index_flags_only_unverified_period():
    market = wide({"KOSPI 종가": [2000, 2300, 2310]}, start="2025-12-30")
    rows = pq.index_flags(market)
    assert rows == []  # 2025-12-31 +15%는 검증된 기간
    market = wide({"KOSPI 종가": [2000, 2300, 2000]}, start="2026-01-01")
    rows = pq.index_flags(market)
    assert [(r["market"], r["trade_date"]) for r in rows] == [("KOSPI", dt.date(2026, 1, 2)), ("KOSPI", dt.date(2026, 1, 5))]
    assert {r["grade"] for r in rows} == {pq.CAUTION}
