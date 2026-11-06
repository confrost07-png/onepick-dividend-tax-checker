"""원문 대조 불일치 칸 → 사람 검토용 표 report/검증/DART_불일치_검토표.csv (엑셀에서 열기 좋게 UTF-8 BOM).

실행: .venv/bin/python -m scripts.export_mismatch_review
검토 결과·메모 칸은 비워 둔다. 사람이 채운 뒤 팀이 정한 값만 반영한다.
"""
from pathlib import Path

import pandas as pd

from core import db

OUT = Path(__file__).resolve().parents[2] / "report" / "검증" / "DART_불일치_검토표.csv"
TARGET = {"core_financial_year": "02 재무", "cf_dividend_paid": "04 배당금 지급", "dart_financial": "04-2 부채·자본총계"}
ITEM = {"ni_owner_won": "지배주주 순이익", "liabilities_won": "부채총계", "equity_won": "자본총계", "dividends_paid_won": "배당금 지급"}
KIND_ORDER = {"사람 확인": 0, "재작성 선택": 1, "확실": 2}


def main(url: str):
    with db.connect(url) as conn:
        m = pd.DataFrame(db.fetch_dicts(conn, """
            SELECT m.*, coalesce(c.corp_name, m.corp_code) AS corp_name,
                   (SELECT value FROM core.core_setting WHERE key = 'restated_policy') AS policy
            FROM core.v_dart_mismatch m LEFT JOIN core.core_company c USING (corp_code)"""))
    m["db"] = m["db_value"].astype(float)
    m["src"] = m["src_value"].astype(float)
    out = pd.DataFrame({
        "구분": m["correction_kind"],
        "판정에 쓰는 연도(2023~2025)": m["bsns_year"].between(2023, 2025).map({True: "예", False: ""}),
        "대상": m["target"].map(TARGET), "회사": m["corp_name"], "corp_code": m["corp_code"], "사업연도": m["bsns_year"],
        "항목": m["item"].map(ITEM), "기준": m["basis"],
        "DB 값(원)": m["db"].map(lambda v: f"{v:,.0f}"), "원문 값(원)": m["src"].map(lambda v: f"{v:,.0f}"),
        "차이율": ((m["db"] - m["src"]) / m["src"].where(m["src"] != 0)).map(lambda v: "" if pd.isna(v) else f"{v * 100:+.1f}%"),
        "원인": m["note"], "원문 검산": m["check_result"],
        "뷰에서 쓰는 값": [("원문 값" if u else "DB 값(원문에서 줄 못 찾음)" if "줄 없음" in str(c) else "DB 값(재작성)")
                       for u, c in zip(m["use_source"], m["check_result"])],
        "원문 보고서": m["src_title"], "접수번호": m["src_rcept_no"],
        "원문 링크": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + m["src_rcept_no"].astype(str),
        "검토 결과(원문 맞음/DB 맞음/기타)": "", "검토자 메모": "",
    })
    out = out.assign(_k=out["구분"].map(KIND_ORDER)).sort_values(
        ["_k", "판정에 쓰는 연도(2023~2025)", "회사", "사업연도"], ascending=[True, False, True, True]).drop(columns="_k")
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"  {OUT.name}: {len(out)}행 · " + " · ".join(f"{k} {v}" for k, v in out["구분"].value_counts().items()))


if __name__ == "__main__":
    main(db.database_url())
