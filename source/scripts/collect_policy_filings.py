"""시연 10개사의 자사주 매입·소각, 투자·인수 공시를 OpenDART에서 받아 raw.dart_policy_filing에 넣는다 (4층 배당 정책 상세).

실행: .venv/bin/python -m scripts.collect_policy_filings [--since 2024-01-01] [--until 오늘] [--url ...]
키: 환경변수 DART_API_KEY·OPENDART_API_KEY, 없으면 .env(워크트리면 메인 폴더 .env)에서 읽는다. 키는 출력·캐시·DB에 남기지 않는다.
응답은 data/raw/dart_api_cache/<api>/에 두고 다시 받지 않는다(git 제외).
API가 없는 주식소각결정 등은 raw.dart_filing_list 제목·접수번호로 보완한다. 다시 돌리면 10개사의 행을 지우고 새로 넣는다.
"""
import argparse
import datetime as dt
from collections import Counter

from core import db
from core import policy_filings as pf
from core import share_total as st


def collect(url: str, since: dt.date, until: dt.date) -> Counter:
    key = st.api_key()
    if not key:
        raise SystemExit("DART_API_KEY·OPENDART_API_KEY를 찾지 못함 (환경변수 또는 .env)")
    with db.connect(url) as conn:
        db.apply_schema(conn)
        demo = db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_demo_company ORDER BY rank")
        codes = [d["corp_code"] for d in demo]
        filings = db.fetch_dicts(conn, """SELECT rcept_no, corp_code, corp_name, report_nm FROM raw.dart_filing_list
                                          WHERE corp_code = ANY(%s) AND rcept_dt BETWEEN %s AND %s ORDER BY rcept_no""",
                                 (codes, since, until))
    titles = {f["rcept_no"]: f["report_nm"] for f in filings}
    bgn, end = since.strftime("%Y%m%d"), until.strftime("%Y%m%d")
    rows, status = [], Counter()
    for code in codes:
        for api in pf.SPECS:
            payload = pf.fetch(key, api, code, bgn, end)
            status[payload.get("status")] += 1
            if payload.get("status") in st.STOP_STATUS:
                raise SystemExit(f"멈춤: {api} {code} 응답 {payload.get('status')} {payload.get('message')}")
            rows += pf.rows_from_response(api, payload, titles)
    rows += pf.rows_from_filing_list(filings, {r["rcept_no"] for r in rows})
    with db.connect(url) as conn:
        conn.execute("DELETE FROM raw.dart_policy_filing WHERE corp_code = ANY(%s)", (codes,))
        with conn.cursor() as cur:
            cur.executemany(f"INSERT INTO raw.dart_policy_filing ({', '.join(pf.COLS)}) VALUES ({', '.join(['%s'] * len(pf.COLS))})",
                            [[r[c] for c in pf.COLS] for r in rows])
    by = Counter((r["corp_code"], r["kind"]) for r in rows)
    for d in demo:
        kinds = {k: n for (c, k), n in sorted(by.items()) if c == d["corp_code"]}
        print(f"  {d['corp_name']}: {sum(kinds.values())}건 {kinds}")
    print(f"  API 응답 {sum(status.values())}번: {dict(status)} · 넣은 행 {len(rows):,}")
    return status


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OpenDART 자사주·투자·인수 공시 → raw.dart_policy_filing")
    ap.add_argument("--since", type=dt.date.fromisoformat, default=dt.date(2024, 1, 1))
    ap.add_argument("--until", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    collect(args.url, args.since, args.until)
