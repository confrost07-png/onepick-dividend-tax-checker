"""F-08 데이터 분석 화면 P1: 소급 분석·최소액 분포·기준선 몰림. 회사 이름·순위 없이 집계만 돌려준다.

[팀 해석 · PRD v0.2 5.3]
- 소급 분석: 2018~2025 각 사업연도 숫자에 같은 요건 엔진(core.judgement)을 적용한다. 그해 감액배당 정보가 없어
  B = D로 두고, 제2호 기준선은 '직전 ≥ 전전'(2024 기준선 대신)으로 본다. 충족한 회사가 다음 해에도 충족인지 센다.
- 최소액 분포: 2027 최소 필요 배당액(2025년 기본 시나리오) ÷ 2025 배당.
- 기준선 몰림: 2025 배당성향(25%·40%)과 이익배당금액 증가율(10%) 주변에 회사가 몰리는지.
  순이익 0 이하 회사는 배당성향을 25%(부채 > 자본총액×2면 0%)로 간주받으므로(조특령 제104조의24⑤)
  배당성향 그림에서 빼고 수만 세며, 증가율 그림에서는 흑자 회사와 나눠 센다.
금액은 DART 현금배당총액(백만 원 단위)과 빈칸 채움·원문 수정을 반영한 순이익(core.v_*_verified).
"""
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from core import db
from core.judgement import HOLD, MET, JudgeInput, judge

YEARS = range(2018, 2026)
GROUP_PROFIT = "흑자"
GROUP_DEFICIT = "적자 (배당성향 간주)"
RATIO_BINS = [(0, 100, "100% 이하 (2025만큼이면 충분)"), (100, 110, "100~110%"), (110, 125, "110~125%"),
              (125, 150, "125~150%"), (150, float("inf"), "150% 초과")]


@dataclass(frozen=True)
class P1Results:
    retro: pd.DataFrame        # 사업연도, 충족, 다음 해 확인, 다음 해 탈락, 탈락률(%)
    drop_reasons: pd.DataFrame  # 사유, 건수
    min_ratio: pd.DataFrame    # 구간, 회사 수
    payout: pd.DataFrame       # 배당성향(%) 구간 하한, 회사 수
    growth: pd.DataFrame       # 증가율(%) 구간 하한, 회사 수
    notes: dict
    growth_by_group: pd.DataFrame | None = None  # 증가율 구간·회사 수를 흑자 / 적자(배당성향 간주)로 나눈 것


def retro_status(d: dict, ni: dict, bs: dict, year: int):
    """year 사업연도 숫자로 다음 배당 요건 판정 (B = D, 제2호 기준선 = 전년 D)."""
    dp, dpp = d.get(year), d.get(year - 1)
    liab, eq = bs.get(year, (None, None))
    return judge(JudgeInput(b_prev=dp, b_2024=dpp, d_prev=dp, d_prevprev=dpp, ni_prev=ni.get(year),
                            liabilities=liab, equity=eq))


def retro(companies: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """companies: {corp: (D {연도: 원}, NI {연도: 원}, BS {연도: (부채, 자본)})}."""
    rows, reasons = [], Counter()
    for y in YEARS:
        met = known = drop = 0
        for d, ni, bs in companies.values():
            if retro_status(d, ni, bs, y).status != MET:
                continue
            met += 1
            if y + 1 > max(YEARS):
                continue
            nxt = retro_status(d, ni, bs, y + 1)
            if nxt.status == HOLD:
                continue
            known += 1
            if nxt.status != MET:
                drop += 1
                reasons[nxt.reasons[0].split(":")[0] if nxt.reasons else "기타"] += 1
        rows.append({"사업연도": y, "충족": met, "다음 해 판정 가능": known, "다음 해 탈락": drop,
                     "탈락률(%)": round(drop * 100 / known, 1) if known else None})
    return pd.DataFrame(rows), pd.DataFrame(reasons.most_common(), columns=["탈락 사유", "건수"])


def histogram(values: list[float], lo: float, hi: float, step: float) -> pd.DataFrame:
    n = int((hi - lo) / step)
    counts = Counter(int((v - lo) // step) for v in values if lo <= v < hi)
    return pd.DataFrame({"구간": [round(lo + i * step, 1) for i in range(n)], "회사 수": [counts.get(i, 0) for i in range(n)]})


def ratio_bins(ratios: list[float], passes: list[bool] | None = None) -> pd.DataFrame:
    """passes(엔진의 '2025만큼이면 통과')를 주면 첫 구간은 그 값으로 센다. 비율은 소수 첫째 자리로 반올림돼 있어
    100.0%여도 실제로는 몇 원 모자랄 수 있으므로, 통과 못 한 회사는 100% 초과 쪽으로 보낸다."""
    if passes is not None:
        ratios = [r if ok else max(r, 100.0001) for r, ok in zip(ratios, passes)]
    return pd.DataFrame([{"구간": label, "회사 수": sum(1 for r in ratios if a < r <= b or (a == 0 and r == 0))}
                         for a, b, label in RATIO_BINS])


def threshold_distributions(companies: dict) -> tuple[list[float], pd.DataFrame, dict]:
    """2025 배당성향(흑자만)과 증가율(흑자·적자 나눔) 분포. companies 모양은 retro와 같다."""
    payouts, growths, deficit_n = [], {GROUP_PROFIT: [], GROUP_DEFICIT: []}, 0
    for d, ni, _ in companies.values():
        n = ni.get(2025)
        deficit = n is not None and n <= 0
        if d.get(2025) and n is not None:
            if deficit:
                deficit_n += 1
            else:
                payouts.append(d[2025] * 100 / n)
        if d.get(2025) and d.get(2024) and n is not None:  # 순이익을 모르면 흑자·적자를 나눌 수 없어 뺀다
            growths[GROUP_DEFICIT if deficit else GROUP_PROFIT].append((d[2025] - d[2024]) * 100 / d[2024])
    growth = pd.concat([histogram(v, -10, 30, 1).assign(구분=g) for g, v in growths.items()], ignore_index=True)
    notes = {"payout_n": len(payouts), "deficit_n": deficit_n, "growth_n": sum(len(v) for v in growths.values()),
             "growth_deficit_n": len(growths[GROUP_DEFICIT])}
    return payouts, growth, notes



DIV_SQL = "SELECT corp_code, bsns_year, d_dart_won FROM core.v_dividend_year_verified"
FIN_SQL = """SELECT corp_code, bsns_year, ni_owner_won, liabilities_won, equity_won FROM core.v_financial_year_verified"""


def companies(div: list[dict], fin: list[dict]) -> dict:
    """DB 행 → {corp: (D {연도: 원}, NI {연도: 원}, BS {연도: (부채, 자본)})}."""
    comp = {}
    for r in div:
        comp.setdefault(r["corp_code"], ({}, {}, {}))[0][r["bsns_year"]] = int(r["d_dart_won"]) if r["d_dart_won"] is not None else None
    for r in fin:
        c = comp.setdefault(r["corp_code"], ({}, {}, {}))
        c[1][r["bsns_year"]] = int(r["ni_owner_won"]) if r["ni_owner_won"] is not None else None
        c[2][r["bsns_year"]] = tuple(int(v) if v is not None else None for v in (r["liabilities_won"], r["equity_won"]))
    return comp


def rates(comp: dict) -> dict[str, tuple[float | None, float | None]]:
    """회사별 (2025 배당성향 %, 2025 이익배당금액 증가율 %). 성향은 흑자일 때만, 증가율은 2024·2025 모두 배당일 때만."""
    out = {}
    for corp, (d, ni, _) in comp.items():
        payout = d[2025] * 100 / ni[2025] if d.get(2025) and ni.get(2025) and ni[2025] > 0 else None
        growth = (d[2025] - d[2024]) * 100 / d[2024] if d.get(2025) and d.get(2024) else None
        out[corp] = (payout, growth)
    return out


def load(url: str | None = None) -> P1Results | None:
    try:
        with db.connect(url) as conn:
            div = db.fetch_dicts(conn, DIV_SQL)
            fin = db.fetch_dicts(conn, FIN_SQL)
            # 최소액 엔진과 같은 순이익(검토본·원문 정정 반영 core.v_financial_year_verified)으로 맞춰야 빠지는 회사가 없다
            mins = db.fetch_dicts(conn, """SELECT m.ratio_to_2025_pct, m.pass_if_same_as_2025, m.status
                                           FROM core.core_min_dividend_2027 m
                                           JOIN core.v_financial_year_verified f ON f.corp_code = m.corp_code AND f.bsns_year = 2025
                                           WHERE m.scenario = '2025년 (기본)' OR m.ni2026_won = f.ni_owner_won""")
    except Exception:  # noqa: BLE001 DB가 없으면 화면은 안내만
        return None
    comp = companies(div, fin)
    retro_df, reasons = retro(comp)
    rated = [r for r in mins if r["ratio_to_2025_pct"] is not None]
    ratios = [float(r["ratio_to_2025_pct"]) for r in rated]
    passes = [bool(r["pass_if_same_as_2025"]) for r in rated]
    payouts, growth, notes = threshold_distributions(comp)
    notes |= {"min_n": len(ratios), "min_other": Counter(r["status"] for r in mins if r["ratio_to_2025_pct"] is None)}
    total = growth.groupby("구간", as_index=False, sort=True)["회사 수"].sum()
    return P1Results(retro_df, reasons, ratio_bins(ratios, passes), histogram(payouts, 10, 60, 1), total, notes, growth)
