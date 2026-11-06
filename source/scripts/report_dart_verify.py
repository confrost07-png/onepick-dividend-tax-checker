"""core.core_dart_verify → report/검증/DART_원문대조_재무제표_결과.md. 숫자는 모두 DB에서 센다.

실행: .venv/bin/python -m scripts.report_dart_verify
"""
import re
from pathlib import Path

import pandas as pd

from core import db
from core import dart_verify as dv

OUT = Path(__file__).resolve().parents[2] / "report" / "검증" / "DART_원문대조_재무제표_결과.md"
TARGET = {"core_financial_year": "02 재무 (core_financial_year)", "cf_dividend_paid": "04 배당금 지급 (cf_dividend_paid)",
          "dart_financial": "04-2 부채·자본총계 (dart_financial)"}
ITEM = {"ni_owner_won": "지배주주 순이익", "liabilities_won": "부채총계", "equity_won": "자본총계", "dividends_paid_won": "배당금 지급"}
ORDER = [dv.MATCH, dv.ROUNDING, dv.MISMATCH, dv.FOREIGN, dv.UNREADABLE, dv.NO_REPORT]


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(x) else str(x).replace("|", "\\|") for x in r) + " |")
    return "\n".join(out)


def won(v):
    return "" if pd.isna(v) else f"{float(v):,.0f}"


def cause(note: str) -> str:
    note = note or ""
    for key, label in (("뒤 보고서 비교기간", "DB = 1~2년 뒤 보고서의 재작성 값"), ("당기순이익 전체", "DB = 당기순이익 전체(비지배 포함)"), ("단위", "DB와 원문이 단위 배수 차이"), ("통화 다름", "DB = 외화(USD) 기준 값을 원화로 적음"), ("정정 전 원공시", "DB = 정정 전 원공시 값"),
                       ("다른 기준", "DB = 다른 기준(연결↔별도) 값"), ("찾지 못함", "DB 값과 같은 원문 값 없음")):
        if key in note:
            return label
    return "기타"


def main(url: str):
    with db.connect(url) as conn:
        v = pd.DataFrame(db.fetch_dicts(conn, """
            SELECT v.*, coalesce(c.corp_name, v.corp_code) AS corp_name FROM core.core_dart_verify v
            LEFT JOIN core.core_company c USING (corp_code)"""))
        n_corp = conn.execute("SELECT count(*) FROM core.core_company").fetchone()[0]
    v["대상"] = v["target"].map(TARGET)
    v["항목"] = v["item"].map(ITEM)
    done = v["corp_code"].nunique()

    summary = v.pivot_table(index="대상", columns="result", values="item", aggfunc="count", fill_value=0)
    summary = summary.reindex(columns=[c for c in ORDER if c in summary.columns])
    summary["합계"] = summary.sum(axis=1)
    summary["일치율(읽은 칸 중)"] = ((summary.get(dv.MATCH, 0) + summary.get(dv.ROUNDING, 0))
                                / (summary["합계"] - summary.get(dv.UNREADABLE, 0) - summary.get(dv.NO_REPORT, 0) - summary.get(dv.FOREIGN, 0)) * 100).round(1).astype(str) + "%"
    summary = summary.reset_index()

    by_year = v[v["target"] == "core_financial_year"].pivot_table(index="bsns_year", columns="result", values="item",
                                                                 aggfunc="count", fill_value=0)
    by_year = by_year.reindex(columns=[c for c in ORDER if c in by_year.columns]).reset_index().rename(columns={"bsns_year": "사업연도"})

    mis = v[v["result"] == dv.MISMATCH].copy()
    mis["원인"] = mis["note"].map(cause)
    causes = mis.groupby(["대상", "원인"]).size().reset_index(name="칸 수")
    engine = mis[mis["bsns_year"].between(2023, 2025) & (mis["target"] == "core_financial_year")]
    mis_tbl = pd.DataFrame({"회사": mis["corp_name"], "연도": mis["bsns_year"], "대상": mis["target"], "항목": mis["항목"],
                            "기준": mis["basis"], "DB 값": mis["db_value"].map(won), "원문 값": mis["src_value"].map(won),
                            "원인": mis["원인"], "원문": mis["src_title"] + " " + mis["src_rcept_no"]}
                           ).sort_values(["연도", "회사"], ascending=[False, True])

    unread = v[v["result"].isin([dv.UNREADABLE, dv.NO_REPORT])].copy()
    unread["이유"] = (unread["check_result"].fillna("") + " " + unread["note"].fillna("")).str.strip().map(
        lambda s: re.sub(r"[\d,.\-+]{4,}", "#", s)[:60])
    unread_tbl = unread.groupby(["result", "이유"]).size().reset_index(name="칸 수").sort_values("칸 수", ascending=False)

    md = f"""# DART 원문 대조 결과 — 재무제표

- 실행: `.venv/bin/python -m scripts.verify_db` → 표 `core.core_dart_verify` ({len(v):,}칸), 이 문서: `scripts.report_dart_verify`
- 대조한 회사: **{done} / {n_corp}곳**
- 대상: 02 재무(지배주주 순이익·부채·자본, 2018~2025) · 04 배당금 지급(2023~2025) · 04-2 부채·자본총계(2023~2025). KRX 주가는 제외.
- 원문: 그 사업연도 **자기 사업보고서**(정정 포함 가장 최근 판, 재무제표 없는 [첨부정정]은 건너뜀)의 연결/별도 재무제표 당기 열.
- 검산: 재무상태표는 부채+자본=부채와자본총계, 연결 손익은 지배+비지배=당기순이익이 맞아야 원문 값으로 씀. 안 맞으면 '원문 못 읽음'.
- 일치(단위 반올림): DB가 백만 원 단위라 원문 원 단위 값과 반올림 차이만 있음.
- 불일치이면 DB 값이 ① 다른 기준(연결↔별도) ② 정정 전 원공시 ③ 다음 해 보고서 비교기간(재작성) 값과 같은지 찾아 '원인'에 적음.
- **원본 표는 고치지 않았습니다.** 불일치 칸을 원문 값으로 바꿔 본 값은 뷰 `core.v_financial_year_verified`·`core.v_dividend_year_verified`에 있고, 사람 검토표는 [DART_불일치_검토표.csv](DART_불일치_검토표.csv)입니다(구분: 확실·재작성 선택·사람 확인).

## 요약

{table(summary)}

## 02 재무 — 연도별

{table(by_year)}

## 불일치 원인

{table(causes)}

판정·최소액에 쓰는 2023~2025년 02 재무의 불일치: **{len(engine)}칸**

## 원문 못 읽음·원문 없음 이유

{table(unread_tbl)}

## 불일치 전체 ({len(mis)}칸, 최근 연도 순)

<details><summary>펼치기</summary>

{table(mis_tbl)}

</details>
"""
    OUT.write_text(md, encoding="utf-8")
    print(f"  {OUT.name}: {len(md.splitlines())}줄 · 회사 {done}곳 · {len(v):,}칸")


if __name__ == "__main__":
    main(db.database_url())
