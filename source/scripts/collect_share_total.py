"""638사 주식의 총수 현황(발행·자기·유통)을 OpenDART에서 받아 raw.dart_share_total에 넣는다.

실행: .venv/bin/python -m scripts.collect_share_total [--year 2025] [--limit N] [--url ...]
키: 환경변수 DART_API_KEY·OPENDART_API_KEY, 없으면 .env(워크트리면 메인 폴더 .env)에서 읽는다. 키는 출력·캐시·DB에 남기지 않는다.
응답은 data/raw/dart_api_cache/stockTotqySttus/에 두고 다시 받지 않는다(git 제외). 다시 돌리면 같은 연도·보고서 행을 지우고 새로 넣는다.
키 오류·하루 한도 초과 응답이 오면 거기서 멈추고, 그때까지 받은 회사만 넣는다.
"""
import argparse
from collections import Counter

from core import db
from core import share_total as st

COLS = ["corp_code", "bsns_year", "reprt_code", "se", "share_class", "rcept_no", "stlm_dt", "issued", "treasury", "floating",
        "issued_raw", "treasury_raw", "floating_raw", "floating_note", "api_status", "api_message"]


def collect(url: str, year: int, limit: int | None = None) -> Counter:
    key = st.api_key()
    if not key:
        raise SystemExit("DART_API_KEY·OPENDART_API_KEY를 찾지 못함 (환경변수 또는 .env)")
    with db.connect(url) as conn:
        db.apply_schema(conn)
        codes = [r["corp_code"] for r in db.fetch_dicts(conn, "SELECT corp_code FROM core.core_company ORDER BY corp_code")]
    codes = codes[:limit] if limit else codes
    rows, status = [], Counter()
    for i, code in enumerate(codes, 1):
        payload = st.fetch(key, code, year)
        status[payload.get("status")] += 1
        if payload.get("status") in st.STOP_STATUS:
            print(f"  멈춤: {code} 응답 {payload.get('status')} {payload.get('message')}")
            break
        rows += st.rows_from_response(code, year, st.ANNUAL, payload)
        if i % 50 == 0:
            print(f"  {i}/{len(codes)}")
    with db.connect(url) as conn:
        conn.execute("DELETE FROM raw.dart_share_total WHERE bsns_year = %s AND reprt_code = %s AND corp_code = ANY(%s)",
                     (year, st.ANNUAL, sorted({r["corp_code"] for r in rows})))
        with conn.cursor() as cur:
            cur.executemany(f"INSERT INTO raw.dart_share_total ({', '.join(COLS)}) VALUES ({', '.join(['%s'] * len(COLS))})",
                            [[r[c] for c in COLS] for r in rows])
    print(f"  회사 {sum(status.values())}곳 응답: {dict(status)} · 넣은 행 {len(rows):,}")
    return status


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OpenDART 주식의 총수 현황 → raw.dart_share_total")
    ap.add_argument("--year", type=int, default=2025, help="사업연도 (사업보고서)")
    ap.add_argument("--limit", type=int, help="앞에서 N곳만 (시험용)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    collect(args.url, args.year, args.limit)
