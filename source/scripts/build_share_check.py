"""주식 총수 이상치 표 core.core_share_check를 만든다 (source/scripts/collect_share_total.py 다음에 실행).

실행: .venv/bin/python -m scripts.build_share_check [--year 2025] [--url ...]
자료: 발행주식수(raw.dart_share_total), 액면가(raw.dart_dividend_item '주당액면가액(원)'),
자본금(raw.dart_financial 재무상태표 '자본금', 별도 우선), 자본총계(core.core_financial_year), 결산 기준일 이전 마지막 종가(raw.krx_price_daily).
판정 규칙은 source/core/share_check.py. 다시 돌리면 그 연도 행을 지우고 새로 넣는다.
"""
import argparse
from collections import Counter
from decimal import Decimal

from core import db
from core import share_check as sc
from core import share_total as st

FACTS = """
WITH s AS (
  SELECT corp_code,
         bool_or(share_class = '보통') AS has_common,
         sum(issued) FILTER (WHERE share_class IN ('보통', '우선·종류', '기타')) AS issued_all,
         max(floating) FILTER (WHERE share_class = '보통') AS floating,
         max(stlm_dt) AS stlm_dt
  FROM raw.dart_share_total WHERE bsns_year = %(y)s AND reprt_code = %(r)s GROUP BY 1),
par AS (
  SELECT corp_code, max(replace(value, ',', ''))::numeric AS par FROM raw.dart_dividend_item
  WHERE bsns_year = %(y)s AND item = '주당액면가액(원)' AND value ~ '^[0-9,.]+$' GROUP BY 1),
cap AS (
  SELECT corp_code, coalesce(max(thstrm_amount) FILTER (WHERE fs_div = 'OFS'),
                             max(thstrm_amount) FILTER (WHERE fs_div = 'CFS')) AS capital
  FROM raw.dart_financial WHERE bsns_year = %(y)s AND sj_div = 'BS' AND account_nm ~ '^\\s*자본금\\s*$' GROUP BY 1)
SELECT s.corp_code, s.has_common, s.issued_all, s.floating, par.par, cap.capital, f.equity_won AS equity,
       (SELECT p.close_adj FROM raw.krx_price_daily p
        WHERE p.corp_code = s.corp_code AND p.trade_date <= s.stlm_dt::date ORDER BY p.trade_date DESC LIMIT 1) AS close
FROM s LEFT JOIN par USING (corp_code) LEFT JOIN cap USING (corp_code)
LEFT JOIN core.core_financial_year f ON f.corp_code = s.corp_code AND f.bsns_year = %(y)s
"""
COLS = ["corp_code", "bsns_year", "reprt_code", "check", "action", "factor", "reason", "ratio", "pbr_api", "pbr_fixed",
        "issued_all", "par_won", "capital_won", "close_won", "equity_won", "rule"]


def _dec(v):
    return None if v is None else Decimal(str(v))


def main(url: str, year: int) -> Counter:
    with db.connect(url) as conn:
        db.apply_schema(conn)
        facts = db.fetch_dicts(conn, FACTS, {"y": year, "r": st.ANNUAL})
        rows, count = [], Counter()
        for r in facts:
            f = sc.Facts(bool(r["has_common"]), _dec(r["issued_all"]), _dec(r["floating"]), _dec(r["par"]),
                         _dec(r["capital"]), _dec(r["close"]), _dec(r["equity"]))
            got = sc.judge(f)
            count[got.check if got else "자본금 일치"] += 1
            if got:
                rows.append([r["corp_code"], year, st.ANNUAL, got.check, got.action, got.factor, got.reason, got.ratio,
                             got.pbr_api, got.pbr_fixed, f.issued_all, f.par, f.capital, f.close, f.equity, sc.RULE])
        conn.execute("DELETE FROM core.core_share_check WHERE bsns_year = %s AND reprt_code = %s", (year, st.ANNUAL))
        with conn.cursor() as cur:
            cols = ", ".join(f'"{c}"' for c in COLS)
            cur.executemany(f"INSERT INTO core.core_share_check ({cols}) VALUES ({', '.join(['%s'] * len(COLS))})", rows)
    for k, n in count.most_common():
        print(f"  {k}: {n}곳")
    return count


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="주식 총수 이상치 판정 → core.core_share_check")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    main(args.url, args.year)
