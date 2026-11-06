"""DB 재무제표 값을 DART 사업보고서 원문과 전수 대조 → core.core_dart_verify.

실행: .venv/bin/python -m scripts.verify_db [--limit N] [--redo] [--url ...]
- core.core_financial_year 2018~2025: 지배주주 순이익·부채·자본 (02 원천, 백만 원 단위)
- raw.cf_dividend_paid 2023~2025: 배당금 지급 (04 원천, 백만 원)
- raw.dart_financial 2023~2025: 부채총계·자본총계 (04-2 원천, 원 단위)
회사 하나를 끝낼 때마다 저장한다. 다시 돌리면 끝난 회사는 건너뛴다(--redo면 처음부터). 원문은 data/raw/dart_cache/에 둔다.
"""
import argparse
import sys
import time
from collections import defaultdict

from psycopg import sql

from core import dart_doc as dd
from core import dart_verify as dv
from core import db

COLS = ["target", "corp_code", "bsns_year", "item", "basis", "db_value", "src_value", "result", "src_rcept_no",
        "src_title", "src_period", "check_result", "note", "engine"]


def company_cells(conn, corp: str) -> list[tuple]:
    """(target, 사업연도, item, 연결여부, DB 값(원))"""
    cells = []
    for r in db.fetch_dicts(conn, """
        SELECT bsns_year, fs_basis, ni_owner_won, liabilities_won, equity_won FROM core.core_financial_year
        WHERE corp_code = %s AND bsns_year BETWEEN 2018 AND 2025""", (corp,)):
        cons = r["fs_basis"] != "별도"
        for item in ("ni_owner_won", "liabilities_won", "equity_won"):
            if r[item] is not None:
                cells.append(("core_financial_year", r["bsns_year"], item, cons, float(r[item])))
    for r in db.fetch_dicts(conn, """
        SELECT bsns_year, fs_div, paid_mil FROM raw.cf_dividend_paid
        WHERE corp_code = %s AND bsns_year BETWEEN 2023 AND 2025 AND paid_mil IS NOT NULL""", (corp,)):
        cells.append(("cf_dividend_paid", r["bsns_year"], "dividends_paid_won", r["fs_div"] != "OFS",
                      float(r["paid_mil"]) * 1_000_000))
    for r in db.fetch_dicts(conn, """
        SELECT bsns_year, fs_div, account_nm, thstrm_amount FROM raw.dart_financial
        WHERE corp_code = %s AND bsns_year BETWEEN 2023 AND 2025 AND sj_div = 'BS'
          AND regexp_replace(account_nm, '\\s', '', 'g') IN ('부채총계', '자본총계') AND thstrm_amount IS NOT NULL""", (corp,)):
        item = "liabilities_won" if "부채" in r["account_nm"] else "equity_won"
        cells.append(("dart_financial", r["bsns_year"], item, r["fs_div"] == "CFS", float(r["thstrm_amount"])))
    return list({(c[0], c[1], c[2], c[3]): c for c in cells}.values())


def main(url: str, limit: int | None, redo: bool):
    reader = dv.Reader()
    with db.connect(url) as conn:
        db.apply_schema(conn)
        if redo:
            conn.execute("TRUNCATE core.core_dart_verify")
        conn.commit()
        done = {r["corp_code"] for r in db.fetch_dicts(conn, "SELECT DISTINCT corp_code FROM core.core_dart_verify")}
        companies = [c for c in db.fetch_dicts(conn, "SELECT corp_code, corp_name, fiscal_month FROM core.core_company "
                                                     "ORDER BY corp_code") if c["corp_code"] not in done]
        if limit:
            companies = companies[:limit]
        t0 = time.time()
        for i, c in enumerate(companies, 1):
            reports = defaultdict(list)
            try:
                for rcp, title, period in dd.annual_reports(c["corp_code"]):
                    reports[period].append((rcp, title))
            except Exception as ex:  # noqa: BLE001
                print(f"  ! {c['corp_name']} 사업보고서 검색 실패: {ex}", file=sys.stderr, flush=True)
                continue
            rows = [dv.verify_cell(reader, reports, c["corp_code"], c["corp_name"], y, c["fiscal_month"], item, cons, v, t)
                    for t, y, item, cons, v in company_cells(conn, c["corp_code"])]
            conn.execute("DELETE FROM core.core_dart_verify WHERE corp_code = %s", (c["corp_code"],))
            if rows:
                with conn.cursor().copy(sql.SQL("COPY core.core_dart_verify ({}) FROM STDIN").format(
                        sql.SQL(", ").join(map(sql.Identifier, COLS)))) as cp:
                    for r in rows:
                        cp.write_row([r[k] for k in COLS])
            conn.commit()
            reader._cache.clear()
            bad = sum(r["result"] == dv.MISMATCH for r in rows)
            print(f"  [{i}/{len(companies)}] {c['corp_name']}: {len(rows)}칸 · 불일치 {bad} · {time.time() - t0:,.0f}초",
                  flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DB 재무제표 값 ↔ DART 사업보고서 원문 전수 대조")
    ap.add_argument("--limit", type=int, default=None, help="회사 수 (시험용)")
    ap.add_argument("--redo", action="store_true", help="결과를 지우고 처음부터")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.limit, a.redo)
