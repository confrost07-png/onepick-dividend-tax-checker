"""raw 스키마 + 02·07 가공본 → core 스키마, 그리고 판정·최소액 계산.

실행: .venv/bin/python -m scripts.build_core [--source 원천폴더] [--url ...]
scripts.load_raw를 먼저 돌려야 한다. core 표는 매번 비우고 다시 채운다.
"""
import argparse
import warnings
from pathlib import Path

from core import core_tables as ct
from core import db
from core.raw_tables import DEFAULT_SOURCE_DIR, read_source


def build_core(url: str, source_dir: Path) -> dict[str, int]:
    warnings.filterwarnings("ignore", module="openpyxl")
    df02, df07 = read_source("02", source_dir), read_source("07", source_dir)
    with db.connect(url) as conn:
        kind = db.fetch_dicts(conn, "SELECT corp_name, corp_code, is_high_dividend FROM raw.kind_list")
        decisions = db.fetch_dicts(conn, "SELECT * FROM raw.dividend_decision")
        cf = db.fetch_dicts(conn, "SELECT corp_code, bsns_year, paid_mil, status FROM raw.cf_dividend_paid")

        companies = ct.company_rows(df02, df07, kind)
        codes = {c["corp_code"] for c in companies}
        div_rows = ct.dividend_year_rows(df02, decisions, cf, codes)
        fin_rows = ct.financial_rows(df02)
        tables = {
            "core.core_company": companies,  # 이 표를 비우면 나머지 core 표도 함께 비워진다(FK CASCADE)
            "core.core_dividend_year": div_rows,
            "core.core_financial_year": fin_rows,
            "core.core_judgement_2026": ct.judgement_rows(companies, div_rows, fin_rows),
            "core.core_min_dividend_2027": ct.min_dividend_rows(companies, div_rows, fin_rows),
        }
        counts = {}
        for table, rows in tables.items():
            counts[table] = db.replace_rows(conn, table, rows)
            print(f"  {table}: {counts[table]:,}행")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="raw → core 가공과 판정·최소액 계산")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DIR, help="02·07 엑셀이 있는 폴더")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    build_core(args.url, args.source)
