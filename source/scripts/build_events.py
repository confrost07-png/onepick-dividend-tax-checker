"""배당 결정·KIND 고배당·증자·감자·분할·병합 공시 → 이벤트 스터디(CAR) → core.core_event_car, core_event_summary, core_event_curve.

배당 결정은 기준일 셋(공시일·주주총회 결의일·배당락일), 수익률 둘(주가만·배당 포함), 표본 둘(전체·자본 변동 겹침 제외)로
나눠 집계한다(source/core/event_study.py).

실행: .venv/bin/python -m scripts.build_events [--url ...]
scripts.load_raw, scripts.build_core, scripts.load_prices를 먼저 돌려야 한다. 결과 표는 매번 비우고 다시 채운다.
주가 사용 등급이 '제외'인 날이 창 안에 있는 이벤트는 빼고, 사유를 남긴다.
"""
import argparse

import pandas as pd

from core import db
from core import event_study as es

ENGINE = "source/core/event_study.py"
MARKET_NAMES = {"코스피": "KOSPI", "코스닥": "KOSDAQ"}


def _wide(rows: list[dict], key: str, value: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    out = df.pivot(index="trade_date", columns=key, values=value).sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def build_events(url: str) -> pd.DataFrame:
    with db.connect(url) as conn:
        db.apply_schema(conn)
        daily =db.fetch_dicts(conn, "SELECT corp_code, trade_date, close_adj::float AS close, grade FROM core.v_price_daily")
        index = db.fetch_dicts(conn, "SELECT market, trade_date, close::float AS close, grade FROM core.v_index_daily")
        decisions = db.fetch_dicts(conn, "SELECT * FROM raw.dividend_decision")
        kind = db.fetch_dicts(conn, "SELECT k.corp_code, k.final_disclosed_on, k.final_rcept_no FROM raw.kind_list k")
        company = db.fetch_dicts(conn, "SELECT corp_code, market FROM core.core_company")
        capital = db.fetch_dicts(conn, "SELECT * FROM raw.dart_capital_event")
        splits = db.fetch_dicts(conn, "SELECT * FROM raw.dart_split_merge")

        prices, grades = _wide(daily, "corp_code", "close"), _wide(daily, "corp_code", "grade")
        markets, index_grades = _wide(index, "market", "close"), _wide(index, "market", "grade")
        markets, index_grades = markets.reindex(prices.index), index_grades.reindex(prices.index)
        market_of = {c["corp_code"]: MARKET_NAMES.get(c["market"]) for c in company}
        for d in decisions:
            d["disclosed_on"] = str(d["disclosed_on"]) if d["disclosed_on"] else None
        days = [d.date() for d in prices.index]
        cap_events = es.capital_events(capital, splits)
        capital_dates = {}
        for e in cap_events:
            capital_dates.setdefault(e.corp_code, []).append((e.disclosed_at.date(), e.rcept_no))
        events = (es.dps_events(decisions) + es.dps_events(decisions, es.BASIS_AGM)
                  + es.dps_events(decisions, es.BASIS_EX, days) + es.kind_events(kind) + cap_events)

        rows, curve = [], []
        for window in es.WINDOWS:
            found = es.evaluate_events(events, prices, grades, markets, index_grades, market_of, window, capital_dates)
            curve += es.curve_rows(found, prices, markets, window)
            rows += found
        for r in rows + curve:
            r["engine"] = ENGINE
        table = es.summarize_results(rows)
        summary = [{"kind": t["공시 종류"], "period": t["기간"], "window_days": int(t["관측 기간"]), "n_cases": int(t["사례 수"]),
                    "basis": t["기준일"], "return_type": t["수익률"], "sample": t["표본"],
                    "median_pct": t["중앙값"], "p25_pct": t["25%"], "p75_pct": t["75%"], "shown": bool(t["표시"]),
                    "n_caution": int(t["주의 포함"]), "n_excluded": int(t["제외"]), "engine": ENGINE}
                   for t in table.to_dict("records")]
        db.replace_rows(conn, "core.core_event_car", rows)
        db.replace_rows(conn, "core.core_event_summary", summary)
        db.replace_rows(conn, "core.core_event_curve", curve)
    print(f"  이벤트 {len(events):,}건 × 관측 기간 {len(es.WINDOWS)}개 → core.core_event_car {len(rows):,}행")
    print(table[table["기간"] == es.VERIFIED].to_string(index=False))
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="배당 공시 이벤트 스터디(CAR) 계산")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    build_events(ap.parse_args().url)
