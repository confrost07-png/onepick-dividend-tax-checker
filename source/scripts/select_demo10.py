"""시연 10개사를 고른다 → core.core_demo_company (source/scripts/build_capacity.py 다음에 실행).

실행: .venv/bin/python -m scripts.select_demo10 [--n 10] [--url ...]
규칙: 2026 판정 '충족' + 기업가치 제고 계획 공시(예고 제외)가 있음 + 금융업 아님(core.core_capacity_2025) → 추정 시가총액 상위.
추정 시가총액 = (2025 자본금 ÷ 주당 액면가) × 마지막 수정주가. 발행주식 수 원천이 없어 근사치이며 순서 정하기에만 쓴다.
"""
import argparse

from core import db

RULE = "2026 판정 충족 · 기업가치 제고 계획 공시 있음 · 금융업 제외 · 추정 시가총액 상위"


def main(url: str, n: int):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        rows = db.fetch_dicts(conn, f"""
            WITH vu AS (SELECT corp_code, count(*) AS n, max(rcept_no) AS last_rcept FROM raw.dart_filing_list
                        WHERE report_nm ~ '기업가치제고계획' AND report_nm !~ '예고' GROUP BY 1),
                 par AS (SELECT corp_code, max(value)::numeric AS par FROM raw.dart_dividend_item
                         WHERE bsns_year = 2025 AND item LIKE '주당액면가액%%' AND value ~ '^[0-9.]+$' GROUP BY 1),
                 cap AS (SELECT DISTINCT ON (corp_code) corp_code, thstrm_amount FROM raw.dart_financial
                         WHERE bsns_year = 2025 AND account_id = 'ifrs-full_IssuedCapital' ORDER BY corp_code, ord),
                 px AS (SELECT DISTINCT ON (corp_code) corp_code, close_adj, trade_date FROM raw.krx_price_daily
                        ORDER BY corp_code, trade_date DESC)
            SELECT k.corp_code, k.corp_name, cc.industry, vu.n, vu.last_rcept, px.trade_date,
                   cap.thstrm_amount / par.par * px.close_adj AS mcap
            FROM core.core_company k JOIN core.core_judgement_2026 j USING (corp_code)
            JOIN core.core_capacity_2025 cc USING (corp_code) JOIN vu USING (corp_code)
            LEFT JOIN par USING (corp_code) LEFT JOIN cap USING (corp_code) LEFT JOIN px USING (corp_code)
            WHERE j.status = '충족' AND cc.status <> '미적용(금융업)' AND par.par > 0
            ORDER BY mcap DESC NULLS LAST LIMIT {int(n)}""")
        out = [{"rank": i, "corp_code": r["corp_code"], "corp_name": r["corp_name"], "industry": r["industry"],
                "mcap_est_won": r["mcap"], "price_date": r["trade_date"], "valueup_count": r["n"],
                "last_valueup_rcept": r["last_rcept"], "rule": RULE} for i, r in enumerate(rows, 1)]
        db.replace_rows(conn, "core.core_demo_company", out)
        conn.commit()
    for r in out:
        print(f"  {r['rank']:>2}. {r['corp_name']} ({r['industry']}) 추정 시총 {float(r['mcap_est_won'] or 0) / 1e12:,.1f}조 · 밸류업 공시 {r['valueup_count']}건")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="시연 10개사 고르기")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.n)
