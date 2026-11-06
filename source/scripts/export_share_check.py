"""주식 총수(발행·자기·유통) 검산표 → 엑셀 (API 값·보정값·이상치 사유, 자본금·PBR·배당 교차 대조, 원문 대조).

실행: .venv/bin/python -m scripts.export_share_check [--year 2025] [--out 파일] [--no-source]
자료: core.v_share_total_checked, core.core_share_check, raw.dart_share_total (source/scripts/collect_share_total.py → build_share_check.py 다음).
원문 대조 시트는 시연 10개사와 ÷1,000 보정 회사의 사업보고서 '주식의 총수 등' 표를 DART 원문(캐시)에서 읽는다.
검토자는 '주식총수'·'원문대조' 시트 맨 끝 노란 칸(검토 상태·검토자·메모)만 채운다. '진행현황' 시트는 엑셀 수식이라 채우는 대로 바뀐다.
"""
import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import db
from core import share_check as sc
from core import share_total as st
from scripts.build_share_check import FACTS

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "tables"
VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
FIXED = PatternFill("solid", fgColor="FCE4D6")
DIFF = PatternFill("solid", fgColor="FBEDEA")
FILL = PatternFill("solid", fgColor="FFFF00")
BOX = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
NUM = "#,##0;(#,##0);-"
DEC = "#,##0.00;(#,##0.00);-"

REVIEWERS = ["금민권", "박예지", "한상범", "김민지", "조진영"]
STATES = ["확인완료", "확인불가", "정정됨(배제)"]
REVIEW = [("검토 상태", 13), ("검토자", 10), ("메모", 40)]

MAIN = """
WITH div AS (
  SELECT corp_code,
         max(replace(value, ',', '')) FILTER (WHERE item = '현금배당금총액(백만원)') AS total_mil,
         max(replace(value, ',', '')) FILTER (WHERE item = '주당 현금배당금(원)' AND stock_kind IN ('보통주', '보통주식')) AS dps,
         count(*) FILTER (WHERE item = '주당 현금배당금(원)' AND stock_kind NOT IN ('보통주', '보통주식', '-')
                          AND value ~ '^[0-9,.]+$' AND replace(value, ',', '')::numeric > 0) AS other_dps
  FROM raw.dart_dividend_item WHERE bsns_year = %(y)s GROUP BY 1)
SELECT c.corp_name, c.corp_code, c.stock_code, c.market, v.stlm_dt,
       v.issued_api, v.treasury_api, v.floating_api, v.floating,
       coalesce(v."check", k."check", '자료 없음') AS "check", coalesce(v.action, k.action) AS action, k.reason,
       CASE WHEN div.other_dps = 0 AND div.total_mil ~ '^[0-9.]+$' AND div.dps ~ '^[0-9.]+$' AND div.dps::numeric > 0
            THEN div.total_mil::numeric * 1000000 / div.dps::numeric END AS implied,
       coalesce(v.rcept_no, (SELECT max(rcept_no) FROM raw.dart_share_total t WHERE t.corp_code = c.corp_code
                                                                              AND t.bsns_year = %(y)s)) AS rcept_no,
       c.corp_code IN (SELECT corp_code FROM core.core_demo_company) AS demo
FROM core.core_company c
LEFT JOIN core.v_share_total_checked v ON v.corp_code = c.corp_code AND v.bsns_year = %(y)s
LEFT JOIN core.core_share_check k ON k.corp_code = c.corp_code AND k.bsns_year = %(y)s
LEFT JOIN div ON div.corp_code = c.corp_code
ORDER BY c.corp_name
"""


def _f(v):
    return None if v is None else float(v)


def build(conn, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    facts = {f["corp_code"]: f for f in db.fetch_dicts(conn, FACTS, {"y": year, "r": st.ANNUAL})}
    rows = []
    for r in db.fetch_dicts(conn, MAIN, {"y": year}):
        f = facts.get(r["corp_code"], {})
        issued_all, par, capital = _f(f.get("issued_all")), _f(f.get("par")), _f(f.get("capital"))
        close, equity, floating_api = _f(f.get("close")), _f(f.get("equity")), _f(r["floating_api"])
        cap_calc = issued_all * par if issued_all and par else None
        ratio = cap_calc / capital if cap_calc and capital and capital > 0 else None
        pbr = close * floating_api / equity if close and floating_api and equity and equity > 0 else None
        implied, floating = _f(r["implied"]), _f(r["floating"])
        gap = (implied / floating - 1) * 100 if implied and floating else None
        rows.append({
            "회사명": r["corp_name"], "corp_code": r["corp_code"], "종목코드": r["stock_code"], "시장": r["market"],
            "시연 10개사": "○" if r["demo"] else "", "결산 기준일": r["stlm_dt"],
            "보통주 발행(API, 주)": _f(r["issued_api"]), "보통주 자기주식(API, 주)": _f(r["treasury_api"]),
            "보통주 유통(API, 주)": _f(r["floating_api"]), "보통주 유통(보정, 주)": floating,
            "판정": r["check"], "처리": r["action"], "사유": r["reason"],
            "전체 발행(주)": issued_all, "액면가(원)": par, "발행×액면(원)": cap_calc,
            "자본금(원)": capital, "자본금 비율": ratio, "종가(원)": close, "자본총계(원)": equity,
            "PBR(API 값)": pbr, "PBR(÷1,000)": pbr / 1000 if pbr else None,
            "배당총액÷주당배당금(주)": implied, "배당 교차 차이(%, 보정값 기준)": gap,
            "접수번호": r["rcept_no"], "원문": VIEW + r["rcept_no"] if r["rcept_no"] else None})
    raw = pd.DataFrame(db.fetch_dicts(conn, """
        SELECT c.corp_name AS "회사명", s.corp_code, s.se AS "주식 종류(받은 그대로)", s.share_class AS "묶은 종류",
               s.issued_raw AS "발행(받은 글자)", s.treasury_raw AS "자기(받은 글자)", s.floating_raw AS "유통(받은 글자)",
               s.issued AS "발행(주)", s.treasury AS "자기(주)", s.floating AS "유통(주)", s.floating_note AS "유통 메모",
               s.stlm_dt AS "결산 기준일", s.api_status AS "API 상태", s.rcept_no AS "접수번호"
        FROM raw.dart_share_total s JOIN core.core_company c USING (corp_code)
        WHERE s.bsns_year = %(y)s ORDER BY c.corp_name, s.se""", {"y": year}))
    return pd.DataFrame(rows), raw


def source_rows(df: pd.DataFrame) -> pd.DataFrame:
    """시연 10개사·보정 회사: 사업보고서 '주식의 총수 등' 표의 단위와 Ⅵ 유통주식수(첫 칸)를 API 값과 맞춰 본다."""
    from core import dart_doc as dd
    out = []
    pick = df[(df["시연 10개사"] == "○") | (df["처리"] == sc.FIX)]
    for r in pick.to_dict("records"):
        if not r["접수번호"]:
            continue
        _, nodes = dd.filing(r["접수번호"])
        sec = [n for n in nodes if re.search(r"주식의\s*총수", n.text)]
        lines = dd.section_lines(sec[:1]) if sec else []
        unit = next((m.group(1).strip() for ln in lines if (m := re.search(r"단위\s*:\s*([^,|)]*)", ln))), None)
        row = next((ln for ln in lines if "유통주식수" in ln and "|" in ln), "")
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+|\b\d+\b", row.split("|", 1)[1])] if row else []
        src = next((n for n in nums if n > 0), None)
        api, fixed = r["보통주 유통(API, 주)"], r["보통주 유통(보정, 주)"]
        result = ("확인 못 함" if src is None or api is None else "API = 원문" if api == src
                  else "API = 원문 × 1,000" if api == src * 1000 else "다름")
        out.append({"회사명": r["회사명"], "시연 10개사": r["시연 10개사"], "원문 표 단위": unit, "원문 Ⅵ 유통주식수(주)": src,
                    "API 유통(주)": api, "보정 유통(주)": fixed, "API와 원문": result,
                    "보정값 = 원문": ("예" if src is not None and fixed == src else "아니오") if fixed is not None else None,
                    "원문 줄": row[:200], "원문": VIEW + r["접수번호"]})
    return pd.DataFrame(out)


def _sheet(wb, title: str, df: pd.DataFrame, widths: dict, fill=None, freeze="C2", review=False):
    ws = wb.create_sheet(title)
    cols = list(df.columns)
    for j, c in enumerate(cols, 1):
        h = ws.cell(1, j, c)
        h.font, h.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
        h.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = widths.get(c, 16 if re.search(r"\((원|주)\)|원\)|주\)", c) else 12)
    for i, r in enumerate(df.itertuples(index=False), 2):
        for j, (c, v) in enumerate(zip(cols, r), 1):
            v = None if isinstance(v, float) and pd.isna(v) else v
            cell = ws.cell(i, j, v)
            cell.font = Font(name=F, size=10)
            if isinstance(v, (int, float)):
                cell.number_format = DEC if c in ("자본금 비율", "PBR(API 값)", "PBR(÷1,000)", "배당 교차 차이(%, 보정값 기준)") else NUM
            if c == "원문" and v:
                cell.hyperlink, cell.value = v, "원문 열기"
                cell.font = Font(name=F, size=10, color="0563C1", underline="single")
        if fill:
            color = fill(dict(zip(cols, r)))
            if color:
                for j in range(1, len(cols) + 1):
                    ws.cell(i, j).fill = color
    if review:
        _review_cols(ws, len(cols), len(df) + 1)
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions
    return ws


def _review_cols(ws, n_cols: int, last: int):
    """맨 끝에 검토 상태·검토자·메모 노란 칸. 검토 상태·검토자는 목록에서 고른다."""
    for k, (name, width) in enumerate(REVIEW, n_cols + 1):
        h = ws.cell(1, k, name)
        h.font, h.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
        h.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(k)].width = width
        for i in range(2, last + 1):
            c = ws.cell(i, k)
            c.fill, c.font, c.border = FILL, Font(name=F, size=10), BOX
    for k, options in ((n_cols + 1, STATES), (n_cols + 2, REVIEWERS)):
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True, showErrorMessage=True,
                            errorTitle="목록에서 고르기", error=", ".join(options) + " 중에서 고르세요")
        dv.add(f"{get_column_letter(k)}2:{get_column_letter(k)}{max(last, 2)}")
        ws.add_data_validation(dv)


def _progress(wb, sheets: list[tuple[str, int, int]], groups: list[tuple[str, str, str]]):
    """sheets: (시트, 행 수, 검토 상태 열 번호). groups: (구분 이름, 시트, '판정' 같은 조건 열 글자=값)."""
    ws = wb.create_sheet("진행현황", 1)
    head = ["구분", "전체 행"] + STATES + ["미검토", "진행률"] + REVIEWERS
    for j, h in enumerate(head, 1):
        c = ws.cell(1, j, h)
        c.font, c.fill, c.border = Font(name=F, bold=True, color="FFFFFF"), HEAD, BOX
        c.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = 30 if j == 1 else 11
    info = {name: (n, col) for name, n, col in sheets}
    rows = [(name, name, None) for name, _, _ in sheets] + groups
    for i, (label, sheet, cond) in enumerate(rows, 2):
        n, col = info[sheet]
        rng = lambda k: f"'{sheet}'!${get_column_letter(k)}$2:${get_column_letter(k)}${n + 1}"
        where, total = "", n
        if cond:
            k, val = cond.split("=", 1)
            where, total = f',{rng(int(k))},"{val}"', f'=COUNTIFS({rng(int(k))},"{val}")'
        vals = [label, total] + [f'=COUNTIFS({rng(col)},"{s}"{where})' for s in STATES]
        vals += [f"=B{i}-SUM(C{i}:E{i})", f"=IF(B{i}=0,0,SUM(C{i}:E{i})/B{i})"]
        vals += [f'=COUNTIFS({rng(col + 1)},"{p}"{where})' for p in REVIEWERS]
        for j, v in enumerate(vals, 1):
            c = ws.cell(i, j, v)
            c.font, c.border = Font(name=F, size=10, bold=cond is None), BOX
            c.number_format = "0.0%" if j == 7 else NUM
    ws.freeze_panes = "B2"


def write(main: pd.DataFrame, raw: pd.DataFrame, src: pd.DataFrame | None, out: Path, year: int):
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "주식총수", main, {"회사명": 16, "판정": 18, "사유": 60, "원문": 10},
           lambda r: FIXED if r["처리"] == sc.FIX else DIFF if r["처리"] == sc.MARK else None, review=True)
    reviewed = [("주식총수", len(main), len(main.columns) + 1)]
    if src is not None and len(src):
        _sheet(wb, "원문대조", src, {"회사명": 16, "API와 원문": 18, "원문 줄": 60, "원문": 10},
               lambda r: FIXED if r["API와 원문"] != "API = 원문" else None, freeze="B2", review=True)
        reviewed.append(("원문대조", len(src), len(src.columns) + 1))
    _sheet(wb, "주식종류별 원자료", raw, {"회사명": 16, "주식 종류(받은 그대로)": 28, "유통 메모": 30})
    counts = main["판정"].value_counts()
    verdict_col = list(main.columns).index("판정") + 1
    demo_col = list(main.columns).index("시연 10개사") + 1
    groups = [(f"  주식총수 · 판정 {k}", "주식총수", f"{verdict_col}={k}") for k in counts.index]
    groups.append(("  주식총수 · 시연 10개사", "주식총수", f"{demo_col}=○"))
    g = wb.create_sheet("안내", 0)
    notes = [("무엇", f"{year} 사업연도 사업보고서 기준 보통주 발행·자기·유통 주식수와 검산 결과 ({len(main)}사)"),
             ("출처", "OpenDART 주식의 총수 현황(stockTotqySttus) → raw.dart_share_total. 원본은 고치지 않음"),
             ("보정값", "core.v_share_total_checked.floating = API 값 × 보정 배수(core.core_share_check.factor, 정상이면 1)"),
             ("판정", " · ".join(f"{k} {v}곳" for k, v in counts.items())),
             ("자본금 비율", "(보통+우선·종류+기타 발행주식수, API 값) × 주당 액면가 ÷ 자본금(재무상태표, 별도 우선). 1% 안이면 '자본금 일치'. 근거 열은 모든 회사에 계산해 둠"),
             ("÷1,000 보정 (주황)", "자본금 비율이 1,000배(±0.1%)이고, PBR(종가 × 보통주 유통 ÷ 자본총계)이 API 값으로 100 넘고 ÷1,000 하면 100 이하일 때만. "
                                   "회사가 사업보고서 표 단위를 '천주'로 잘못 적어 API 값이 1,000배가 된 경우"),
             ("표시만 (분홍)", "자본금과 차이·대조 불가·보통주 행 없음. 값은 그대로 쓰고 사유만 적음. 이익소각(주식은 줄고 자본금은 그대로) 등으로 생길 수 있으나 회사별 원인은 미확인"),
             ("배당 교차", "2025 현금배당총액(백만 원) ÷ 보통주 주당 현금배당금 → 배당 받은 주식 수 추정, 보정 유통주식수와 비교. 우선·종류주 배당이 있는 회사는 비움. "
                          "중간배당·기준일 차이·배당 자료 오류로도 차이가 남"),
             ("원문대조 시트", "시연 10개사와 ÷1,000 보정 회사: 사업보고서 '주식의 총수 등' 표의 단위와 Ⅵ 유통주식수(첫 칸)를 API 값과 맞춤"),
             ("검토하는 법", "'주식총수'·'원문대조' 시트에서 행마다 원문 링크·근거 열을 보고, 맨 끝 노란 칸만 채웁니다. 다른 칸은 DB 값이라 고치지 않습니다."),
             ("검토 상태 뜻", "확인완료 = 보정값(유통주식수)이 원문과 같음 · 확인불가 = 원문을 못 찾거나 판단 못 함 · "
                           "정정됨(배제) = 보정값이 틀려 이 값을 쓰면 안 됨(메모에 원문 값)"),
             ("검토자", " · ".join(REVIEWERS) + " 중 목록에서 고름"),
             ("메모", "틀린 칸과 원문 값, 판단 근거. 예: 유통주식수 원문 8,626,833주 = 보정값과 같음 (사업보고서 4. 주식의 총수 등 Ⅵ)"),
             ("나눠 보기", "필터로 판정·시연 10개사를 골라 나눠 보면 됩니다. 먼저 볼 곳: 판정 'API 단위 오류(1,000배)'·'자본금과 차이', 시연 10개사. "
                         "진행 정도는 '진행현황' 시트(수식)가 보여 줍니다"),
             ("만든 날", f"{date.today().isoformat()} · source/scripts/export_share_check.py · 판정 규칙 {sc.RULE}")]
    for i, (a, b) in enumerate(notes, 1):
        g.cell(i, 1, a).font = Font(name=F, bold=True)
        g.cell(i, 2, b).font = Font(name=F)
        g.cell(i, 2).alignment = Alignment(wrap_text=True, vertical="top")
        if a in ("검토하는 법", "검토 상태 뜻"):
            g.cell(i, 2).fill = FILL
    g.column_dimensions["A"].width, g.column_dimensions["B"].width = 20, 120
    _progress(wb, reviewed, groups)
    wb.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="주식 총수 검산표를 엑셀로 내보냄")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--out", type=Path, default=OUT_DIR / f"주식총수_검산표_{date.today():%Y%m%d}.xlsx")
    ap.add_argument("--no-source", action="store_true", help="원문대조 시트를 만들지 않음 (DART 원문을 읽지 않음)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        main, raw = build(conn, a.year)
    src = None if a.no_source else source_rows(main)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    write(main, raw, src, a.out, a.year)
    print(a.out, f"{len(main)}사 · " + " · ".join(f"{k} {v}" for k, v in main["판정"].value_counts().items()))
    if src is not None:
        print("  원문대조:", " · ".join(f"{k} {v}" for k, v in src["API와 원문"].value_counts().items()))
