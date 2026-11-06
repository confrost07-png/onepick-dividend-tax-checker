"""B(2024·2025)를 채우고 2026 판정·2027 최소 필요 배당액을 다시 계산한다 (source/scripts/build_core.py 다음에 실행).

실행: .venv/bin/python -m scripts.build_judgement [--url ...]
- B 규칙: source/core/b_income.py (PRD v0.2: 현금배당 − 비과세 감액배당 + 주식배당, B2024는 KIND 공시)
- 재무 숫자는 빈칸 채움·원문 수정을 반영한 뷰(core.v_financial_year_verified)를 쓴다.
- 배당 원본 열(d_dart_won 등)은 고치지 않고 core.core_dividend_year의 b_won·b_status만 2024·2025에 적는다.
"""
import argparse
from collections import Counter

from core import core_tables as ct
from core import db
from core.company_repo import apply_b, load_inputs


def main(url: str):
    with db.connect(url) as conn:
        companies, kind, src_b, stock, div, fin = load_inputs(conn)
        bs = apply_b(companies, kind, src_b, stock, div)
        with conn.cursor() as cur:
            cur.execute("UPDATE core.core_dividend_year SET b_won = NULL, b_status = '미산출' WHERE bsns_year IN (2024, 2025)")
            for code, b in bs.items():
                cur.execute("UPDATE core.core_dividend_year SET b_won = %s, b_status = %s WHERE corp_code = %s AND bsns_year = 2024",
                            (b.b2024, b.b2024_source, code))
                cur.execute("UPDATE core.core_dividend_year SET b_won = %s, b_status = %s WHERE corp_code = %s AND bsns_year = 2025",
                            (b.b2025, b.b2025_source, code))
        judge = ct.judgement_rows(companies, div, fin)
        mins = ct.min_dividend_rows(companies, div, fin)
        db.replace_rows(conn, "core.core_judgement_2026", judge)
        db.replace_rows(conn, "core.core_min_dividend_2027", mins)
        conn.commit()
    print("  B(2024): " + " · ".join(f"{k} {v}" for k, v in Counter(b.b2024_source for b in bs.values()).items()))
    print("  B(2025): " + " · ".join(f"{k} {v}" for k, v in Counter(b.b2025_source for b in bs.values()).items()))
    print("  2026 판정: " + " · ".join(f"{k} {v}" for k, v in Counter(r["status"] for r in judge).most_common()))
    print("  2027 최소액: " + " · ".join(f"{k} {v}" for k, v in Counter((r["scenario"], r["status"]) for r in mins).most_common()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="B 산출과 판정·최소액 재계산")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    main(ap.parse_args().url)
