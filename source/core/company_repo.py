"""DB의 실제 회사 638곳을 챗봇 점검(core.checkup)이 쓰는 회사 모양으로 읽는다.

판정용 숫자는 source/scripts/build_judgement.py와 같은 규칙(source/core/b_income.py)으로 만든다:
B(2024)·D(2025)·D(2024)는 KIND 고배당기업 공시, 순이익·부채·자본은 빈칸 채움·원문 수정을 반영한 뷰.
DB에 연결하지 못하면 빈 사전을 돌려주고 화면은 가상 회사만 쓴다.
"""
import csv
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from core import b_income as bi
from core import db
from core.valueup import DividendTarget, PastTarget, implementation
from core.virtual_cases import VirtualCompany

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
LAST_ACTUAL_YEAR = 2025  # 실제 배당을 대조할 수 있는 마지막 사업연도


@dataclass(frozen=True)
class RealCompany(VirtualCompany):
    corp_code: str = ""
    stock_code: str = ""
    declared_2026_won: int = 0  # 이미 결의한 2026 사업연도 중간·분기배당 합계 (결정 공시)
    capacity: dict | None = None  # F-06 재무 여력 (core.core_capacity_2025 한 행)
    policy: tuple = ()  # F-07 원문 확인을 마친 정책 항목 ({item, text, where}, ...)
    filings: tuple | None = None  # 4층 정책 상세: 자사주·투자·인수 공시 (core.v_policy_filing 행, 최근 순). None = 표가 없음
    pref_of: str = ""  # 우선주면 그 회사(보통주) 이름. 요건 판정은 회사 단위라 보통주와 같고, 주당배당금만 우선주 값
    pref_code: str = ""  # 우선주 종목코드

    @property
    def declared_2026(self) -> int:
        return self.declared_2026_won


def _int(v) -> int | None:
    return int(v) if v is not None else None


def load_inputs(conn):
    """판정 입력에 쓰는 표들을 한 번에 읽는다."""
    companies = db.fetch_dicts(conn, "SELECT * FROM core.core_company ORDER BY corp_code")
    kind = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT * FROM raw.kind_list")}
    src_b = {r["corp_code"]: r["src_value"] for r in db.fetch_dicts(
        conn, "SELECT corp_code, src_value FROM core.core_source_verify WHERE target = 'kind_list' AND item = 'b2024_won'")}
    stock = {r["corp_code"]: float(r["v"]) * bi.MIL for r in db.fetch_dicts(conn, """
        SELECT corp_code, max(value)::numeric AS v FROM raw.dart_dividend_item
        WHERE bsns_year = 2025 AND item LIKE '주식배당금총액%%' AND value ~ '^[0-9.]+$' GROUP BY 1""")}
    div = db.fetch_dicts(conn, """SELECT v.corp_code, v.bsns_year, v.d_dart_won, v.d_decision_won, o.d_dart_unit
                                  FROM core.v_dividend_year_verified v JOIN core.core_dividend_year o USING (corp_code, bsns_year)""")
    fin = db.fetch_dicts(conn, "SELECT corp_code, bsns_year, ni_owner_won, liabilities_won, equity_won FROM core.v_financial_year_verified")
    return companies, kind, src_b, stock, div, fin


def _num(s):
    try:
        return float(str(s).replace(",", "")) if s is not None else None
    except ValueError:
        return None


def apply_b(companies, kind, src_b, stock, div) -> dict:
    """div 행(2024·2025)에 판정용 B·D를 넣는다. 반환: {corp_code: BYear}."""
    by = {(r["corp_code"], r["bsns_year"]): r for r in div}
    out = {}
    for c in companies:
        code = c["corp_code"]
        r25, r24 = by.get((code, 2025)), by.get((code, 2024))
        b = bi.b_year(kind.get(code), r25 and r25["d_dart_won"], r24 and r24["d_dart_won"], stock.get(code),
                      _num(src_b.get(code)))
        out[code] = b
        if r24 is not None:
            r24.update(b_won=b.b2024, d_dart_won=b.d2024 if b.d2024 is not None else r24["d_dart_won"])
        if r25 is not None:
            r25.update(b_won=b.b2025, d_dart_won=b.d2025, d_dart_unit=b.d_unit, reduction_unconfirmed=b.reduction_unconfirmed)
    return out


def _latest_decisions(conn, column: str) -> dict[tuple, dict]:
    """2025·2026 현금배당 결정 공시. 같은 기준일·배당구분·감액 여부의 공시가 여럿이면 정정 공시로 보고 가장 늦은 것만 남긴다.
    키: (corp_code, 귀속 연도, 배당구분, 기준일, 감액 여부)."""
    latest = {}
    for r in db.fetch_dicts(conn, f"""SELECT corp_code, attributed_year, div_kind, report_nm, record_date, {column} AS dps, rcept_no
                                     FROM raw.dividend_decision WHERE parse_status = '정상' AND div_type LIKE '현금%%'
                                     AND attributed_year IN (2025, 2026) ORDER BY rcept_no"""):
        key = (r["corp_code"], r["attributed_year"], r["div_kind"], r["record_date"], "감액" in (r["report_nm"] or ""))
        latest[key] = r
    return latest


def dps_from_decisions(conn, column: str) -> dict[str, dict]:
    """배당 결정 공시의 주당배당금 → {corp_code: {final: 2025 결산, interim: 2026 중간·분기 합, final_rcept, missing}}.

    column: dps_common_won(보통주) / dps_pref_won(우선주). 감액배당 결정은 비과세라 뺀다.
    같은 기준일·배당구분·감액 여부의 공시가 여럿이면 정정 공시로 보고 가장 늦은 것만 쓴다.
    missing: 결산배당 공시는 있는데 이 칸이 비어 있었는지(우선주 금액을 공시에서 읽지 못한 경우).
    """
    dps = {}
    for (code, year, kind_, _, reduction), r in _latest_decisions(conn, column).items():
        d = dps.setdefault(code, {"final": 0, "interim": 0, "final_rcept": "", "missing": False})
        if reduction:  # 감액배당 결정은 비과세라 배당소득(세액 계산)에 넣지 않는다
            continue
        if year == 2025 and kind_ == "결산배당":
            d["final"] += Decimal(r["dps"] or 0)  # 원 미만도 그대로 (예: 8,751.5원)
            d["final_rcept"] = d["final_rcept"] or r["rcept_no"]
            d["missing"] = d["missing"] or r["dps"] is None
        elif year == 2026:
            d["interim"] += Decimal(r["dps"] or 0)
    return dps


PREF_NOTE = ("우선주로 받은 현금 배당도 특례배당소득으로 계산했어요 [현재 해석 기준]: 조세특례제한법 제104조의27 ①은 "
             "'고배당기업의 주식'에서 받은 배당소득, 시행령 제104조의24 ①은 그중 '금전으로 받은 금액'이라고만 해 주식 종류를 나누지 않아요.")


PREF_BY_CLASS = Path(__file__).resolve().parents[2] / "data" / "processed" / "review" / "우선주_종목별_배당금_2025.csv"


def pref_by_class(path: Path = PREF_BY_CLASS) -> dict[str, Decimal]:
    """우선주가 2종목 이상인 회사의 종목별 2025 주당배당금 {우선주 코드: 원}. 사업보고서 원문(배당 표·주석)에서 확인한 값."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["pref_code"]: Decimal(r["dps_won"]) for r in csv.DictReader(f) if r["bsns_year"] == "2025"}


CLASS_SOURCE = "우선주 종목별 금액: 배당 결정 공시의 '종류주식에 대한 배당 관련 사항' 표 (raw.dividend_decision_class)"


def _class_no(row: dict) -> int | None:
    """종류주식 표 한 행의 우선주 번호. '2우선주'·'제3우선주' → 2·3, 번호 없는 '우선주' → 1."""
    text = f"{row['class_name']} {row['class_kind']}"
    m = re.search(r"(\d)\s*우선주", text)
    return int(m.group(1)) if m else (1 if "우선주" in text else None)


def _pref_no(pref_name: str) -> int:
    """상장 우선주 이름의 번호. '두산2우B'·'아모레퍼시픽홀딩스3우C' → 2·3, '삼성전자우'·'대덕1우' → 1."""
    m = re.search(r"(\d)우[A-Z]?(\(전환\))?$", pref_name)
    return int(m.group(1)) if m else 1


def match_class(pref_name: str, rows: list[dict]) -> dict | None:
    """공시의 종류주식 표에서 이 상장 우선주의 행. 표에 한 행뿐이면 그 행, 아니면 종목 이름이 적힌 행,
    그것도 없으면 우선주 번호가 같은 행(상환우선주 제외). 하나로 가를 수 없으면 None."""
    if len(rows) == 1:
        return rows[0]
    key = pref_name.replace(" ", "")
    hit = [r for r in rows if key in f"{r['class_name']}{r['class_kind']}".replace(" ", "")]
    if len(hit) == 1:
        return hit[0]
    no = _pref_no(pref_name)
    hit = [r for r in rows if "상환" not in f"{r['class_name']}{r['class_kind']}" and _class_no(r) == no]
    return hit[0] if len(hit) == 1 else None


def pref_dps_by_class(conn, listed: dict[str, list[dict]]) -> dict[str, dict]:
    """상장 우선주 종목별 주당배당금 {우선주 코드: {final, interim, final_rcept, unresolved}} (raw.dividend_decision_class).

    dps_from_decisions와 같은 공시(가장 늦은 정정본, 감액배당 제외)를 쓰고, 공시마다 종류주식 표에서 그 종목의 행을 찾는다.
    unresolved: 표가 없거나 그 종목의 행을 가르지 못한 공시 번호. 하나라도 있으면 이 값으로 계산하지 않는다.
    """
    if not _has_table(conn, "raw.dividend_decision_class"):
        return {}
    rows: dict[str, list[dict]] = {}
    for r in db.fetch_dicts(conn, "SELECT rcept_no, class_name, class_kind, dps_won FROM raw.dividend_decision_class ORDER BY rcept_no, class_name, class_kind"):
        rows.setdefault(r["rcept_no"], []).append(r)
    out = {}
    for (code, year, kind_, _, reduction), r in _latest_decisions(conn, "dps_pref_won").items():
        if reduction or code not in listed or not (year == 2026 or kind_ == "결산배당"):
            continue
        for p in listed[code]:
            d = out.setdefault(p["pref_code"], {"final": Decimal(0), "interim": Decimal(0), "final_rcept": "", "unresolved": []})
            hit = match_class(p["pref_name"], rows.get(r["rcept_no"], []))
            if hit is None:
                d["unresolved"].append(r["rcept_no"])
            elif year == 2025:
                d["final"] += Decimal(hit["dps_won"])
                d["final_rcept"] = d["final_rcept"] or r["rcept_no"]
            else:
                d["interim"] += Decimal(hit["dps_won"])
    return out


def pref_companies(conn, base: dict[str, "RealCompany"]) -> tuple[dict[str, "RealCompany"], dict[str, str]]:
    """상장 우선주(raw.krx_pref_stock) → ({우선주 이름: 회사}, {계산하지 못한 우선주 이름: 이유}).

    요건 판정 숫자는 보통주 회사와 같고 주당배당금만 우선주 값으로 바꾼다.
    먼저 배당 결정 공시의 종목별 표(pref_dps_by_class)를 쓴다. 그 표를 쓸 수 없으면, 우선주가 1종목인 회사는 공시의 우선주 칸,
    2종목 이상인 회사는 사업보고서에서 종목별 금액을 확인한 값(pref_by_class)을 쓰고,
    그 값이 없거나 2026 중간·분기배당이 어느 종목 것인지 가를 수 없는 종목은 계산하지 않는다.
    """
    if not _has_table(conn, "raw.krx_pref_stock"):
        return {}, {}
    by_code = {c.corp_code: c for c in base.values()}
    listed: dict[str, list[dict]] = {}
    for r in db.fetch_dicts(conn, "SELECT corp_code, pref_code, pref_name FROM raw.krx_pref_stock WHERE status = '상장 중' ORDER BY pref_code"):
        listed.setdefault(r["corp_code"], []).append(r)
    dps = dps_from_decisions(conn, "dps_pref_won")
    by_class = pref_by_class()
    from_notice = pref_dps_by_class(conn, listed)
    book, skipped = {}, {}
    for code, prefs in listed.items():
        c = by_code.get(code)
        if c is None:
            continue
        d = dps.get(code)
        for p in prefs:
            k = from_notice.get(p["pref_code"])
            if k is not None and not k["unresolved"]:
                book[p["pref_name"]] = replace(c, name=p["pref_name"], pref_of=c.name, pref_code=p["pref_code"],
                                               dps_2025_final=k["final"], dps_2026_interim=k["interim"],
                                               sources=[*c.sources, PREF_NOTE, CLASS_SOURCE])
                continue
            if len(prefs) > 1:
                final = by_class.get(p["pref_code"])
                # 공시의 우선주 칸과 금액이 같은 종목이 공시가 가리키는 종목. 2026 중간·분기배당은 그 종목에만 붙인다
                same_as_notice = d is not None and final is not None and final == d["final"]
                if final is None:
                    skipped[p["pref_name"]] = f"{c.name} 우선주가 {len(prefs)}종목인데 이 종목의 주당배당금을 사업보고서에서 확인하지 못했어요"
                elif d is not None and d["interim"] and not same_as_notice:
                    skipped[p["pref_name"]] = f"{c.name}의 2026 중간·분기배당이 우선주 종목별로 얼마인지 공시에서 가를 수 없어요"
                else:
                    book[p["pref_name"]] = replace(c, name=p["pref_name"], pref_of=c.name, pref_code=p["pref_code"],
                                                   dps_2025_final=final, dps_2026_interim=d["interim"] if same_as_notice else 0,
                                                   sources=[*c.sources, PREF_NOTE, f"우선주 종목별 금액: 사업보고서 원문 ({PREF_BY_CLASS.name})"])
                continue
            if c.dps_2025_final and (d is None or d["missing"]):
                skipped[p["pref_name"]] = "배당 결정 공시에서 우선주 주당배당금을 읽지 못했어요"
            else:
                d = d or {"final": 0, "interim": 0}
                book[p["pref_name"]] = replace(c, name=p["pref_name"], pref_of=c.name, pref_code=p["pref_code"],
                                               dps_2025_final=d["final"], dps_2026_interim=d["interim"],
                                               sources=[*c.sources, PREF_NOTE])
    return book, skipped


def pref_index(prefs: dict[str, "RealCompany"]) -> dict[str, str]:
    """우선주 이름·종목코드 → 우선주 이름 (name_index와 같은 규칙)."""
    out = {}
    for name, c in prefs.items():
        for k in (name, name.replace(" ", ""), name.upper(), c.pref_code):
            out[k] = name
    return out


def load_prefs(base: dict, url: str | None = None) -> tuple[dict, dict]:
    try:
        with db.connect(url or db.database_url()) as conn:
            return pref_companies(conn, base)
    except Exception:  # noqa: BLE001 DB가 없으면 우선주는 계산하지 않는다
        return {}, {}


def real_companies(conn) -> dict[str, RealCompany]:
    companies, kind, src_b, stock, div, fin = load_inputs(conn)
    bs = apply_b(companies, kind, src_b, stock, div)
    f = {(r["corp_code"], r["bsns_year"]): r for r in fin}
    dv = {(r["corp_code"], r["bsns_year"]): r for r in div}
    dps = dps_from_decisions(conn, "dps_common_won")
    reports = {r["corp_code"]: r["rcept_no"] for r in db.fetch_dicts(conn, """
        SELECT DISTINCT ON (corp_code) corp_code, src_rcept_no AS rcept_no FROM core.core_dart_verify
        WHERE bsns_year = 2025 AND target = 'core_financial_year' AND src_rcept_no <> '' ORDER BY corp_code""")}
    cap = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_capacity_2025")} if _has_table(
        conn, "core.core_capacity_2025") else {}
    policy, targets, past = {}, {}, {}
    if _has_table(conn, "core.core_policy_item"):
        for r in db.fetch_dicts(conn, "SELECT * FROM core.core_policy_item ORDER BY corp_code, rcept_no DESC, seq"):
            where = f'<a href="{DART}{r["rcept_no"]}" target="_blank">{r["rcept_no"]}</a> · {r["section"]}'
            policy.setdefault(r["corp_code"], []).append({"item": r["category"], "text": r["text"], "where": where})
            if r["use_as_target"] and r["target_kind"] and r["corp_code"] not in targets:
                targets[r["corp_code"]] = r
            if r.get("target_year") and r["target_year"] <= LAST_ACTUAL_YEAR and r["target_kind"] and r["target_value"]:
                past.setdefault(r["corp_code"], []).append(PastTarget(
                    r["target_year"], r["target_kind"], r["target_value"], r["basis_note"] or "", r["rcept_no"]))
    dps_year = _dps_by_year(conn) if past else {}
    filings = {}
    if _has_table(conn, "core.v_policy_filing"):
        for r in db.fetch_dicts(conn, """SELECT * FROM core.v_policy_filing WHERE rcept_dt >= '2024-01-01'
                                        ORDER BY corp_code, rcept_dt DESC, rcept_no DESC"""):
            filings.setdefault(r["corp_code"], []).append(r)
    demo = {r["corp_code"] for r in db.fetch_dicts(conn, "SELECT corp_code FROM core.core_demo_company")} if _has_table(
        conn, "core.core_demo_company") else set()
    out = {}
    for c in companies:
        code, b, k = c["corp_code"], bs[c["corp_code"]], kind.get(c["corp_code"], {})
        f25 = f.get((code, 2025), {})
        d = dps.get(code, {"final": 0, "interim": 0, "final_rcept": ""})
        links = []
        if k.get("final_rcept_no"):
            links.append(f'<a href="{DART}{k["final_rcept_no"]}" target="_blank">KIND 고배당 공시 {k["final_rcept_no"]}</a>')
        if reports.get(code):
            links.append(f'<a href="{DART}{reports[code]}" target="_blank">2025 사업보고서 {reports[code]}</a>')
        if d["final_rcept"]:
            links.append(f'<a href="{DART}{d["final_rcept"]}" target="_blank">2025 결산배당 결정 {d["final_rcept"]}</a>')
        links.append("조세특례제한법 제104조의27")
        out[c["corp_name"]] = RealCompany(
            name=c["corp_name"], kind_2025=k.get("is_high_dividend") == "해당",
            b2024=_int(b.b2024), b2025=_int(b.b2025), d2024=_int(b.d2024) or 0, d2025=_int(b.d2025) or 0,
            ni_history={y: _int(f.get((code, y), {}).get("ni_owner_won")) for y in (2023, 2024, 2025)},
            liabilities_2025=_int(f25.get("liabilities_won")), equity_2025=_int(f25.get("equity_won")),
            issued_shares=0, treasury_shares=0, dps_2025_final=d["final"], dps_2026_interim=d["interim"],
            reduction_unconfirmed=b.reduction_unconfirmed, sources=links,
            corp_code=code, stock_code=c["stock_code"] or "",
            declared_2026_won=_int((dv.get((code, 2026)) or {}).get("d_decision_won")) or 0,
            capacity=cap.get(code), policy=tuple(policy.get(code, ())),
            filings=tuple(filings.get(code, ())) if code in demo or code in filings else None,
            target=_target(targets.get(code), f.get((code, 2025), {}).get("ni_owner_won")),
            implementation=_implementation(past.get(code, []), dv, f, dps_year, code),
        )
    return out


def _target(r: dict | None, ni2025) -> DividendTarget | None:
    """검토자가 F-03 목표로 고른 문장 → 2026 사업연도 배당 목표. 배당성향은 2025 지배주주 순이익을 분모로 둔다."""
    if r is None:
        return None
    note = r["basis_note"] or ""
    return DividendTarget(
        kind=r["target_kind"], value=r["target_value"],
        denominator=_int(ni2025) if r["target_kind"] == "배당성향" else None,
        denominator_is_tax_basis=not note,
        source=f'기업가치 제고 계획 {r["rcept_no"]} · {r["section"]} (검토 {r["reviewer"]})')


def _dps_by_year(conn) -> dict:
    """사업보고서 '배당에 관한 사항'의 보통주 주당 현금배당금 {(corp_code, 사업연도): 원}."""
    return {(r["corp_code"], r["bsns_year"]): _num(r["value"]) for r in db.fetch_dicts(conn, """
        SELECT corp_code, bsns_year, value FROM raw.dart_dividend_item
        WHERE item = '주당 현금배당금(원)' AND stock_kind IN ('보통주', '보통주식') AND value ~ '^[0-9.,]+$'""")}


def _implementation(targets: list, dv: dict, fin: dict, dps: dict, code: str) -> str | None:
    """검토자가 '목표 대상 연도'를 적은 과거 목표를 그해 실제 배당과 대조. 최근 연도 먼저, 출처 접수번호를 붙인다."""
    out = []
    for t in sorted(targets, key=lambda t: (-t.year, t.source)):
        d = (dv.get((code, t.year)) or {}).get("d_dart_won")
        ni = (fin.get((code, t.year)) or {}).get("ni_owner_won")
        text = implementation(t, d, ni, dps.get((code, t.year)))
        if text:
            out.append(f"{text} (계획 {t.source})")
    return " / ".join(dict.fromkeys(out)) or None


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (name,)).fetchone()[0]


def name_index(companies: dict) -> dict[str, str]:
    """입력에 쓰일 이름 → 표준 회사명. 회사명, 띄어쓰기·대소문자 무시, 종목코드."""
    out = {}
    for name, c in companies.items():
        out[name] = name
        out[name.replace(" ", "")] = name
        out[name.upper()] = name
        if getattr(c, "stock_code", ""):
            out[c.stock_code] = name
    return out


def load(url: str | None = None) -> dict[str, RealCompany]:
    try:
        with db.connect(url or db.database_url()) as conn:
            return real_companies(conn)
    except Exception:  # noqa: BLE001 DB가 없으면 가상 회사만으로 화면을 띄운다
        return {}


def judgement_counts(url: str | None = None) -> dict[str, int] | None:
    """2026 판정 상태별 회사 수 (core.core_judgement_2026). DB가 없으면 None."""
    try:
        with db.connect(url or db.database_url()) as conn:
            rows = conn.execute("SELECT status, count(*) FROM core.core_judgement_2026 GROUP BY status").fetchall()
    except Exception:  # noqa: BLE001 DB가 없으면 첫 화면은 숫자 대신 안내만
        return None
    return {status: n for status, n in rows} or None


def dividend_history(corp_code: str, url: str | None = None) -> list[dict]:
    """회사 한 곳의 사업연도별 현금배당총액(DART)과 보통주 주당배당금. DB가 없으면 빈 목록."""
    try:
        with db.connect(url or db.database_url()) as conn:
            return db.fetch_dicts(conn, """
                SELECT bsns_year, d_dart_won, dps_common_won FROM core.core_dividend_year
                WHERE corp_code = %s AND d_dart_won IS NOT NULL ORDER BY bsns_year""", (corp_code,))
    except Exception:  # noqa: BLE001 DB가 없으면 이력 없이 화면을 띄운다
        return []


def data_built_at(url: str | None = None) -> str | None:
    """2026 판정을 계산한 날(core.core_judgement_2026). 화면 아래 데이터 기준일로 쓴다."""
    try:
        with db.connect(url or db.database_url()) as conn:
            row = conn.execute("SELECT max(built_at) FROM core.core_judgement_2026").fetchone()
    except Exception:  # noqa: BLE001
        return None
    return row[0].strftime("%Y-%m-%d") if row and row[0] else None
