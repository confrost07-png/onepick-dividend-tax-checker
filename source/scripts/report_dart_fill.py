"""core.core_dart_fill → report/검증/DART_빈칸_채우기_결과.md (사람이 볼 표). 숫자는 모두 DB에서 센다.

실행: .venv/bin/python -m scripts.report_dart_fill
"""
from pathlib import Path

import pandas as pd

from core import db

OUT = Path(__file__).resolve().parents[2] / "report" / "검증" / "DART_빈칸_채우기_결과.md"
GROUP = {"ni_owner_won": "① 재무", "liabilities_won": "① 재무", "equity_won": "① 재무", "decision": "② 배당 결정 원공시",
         "dps_common_won": "③ 주당배당금", "cf_paid_won": "④ 현금흐름표 배당금 지급", "ofs": "⑤ 별도 자료 남은 빈칸",
         "d_dart_won": "⑥ 현금배당총액 D"}
STATUS = ["채움", "무배당 확인", "원문도 비어 있음", "계산 대상 아님", "정책 대기", "사업보고서 없음", "확인 필요"]
BLANKS = [("지배주주 순이익", "core.core_financial_year", "core.v_financial_year_filled", "ni_owner_won"),
          ("부채총계", "core.core_financial_year", "core.v_financial_year_filled", "liabilities_won"),
          ("자본총계", "core.core_financial_year", "core.v_financial_year_filled", "equity_won"),
          ("현금배당총액 D", "core.core_dividend_year", "core.v_dividend_year_filled", "d_dart_won"),
          ("보통주 주당배당금", "core.core_dividend_year", "core.v_dividend_year_filled", "dps_common_won")]


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(x) else str(x).replace("|", "\\|") for x in r) + " |")
    return "\n".join(out)


def won(v):
    return "" if pd.isna(v) else f"{float(v):,.0f}"


def main(url: str):
    with db.connect(url) as conn:
        f = pd.DataFrame(db.fetch_dicts(conn, """
            SELECT f.*, coalesce(c.corp_name, '') AS corp_name FROM core.core_dart_fill f
            LEFT JOIN core.core_company c USING (corp_code)"""))
        fin = db.fetch_dicts(conn, """
            SELECT (SELECT count(*) FROM core.core_financial_year WHERE bsns_year BETWEEN 2023 AND 2025
                    AND (ni_owner_won IS NULL OR liabilities_won IS NULL OR equity_won IS NULL)) AS before,
                   (SELECT count(*) FROM core.v_financial_year_filled WHERE bsns_year BETWEEN 2023 AND 2025
                    AND (ni_owner_won IS NULL OR liabilities_won IS NULL OR equity_won IS NULL)) AS after""")[0]
        blanks = []
        for label, orig, view, col in BLANKS:
            for r in db.fetch_dicts(conn, f"""
                SELECT o.bsns_year, count(*) FILTER (WHERE o.{col} IS NULL) AS before,
                       count(*) FILTER (WHERE v.{col} IS NULL) AS after,
                       count(*) FILTER (WHERE o.{col} IS NULL AND f.status = '사업보고서 없음') AS no_report
                FROM {orig} o JOIN {view} v USING (corp_code, bsns_year)
                LEFT JOIN core.core_dart_fill f ON f.corp_code = o.corp_code AND f.bsns_year = o.bsns_year AND f.item = '{col}'
                WHERE o.bsns_year BETWEEN 2017 AND 2025 GROUP BY 1 ORDER BY 1"""):
                blanks.append({"항목": label, "사업연도": r["bsns_year"], "채우기 전 빈칸": r["before"], "채운 뒤 빈칸": r["after"],
                               "그중 사업보고서 없음": r["no_report"]})
        dec = pd.DataFrame(db.fetch_dicts(conn, """
            SELECT c.corp_name, f.bsns_year, f.value_won, d.d_dart_won, f.source_rcept_no, f.note
            FROM core.core_dart_fill f JOIN core.core_company c USING (corp_code)
            LEFT JOIN core.core_dividend_year d ON d.corp_code = f.corp_code AND d.bsns_year = f.bsns_year
            WHERE f.item = 'decision.total_won' ORDER BY 1"""))
    f["묶음"] = f["item"].map(lambda i: GROUP.get(i.split(".")[0], i))
    f["회사"] = f["corp_name"].where(f["corp_name"] != "", f["corp_code"])
    summary = f.pivot_table(index="묶음", columns="status", values="item", aggfunc="count", fill_value=0)
    summary = summary.reindex(columns=[s for s in STATUS if s in summary.columns]).reset_index()
    summary["합계"] = summary.drop(columns="묶음").sum(axis=1)

    filled = f[(f["status"] == "채움") & ~f["item"].str.startswith("ofs.") & ~f["item"].str.startswith("decision.")]
    filled_tbl = pd.DataFrame({"회사": filled["회사"], "연도": filled["bsns_year"], "항목": filled["item"],
                               "채운 값(원)": filled["value_won"].map(won), "열": filled["column_kind"],
                               "검산": filled["check_result"], "원문": filled["source_title"]}).sort_values(["항목", "회사", "연도"])
    review = f[f["status"] == "확인 필요"]
    review_main = review[~review["item"].str.startswith("ofs.")]
    review_tbl = pd.DataFrame({"회사": review_main["회사"], "연도": review_main["bsns_year"], "항목": review_main["item"],
                               "이유": review_main["note"].fillna("").where(review_main["note"].fillna("") != "",
                                                                         review_main["check_result"])}).sort_values(["항목", "회사"])
    ofs = f[f["item"].str.startswith("ofs.")]
    ofs_tbl = ofs.pivot_table(index="item", columns="status", values="corp_code", aggfunc="count", fill_value=0).reset_index()
    ofs_tbl = ofs_tbl.rename(columns={"item": "별도 자료 항목"})
    ofs_review = ofs[ofs["status"] == "확인 필요"]["note"].value_counts().reset_index()
    ofs_review.columns = ["확인 필요 이유", "칸 수"]
    dec["비교"] = (dec["value_won"].astype(float) / dec["d_dart_won"].astype(float) * 100).round(1).astype(str) + "%"
    dec_tbl = pd.DataFrame({"회사": dec["corp_name"], "사업연도": dec["bsns_year"], "원공시 배당금총액(원)": dec["value_won"].map(won),
                            "사업보고서 현금배당총액(원)": dec["d_dart_won"].map(won), "비교": dec["비교"],
                            "원공시 접수번호": dec["source_rcept_no"]})

    md = f"""# DART 원문으로 DB 빈칸 채우기 결과

- 실행: `.venv/bin/python -m scripts.fill_from_dart` → 표 `core.core_dart_fill` ({len(f):,}행), 이 문서: `scripts.report_dart_fill`
- **원본 표는 고치지 않았습니다.** 채운 값은 `core.core_dart_fill`에만 있고, 뷰 `core.v_financial_year_filled`·`core.v_dividend_year_filled`가 원본이 빈 칸에만 '채움' 값을 끼워 넣으며 `filled_items` 열에 어느 칸을 채웠는지 적습니다.
- 방법: DART 원문(사업보고서·배당 결정 공시)을 받아 ① 공시 제목의 회사가 맞는지 ② 표 머리의 연도 열·단위 ③ **같은 표 안의 합계로 검산**(부채+자본=부채와자본총계, 지배+비지배=당기순이익)이 맞을 때만 '채움'으로 둡니다. 다음 해 보고서의 비교기간 열에서 읽은 값은 열 칸에 '비교기간(재작성 가능)'으로 표시합니다.
- 상태: 채움 · 무배당 확인 · 원문도 비어 있음 · 계산 대상 아님 · 정책 대기(값을 넣지 않는 것이 맞음) · 확인 필요(사람이 볼 칸)

## 요약

{table(summary)}

판정·최소액에 쓰는 2023~2025년 재무(순이익·부채·자본) 중 빈 칸이 있는 회사·연도: **{fin['before']}행 → {fin['after']}행**

## 연도별 빈칸 전후 (2017~2025)

'사업보고서 없음'은 DART 사업보고서 검색에 그 해 보고서가 없고(상장 전 등) 뒤 보고서 비교기간에서도 값을 못 찾은 칸입니다.
현금흐름표 배당금 지급(04)은 2023년부터, 배당 결정 공시(05)는 2023년 1월 접수분부터 모은 자료라 그 앞 연도는 채우기 대상이 아닙니다.

{table(pd.DataFrame(blanks))}

## ② 배당 결정 원공시 (DB에 '[첨부정정]'만 있던 10건)

[첨부정정] 공시는 이사회 의사록 공개 여부만 고친 것이라 숫자가 없습니다. 같은 회사의 두 달 안 '현금ㆍ현물배당결정' 원공시를 찾아 읽었습니다. 결산배당 기준일이 다음 해 1~6월이면(2024년 제도 변경) 앞 사업연도로 봤습니다.

{table(dec_tbl)}

SK케미칼 2022는 원공시 결산배당이 사업보고서 연간 현금배당총액의 73%라 중간배당 등 다른 배당이 더 있는지 확인이 필요합니다.

## 확인 필요 (①~④)

{table(review_tbl)}

## 채운 값 (①·③·④)

{table(filled_tbl)}

## ⑤ 별도재무제표 보완 자료의 남은 빈칸

{table(ofs_tbl)}

- 무배당 확인: 배당 표가 '-'이고, 그 회사·연도의 현금배당 결정 공시가 DB(05 자료)에 없음 → 0으로 봄
- 계산 대상 아님: 별도 당기순이익이 0 이하라 배당성향을 계산하지 않음
- 정책 대기: 배당 표에 연결 주당순이익만 있는 회사의 별도 주당순이익 (팀 결정 필요)
- 현금배당성향 '채움'은 원문이 아니라 `현금배당금총액 ÷ 당기순이익 × 100`을 코드로 계산한 값

확인 필요 이유:

{table(ofs_review)}
"""
    OUT.write_text(md, encoding="utf-8")
    print(f"  {OUT.name}: {len(md.splitlines())}줄")


if __name__ == "__main__":
    main(db.database_url())
