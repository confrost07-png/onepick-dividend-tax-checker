"""4조참치 협조 자료 → onepick DB partner 스키마 (source/db/schema.sql partner.*).

실행: .venv/bin/python -m scripts.load_partner [--src 원본 폴더] [--url postgresql://localhost/onepick]
값은 검산표 엑셀과 같은 코드(source/scripts/export_partner_workbook.py)로 뽑아, 엑셀과 DB가 따로 놀지 않게 한다.
4조 수집 대상 회사를 모두 넣고 company.grp로 나눈다: 대조군(우리 638사 밖, 분석용) · 겹침(우리 638사와 겹침, 대조용만).
주식 총수·최대주주의 주식수는 원문 표 단위 표시(주 · 천주 · 백만주)로 곱해 주 단위로 맞춘다.
다시 돌리면 partner 표만 비우고 새로 채운다. raw·core·ref 표는 건드리지 않는다.
"""
import argparse
import json
import os
import re
from pathlib import Path

from core import db
from core.share_total import share_class
from scripts import export_partner_workbook as pw

TABLES = ["partner.company", "partner.report", "partner.financial_year", "partner.dividend_year", "partner.dividend_item",
          "partner.share_total", "partner.major_holder", "partner.fs_line", "partner.filing", "partner.risk_event",
          "partner.audit_opinion"]
FIN = {"지배주주 순이익": "ni", "부채총계": "liabilities", "자본총계": "equity", "자산총계": "assets"}
SHARE = {"Ⅰ. 발행할 주식의 총수": "authorized", "Ⅱ. 현재까지 발행한 주식의 총수": "ever_issued",
         "Ⅲ. 현재까지 감소한 주식의 총수": "decreased", "1. 감자": "reduced", "2. 이익소각": "retired",
         "3. 상환주식의 상환": "redeemed", "4. 기타": "other_decrease", "Ⅳ. 발행주식의 총수": "issued",
         "Ⅴ. 자기주식수": "treasury", "Ⅵ. 유통주식수": "floating"}


unit_factor = pw.unit_factor


def base_date(text: str | None) -> str | None:
    m = re.search(r"\[(\d{8})\]", text or "")
    return m.group(1) if m else None


def scaled(v, factor):
    return None if v is None else v * factor


def company_rows(p: pw.Partner, ours: set[str]):
    for folder, r in p.companies:
        info = p.company_info(r["corp_code"])
        st, cls = r["_status"], r["_cls"]
        yield {"corp_code": r["corp_code"], "grp": "겹침" if r["corp_code"] in ours else "대조군", "corp_name": r["corp_name"],
               "stock_code": r["stock_code"] or None, "corp_cls": r["corp_cls"], "market": pw.MARKET.get(r["corp_cls"], r["corp_cls"]),
               "listed_now": st.get("listed_now") or None, "delist_date": st.get("delist_date") or None,
               "delist_reason": st.get("delist_reason") or None, "fiscal_month": int(r["acc_mt"]) if r["acc_mt"].isdigit() else None,
               "industry": pw.INDUSTRIES[folder], "ksic_code": r["ksic_code"] or None, "ksic_name": r["ksic_name"] or None,
               "classify_method": r["method"] or None, "classify_reason": r["reason"] or None,
               "induty_code": info.get("induty_code") or None, "est_dt": info.get("est_dt") or None,
               "source": f"4조 {folder}/lists/companies.csv · common/company/{r['corp_code']}.json"}


def report_rows(p: pw.Partner):
    for corp, ms in p.manifest.items():
        for m in ms:
            yield {"rcept_no": m["rcept_no"], "corp_code": corp, "period": m["period"], "bsns_year": int(m["period"][:4]),
                   "report_nm": m["report_nm"], "rcept_dt": m["rcept_dt"], "version": m["version"], "is_first": m["is_first"] == "Y",
                   "is_latest_full": m["is_latest_full"] == "Y", "doc_status": pw.GOT if m["status"] == "수집완료" else pw.CANNOT,
                   "api_status": m["last_api_status"] or None,
                   "notes_sections": int(m["notes_sections"]) if m["notes_sections"].isdigit() else None}


def financial_rows(p: pw.Partner):
    for r in pw.sheet_fin(p)[1]:
        rep = p.report(r["corp_code"], r["사업연도"])
        out = {"corp_code": r["corp_code"], "bsns_year": r["사업연도"], "fs_basis": r["재무 기준"] or None,
               "source_rcept_no": r["접수번호"] or None, "source_column": r["원천 열"] or None,
               "report_rcept_no": rep["rcept_no"] if rep else None}
        for label, key in FIN.items():
            out |= {f"{key}{'_owner' if key == 'ni' else ''}_won": r[f"{label}(원)"], f"{key}_status": r[f"{label} 상태"],
                    f"{key}_reason": r[f"{label} 사유"] or None}
        yield out


def dividend_rows(p: pw.Partner, ex: pw.Extract):
    cf = {(r["corp_code"], r["사업연도"]): r for r in pw.sheet_cf(p)[1]}
    for r in pw.sheet_div(p, ex)[1]:
        c = cf[(r["corp_code"], r["사업연도"])]
        yield {"corp_code": r["corp_code"], "bsns_year": r["사업연도"],
               "d_won": r.get("현금배당총액 D(원)"), "d_mil_raw": r.get("D 원문 값(백만원)"), "d_status": r["D 상태"],
               "d_reason": r.get("D 사유") or None, "dps_common_won": r.get("보통주 주당배당금(원)"), "dps_status": r["보통주 DPS 상태"],
               "dps_reason": r.get("보통주 DPS 사유") or None, "div_source_rcept_no": r.get("접수번호") or None,
               "div_source_column": r.get("원천 열") or None,
               "cf_paid_won": c["배당금 지급(원)"], "cf_status": c["배당금 지급 상태"], "cf_reason": c["배당금 지급 사유"] or None,
               "cf_accounts": c["더한 계정"] or None, "nci_paid_won": c["비지배지분 배당(원)"], "cf_fs_basis": c["재무 기준"] or None,
               "cf_source_rcept_no": c["접수번호"] or None, "cf_source_column": c["원천 열"] or None}


def dividend_item_rows(ex: pw.Extract):
    for corp, year, rcept, col, item, kind, raw in ex.div_long:
        yield {"corp_code": corp, "bsns_year": year, "rcept_no": rcept, "report_column": col, "item": item,
               "stock_kind": kind, "value": raw, "value_num": pw.dx.number(raw)}


def share_rows(ex: pw.Extract):
    for r in ex.share:
        unit = r.get("기준일·단위")
        f = unit_factor(unit)
        out = {"corp_code": r["corp_code"], "bsns_year": r["사업연도"], "rcept_no": r["접수번호"], "se": r.get("주식 종류"),
               "share_class": share_class(r.get("주식 종류")) if r.get("주식 종류") else None, "stlm_dt": base_date(unit),
               "treasury_pct": r.get("Ⅶ. 자기주식 보유비율"), "unit_text": unit, "unit_factor": f if unit else None,
               "extra": r.get("그 밖의 칸") or None, "note": r.get("비고") or None, "status": r["상태"], "reason": r.get("사유") or None}
        out |= {key: scaled(r.get(name), f) for name, key in SHARE.items()}
        yield out


def holder_rows(ex: pw.Extract):
    for r in ex.holder:
        unit = r.get("기준일·단위")
        f = unit_factor(unit)
        yield {"corp_code": r["corp_code"], "bsns_year": r["사업연도"], "rcept_no": r["접수번호"], "seq": r.get("행 번호"),
               "stlm_dt": base_date(unit), "nm": r.get("성명"), "relate": r.get("관계"), "stock_knd": r.get("주식 종류"),
               "share_class": share_class(r.get("주식 종류")) if r.get("주식 종류") else None,
               "bsis_shares": scaled(r.get("기초 주식수"), f), "bsis_pct": r.get("기초 지분율(%)"),
               "trmend_shares": scaled(r.get("기말 주식수"), f), "trmend_pct": r.get("기말 지분율(%)"), "rm": r.get("비고"),
               "is_total": r.get("합계 행") == "Y" if r["상태"] == pw.HAS else None, "unit_text": unit,
               "unit_factor": f if unit else None, "status": r["상태"], "reason": r.get("사유") or None}


def fs_line_rows(p: pw.Partner):
    for _, c in p.companies:
        corp = c["corp_code"]
        d = p.fnltt(corp)
        if not d.exists():
            continue
        for f in sorted(os.listdir(d)):
            year, fs = int(f[:4]), f.split("_")[-1][:3]
            for x in json.loads((d / f).read_text(encoding="utf-8")).get("list") or []:
                yield {"corp_code": corp, "bsns_year": year, "fs_div": fs, "sj_div": x.get("sj_div"), "sj_nm": x.get("sj_nm"),
                       "ord": int(x["ord"]) if str(x.get("ord", "")).isdigit() else None, "account_id": x.get("account_id"),
                       "account_nm": x.get("account_nm"), "account_detail": x.get("account_detail"),
                       "thstrm_nm": x.get("thstrm_nm"), "thstrm_amount": pw.amount(x.get("thstrm_amount")),
                       "frmtrm_nm": x.get("frmtrm_nm"), "frmtrm_amount": pw.amount(x.get("frmtrm_amount")),
                       "bfefrmtrm_nm": x.get("bfefrmtrm_nm"), "bfefrmtrm_amount": pw.amount(x.get("bfefrmtrm_amount")),
                       "thstrm_add_amount": pw.amount(x.get("thstrm_add_amount")), "currency": x.get("currency"),
                       "rcept_no": x.get("rcept_no")}


def filing_rows(p: pw.Partner):
    for _, ty, tpl, _ in pw.FILING_SHEETS:
        for r in pw.filing_rows(p, tpl):
            dt = r["접수일"]
            yield {"corp_code": r["corp_code"], "pblntf_ty": ty, "rcept_no": r["접수번호"],
                   "rcept_dt": dt if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt or "") else None, "report_nm": r["공시명"],
                   "flr_nm": r["제출인"] or None, "rm": r["비고"] or None, "corp_cls": r["법인 구분"] or None}


def event_csv(p: pw.Partner, file: str):
    for folder in pw.INDUSTRIES:
        path = p.src / folder / "events" / f"{file}.csv"
        for m in pw.read_csv(path) if path.exists() else []:
            if m["corp_code"] in p.folder:
                yield m


def risk_rows(p: pw.Partner):
    keys = ["event_type", "severity", "use", "is_first_of_type", "event_date", "date_basis", "fiscal_period", "rcept_no", "title"]
    for m in event_csv(p, "risk_events"):
        yield {"corp_code": m["corp_code"], **{k: m.get(k) or None for k in keys}, "raw": json.dumps(m, ensure_ascii=False)}


def audit_rows(p: pw.Partner):
    for m in event_csv(p, "audit_from_documents"):
        yield {"corp_code": m["corp_code"], "source": "원문", "fiscal_period": m.get("period") or None, "rcept_no": m.get("rcept_no") or None,
               "fs": m.get("fs") or None, "auditor": None, "opinion": m.get("opinion") or None,
               "going_concern": m.get("going_concern") or None, "raw": json.dumps(m, ensure_ascii=False)}
    for m in event_csv(p, "audit_api"):
        yield {"corp_code": m["corp_code"], "source": "API", "fiscal_period": m.get("fiscal_year") or m.get("call_year") or None,
               "rcept_no": m.get("rcept_no") or None, "fs": None, "auditor": m.get("auditor") or None,
               "opinion": m.get("opinion") or None, "going_concern": m.get("going_concern") or None,
               "raw": json.dumps(m, ensure_ascii=False)}


COLS = {  # 표 → 열 순서 (source/db/schema.sql과 같게)
    "partner.company": ["corp_code", "grp", "corp_name", "stock_code", "corp_cls", "market", "listed_now", "delist_date",
                        "delist_reason", "fiscal_month", "industry", "ksic_code", "ksic_name", "classify_method", "classify_reason",
                        "induty_code", "est_dt", "source"],
    "partner.report": ["rcept_no", "corp_code", "period", "bsns_year", "report_nm", "rcept_dt", "version", "is_first",
                       "is_latest_full", "doc_status", "api_status", "notes_sections"],
    "partner.financial_year": ["corp_code", "bsns_year", "fs_basis", "ni_owner_won", "ni_status", "ni_reason", "liabilities_won",
                               "liabilities_status", "liabilities_reason", "equity_won", "equity_status", "equity_reason",
                               "assets_won", "assets_status", "assets_reason", "source_rcept_no", "source_column", "report_rcept_no"],
    "partner.dividend_year": ["corp_code", "bsns_year", "d_won", "d_mil_raw", "d_status", "d_reason", "dps_common_won",
                              "dps_status", "dps_reason", "div_source_rcept_no", "div_source_column", "cf_paid_won", "cf_status",
                              "cf_reason", "cf_accounts", "nci_paid_won", "cf_fs_basis", "cf_source_rcept_no", "cf_source_column"],
    "partner.dividend_item": ["corp_code", "bsns_year", "rcept_no", "report_column", "item", "stock_kind", "value", "value_num"],
    "partner.share_total": ["corp_code", "bsns_year", "rcept_no", "se", "share_class", "stlm_dt", "authorized", "ever_issued",
                            "decreased", "reduced", "retired", "redeemed", "other_decrease", "issued", "treasury", "floating",
                            "treasury_pct", "unit_text", "unit_factor", "extra", "note", "status", "reason"],
    "partner.major_holder": ["corp_code", "bsns_year", "rcept_no", "seq", "stlm_dt", "nm", "relate", "stock_knd", "share_class",
                             "bsis_shares", "bsis_pct", "trmend_shares", "trmend_pct", "rm", "is_total", "unit_text",
                             "unit_factor", "status", "reason"],
    "partner.fs_line": ["corp_code", "bsns_year", "fs_div", "sj_div", "sj_nm", "ord", "account_id", "account_nm", "account_detail",
                        "thstrm_nm", "thstrm_amount", "frmtrm_nm", "frmtrm_amount", "bfefrmtrm_nm", "bfefrmtrm_amount",
                        "thstrm_add_amount", "currency", "rcept_no"],
    "partner.filing": ["corp_code", "pblntf_ty", "rcept_no", "rcept_dt", "report_nm", "flr_nm", "rm", "corp_cls"],
    "partner.risk_event": ["corp_code", "event_type", "severity", "use", "is_first_of_type", "event_date", "date_basis",
                           "fiscal_period", "rcept_no", "title", "raw"],
    "partner.audit_opinion": ["corp_code", "source", "fiscal_period", "rcept_no", "fs", "auditor", "opinion", "going_concern", "raw"],
}


def load(conn, src, ours: set[str], log=print) -> dict[str, int]:
    """partner 표를 비우고 4조 원본 폴더(src)에서 새로 채운다. ours = 우리 회사 corp_code (겹침 구분용)."""
    p = pw.Partner(src, set())
    log(f"4조 회사 {len(p.companies):,}곳 (겹침 {len(set(p.folder) & ours):,}) · 원문 읽는 중")
    ex = pw.Extract(p)
    ex.run()
    db.apply_schema(conn)
    conn.execute("TRUNCATE " + ", ".join(TABLES))
    makers = {"partner.company": lambda: company_rows(p, ours), "partner.report": lambda: report_rows(p),
              "partner.financial_year": lambda: financial_rows(p), "partner.dividend_year": lambda: dividend_rows(p, ex),
              "partner.dividend_item": lambda: dividend_item_rows(ex), "partner.share_total": lambda: share_rows(ex),
              "partner.major_holder": lambda: holder_rows(ex), "partner.fs_line": lambda: fs_line_rows(p),
              "partner.filing": lambda: filing_rows(p), "partner.risk_event": lambda: risk_rows(p),
              "partner.audit_opinion": lambda: audit_rows(p)}
    counts = {}
    for t in TABLES:
        counts[t] = db.copy_rows(conn, t, COLS[t], makers[t]())
        log(f"  {t} {counts[t]:,}행")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="4조참치 협조 자료 → partner 스키마")
    ap.add_argument("--src", type=Path, default=pw.SRC, help="4조 원본 폴더")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    ours = pw.our_companies(args.url)
    with db.connect(args.url) as conn:
        load(conn, args.src, ours)
