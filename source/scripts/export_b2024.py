"""2024 사업연도 배당소득 B(2024) 자료 → 엑셀 한 장 (KIND 고배당기업 공시 원문 값 + DART 현금배당총액 D 비교).

실행: .venv/bin/python -m scripts.export_b2024 [--out 파일]
B(2024)는 회사가 KIND 고배당기업 공시에 적은 '2024.12.31.이 속하는 사업연도의 배당소득'(raw.kind_list.b2024_won).
DB에 없는 칸은 원문 재대조(core.core_source_verify)에서 읽은 원문 값으로 채워 따로 표시한다. 원본 표는 고치지 않는다.
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core import db

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "tables"
F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
FILLED = PatternFill("solid", fgColor="FFF6DD")
DIFF = PatternFill("solid", fgColor="FBEDEA")
NUM = "#,##0;(#,##0);-"
TOL = 1_000_000  # D는 백만 원 단위라 이만큼은 같은 값으로 봄


def num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def build(conn) -> pd.DataFrame:
    k = pd.DataFrame(db.fetch_dicts(conn, """
        SELECT k.corp_code, c.corp_name, c.stock_code, c.market, k.is_high_dividend, k.b2024_won, k.prev_year,
               k.prev_d_won, k.prevprev_d_won, k.reduction_note, k.final_rcept_no, k.final_disclosed_on, k.link,
               d.d_dart_won AS d2024, d.d_decision_won AS dec2024, d.cf_paid_won AS cf2024
        FROM raw.kind_list k JOIN core.core_company c USING (corp_code)
        LEFT JOIN core.core_dividend_year d ON d.corp_code = k.corp_code AND d.bsns_year = 2024"""))
    chk = {r["corp_code"]: r for r in db.fetch_dicts(conn, """
        SELECT corp_code, result, src_value FROM core.core_source_verify WHERE target = 'kind_list' AND item = 'b2024_won'""")}
    rows = []
    for r in k.itertuples():
        v = chk.get(r.corp_code, {})
        src = num(v.get("src_value"))
        b, how = (float(r.b2024_won), "KIND 공시 (DB 원천 09)") if r.b2024_won is not None else (
            (src, "KIND 공시 원문 (DB 빈칸, 원문 재대조에서 읽음)") if src is not None else (None, "없음"))
        d = float(r.d2024) if r.d2024 is not None else None
        if b is None or d is None:
            rel = "비교 불가"
        elif abs(b - d) <= TOL:
            rel = "B = D (감액배당·주식배당 없음으로 보임)"
        elif b < d:
            rel = "B < D (감액배당 등을 뺀 것으로 보임)"
        else:
            rel = "B > D (주식배당 등을 더한 것으로 보임)"
        rows.append({"회사명": r.corp_name, "corp_code": r.corp_code, "종목코드": r.stock_code, "시장": r.market,
                     "고배당기업 여부": r.is_high_dividend, "B(2024) 배당소득(원)": b, "B 출처": how,
                     "원문 재대조": v.get("result", "재대조 안 함"),
                     "D(2024) 현금배당총액(원)": d, "B − D(원)": (b - d) if b is not None and d is not None else None,
                     "B와 D 관계": rel,
                     "2024 배당 결정 공시 합계(원)": float(r.dec2024) if r.dec2024 is not None else None,
                     "2024 현금흐름표 배당금 지급(원)": float(r.cf2024) if r.cf2024 is not None else None,
                     "감액배당 메모(공시 원문)": r.reduction_note, "공시 접수번호": r.final_rcept_no,
                     "공시일": str(r.final_disclosed_on or ""), "원문": r.link})
    return pd.DataFrame(rows).sort_values("회사명")


def write(df: pd.DataFrame, out: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "B2024"
    cols = list(df.columns)
    widths = {"회사명": 16, "B 출처": 30, "B와 D 관계": 30, "감액배당 메모(공시 원문)": 50, "원문": 12}
    for j, c in enumerate(cols, 1):
        h = ws.cell(1, j, c)
        h.font, h.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
        h.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = widths.get(c, 17 if "(원)" in c else 12)
    for i, r in enumerate(df.itertuples(index=False), 2):
        for j, (c, v) in enumerate(zip(cols, r), 1):
            v = None if isinstance(v, float) and pd.isna(v) else v
            cell = ws.cell(i, j, v)
            cell.font = Font(name=F, size=10)
            if "(원)" in c:
                cell.number_format = NUM
            if c == "원문" and v:
                cell.hyperlink, cell.value = v, "원문 열기"
                cell.font = Font(name=F, size=10, color="0563C1", underline="single")
        if "DB 빈칸" in r[cols.index("B 출처")]:
            ws.cell(i, cols.index("B(2024) 배당소득(원)") + 1).fill = FILLED
        if not str(r[cols.index("B와 D 관계")]).startswith("B = D"):
            ws.cell(i, cols.index("B와 D 관계") + 1).fill = DIFF
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    g = wb.create_sheet("안내")
    notes = [("B(2024)", "회사가 KIND 고배당기업 공시에 적은 '2024.12.31.이 속하는 사업연도의 배당소득'. 2027 판정의 기준 배당소득"),
             ("출처", "raw.kind_list.b2024_won (09 KIND 고배당공시 원문 대조 자료). DB가 빈 칸은 DART 공시 원문에서 다시 읽은 값 (노란색)"),
             ("원문 재대조", "core.core_source_verify: 코드가 그 공시 원문을 다시 읽어 B 칸을 맞춰 본 결과"),
             ("D(2024)", "사업보고서 배당 표 현금배당금총액 (core.core_dividend_year.d_dart_won, 백만 원 단위라 100만 원 미만 차이는 같음)"),
             ("B와 D 관계", "PRD v0.2: B = 현금배당 − 비과세로 확인된 감액배당 + 주식배당. B와 D가 다르면(분홍) 감액배당·주식배당 여부를 공시 원문에서 확인"),
             ("만든 날", f"{date.today().isoformat()} · source/scripts/export_b2024.py")]
    for i, (a, b) in enumerate(notes, 1):
        g.cell(i, 1, a).font = Font(name=F, bold=True)
        g.cell(i, 2, b).font = Font(name=F)
    g.column_dimensions["A"].width, g.column_dimensions["B"].width = 14, 110
    wb.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="2024 배당소득 B 자료를 엑셀로 내보냄")
    ap.add_argument("--out", type=Path, default=OUT_DIR / f"B2024_배당소득_{date.today():%Y%m%d}.xlsx")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        df = build(conn)
    write(df, a.out)
    print(a.out, f"{len(df)}사 · B 있음 {df['B(2024) 배당소득(원)'].notna().sum()} · " +
          " · ".join(f"{k} {v}" for k, v in df["B와 D 관계"].value_counts().items()))
