"""638사 최대주주 현황을 OpenDART에서 받아 raw.dart_major_holder에 넣고, core.core_major_holder(지분율 합계·개인/법인)를 만든다.

실행: .venv/bin/python -m scripts.collect_major_holder [--year 2025] [--limit N] [--build-only] [--url ...]
키: 환경변수 DART_API_KEY·OPENDART_API_KEY, 없으면 .env(워크트리면 메인 폴더 .env)에서 읽는다. 키는 출력·캐시·DB에 남기지 않는다.
응답은 data/raw/dart_api_cache/hyslrSttus/에 두고 다시 받지 않는다(git 제외). 다시 돌리면 같은 연도·보고서 행을 지우고 새로 넣는다.
키 오류·하루 한도 초과 응답이 오면 거기서 멈추고, 그때까지 받은 회사만 넣는다.
"""
import argparse
from collections import Counter

from core import db
from core import major_holder as mh
from core import share_total as st

COLS = ["corp_code", "bsns_year", "reprt_code", "seq", "rcept_no", "stlm_dt", "nm", "relate", "stock_knd", "share_class",
        "bsis_shares", "bsis_pct", "trmend_shares", "trmend_pct", "bsis_shares_raw", "bsis_pct_raw", "trmend_shares_raw",
        "trmend_pct_raw", "rm", "api_status", "api_message"]
CORE_COLS = ["corp_code", "bsns_year", "reprt_code", "pct_common", "pct_source", "largest_kind", "largest_rule", "n_rows",
             "api_status", "rule"]


def _insert(conn, table: str, cols: list[str], rows: list[list]) -> None:
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", rows)


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
        payload = st.fetch(key, code, year, api=mh.API, cache=mh.CACHE)
        status[payload.get("status")] += 1
        if payload.get("status") in st.STOP_STATUS:
            print(f"  멈춤: {code} 응답 {payload.get('status')} {payload.get('message')}")
            break
        rows += mh.rows_from_response(code, year, st.ANNUAL, payload)
        if i % 50 == 0:
            print(f"  {i}/{len(codes)}")
    with db.connect(url) as conn:
        conn.execute("DELETE FROM raw.dart_major_holder WHERE bsns_year = %s AND reprt_code = %s AND corp_code = ANY(%s)",
                     (year, st.ANNUAL, sorted({r["corp_code"] for r in rows})))
        _insert(conn, "raw.dart_major_holder", COLS, [[r[c] for c in COLS] for r in rows])
    print(f"  회사 {sum(status.values())}곳 응답: {dict(status)} · 넣은 행 {len(rows):,}")
    return status


def build(url: str, year: int) -> Counter:
    """raw.dart_major_holder → core.core_major_holder (회사마다 1행)."""
    with db.connect(url) as conn:
        db.apply_schema(conn)
        raw = db.fetch_dicts(conn, "SELECT * FROM raw.dart_major_holder WHERE bsns_year = %s AND reprt_code = %s ORDER BY corp_code, seq",
                             (year, st.ANNUAL))
        by_corp: dict[str, list[dict]] = {}
        for r in raw:
            by_corp.setdefault(r["corp_code"], []).append(r)
        out, count = [], Counter()
        for corp, rs in by_corp.items():
            h = mh.summarize(rs)
            count[h.largest_kind or h.pct_source] += 1
            out.append([corp, year, st.ANNUAL, h.pct_common, h.pct_source, h.largest_kind, h.largest_rule, h.n_rows,
                        rs[0]["api_status"], mh.RULE])
        conn.execute("DELETE FROM core.core_major_holder WHERE bsns_year = %s AND reprt_code = %s", (year, st.ANNUAL))
        _insert(conn, "core.core_major_holder", CORE_COLS, out)
    print(f"  core.core_major_holder {len(out):,}곳: {dict(count)}")
    return count


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OpenDART 최대주주 현황 → raw.dart_major_holder → core.core_major_holder")
    ap.add_argument("--year", type=int, default=2025, help="사업연도 (사업보고서)")
    ap.add_argument("--limit", type=int, help="앞에서 N곳만 (시험용)")
    ap.add_argument("--build-only", action="store_true", help="받지 않고 raw에서 core만 다시 만듦")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    if not args.build_only:
        collect(args.url, args.year, args.limit)
    build(args.url, args.year)
