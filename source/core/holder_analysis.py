"""추가 분석 '최대주주 지분 비교': 2025 기준선 근처 회사와 나머지의 최대주주+특수관계인 보통주 지분율 분포. 회사·개인 이름 없이 집계만.

[팀 해석 · 기획안 추가 분석]
- 기준선 근처 = 2025 배당성향(core.p1_analysis.rates)이 25%·40%에서 ±NEAR_PP%p 안, 또는 이익배당금액 증가율이 10%에서 ±NEAR_PP%p 안.
- 나머지 = 배당성향·증가율 가운데 하나 이상 계산되고, 어느 기준선 근처에도 들지 않는 회사.
- 지분율은 core.core_major_holder(2025 사업보고서). 사분위는 pandas 기본(선형 보간).
- 사례 MIN_CASES건 미만인 묶음은 숫자를 보이지 않는다. 지분과 기준선 몰림의 관계는 상관관계로만 읽고 원인으로 해석하지 않는다.
"""
from dataclasses import dataclass

import pandas as pd

from core import db, p1_analysis
from core.major_holder import CORP, PERSON, UNKNOWN

YEAR = 2025
NEAR_PP = 3.0
MIN_CASES = 10
THRESHOLDS = (("배당성향 25% 근처", 0, 25.0), ("배당성향 40% 근처", 0, 40.0), ("증가율 10% 근처", 1, 10.0))
NEAR_ANY, REST = "기준선 근처 (하나 이상)", "나머지 (기준선에서 먼 회사)"


@dataclass(frozen=True)
class HolderResults:
    table: pd.DataFrame  # 묶음, 회사 수, 지분 자료, 중앙값, 1사분위, 3사분위, 개인 최대주주(%), 표시
    notes: dict


def groups(rates: dict[str, tuple[float | None, float | None]]) -> dict[str, set[str]]:
    """회사 → 기준선 묶음. 한 회사가 여러 기준선 근처에 함께 들 수 있다."""
    out = {name: set() for name, _, _ in THRESHOLDS} | {NEAR_ANY: set(), REST: set()}
    for corp, vals in rates.items():
        if all(v is None for v in vals):
            continue
        near = [name for name, i, t in THRESHOLDS if vals[i] is not None and abs(vals[i] - t) <= NEAR_PP]
        for name in near:
            out[name].add(corp)
        out[NEAR_ANY if near else REST].add(corp)
    return out


def compare(rates: dict, holders: dict[str, tuple[float | None, str | None]]) -> pd.DataFrame:
    """holders: {corp: (보통주 지분율 %, 최대주주 종류)}."""
    rows = []
    for name, corps in groups(rates).items():
        pct = pd.Series([holders[c][0] for c in corps if c in holders and holders[c][0] is not None], dtype=float)
        kinds = [holders[c][1] for c in corps if c in holders and holders[c][0] is not None]
        shown = len(pct) >= MIN_CASES
        rows.append({"묶음": name, "회사 수": len(corps), "지분 자료": len(pct),
                     "중앙값": round(pct.median(), 1) if shown else None,
                     "1사분위": round(pct.quantile(0.25), 1) if shown else None,
                     "3사분위": round(pct.quantile(0.75), 1) if shown else None,
                     "개인 최대주주(%)": round(kinds.count(PERSON) * 100 / len(kinds), 1) if shown else None,
                     "표시": shown})
    return pd.DataFrame(rows)


def load(url: str | None = None) -> HolderResults | None:
    try:
        with db.connect(url) as conn:
            comp = p1_analysis.companies(db.fetch_dicts(conn, p1_analysis.DIV_SQL), db.fetch_dicts(conn, p1_analysis.FIN_SQL))
            hold = db.fetch_dicts(conn, """SELECT corp_code, pct_common, largest_kind FROM core.core_major_holder
                                           WHERE bsns_year = %s AND reprt_code = '11011'""", (YEAR,))
    except Exception:  # noqa: BLE001 DB·표가 없으면 화면은 안내만
        return None
    if not hold:
        return None
    holders = {r["corp_code"]: (float(r["pct_common"]) if r["pct_common"] is not None else None, r["largest_kind"])
               for r in hold}
    with_pct = [v for v in holders.values() if v[0] is not None]
    table = compare(p1_analysis.rates(comp), holders)
    compared = int(table.loc[table["묶음"].isin([NEAR_ANY, REST]), "회사 수"].sum())
    notes = {"n_holder": len(hold), "n_pct": len(with_pct), "n_compared": compared,
             "kinds": {k: sum(1 for v in with_pct if v[1] == k) for k in (PERSON, CORP, UNKNOWN)}}
    return HolderResults(table, notes)
