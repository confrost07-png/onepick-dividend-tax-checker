"""증자·감자·액면분할·병합 공시 → onepick DB (source/db/schema_capital.sql).

실행: .venv/bin/python -m scripts.load_capital [--limit N] [--url postgresql://localhost/onepick]
회사는 core.core_company 전부, 기간은 2023-01-01 ~ 2026-10-20 (배당 결정 공시와 같음).
① 공시 목록(주요사항보고 B·거래소공시 I) → ② 증자·감자 제목이 있는 회사만 해당 API → ③ 분할·병합 제목은 DART 원문 표를 읽음.
응답은 캐시에 남아, 중간에 멈춰도 다시 실행하면 받지 못한 것만 받는다. 표는 매번 비우고 다시 채운다.
"""
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from core import dart_capital as dc
from core import db

SCHEMA = Path(__file__).resolve().parents[2] / "source" / "db" / "schema_capital.sql"


def companies(conn, limit: int | None) -> list[dict]:
    rows = db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_company ORDER BY corp_name")
    return rows[:limit] if limit else rows


def result_of(msg: str) -> str:
    return "실패" if msg.startswith("실패") else msg


def collect(key: str, corps: list[dict]) -> dict[str, list[dict]]:
    filings, events, splits, log = {}, [], [], []
    # ① 공시 목록
    for i, c in enumerate(corps, 1):
        for ty in ("B", "I"):
            rows, msg = dc.filing_list(key, c["corp_code"], ty)
            for r in rows:
                filings[r["rcept_no"]] = dc.list_row(r, ty)
            log.append({"corp_code": c["corp_code"], "step": f"list:{ty}", "result": result_of(msg),
                        "n_rows": len(rows), "message": msg if msg.startswith("실패") else None})
        if i % 50 == 0 or i == len(corps):
            print(f"  ① 공시 목록 {i}/{len(corps)}사 · {len(filings):,}건", flush=True)

    # 제목으로 고르기
    wanted = defaultdict(dict)  # (corp, API) → {접수번호: 보고서명}
    split_targets = []
    for f in filings.values():
        hit = dc.classify(f["report_nm"])
        if not hit:
            continue
        kind, endpoint = hit
        if endpoint == "doc":
            split_targets.append((f, kind))
        elif f["pblntf_ty"] == "B":  # 증자·감자는 주요사항보고서만 API가 있음
            wanted[(f["corp_code"], endpoint)][f["rcept_no"]] = f["report_nm"]

    # ② 증자·감자 API. API는 정정 묶음의 최종본만 주므로 앞선 판은 목록 정보로 행을 만든다
    kinds = {endpoint: kind for _, kind, endpoint in dc.CAPITAL_TITLES}
    for (corp, endpoint), titles in sorted(wanted.items()):
        rows, msg = dc.decision_rows(key, corp, endpoint)
        for r in rows:
            events += dc.capital_rows(r, endpoint, filings.get(r.get("rcept_no"), {}).get("report_nm"))
        got = {r.get("rcept_no") for r in rows}
        ver = dc.versions(titles, got)
        # API가 주지 않은 유상증자 묶음은 마지막 판을 원문에서 읽는다. 읽으면 앞 판은 그것을 가리킨다
        read = {}
        if endpoint == "piicDecsn":
            for last in {final for v, final in ver.values() if v == "API 응답 없음"}:
                base = dc.listed_only_row(filings[last], kinds[endpoint], "API 응답 없음", None, endpoint)
                try:
                    read[last] = dc.paid_doc_row(base, dc.doc_lines(last))
                except RuntimeError as e:
                    read[last] = dc.paid_doc_row(base, None, str(e))
        done = {last for last, row in read.items() if row["version"] == "원문 최종본"}
        lost = [rc for rc, (v, final) in ver.items() if v == "API 응답 없음" and final not in done]
        for rc, (v, final) in ver.items():
            if rc in got:
                continue
            if rc in read:
                events.append(read[rc])
            elif v == "API 응답 없음" and final in done:
                events.append(dc.listed_only_row(filings[rc], kinds[endpoint], "앞선 판", final, endpoint))
            else:
                events.append(dc.listed_only_row(filings[rc], kinds[endpoint], v, final, endpoint))
        log.append({"corp_code": corp, "step": endpoint, "result": "실패" if lost or msg.startswith("실패") else msg,
                    "n_rows": len(rows), "message": (f"API 응답에 없는 공시: {', '.join(lost)}" if lost else
                                                     msg if msg.startswith("실패") else None)})
    events = list({(e["rcept_no"], e["kind"]): e for e in events}.values())
    print(f"  ② 증자·감자 API {len(wanted)}회 · {len(events)}행", flush=True)

    # ③ 분할·병합 원문
    for f, kind in split_targets:
        try:
            lines, err = dc.doc_lines(f["rcept_no"]), None
        except RuntimeError as e:
            lines, err = None, str(e)
        row = dc.split_row(f, kind, lines, err)
        splits.append(row)
        log.append({"corp_code": f["corp_code"], "step": f"doc:{f['rcept_no']}",
                    "result": "실패" if row["status"] == "원문 못 받음" else "성공", "n_rows": 1,
                    "message": row["check_result"] if row["status"] != "읽음" else None})
    print(f"  ③ 분할·병합 원문 {len(splits)}건", flush=True)
    return {"raw.dart_filing_list": list(filings.values()), "raw.dart_capital_event": events,
            "raw.dart_split_merge": splits, "raw.dart_capital_fetch_log": log}


def report(tables: dict[str, list[dict]], n_corps: int) -> None:
    log = tables["raw.dart_capital_fetch_log"]
    lists = Counter(r["result"] for r in log if r["step"].startswith("list:"))
    print(f"\n회사 {n_corps}곳 × 목록 2종 = {sum(lists.values())}회: " + " · ".join(f"{k} {v}" for k, v in sorted(lists.items())))
    ev = Counter((r["kind"], r["version"]) for r in tables["raw.dart_capital_event"])
    for kind in ("유상증자", "무상증자", "유무상증자", "유무상증자(유상)", "유무상증자(무상)", "감자"):
        n = {v: ev[(kind, v)] for v in ("API 최종본", "원문 최종본", "앞선 판", "첨부만 정정", "API 응답 없음")}
        if any(n.values()):
            print(f"  {kind}: " + " · ".join(f"{v} {c}" for v, c in n.items()))
    cut = Counter((r["check_result"] or "").split(" (")[0] for r in tables["raw.dart_capital_event"]
                  if r["kind"] == "감자" and r["version"] == "API 최종본")
    if cut:
        print("  감자 검산: " + " · ".join(f"{k} {v}" for k, v in sorted(cut.items())))
    sp = Counter((r["kind"], r["status"]) for r in tables["raw.dart_split_merge"])
    for (kind, status), n in sorted(sp.items()):
        print(f"  {kind} · {status}: {n}건")
    bad = [r for r in log if r["result"] == "실패"]
    print(f"  실패·불일치 {len(bad)}건 → raw.dart_capital_fetch_log에서 result='실패' 또는 message 확인")


def main() -> int:
    ap = argparse.ArgumentParser(description="증자·감자·액면분할·병합 공시를 onepick DB에 적재")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    ap.add_argument("--limit", type=int, help="앞에서 N개 회사만 (시험용, DB에는 그만큼만 들어감)")
    args = ap.parse_args()
    key = dc.api_key()
    if not key:
        print(f"OpenDART API 키가 없습니다. 저장소 폴더의 .env에 '{dc.KEY_NAME}=발급받은키' 한 줄을 넣거나 "
              f"환경변수 {dc.KEY_NAME}를 설정한 뒤 다시 실행하세요. (발급: https://opendart.fss.or.kr)")
        return 1
    with db.connect(args.url) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        corps = companies(conn, args.limit)
        print(f"회사 {len(corps)}곳 · 기간 {dc.BEGIN}~{dc.END}")
        try:
            tables = collect(key, corps)
        except dc.StopRun as e:
            conn.rollback()
            print(f"\n멈춤: {e}. 받은 응답은 캐시에 있어 다시 실행하면 이어서 받습니다. DB는 바꾸지 않았습니다.")
            return 2
        for table, rows in tables.items():
            print(f"  {table}: {db.replace_rows(conn, table, rows):,}행")
    report(tables, len(corps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
