"""이벤트 스터디(6장) 테스트: 공시일 맞추기, 누적 초과수익률, 겹치는 공시 빼기, 요약 통계."""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from core.event_study import Event, car, collect_cars, drop_overlapping, event_day_index, summarize

DAYS = [date(2025, 1, 1) + timedelta(days=i) for i in range(200)]


def test_after_close_moves_to_next_trading_day():
    assert event_day_index(DAYS, datetime(2025, 1, 5, 15, 29)) == 4
    assert event_day_index(DAYS, datetime(2025, 1, 5, 15, 30)) == 5
    holiday_days = [date(2025, 1, 3), date(2025, 1, 6)]
    assert event_day_index(holiday_days, datetime(2025, 1, 4, 10, 0)) == 1  # 휴장일 → 다음 거래일


def test_car_is_sum_of_excess_returns():
    stock = pd.Series([100.0, 110.0, 121.0, 121.0])  # +10%, +10%, 0%
    market = pd.Series([100.0, 100.0, 100.0, 100.0])
    assert car(stock, market, event_idx=1, window=2) == pytest.approx(0.20)
    assert car(stock, market, event_idx=1, window=3) is None  # 관측 기간 부족


def test_overlapping_events_of_same_company_are_dropped():
    ev = [Event("A", "배당", datetime(2025, 1, 10, 9)), Event("A", "배당", datetime(2025, 1, 20, 9)),
          Event("B", "배당", datetime(2025, 1, 20, 9))]
    kept = drop_overlapping(ev, DAYS, window=20)
    assert [(e.corp_code, e.disclosed_at.day) for e in kept] == [("A", 10), ("B", 20)]


def _prices(n_companies: int, daily_excess: float) -> tuple[pd.DataFrame, pd.Series]:
    idx = pd.to_datetime(DAYS)
    market = pd.Series(100.0, index=idx)
    cols = {f"C{i}": [100.0 * (1 + daily_excess) ** t for t in range(len(DAYS))] for i in range(n_companies)}
    return pd.DataFrame(cols, index=idx), market


def test_summary_hides_under_10_cases():
    prices, market = _prices(12, 0.001)
    events = [Event(f"C{i}", "밸류업", datetime(2025, 2, 1, 10)) for i in range(12)]
    events += [Event(f"C{i}", "배당 증가", datetime(2025, 5, 1, 10)) for i in range(9)]
    cars = collect_cars(events, prices, market, window=20)
    table = summarize(cars, window=20).set_index("공시 종류")
    assert table.loc["밸류업", "사례 수"] == 12 and bool(table.loc["밸류업", "표시"])
    assert table.loc["밸류업", "중앙값"] == pytest.approx(2.1, abs=0.01)  # 0.1%p × 21거래일
    assert table.loc["배당 증가", "사례 수"] == 9
    assert not table.loc["배당 증가", "표시"] and pd.isna(table.loc["배당 증가", "중앙값"])


# --- 실제 데이터용: 이벤트 만들기와 등급에 따른 제외 ---

from core.event_study import (COMPUTED, DPS_FLAT_DOWN, DPS_UP, EXCLUDED, KIND_HIGH_DIV, dps_events,  # noqa: E402
                              evaluate_events, kind_events, summarize_results)


def _decision(code, year, dps, day, rcept, kind="결산배당", div_type="현금배당"):
    return {"corp_code": code, "attributed_year": year, "dps_common_won": dps, "disclosed_on": day,
            "rcept_no": rcept, "div_kind": kind, "div_type": div_type}


def test_dps_events_compare_with_previous_year_and_use_first_disclosure_day():
    decisions = [
        _decision("A", 2023, 1000, "2024-02-01", "1"),
        _decision("A", 2024, 1100, "2025-02-03", "2"),
        _decision("A", 2024, 1000, "2025-02-10", "3"),  # 정정: 값은 이것(1000 = 유지), 날짜는 첫 공시
        _decision("B", 2023, 500, "2024-02-01", "4"),
        _decision("B", 2024, 600, "2025-02-05", "5"),
        _decision("B", 2024, 300, "2024-08-01", "6", kind="중간배당"),  # 결산배당만 비교
        _decision("C", 2024, 700, "2025-02-05", "7"),  # 직전 연도 없음 → 제외
    ]
    got = [(e.corp_code, e.kind, e.disclosed_at.date(), e.rcept_no) for e in dps_events(decisions)]
    assert got == [("A", DPS_FLAT_DOWN, date(2025, 2, 3), "2"), ("B", DPS_UP, date(2025, 2, 5), "5")]


def test_kind_events():
    rows = [{"corp_code": "A", "final_disclosed_on": "2026-03-03", "final_rcept_no": "9"},
            {"corp_code": None, "final_disclosed_on": "2026-03-03", "final_rcept_no": "8"}]
    assert [(e.corp_code, e.kind) for e in kind_events(rows)] == [("A", KIND_HIGH_DIV)]


def _grid():
    idx = pd.to_datetime(DAYS[:40])
    prices = pd.DataFrame({c: [100.0 * 1.01 ** t for t in range(40)] for c in "ABCD"}, index=idx)
    grades = pd.DataFrame("사용 가능", index=idx, columns=list("ABCD"))
    prices.loc[idx[12], "B"] = None
    grades.loc[idx[12], "B"] = "제외"            # 빈칸
    grades.loc[idx[12], "C"] = "제외"            # 이상 가격
    grades.loc[idx[12], "D"] = "주의"
    markets = pd.DataFrame({"KOSPI": 100.0}, index=idx)
    index_grades = pd.DataFrame({"KOSPI": "사용 가능"}, index=idx)
    return prices, grades, markets, index_grades


def test_evaluate_events_excludes_bad_windows_and_keeps_caution():
    prices, grades, markets, index_grades = _grid()
    events = [Event(c, DPS_UP, datetime(2025, 1, 11)) for c in "ABCDE"] + [Event("A", DPS_UP, datetime(2025, 2, 5))]
    market_of = {c: "KOSPI" for c in "ABCDE"}
    rows = {(r["corp_code"], r["disclosed_on"].day): r
            for r in evaluate_events(events, prices, grades, markets, index_grades, market_of, window=5)}
    a = rows[("A", 11)]
    assert a["status"] == COMPUTED and a["car"] == pytest.approx(0.06, abs=1e-9) and not a["caution"]
    assert rows[("B", 11)]["reason"].startswith("창 안에 빈칸")
    assert rows[("C", 11)]["reason"].startswith("창 안에 이상 가격")
    assert rows[("D", 11)]["status"] == COMPUTED and rows[("D", 11)]["caution"]
    assert rows[("E", 11)]["reason"] == "주가 미수집"
    assert rows[("A", 5)]["reason"] == "관측 기간 부족"  # 2025-02-05 = 35번째 날, 35+5 ≥ 40
    table = summarize_results(list(rows.values()), min_cases=1).set_index("공시 종류")
    assert set(table["기간"]) == {"2025년까지"}
    assert table.loc[DPS_UP, "사례 수"] == 2 and table.loc[DPS_UP, "주의 포함"] == 1 and table.loc[DPS_UP, "제외"] == 4
    assert {r["status"] for r in rows.values()} == {COMPUTED, EXCLUDED}


def test_overlap_is_checked_within_the_same_kind_and_recorded():
    prices, grades, markets, index_grades = _grid()
    events = [Event("A", DPS_UP, datetime(2025, 1, 5), "1"), Event("A", DPS_UP, datetime(2025, 1, 7), "2"),
              Event("A", KIND_HIGH_DIV, datetime(2025, 1, 7), "3")]
    rows = {r["rcept_no"]: r for r in evaluate_events(events, prices, grades, markets, index_grades, {"A": "KOSPI"}, 5)}
    assert rows["1"]["status"] == COMPUTED and rows["3"]["status"] == COMPUTED  # 종류가 다르면 겹쳐도 남김
    assert rows["2"]["reason"] == "같은 회사 앞 공시의 관측 기간과 겹침"


def test_curve_rows_end_at_car_and_hide_small_groups():
    from core.event_study import curve_rows

    prices, grades, markets, index_grades = _grid()
    events = [Event(c, DPS_UP, datetime(2025, 1, 11), c) for c in "AD"]
    rows = evaluate_events(events, prices, grades, markets, index_grades, {c: "KOSPI" for c in "AD"}, window=5)
    curve = curve_rows(rows, prices, markets, window=5, min_cases=2)
    assert [c["day"] for c in curve] == [0, 1, 2, 3, 4, 5]
    assert curve[0]["median_pct"] == pytest.approx(1.0) and curve[-1]["median_pct"] == pytest.approx(6.0)
    assert curve[-1]["median_pct"] == pytest.approx(rows[0]["car"] * 100)
    assert curve[0]["period"] == "2025년까지" and curve[0]["n_cases"] == 2
    assert all(c["median_pct"] is None for c in curve_rows(rows, prices, markets, window=5, min_cases=3))


def test_ex_dividend_day_is_trading_day_before_record_or_last_before_holiday():
    from core.event_study import ex_dividend_index

    days = [date(2024, 12, 27), date(2024, 12, 30), date(2025, 3, 28), date(2025, 3, 31)]
    assert days[ex_dividend_index(days, date(2024, 12, 31))] == date(2024, 12, 30)  # 기준일 휴장 → 마지막 거래일
    assert days[ex_dividend_index(days, date(2025, 3, 31))] == date(2025, 3, 28)    # 기준일 거래일 → 직전 거래일


def test_dps_events_by_basis_use_agm_and_ex_dates():
    from core.event_study import BASIS_AGM, BASIS_EX

    decisions = [dict(_decision("A", 2023, 1000, "2024-02-01", "1"), record_date="2023-12-31", agm_date="2024-03-20"),
                 dict(_decision("A", 2024, 1100, "2025-02-03", "2"), record_date="2025-03-31", agm_date="2025-03-21")]
    days = [date(2025, 3, 21), date(2025, 3, 28), date(2025, 3, 31)]
    agm = dps_events(decisions, BASIS_AGM)
    ex = dps_events(decisions, BASIS_EX, days)
    assert agm[0].disclosed_at.date() == date(2025, 3, 21) and agm[0].basis == BASIS_AGM and agm[0].dps == 1100
    assert ex[0].disclosed_at.date() == date(2025, 3, 28) and ex[0].record_date == date(2025, 3, 31)


def test_capital_events_kinds_and_first_disclosure_day():
    from core.event_study import capital_events

    cap = [{"rcept_no": "20240110000002", "kind": "유상증자", "corp_code": "A", "rcept_dt": date(2024, 1, 10),
            "method": "제3자배정증자", "version": "API 최종본", "check_result": ""},
           {"rcept_no": "20240105000001", "kind": "유상증자", "corp_code": "A", "rcept_dt": date(2024, 1, 5),
            "method": None, "version": "앞선 판", "check_result": "정정 묶음의 최종본 20240110000002에 값이 있음"},
           {"rcept_no": "20240301000003", "kind": "감자", "corp_code": "B", "rcept_dt": date(2024, 3, 1),
            "method": "자기주식 소각", "version": "원문 최종본", "check_result": ""}]
    split = [{"rcept_no": "20240401000004", "kind": "주식분할", "corp_code": "C", "rcept_dt": date(2024, 4, 1)}]
    got = [(e.corp_code, e.kind, e.disclosed_at.date()) for e in capital_events(cap, split)]
    assert got == [("A", "유상증자(제3자배정)", date(2024, 1, 5)), ("B", "감자(자기주식 소각)", date(2024, 3, 1)),
                   ("C", "주식분할", date(2024, 4, 1))]


def test_total_return_adds_dividend_on_ex_day_and_flags_capital_overlap():
    prices, grades, markets, index_grades = _grid()
    days = [d.date() for d in prices.index]
    record = days[14]  # 배당락일 = days[13], 창(이벤트일 days[10] ~ +5) 안
    e = Event("A", DPS_UP, datetime.combine(days[10], datetime.min.time()), "1", dps=5.0, record_date=record)
    rows = evaluate_events([e], prices, grades, markets, index_grades, {"A": "KOSPI"}, 5,
                           capital_dates={"A": [(days[12], "9")]})
    r = rows[0]
    assert r["car_total"] == pytest.approx(r["car"] + 5.0 / prices["A"].iloc[12])
    assert r["overlap_capital"]
    table = summarize_results(rows, min_cases=1)
    assert set(zip(table["수익률"], table["표본"])) == {("주가만", "전체"), ("주가만", "자본 변동 겹침 제외"),
                                                    ("배당 포함", "전체"), ("배당 포함", "자본 변동 겹침 제외")}
    assert table[(table["표본"] == "자본 변동 겹침 제외")]["사례 수"].tolist() == [0, 0]
