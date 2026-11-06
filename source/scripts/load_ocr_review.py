"""검토를 마친 OCR 검토표 → raw.policy_page_ocr 검토 칸, 정정 글자는 검색 문단(raw.policy_chunk)에도 반영.

실행: .venv/bin/python -m scripts.load_ocr_review <OCR_검토표.xlsx> [--url ...]
검토 상태와 검토자가 둘 다 적힌 행만 넣는다. 검토자가 Claude(AI)인 행(미리 채운 AI 결과)은 건너뛴다. '정정함'인데 정정 글자가 비어 있으면 넣지 않고 알려 준다.
같은 쪽을 다시 넣으면 새 값으로 바뀐다. 검토 칸이 빈 행은 DB의 기존 검토 결과를 지우지 않는다.
"""
import argparse
from pathlib import Path

import pandas as pd

from core import db
from scripts.export_ocr_review import REVIEWERS, STATES
from scripts.ocr_policy_docs import rebuild_chunks


def text(v) -> str | None:
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip() else str(v).strip()


def rows_from(path: Path) -> tuple[list[dict], list[str]]:
    df = pd.read_excel(path, sheet_name="검토표", dtype={"접수번호": str, "문서": str})
    ok, problems = [], []
    for i, r in df.iterrows():
        state, who = text(r["검토 상태"]), text(r["검토자"])
        if not state and not who:
            continue
        if who == "Claude(AI)":  # AI 검토를 미리 채워 둔 행을 사람이 바꾸지 않았으면 그대로 둔다 (source/scripts/ocr_ai_review.py)
            continue
        where = f"{i + 2}행 {r['접수번호']} {r['문서']} {int(r['쪽'])}쪽"
        fixed = text(r["정정 글자 (정정함일 때 쪽 전체를 고친 글자)"])
        if state not in STATES or who not in REVIEWERS:
            problems.append(f"{where}: 검토 상태·검토자 둘 다 목록에서 골라야 함 ({state}, {who})")
        elif state == "정정함" and not fixed:
            problems.append(f"{where}: 정정함인데 정정 글자가 비어 있음")
        else:
            ok.append({"rcept_no": r["접수번호"], "dcm_no": r["문서"], "page": int(r["쪽"]), "review_status": state,
                       "reviewer": who, "corrected_text": fixed if state == "정정함" else None, "review_note": text(r["메모"])})
    return ok, problems


def load(conn, items: list[dict]) -> int:
    n = 0
    for it in items:
        n += conn.execute("""UPDATE raw.policy_page_ocr SET review_status = %(review_status)s, reviewer = %(reviewer)s,
                                corrected_text = %(corrected_text)s, review_note = %(review_note)s, reviewed_at = now()
                             WHERE rcept_no = %(rcept_no)s AND dcm_no = %(dcm_no)s AND page = %(page)s""", it).rowcount
    for rcept_no, dcm_no in sorted({(it["rcept_no"], it["dcm_no"]) for it in items}):
        rebuild_chunks(conn, rcept_no, dcm_no)
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OCR 검토 결과를 DB에 넣기")
    ap.add_argument("path", type=Path)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    items, problems = rows_from(a.path)
    with db.connect(a.url) as conn:
        db.apply_schema(conn)
        n = load(conn, items)
        conn.commit()
    print(f"  raw.policy_page_ocr 검토 반영: {n}쪽 (" +
          ", ".join(f"{s} {sum(1 for it in items if it['review_status'] == s)}" for s in STATES) + ")")
    for p in problems:
        print("  넣지 않음 —", p)
