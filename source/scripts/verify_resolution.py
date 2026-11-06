"""코드가 원문과 대조해 '불일치·못 찾음'이 나온 칸이 그 뒤 어떻게 처리됐는지 센다 → data/processed/analysis/verify_resolution.json.

실행: .venv/bin/python -m scripts.verify_resolution [--review 검토본.xlsx] [--url ...]
- 대조 결과: core.core_source_verify(원문 재대조), core.core_dart_verify(DART 공시 원문 재대조)
- 처리 기록: 팀 전수 검산표 검토본의 행별 '검토 상태'(확인완료 · 정정됨(배제) · 확인불가 = 원문에 없음)와
  원문 대조 파일(data/processed/review/*원문대조_*.csv, 상태 '원문 대조')
- 칸마다 그 칸이 든 검산표 행을 찾는다: 배당 표 전체항목(회사·연도·보고서), 배당 결정 공시(접수번호), KIND(회사),
  재무·현금흐름표·재무 API(회사·연도[·재무제표]). 데이터 이야기 '이 숫자들, 믿어도 될까요?' 장이 읽는다.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from core import db

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "output" / "tables" / "원픽_전수검산표_20261023_검토본.xlsx"
OUT = ROOT / "data" / "processed" / "analysis" / "verify_resolution.json"
OK_RESULTS = ("일치", "일치(단위 반올림)")


def sheet_status(path: Path, sheet: str, keys: list[str]) -> dict[tuple, str]:
    df = pd.read_excel(path, sheet, dtype=str)
    out = {}
    for _, r in df.iterrows():
        key = tuple(str(r[k]).strip() if pd.notna(r[k]) else "" for k in keys)
        key = tuple(v.zfill(8) if k == "corp_code" else v for k, v in zip(keys, key))
        st = r.get("검토 상태")
        out[key] = st.strip() if isinstance(st, str) and st.strip() else "검토 안 함"
    return out


def source_checks() -> set[tuple]:
    """원문 대조 파일에 든 (분류, 회사, 연도, 항목)."""
    out = set()
    for f in sorted((ROOT / "data" / "processed" / "review").glob("*원문대조_*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            out.add((r["corp_code"].zfill(8), int(r["bsns_year"]), r["item"]))
    return out


def outcome(status: str | None, in_check: bool) -> str:
    if in_check:
        return "원문 대조로 고침"
    if status in ("정정됨(배제)",):
        return "팀이 원문 보고 정정"
    if status == "확인완료":
        return "팀이 원문 보고 확인"
    if status == "확인불가":  # 팀 검토에서 '확인불가' = 원문을 찾아봤지만 그 값이 원문에 없음
        return "팀이 원문 보고 원문에 없음 확인"
    return "검토 안 함"


def resolve(conn, review: Path) -> dict:
    items = sheet_status(review, "02_배당표_전체항목", ["corp_code", "사업연도", "보고서 접수번호"])
    decisions = sheet_status(review, "05_배당결정공시", ["corp_code", "접수번호"])
    kind = {k[0]: v for k, v in sheet_status(review, "09_KIND고배당", ["corp_code"]).items()}
    fin = sheet_status(review, "02_재무", ["corp_code", "사업연도"])
    cf = sheet_status(review, "04_배당금지급", ["corp_code", "사업연도"])
    api = sheet_status(review, "04-2_재무API", ["corp_code", "사업연도", "재무제표"])
    checked = source_checks()

    src = Counter()
    for r in db.fetch_dicts(conn, "SELECT * FROM core.core_source_verify WHERE result NOT IN ('일치')"):
        corp, ref = r["corp_code"], (r["ref"] or "").split("|")
        if r["target"] == "dart_dividend_item":
            st = items.get((corp, ref[1] if len(ref) > 1 else "", ref[0]))
        elif r["target"] == "dividend_decision":
            st = decisions.get((corp, ref[0]))
        elif r["target"] == "kind_list":
            st = kind.get(corp)
        else:
            st = None
        src[(r["result"], outcome(st, False))] += 1

    dart = Counter()
    for r in db.fetch_dicts(conn, f"SELECT * FROM core.core_dart_verify WHERE result NOT IN {OK_RESULTS}"):
        corp, year = r["corp_code"], r["bsns_year"]
        if r["target"] == "core_financial_year":
            st, item = fin.get((corp, str(year))), r["item"]
        elif r["target"] == "cf_dividend_paid":
            st, item = cf.get((corp, str(year))), "cf_paid_won"
        else:  # dart_financial (재무 API)
            st, item = api.get((corp, str(year), r["basis"] or "")), r["item"]  # 검산표 재무제표 칸도 연결/별도
        dart[(r["result"], outcome(st, (corp, year, item) in checked))] += 1

    group = lambda c: {f"{a}|{b}": n for (a, b), n in sorted(c.items())}  # noqa: E731
    total = lambda c, pred: sum(n for (a, b), n in c.items() if pred(b))  # noqa: E731
    done = lambda b: b != "검토 안 함"  # noqa: E731
    return {
        "built": date.today().isoformat(), "review_file": review.name,
        "source_verify": {"open": sum(src.values()), "settled": total(src, done), "detail": group(src)},
        "dart_verify": {"open": sum(dart.values()), "settled": total(dart, done), "detail": group(dart)},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="원문 대조 불일치 칸의 처리 결과 세기")
    ap.add_argument("--review", type=Path, default=REVIEW)
    ap.add_argument("--url", default=db.database_url())
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        res = resolve(conn, a.review)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
