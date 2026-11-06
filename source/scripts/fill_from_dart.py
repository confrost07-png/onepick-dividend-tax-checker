"""DB 빈칸을 DART 원문으로 다시 확인해 core.core_dart_fill에 적는다. 원본 표는 고치지 않는다.

실행: .venv/bin/python -m scripts.fill_from_dart [--only 1,2,3,4,5,6] [--url ...]
① 재무(2017~2025 지배주주 순이익·부채·자본) ② [첨부정정]만 있는 배당 결정 공시의 원공시
③ 주당배당금(2017~2025) ④ 현금흐름표 배당금 지급(2023~2025, 재무제표 없음·여러 줄) ⑤ 별도재무제표 보완 자료의 남은 빈칸
⑥ 현금배당총액 D(2017~2025)
볼 사업보고서: 01 배당 자료의 접수번호 + DART 사업보고서 검색 결과(그 해·다음 해·다다음 해). 그 해 사업보고서가
없으면(상장 전 등) 재무 칸은 차례로 ① 감사보고서(연결 → 없으면 별도, 그 해·다음 해 비교기간) ② '감사보고서제출'
공시의 첨부 감사보고서 ③ 분기·반기보고서의 첨부 사업보고서·감사보고서에서 찾고, 앞 단계에서 찾으면 멈춘다. 그래도 못 찾으면
'사업보고서 없음'으로 적는다. 배당 표(D·주당배당금)는 감사보고서에 없어 사업보고서에서만 찾는다.
매번 모든 묶음을 다시 돌린다(결과 표를 비우고 채우므로 --only는 시험용).
원문은 data/raw/dart_cache/에 저장해 다시 돌릴 때는 받지 않는다. 결과 표는 매번 비우고 다시 채운다.
"""
import argparse
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pandas as pd

from core import dart_doc as dd
from core import dart_fill as df
from core import db

YEARS = tuple(range(2017, 2026))  # 재무·배당 표 (원천 자료 2017~)
CF_YEARS = (2023, 2024, 2025)  # 04 현금흐름표 자료는 2023~
OFS_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "03_별도보완"


def log(rows, label):
    n = defaultdict(int)
    for r in rows:
        n[r["status"]] += 1
    print(f"  {label}: {len(rows)}칸 · " + " · ".join(f"{k} {v}" for k, v in sorted(n.items())), flush=True)
    return rows


def report_rcepts(conn) -> dict:
    """(corp_code, 사업연도) → 사업보고서 접수번호 목록 (01 배당 자료)."""
    out = defaultdict(list)
    for r in db.fetch_dicts(conn, "SELECT DISTINCT corp_code, bsns_year, rcept_no FROM raw.dart_dividend_item "
                                  "WHERE rcept_no IS NOT NULL ORDER BY rcept_no"):
        out[(r["corp_code"], r["bsns_year"])].append(r["rcept_no"])
    return out


@lru_cache(maxsize=None)
def annual(corp) -> dict[int, list[str]]:
    """DART 사업보고서 검색 → {기간 연도: [접수번호(최신 정정 먼저)]}."""
    out = defaultdict(list)
    for rcp, _, period in dd.annual_reports(corp):
        out[int(period[:4])].append(rcp)
    return out


def candidates(rcepts, corp, year, ahead=2):
    """그 연도 보고서 먼저, 없으면 다음 해·다다음 해 보고서(비교기간 열). 01 자료 + DART 검색."""
    found = annual(corp)
    seen = []
    for y in range(year, year + ahead + 1):
        for r in found.get(y, []) + rcepts.get((corp, y), []):
            if r not in seen:
                seen.append(r)
    return seen


def safe(fn, corp, year, items):
    """원문을 끝내 못 받으면 멈추지 않고 그 칸을 '확인 필요'로 적는다."""
    try:
        return fn()
    except RuntimeError as e:
        return [df.row(corp, year, item, note=f"원문 받기 실패: {e}") for item in items]


@lru_cache(maxsize=None)
def audits(corp) -> dict[tuple[int, bool], list[str]]:
    """DART 감사보고서 검색 → {(기간 연도, 연결 여부): [접수번호]}."""
    out = defaultdict(list)
    for rcp, _, period, consolidated in dd.audit_reports(corp):
        out[(int(period[:4]), consolidated)].append(rcp)
    return out


def from_audit(rows, corp, name, year, consolidated):
    """사업보고서에서 못 찾은 재무 칸을 감사보고서(그 해·다음 해 비교기간)에서 읽는다.
    연결이 필요한데 그 해 연결감사보고서가 없으면(자회사가 없던 해) 별도 감사보고서 값을 쓰고 메모에 남긴다."""
    need = [r["item"] for r in rows if r["status"] == df.NEEDS_REVIEW and not r["source_rcept_no"]]
    if not need or year in annual(corp):
        return rows
    try:
        found = audits(corp)
    except RuntimeError:  # 검색이 안 되면 첨부파일 단계로 넘어감
        found = {}
    note = ""
    cons = consolidated
    rcepts = found.get((year, cons), []) + found.get((year + 1, cons), [])
    if cons and not found.get((year, True)):
        cons, note = False, "그 해 연결감사보고서 없음(자회사 없던 해) → 별도 감사보고서 값"
        rcepts = found.get((year, False), []) + found.get((year + 1, False), [])
    got = safe(lambda: df.financial(corp, name, year, need, cons, rcepts), corp, year, need) if rcepts else []
    how = "사업보고서 없는 해 → 감사보고서"
    for find, label in ((dd.audit_attachments, "감사보고서제출 첨부"), (dd.report_attachments, "분기·반기보고서 첨부")):
        if any(g["status"] == df.FILLED for g in got):  # 앞 단계에서 찾았으면 멈춤
            break
        try:  # 장에서 원문이 안 뜨는 회사: 첨부파일로만 열리는 문서 (그 해 공시 → 다음 해 공시 비교기간)
            att = find(corp, year) + find(corp, year + 1)
        except RuntimeError:
            att = []
        want = [a for a in att if a[3] == consolidated] or ([a for a in att if not a[3]] if consolidated else [])
        if not want:
            continue
        cons = want[0][3]
        alt = safe(lambda: df.financial_attached(corp, year, need, cons, [a[:3] for a in want]) or [], corp, year, need)
        if alt and any(g["status"] == df.FILLED for g in alt):
            got, how = alt, f"사업보고서 없는 해 → {label} 문서"
            note = "그 해 연결 재무제표 없음(자회사 없던 해) → 별도 값" if consolidated and not cons else ""
    if not got:
        return rows
    got = {g["item"]: {**g, "note": " · ".join(x for x in (g["note"], how, note) if x)} for g in got}
    return [got.get(r["item"], r) if r["item"] in need else r for r in rows]


def no_report(rows):
    """원문을 못 찾은 칸 중 그 해 사업보고서 자체가 없는 칸은 '사업보고서 없음'으로 바꾼다."""
    for r in rows:
        if r["status"] == df.NEEDS_REVIEW and not r["source_rcept_no"] and r["bsns_year"] not in annual(r["corp_code"]):
            r["status"] = df.NO_REPORT
            r["note"] = (f"DART 사업보고서 검색에 {r['bsns_year']}년 보고서 없음(상장 전 등), "
                         f"뒤 보고서 비교기간에서도 못 찾음 · {r['note']}")
    return rows


def task1(conn, rcepts):
    rows = []
    for r in db.fetch_dicts(conn, f"""
        SELECT f.corp_code, c.corp_name, c.fiscal_month, f.bsns_year,
               coalesce(f.fs_basis, (SELECT g.fs_basis FROM core.core_financial_year g WHERE g.corp_code = f.corp_code
                                     AND g.fs_basis IS NOT NULL ORDER BY abs(g.bsns_year - f.bsns_year) LIMIT 1)) AS basis,
               f.ni_owner_won IS NULL AS ni, f.liabilities_won IS NULL AS li, f.equity_won IS NULL AS eq
        FROM core.core_financial_year f JOIN core.core_company c USING (corp_code)
        WHERE f.bsns_year IN {YEARS} AND (f.ni_owner_won IS NULL OR f.liabilities_won IS NULL OR f.equity_won IS NULL)
        ORDER BY 2, 4"""):
        need = [k for k, flag in (("ni_owner_won", r["ni"]), ("liabilities_won", r["li"]), ("equity_won", r["eq"])) if flag]
        if r["fiscal_month"] != 12:
            rows += [df.row(r["corp_code"], r["bsns_year"], k, note=f"{r['fiscal_month']}월 결산: 사업연도와 표 연도 대응 확인 필요")
                     for k in need]
            continue
        got = safe(lambda: df.financial(r["corp_code"], r["corp_name"], r["bsns_year"], need, r["basis"] != "별도",
                                        candidates(rcepts, r["corp_code"], r["bsns_year"])), r["corp_code"], r["bsns_year"], need)
        rows += from_audit(got, r["corp_code"], r["corp_name"], r["bsns_year"], r["basis"] != "별도")
    return log(no_report(rows), "① 재무")


def task2(conn):
    rows = []
    for r in db.fetch_dicts(conn, "SELECT corp_code, corp_name, rcept_no, disclosed_on FROM raw.dividend_decision "
                                  "WHERE parse_status = '원문 못 받음' ORDER BY corp_name"):
        rows += df.decision(r["corp_code"], r["corp_name"], r["rcept_no"], str(r["disclosed_on"]))
    return log(rows, "② 배당 결정 원공시")


def task3(conn, rcepts):
    rows = []
    for r in db.fetch_dicts(conn, f"""
            SELECT d.corp_code, c.corp_name, d.bsns_year FROM core.core_dividend_year d JOIN core.core_company c USING (corp_code)
            WHERE d.bsns_year IN {YEARS} AND d.dps_common_won IS NULL ORDER BY 2, 3"""):
        rows += safe(lambda: [df.common_dps(r["corp_code"], r["corp_name"], r["bsns_year"],
                                            candidates(rcepts, r["corp_code"], r["bsns_year"]))],
                     r["corp_code"], r["bsns_year"], ["dps_common_won"])
    return log(no_report(rows), "③ 주당배당금")


def task4(conn, rcepts):
    rows = []
    for r in db.fetch_dicts(conn, f"""
        SELECT d.corp_code, c.corp_name, d.bsns_year, p.fs_div, f.fs_basis,
               (SELECT q.d_dart_won FROM core.core_dividend_year q WHERE q.corp_code = d.corp_code AND q.bsns_year = d.bsns_year - 1) AS prev_d
        FROM core.core_dividend_year d JOIN core.core_company c USING (corp_code)
        LEFT JOIN raw.cf_dividend_paid p ON p.corp_code = d.corp_code AND p.bsns_year = d.bsns_year
        LEFT JOIN core.core_financial_year f ON f.corp_code = d.corp_code AND f.bsns_year = d.bsns_year
        WHERE d.bsns_year IN {CF_YEARS} AND d.cf_paid_won IS NULL
          AND d.cf_status IN ('재무제표 없음', '여러 줄 합산(중복인지 확인)') ORDER BY 2, 3"""):
        cons = r["fs_div"] == "CFS" if r["fs_div"] else r["fs_basis"] != "별도"
        rows += safe(lambda: [df.dividends_paid(r["corp_code"], r["corp_name"], r["bsns_year"], cons,
                                                candidates(rcepts, r["corp_code"], r["bsns_year"]), r["prev_d"])],
                     r["corp_code"], r["bsns_year"], ["cf_paid_won"])
    return log(rows, "④ 현금흐름표 배당금 지급")


def task5(conn, rcepts):
    """별도재무제표 보완 자료(data/raw/03_별도보완)의 남은 빈칸."""
    b = pd.read_csv(OFS_DIR / "별도_보완결과.csv", dtype=str, encoding="utf-8-sig")
    nd = pd.read_csv(OFS_DIR / "남은결측_목록.csv", dtype=str, encoding="utf-8-sig")
    b["v"] = pd.to_numeric(b["확정값"], errors="coerce")
    val = {(r.corp_code, int(r.사업연도), r.항목): r.v for r in b.itertuples()}
    decided = {(r["corp_code"], r["attributed_year"]) for r in db.fetch_dicts(
        conn, "SELECT DISTINCT corp_code, attributed_year FROM raw.dividend_decision "
              "WHERE div_type IN ('현금배당', '현금ㆍ현물배당') AND attributed_year IS NOT NULL")}
    rows = []
    for r in nd.itertuples():
        corp, year, item, memo = r.corp_code, int(r.사업연도), r.항목, str(r._10)
        key = f"ofs.{item}"
        cands = candidates(rcepts, corp, year)
        if item in ("현금배당금총액", "주당현금배당금") and r.구분 == "데이터 없음":
            if (corp, year) in decided:
                rows.append(df.row(corp, year, key, note="배당 표는 '-'인데 그 연도 현금배당 결정 공시가 있음"))
            else:
                rows.append(df.row(corp, year, key, 0.0, df.NO_DIVIDEND,
                                   check="배당 표 '-' + 그 연도 현금배당 결정 공시 없음(05 자료)"))
        elif item == "주당현금배당금":
            rows.append(df.common_dps(corp, r.회사명, year, cands, item=key))
        elif item == "당기순이익":
            got = df.financial(corp, r.회사명, year, ["ni_owner_won"], False, cands)[0]
            got["item"] = key
            rows.append(got)
        elif item == "배당금지급_지급기준":
            rows.append(df.dividends_paid(corp, r.회사명, year, False, cands, item=key))
        elif item == "현금배당성향":
            total, ni = val.get((corp, year, "현금배당금총액")), val.get((corp, year, "당기순이익"))
            if ni is not None and ni <= 0:
                rows.append(df.row(corp, year, key, status=df.NOT_APPLICABLE, check=f"별도 당기순이익 {ni:,.0f} ≤ 0"))
            elif pd.notna(total) and pd.notna(ni) and ni > 0:
                rows.append(df.row(corp, year, key, round(total / ni * 100, 2), df.FILLED,
                                   check=f"현금배당금총액 {total:,.0f} ÷ 당기순이익 {ni:,.0f} × 100 (코드 계산)"))
            else:
                rows.append(df.row(corp, year, key, note="배당금총액 또는 당기순이익이 비어 계산 못 함"))
        elif item == "주당순이익":
            rows.append(df.row(corp, year, key, status=df.POLICY, note=memo))
        else:
            rows.append(df.row(corp, year, key, note=memo))
    return log(rows, "⑤ 별도 자료 남은 빈칸")


def task6(conn, rcepts):
    rows = []
    for r in db.fetch_dicts(conn, f"""
            SELECT d.corp_code, c.corp_name, d.bsns_year FROM core.core_dividend_year d JOIN core.core_company c USING (corp_code)
            WHERE d.bsns_year IN {YEARS} AND d.d_dart_won IS NULL ORDER BY 2, 3"""):
        rows += safe(lambda: [df.dividend_total(r["corp_code"], r["corp_name"], r["bsns_year"],
                                                candidates(rcepts, r["corp_code"], r["bsns_year"]))],
                     r["corp_code"], r["bsns_year"], ["d_dart_won"])
    return log(no_report(rows), "⑥ 현금배당총액 D")


def main(url: str, only: set[int]):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        conn.commit()
        rcepts = report_rcepts(conn)
        rows = []
        for n, fn in ((1, lambda: task1(conn, rcepts)), (2, lambda: task2(conn)), (3, lambda: task3(conn, rcepts)),
                      (4, lambda: task4(conn, rcepts)), (5, lambda: task5(conn, rcepts)), (6, lambda: task6(conn, rcepts))):
            if n in only:
                rows += fn()
        seen = {}
        for r in rows:  # 같은 칸이 두 번 나오면 뒤의 것 (예: 같은 원공시를 여러 정정이 가리킴)
            seen[(r["corp_code"], r["bsns_year"], r["item"], r["ref"])] = r
        n = db.replace_rows(conn, "core.core_dart_fill", list(seen.values()))
    print(f"  core.core_dart_fill: {n:,}행")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DB 빈칸을 DART 원문으로 다시 확인")
    ap.add_argument("--only", default="1,2,3,4,5,6", help="할 묶음 번호 (쉼표)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, {int(x) for x in a.only.split(",")})
