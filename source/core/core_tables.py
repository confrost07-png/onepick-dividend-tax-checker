"""raw·02·07 → core 테이블 행, 그리고 판정·최소액 결과 행. DB 없이 시험할 수 있게 순수 함수로 둔다.

[팀 해석]
- D(이익배당금액) 기본값은 DART 현금배당총액(02, 백만 원). 배당 결정 공시 합계(05, 원 단위 원값)와
  현금흐름표 지급액(04)은 나란히 두고 자동으로 대체하지 않는다.
- B(배당소득)는 원천 적재 때는 '미산출'로 비워 두고, source/scripts/build_judgement.py가 source/core/b_income.py 규칙
  (PRD v0.2: 현금배당 − 비과세 감액배당 + 주식배당, B2024는 KIND 공시)으로 2024·2025를 채운 뒤 판정·최소액을 다시 만든다.
- 배당 결정 공시는 정정공시가 있으면 회사·귀속연도·배당구분·기준일이 같은 것 중 가장 늦은 공시만 쓴다.
  금전 배당이 아닌 현물배당은 D 합계에서 뺀다(조특법 시행령 제104조의24 제3항).
- 2024 부채총계는 02(다음 해 보고서의 재작성 값)를 쓴다. 최초 보고 값과 19곳이 다르며 팀 결정 전이다.
"""
from collections import defaultdict
from decimal import Decimal

import pandas as pd

from core.judgement import judge_2026
from core.min_dividend import COMPUTED, scenarios
from core.raw_tables import FILES, code6, code8, integer, num, text

MIL = 1_000_000
CASH_TYPES = {"현금배당"}
B_STATUS = "미산출"
ENGINE_JUDGE = "core.judgement.judge_2026"
ENGINE_MIN = "core.min_dividend.scenarios"


def _mil_to_won(v) -> Decimal | None:
    n = num(v)
    return n * MIL if n is not None else None


def company_rows(df02: pd.DataFrame, df07: pd.DataFrame, kind_rows: list[dict]) -> list[dict]:
    pref = {code8(r["DART고유번호"]): r for r in df07.to_dict("records")}
    listed_by_code = {r["corp_code"]: r["is_high_dividend"] == "해당" for r in kind_rows if r.get("corp_code")}
    listed_by_name = {r["corp_name"]: r["is_high_dividend"] == "해당" for r in kind_rows}
    out = {}
    for r in df02.to_dict("records"):
        code = code8(r["DART고유번호"])
        if code in out:
            continue
        name = text(r["회사명"])
        p = pref.get(code, {})
        month = integer(r["결산월"])
        out[code] = {
            "corp_code": code,
            "corp_name": name,
            "stock_code": code6(r["종목코드"]),
            "market": text(r["시장"]),
            "fiscal_month": month,
            "is_december_fye": month == 12 if month is not None else None,
            "kind_type_2025": text(r["KIND유형_2025"]),
            "kind_listed": listed_by_code.get(code, listed_by_name.get(name)),
            "pref_stock_codes": text(p.get("상장우선주_코드")),
            "pref_status": text(p.get("상태")),
            "source_file": f"{FILES['02']} + {FILES['07']} + {FILES['09']}",
        }
    return list(out.values())


def financial_rows(df02: pd.DataFrame) -> list[dict]:
    return [{
        "corp_code": code8(r["DART고유번호"]),
        "bsns_year": integer(r["사업연도"]),
        "fs_basis": text(r["재무제표_기준"]),
        "ni_owner_won": _mil_to_won(r["지배주주순이익(백만원)"]),
        "liabilities_won": _mil_to_won(r["부채총계(백만원)"]),
        "equity_won": _mil_to_won(r["자본총계(백만원)"]),
        "unit": MIL,
        "source": "02",
    } for r in df02.to_dict("records")]


def latest_cash_decisions(decision_rows: list[dict]) -> list[dict]:
    """정정공시를 정리하고 금전 배당만 남긴다."""
    best: dict[tuple, dict] = {}
    for r in decision_rows:
        if r.get("div_type") not in CASH_TYPES or r.get("total_won") is None:
            continue
        key = (r["corp_code"], r["attributed_year"], r["div_kind"], r["record_date"])
        cur = best.get(key)
        if cur is None or (r["disclosed_on"] or "", r["rcept_no"]) > (cur["disclosed_on"] or "", cur["rcept_no"]):
            best[key] = r
    return list(best.values())


def dividend_year_rows(df02: pd.DataFrame, decision_rows: list[dict], cf_rows: list[dict],
                       companies: set[str]) -> list[dict]:
    rows: dict[tuple, dict] = {}

    def row(code, year):
        return rows.setdefault((code, year), {
            "corp_code": code, "bsns_year": year,
            "d_dart_won": None, "d_dart_unit": None,
            "d_decision_won": None, "decision_count": 0,
            "cf_paid_won": None, "cf_paid_unit": None, "cf_status": None,
            "dps_common_won": None, "b_won": None, "b_status": B_STATUS, "source": "",
        })

    def mark(r, src):
        parts = [p for p in r["source"].split("+") if p]
        if src not in parts:
            r["source"] = "+".join(parts + [src])

    for rec in df02.to_dict("records"):
        r = row(code8(rec["DART고유번호"]), integer(rec["사업연도"]))
        r["d_dart_won"] = _mil_to_won(rec["현금배당총액(백만원)"])
        r["d_dart_unit"] = MIL
        r["dps_common_won"] = num(rec["주당배당금_보통주(원)"])
        mark(r, "02")

    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    counts: dict[tuple, int] = defaultdict(int)
    for d in latest_cash_decisions(decision_rows):
        if d["corp_code"] in companies and d["attributed_year"] is not None:
            key = (d["corp_code"], d["attributed_year"])
            sums[key] += d["total_won"]
            counts[key] += 1
    for key, total in sums.items():
        r = row(*key)
        r["d_decision_won"] = total
        r["decision_count"] = counts[key]
        mark(r, "05")

    for c in cf_rows:
        if c["corp_code"] not in companies:
            continue
        r = row(c["corp_code"], c["bsns_year"])
        r["cf_paid_won"] = c["paid_mil"] * MIL if c["paid_mil"] is not None else None
        r["cf_paid_unit"] = MIL
        r["cf_status"] = c["status"]
        mark(r, "04")
    return list(rows.values())


def _index(rows: list[dict]) -> dict[tuple, dict]:
    return {(r["corp_code"], r["bsns_year"]): r for r in rows}


def judgement_rows(companies: list[dict], div_rows: list[dict], fin_rows: list[dict]) -> list[dict]:
    div, fin = _index(div_rows), _index(fin_rows)
    out = []
    for c in companies:
        code = c["corp_code"]
        d25, d24 = div.get((code, 2025), {}), div.get((code, 2024), {})
        f25 = fin.get((code, 2025), {})
        x = dict(
            b2025=d25.get("b_won"), b2024=d24.get("b_won"),
            d2025=d25.get("d_dart_won"), d2024=d24.get("d_dart_won"),
            ni2025=f25.get("ni_owner_won"),
            liabilities=f25.get("liabilities_won"), equity=f25.get("equity_won"),
        )
        j = judge_2026(*(_int(x[k]) for k in ("b2025", "b2024", "d2025", "d2024", "ni2025", "liabilities", "equity")),
                       reduction_unconfirmed=bool(d25.get("reduction_unconfirmed")),
                       d_unit=int(d25.get("d_dart_unit") or MIL), ni_unit=MIL)
        out.append({
            "corp_code": code, "status": j.status, "route": j.route, "deemed_payout_pct": j.deemed_payout, "tag": j.tag,
            "reasons": " / ".join(j.reasons), "needs_recheck": j.needs_recheck,
            "b_prev_won": x["b2025"], "b_2024_won": x["b2024"], "d_prev_won": x["d2025"],
            "d_prevprev_won": x["d2024"], "ni_prev_won": x["ni2025"],
            "liabilities_won": x["liabilities"], "equity_won": x["equity"], "engine": ENGINE_JUDGE,
        })
    return out


def min_dividend_rows(companies: list[dict], div_rows: list[dict], fin_rows: list[dict]) -> list[dict]:
    div, fin = _index(div_rows), _index(fin_rows)
    out = []
    for c in companies:
        code = c["corp_code"]
        f25 = fin.get((code, 2025), {})
        history = {y: _int(fin.get((code, y), {}).get("ni_owner_won")) for y in (2023, 2024, 2025)}
        declared = _int(div.get((code, 2026), {}).get("d_decision_won")) or 0
        rows = scenarios(_int(div.get((code, 2024), {}).get("b_won")), _int(div.get((code, 2025), {}).get("d_dart_won")),
                         history, _int(f25.get("liabilities_won")), _int(f25.get("equity_won")), declared)
        for s in rows:
            r = s.result
            out.append({
                "corp_code": code, "scenario": s.label, "ni2026_won": s.ni2026,
                "status": r.status, "min_won": r.amount if r.status == COMPUTED else None,
                "basis": r.basis or None, "reasons": " / ".join(r.reasons) or None,
                "ratio_to_2025_pct": s.ratio_to_2025_pct, "additional_won": s.additional_needed,
                "pass_if_same_as_2025": s.pass_if_same_as_2025, "engine": ENGINE_MIN,
            })
    return out


def _int(v) -> int | None:
    return int(v) if v is not None else None
