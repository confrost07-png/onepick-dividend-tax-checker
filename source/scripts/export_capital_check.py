"""onepick DB 증자·감자·분할·병합 표 → 팀 검산용 엑셀 (source/scripts/load_capital.py로 적재한 뒤).

실행: .venv/bin/python -m scripts.export_capital_check [--out 파일] [--url postgresql://localhost/onepick]
시트: 안내 · 증자감자_최종본 · 분할병합 · 정정_앞선판. 노란 칸(검산결과·검산자·메모)만 검산자가 채운다.
'수식 검산' 열은 엑셀 수식이라 파일을 열 때 계산된다. 기본 저장 위치 data/raw/export/는 git에 올라가지 않는다.
"""
import argparse
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import db

EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "export"

F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
FILL = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
NUM = "#,##0;(#,##0);-"



def header(ws, cols, fill_from):
    for j, (name, width) in enumerate(cols, 1):
        c = ws.cell(1, j, name)
        c.font = Font(name=F, bold=True, color="000000" if j >= fill_from else "FFFFFF")
        c.fill = FILL if j >= fill_from else HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "D2"


def body(ws, i, values, numeric, link_col=None):
    for j, v in enumerate(values, 1):
        c = ws.cell(i, j, v)
        c.font = Font(name=F, size=10)
        c.border = BOX
        if j in numeric:
            c.number_format = NUM
    if link_col:
        c = ws.cell(i, link_col)
        c.hyperlink = c.value
        c.value = "원문 열기"
        c.font = Font(name=F, size=10, color="0563C1", underline="single")


def fill_cols(ws, n_rows, first, last):
    dv = DataValidation(type="list", formula1='"일치,불일치,확인 불가"', allow_blank=True)
    ws.add_data_validation(dv)
    col = get_column_letter(first)
    dv.add(f"{col}2:{col}{n_rows + 1}")
    for i in range(2, n_rows + 2):
        for j in range(first, last + 1):
            c = ws.cell(i, j)
            c.fill = FILL
            c.border = BOX
            c.font = Font(name=F, size=10)


def to_int(v):
    return int(v) if v is not None and v == int(v) else (float(v) if v is not None else None)


def build(conn, out: Path) -> dict[str, int]:
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    wb = Workbook()
    # ---- 안내
    ws = wb.active
    ws.title = "안내"
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 100
    counts = dict(q("select version, count(*) from raw.dart_capital_event group by 1"))
    n_split = q("select count(*) from raw.dart_split_merge")[0][0]
    rows = [
        ("증자·감자·액면분할·병합 공시 검산표", None),
        (None, None),
        ("만든 날", f"{date.today().isoformat()} (onepick DB raw.dart_capital_event · raw.dart_split_merge 에서 내보냄)"),
        ("대상 회사", "core.core_company 638사 (배당 분석 DB와 같은 목록)"),
        ("기간", "공시 접수일 2023-01-01 ~ 2026-10-20 (배당 결정 공시 자료와 같은 기간)"),
        ("출처", "증자·감자: OpenDART 주요사항보고서 API(piicDecsn·fricDecsn·pifricDecsn·crDecsn). "
                "API에 없는 6건과 분할·병합 전부는 DART 공시 원문 표를 코드로 읽음. 각 행 '원문 열기'가 그 공시."),
        ("시트", f"증자감자_최종본 {counts.get('API 최종본', 0) + counts.get('원문 최종본', 0)}건 · 분할병합 {n_split}건 · "
                f"정정_앞선판 {counts.get('앞선 판', 0) + counts.get('첨부만 정정', 0)}건(값 없음, 참고용)"),
        (None, None),
        ("검산 방법", "1) '원문 열기'로 DART 공시를 엽니다. 2) 노란 칸 앞의 숫자·날짜를 원문과 한 칸씩 비교합니다. "
                    "3) 노란 칸 '검산결과'에 일치 / 불일치 / 확인 불가 중 하나를 고르고, 검산자 이름과 메모(틀린 칸·원문 값)를 적습니다."),
        ("고칠 칸", "노란색 칸(검산결과·검산자·메모)만 적어 주세요. 다른 칸은 DB 값이라 고치지 않습니다."),
        ("수식 칸", "'수식 검산' 열은 엑셀 수식입니다. 감자: 감자 전 − 감자 주식 = 감자 후, "
                  "분할·병합: 변경 전 주식 × (변경 전 액면 ÷ 변경 후 액면) = 변경 후 주식. 숫자를 고치면 다시 계산됩니다."),
        ("판 구분", "API 최종본 = OpenDART가 준 값 · 원문 최종본 = API에 없어 원문에서 읽은 값 · "
                  "앞선 판 = 정정 묶음의 앞 공시(값은 최종본에 있음) · 첨부만 정정 = 첨부서류만 바꾼 정정"),
        ("빈칸 뜻", "원문에 '-'이거나 해당 없음. 예: 제3자배정 우선주 발행은 보통주 칸이 비어 있음"),
        ("금액 단위", "원. 주식 수는 주. 날짜는 원문 표기 그대로(예: 2025년 04월 24일, 2024.03.25)"),
        (None, None),
        ("작성 예시", "검산결과: 불일치 · 검산자: 홍길동 · 메모: 신주 수 원문 4,267,200 ↔ 표 4,276,200"),
    ]
    for i, (a, b) in enumerate(rows, 1):
        ws.cell(i, 1, a).font = Font(name=F, bold=True, size=14 if i == 1 else 10)
        c = ws.cell(i, 2, b)
        c.font = Font(name=F, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i in (10, 16):
        ws.cell(i, 2).fill = FILL

    # ---- 증자감자_최종본
    ws = wb.create_sheet("증자감자_최종본")
    cols = [("종류", 16), ("회사명", 16), ("접수번호", 16), ("접수일", 11), ("보고서명", 34), ("판 구분", 11),
            ("신주·감자 주식 수(보통)", 15), ("같은 기준(기타·종류주)", 15), ("1주당 액면가(원)", 11),
            ("전 발행주식총수(보통)", 15), ("전 발행주식총수(기타·종류)", 15), ("감자 후 발행주식총수(보통)", 15),
            ("감자 후 발행주식총수(기타·종류)", 15), ("무상: 1주당 배정 주식 수(보통)", 12), ("유상: 자금 합계(원)", 18),
            ("감자 전 자본금(원)", 17), ("감자 후 자본금(원)", 17), ("감자비율 보통(%)", 10), ("증자방식·감자방법", 24),
            ("감자사유", 24), ("기준일(배정·감자)", 15), ("신주 상장 예정일", 15), ("이사회결의일", 15),
            ("DB 검산 결과", 26), ("수식 검산(감자)", 14), ("원문", 10),
            ("검산결과", 11), ("검산자", 10), ("메모", 30)]
    header(ws, cols, 27)
    data = q("""select kind, corp_name, rcept_no, rcept_dt, report_nm, version, shares_common, shares_pref, par_won,
                       before_common, before_pref, after_common, after_pref, per_share_common, funds_won,
                       capital_before_won, capital_after_won, ratio_common_pct, method, reason, record_date, listing_date,
                       board_date, check_result, link
                from raw.dart_capital_event where version in ('API 최종본', '원문 최종본')
                order by kind, corp_name, rcept_no""")
    for i, r in enumerate(data, 2):
        r = list(r)
        vals = r[:24]
        for k in (6, 7, 8, 9, 10, 11, 12, 14, 15, 16):
            vals[k] = to_int(vals[k])
        vals[13] = float(vals[13]) if vals[13] is not None else None
        vals[17] = float(vals[17]) if vals[17] is not None else None
        vals[3] = vals[3].isoformat() if vals[3] else None
        vals[23] = vals[23] or ""
        if r[0] == "감자":
            side = ("G", "J", "L") if r[6] is not None or r[7] is None else ("H", "K", "M")  # 보통주 / 종류주식만 감자
            cut, bef, aft = (f"{c}{i}" for c in side)
            if r[18] and "액면" in r[18] and r[9] is not None and r[9] == r[11]:
                f = f'=IF({bef}={aft},"일치(액면감액)","불일치")'
            else:
                f = f'=IF(AND(ISNUMBER({cut}),ISNUMBER({bef}),ISNUMBER({aft})),IF({bef}-{cut}={aft},"일치","불일치"),"빈칸")'
        else:
            f = None
        body(ws, i, vals + [f, r[24]], numeric={7, 8, 9, 10, 11, 12, 13, 15, 16, 17}, link_col=26)
        ws.cell(i, 14).number_format = "0.##########"
    fill_cols(ws, len(data), 27, 29)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(data) + 1}"
    ws["F1"].comment = Comment("API 최종본: OpenDART 응답 / 원문 최종본: API에 없어 DART 원문 표에서 읽음", "onepick")
    n_capital = len(data)

    # ---- 분할병합
    ws = wb.create_sheet("분할병합")
    cols = [("종류", 10), ("회사명", 16), ("접수번호", 16), ("접수일", 11), ("보고서명", 26), ("정정 여부", 9),
            ("액면가 전(원)", 11), ("액면가 후(원)", 11), ("보통주 전(주)", 15), ("보통주 후(주)", 15),
            ("종류주 전(주)", 12), ("종류주 후(주)", 12), ("주주총회 예정일", 13), ("효력발생일", 12),
            ("매매정지 시작", 12), ("매매정지 끝", 12), ("신주 상장 예정일", 13), ("이사회결의일", 13), ("목적", 20),
            ("DB 검산 결과", 40), ("수식 검산", 12), ("원문", 10), ("검산결과", 11), ("검산자", 10), ("메모", 30)]
    header(ws, cols, 23)
    data = q("""select kind, corp_name, rcept_no, rcept_dt, report_nm, is_correction, par_before_won, par_after_won,
                       shares_before_common, shares_after_common, shares_before_pref, shares_after_pref, agm_date,
                       effective_date, halt_start, halt_end, listing_date, board_date, purpose, check_result, link
                from raw.dart_split_merge order by kind, corp_name, rcept_no""")
    for i, r in enumerate(data, 2):
        r = list(r)
        vals = r[:20]
        for k in range(6, 12):
            vals[k] = to_int(vals[k])
        vals[3] = vals[3].isoformat()
        vals[5] = "정정" if vals[5] else ""
        e = f"I{i}*G{i}/H{i}"  # 변경 전 주식 × 액면 비율 = 기대 변경 후 주식
        tol = "0" if r[0] == "주식분할" else f"MAX(1,{e}*0.001)"  # 병합은 단주 처리로 조금 다를 수 있음
        f = f'=IF(AND(ISNUMBER(G{i}),ISNUMBER(H{i}),ISNUMBER(I{i}),ISNUMBER(J{i})),IF(ABS(J{i}-{e})<={tol},"일치","불일치"),"빈칸")'
        body(ws, i, vals + [f, r[20]], numeric={7, 8, 9, 10, 11, 12}, link_col=22)
    fill_cols(ws, len(data), 23, 25)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(data) + 1}"
    n_split = len(data)

    # ---- 정정_앞선판
    ws = wb.create_sheet("정정_앞선판")
    cols = [("종류", 12), ("회사명", 16), ("접수번호", 16), ("접수일", 11), ("보고서명", 36), ("판 구분", 11),
            ("값이 있는 공시", 46), ("원문", 10)]
    header(ws, cols, 99)
    data = q("""select kind, corp_name, rcept_no, rcept_dt, report_nm, version, check_result, link
                from raw.dart_capital_event where version in ('앞선 판', '첨부만 정정') order by kind, corp_name, rcept_no""")
    for i, r in enumerate(data, 2):
        r = list(r)
        r[3] = r[3].isoformat()
        body(ws, i, r, numeric=set(), link_col=8)
    ws.auto_filter.ref = f"A1:H{len(data) + 1}"

    wb.calculation.fullCalcOnLoad = True  # 엑셀이 열 때 수식을 계산
    wb.save(out)
    return {"증자감자_최종본": n_capital, "분할병합": n_split, "정정_앞선판": len(data)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="증자·감자·분할·병합 표를 팀 검산용 엑셀로 내보냄")
    ap.add_argument("--out", type=Path, default=EXPORT_DIR / f"증자감자_분할병합_검산표_{date.today():%Y%m%d}.xlsx")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with db.connect(args.url) as conn:
        counts = build(conn, args.out)
    print(args.out, " · ".join(f"{k} {v}건" for k, v in counts.items()))
