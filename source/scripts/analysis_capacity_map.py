"""배당 여력 지도(B2)를 report/분석/배당_여력_지도_결과.md와 output/charts/배당_여력_지도*.svg로 쓴다.

실행: .venv/bin/python -m scripts.analysis_capacity_map [--url ...]
데이터: core.core_capacity_2025('표시' 회사, 금융업 제외), core.core_min_dividend_2027(2025년 순이익 가정),
raw.dart_financial 현금흐름표 2023~2025(여력 표와 같은 연결·별도 기준).
"""
import argparse
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from core import capacity_map as cm
from core import db
from scripts import analysis_groups as ag

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "분석" / "배당_여력_지도_결과.md"
FIG_DIR = ROOT / "output" / "charts"
OCF = "ifrs-full_CashFlowsFromUsedInOperatingActivities"
CAPEX = ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "ifrs-full_PurchaseOfPropertyPlantAndEquipment")
CAP_SQL = """SELECT corp_code, industry, fs_div, fcf_won, min_won, cover_x, industry_median_cover
             FROM core.core_capacity_2025 WHERE status = '표시' AND cover_x IS NOT NULL"""
MIN_SQL = """SELECT m.corp_code, m.ratio_to_2025_pct FROM core.core_min_dividend_2027 m
             JOIN core.v_financial_year_verified f ON f.corp_code = m.corp_code AND f.bsns_year = 2025  -- 최소액 계산과 같은 확정 값(원문 대조로 고친 순이익 포함)
             WHERE m.status = '산출' AND (m.scenario = '2025년 (기본)' OR m.ni2026_won = f.ni_owner_won)"""
CF_SQL = f"""SELECT corp_code, bsns_year, fs_div, account_id, thstrm_amount FROM raw.dart_financial
             WHERE sj_div = 'CF' AND bsns_year BETWEEN 2023 AND 2025
               AND account_id IN ('{OCF}', '{CAPEX[0]}', '{CAPEX[1]}') ORDER BY ord"""


def cash_flows(rows, fs_div: dict) -> dict:
    """회사별 {연도: 영업현금흐름}, {연도: 유형자산 취득}. 여력 표와 같은 연결·별도, 같은 계정이 여러 줄이면 첫 줄."""
    out = {}
    for r in rows:
        c = r["corp_code"]
        if fs_div.get(c) != r["fs_div"] or r["thstrm_amount"] is None:
            continue
        ocf, capex = out.setdefault(c, ({}, {}))
        target = ocf if r["account_id"] == OCF else capex
        target.setdefault(r["bsns_year"], float(r["thstrm_amount"]))
    return out


def med(xs, digits=2):
    xs = [x for x in xs if x is not None]
    return f"{statistics.median(xs):.{digits}f}" if xs else "-"


def quad_table(rows, key):
    total = len(rows)
    lines = ["| 칸 | 회사 수 | 최소 배당 ÷ 2025 배당 중앙값 | 현금 배수 중앙값 | 더 내야 하는 금액 합계 |", "|---|---|---|---|---|"]
    for q in cm.QUADRANTS:
        g = [r for r in rows if r[key] == q]
        extra = sum(r["additional"] for r in g if r["additional"]) / 1e8
        lines.append(f"| {q} | {len(g)} ({len(g) * 100 / total:.0f}%) | {med([r['need'] for r in g], 0)}% | "
                     f"{med([r['cover1' if key == 'q1' else 'cover3'] for r in g])}배 | {extra:,.0f}억 원 |")
    return "\n".join(lines)


def group_table(rows, gkey, groups):
    lines = ["| 무리 | 회사 수 | " + " | ".join(cm.QUADRANTS) + " |", "|---" * (len(cm.QUADRANTS) + 2) + "|"]
    for g in groups:
        sub = [r for r in rows if r[gkey] == g]
        if sub:
            cells = [f"{sum(1 for r in sub if r['q1'] == q) * 100 / len(sub):.0f}%" for q in cm.QUADRANTS]
            lines.append(f"| {g} | {len(sub)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(url: str | None):
    with db.connect(url) as conn:
        cap = db.fetch_dicts(conn, CAP_SQL)
        mins = {r["corp_code"]: r for r in db.fetch_dicts(conn, MIN_SQL)}
        cf = cash_flows(db.fetch_dicts(conn, CF_SQL), {r["corp_code"]: r["fs_div"] for r in cap})
        comp_rows = {r["corp_code"]: r for r in db.fetch_dicts(conn, ag.SQL["first"])}
        holder = {r["corp_code"]: r["largest_kind"] for r in db.fetch_dicts(conn, ag.SQL["holder"])}
        market = {r["corp_code"]: r["market"] for r in db.fetch_dicts(conn, ag.SQL["company"])}
    rows, no_ratio = [], 0
    for r in cap:
        m = mins.get(r["corp_code"])
        if not m or m["ratio_to_2025_pct"] is None:
            no_ratio += 1
            continue
        mn = float(r["min_won"])
        avg = cm.average_fcf(*cf.get(r["corp_code"], ({}, {})))
        row = {"corp": r["corp_code"], "need": float(m["ratio_to_2025_pct"]), "cover1": float(r["cover_x"]),
               "cover3": avg / mn if avg is not None and mn else None,
               # 2025보다 더 내야 하는 금액 = 최소액 − 2025 배당(= 최소액 ÷ 비율). 2025만큼이면 충분하면 0
               "additional": max(0.0, mn - mn * 100 / float(m["ratio_to_2025_pct"])) if float(m["ratio_to_2025_pct"]) > 0 else 0.0,
               "below_industry": r["industry_median_cover"] is not None and float(r["cover_x"]) < float(r["industry_median_cover"]),
               "timing": ag.EARLY if comp_rows.get(r["corp_code"]) and comp_rows[r["corp_code"]]["first_dt"].year < 2026 else ag.LATE,
               "holder": {"개인": "최대주주 개인", "법인": "최대주주 법인"}.get(holder.get(r["corp_code"])),
               "market": market.get(r["corp_code"])}
        row["q1"] = cm.quadrant(row["need"], row["cover1"])
        row["q3"] = cm.quadrant(row["need"], row["cover3"]) if row["cover3"] is not None else None
        rows.append(row)

    FIG_DIR.mkdir(exist_ok=True)
    (FIG_DIR / "배당_여력_지도_2025.svg").write_text(cm.svg([cm.Point(r["need"], r["cover1"]) for r in rows]), encoding="utf-8")
    r3 = [r for r in rows if r["q3"]]
    (FIG_DIR / "배당_여력_지도_3년평균.svg").write_text(cm.svg([cm.Point(r["need"], r["cover3"]) for r in r3]), encoding="utf-8")

    move = Counter((r["q1"], r["q3"]) for r in r3)
    risk1 = sum(1 for r in r3 if r["q1"] == cm.RISK)
    risk_both = move[(cm.RISK, cm.RISK)]
    risk_rows = [r for r in rows if r["q1"] == cm.RISK]
    below = sum(1 for r in risk_rows if r["below_industry"])
    extra_risk = sum(r["additional"] for r in risk_rows) / 1e8
    move_lines = ["| 2025 한 해 기준 \\ 3년 평균 기준 | " + " | ".join(cm.QUADRANTS) + " |", "|---" * (len(cm.QUADRANTS) + 1) + "|"]
    for a in cm.QUADRANTS:
        move_lines.append(f"| {a} | " + " | ".join(str(move[(a, b)]) for b in cm.QUADRANTS) + " |")

    text = f"""# 배당 여력 지도 — 2027년에 더 내야 하는 배당을 낼 현금이 있나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_capacity_map.py`, `source/core/capacity_map.py` · 설계: `report/설계/데이터_분석_설계.md` B2
- 대상: 배당 여력 표(`core.core_capacity_2025`)에 '표시'된 회사 중 2027 최소 배당액 비율이 있는 **{len(rows)}사**. 금융업(은행·보험·증권 등)은 현금흐름 구조가 달라 뺐다. 비율이 없어 뺀 회사 {no_ratio}사
- 가로: 2027 최소 배당액 ÷ 2025 배당(`core_min_dividend_2027`, 2025년 순이익이 2026년에도 같다고 볼 때). 100%를 넘으면 2025보다 더 내야 한다
- 세로: 잉여현금흐름(영업현금흐름 − 유형자산 취득) ÷ 2027 최소 배당액. 1배보다 작으면 한 해 번 현금으로 모자란다
- 그림의 세로축은 0 근처는 그대로, 큰 값은 줄여 보이는 눈금(대칭 로그)이다. 현금 배수가 −수십 배에서 +수십 배까지 넓게 퍼져 있어서다
- 점이 100%와 110%에 세로로 몰린 것은 판정 규칙 때문이다. 가목(배당성향 40% 이상) 회사는 2025만큼(100%), 나목 회사는 10% 더(110%) 내야 하는 경우가 많다
- 기준선(100%, 1배)은 나눠 보기 위한 선이지 합격점이 아니다

## 한 줄 결과

{len(rows)}사 중 **{len(risk_rows)}사({len(risk_rows) * 100 / len(rows):.0f}%)가 '더 내야 함 · 현금 부족'** 칸에 있다. 이 회사들이 2027년 요건을 지키려면 2025보다 모두 합쳐 {extra_risk:,.0f}억 원을 더 배당해야 한다. 다만 한 해 현금흐름은 출렁인다. 2023~2025 평균을 계산할 수 있는 회사 중 2025 기준 위험 칸 {risk1}사를 다시 보면, **{risk_both}사만 3년 평균으로도 위험 칸**에 남는다.

## 1. 지도 (2025 한 해 잉여현금흐름 기준)

![배당 여력 지도 2025](그림/배당_여력_지도_2025.svg)

{quad_table(rows, "q1")}

- 위험 칸 {len(risk_rows)}사 중 {below}사는 현금 배수가 같은 업종 중앙값보다도 낮다(`industry_median_cover`).
- '더 내야 하는 금액'은 회사마다 (2027 최소 배당액 − 2025 배당)을 0 아래로는 내리지 않고 더한 값이다. 2026년에 이미 결의한 배당은 빼지 않았다.

## 2. 3년 평균으로 다시 보기 (2023~2025 평균 잉여현금흐름)

![배당 여력 지도 3년 평균](그림/배당_여력_지도_3년평균.svg)

{quad_table(r3, "q3")}

3년 평균을 계산할 수 있는 {len(r3)}사(현금흐름이 2년 이상 있는 회사)에서, 2025 한 해 기준 칸과 3년 평균 기준 칸이 어떻게 바뀌는지:

{chr(10).join(move_lines)}

## 3. 무리별로 어느 칸에 많나 (2025 한 해 기준)

{group_table(rows, "timing", (ag.EARLY, ag.LATE))}

{group_table(rows, "holder", ("최대주주 개인", "최대주주 법인"))}

{group_table(rows, "market", ("코스피", "코스닥"))}

## 4. 읽을 때 주의

- 2027 최소 배당액은 2026년 순이익이 2025년과 같다고 본 값이다. 순이익이 늘면 최소액도 늘고, 줄면 준다(`core_min_dividend_2027`의 다른 시나리오).
- 잉여현금흐름이 모자라도 쌓아 둔 현금이나 차입으로 배당할 수 있다. 이 지도는 '버는 돈으로 감당되나'만 본다.
- 2026년에 이미 결의한 배당(분기·중간배당)은 반영하지 않았다.
- B1(`report/분석/유지가능성_분석_결과.md`)의 '③ 더 내야 하고 잉여현금흐름도 부족 72사'는 과거 판정 엔진으로 2025에 충족하고 예측 특징 값이 모두 있는 521사만 센 값이라, 이 지도의 위험 칸({len(risk_rows)}사)보다 적다.
- 회사 이름은 이 문서에 적지 않는다.
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    a = ap.parse_args()
    main(a.url)
