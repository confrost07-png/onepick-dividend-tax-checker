"""증자·감자·분할·병합 공시마다 그 회사의 배당이 전년보다 늘었는지 → 엑셀 (output/tables/증자감자_배당증감_YYYYMMDD.xlsx).

실행: .venv/bin/python -m scripts.capital_dividend_change [--out 파일]
- 주식 수가 바뀐 날: 무상증자 = 신주배정기준일, 분할·병합 = 효력발생일(없으면 공시일), 유상증자·감자 = 공시일
- 비교 연도 T: 그 날 이후 처음 오는 결산배당 기준일의 사업연도 (기준일 공시가 없으면 그해 12월 31일로 봄)
- 총액: 사업보고서 현금배당총액 D(T) ↔ D(T−1) (core.v_dividend_year_verified)
- 주당: 보통주 주당배당금 DPS(T) ↔ DPS(T−1) ÷ 조정 계수. 계수 = 무상증자 (기존 + 신주) ÷ 기존 주식 수,
  분할·병합 변경 전 액면 ÷ 변경 후 액면. 유상증자·감자는 주당 금액을 기계적으로 바꾸지 않아 계수 1
- T가 아직 끝나지 않은 해(D 없음)면 그해 배당 결정 공시 합계 누계 ↔ 전년 같은 날짜까지 누계로 비교 ('진행 중')
"""
import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core import db
from core.event_study import capital_events

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "tables"
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
COLOR = {"증가": "C00000", "감소": "1F4EA8"}


def kdate(s) -> date | None:
    """'2025년 01월 01일' · '2025-01-01' · '2025.01.01' → date."""
    if s is None:
        return None
    if isinstance(s, date):
        return s
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(s))
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    except ValueError:
        return None


def change(now, before, tol=0.0) -> str:
    if now is None or before is None or pd.isna(now) or pd.isna(before):
        return "자료 없음"
    if abs(float(now) - float(before)) <= tol:
        return "유지"
    return "증가" if float(now) > float(before) else "감소"


def build(conn) -> pd.DataFrame:
    cap = db.fetch_dicts(conn, "SELECT * FROM raw.dart_capital_event")
    split = db.fetch_dicts(conn, "SELECT * FROM raw.dart_split_merge")
    name = {r["corp_code"]: r["corp_name"] for r in db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_company")}
    div = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, """
        SELECT corp_code, bsns_year, d_dart_won, dps_common_won FROM core.v_dividend_year_verified""")}
    decisions = pd.DataFrame(db.fetch_dicts(conn, """
        SELECT corp_code, attributed_year, div_kind, record_date, disclosed_on, total_won, rcept_no FROM raw.dividend_decision
        WHERE parse_status = '정상' AND div_type LIKE '현금%%'"""))
    decisions["record"] = decisions["record_date"].map(kdate)
    decisions["disclosed_on"] = pd.to_datetime(decisions["disclosed_on"]).dt.date
    final_record = {(r.corp_code, r.attributed_year): r.record for r in decisions[decisions["div_kind"] == "결산배당"].itertuples()
                    if r.record}
    by_rcept = {r["rcept_no"]: r for r in cap}
    by_rcept.update({r["rcept_no"]: r for r in split})
    rows = []
    for e in capital_events(cap, split):
        src = by_rcept[e.rcept_no]
        announced = e.disclosed_at.date()
        factor, changed_on = 1.0, announced
        if e.kind == "무상증자":
            before, new = src.get("before_common"), src.get("shares_common")
            if before and new:
                factor = (float(before) + float(new)) / float(before)
            elif src.get("per_share_common"):
                factor = 1 + float(src["per_share_common"])
            changed_on = kdate(src.get("record_date")) or announced
        elif e.kind in ("주식분할", "주식병합"):
            if src.get("par_before_won") and src.get("par_after_won"):
                factor = float(src["par_before_won"]) / float(src["par_after_won"])
            changed_on = kdate(src.get("effective_date")) or announced
        y = changed_on.year
        rec = final_record.get((e.corp_code, y)) or date(y, 12, 31)
        target = y if changed_on <= rec else y + 1
        now, prev = div.get((e.corp_code, target), {}), div.get((e.corp_code, target - 1), {})
        d_now, d_prev = now.get("d_dart_won"), prev.get("d_dart_won")
        how = "사업보고서 현금배당총액"
        if d_now is None:  # 그해 배당이 아직 확정 전: 결정 공시 누계 ↔ 전년 같은 날짜까지
            cut = date.today()
            mine = decisions[decisions["corp_code"] == e.corp_code]
            ytd = mine[(mine["attributed_year"] == target)]["total_won"].astype(float).sum()
            same = mine[(mine["attributed_year"] == target - 1)
                        & (mine["disclosed_on"] <= date(cut.year - (cut.year - target) - 1, cut.month, min(cut.day, 28)))]
            d_now = ytd if len(mine[mine["attributed_year"] == target]) else None
            d_prev = same["total_won"].astype(float).sum() if d_now is not None else None
            how = f"진행 중: {target} 결정 공시 누계 ↔ {target - 1} 같은 날짜까지 누계" if d_now is not None else "그해 배당 아직 없음"
        dps_now, dps_prev = now.get("dps_common_won"), prev.get("dps_common_won")
        adj_prev = float(dps_prev) / factor if dps_prev is not None else None
        rows.append({"회사명": name.get(e.corp_code, e.corp_code), "corp_code": e.corp_code, "공시 종류": e.kind,
                     "공시일": announced, "주식 수 바뀐 날": changed_on, "비교 사업연도": target,
                     "시점": "그해 결산배당 기준일 전" if target == y else "그해 결산배당 기준일 뒤 → 다음 해 배당과 비교",
                     "배당 총액(원)": float(d_now) if d_now is not None else None,
                     "전년 총액(원)": float(d_prev) if d_prev is not None else None,
                     "총액 증감": change(d_now, d_prev, tol=1_000_000), "총액 기준": how,
                     "보통주 DPS(원)": float(dps_now) if dps_now is not None else None,
                     "전년 DPS(원)": float(dps_prev) if dps_prev is not None else None,
                     "주식 수 조정 계수": round(factor, 4), "조정한 전년 DPS(원)": round(adj_prev, 2) if adj_prev is not None else None,
                     "DPS 증감(조정)": change(dps_now, adj_prev, tol=0.5), "DPS 증감(조정 전)": change(dps_now, dps_prev),
                     "접수번호": e.rcept_no, "원문": DART + e.rcept_no})
    return pd.DataFrame(rows).sort_values(["공시 종류", "공시일", "회사명"])


def write(df: pd.DataFrame, out: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    r0 = 1
    for col in ("총액 증감", "DPS 증감(조정)"):
        t = pd.crosstab(df["공시 종류"], df[col]).reindex(columns=["증가", "유지", "감소", "자료 없음"], fill_value=0)
        ws.cell(r0, 1, f"{col} (공시 건수)").font = Font(name=F, bold=True, size=12)
        r0 += 1
        for j, h in enumerate(["공시 종류"] + list(t.columns), 1):
            c = ws.cell(r0, j, h)
            c.font, c.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
        for kind, vals in t.iterrows():
            r0 += 1
            ws.cell(r0, 1, kind).font = Font(name=F)
            for j, (h, v) in enumerate(vals.items(), 2):
                ws.cell(r0, j, int(v)).font = Font(name=F, color=COLOR.get(h, "000000"))
        r0 += 2
    notes = ["비교 사업연도: 주식 수가 바뀐 날 뒤 처음 오는 결산배당 기준일의 사업연도 (기준일 공시가 없으면 12월 31일)",
             "총액: 사업보고서 현금배당총액 D (백만 원 단위라 100만 원 이하 차이는 유지). 확정 전 연도는 결정 공시 누계 비교",
             "DPS 조정: 무상증자 (기존+신주)÷기존, 분할·병합 변경 전 액면÷변경 후 액면으로 전년 DPS를 나눔. 유상증자·감자는 1",
             "증가는 붉은색, 감소는 푸른색. 코드: source/scripts/capital_dividend_change.py"]
    for n in notes:
        ws.cell(r0, 1, n).font = Font(name=F, size=9, color="555555")
        r0 += 1
    ws.column_dimensions["A"].width = 24
    d = wb.create_sheet("공시별")
    cols = list(df.columns)
    for j, h in enumerate(cols, 1):
        c = d.cell(1, j, h)
        c.font, c.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
        c.alignment = Alignment(wrap_text=True)
        d.column_dimensions[get_column_letter(j)].width = 16 if "(원)" in h else 12
    for i, r in enumerate(df.itertuples(index=False), 2):
        for j, (h, v) in enumerate(zip(cols, r), 1):
            v = None if isinstance(v, float) and pd.isna(v) else v
            c = d.cell(i, j, v)
            c.font = Font(name=F, size=10, color=COLOR.get(v, "000000") if "증감" in h else "000000")
            if "(원)" in h:
                c.number_format = "#,##0"
            if h == "원문" and v:
                c.hyperlink, c.value = v, "원문 열기"
                c.font = Font(name=F, size=10, color="0563C1", underline="single")
    d.freeze_panes = "C2"
    d.auto_filter.ref = d.dimensions
    wb.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="증자·감자·분할·병합 공시별 배당 증감")
    ap.add_argument("--out", type=Path, default=OUT_DIR / f"증자감자_배당증감_{date.today():%Y%m%d}.xlsx")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        df = build(conn)
    write(df, a.out)
    print(a.out, f"{len(df)}건")
    for col in ("총액 증감", "DPS 증감(조정)"):
        print(pd.crosstab(df["공시 종류"], df[col]).to_string(), "\n")
    print(df["총액 기준"].value_counts().to_string())
