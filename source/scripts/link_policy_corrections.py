"""정책 공시마다 최초 접수번호(root_rcept_no)를 채워 정정 공시를 원래 공시와 잇는다.

실행: .venv/bin/python -m scripts.link_policy_corrections [--all] [--url ...]
- DART 공시 화면(dsaf001/main.do)은 수집할 때 받아 둔 캐시(data/raw/dart_cache)에서 먼저 읽고, 없을 때만 DART에 접속한다
- 비어 있는 행만 채운다 (--all이면 전부 다시)
- 결과는 core.v_policy_filing_latest에서 is_latest로 본다: 같은 최초 번호 묶음에서 접수번호가 가장 늦은 판이 최신
"""
import argparse

from core import dart_doc as dd
from core import db
from core import policy_docs as pd_


def main(url: str, redo: bool):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        conn.commit()
        todo = [r[0] for r in conn.execute(
            "SELECT rcept_no FROM raw.policy_filing" + ("" if redo else " WHERE root_rcept_no IS NULL") + " ORDER BY 1")]
        missing = []
        for rcept_no in todo:
            root = pd_.root_rcept_no(dd.get(f"{dd.BASE}/dsaf001/main.do?rcpNo={rcept_no}"), rcept_no)
            if root is None:
                missing.append(rcept_no)
                continue
            conn.execute("UPDATE raw.policy_filing SET root_rcept_no = %s WHERE rcept_no = %s", (root, rcept_no))
        conn.commit()
        n, latest, chains = conn.execute("""SELECT count(*), count(*) FILTER (WHERE is_latest),
                                                   count(DISTINCT chain_root) FILTER (WHERE n_versions > 1)
                                            FROM core.v_policy_filing_latest""").fetchone()
        outside = conn.execute("""SELECT count(*) FROM raw.policy_filing f WHERE f.root_rcept_no <> f.rcept_no
                                  AND NOT EXISTS (SELECT 1 FROM raw.policy_filing o WHERE o.rcept_no = f.root_rcept_no)""").fetchone()[0]
    print(f"  최초 접수번호 채움 {len(todo) - len(missing)}/{len(todo)}건 (못 읽음 {len(missing)}: {missing[:5]})")
    print(f"  공시 {n}건 중 최신 판 {latest}건 · 정정 전 판 {n - latest}건 · 판이 여럿인 계획 {chains}개 · 원공시가 목록 밖 {outside}건")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="정정 공시를 원래 공시와 잇기")
    ap.add_argument("--all", action="store_true", help="이미 채운 행도 다시 읽음")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.all)
