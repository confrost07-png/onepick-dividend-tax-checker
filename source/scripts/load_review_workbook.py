"""검토를 마친 전수 검산표·증자감자 검산표 → DB (팀이 원문을 보고 확정한 값).

실행: .venv/bin/python -m scripts.load_review_workbook <전수검산표 검토본.xlsx> [--capital <증자감자 검산표.xlsx>]
      [--source-check data/processed/review/재무_원문대조_20261029.csv data/processed/review/원문대조_20261102.csv] [--url ...]
순서: load_raw → load_review_workbook → build_core → build_judgement → build_capacity
  원천 표(raw.*)를 고치는 부분이 있어 build_core보다 먼저 돌린다. load_raw를 다시 돌리면 이 스크립트도 다시 돌린다.

- 02_재무: 행마다 '분석 값' 세 칸. '정정됨(배제)' 행은 메모의 '항목 X→원문 Y'의 Y
- 02_배당표(확인완료·확인불가 행): D·보통주 DPS 분석 값 / 04_배당금지급(확인완료 행): 분석 값
  → core.core_review_value. verified 뷰가 이 값을 가장 먼저 쓴다
- 원문 대조 파일(--source-check, 여러 개): 검토값이 사업보고서 원문과 달랐던 칸의 원문 값. 검토값보다 우선.
  item이 d_dart_won·dps_common_won·cf_paid_won이면 배당, 아니면 재무 칸
- 02_배당표_전체항목 → raw.dart_dividend_item / 04-1_배당계정별 → raw.cf_dividend_account
  04-2_재무API → raw.dart_financial / 05_배당결정공시 → raw.dividend_decision (첨부정정은 빼고 원공시를 넣음)
- 증자감자·분할병합: 검산결과 '정정된 공시임'(같은 묶음의 정정본이 따로 있음) 행을 원천 표에서 뺀다
"""
import argparse
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from core import db
from scripts.export_review_workbook import API_ACCOUNTS, DIV_ITEMS, stock_kind

REVIEW_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "review"
DEFAULT_CHECKS = [REVIEW_DIR / "재무_원문대조_20261029.csv", REVIEW_DIR / "원문대조_20261102.csv"]
DEFAULT_CHECK = DEFAULT_CHECKS[0]
DIVIDEND_ITEMS = ("d_dart_won", "dps_common_won", "cf_paid_won")
FIN_ITEMS = [("지배주주 순이익", "ni_owner_won"), ("부채총계", "liabilities_won"), ("자본총계", "equity_won")]
FS = {"연결": "CFS", "별도": "OFS"}
# 숫자 칸에 숫자 아닌 글자가 들어간 칸: 같은 행 메모에 적힌 원문 값으로 넣는다
TYPOS = {("02_배당표", "00299002", 2018, "보통주 DPS 분석 값(원)"): 2000}  # 메모: "보통주 DPS를 2,000원으로 수정"


def blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "-")


def num(v, where: str = ""):
    if blank(v):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        raise ValueError(f"{where}: 숫자가 아님 {v!r}") from None


def text(v) -> str | None:
    return None if blank(v) else str(v).strip()


def day(v) -> str | None:
    if blank(v):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()[:10]


def sheet(path: Path, name: str, **dtype) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=name, dtype={"corp_code": str, **dtype})
    df = df[df["corp_code"].notna()].copy()
    df["corp_code"] = df["corp_code"].str.strip().str.zfill(8)
    return df


def review(target, corp, year, item, value, status, who, memo, source) -> dict:
    return {"target": target, "corp_code": corp, "bsns_year": int(year), "item": item, "value_won": value,
            "status": status, "reviewer": text(who), "memo": text(memo), "source": source}


# --- core.core_review_value ---------------------------------------------------------------


def financial_rows(path: Path) -> list[dict]:
    out = []
    for i, r in sheet(path, "02_재무").iterrows():
        state = text(r["검토 상태"])
        if state not in ("확인완료", "정정됨(배제)"):
            continue
        fixed = {}
        if state == "정정됨(배제)":  # 메모: "[원문 확인·DB 수정 필요] 부채총계 빈칸→원문 49,013,227,245 / ..."
            fixed = {lab: float(v.replace(",", "")) for lab, v in
                     re.findall(r"(지배주주 순이익|부채총계|자본총계) \S+→원문 (-?[\d,]+)", str(r["메모"]))}
        for label, item in FIN_ITEMS:
            v = fixed[label] if label in fixed else num(r[f"{label} 분석 값(원)"], f"02_재무 {i + 2}행 {label}")
            out.append(review("financial", r["corp_code"], r["사업연도"], item, v, state, r["검토자"], r["메모"], path.name))
    return out


def dividend_rows(path: Path) -> list[dict]:
    out = []
    for i, r in sheet(path, "02_배당표").iterrows():
        state = text(r["검토 상태"])  # 확인불가 행도 넣는다: 한 칸(예: DPS)만 확인 못 하고 D는 원문으로 채운 행이 있음
        if state not in ("확인완료", "확인불가"):
            continue
        for col, item in (("D 분석 값(원)", "d_dart_won"), ("보통주 DPS 분석 값(원)", "dps_common_won")):
            key = ("02_배당표", r["corp_code"], int(r["사업연도"]), col)
            v = TYPOS[key] if key in TYPOS else num(r[col], f"02_배당표 {i + 2}행 {col}")
            out.append(review("dividend", r["corp_code"], r["사업연도"], item, v, state, r["검토자"], r["메모"], path.name))
    for i, r in sheet(path, "04_배당금지급").iterrows():
        if text(r["검토 상태"]) == "확인완료":
            out.append(review("dividend", r["corp_code"], r["사업연도"], "cf_paid_won", num(r["분석 값(원)"], f"04 {i + 2}행"),
                              "확인완료", r["검토자"], r["메모"], path.name))
    return out


def source_check_rows(path: Path) -> list[dict]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [review("dividend" if r["item"] in DIVIDEND_ITEMS else "financial", r["corp_code"], r["bsns_year"], r["item"],
                   num(r["value_won"]), "원문 대조", None,
                   f"{r['note']} (접수번호 {r['rcept_no']} {r['column']} 열)" if r["rcept_no"] else r["note"], path.name)
            for _, r in df.iterrows()]


def merge(rows: list[dict]) -> list[dict]:
    """같은 칸이 여러 번 나오면 뒤의 것(원문 대조)이 이긴다."""
    return list({(r["target"], r["corp_code"], r["bsns_year"], r["item"]): r for r in rows}.values())


# --- 원천 표 고치기 ---------------------------------------------------------------------------


def fix_dividend_items(conn, path: Path) -> int:
    """02_배당표_전체항목: 검토값과 다른 칸만 고친다 (같은 보고서·연도·항목·주식 종류의 첫 값 = 검산표에 보인 값)."""
    have = {}
    for r in db.fetch_dicts(conn, "SELECT ctid::text AS id, * FROM raw.dart_dividend_item ORDER BY ctid"):
        have.setdefault((r["corp_code"], r["bsns_year"], r["rcept_no"], r["item"], stock_kind(r["stock_kind"])), []).append(r)
    n = 0
    for i, r in sheet(path, "02_배당표_전체항목", **{"보고서 접수번호": str}).iterrows():
        for item, kind, col, _ in DIV_ITEMS:
            v = num(r[col], f"전체항목 {i + 2}행 {col}")
            if v is None:
                continue
            rows = have.get((r["corp_code"], int(r["사업연도"]), r["보고서 접수번호"], item, kind), [])
            if any(not blank(x["value"]) and abs(num(x["value"]) - v) < 1e-6 for x in rows):
                continue  # 같은 종류 줄 중 하나라도 검토값이면 그대로 (UPDATE하면 ctid 순서가 바뀌므로 '첫 줄'만 보지 않음)
            shown = next((x for x in rows if not blank(x["value"])), rows[0] if rows else None)
            if shown is None:
                conn.execute("""INSERT INTO raw.dart_dividend_item (corp_code, corp_name, bsns_year, item, stock_kind, value,
                                is_dash, col_02, rcept_no, source_file) VALUES (%s, %s, %s, %s, %s, %s, '아니오', '(안 씀)', %s, %s)""",
                             (r["corp_code"], r["회사명"], int(r["사업연도"]), item, {"보통": "보통주", "우선": "우선주"}.get(kind, "-"),
                              f"{v:.15g}", r["보고서 접수번호"], path.name))
                n += 1
            else:  # 위에서 같은 값이 없음을 확인함
                conn.execute("UPDATE raw.dart_dividend_item SET value = %s WHERE ctid = %s::tid", (f"{v:.15g}", shown["id"]))
                n += 1
    return n


def fix_cf_accounts(conn, path: Path) -> int:
    """04-1_배당계정별: 판정·계정명·부호 정정. 계정 줄은 (회사, 연도, 연결/별도, 표준계정코드, 금액 크기)로 찾는다."""
    have = {}
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.cf_dividend_account"):
        k = (r["corp_code"], r["bsns_year"], r["fs_div"], r["account_id"],
             abs(float(r["thstrm_amount"] or 0)), abs(float(r["frmtrm_amount"] or 0)))
        have.setdefault(k, []).append(r)
    n, missing = 0, []
    for i, r in sheet(path, "04-1_배당계정별").iterrows():
        cur, prev = num(r["당기 금액(원)"]) or 0.0, num(r["전기 금액(원)"]) or 0.0
        k = (r["corp_code"], int(r["사업연도"]), FS[r["재무제표"]], text(r["표준계정코드"]), abs(cur), abs(prev))
        if not have.get(k):
            missing.append(f"{i + 2}행 {r['회사명']} {r['사업연도']} {r['계정명']}")
            continue
        x = have[k].pop(0)
        new = (text(r["판정"]), text(r["계정명"]), cur, prev)
        if new != (x["judgement"], x["account_nm"], float(x["thstrm_amount"] or 0), float(x["frmtrm_amount"] or 0)):
            conn.execute("""UPDATE raw.cf_dividend_account SET judgement = %s, account_nm = %s, thstrm_amount = %s, frmtrm_amount = %s
                            WHERE corp_code = %s AND bsns_year = %s AND fs_div = %s AND ord = %s""",
                         (*new, x["corp_code"], x["bsns_year"], x["fs_div"], x["ord"]))
            n += 1
    if missing:
        raise ValueError("04-1 행을 DB에서 못 찾음: " + "; ".join(missing[:5]))
    return n


def fix_api_accounts(conn, path: Path) -> int:
    """04-2_재무API: 검산표에 보인 계정 값(같은 계정 여러 줄이면 첫 줄)을 검토값으로. DB에 없던 계정은 줄을 더한다."""
    first = {}
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.dart_financial ORDER BY ord"):
        first.setdefault((r["corp_code"], r["bsns_year"], r["fs_div"], r["sj_div"], r["account_id"]), r)
    last_ord = {(r["corp_code"], r["bsns_year"], r["fs_div"], r["sj_div"]): r["m"] for r in db.fetch_dicts(
        conn, "SELECT corp_code, bsns_year, fs_div, sj_div, max(ord) AS m FROM raw.dart_financial GROUP BY 1, 2, 3, 4")}
    n = 0
    for i, r in sheet(path, "04-2_재무API", **{"접수번호": str}).iterrows():
        fs = FS[r["재무제표"]]
        for sj, aid, col, _ in API_ACCOUNTS:
            v = num(r[col], f"04-2 {i + 2}행 {col}")
            if v is None:
                continue
            x = first.get((r["corp_code"], int(r["사업연도"]), fs, sj, aid))
            if x is None:
                k = (r["corp_code"], int(r["사업연도"]), fs, sj)
                last_ord[k] = last_ord.get(k, 0) + 1
                conn.execute("""INSERT INTO raw.dart_financial (corp_code, corp_name, bsns_year, fs_div, sj_div, account_nm, account_id,
                                thstrm_amount, ord, currency, rcept_no, source_file) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'KRW', %s, %s)""",
                             (r["corp_code"], text(r.iloc[0]), int(r["사업연도"]), fs, sj, col.removesuffix("(원)"), aid, v,
                              last_ord[k], text(r["접수번호"]), path.name))
                n += 1
            elif x["thstrm_amount"] is None or float(x["thstrm_amount"]) != v:
                conn.execute("UPDATE raw.dart_financial SET thstrm_amount = %s WHERE corp_code = %s AND bsns_year = %s AND fs_div = %s "
                             "AND sj_div = %s AND ord = %s", (v, x["corp_code"], x["bsns_year"], fs, sj, x["ord"]))
                n += 1
    return n


DECISION_COLS = [("배당구분", "div_kind", text), ("배당종류", "div_type", text), ("귀속 사업연도", "attributed_year", num),
                 ("보통주 주당배당금(원)", "dps_common_won", num), ("우선주 주당배당금(원)", "dps_pref_won", num),
                 ("시가배당률 보통(%)", "yield_common_pct", num), ("배당금총액(원)", "total_won", num),
                 ("배당기준일", "record_date", day), ("배당금지급 예정일", "pay_date", day)]


def fix_decisions(conn, path: Path) -> tuple[int, int, int]:
    """05_배당결정공시: 확인완료 행의 칸을 검토값으로. 첨부정정(정정됨(배제))은 빼고, DB에 없던 원공시 행은 그 첨부정정 행을 본떠 넣는다."""
    df = sheet(path, "05_배당결정공시", **{"접수번호": str})
    have = {r["rcept_no"]: r for r in db.fetch_dicts(conn, "SELECT * FROM raw.dividend_decision")}
    dropped = df[df["검토 상태"] == "정정됨(배제)"]
    attach = {r["corp_code"]: have[r["접수번호"]] for _, r in dropped.iterrows() if r["접수번호"] in have}
    updated = added = 0
    for _, r in df[df["검토 상태"] == "확인완료"].iterrows():
        vals = {col: f(r[name]) for name, col, f in DECISION_COLS}
        if vals["attributed_year"] is not None:
            vals["attributed_year"] = int(vals["attributed_year"])
        if r["접수번호"] not in have:
            base = attach.get(r["corp_code"])
            if base is None:
                raise ValueError(f"05 {r['회사명']} {r['접수번호']}: DB에 없고 짝이 되는 첨부정정 행도 없음")
            row = {**base, **vals, "rcept_no": r["접수번호"], "disclosed_on": day(r["공시일"]), "is_correction": False,
                   "report_nm": re.sub(r"^\[첨부정정\]", "", base["report_nm"] or ""), "source_file": path.name,
                   "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['접수번호']}"}
            cols = list(row)
            conn.execute(f"INSERT INTO raw.dividend_decision ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                         [row[c] for c in cols])
            added += 1
            continue
        old = have[r["접수번호"]]
        changed = {c: v for c, v in vals.items() if not same(old[c], v)}
        if changed:
            conn.execute(f"UPDATE raw.dividend_decision SET {', '.join(f'{c} = %s' for c in changed)} WHERE rcept_no = %s",
                         [*changed.values(), r["접수번호"]])
            updated += 1
    removed = sum(conn.execute("DELETE FROM raw.dividend_decision WHERE rcept_no = %s", (rc,)).rowcount for rc in dropped["접수번호"])
    return updated, added, removed


def same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return str(a)[:10] == str(b)[:10]


def drop_superseded(conn, path: Path) -> int:
    """증자감자·분할병합 검산표에서 '정정된 공시임'으로 표시한 앞선 판을 원천 표에서 뺀다 (정정본이 같은 표에 있음)."""
    n = 0
    for name, table in (("증자감자_최종본", "raw.dart_capital_event"), ("분할병합", "raw.dart_split_merge")):
        df = pd.read_excel(path, sheet_name=name, dtype={"접수번호": str})
        for rc in df.loc[df["검산결과"] == "정정된 공시임", "접수번호"]:
            n += conn.execute(f"DELETE FROM {table} WHERE rcept_no = %s", (rc,)).rowcount
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="검토를 마친 전수 검산표·증자감자 검산표를 DB에 반영")
    ap.add_argument("path", type=Path, help="전수 검산표 검토본 (원픽_전수검산표_*.xlsx)")
    ap.add_argument("--capital", type=Path, help="증자감자·분할병합 검산표 검토본")
    ap.add_argument("--source-check", type=Path, nargs="+", default=DEFAULT_CHECKS, help="검토값을 원문과 다시 대조한 결과 CSV (여러 개)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    rows = merge(financial_rows(a.path) + dividend_rows(a.path) + [r for f in a.source_check for r in source_check_rows(f)])
    with db.connect(a.url) as conn:
        db.apply_schema(conn)
        print(f"  core.core_review_value: {db.replace_rows(conn, 'core.core_review_value', rows):,}행")
        print(f"  raw.dart_dividend_item: {fix_dividend_items(conn, a.path):,}칸 고침")
        print(f"  raw.cf_dividend_account: {fix_cf_accounts(conn, a.path):,}줄 고침")
        print(f"  raw.dart_financial: {fix_api_accounts(conn, a.path):,}칸 고침·추가")
        u, ad, dr = fix_decisions(conn, a.path)
        print(f"  raw.dividend_decision: {u:,}건 고침 · 원공시 {ad}건 추가 · 첨부정정 {dr}건 뺌")
        if a.capital:
            print(f"  증자감자·분할병합 앞선 판: {drop_superseded(conn, a.capital)}건 뺌")
        conn.commit()
