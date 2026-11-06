"""검토를 마친 밸류업 정책 검토표 → core.core_policy_item ('확인완료' 행만).

실행: .venv/bin/python -m scripts.load_policy_review <검토표.xlsx> [--url ...]
검토 상태가 '확인완료'이고 검토자가 적힌 행만 넣는다. 표를 비우고 다시 넣는다.
'목표 대상 연도'가 2025 이하인 목표는 그해 실제 배당과 대조해 카드 ③ '과거 계획 이행'에 보인다(source/core/valueup.py implementation).
"""
import argparse
from pathlib import Path

import pandas as pd

from core import db


def rows_from(path: Path) -> list[dict]:
    df = pd.read_excel(path, sheet_name="검토표", dtype={"corp_code": str, "접수번호": str, "목표 값": str, "목표 대상 연도": str})
    df = df[(df["검토 상태"] == "확인완료") & df["검토자"].notna()]
    return [{"corp_code": r["corp_code"], "rcept_no": r["접수번호"], "seq": int(r["순번"]), "section": r["원문 위치"],
             "category": r["분류"], "text": r["원문 문장 (글자 그대로)"],
             "target_kind": None if pd.isna(r["코드가 읽은 목표 종류"]) else r["코드가 읽은 목표 종류"],
             "target_value": None if pd.isna(r["목표 값"]) else str(r["목표 값"]),
             "basis_note": None if pd.isna(r["분모·기준 메모"]) else r["분모·기준 메모"],
             "use_as_target": r["F-03 목표로 쓰기"] == "예", "reviewer": r["검토자"],
             "target_year": _year(r.get("목표 대상 연도")),
             "memo": None if pd.isna(r["메모"]) else r["메모"]} for _, r in df.iterrows()]


def _year(v) -> int | None:
    """목표 대상 연도 칸 (2026-10-25판 검토표에는 이 칸이 없다)."""
    return None if v is None or pd.isna(v) or str(v).strip() == "" else int(float(v))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="확인완료한 밸류업 정책 항목을 DB에 넣기")
    ap.add_argument("path", type=Path)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    rows = rows_from(a.path)
    with db.connect(a.url) as conn:
        db.apply_schema(conn)
        n = db.replace_rows(conn, "core.core_policy_item", rows)
        conn.commit()
    print(f"  core.core_policy_item: {n}행 (확인완료만)")
