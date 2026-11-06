"""분석에 쓰는 데이터 전체를 엑셀 한 파일로 → output/tables/원픽_분석데이터_<날짜>.xlsx

실행: .venv/bin/python -m scripts.export_dataset
값은 원문 기준 뷰(core.v_financial_year_verified·v_dividend_year_verified)를 쓰고, 칸마다 상태(원본·DART로 채움·
원문으로 수정·결측+이유)를 옆 열에 적는다. 결측 현황 시트는 COUNTIFS 수식이라 데이터 시트를 고치면 다시 계산된다.
KRX 주가(124만 행)는 엑셀 행 수 한도를 넘어 넣지 않는다.
"""
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from core import db
from core.dart_fill import source_tag

OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "tables"
FONT, BOLD = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
HEAD_FILL = PatternFill("solid", fgColor="E7ECF3")
MISSING_FILL = PatternFill("solid", fgColor="FBEDEA")
REVIEW_FILL = PatternFill("solid", fgColor="FFF6DD")
UNREAD_FILL = PatternFill("solid", fgColor="ECE6F5")
WON = "#,##0;(#,##0);-"
LINK = Font(name="Arial", size=10, color="1F4E99", underline="single")
REVIEWERS = ["한상범", "김민지", "박예지", "조진영"]
REVIEW_STATES = ["확인완료", "확인불가", "정정됨(배제)"]


def q(conn, sql):
    return pd.DataFrame(db.fetch_dicts(conn, sql))


def fin_status(orig, verify, fill):
    """재무·배당 지급 한 칸의 상태."""
    if pd.notna(orig):
        if verify is None:
            return "원본 (원문 대조 안 함)"
        res, kind, use = verify
        if res in ("일치", "일치(단위 반올림)"):
            return "원본 (원문 일치)"
        if res == "불일치":
            return f"원문으로 수정 ({kind})" if use else f"원본 유지 ({kind} · 원문과 다름)"
        return {"원문 못 읽음": "원본 (원문 못 읽음)", "원문 없음": "원본 (그 해 사업보고서 없음)",
                "원문 외화 표시": "원본 (원문 외화 표시)"}.get(res, f"원본 ({res})")
    if fill is not None:
        st, note = fill
        if st == "채움":
            return "DART로 채움"
        return f"결측: {st}" + (f" ({note})" if note else "")
    return "결측"


def build(conn):
    company = q(conn, """SELECT corp_code, corp_name, stock_code, market, fiscal_month, kind_type_2025, kind_listed,
                                pref_stock_codes FROM core.core_company ORDER BY corp_name""")
    name = dict(zip(company.corp_code, company.corp_name))
    verify = {(r["target"], r["corp_code"], r["bsns_year"], r["item"]): r for r in db.fetch_dicts(conn, """
        SELECT v.target, v.corp_code, v.bsns_year, v.item, v.result, m.correction_kind, m.use_source
        FROM core.core_dart_verify v LEFT JOIN core.v_dart_mismatch m USING (target, corp_code, bsns_year, item, basis)""")}
    fills = {(r["corp_code"], r["bsns_year"], r["item"]): (r["status"], r["note"] or r["check_result"] or "")
             for r in db.fetch_dicts(conn, "SELECT corp_code, bsns_year, item, status, note, check_result FROM core.core_dart_fill "
                                           "WHERE item NOT LIKE 'ofs.%' AND item NOT LIKE 'decision.%'")}

    # 출처 공시: 원문 대조에 쓴 그 해 사업보고서 > 빈칸을 채운 공시 > 원천 자료의 접수번호
    src_verify = {}
    for r in db.fetch_dicts(conn, "SELECT target, corp_code, bsns_year, src_rcept_no, src_title FROM core.core_dart_verify "
                                  "WHERE src_rcept_no <> '' ORDER BY item"):
        src_verify.setdefault((r["target"], r["corp_code"], r["bsns_year"]), (r["src_rcept_no"], r["src_title"]))
    src_fill = {}
    for r in db.fetch_dicts(conn, "SELECT corp_code, bsns_year, item, source_rcept_no, source_title FROM core.core_dart_fill "
                                  "WHERE source_rcept_no <> '' AND item NOT LIKE 'ofs.%'"):
        src_fill.setdefault((r["corp_code"], r["bsns_year"], r["item"]), (r["source_rcept_no"], r["source_title"]))
    fill_title = {(r["corp_code"], r["bsns_year"], r["item"]): r["source_title"] for r in db.fetch_dicts(
        conn, "SELECT corp_code, bsns_year, item, source_title FROM core.core_dart_fill WHERE status = '채움'")}
    src_item = {(r["corp_code"], r["bsns_year"]): (r["rcept_no"], "02 원천 사업보고서 (배당에 관한 사항)") for r in db.fetch_dicts(
        conn, "SELECT corp_code, bsns_year, min(rcept_no) AS rcept_no FROM raw.dart_dividend_item WHERE rcept_no IS NOT NULL GROUP BY 1, 2")}
    src_cf = {(r["corp_code"], r["bsns_year"]): (r["rcept_no"], "04 원천 사업보고서 (현금흐름표)") for r in db.fetch_dicts(
        conn, "SELECT corp_code, bsns_year, rcept_no FROM raw.cf_dividend_paid WHERE rcept_no IS NOT NULL")}
    dec_list = {}
    for r in db.fetch_dicts(conn, """SELECT corp_code, attributed_year AS y, rcept_no FROM raw.dividend_decision
                                    WHERE parse_status = '정상' AND attributed_year IS NOT NULL
                                    UNION SELECT corp_code, bsns_year, ref FROM core.core_dart_fill WHERE item = 'decision.total_won'
                                    ORDER BY 3"""):
        dec_list.setdefault((r["corp_code"], r["y"]), []).append(r["rcept_no"])

    def first(*cands):
        return next((c for c in cands if c), ("", ""))

    def vtuple(target, corp, year, item):
        r = verify.get((target, corp, year, item))
        return None if r is None else (r["result"], r["correction_kind"], bool(r["use_source"]))

    # 재무
    orig = q(conn, "SELECT corp_code, bsns_year, ni_owner_won, liabilities_won, equity_won FROM core.core_financial_year")
    ver = q(conn, "SELECT * FROM core.v_financial_year_verified WHERE bsns_year BETWEEN 2018 AND 2025")
    f = ver.merge(orig, on=["corp_code", "bsns_year"], suffixes=("", "_orig"))
    fin = pd.DataFrame({"corp_code": f.corp_code, "회사명": f.corp_code.map(name), "사업연도": f.bsns_year,
                        "재무 기준": f.fs_basis})
    for item, label in (("ni_owner_won", "지배주주 순이익(원)"), ("liabilities_won", "부채총계(원)"), ("equity_won", "자본총계(원)")):
        fin[label] = f[item].astype(float)
        fin[label.replace("(원)", " 상태")] = [fin_status(o, vtuple("core_financial_year", c, y, item), fills.get((c, y, item)))
                                             for o, c, y in zip(f[item + "_orig"], f.corp_code, f.bsns_year)]
    srcs = [first(src_verify.get(("core_financial_year", c, y)), src_fill.get((c, y, "ni_owner_won")),
                  src_fill.get((c, y, "liabilities_won")), src_item.get((c, y))) for c, y in zip(f.corp_code, f.bsns_year)]
    fin["출처 태그"] = [" / ".join(dict.fromkeys(t for t in (source_tag(fill_title.get((c, y, k))) for k in ("ni_owner_won", "liabilities_won", "equity_won")) if t))
                     for c, y in zip(f.corp_code, f.bsns_year)]
    fin["원문 공시"] = [t for _, t in srcs]
    fin["원문 접수번호(클릭)"] = [r for r, _ in srcs]
    fin = fin.sort_values(["회사명", "사업연도"])

    # 배당
    d = q(conn, """SELECT v.*, o.d_dart_won AS d_orig, o.d_decision_won AS dec_orig, o.cf_paid_won AS cf_orig, o.dps_common_won AS dps_orig, o.cf_status
                   FROM core.v_dividend_year_verified v JOIN core.core_dividend_year o USING (corp_code, bsns_year)""")
    div = pd.DataFrame({"corp_code": d.corp_code, "회사명": d.corp_code.map(name), "사업연도": d.bsns_year,
                        "현금배당총액 D(원)": d.d_dart_won.astype(float)})
    div["현금배당총액 D 상태"] = [fin_status(o, None, fills.get((c, y, "d_dart_won"))).replace("원본 (원문 대조 안 함)", "원본 (02 DART 배당 표)")
                           for o, c, y in zip(d.d_orig, d.corp_code, d.bsns_year)]
    div["배당 결정 공시 합계(원)"] = d.d_decision_won.astype(float)
    div["배당 결정 공시 상태"] = ["원본 (05 결정 공시)" if pd.notna(o) else "DART로 채움 (원공시)" if pd.notna(v)
                           else "결측: 그 해 현금배당 결정 공시 없음" for o, v in zip(d.dec_orig, d.d_decision_won)]
    div["현금흐름표 배당금 지급(원)"] = d.cf_paid_won_verified.astype(float)
    div["현금흐름표 배당금 지급 상태"] = [
        fin_status(o, vtuple("cf_dividend_paid", c, y, "dividends_paid_won"), fills.get((c, y, "cf_paid_won")))
        if pd.notna(o) or (c, y, "cf_paid_won") in fills else (f"결측: {s}" if s else "결측")
        for o, c, y, s in zip(d.cf_orig, d.corp_code, d.bsns_year, d.cf_status)]
    div["보통주 주당배당금(원)"] = d.dps_common_won.astype(float)
    div["보통주 주당배당금 상태"] = [fin_status(o, None, fills.get((c, y, "dps_common_won"))).replace("원본 (원문 대조 안 함)", "원본 (02)")
                             for o, c, y in zip(d.dps_orig, d.corp_code, d.bsns_year)]
    div["배당소득 B(원)"] = d.b_won.astype(float)
    div["배당소득 B 상태"] = [(f"결측: {st}" if st != "미산출" else "결측: 미산출 (판정에 쓰는 2024·2025만 산출)") if pd.isna(b)
                          else f"산출: {st}" for b, st in zip(d.b_won, d.b_status)]
    div["배당 표 원문 접수번호(클릭)"] = [first(src_fill.get((c, y, "d_dart_won")), src_fill.get((c, y, "dps_common_won")), src_item.get((c, y)))[0]
                                for c, y in zip(d.corp_code, d.bsns_year)]
    cf_src = [first(src_verify.get(("cf_dividend_paid", c, y)), src_fill.get((c, y, "cf_paid_won")), src_cf.get((c, y)))
              for c, y in zip(d.corp_code, d.bsns_year)]
    div["현금흐름표 원문 공시"] = [t for _, t in cf_src]
    div["현금흐름표 원문 접수번호(클릭)"] = [r for r, _ in cf_src]
    div["배당 결정 공시 접수번호(배당결정공시 시트)"] = [", ".join(dec_list.get((c, y), [])) for c, y in zip(d.corp_code, d.bsns_year)]
    div = div.sort_values(["회사명", "사업연도"])

    decisions = q(conn, """
        SELECT rcept_no AS 접수번호, corp_code, corp_name AS 회사명, disclosed_on AS 공시일, report_nm AS 공시명,
               div_kind AS 배당구분, div_type AS 배당종류, attributed_year AS 귀속사업연도, dps_common_won AS "보통주 주당배당금(원)",
               total_won AS "배당금총액(원)", record_date AS 배당기준일, parse_status AS 상태, '05 원천' AS 출처,
               rcept_no AS "원문 접수번호(클릭)"
        FROM raw.dividend_decision
        UNION ALL
        SELECT t.ref, t.corp_code, c.corp_name, NULL, 'DART 원공시 (첨부정정의 원공시)', NULL, NULL, t.bsns_year, p.value_won,
               t.value_won, r.value_text, t.status, 'DART로 채움', t.ref
        FROM core.core_dart_fill t JOIN core.core_company c USING (corp_code)
        LEFT JOIN core.core_dart_fill p ON p.ref = t.ref AND p.item = 'decision.dps_common_won'
        LEFT JOIN core.core_dart_fill r ON r.ref = t.ref AND r.item = 'decision.record_date'
        WHERE t.item = 'decision.total_won' ORDER BY 3, 4""")
    kind = q(conn, """SELECT corp_name AS 회사명, corp_code, is_high_dividend AS 고배당기업여부, final_rcept_no AS 최종접수번호,
                             final_disclosed_on AS 최종공시일, b2024_won AS "원문 2024 배당소득(원)", prev_d_won AS "원문 직전 이익배당금액(원)",
                             prevprev_d_won AS "원문 전전 이익배당금액(원)", prev_payout_pct AS "원문 직전 배당성향(%)",
                             growth_pct AS "원문 증가율(%)", reduction_note AS 감액배당_문구, link AS "원문 링크(클릭)"
                      FROM raw.kind_list ORDER BY 1""")
    judge = q(conn, """SELECT c.corp_name AS 회사명, j.corp_code, j.status AS 판정, j.route AS 경로, j.tag AS 꼬리표, j.reasons AS 사유
                       FROM core.core_judgement_2026 j JOIN core.core_company c USING (corp_code) ORDER BY 1""")
    review = q(conn, """
        SELECT '원문 대조 불일치' AS 구분, m.correction_kind AS 세부, c.corp_name AS 회사명, m.corp_code, m.bsns_year AS 사업연도,
               m.target || '.' || m.item AS 항목, m.db_value AS "DB 값(원)", m.src_value AS "원문 값(원)", m.note AS 이유,
               'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' || m.src_rcept_no AS "원문 링크(클릭)"
        FROM core.v_dart_mismatch m LEFT JOIN core.core_company c USING (corp_code) WHERE m.correction_kind = '사람 확인'
        UNION ALL
        SELECT '빈칸 채우기 확인 필요', '', c.corp_name, f.corp_code, f.bsns_year, f.item, NULL, f.value_won,
               coalesce(nullif(f.note, ''), f.check_result), f.source_url
        FROM core.core_dart_fill f LEFT JOIN core.core_company c USING (corp_code)
        WHERE f.status = '확인 필요' AND f.item NOT LIKE 'ofs.%' ORDER BY 1, 3, 5""")
    return company, fin, div, decisions, kind, judge, review


def write_sheet(ws, df, money_cols=(), widths=None):
    ws.append(list(df.columns))
    for c in ws[1]:
        c.font, c.fill, c.alignment = BOLD, HEAD_FILL, Alignment(wrap_text=True, vertical="center")
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) or v is pd.NA else v for v in row])
    cols = list(df.columns)
    for j, col in enumerate(cols, 1):
        letter = get_column_letter(j)
        ws.column_dimensions[letter].width = (widths or {}).get(col, min(max(len(str(col)) * 1.6, 10), 40))
        for cell in ws[letter][1:]:
            cell.font = FONT
            if col in money_cols:
                cell.number_format = WON
            if "(클릭)" in col and isinstance(cell.value, str) and cell.value:  # 원문 공시 링크
                url = cell.value if cell.value.startswith("http") else f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={cell.value}"
                cell.hyperlink, cell.font = url, LINK
            if "상태" in col and isinstance(cell.value, str):
                if cell.value.startswith("결측"):
                    cell.fill = MISSING_FILL
                elif "사람 확인" in cell.value or "원본 유지" in cell.value:
                    cell.fill = REVIEW_FILL
                elif "원문 못 읽음" in cell.value:
                    cell.fill = UNREAD_FILL
    ws.freeze_panes = "C2" if "회사명" in cols[:3] else "A2"
    ws.auto_filter.ref = ws.dimensions


def review_inputs(ws, df):
    """검토필요 시트의 검토자·검토 상태 칸을 목록에서만 고르게 한다."""
    last = len(df) + 1
    for col, options in (("검토자", REVIEWERS), ("검토 상태", REVIEW_STATES)):
        letter = get_column_letter(list(df.columns).index(col) + 1)
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True,
                            showErrorMessage=True, errorTitle="목록에서 고르기", error=", ".join(options) + " 중에서 고르세요")
        dv.add(f"{letter}2:{letter}{last}")
        ws.add_data_validation(dv)
        ws.column_dimensions[letter].width = 14


def guide_sheet(ws, counts):
    rows = [
        ["원픽 분석 데이터", ""],
        ["만든 날", date.today().isoformat()],
        ["원천", "DART·KIND 원자료(638사 판, 임시) → onepick DB. 빈칸은 DART 원문으로 다시 읽어 채움, 재무 값은 그 해 사업보고서와 전수 대조"],
        ["값 기준", "원문 기준 뷰(core.v_financial_year_verified·v_dividend_year_verified). 원본 표는 고치지 않았음"],
        ["재작성 값 설정", "restated_policy = original (원래 공시 값 사용, 팀 결정 전 임시)"],
        ["", ""],
        ["원문 링크", "'(클릭)'이 붙은 열의 접수번호·링크를 누르면 DART(또는 KIND) 원문이 열립니다. 재무는 원문 대조에 쓴 그 해 사업보고서, 채운 값은 그 값을 읽은 공시, 대조 못 한 값은 원천 자료의 사업보고서입니다."],
        ["", ""],
        ["상태 표기", "뜻"],
        ["원본 (원문 일치)", "DB 원본 값이 그 해 사업보고서 원문과 같음 (백만 원 반올림 차이 포함)"],
        ["원본 (원문 대조 안 함 / 사업보고서 없음)", "DB 원본 값. 원문과 맞춰 보지 못함"],
        ["원본 (원문 못 읽음)", "사업보고서는 있지만 표를 못 읽었거나 합계 검산이 안 맞아 대조 못 함 (보라색)"],
        ["DART로 채움", "DB에 없던 값을 DART 원문에서 읽어 넣음 (표 안 합계 검산 통과)"],
        ["원문으로 수정 (확실)", "DB 값이 다른 기준·순이익 전체·USD 값 등이라 원문 값으로 바꿈"],
        ["원문으로 수정 (재작성 선택)", "DB가 1~2년 뒤 재작성 값이라 그 해 원래 공시 값으로 바꿈 (설정에 따름)"],
        ["원문으로 수정 (사람 확인)", "원인을 모르는 불일치. 원문 값을 쓰되 사람 확인 필요 (노란색)"],
        ["결측: …", "값 없음과 그 이유 (빨간색). 예: 보통주 배당 없음(원문 -), 그 해 결정 공시 없음, 미산출"],
        ["", ""],
        ["시트", "내용"],
        ["결측_현황", "시트별 결측·채움·수정 칸 수 (수식, 데이터 시트를 고치면 다시 계산)"],
        ["회사", f"회사 {counts['회사']}곳"],
        ["재무_연도별", f"2018~2025 지배주주 순이익·부채·자본 ({counts['재무']}행)"],
        ["배당_연도별", f"2017~2026 현금배당총액·결정 공시 합계·현금흐름표 지급·주당배당금·B ({counts['배당']}행)"],
        ["배당결정공시", f"배당 결정 공시 1건당 1행 ({counts['결정']}행, DART로 찾은 원공시 포함)"],
        ["KIND_고배당", "KIND 고배당기업 공시 원문 값 (B2024 등)"],
        ["판정_2026", "2026 사업연도 판정 결과 (B는 source/scripts/build_judgement.py: B2024 KIND 공시, B2025 = D2025 + 주식배당, 감액배당이면 보류)"],
        ["검토필요", f"사람이 볼 칸 ({counts['검토']}행): 원인 모르는 원문 불일치, 빈칸 채우기 확인 필요. "
                     f"검토자({'·'.join(REVIEWERS)})와 검토 상태({'·'.join(REVIEW_STATES)})는 목록에서 고름"],
        ["", ""],
        ["빠진 것", "KRX 주가(124만 행)는 엑셀 행 수 한도를 넘어 넣지 않음 (DB raw.krx_price_daily, 사용 등급 뷰 core.v_price_daily)"],
    ]
    for r in rows:
        ws.append(r)
    ws["A1"].font = Font(name="Arial", size=14, bold=True)
    for r in (9, 19):
        for c in ws[r]:
            c.font, c.fill = BOLD, HEAD_FILL
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.font != BOLD and c.row not in (9, 19):
                c.font = FONT
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 42, 110


def missing_sheet(ws, n_fin, n_div):
    """COUNTIFS 수식으로 연도별·항목별 칸 수를 센다."""
    ws.append(["시트", "항목", "사업연도", "전체 행", "결측", "DART로 채움", "원문으로 수정", "원본"])
    for c in ws[1]:
        c.font, c.fill = BOLD, HEAD_FILL
    specs = [("재무_연도별", "지배주주 순이익", "F", n_fin, range(2018, 2026)), ("재무_연도별", "부채총계", "H", n_fin, range(2018, 2026)),
             ("재무_연도별", "자본총계", "J", n_fin, range(2018, 2026)),
             ("배당_연도별", "현금배당총액 D", "E", n_div, range(2017, 2027)), ("배당_연도별", "배당 결정 공시 합계", "G", n_div, range(2017, 2027)),
             ("배당_연도별", "현금흐름표 배당금 지급", "I", n_div, range(2017, 2027)), ("배당_연도별", "보통주 주당배당금", "K", n_div, range(2017, 2027)),
             ("배당_연도별", "배당소득 B", "M", n_div, range(2017, 2027))]
    for sheet, label, col, n, years in specs:
        last = n + 1
        yr = f"{sheet}!$C$2:$C${last}"
        st = f"{sheet}!${col}$2:${col}${last}"
        for y in years:
            r = ws.max_row + 1
            ws.append([sheet, label, str(y), f"=COUNTIFS({yr},{y})", f'=COUNTIFS({yr},{y},{st},"결측*")',
                       f'=COUNTIFS({yr},{y},{st},"DART로 채움*")', f'=COUNTIFS({yr},{y},{st},"원문으로 수정*")',
                       f'=COUNTIFS({yr},{y},{st},"원본*")'])
            ws.cell(r, 5).fill = MISSING_FILL
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = FONT
    for col, w in zip("ABCDEFGH", (14, 22, 10, 10, 10, 12, 14, 10)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"


def main(url: str):
    with db.connect(url) as conn:
        company, fin, div, decisions, kind, judge, review = build(conn)
    wb = Workbook()
    guide = wb.active
    guide.title = "안내"
    guide_sheet(guide, {"회사": len(company), "재무": len(fin), "배당": len(div), "결정": len(decisions), "검토": len(review)})
    missing_sheet(wb.create_sheet("결측_현황"), len(fin), len(div))
    company = company.rename(columns={"corp_name": "회사명", "stock_code": "종목코드", "market": "시장", "fiscal_month": "결산월",
                                      "kind_type_2025": "KIND 유형(2025)", "kind_listed": "KIND 고배당 공시 해당",
                                      "pref_stock_codes": "상장 우선주 코드"})
    write_sheet(wb.create_sheet("회사"), company[["corp_code", "회사명"] + [c for c in company.columns if c not in ("corp_code", "회사명")]])
    write_sheet(wb.create_sheet("재무_연도별"), fin, money_cols=[c for c in fin.columns if c.endswith("(원)")],
                widths={c: 34 for c in fin.columns if c.endswith("상태")})
    write_sheet(wb.create_sheet("배당_연도별"), div, money_cols=[c for c in div.columns if c.endswith("(원)")],
                widths={c: 34 for c in div.columns if c.endswith("상태")})
    write_sheet(wb.create_sheet("배당결정공시"), decisions, money_cols=["보통주 주당배당금(원)", "배당금총액(원)"])
    write_sheet(wb.create_sheet("KIND_고배당"), kind, money_cols=[c for c in kind.columns if c.endswith("(원)")])
    write_sheet(wb.create_sheet("판정_2026"), judge)
    review = review.assign(**{"검토자": None, "검토 상태": None, "검토 메모": None})
    ws = wb.create_sheet("검토필요")
    write_sheet(ws, review, money_cols=["DB 값(원)", "원문 값(원)"], widths={"이유": 60, "원문 링크(클릭)": 50, "검토 메모": 40})
    review_inputs(ws, review)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"원픽_분석데이터_{date.today():%Y%m%d}.xlsx"
    wb.calculation.fullCalcOnLoad = True  # 결측_현황 수식은 엑셀에서 열 때 계산된다
    wb.save(out)
    print(f"  {out.name}: 재무 {len(fin):,} · 배당 {len(div):,} · 결정 공시 {len(decisions):,} · 검토 {len(review):,}행")
    return out


if __name__ == "__main__":
    main(db.database_url())
