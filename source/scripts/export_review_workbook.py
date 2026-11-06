"""onepick DB 전체 → 파트별 전수 검산표 엑셀 (사람이 원문과 한 행씩 맞춰 보는 용도).

실행: .venv/bin/python -m scripts.export_review_workbook [--out 파일] [--url postgresql://localhost/onepick]
형식은 증자·감자 검산표(source/scripts/export_capital_check.py)와 같다. 시트마다 맨 끝 노란 칸(검토 상태·검토자·메모)만
검토자가 채우고, '수식 검산' 열은 엑셀 수식이라 파일을 열 때 계산된다. 일치로 나온 행도 모두 넣는다
(코드가 원문을 잘못 읽었을 수도 있으므로). 열마다 뜻·원천·더한 값은 '항목_설명' 시트에 있다.
"""
import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import dart_doc as dd
from core import db
from core.dart_fill import source_tag

EXPORT_DIR = Path(__file__).resolve().parents[2] / "output" / "tables"
OFS_FILE = Path(__file__).resolve().parents[2] / "data" / "raw" / "03_별도보완" / "별도_보완결과.csv"
VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

REVIEWERS = ["한상범", "김민지", "박예지", "조진영"]
STATES = ["확인완료", "확인불가", "정정됨(배제)"]

F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
FILL = PatternFill("solid", fgColor="FFFF00")
FORMULA_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
NUM = "#,##0;(#,##0);-"
TOL = 1_000_000  # DB 재무·배당 값은 백만 원 단위라 원 단위 원문과 이만큼 차이 날 수 있음


@dataclass
class Col:
    name: str
    width: float
    meaning: str
    source: str = ""
    how: str = ""
    kind: str = "text"  # text · num · pct · link · formula


REVIEW_COLS = [
    Col("검토 상태", 12, "검토자가 고르는 결과: 확인완료(원문과 같음) · 확인불가(원문을 못 찾거나 판단 못 함) · 정정됨(배제)(값이 틀려 분석에서 뺌)",
        "검토자 입력", "목록에서 고름"),
    Col("검토자", 10, "이 행을 본 사람", "검토자 입력", "한상범 · 김민지 · 박예지 · 조진영 중 고름"),
    Col("메모", 32, "틀린 칸과 원문 값, 판단 근거", "검토자 입력"),
]


# --- 공통 -------------------------------------------------------------------------------


def num(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA else float(v)


def link(rcept: str | None) -> str | None:
    if not rcept:
        return None
    return rcept if str(rcept).startswith("http") else VIEW + str(rcept)


class Sources:
    """DB에서 한 번에 읽어 두는 원문 대조·빈칸 채우기·사업보고서 목록."""

    def __init__(self, conn):
        self.name = {r["corp_code"]: r["corp_name"] for r in db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_company")}
        self.verify = {}
        for r in db.fetch_dicts(conn, """SELECT v.*, m.correction_kind, m.use_source FROM core.core_dart_verify v
                                         LEFT JOIN core.v_dart_mismatch m USING (target, corp_code, bsns_year, item, basis)"""):
            self.verify.setdefault((r["target"], r["corp_code"], r["bsns_year"], r["item"]), []).append(r)
        self.fill = {(r["corp_code"], r["bsns_year"], r["item"]): r for r in db.fetch_dicts(
            conn, "SELECT * FROM core.core_dart_fill WHERE item NOT LIKE 'decision.%%'")}
        self.reports = {}  # (corp, 연도) → (접수번호, 보고서명) 최신 정정
        self.period = {}  # 접수번호 → 보고서 기간 연도
        for corp in self.name:
            for rcp, title, period in dd.annual_reports(corp):
                self.reports.setdefault((corp, int(period[:4])), (rcp, title))
                self.period[rcp] = int(period[:4])

        self.recheck = {}  # 원문 재대조 (source/scripts/verify_sources.py): (대상, 행 열쇠) → [칸]
        self.recheck_year = {}  # 배당 표: (회사, 연도) → [D·보통주 DPS 칸]
        for r in db.fetch_dicts(conn, "SELECT * FROM core.core_source_verify ORDER BY ref, item"):
            t = r["target"]
            key = r["ref"].split("|")[0] if t != "dart_dividend_item" else tuple(r["ref"].split("|")[:2])
            self.recheck.setdefault((t, key), []).append(r)
            if t == "dart_dividend_item" and (r["item"].startswith("현금배당금총액") or
                                              (r["item"].startswith("주당 현금배당금") and "보통" in r["ref"].split("|")[3])):
                self.recheck_year.setdefault((r["corp_code"], r["bsns_year"]), []).append(r)

    def verified(self, target, corp, year, item, basis=None) -> dict | None:
        rows = self.verify.get((target, corp, year, item), [])
        return next((r for r in rows if r["basis"] == basis), rows[0] if rows else None)

    def recheck_text(self, target, key=None, rows=None) -> str:
        rows = rows if rows is not None else self.recheck.get((target, key), [])
        if not rows:
            return "재대조 안 함"
        bad = [r for r in rows if r["result"] == "불일치"]
        miss = [r for r in rows if r["result"] == "원문에서 못 찾음"]
        if not bad and not miss:
            return f"{len(rows)}칸 일치"
        parts = [f"불일치 {len(bad)}칸: " + "; ".join(f"{r['item']} DB {r['db_value']} ↔ 원문 {r['src_value']}" for r in bad[:3])] if bad else []
        if miss:
            parts.append(f"원문에서 못 찾음 {len(miss)}칸 ({', '.join(sorted({r['item'] for r in miss})[:3])})")
        return " / ".join(parts)

    def own_report(self, corp, year) -> tuple[str, str]:
        rcp, title = self.reports.get((corp, year), ("", ""))
        return rcp, (f"사업보고서 ({year}) " + title).strip() if rcp else ""

    def column_of(self, rcept, year) -> str:
        p = self.period.get(rcept)
        return {0: "당기", 1: "전기", 2: "전전기"}.get(p - year, "") if p else ""


def result_of(src: Sources, target, corp, year, item, basis, fill_item=None) -> tuple:
    """(원문에서 읽은 값, 대조 결과 글, 근거 공시 접수번호, 공시명, 열)"""
    v = src.verified(target, corp, year, item, basis)
    if v is not None:
        res = v["result"] + (f" ({v['correction_kind']})" if v["correction_kind"] else "")
        return num(v["src_value"]), res, v["src_rcept_no"], v["src_title"], v["src_period"] or ""
    f = src.fill.get((corp, year, fill_item or item))
    if f is not None:
        res = "DART로 채움" if f["status"] == "채움" else f"빈칸: {f['status']}"
        return num(f["value_won"]) if f["status"] == "채움" else None, res, f["source_rcept_no"], f["source_title"], f["column_kind"] or ""
    return None, "대조 안 함", "", "", ""


# --- 시트 쓰기 -------------------------------------------------------------------------------


def write(ws, cols: list[Col], rows: list[dict], formulas: dict | None = None) -> int:
    """rows: 열 이름 → 값. formulas: 열 이름 → (letter 함수, 행 번호) → 수식."""
    cols = cols + REVIEW_COLS
    first_yellow = len(cols) - len(REVIEW_COLS) + 1
    letter = {c.name: get_column_letter(j) for j, c in enumerate(cols, 1)}
    for j, c in enumerate(cols, 1):
        h = ws.cell(1, j, c.name)
        yellow = j >= first_yellow
        h.font = Font(name=F, bold=True, color="000000" if yellow else "FFFFFF")
        h.fill = FILL if yellow else HEAD
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = BOX
        ws.column_dimensions[get_column_letter(j)].width = c.width
    ws.row_dimensions[1].height = 36
    for i, r in enumerate(rows, 2):
        for j, c in enumerate(cols, 1):
            if c.kind == "formula":
                v = formulas[c.name](letter, i)
            else:
                v = r.get(c.name)
                if isinstance(v, float) and pd.isna(v):
                    v = None
            cell = ws.cell(i, j, v)
            cell.font = Font(name=F, size=10)
            cell.border = BOX
            if c.kind == "num":
                cell.number_format = NUM
            elif c.kind == "pct":
                cell.number_format = "0.00"
            elif c.kind == "formula":
                cell.fill = FORMULA_FILL
            elif c.kind == "link" and v:
                cell.hyperlink, cell.value = v, "원문 열기"
                cell.font = Font(name=F, size=10, color="0563C1", underline="single")
            if j >= first_yellow:
                cell.fill = FILL
    last = len(rows) + 1
    for name, options in (("검토 상태", STATES), ("검토자", REVIEWERS)):
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True, showErrorMessage=True,
                            errorTitle="목록에서 고르기", error=", ".join(options) + " 중에서 고르세요")
        dv.add(f"{letter[name]}2:{letter[name]}{max(last, 2)}")
        ws.add_data_validation(dv)
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{last}"
    return len(rows)


def same(a, b, tol=TOL):
    """두 칸이 둘 다 비었거나, 둘 다 숫자이고 차이가 tol 미만이면 TRUE인 수식 조각."""
    return f"OR(AND(ISBLANK({a}),ISBLANK({b})),AND(ISNUMBER({a}),ISNUMBER({b}),ABS({a}-{b})<{tol}))"


# --- 자동 조사 (수식에 걸린 행의 원인 찾기) ------------------------------------------------------------


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not pd.isna(v)


def investigate_div(r) -> str:
    """D(배당 표) ↔ 배당 결정 공시 합계가 ±1%를 넘게 다를 때."""
    d, s, y = r["D 분석 값(원)"], r["배당 결정 공시 합계(원)"], r["사업연도"]
    if not (_isnum(d) and _isnum(s)) or abs(d - s) <= max(TOL, d * 0.01):
        return ""
    if d == 0:
        return "D는 0(배당 표 '-')인데 그 해 귀속 결정 공시가 있음 → 배당 표 연도·귀속 연도 확인"
    if s < TOL:
        return f"결정 공시 배당금총액이 {s:,.0f}원 → 결정 공시 읽기 오류 의심 (05 원천)"
    ratio = s / d
    if 0.0009 < ratio < 0.0011 or 900 < ratio < 1100:
        return f"두 값이 약 1,000배 차이 (결정 공시 ÷ D = {ratio:,.4f}) → 한쪽 단위 오류 의심"
    if y <= 2022:
        return f"05 결정 공시는 2023-01 접수분부터라 {y}년 중간·분기 결정 공시가 빠짐 (결정 공시 ÷ D = {ratio:.1%})"
    return (f"결정 공시 ÷ D = {ratio:.1%} (결정 공시 {r['결정 공시 건수']}건) → 중간·분기·감액배당 포함 범위, "
            "결산배당 귀속 연도 확인 필요")


def investigate_payout(r) -> str:
    p, t, n, b = (r.get(c) for c in ("(연결)현금배당성향(%)", "현금배당금총액(백만원)", "(연결)당기순이익(백만원)", "(별도)당기순이익(백만원)"))
    if not (_isnum(p) and _isnum(t) and _isnum(n)) or n <= 0 or abs(p - t / n * 100) <= 0.5:
        return ""
    if _isnum(b) and b > 0 and abs(p - t / b * 100) <= 0.5:
        return "별도 당기순이익으로 계산하면 일치 → 회사가 별도 기준 성향을 적음"
    calc = t / n * 100
    if abs(p - calc) <= 3:
        return f"계산 {calc:.1f}% ↔ 공시 {p}% (차이 {p - calc:+.1f}%p) → 원 단위 계산·우선주·지배 순이익 범위 차이로 보임"
    return f"계산 {calc:.1f}% ↔ 공시 {p}% → 원문 확인 필요 (원문 재대조 칸 참고)"


def investigate_decision(r) -> str:
    a, b = r.get("배당기준일"), r.get("배당금지급 예정일")
    if a and b and str(a) > str(b):
        return "지급 예정일이 기준일보다 앞섬 → 공시 원문의 연도 오타 의심 (원문 재대조 칸에서 원문 글자 확인)"
    if _isnum(r.get("배당금총액(원)")) and r["배당금총액(원)"] < TOL:
        return f"배당금총액 {r['배당금총액(원)']:,.0f}원 → 읽기 오류 의심"
    return ""


def investigate_kind(r) -> str:
    g, a, b = r["증가율(%)"], r["직전 배당총액 D(원)"], r["전전 배당총액 D(원)"]
    if not (_isnum(g) and _isnum(a) and _isnum(b)) or b == 0:
        return ""
    calc = (a / b - 1) * 100
    if abs(g - calc) <= 0.5:
        return ""
    if abs(g - a / b * 100) <= 0.5:
        return f"증가율 칸에 비율(직전÷전전×100 = {a / b * 100:.1f})을 적음 → 실제 증가율 {calc:.1f}%"
    return f"계산 증가율 {calc:.1f}% ↔ 공시 {g}% → 회사 공시 값이 계산과 다름, 원문 확인 필요"


# --- 02 재무 -------------------------------------------------------------------------------

FIN_ITEMS = [("ni_owner_won", "지배주주 순이익", "지배기업 소유주지분 당기순이익 (연결이면 지배주주 몫, 별도면 당기순이익)"),
             ("liabilities_won", "부채총계", "재무상태표 부채총계"), ("equity_won", "자본총계", "재무상태표 자본총계 (비지배지분 포함)")]


def sheet_fin(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "core.core_company.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "core.core_financial_year.corp_code"),
            Col("사업연도", 8, "재무제표 기간 연도 (12월 결산이면 그 해 1~12월)", "core.core_financial_year.bsns_year"),
            Col("재무 기준", 8, "연결 또는 별도. 연결재무제표가 있으면 연결", "core.core_financial_year.fs_basis"),
            Col("출처 태그", 26, "채운 값을 사업보고서가 아닌 곳(감사보고서, 감사보고서제출·분기·반기보고서 첨부파일)에서 찾았으면 그 출처. "
                "사업보고서에서 찾았거나 DB 원본이면 빈칸", "core.core_dart_fill.source_title",
                "source/core/dart_fill.py source_tag(): 공시 제목으로 판단. 한 행에 여러 출처면 모두 적음")]
    for _, label, meaning in FIN_ITEMS:
        cols += [Col(f"{label} DB(원)", 17, f"{meaning}. DB 원본 값", "core.core_financial_year (02 원천, 백만 원 단위를 원으로)", "", "num"),
                 Col(f"{label} 원문 읽은 값(원)", 17, f"{meaning}. 코드가 DART 원문 표에서 다시 읽은 값",
                     "core.core_dart_verify.src_value (대조) 또는 core.core_dart_fill.value_won (빈칸 채움)",
                     "지배주주 순이익은 손익계산서 '지배기업 소유주' 행. 지배+비지배=당기순이익 검산이 맞을 때만 씀. "
                     "부채·자본은 부채+자본=부채와자본총계 검산이 맞을 때만 씀", "num"),
                 Col(f"{label} 대조 결과", 18, "코드 대조 결과: 일치 · 일치(단위 반올림) · 불일치(원인) · 원문 못 읽음 · 원문 없음 · DART로 채움 · 빈칸: 이유",
                     "core.core_dart_verify.result · core.core_dart_fill.status"),
                 Col(f"{label} 분석 값(원)", 17, f"{meaning}. 분석·판정에 실제로 쓰는 값 (빈칸 채움·불일치 수정 반영)",
                     "core.v_financial_year_verified", "DB 값이 없으면 채운 값, 불일치면 설정(restated_policy)에 따라 원문 값", "num")]
    cols += [Col("수식 검산", 12, "분석 값과 원문 읽은 값이 세 항목 모두 같은지 (100만 원 미만 차이는 같음)", "엑셀 수식",
                 "항목마다 둘 다 비었거나 차이 < 1,000,000원이면 같음. 원문 읽은 값이 하나도 없으면 '원문 값 없음'", "formula"),
             Col("자동 조사", 36, "수식·대조에 걸린 행을 코드가 자료로 더 살펴본 원인 (사람 확인 전 참고, 걸리지 않은 행은 빈칸)",
                "source/scripts/export_review_workbook.py investigate_*", "규칙: 항목_설명의 이 칸 아래 설명과 같음. 원인을 못 정하면 '원문 확인 필요'"),
             Col("원문 공시", 30, "대조·채움에 쓴 공시. 없으면 그 해 사업보고서", "core.core_dart_verify.src_title · core.core_dart_fill.source_title · DART 사업보고서 검색"),
             Col("원문 열", 10, "그 공시 표의 어느 열에서 읽었는지 (당기 / 비교기간)", "core.core_dart_verify.src_period · core.core_dart_fill.column_kind"),
             Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    orig = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_financial_year")}
    rows = []
    for v in db.fetch_dicts(conn, "SELECT * FROM core.v_financial_year_verified ORDER BY corp_code, bsns_year"):
        c, y, basis = v["corp_code"], v["bsns_year"], v["fs_basis"]
        o = orig[(c, y)]
        r = {"회사명": src.name.get(c, c), "corp_code": c, "사업연도": y, "재무 기준": basis or ""}
        rcept = title = column = ""
        notes = []
        tags = []
        for item, label, _ in FIN_ITEMS:
            f = src.fill.get((c, y, item))
            if f is not None and f["status"] == "채움" and o[item] is None:
                tag = source_tag(f["source_title"])
                if tag and tag not in tags:
                    tags.append(tag)
            val, res, rc, ti, co = result_of(src, "core_financial_year", c, y, item, basis)
            chk = src.verified("core_financial_year", c, y, item, basis)
            if chk is not None and chk["result"] == "불일치":
                notes.append(f"{label}: {chk['note'] or '원인 모름'}")
            r |= {f"{label} DB(원)": num(o[item]), f"{label} 원문 읽은 값(원)": val, f"{label} 대조 결과": res,
                  f"{label} 분석 값(원)": num(v[item])}
            if rc and not rcept:
                rcept, title, column = rc, ti, co
        if not rcept:
            rcept, title = src.own_report(c, y)
        r |= {"원문 공시": title, "원문 열": column, "원문": link(rcept), "자동 조사": " / ".join(notes), "출처 태그": " / ".join(tags)}
        rows.append(r)
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"]))

    def check(L, i):
        pairs = [(f"{L[label + ' 분석 값(원)']}{i}", f"{L[label + ' 원문 읽은 값(원)']}{i}") for _, label, _ in FIN_ITEMS]
        srcs = ",".join(b for _, b in pairs)
        return f'=IF(COUNT({srcs})=0,"원문 값 없음",IF(AND({",".join(same(a, b) for a, b in pairs)}),"같음","다름"))'

    return cols, rows, {"수식 검산": check}


# --- 02 배당 표 ---------------------------------------------------------------------------


def sheet_div(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "core.core_company.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "core.core_dividend_year.corp_code"),
            Col("사업연도", 8, "배당이 속한 사업연도 (그 해 결산배당 + 중간·분기배당)", "core.core_dividend_year.bsns_year"),
            Col("현금배당총액 D DB(원)", 17, "사업보고서 '배당에 관한 사항' 표의 현금배당금총액 (보통주+우선주, 중간·분기 포함 1년 합계)",
                "core.core_dividend_year.d_dart_won (02 원천 raw.dart_dividend_item '현금배당금총액(백만원)' × 1,000,000)",
                "회사가 배당 표에 적은 1년 합계. 코드가 더하지 않음", "num"),
            Col("D 원문 읽은 값(원)", 17, "DB가 비어 있어 코드가 원문 배당 표에서 읽은 현금배당금총액", "core.core_dart_fill (item d_dart_won)",
                "'현금배당금총액' 행의 그 해 열 × 표 단위('-'는 0)", "num"),
            Col("D 상태", 14, "DB 원본 · DART로 채움 · 빈칸: 이유", "core.core_dart_fill.status"),
            Col("D 분석 값(원)", 17, "분석에 쓰는 현금배당총액", "core.v_dividend_year_verified.d_dart_won", "DB 값, 없으면 채운 값", "num"),
            Col("보통주 주당배당금 DB(원)", 13, "배당 표 '주당 현금배당금' 중 보통주 행", "core.core_dividend_year.dps_common_won (02 원천)", "", "num"),
            Col("보통주 DPS 원문 읽은 값(원)", 13, "DB가 비어 코드가 원문에서 읽은 보통주 주당배당금", "core.core_dart_fill (item dps_common_won)",
                "보통주 행이 없고 결산·중간·분기 행으로 나뉜 표는 그 행들을 더함 (원문 검산 칸에 적음)", "num"),
            Col("보통주 DPS 상태", 14, "DB 원본 · DART로 채움 · 빈칸: 이유", "core.core_dart_fill.status"),
            Col("보통주 DPS 분석 값(원)", 13, "분석에 쓰는 보통주 주당배당금", "core.v_dividend_year_verified.dps_common_won", "", "num"),
            Col("원문 검산", 30, "채운 값을 원문 어느 행에서 어떻게 읽었는지", "core.core_dart_fill.check_result"),
            Col("원문 재대조", 34, "DB D·보통주 DPS를 준 배당 표 칸을 코드가 원문에서 다시 읽어 맞춰 본 결과 (그 연도를 담은 모든 보고서)",
                "core.core_source_verify (target dart_dividend_item, 현금배당금총액·주당 현금배당금 보통주 칸)"),
            Col("배당 결정 공시 합계(원)", 17, "그 사업연도에 속하는 현금배당 결정 공시들의 배당금총액 합계 (참고·대조용)",
                "core.v_dividend_year_verified.d_decision_won (05 원천 raw.dividend_decision.total_won 합)",
                "결산·중간·분기 결정 공시를 귀속 사업연도별로 더함 (결산배당 기준일이 다음 해 1~6월이면 앞 해)", "num"),
            Col("결정 공시 건수", 8, "더한 결정 공시 수", "core.core_dividend_year.decision_count", "", "num"),
            Col("수식 검산", 13, "D 분석 값과 결정 공시 합계 비교", "엑셀 수식",
                "차이가 max(100만 원, D의 1%) 이하면 '±1% 이내', 넘으면 '다름', 한쪽이 비면 '비교 불가'", "formula"),
            Col("자동 조사", 36, "수식·대조에 걸린 행을 코드가 자료로 더 살펴본 원인 (사람 확인 전 참고, 걸리지 않은 행은 빈칸)",
                "source/scripts/export_review_workbook.py investigate_*", "규칙: 항목_설명의 이 칸 아래 설명과 같음. 원인을 못 정하면 '원문 확인 필요'"),
            Col("원천 공시", 30, "DB 값을 가져온 사업보고서 (채운 값이면 채울 때 읽은 공시)", "raw.dart_dividend_item.rcept_no · core.core_dart_fill.source_title"),
            Col("원천 열", 8, "그 보고서 배당 표의 당기·전기·전전기 중 어느 열인지", "보고서 기간 연도 − 사업연도"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    orig = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_dividend_year")}
    first_rcept = {(r["corp_code"], r["bsns_year"]): r["rcept_no"] for r in db.fetch_dicts(
        conn, "SELECT corp_code, bsns_year, min(rcept_no) AS rcept_no FROM raw.dart_dividend_item WHERE rcept_no IS NOT NULL GROUP BY 1, 2")}
    rows = []
    for v in db.fetch_dicts(conn, "SELECT * FROM core.v_dividend_year_verified"):
        c, y = v["corp_code"], v["bsns_year"]
        o = orig[(c, y)]
        fd, fp = src.fill.get((c, y, "d_dart_won")), src.fill.get((c, y, "dps_common_won"))

        def state(orig_v, f):
            if orig_v is not None:
                return "DB 원본"
            if f is None:
                return "빈칸 (원문 확인 안 함)"
            return "DART로 채움" if f["status"] == "채움" else f"빈칸: {f['status']}"

        used = next((f for f in (fd, fp) if f is not None and f["source_rcept_no"]), None)
        rcept = first_rcept.get((c, y)) if o["d_dart_won"] is not None else (used["source_rcept_no"] if used else first_rcept.get((c, y)))
        title = (used["source_title"] if used and rcept == used["source_rcept_no"] else
                 (f"사업보고서 ({src.period[rcept]})" if rcept in src.period else "") if rcept else "")
        rows.append({"회사명": src.name.get(c, c), "corp_code": c, "사업연도": y,
                     "현금배당총액 D DB(원)": num(o["d_dart_won"]),
                     "D 원문 읽은 값(원)": num(fd["value_won"]) if fd and fd["status"] == "채움" else None,
                     "D 상태": state(o["d_dart_won"], fd), "D 분석 값(원)": num(v["d_dart_won"]),
                     "보통주 주당배당금 DB(원)": num(o["dps_common_won"]),
                     "보통주 DPS 원문 읽은 값(원)": num(fp["value_won"]) if fp and fp["status"] == "채움" else None,
                     "보통주 DPS 상태": state(o["dps_common_won"], fp), "보통주 DPS 분석 값(원)": num(v["dps_common_won"]),
                     "원문 검산": " / ".join(f"{k}: {f['check_result'] or f['note']}" for k, f in (("D", fd), ("DPS", fp)) if f),
                     "원문 재대조": src.recheck_text("", rows=src.recheck_year.get((c, y), [])),
                     "배당 결정 공시 합계(원)": num(v["d_decision_won"]), "결정 공시 건수": o["decision_count"],
                     "원천 공시": title, "원천 열": src.column_of(rcept, y) if rcept else "", "원문": link(rcept)})
    for r in rows:
        r["자동 조사"] = investigate_div(r)
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"]))

    def check(L, i):
        d, s = f"{L['D 분석 값(원)']}{i}", f"{L['배당 결정 공시 합계(원)']}{i}"
        return f'=IF(OR(NOT(ISNUMBER({d})),NOT(ISNUMBER({s}))),"비교 불가",IF(ABS({d}-{s})<=MAX({TOL},{d}*0.01),"±1% 이내","다름"))'

    return cols, rows, {"수식 검산": check}


# --- 04 현금흐름표 배당금 지급 -------------------------------------------------------------------


def sheet_cf(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "core.core_company.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "core.core_dividend_year.corp_code"),
            Col("사업연도", 8, "현금흐름표 기간 연도", "core.core_dividend_year.bsns_year"),
            Col("재무제표", 8, "연결(CFS) 또는 별도(OFS) 현금흐름표", "raw.cf_dividend_paid.fs_div"),
            Col("원천 상태", 18, "04 원천 자료가 계정을 찾은 결과", "raw.cf_dividend_paid.status"),
            Col("더한 계정", 34, "DB 값이 합계일 때 더한 현금흐름표 계정 이름들 (계정 1개면 그 계정)", "raw.cf_dividend_paid.accounts",
                "재무활동 현금흐름 중 '배당금의 지급' 계열 계정을 더함. 비지배지분 배당·배당금 수령은 뺌"),
            Col("계정 수", 6, "더한 계정 수", "raw.cf_dividend_paid.n_accounts", "", "num"),
            Col("비지배지분 배당(원)", 15, "따로 뺀 비지배지분 배당금 지급 (참고)", "raw.cf_dividend_paid.nci_paid_mil × 1,000,000", "", "num"),
            Col("배당금 지급 DB(원)", 17, "현금흐름표 '배당금의 지급' (지배회사가 주주에게 실제 낸 현금, 양수로 적음)",
                "core.core_dividend_year.cf_paid_won (04 원천 raw.cf_dividend_paid.paid_mil × 1,000,000)", "더한 계정의 합", "num"),
            Col("원문 읽은 값(원)", 17, "코드가 DART 원문 현금흐름표에서 다시 읽은 값", "core.core_dart_verify.src_value · core.core_dart_fill.value_won",
                "원문에서 배당금 지급 줄이 1줄일 때만 그 값. 여러 줄이면 사람 확인", "num"),
            Col("대조 결과", 18, "일치 · 불일치(원인) · 원문 못 읽음 · DART로 채움 · 빈칸: 이유", "core.core_dart_verify.result · core.core_dart_fill.status"),
            Col("분석 값(원)", 17, "분석에 쓰는 배당금 지급", "core.v_dividend_year_verified.cf_paid_won_verified", "불일치면 설정에 따라 원문 값", "num"),
            Col("수식 검산", 12, "분석 값과 원문 읽은 값이 같은지", "엑셀 수식", "차이 < 1,000,000원이면 같음, 원문 값이 없으면 '원문 값 없음'", "formula"),
            Col("원문 공시", 30, "대조·채움에 쓴 공시 (없으면 원천 공시)", "core.core_dart_verify.src_title · raw.cf_dividend_paid.rcept_no"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    paid = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM raw.cf_dividend_paid")}
    orig = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_dividend_year")}
    rows = []
    for v in db.fetch_dicts(conn, "SELECT * FROM core.v_dividend_year_verified WHERE bsns_year >= 2023"):
        c, y = v["corp_code"], v["bsns_year"]
        p, o = paid.get((c, y), {}), orig[(c, y)]
        basis = {"CFS": "연결", "OFS": "별도"}.get(p.get("fs_div"), "")
        val, res, rc, ti, _ = result_of(src, "cf_dividend_paid", c, y, "dividends_paid_won", basis or None, "cf_paid_won")
        if not rc and p.get("rcept_no"):
            rc, ti = p["rcept_no"], "04 원천 사업보고서"
        rows.append({"회사명": src.name.get(c, c), "corp_code": c, "사업연도": y, "재무제표": basis,
                     "원천 상태": p.get("status") or o["cf_status"] or "04 원천에 없음", "더한 계정": p.get("accounts") or "",
                     "계정 수": p.get("n_accounts"), "비지배지분 배당(원)": num(p["nci_paid_mil"]) * 1e6 if p.get("nci_paid_mil") is not None else None,
                     "배당금 지급 DB(원)": num(o["cf_paid_won"]), "원문 읽은 값(원)": val, "대조 결과": res,
                     "분석 값(원)": num(v["cf_paid_won_verified"]), "원문 공시": ti, "원문": link(rc)})
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"]))

    def check(L, i):
        a, b = f"{L['분석 값(원)']}{i}", f"{L['원문 읽은 값(원)']}{i}"
        return f'=IF(NOT(ISNUMBER({b})),"원문 값 없음",IF({same(a, b)},"같음","다름"))'

    return cols, rows, {"수식 검산": check}


# --- 04-2 DART 재무 API 주요 계정 -------------------------------------------------------------

API_ACCOUNTS = [  # (account_id, 열 이름, 뜻)
    ("BS", "ifrs-full_CurrentAssets", "유동자산(원)", "재무상태표 유동자산 합계"),
    ("BS", "ifrs-full_NoncurrentAssets", "비유동자산(원)", "재무상태표 비유동자산 합계"),
    ("BS", "ifrs-full_Assets", "자산총계(원)", "재무상태표 자산총계"),
    ("BS", "ifrs-full_CurrentLiabilities", "유동부채(원)", "재무상태표 유동부채 합계"),
    ("BS", "ifrs-full_NoncurrentLiabilities", "비유동부채(원)", "재무상태표 비유동부채 합계"),
    ("BS", "ifrs-full_Liabilities", "부채총계(원)", "재무상태표 부채총계"),
    ("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분(원)", "자본 중 지배기업 주주 몫 (연결만)"),
    ("BS", "ifrs-full_NoncontrollingInterests", "비지배지분(원)", "자본 중 비지배주주 몫 (연결만)"),
    ("BS", "ifrs-full_Equity", "자본총계(원)", "재무상태표 자본총계 (비지배지분 포함)"),
    ("BS", "ifrs-full_IssuedCapital", "자본금(원)", "자본금"),
    ("BS", "ifrs-full_RetainedEarnings", "이익잉여금(원)", "이익잉여금 (배당 재원)"),
    ("BS", "ifrs-full_EquityAndLiabilities", "부채와자본총계(원)", "재무상태표 부채와자본총계"),
    ("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산(원)", "재무상태표 현금및현금성자산"),
    ("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동 현금흐름(원)", "현금흐름표 영업활동으로 인한 현금흐름"),
    ("CF", "ifrs-full_CashFlowsFromUsedInInvestingActivities", "투자활동 현금흐름(원)", "현금흐름표 투자활동으로 인한 현금흐름"),
    ("CF", "ifrs-full_CashFlowsFromUsedInFinancingActivities", "재무활동 현금흐름(원)", "현금흐름표 재무활동으로 인한 현금흐름"),
    ("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "배당금 지급(재무활동)(원)", "현금흐름표 재무활동 배당금의 지급 (표준계정 1줄)"),
    ("CF", "dart_CashAndCashEquivalentsAtBeginningOfPeriodCf", "기초 현금(원)", "현금흐름표 기초 현금및현금성자산"),
    ("CF", "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents", "현금 순증감(원)", "현금흐름표 현금및현금성자산의 순증가(감소)"),
    ("CF", "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents", "환율변동효과(원)", "현금흐름표 현금및현금성자산 환율변동효과"),
    ("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "기말 현금(원)", "현금흐름표 기말 현금및현금성자산"),
]


def sheet_bs(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "raw.dart_financial.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "raw.dart_financial.corp_code"),
            Col("사업연도", 8, "재무제표 기준 연도 (기말)", "raw.dart_financial.bsns_year"),
            Col("재무제표", 8, "연결(CFS) 또는 별도(OFS). 한 회사·연도에 둘 중 하나만 있음", "raw.dart_financial.fs_div")]
    cols += [Col(name, 17, meaning + " 당기 금액", f"raw.dart_financial (sj_div {sj}, account_id {aid}, thstrm_amount)",
                 "회사가 공시한 값 그대로. 같은 계정이 여러 줄이면 표의 첫 줄", "num") for sj, aid, name, meaning in API_ACCOUNTS]
    cols += [Col("매각예정자산(원)", 15, "재무상태표에 유동·비유동과 따로 적힌 매각예정자산(처분자산집단)", "raw.dart_financial (계정명에 '매각예정', 부채 아님, 첫 줄)",
                 "자산 합 검산에서 유동+비유동에 더해 봄", "num"),
             Col("매각예정부채(원)", 15, "유동·비유동과 따로 적힌 매각예정자산 관련 부채", "raw.dart_financial (계정명에 '매각예정'과 '부채', 첫 줄)",
                 "부채 합 검산에서 유동+비유동에 더해 봄", "num"),
             Col("부채 원문 읽은 값(원)", 17, "코드가 그 해 사업보고서 원문 재무상태표에서 다시 읽은 부채총계", "core.core_dart_verify (target dart_financial)", "", "num"),
             Col("자본 원문 읽은 값(원)", 17, "코드가 원문에서 다시 읽은 자본총계", "core.core_dart_verify (target dart_financial)", "", "num"),
             Col("대조 결과", 20, "부채·자본 각각의 코드 대조 결과", "core.core_dart_verify.result"),
             Col("수식: 자산 합", 11, "유동자산 + 비유동자산 (+ 매각예정자산) = 자산총계", "엑셀 수식",
                 "매각예정자산을 빼고 또는 더해서 차이 1원 이하면 '일치', 칸이 비면 '빈칸'", "formula"),
             Col("수식: 부채 합", 11, "유동부채 + 비유동부채 (+ 매각예정부채) = 부채총계", "엑셀 수식", "차이 1원 이하면 '일치'", "formula"),
             Col("수식: 지배+비지배", 11, "지배기업 소유주지분 + 비지배지분 = 자본총계 (연결만)", "엑셀 수식", "차이 1원 이하면 '일치'", "formula"),
             Col("수식: 부채+자본=자산", 12, "부채총계 + 자본총계 = 자산총계", "엑셀 수식", "차이 1원 이하면 '일치'", "formula"),
             Col("수식: 현금 흐름", 12, "기초 현금 + 현금 순증감 + 환율변동효과 = 기말 현금", "엑셀 수식",
                 "회사에 따라 순증감에 환율효과가 이미 들어 있어 '기초+순증감=기말' 또는 '기초+순증감+환율효과=기말' 중 하나가 "
                 "1원 이하 차이면 '일치'", "formula"),
             Col("수식: DB=원문", 11, "부채·자본 API 값과 원문 읽은 값이 같은지", "엑셀 수식", "차이 1,000원 미만이면 같음", "formula"),
             Col("접수번호", 15, "이 값을 준 사업보고서 접수번호", "raw.dart_financial.rcept_no"),
             Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    want = {(sj, aid): name for sj, aid, name, _ in API_ACCOUNTS}
    data = {}
    for r in db.fetch_dicts(conn, """SELECT corp_code, corp_name, bsns_year, fs_div, sj_div, account_id, account_nm, thstrm_amount, rcept_no
                                    FROM raw.dart_financial ORDER BY corp_code, bsns_year, fs_div, ord"""):
        k = (r["corp_code"], r["bsns_year"], r["fs_div"])
        row = data.setdefault(k, {"회사명": src.name.get(r["corp_code"], r["corp_name"]), "corp_code": r["corp_code"],
                                  "사업연도": r["bsns_year"], "재무제표": {"CFS": "연결", "OFS": "별도"}.get(r["fs_div"], r["fs_div"]),
                                  "접수번호": r["rcept_no"], "원문": link(r["rcept_no"])})
        col = want.get((r["sj_div"], r["account_id"]))
        nm = re.sub(r"\s", "", r["account_nm"] or "")
        if r["sj_div"] == "BS" and "매각예정" in nm and "기타포괄" not in nm:
            col = col or ("매각예정부채(원)" if "부채" in nm else "매각예정자산(원)")
        if col and row.get(col) is None:
            try:
                row[col] = float(str(r["thstrm_amount"]).replace(",", ""))
            except ValueError:
                pass
    rows = []
    for (c, y, fs), row in data.items():
        basis = {"CFS": "연결", "OFS": "별도"}.get(fs)
        res = []
        for item, key in (("liabilities_won", "부채 원문 읽은 값(원)"), ("equity_won", "자본 원문 읽은 값(원)")):
            v = src.verified("dart_financial", c, y, item, basis)
            if v is not None and v["basis"] == basis:
                row[key] = num(v["src_value"])
                res.append(("부채 " if item == "liabilities_won" else "자본 ") + v["result"])
        row["대조 결과"] = " · ".join(res) or "대조 안 함"
        rows.append(row)
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"], r["재무제표"]))

    def total(parts, whole, extra=None):
        def f(L, i):
            ps = [f"{L[p]}{i}" for p in parts]
            w = f"{L[whole]}{i}"
            ok = f'ABS({"+".join(ps)}-{w})<=1'
            if extra:
                ok = f'OR({ok},ABS({"+".join(ps)}+N({L[extra]}{i})-{w})<=1)'
            return f'=IF(COUNT({",".join(ps)},{w})<{len(ps) + 1},"빈칸",IF({ok},"일치","불일치"))'
        return f

    def cash(L, i):
        b, d, fx, e = (f"{L[n]}{i}" for n in ("기초 현금(원)", "현금 순증감(원)", "환율변동효과(원)", "기말 현금(원)"))
        return f'=IF(COUNT({b},{d},{e})<3,"빈칸",IF(OR(ABS({b}+{d}-{e})<=1,ABS({b}+{d}+N({fx})-{e})<=1),"일치","불일치"))'

    def match(L, i):
        p = [(f"{L['부채총계(원)']}{i}", f"{L['부채 원문 읽은 값(원)']}{i}"), (f"{L['자본총계(원)']}{i}", f"{L['자본 원문 읽은 값(원)']}{i}")]
        return f'=IF(COUNT({p[0][1]},{p[1][1]})=0,"원문 값 없음",IF(AND({same(*p[0], 1000)},{same(*p[1], 1000)}),"같음","다름"))'

    return cols, rows, {"수식: 자산 합": total(["유동자산(원)", "비유동자산(원)"], "자산총계(원)", "매각예정자산(원)"),
                        "수식: 부채 합": total(["유동부채(원)", "비유동부채(원)"], "부채총계(원)", "매각예정부채(원)"),
                        "수식: 지배+비지배": total(["지배기업 소유주지분(원)", "비지배지분(원)"], "자본총계(원)"),
                        "수식: 부채+자본=자산": total(["부채총계(원)", "자본총계(원)"], "자산총계(원)"),
                        "수식: 현금 흐름": cash, "수식: DB=원문": match}


# --- 04-1 현금흐름표 배당 계정별 -------------------------------------------------------------------


def sheet_cf_accounts(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "raw.cf_dividend_account.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "raw.cf_dividend_account.corp_code"),
            Col("사업연도", 8, "현금흐름표 기간 연도", "raw.cf_dividend_account.bsns_year"),
            Col("재무제표", 8, "연결(CFS) 또는 별도(OFS)", "raw.cf_dividend_account.fs_div"),
            Col("판정", 16, "이 계정을 배당금 지급 합계에 넣었는지: 포함 / 제외(받은 배당) / 제외(비지배지분) 등",
                "raw.cf_dividend_account.judgement (04-1 원천 판정)", "'포함'인 계정만 더해 04 배당금 지급 값을 만듦"),
            Col("계정명", 30, "현금흐름표에 적힌 계정 이름", "raw.cf_dividend_account.account_nm"),
            Col("표준계정코드", 30, "DART XBRL 표준계정 코드 (미사용이면 회사 자체 계정)", "raw.cf_dividend_account.account_id"),
            Col("당기 금액(원)", 17, "그 해 금액 (현금 유출은 회사에 따라 양수 또는 음수로 적힘)", "raw.cf_dividend_account.thstrm_amount", "", "num"),
            Col("전기 금액(원)", 17, "앞 해 금액 (같은 보고서의 비교기간)", "raw.cf_dividend_account.frmtrm_amount", "", "num"),
            Col("기수", 10, "보고서의 기수 표기", "raw.cf_dividend_account.term_name"),
            Col("04 합계 DB(원)", 17, "이 회사·연도의 배당금 지급 합계 (포함 계정을 더한 값)", "raw.cf_dividend_paid.paid_mil × 1,000,000", "", "num"),
            Col("수식: 포함 계정 합", 13, "이 회사·연도 '포함' 계정 당기 금액(절댓값) 합이 04 합계와 같은지", "엑셀 수식",
                "SUMIFS로 같은 회사·연도·재무제표의 '포함' 행 금액을 더해 04 합계와 비교. 04 합계가 백만 원 단위라 100만 원 미만 차이는 같음", "formula"),
            Col("접수번호", 15, "이 값을 준 사업보고서", "raw.cf_dividend_account.rcept_no"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    paid = {(r["corp_code"], r["bsns_year"], r["fs_div"]): r for r in db.fetch_dicts(conn, "SELECT * FROM raw.cf_dividend_paid")}
    rows = []
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.cf_dividend_account ORDER BY corp_name, bsns_year, ord"):
        p = paid.get((r["corp_code"], r["bsns_year"], r["fs_div"]), {})
        rows.append({"회사명": src.name.get(r["corp_code"], r["corp_name"]), "corp_code": r["corp_code"], "사업연도": r["bsns_year"],
                     "재무제표": {"CFS": "연결", "OFS": "별도"}.get(r["fs_div"], r["fs_div"]), "판정": r["judgement"],
                     "계정명": r["account_nm"], "표준계정코드": r["account_id"], "당기 금액(원)": num(r["thstrm_amount"]),
                     "전기 금액(원)": num(r["frmtrm_amount"]), "기수": r["term_name"],
                     "04 합계 DB(원)": num(p["paid_mil"]) * 1e6 if p.get("paid_mil") is not None else None,
                     "접수번호": r["rcept_no"], "원문": link(r["rcept_no"])})

    def check(L, i):
        n = len(rows) + 1
        rng = lambda c: f"${L[c]}$2:${L[c]}${n}"  # noqa: E731
        total = f"{L['04 합계 DB(원)']}{i}"
        crit = (f'{rng("corp_code")},{L["corp_code"]}{i},{rng("사업연도")},{L["사업연도"]}{i},'
                f'{rng("재무제표")},{L["재무제표"]}{i},{rng("판정")},"포함"')
        pos = f'SUMIFS({rng("당기 금액(원)")},{crit},{rng("당기 금액(원)")},">0")'
        neg = f'SUMIFS({rng("당기 금액(원)")},{crit},{rng("당기 금액(원)")},"<0")'
        return f'=IF(NOT(ISNUMBER({total})),"04 합계 없음",IF(ABS({pos}-{neg}-{total})<{TOL},"같음","다름"))'

    return cols, rows, {"수식: 포함 계정 합": check}


# --- 02 배당 표 전체 항목 ---------------------------------------------------------------------------

DIV_ITEMS = [  # (원천 item, 종류, 열 이름, 뜻)
    ("주당액면가액(원)", "-", "주당 액면가(원)", "1주당 액면가"),
    ("(연결)당기순이익(백만원)", "-", "(연결)당기순이익(백만원)", "배당 표에 적힌 연결 당기순이익 (지배주주 몫)"),
    ("(별도)당기순이익(백만원)", "-", "(별도)당기순이익(백만원)", "배당 표에 적힌 별도 당기순이익"),
    ("(연결)주당순이익(원)", "-", "(연결)주당순이익(원)", "배당 표에 적힌 연결 주당순이익"),
    ("현금배당금총액(백만원)", "-", "현금배당금총액(백만원)", "1년 현금배당 합계 (보통+우선, 중간·분기 포함) = D"),
    ("주식배당금총액(백만원)", "-", "주식배당금총액(백만원)", "주식으로 준 배당의 금액"),
    ("(연결)현금배당성향(%)", "-", "(연결)현금배당성향(%)", "현금배당금총액 ÷ (연결)당기순이익 × 100 (회사가 적은 값)"),
    ("주당 현금배당금(원)", "보통", "주당 현금배당금 보통(원)", "보통주 1주당 현금배당금"),
    ("주당 현금배당금(원)", "우선", "주당 현금배당금 우선(원)", "우선주·종류주 1주당 현금배당금"),
    ("주당 현금배당금(원)", "-", "주당 현금배당금 종류 미표기(원)", "주식 종류 칸이 '-'인 행 (종류 칸이 없는 표면 보통주)"),
    ("현금배당수익률(%)", "보통", "현금배당수익률 보통(%)", "보통주 현금배당수익률"),
    ("현금배당수익률(%)", "우선", "현금배당수익률 우선(%)", "우선주 현금배당수익률"),
    ("주당 주식배당(주)", "보통", "주당 주식배당 보통(주)", "보통주 1주당 주식배당 주식 수"),
    ("주당 주식배당(주)", "우선", "주당 주식배당 우선(주)", "우선주 1주당 주식배당 주식 수"),
    ("주식배당수익률(%)", "보통", "주식배당수익률 보통(%)", "보통주 주식배당수익률"),
    ("주식배당수익률(%)", "우선", "주식배당수익률 우선(%)", "우선주 주식배당수익률"),
]


def stock_kind(k: str) -> str:
    k = (k or "").replace(" ", "")
    if k in ("", "-"):
        return "-"
    if "우선" in k or "종류" in k or "없는" in k:
        return "우선"
    return "보통" if "보통" in k or "있는" in k else "-"


def sheet_div_items(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "raw.dart_dividend_item.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "raw.dart_dividend_item.corp_code"),
            Col("사업연도", 8, "배당 표의 그 열이 가리키는 사업연도", "raw.dart_dividend_item.bsns_year"),
            Col("보고서 접수번호", 15, "배당 표를 읽은 사업보고서 (한 보고서가 당기·전기·전전기 3개 연도를 줌)", "raw.dart_dividend_item.rcept_no"),
            Col("보고서 열", 8, "그 보고서 배당 표의 당기·전기·전전기 중 어느 열인지", "보고서 기간 연도 − 사업연도")]
    cols += [Col(name, 13, meaning, f"raw.dart_dividend_item.value (item '{item}', 주식 종류 {kind})",
                 "원문 표 값 그대로. '-'는 빈칸으로 둠", "pct" if "%" in name else "num") for item, kind, name, meaning in DIV_ITEMS]
    cols += [Col("DB에서 쓰는 곳", 30, "이 표의 값 중 core 표로 넘어간 항목", "raw.dart_dividend_item.col_02"),
             Col("원문 재대조", 34, "코드가 DART 원문을 다시 읽어 이 행의 칸들과 맞춰 본 결과 (N칸 일치 / 불일치 칸과 두 값 / 원문에서 못 찾음)",
                 "core.core_source_verify (source/scripts/verify_sources.py)", "원문 표·본문에서 같은 항목·주식 종류·연도 열을 찾아 글자·숫자 비교 (차이 0)"),
             Col("수식: 배당성향", 11, "(연결)현금배당성향이 현금배당금총액 ÷ (연결)당기순이익 × 100 과 같은지", "엑셀 수식",
                 "|성향 − 총액÷순이익×100| ≤ 0.5 이면 '일치'. 순이익이 0 이하이거나 빈칸이면 '계산 대상 아님'. "
                 "회사가 별도 순이익·다른 기간으로 계산해 적은 경우도 '불일치'로 나오므로 원문 주석을 봄", "formula"),
             Col("자동 조사", 36, "수식·대조에 걸린 행을 코드가 자료로 더 살펴본 원인 (사람 확인 전 참고, 걸리지 않은 행은 빈칸)",
                "source/scripts/export_review_workbook.py investigate_*", "원인을 못 정하면 '원문 확인 필요'"),
             Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    want = {(item, kind): name for item, kind, name, _ in DIV_ITEMS}
    data = {}
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.dart_dividend_item ORDER BY corp_code, bsns_year, rcept_no"):
        k = (r["corp_code"], r["bsns_year"], r["rcept_no"])
        row = data.setdefault(k, {"회사명": src.name.get(r["corp_code"], r["corp_name"]), "corp_code": r["corp_code"],
                                  "사업연도": r["bsns_year"], "보고서 접수번호": r["rcept_no"],
                                  "보고서 열": src.column_of(r["rcept_no"], r["bsns_year"]), "원문": link(r["rcept_no"]), "_uses": set()})
        col = want.get((r["item"], stock_kind(r["stock_kind"])))
        if col and row.get(col) is None and r["value"] not in (None, "", "-"):
            try:
                row[col] = float(str(r["value"]).replace(",", ""))
            except ValueError:
                pass
        if r["col_02"] and r["col_02"] != "(안 씀)":
            row["_uses"].add(r["col_02"])
    rows = []
    for row in data.values():
        row["DB에서 쓰는 곳"] = ", ".join(sorted(row.pop("_uses")))
        row["원문 재대조"] = src.recheck_text("dart_dividend_item", (row["보고서 접수번호"], str(row["사업연도"])))
        row["자동 조사"] = investigate_payout(row)
        rows.append(row)
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"], r["보고서 접수번호"]))

    def check(L, i):
        p, t, n = (f"{L[c]}{i}" for c in ("(연결)현금배당성향(%)", "현금배당금총액(백만원)", "(연결)당기순이익(백만원)"))
        return (f'=IF(OR(NOT(ISNUMBER({n})),{n}<=0,NOT(ISNUMBER({t}))),"계산 대상 아님",'
                f'IF(NOT(ISNUMBER({p})),"성향 빈칸",IF(ABS({p}-{t}/{n}*100)<=0.5,"일치","불일치")))')

    return cols, rows, {"수식: 배당성향": check}


# --- 05 배당 결정 공시 -------------------------------------------------------------------------


def sheet_decision(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "raw.dividend_decision.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "raw.dividend_decision.corp_code"),
            Col("접수번호", 15, "배당 결정 공시 접수번호", "raw.dividend_decision.rcept_no"),
            Col("공시일", 11, "공시 접수일", "raw.dividend_decision.disclosed_on"),
            Col("공시명", 30, "보고서명 (정정이면 [기재정정] 등)", "raw.dividend_decision.report_nm"),
            Col("배당구분", 9, "결산 · 중간 · 분기", "raw.dividend_decision.div_kind"),
            Col("배당종류", 11, "현금배당 · 현금ㆍ현물배당 · 주식배당 등", "raw.dividend_decision.div_type"),
            Col("귀속 사업연도", 8, "이 배당이 속한 사업연도", "raw.dividend_decision.attributed_year",
                "배당기준일 연도. 결산배당 기준일이 다음 해 1~6월이면 앞 해 (2024년 배당절차 개선 반영)", "num"),
            Col("보통주 주당배당금(원)", 12, "1주당 배당금 (보통주)", "raw.dividend_decision.dps_common_won", "", "num"),
            Col("우선주 주당배당금(원)", 12, "1주당 배당금 (우선주·종류주)", "raw.dividend_decision.dps_pref_won", "", "num"),
            Col("시가배당률 보통(%)", 9, "보통주 시가배당률", "raw.dividend_decision.yield_common_pct", "", "pct"),
            Col("배당금총액(원)", 17, "이 공시의 배당금 총액 (보통+우선)", "raw.dividend_decision.total_won", "공시 표에 적힌 값. 코드가 더하지 않음", "num"),
            Col("배당기준일", 11, "배당 받을 주주를 정하는 날", "raw.dividend_decision.record_date"),
            Col("배당금지급 예정일", 11, "지급 예정일 (원문 '-'이면 빈칸)", "raw.dividend_decision.pay_date"),
            Col("읽은 상태", 12, "원문을 읽은 결과 (정상 · 원문 못 받음 등)", "raw.dividend_decision.parse_status"),
            Col("원문 재대조", 34, "코드가 DART 원문을 다시 읽어 이 행의 칸들과 맞춰 본 결과 (N칸 일치 / 불일치 칸과 두 값 / 원문에서 못 찾음)",
                 "core.core_source_verify (source/scripts/verify_sources.py)", "원문 표·본문에서 같은 항목·주식 종류·연도 열을 찾아 글자·숫자 비교 (차이 0)"),
            Col("출처", 14, "05 원천 · DART로 채움(첨부정정의 원공시)", "raw.dividend_decision / core.core_dart_fill (decision.*)"),
            Col("수식 검산", 12, "배당기준일이 지급 예정일보다 앞서는지", "엑셀 수식", "두 날짜(YYYY-MM-DD 글자)를 비교, 하나라도 비면 '날짜 빈칸'", "formula"),
            Col("자동 조사", 36, "수식·대조에 걸린 행을 코드가 자료로 더 살펴본 원인 (사람 확인 전 참고, 걸리지 않은 행은 빈칸)",
                "source/scripts/export_review_workbook.py investigate_*", "원인을 못 정하면 '원문 확인 필요'"),
            Col("원문", 10, "누르면 DART 원문이 열림", "raw.dividend_decision.link", "", "link")]
    rows = [{"회사명": r["corp_name"], "corp_code": r["corp_code"], "접수번호": r["rcept_no"], "공시일": str(r["disclosed_on"] or ""),
             "공시명": r["report_nm"], "배당구분": r["div_kind"], "배당종류": r["div_type"], "귀속 사업연도": r["attributed_year"],
             "보통주 주당배당금(원)": num(r["dps_common_won"]), "우선주 주당배당금(원)": num(r["dps_pref_won"]),
             "시가배당률 보통(%)": num(r["yield_common_pct"]), "배당금총액(원)": num(r["total_won"]),
             "배당기준일": r["record_date"], "배당금지급 예정일": r["pay_date"], "읽은 상태": r["parse_status"], "출처": "05 원천",
             "원문 재대조": src.recheck_text("dividend_decision", r["rcept_no"]),
             "원문": r["link"] or link(r["rcept_no"])} for r in db.fetch_dicts(conn, "SELECT * FROM raw.dividend_decision")]
    fills = {}
    for r in db.fetch_dicts(conn, "SELECT * FROM core.core_dart_fill WHERE item LIKE 'decision.%%'"):
        fills.setdefault(r["ref"], {})[r["item"]] = r
    for ref, f in fills.items():
        t = f.get("decision.total_won") or next(iter(f.values()))
        rows.append({"회사명": src.name.get(t["corp_code"], t["corp_code"]), "corp_code": t["corp_code"], "접수번호": ref,
                     "공시명": "DART 원공시 (첨부정정의 원공시)", "귀속 사업연도": t["bsns_year"],
                     "보통주 주당배당금(원)": num(f["decision.dps_common_won"]["value_won"]) if "decision.dps_common_won" in f else None,
                     "배당금총액(원)": num(t["value_won"]),
                     "배당기준일": f["decision.record_date"]["value_text"] if "decision.record_date" in f else None,
                     "읽은 상태": t["status"], "출처": "DART로 채움", "원문": link(ref)})
    for r in rows:
        r["자동 조사"] = investigate_decision(r)
    rows.sort(key=lambda r: (r["회사명"], r["접수번호"]))

    def check(L, i):
        a, b = f"{L['배당기준일']}{i}", f"{L['배당금지급 예정일']}{i}"
        return f'=IF(OR({a}="",{b}=""),"날짜 빈칸",IF({a}<={b},"순서 맞음","순서 이상"))'

    return cols, rows, {"수식 검산": check}


# --- 03 별도재무제표 보완 자료 ------------------------------------------------------------------

OFS_ITEMS = [("당기순이익_전체", "당기순이익 전체(원)", "별도 손익계산서 당기순이익 (별도는 지배·비지배 구분 없음)"),
             ("당기순이익", "당기순이익(원)", "배당 표 '(별도)당기순이익' 행 (백만 원 → 원)"),
             ("부채총계", "부채총계(원)", "별도 재무상태표 부채총계"), ("자본총계", "자본총계(원)", "별도 재무상태표 자본총계"),
             ("배당금지급_지급기준", "배당금 지급(원)", "별도 현금흐름표 배당금의 지급 (실제 낸 현금)"),
             ("현금배당금총액", "현금배당금총액(원)", "배당 표 현금배당금총액 (보통+우선, 1년 합계)"),
             ("주당현금배당금", "주당현금배당금(원)", "배당 표 보통주 1주당 현금배당금"),
             ("현금배당성향", "현금배당성향(%)", "현금배당금총액 ÷ (별도)당기순이익 × 100"),
             ("주당순이익", "주당순이익(원)", "별도 기본주당순이익")]


def sheet_ofs(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "03 별도_보완결과.csv 회사명"),
            Col("corp_code", 10, "DART 고유번호", "03 별도_보완결과.csv corp_code"),
            Col("사업연도", 8, "사업연도", "03 별도_보완결과.csv 사업연도")]
    for key, label, meaning in OFS_ITEMS:
        how = ("팀 자료가 '계산: 현금배당금총액 ÷ (별도)당기순이익 × 100'으로 만든 값" if key == "현금배당성향" else "팀 자료의 확정값 (감사보고서 원문·사업보고서 배당 표·API 중 하나)")
        cols.append(Col(label, 16 if "%" not in label else 10, meaning, f"03 별도_보완결과.csv 확정값 (항목 {key})", how,
                        "pct" if "%" in label else "num"))
    cols += [Col("팀 자료 대조 요약", 26, "팀 자료의 '대조' 칸을 항목별로 모은 것 (일치 · 불일치 · 감사보고서 값 없음 …)", "03 별도_보완결과.csv 대조"),
             Col("남은 빈칸 DART 확인", 34, "팀 자료에서 비어 있던 칸을 코드가 DART로 다시 본 결과 (항목: 상태 값)", "core.core_dart_fill (item ofs.*)"),
             Col("수식: 배당성향", 12, "현금배당성향이 현금배당금총액 ÷ 당기순이익 × 100 과 같은지", "엑셀 수식",
                 "|성향 − 총액÷당기순이익×100| ≤ 0.5 이면 '일치'. 당기순이익이 0 이하이거나 빈칸이면 '계산 대상 아님'", "formula"),
             Col("재무 원문", 10, "부채총계를 읽은 원문 (감사보고서 등)", "03 별도_보완결과.csv 원문 · 접수번호", "", "link"),
             Col("배당 원문", 10, "현금배당금총액을 읽은 원문 (사업보고서)", "03 별도_보완결과.csv 원문 · 접수번호", "", "link")]
    b = pd.read_csv(OFS_FILE, dtype=str, encoding="utf-8-sig")
    fills = {}
    for r in db.fetch_dicts(conn, "SELECT * FROM core.core_dart_fill WHERE item LIKE 'ofs.%%'"):
        v = f" {float(r['value_won']):,.2f}".rstrip("0").rstrip(".") if r["value_won"] is not None else ""
        fills.setdefault((r["corp_code"], r["bsns_year"]), []).append(f"{r['item'][4:]}: {r['status']}{v}")
    rows = []
    for (c, y), g in b.groupby(["corp_code", "사업연도"], sort=False):
        g = g.set_index("항목")
        r = {"회사명": g["회사명"].iloc[0], "corp_code": c, "사업연도": int(y)}
        for key, label, _ in OFS_ITEMS:
            r[label] = pd.to_numeric(g.at[key, "확정값"], errors="coerce") if key in g.index else None
        agg = g["대조"].dropna().map(lambda s: s.split("(")[0]).value_counts()
        r["팀 자료 대조 요약"] = " · ".join(f"{k} {v}" for k, v in agg.items())
        r["남은 빈칸 DART 확인"] = " / ".join(fills.get((c, int(y)), []))

        def src_link(key):
            if key not in g.index:
                return None
            u, rc = g.at[key, "원문"], g.at[key, "접수번호"]
            return u if isinstance(u, str) and u.startswith("http") else link(rc if isinstance(rc, str) else None)

        r["재무 원문"], r["배당 원문"] = src_link("부채총계"), src_link("현금배당금총액")
        rows.append(r)
    rows.sort(key=lambda r: (r["회사명"], r["사업연도"]))

    def check(L, i):
        p, t, n = f"{L['현금배당성향(%)']}{i}", f"{L['현금배당금총액(원)']}{i}", f"{L['당기순이익(원)']}{i}"
        return (f'=IF(OR(NOT(ISNUMBER({n})),{n}<=0,NOT(ISNUMBER({t}))),"계산 대상 아님",'
                f'IF(NOT(ISNUMBER({p})),"성향 빈칸",IF(ABS({p}-{t}/{n}*100)<=0.5,"일치","불일치")))')

    return cols, rows, {"수식: 배당성향": check}


# --- 09 KIND 고배당기업 공시 ---------------------------------------------------------------------


def sheet_kind(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "raw.kind_list.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "raw.kind_list.corp_code"),
            Col("고배당기업 여부", 9, "KIND 고배당기업 공시상 해당 여부", "raw.kind_list.is_high_dividend"),
            Col("최종 접수번호", 15, "가장 최근(정정 포함) 고배당기업 공시", "raw.kind_list.final_rcept_no"),
            Col("공시일", 11, "최종 공시일", "raw.kind_list.final_disclosed_on"),
            Col("결정일", 11, "이사회 결정일", "raw.kind_list.decision_date"),
            Col("B2024(원)", 17, "공시에 적힌 기준 배당액 B2024", "raw.kind_list.b2024_won", "공시 원문 값. 코드가 계산하지 않음", "num"),
            Col("직전 사업연도", 8, "공시가 말하는 직전 사업연도", "raw.kind_list.prev_year"),
            Col("직전 배당성향(%)", 9, "직전 사업연도 배당성향", "raw.kind_list.prev_payout_pct", "", "pct"),
            Col("직전 배당총액 D(원)", 17, "직전 사업연도 현금배당총액", "raw.kind_list.prev_d_won", "", "num"),
            Col("전전 배당총액 D(원)", 17, "그 앞 사업연도 현금배당총액", "raw.kind_list.prevprev_d_won", "", "num"),
            Col("증가율(%)", 9, "공시에 적힌 배당 증가율", "raw.kind_list.growth_pct", "", "pct"),
            Col("감액배당 메모", 30, "공시 원문의 감액배당(자본준비금 감액) 관련 문장", "raw.kind_list.reduction_note"),
            Col("원문 재대조", 34, "코드가 DART 원문을 다시 읽어 이 행의 칸들과 맞춰 본 결과 (N칸 일치 / 불일치 칸과 두 값 / 원문에서 못 찾음)",
                 "core.core_source_verify (source/scripts/verify_sources.py)", "원문 표·본문에서 같은 항목·주식 종류·연도 열을 찾아 글자·숫자 비교 (차이 0)"),
            Col("수식: 증가율", 12, "증가율이 직전 D ÷ 전전 D − 1 과 같은지", "엑셀 수식",
                "|증가율 − (직전D÷전전D−1)×100| ≤ 0.5 이면 '일치' (공시가 소수 한 자리·정수로 반올림해 적음)", "formula"),
            Col("자동 조사", 36, "수식·대조에 걸린 행을 코드가 자료로 더 살펴본 원인 (사람 확인 전 참고, 걸리지 않은 행은 빈칸)",
                "source/scripts/export_review_workbook.py investigate_*", "원인을 못 정하면 '원문 확인 필요'"),
            Col("원문", 10, "누르면 DART 원문이 열림", "raw.kind_list.link", "", "link")]
    rows = [{"회사명": r["corp_name"], "corp_code": r["corp_code"], "고배당기업 여부": r["is_high_dividend"],
             "최종 접수번호": r["final_rcept_no"], "공시일": str(r["final_disclosed_on"] or ""), "결정일": str(r["decision_date"] or ""),
             "B2024(원)": num(r["b2024_won"]), "직전 사업연도": r["prev_year"], "직전 배당성향(%)": num(r["prev_payout_pct"]),
             "직전 배당총액 D(원)": num(r["prev_d_won"]), "전전 배당총액 D(원)": num(r["prevprev_d_won"]), "증가율(%)": num(r["growth_pct"]),
             "감액배당 메모": r["reduction_note"], "원문 재대조": src.recheck_text("kind_list", r["final_rcept_no"] or r["corp_code"]),
             "원문": r["link"]}
            for r in db.fetch_dicts(conn, "SELECT * FROM raw.kind_list ORDER BY corp_name")]
    for r in rows:
        r["자동 조사"] = investigate_kind(r)

    def check(L, i):
        g, a, b = f"{L['증가율(%)']}{i}", f"{L['직전 배당총액 D(원)']}{i}", f"{L['전전 배당총액 D(원)']}{i}"
        return (f'=IF(OR(NOT(ISNUMBER({g})),NOT(ISNUMBER({a})),NOT(ISNUMBER({b})),{b}=0),"계산 불가",'
                f'IF(ABS({g}-({a}/{b}-1)*100)<=0.5,"일치","불일치"))')

    return cols, rows, {"수식: 증가율": check}


# --- 00 회사 목록 -----------------------------------------------------------------------------------


def sheet_company(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "core.core_company.corp_name"),
            Col("corp_code", 10, "DART 고유번호 (8자리)", "core.core_company.corp_code"),
            Col("종목코드", 9, "KRX 보통주 종목코드 (6자리)", "core.core_company.stock_code"),
            Col("시장", 8, "코스피 · 코스닥", "core.core_company.market"),
            Col("결산월", 6, "회계연도 끝나는 달", "core.core_company.fiscal_month", "", "num"),
            Col("12월 결산", 7, "결산월이 12월인지 (TRUE/FALSE)", "core.core_company.is_december_fye"),
            Col("KIND 유형(2025)", 10, "KIND 고배당기업 유형 (우수형 등)", "core.core_company.kind_type_2025"),
            Col("KIND 고배당 공시 해당", 9, "KIND 고배당기업 공시 대상인지", "core.core_company.kind_listed"),
            Col("상장 우선주 코드", 14, "같은 회사의 상장 우선주 종목코드 (여러 개면 쉼표)", "core.core_company.pref_stock_codes"),
            Col("우선주 상태", 14, "우선주 확인 결과", "core.core_company.pref_status"),
            Col("DART 사업보고서 연도", 22, "DART 사업보고서 검색에서 나온 보고서 기간 연도들", "DART 사업보고서 검색 (dsab007, 캐시)"),
            Col("원천 파일", 34, "이 행을 만든 원천 파일", "core.core_company.source_file"),
            Col("원문 재대조", 34, "코드가 DART 원문을 다시 읽어 이 행의 칸들과 맞춰 본 결과 (N칸 일치 / 불일치 칸과 두 값 / 원문에서 못 찾음)",
                 "core.core_source_verify (source/scripts/verify_sources.py)", "원문 표·본문에서 같은 항목·주식 종류·연도 열을 찾아 글자·숫자 비교 (차이 0)"),
            Col("수식 검산", 12, "종목코드가 6자리이고 결산월과 12월 결산 표시가 맞는지", "엑셀 수식",
                "LEN(종목코드)=6 이고 (결산월=12) = 12월 결산 이면 '정상', 아니면 '확인'", "formula"),
            Col("원문", 10, "누르면 DART 회사 개황이 열림", "dart.fss.or.kr/dsae001/selectPopup.ax?selectKey=corp_code", "", "link")]
    years = {}
    for (corp, y) in src.reports:
        years.setdefault(corp, []).append(y)
    rows = [{"회사명": r["corp_name"], "corp_code": r["corp_code"], "종목코드": r["stock_code"], "시장": r["market"],
             "결산월": r["fiscal_month"], "12월 결산": r["is_december_fye"], "KIND 유형(2025)": r["kind_type_2025"],
             "KIND 고배당 공시 해당": r["kind_listed"], "상장 우선주 코드": r["pref_stock_codes"], "우선주 상태": r["pref_status"],
             "DART 사업보고서 연도": ", ".join(str(y) for y in sorted(years.get(r["corp_code"], []))), "원천 파일": r["source_file"],
             "원문 재대조": src.recheck_text("core_company", r["corp_code"]),
             "원문": f"https://dart.fss.or.kr/dsae001/selectPopup.ax?selectKey={r['corp_code']}"}
            for r in db.fetch_dicts(conn, "SELECT * FROM core.core_company ORDER BY corp_name")]

    def check(L, i):
        code, m, dec = (f"{L[c]}{i}" for c in ("종목코드", "결산월", "12월 결산"))
        return f'=IF(AND(LEN({code})=6,({m}=12)={dec}),"정상","확인")'

    return cols, rows, {"수식 검산": check}


# --- 2027 최소 필요 배당액 (계산 결과) ---------------------------------------------------------------


def sheet_min(conn, src: Sources):
    cols = [Col("회사명", 16, "회사 이름", "core.core_company.corp_name"),
            Col("corp_code", 10, "DART 고유번호", "core.core_min_dividend_2027.corp_code"),
            Col("시나리오", 13, "2026 순이익 가정: 최근 3년 최저 · 2025년(기본) · 최근 3년 최고. 값이 같은 시나리오는 하나로 합침",
                "core.core_min_dividend_2027.scenario", "source/core/min_dividend.py scenarios()"),
            Col("가정한 2026 순이익(원)", 17, "이 시나리오에서 쓴 2026 지배주주 순이익", "core.core_min_dividend_2027.ni2026_won",
                "2023~2025 지배주주 순이익(빈칸 채움·원문 수정 반영, core.v_financial_year_verified) 중 최저·2025년·최고", "num"),
            Col("2023 순이익(원)", 16, "계산에 들어간 2023 지배주주 순이익", "core.v_financial_year_verified.ni_owner_won", "", "num"),
            Col("2024 순이익(원)", 16, "계산에 들어간 2024 지배주주 순이익", "core.v_financial_year_verified.ni_owner_won", "", "num"),
            Col("2025 순이익(원)", 16, "계산에 들어간 2025 지배주주 순이익", "core.v_financial_year_verified.ni_owner_won", "", "num"),
            Col("2025 순이익 DB 원본(원)", 16, "빈칸 채움·원문 수정 전 원본 값 (참고)", "core.core_financial_year.ni_owner_won", "", "num"),
            Col("B2024(원)", 15, "기준 배당소득 B (2024)", "core.core_dividend_year.b_won (2024)", "KIND 고배당기업 공시 값 (source/core/b_income.py)", "num"),
            Col("D2025(원)", 15, "2025 이익배당금액 (계산에 쓴 값)", "KIND 공시 직전 사업연도 이익배당금액, 없으면 DART 현금배당총액", "source/core/b_income.py", "num"),
            Col("결과", 10, "계산됨 · 판정 보류 · 어려움", "core.core_min_dividend_2027.status"),
            Col("최소 필요 배당액(원)", 17, "2027 분리과세 요건을 맞추려면 2026 사업연도에 필요한 최소 현금배당", "core.core_min_dividend_2027.min_won",
                "source/core/min_dividend.py min_required() (조문 대응: report/검증/조문_코드_대응표.md)", "num"),
            Col("근거 조건", 16, "최소액을 정한 조건", "core.core_min_dividend_2027.basis"),
            Col("사유", 26, "판정 보류·계산 근거 설명", "core.core_min_dividend_2027.reasons"),
            Col("2025 대비(%)", 9, "최소액 ÷ D2025 × 100", "core.core_min_dividend_2027.ratio_to_2025_pct", "", "pct"),
            Col("추가로 필요한 배당(원)", 16, "최소액 − 이미 결의한 2026 중간·분기배당", "core.core_min_dividend_2027.additional_won", "", "num"),
            Col("2025만큼 주면 통과", 9, "2025와 같은 배당이면 요건을 맞추는지", "core.core_min_dividend_2027.pass_if_same_as_2025"),
            Col("수식 검산", 13, "가정한 2026 순이익이 시나리오 정의(2023~2025 순이익의 최저·2025·최고)와 같은지", "엑셀 수식",
                "최저=MIN, 기본=2025, 최고=MAX. 1원 이하 차이면 '일치'", "formula"),
            Col("원문", 10, "2025 사업보고서", "DART 사업보고서 검색", "", "link")]
    fin = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM core.v_financial_year_verified WHERE bsns_year BETWEEN 2023 AND 2025")}
    orig = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_financial_year WHERE bsns_year = 2025")}
    div = {(r["corp_code"], r["bsns_year"]): r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_dividend_year WHERE bsns_year IN (2024, 2025)")}
    kind = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT corp_code, prev_year, prev_d_won FROM raw.kind_list")}
    rows = []
    for r in db.fetch_dicts(conn, "SELECT * FROM core.core_min_dividend_2027"):
        c = r["corp_code"]
        rows.append({"회사명": src.name.get(c, c), "corp_code": c, "시나리오": r["scenario"], "가정한 2026 순이익(원)": num(r["ni2026_won"]),
                     **{f"{y} 순이익(원)": num(fin.get((c, y), {}).get("ni_owner_won")) for y in (2023, 2024, 2025)},
                     "2025 순이익 DB 원본(원)": num(orig.get(c, {}).get("ni_owner_won")),
                     "B2024(원)": num(div.get((c, 2024), {}).get("b_won")),
                     "D2025(원)": num(kind[c]["prev_d_won"]) if c in kind and str(kind[c]["prev_year"]) == "2025" and kind[c]["prev_d_won"] is not None
                     else num(div.get((c, 2025), {}).get("d_dart_won")),
                     "결과": r["status"], "최소 필요 배당액(원)": num(r["min_won"]), "근거 조건": r["basis"], "사유": r["reasons"],
                     "2025 대비(%)": num(r["ratio_to_2025_pct"]), "추가로 필요한 배당(원)": num(r["additional_won"]),
                     "2025만큼 주면 통과": r["pass_if_same_as_2025"], "원문": link(src.own_report(c, 2025)[0])})
    order = {"최근 3년 최저": 0, "2025년 (기본)": 1, "최근 3년 최고": 2}
    rows.sort(key=lambda r: (r["회사명"], order.get(r["시나리오"], 9)))

    def check(L, i):
        sc, ni = f"{L['시나리오']}{i}", f"{L['가정한 2026 순이익(원)']}{i}"
        y = [f"{L[f'{y} 순이익(원)']}{i}" for y in (2023, 2024, 2025)]
        rng = ",".join(y)
        want = f'IF({sc}="최근 3년 최저",MIN({rng}),IF({sc}="최근 3년 최고",MAX({rng}),{y[2]}))'
        return f'=IF(NOT(ISNUMBER({ni})),"빈칸",IF(ABS({ni}-{want})<=1,"일치","불일치"))'

    return cols, rows, {"수식 검산": check}


# --- 안내·진행현황·항목_설명 -------------------------------------------------------------------------

SHEETS = [("00_회사목록", sheet_company, "분석 대상 638사 목록 (종목코드·시장·결산월·KIND 유형·우선주)"),
          ("02_재무", sheet_fin, "회사·사업연도별 지배주주 순이익·부채총계·자본총계 (2017~2026 전체 행)"),
          ("02_배당표", sheet_div, "회사·사업연도별 현금배당총액 D·보통주 주당배당금 + 배당 결정 공시 합계 대조"),
          ("02_배당표_전체항목", sheet_div_items, "사업보고서 배당 표의 모든 항목 (보고서·연도별 1행)"),
          ("04_배당금지급", sheet_cf, "현금흐름표 배당금의 지급 합계 (2023~2026, 04 원천 수집 기간)"),
          ("04-1_배당계정별", sheet_cf_accounts, "현금흐름표 배당 관련 계정 1줄당 1행과 포함·제외 판정 (04 합계의 구성)"),
          ("04-2_재무API", sheet_bs, "DART 재무 API 재무상태표·현금흐름표 주요 계정 (회사·연도·연결/별도별)"),
          ("05_배당결정공시", sheet_decision, "배당 결정 공시 1건당 1행 (2023-01 ~ 2026-10 접수분 + 첨부정정의 원공시)"),
          ("03_별도보완", sheet_ofs, "팀 별도재무제표 보완 자료(03)의 확정값, 회사·사업연도별 9개 항목 (DB 밖 파일)"),
          ("09_KIND고배당", sheet_kind, "KIND 고배당기업 공시 원문 값 (B2024 등)"),
          ("2027_최소배당액", sheet_min, "계산 결과: 2027 분리과세 요건용 최소 필요 배당액 (시나리오별)")]


def guide(ws, counts: dict):
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 22, 110
    rows = [("원픽 DB 전수 검산표", None), (None, None),
            ("만든 날", f"{date.today().isoformat()} (onepick DB와 03 별도 보완 자료에서 내보냄, source/scripts/export_review_workbook.py)"),
            ("대상", "core.core_company 638사. 행은 거르지 않고 전부 넣음 (코드 대조가 '일치'인 행도 코드가 잘못 읽었을 수 있어 사람이 봄)"),
            ("항목 뜻", "열마다 뜻·원천(DB 표.열)·더한 값·계산 방법은 '항목_설명' 시트에 있습니다."),
            ("빠진 것", "증자·감자·분할·병합은 별도 검산표(source/scripts/export_capital_check.py). KRX 주가는 행이 많아 넣지 않음. "
                      "core.core_judgement_2026(2026 판정)은 챗봇·B2024 자료로 따로 봄."),
            (None, None)]
    rows += [(n, f"{d} — {counts[n]:,}행") for n, _, d in SHEETS]
    rows += [(None, None),
            ("검산 방법", "1) 행의 '원문 열기'로 DART 공시를 엽니다. 2) 노란 칸 앞의 숫자·날짜를 원문과 한 칸씩 비교합니다 "
                        "(DB 값·원문 읽은 값·분석 값 모두). 3) 노란 칸 '검토 상태'에서 확인완료 / 확인불가 / 정정됨(배제) 중 하나를 고르고, "
                        "검토자 이름을 고르고, 메모에 틀린 칸과 원문 값을 적습니다."),
            ("고칠 칸", "노란색 칸(검토 상태·검토자·메모)만 적어 주세요. 다른 칸은 DB 값이라 고치지 않습니다."),
            ("검토 상태 뜻", "확인완료 = 원문과 같음 · 확인불가 = 원문을 못 찾거나 판단 못 함 · 정정됨(배제) = 값이 틀려 분석에서 빼야 함 (메모에 원문 값)"),
            ("수식 칸", "연두색 '수식 검산' 칸은 엑셀 수식입니다. 표 안 합계·비율과 DB↔원문 일치를 자동으로 봅니다. '다름'·'불일치'인 행부터 보면 빠릅니다."),
            ("대조 결과 뜻", "일치 · 일치(단위 반올림: DB가 백만 원 단위) · 불일치(원인) · 원문 못 읽음(표를 못 읽었거나 합계 검산 실패) · "
                          "원문 없음(그 해 사업보고서 없음) · DART로 채움(DB 빈칸을 원문에서 읽음) · 빈칸: 이유"),
            ("분석 값", "판정·분석에 실제로 쓰는 값입니다. DB 빈칸은 채운 값, 원문과 다른 칸은 설정(restated_policy = original)에 따라 원문 값."),
            ("나눠 보기", "필터로 사업연도·대조 결과를 골라 네 분이 나눠 보시면 됩니다. 진행 정도는 '진행현황' 시트가 자동으로 셉니다."),
            ("금액 단위", "원. 주당 금액은 원/주, 비율은 %. 날짜는 원문 표기 그대로"),
            (None, None),
            ("작성 예시", "검토 상태: 정정됨(배제) · 검토자: 한상범 · 메모: 부채총계 원문 141,888,422,460 ↔ DB 141,888,000,000 (2024 사업보고서 연결 재무상태표)")]
    for i, (a, b) in enumerate(rows, 1):
        ws.cell(i, 1, a).font = Font(name=F, bold=True, size=14 if i == 1 else 10)
        c = ws.cell(i, 2, b)
        c.font = Font(name=F, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, (a, _) in enumerate(rows, 1):
        if a in ("고칠 칸", "작성 예시"):
            ws.cell(i, 2).fill = FILL


def progress(ws, counts: dict, state_col: dict, reviewer_col: dict, sheets: list | None = None):
    sheets = SHEETS if sheets is None else sheets
    head = ["시트", "전체 행"] + STATES + ["미검토", "진행률"] + REVIEWERS
    for j, h in enumerate(head, 1):
        c = ws.cell(1, j, h)
        c.font, c.fill, c.border = Font(name=F, bold=True, color="FFFFFF"), HEAD, BOX
        c.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = 16 if j == 1 else 11
    for i, (name, _, _) in enumerate(sheets, 2):
        last = counts[name] + 1
        st = f"'{name}'!${state_col[name]}$2:${state_col[name]}${last}"
        rv = f"'{name}'!${reviewer_col[name]}$2:${reviewer_col[name]}${last}"
        vals = [name, counts[name]] + [f'=COUNTIF({st},"{s}")' for s in STATES]
        vals += [f"=B{i}-SUM(C{i}:E{i})", f"=IF(B{i}=0,0,SUM(C{i}:E{i})/B{i})"] + [f'=COUNTIF({rv},"{p}")' for p in REVIEWERS]
        for j, v in enumerate(vals, 1):
            c = ws.cell(i, j, v)
            c.font, c.border = Font(name=F, size=10), BOX
            c.number_format = "0.0%" if j == 7 else NUM
    t = len(sheets) + 2
    ws.cell(t, 1, "합계").font = Font(name=F, bold=True)
    for j in range(2, len(head) + 1):
        col = get_column_letter(j)
        c = ws.cell(t, j, f"=IF(B{t}=0,0,SUM(C{t}:E{t})/B{t})" if j == 7 else f"=SUM({col}2:{col}{t - 1})")
        c.font, c.border = Font(name=F, bold=True, size=10), BOX
        c.number_format = "0.0%" if j == 7 else NUM
    ws.freeze_panes = "B2"


def describe(ws, specs: list[tuple[str, list[Col]]]):
    head = [("시트", 16), ("열", 26), ("뜻", 60), ("원천 (DB 표.열 / 파일)", 46), ("더한 값·계산 방법", 60)]
    for j, (h, w) in enumerate(head, 1):
        c = ws.cell(1, j, h)
        c.font, c.fill, c.border = Font(name=F, bold=True, color="FFFFFF"), HEAD, BOX
        ws.column_dimensions[get_column_letter(j)].width = w
    i = 2
    for name, cols in specs:
        for col in cols + REVIEW_COLS:
            for j, v in enumerate((name, col.name, col.meaning, col.source, col.how), 1):
                c = ws.cell(i, j, v)
                c.font, c.border = Font(name=F, size=10), BOX
                c.alignment = Alignment(wrap_text=True, vertical="top")
            i += 1
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:E{i - 1}"


def build(conn, out: Path) -> dict[str, int]:
    src = Sources(conn)
    wb = Workbook()
    wb.active.title = "안내"
    prog = wb.create_sheet("진행현황")
    desc = wb.create_sheet("항목_설명")
    counts, specs, state_col, reviewer_col = {}, [], {}, {}
    for name, fn, _ in SHEETS:
        cols, rows, formulas = fn(conn, src)
        counts[name] = write(wb.create_sheet(name), cols, rows, formulas)
        specs.append((name, cols))
        state_col[name] = get_column_letter(len(cols) + 1)
        reviewer_col[name] = get_column_letter(len(cols) + 2)
    guide(wb["안내"], counts)
    progress(prog, counts, state_col, reviewer_col)
    describe(desc, specs)
    wb.calculation.fullCalcOnLoad = True  # 엑셀이 열 때 수식을 계산
    wb.save(out)
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="onepick DB 전체를 파트별 전수 검산표 엑셀로 내보냄")
    ap.add_argument("--out", type=Path, default=EXPORT_DIR / f"원픽_전수검산표_{date.today():%Y%m%d}.xlsx")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with db.connect(args.url) as conn:
        counts = build(conn, args.out)
    print(args.out, " · ".join(f"{k} {v:,}행" for k, v in counts.items()))
