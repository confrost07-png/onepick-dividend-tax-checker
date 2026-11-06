"""DB의 재무제표 값을 그 연도 자기 사업보고서(DART 원문)와 한 칸씩 대조한다. 원본 표는 고치지 않는다.

대상: core.core_financial_year(지배주주 순이익·부채·자본), raw.cf_dividend_paid(배당금 지급),
      raw.dart_financial(04-2 부채총계·자본총계).
원문: 그 사업연도의 사업보고서 중 가장 최근 판(정정 포함)의 연결/별도 재무제표 당기 열.
불일치이면 ① 다른 기준(연결↔별도) ② 정정 전 원공시 ③ 다음 해 보고서의 비교기간 열과도 맞춰 보고 어느 쪽과 같은지 적는다.
"""
import re

from core import dart_doc as dd

ENGINE = "source/core/dart_verify.py"
MATCH, ROUNDING, MISMATCH, UNREADABLE, NO_REPORT = "일치", "일치(단위 반올림)", "불일치", "원문 못 읽음", "원문 없음"
FOREIGN = "원문 외화 표시"


def grain(v: float) -> int:
    v = abs(v)
    return 1_000_000 if v % 1_000_000 == 0 else 1_000 if v % 1_000 == 0 else 1


def compare(db_value: float, src: float | None) -> str:
    if src is None:
        return UNREADABLE
    if db_value == src:
        return MATCH
    return ROUNDING if abs(db_value - src) <= max(grain(db_value), grain(src)) else MISMATCH


class Reader:
    """사업보고서 한 판의 연결·별도 재무제표에서 값을 읽는다 (같은 판은 한 번만 읽음)."""

    def __init__(self):
        self._cache = {}

    def statements(self, rcp: str, consolidated: bool):
        key = (rcp, consolidated)
        if key not in self._cache:
            title, nodes = dd.filing(rcp)
            lines = dd.chapter_lines(nodes, "연결재무제표" if consolidated else "재무제표")
            sts = {k: dd.statements(lines, k) for k in ("BS", "IS", "CF")}
            picked = {k: dd.pick(v, consolidated) for k, v in sts.items()}
            picked["foreign"] = {k: next((s for s in v if s.consolidated == consolidated and s.currency != "KRW"), None)
                                 for k, v in sts.items()}
            self._cache[key] = (title, picked)
        return self._cache[key]

    def foreign_value(self, rcp: str, consolidated: bool, item: str, year: int) -> tuple[float | None, str]:
        """같은 보고서의 외화(USD 등) 기준 표 값 (외화 그대로, 환산 안 함)."""
        _, st = self.statements(rcp, consolidated)
        f = st["foreign"]
        if item in ("liabilities_won", "equity_won") and f["BS"] and year in f["BS"].years:
            return f["BS"].value(dd.L_LIAB if item == "liabilities_won" else dd.L_EQUITY, year), f["BS"].currency
        if item == "ni_owner_won" and f["IS"]:
            return dd.owner_net_income(f["IS"], year)[0], f["IS"].currency
        if item == "dividends_paid_won" and f["CF"] and year in f["CF"].years:
            k = f["CF"].years.index(year)
            hits = [abs(v[k]) * f["CF"].unit for n, v in f["CF"].rows if re.search(dd.L_DIV_PAID, n) and len(v) > k]
            return (hits[0] if len(hits) == 1 else None), f["CF"].currency
        return None, ""

    def value(self, rcp: str, consolidated: bool, item: str, year: int) -> tuple[float | None, str]:
        _, st = self.statements(rcp, consolidated)
        bs, is_, cf = st["BS"], st["IS"], st["CF"]
        for s_ in (bs, is_, cf):  # pick()이 원화 표를 먼저 고르므로 여기 걸리면 외화 표뿐
            if s_ is not None and s_.currency != "KRW":
                return None, f"외화 표시({s_.currency}) 재무제표만 있음"
        if item == "ni_total_won":
            return (dd.net_income_total(is_, year), "당기순이익 전체") if is_ else (None, "손익계산서 못 찾음")
        if item in ("liabilities_won", "equity_won"):
            if bs is None or year not in bs.years:
                return None, "재무상태표에 그 연도 열 없음"
            ok, chk = dd.check_balance(bs, year)
            v = bs.value(dd.L_LIAB if item == "liabilities_won" else dd.L_EQUITY, year)
            return (v, chk) if ok else (None, chk)
        if item == "ni_owner_won":
            if is_ is None:
                return None, "손익계산서 못 찾음"
            return dd.owner_net_income(is_, year)
        if item == "dividends_paid_won":
            if cf is None or year not in cf.years:
                return None, "현금흐름표에 그 연도 열 없음"
            k = cf.years.index(year)
            hits = [(n, v[k] * cf.unit) for n, v in cf.rows
                    if re.search(dd.L_DIV_PAID, n) and not re.search(dd.L_NCI, n) and len(v) > k]
            if len(hits) == 1:
                return abs(hits[0][1]), f"현금흐름표 '{hits[0][0]}'"
            if not hits:
                return 0.0, "현금흐름표에 배당금 지급 줄 없음"
            return None, "배당금 지급 줄 여러 개: " + " · ".join(f"{n} {abs(v):,.0f}" for n, v in hits)
        raise ValueError(item)


def periods_for(year: int, fiscal_month: int) -> list[str]:
    """DB 사업연도 → 볼 사업보고서 기간. 12월 결산은 'Y.12'. 그 밖은 'Y.MM'과 'Y+1.MM' 둘 다 (대응 규칙을 확인하려고)."""
    if fiscal_month == 12:
        return [f"{year}.12"]
    return [f"{year}.{fiscal_month:02d}", f"{year + 1}.{fiscal_month:02d}"]


def verify_cell(reader: Reader, reports: dict, corp: str, corp_name: str, year: int, fiscal_month: int,
                item: str, consolidated: bool, db_value: float, target: str) -> dict:
    """reports: 기간 'YYYY.MM' → [(접수번호, 보고서명)] 최신순. 후보 기간 중 일치하는 판을 먼저, 없으면 처음 읽힌 판을 쓴다."""
    base = {"target": target, "corp_code": corp, "bsns_year": year, "item": item,
            "basis": "연결" if consolidated else "별도", "db_value": db_value, "engine": ENGINE}
    found, tried = [], []
    for period in periods_for(year, fiscal_month):
        if period not in reports:
            tried.append(f"사업보고서 ({period}) 없음")
            continue
        rcp, title = _readable_filing(reader, reports[period], consolidated)
        try:
            src_year = int(period[:4]) if fiscal_month == 12 else _table_year(reader, rcp, consolidated)
            src, chk = reader.value(rcp, consolidated, item, src_year) if src_year else (None, "표 연도 못 읽음")
        except Exception as ex:  # noqa: BLE001 원문 한 건이 이상해도 나머지는 계속
            src_year, src, chk = None, None, f"원문 읽기 오류: {ex}"
        result = FOREIGN if src is None and chk.startswith("외화") else compare(db_value, src)
        row = {**base, "src_value": src, "result": result, "src_rcept_no": rcp, "src_title": title,
               "src_period": period, "check_result": chk,
               "note": f"{fiscal_month}월 결산: 사업보고서 기간 {period}과 대조" if fiscal_month != 12 else ""}
        if result in (MATCH, ROUNDING):
            return row
        if result == MISMATCH:
            why = _explain(reader, reports, period, rcp, consolidated, item, src_year, db_value)
            row["note"] = f"{row['note']} · {why}" if row["note"] else why
        found.append(row)
        tried.append(f"{period}: {chk}")
    readable = [r for r in found if r["result"] == MISMATCH]
    if readable:
        return readable[0]
    if found:
        return found[0]
    return {**base, "src_value": None, "result": NO_REPORT, "src_rcept_no": "", "src_title": "", "src_period": "",
            "check_result": "", "note": " · ".join(tried)}


def _readable_filing(reader: Reader, filings: list, consolidated: bool) -> tuple[str, str]:
    """같은 기간 판 중 재무제표가 읽히는 가장 최근 판 ([첨부정정] 등 재무제표 없는 정정은 건너뜀)."""
    for rcp, title in filings:
        try:
            if reader.statements(rcp, consolidated)[1]["BS"] is not None:
                return rcp, title
        except Exception:  # noqa: BLE001
            continue
    return filings[0]


def _table_year(reader: Reader, rcp: str, consolidated: bool) -> int | None:
    _, st = reader.statements(rcp, consolidated)
    bs = st["BS"]
    return bs.years[0] if bs else None


def _explain(reader, reports, period, rcp, consolidated, item, year, db_value) -> str:
    """불일치일 때 DB 값이 어디와 같은지 (같은 판 다른 기준·순이익 전체·단위 배수, 정정 전 원공시, 1~2년 뒤 보고서 재작성 값)."""
    checks = [("다른 기준(" + ("별도" if consolidated else "연결") + ")", rcp, not consolidated, item)]
    if item == "ni_owner_won":
        checks.append(("당기순이익 전체(비지배 포함)", rcp, consolidated, "ni_total_won"))
    if len(reports[period]) > 1:
        checks.append(("정정 전 원공시", reports[period][-1][0], consolidated, item))
    for ahead in (1, 2):
        nxt = f"{int(period[:4]) + ahead}{period[4:]}"
        if nxt in reports:
            checks.append((f"{ahead}년 뒤 보고서 비교기간(재작성)", reports[nxt][0][0], consolidated, item))
    for label, r, cons, it in checks:
        try:
            v, _ = reader.value(r, cons, it, year)
        except Exception:  # noqa: BLE001
            continue
        if compare(db_value, v) in (MATCH, ROUNDING):
            return f"DB 값은 {label} 값과 같음 ({v:,.0f})"
    try:
        fv, cur = reader.foreign_value(rcp, consolidated, item, year)
        if fv is not None and compare(db_value, fv) in (MATCH, ROUNDING):
            return f"DB 값은 같은 보고서의 {cur} 기준 재무정보 값({fv:,.0f})을 원화로 적은 것 (통화 다름)"
    except Exception:  # noqa: BLE001
        pass
    try:
        src, _ = reader.value(rcp, consolidated, item, year)
    except Exception:  # noqa: BLE001
        src = None
    if src:
        for k, label in ((1_000, "천 배"), (1_000_000, "백만 배")):
            if compare(db_value, src * k) in (MATCH, ROUNDING) or compare(db_value * k, src) in (MATCH, ROUNDING):
                return f"DB 값과 원문 값이 단위 {label} 차이"
    return "DB 값과 같은 원문 값을 찾지 못함"
