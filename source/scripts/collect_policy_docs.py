"""배당·주주환원 정책 문서를 DART에서 문서째 받아 DB에 넣는다 → raw.policy_filing / policy_document / policy_chunk.

실행: .venv/bin/python -m scripts.collect_policy_docs [--kinds 기업가치] [--since 2024-01-01] [--limit N] [--url ...]
대상: raw.dart_filing_list 중 보고서명이 kinds에 맞는 공시 (since 이후). 기본은 기업가치 제고 계획(예고·이행현황·정정 포함)만.
기업지배구조보고서·주주환원 공정공시까지 넣으려면 --kinds "기업가치|지배구조보고서|주주환원|배당정책|주주가치".
이미 넣은 공시는 건너뛰어 중간에 멈춰도 이어서 돈다. 원본 HTML은 data/raw/policy_docs/<접수번호>/에 저장(git 제외).
DART가 거절하면 source/core/dart_doc.get이 점점 길게 쉬었다 다시 받는다.
"""
import argparse
from collections import Counter
from pathlib import Path

from core import dart_doc as dd
from core import db
from core import policy_docs as pd_

ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "policy_docs"


def main(url: str, since: str, limit: int | None, kinds: str):
    ROOT.mkdir(parents=True, exist_ok=True)
    with db.connect(url) as conn:
        db.apply_schema(conn)
        conn.commit()
        done = {r[0] for r in conn.execute("SELECT rcept_no FROM raw.policy_filing WHERE status = '수집'")}
        todo = [r for r in db.fetch_dicts(conn, """
            SELECT rcept_no, corp_code, corp_name, rcept_dt, report_nm FROM raw.dart_filing_list
            WHERE rcept_dt >= %s AND report_nm ~ %s ORDER BY rcept_dt, rcept_no""", (since, kinds))
                if r["rcept_no"] not in done][:limit]
        print(f"  받을 공시 {len(todo):,}건 (이미 {len(done):,}건)", flush=True)
        stat = Counter()
        for i, f in enumerate(todo, 1):
            report = " ".join(f["report_nm"].split())
            try:
                docs = pd_.documents(f["rcept_no"])
                status, note = "수집", ""
            except RuntimeError as e:
                docs, status, note = [], "원문 받기 실패", str(e)[:300]
            with conn.transaction():
                conn.execute("DELETE FROM raw.policy_filing WHERE rcept_no = %s", (f["rcept_no"],))
                root = pd_.root_rcept_no(dd.get(f"{dd.BASE}/dsaf001/main.do?rcpNo={f['rcept_no']}"), f["rcept_no"])
                conn.execute("""INSERT INTO raw.policy_filing (rcept_no, corp_code, corp_name, rcept_dt, report_nm, doc_kind,
                                is_correction, n_docs, status, note, root_rcept_no) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                             (f["rcept_no"], f["corp_code"], f["corp_name"], f["rcept_dt"], report, pd_.doc_kind(report),
                              report.startswith("["), len(docs), status, note, root))
                for d in docs:
                    text, parts = pd_.text_of(d)
                    path, sha = pd_.save_original(ROOT, f["rcept_no"], d)
                    n_pages = text.count("\f") + 1 if d.file_type == "pdf" else None
                    conn.execute("""INSERT INTO raw.policy_document (rcept_no, dcm_no, doc_name, file_type, n_pages, url, file_path,
                                    sha256, n_chars, text) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                 (f["rcept_no"], d.dcm_no, d.name, d.file_type, n_pages, d.url, path, sha, len(text),
                                  text.replace("\x00", "")))
                    with conn.cursor() as cur:
                        cur.executemany("INSERT INTO raw.policy_chunk (rcept_no, dcm_no, seq, page, text) VALUES (%s,%s,%s,%s,%s)",
                                        [(f["rcept_no"], d.dcm_no, k, pg, t.replace("\x00", ""))
                                         for k, (pg, t) in enumerate(parts, 1)])
            conn.commit()  # 공시 1건마다 확정 (중간에 멈춰도 받은 것은 남음)
            stat[status] += 1
            if i % 50 == 0 or i == len(todo):
                print(f"    {i:,}/{len(todo):,} · " + " · ".join(f"{k} {v}" for k, v in stat.items()), flush=True)
        print("  " + " · ".join(f"{k} {v}" for k, v in conn.execute(
            "SELECT doc_kind || ' ' || status, count(*) FROM raw.policy_filing GROUP BY 1 ORDER BY 1").fetchall()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="배당·주주환원 정책 문서 수집")
    ap.add_argument("--kinds", default="기업가치", help="보고서명 정규식 (기본: 기업가치 제고 계획만)")
    ap.add_argument("--since", default="2024-01-01")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.since, a.limit, a.kinds)
