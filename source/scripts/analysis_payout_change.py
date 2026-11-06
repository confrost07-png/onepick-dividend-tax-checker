"""2025 배당성향이 25%를 넘은 이유(배당 증가 vs 순이익 감소)를 report/분석/배당성향_변화_분해_결과.md로 쓴다 (분석 설계 A1).

실행: .venv/bin/python -m scripts.analysis_payout_change [--url ...] [--reps 1000]
데이터: core.v_dividend_year_verified, core.v_financial_year_verified(팀 검토본 반영), raw.policy_filing, core.core_major_holder.
"""
import argparse
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from core import db
from core import p1_analysis as p1
from core import payout_change as pc

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "배당성향_변화_분해_결과.md"
BANDS = ("25~28%", "28~40%", "40% 이상")
SEED = 20261029
FIRST_FILING_SQL = """SELECT corp_code, min(rcept_dt) AS first_dt FROM raw.policy_filing
                      WHERE report_nm NOT LIKE '%%예고%%' GROUP BY corp_code"""
HOLDER_SQL = "SELECT corp_code, largest_kind FROM core.core_major_holder"


def rows(comp: dict, first: dict, holder: dict) -> tuple[list[dict], Counter]:
    out, skipped = [], Counter()
    for corp, (d, ni, _) in comp.items():
        d25, n25 = d.get(2025), ni.get(2025)
        if not d25 or n25 is None or n25 <= 0:
            skipped["2025 적자·무배당·값 없음"] += 1
            continue
        if not pc.at_least(d25, n25):
            skipped["2025 배당성향 25% 미만"] += 1
            continue
        d24, n24 = d.get(2024), ni.get(2024)
        cat = pc.classify(d24, d25, n24, n25)
        share = pc.dividend_share(d24, d25, n24, n25) if cat in pc.CROSSED else None
        out.append({"corp": corp, "band": pc.payout_band(d25, n25), "cat": cat, "share": share,
                    "margin": d25 * 4 / n25,  # 실제 배당 ÷ 25%를 맞추는 데 필요한 최소 배당
                    "d_growth": (d25 / d24 - 1) * 100 if d24 else None,
                    "ni_growth": (n25 / n24 - 1) * 100 if n24 and n24 > 0 else None,
                    "timing": "2025년까지 첫 공시" if first.get(corp) and first[corp].year < 2026 else "2026년 첫 공시",
                    "holder": holder.get(corp, "판단 불가")})
    return out, skipped


def pct(n: int, total: int) -> str:
    return f"{n} ({n * 100 / total:.1f}%)" if total else "0"


def category_table(rs: list[dict], key: str, groups) -> str:
    head = "| 어떻게 25% 이상이 됐나 | " + " | ".join(groups) + " |"
    lines = [head, "|---" * (len(groups) + 1) + "|"]
    totals = {g: sum(1 for r in rs if r[key] == g) for g in groups}
    for cat in pc.ORDER:
        cells = [pct(sum(1 for r in rs if r[key] == g and r["cat"] == cat), totals[g]) for g in groups]
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    lines.append("| **합계** | " + " | ".join(str(totals[g]) for g in groups) + " |")
    return "\n".join(lines)


def med(values, digits: int = 1) -> str:
    v = [x for x in values if x is not None]
    return f"{statistics.median(v):.{digits}f}" if v else "-"


def crossed_summary(rs: list[dict]) -> str:
    lines = ["| 2025 배당성향 | 2024년엔 25% 미만이던 회사 | 배당 증가율 중앙값(%) | 순이익 증가율 중앙값(%) | 배당성향 상승 중 배당 몫 중앙값(%) | 실제 배당 ÷ 25%에 필요한 최소 배당 (중앙값) |",
             "|---|---|---|---|---|---|"]
    for b in BANDS:
        c = [r for r in rs if r["band"] == b and r["cat"] in pc.CROSSED]
        lines.append(f"| {b} | {len(c)} | {med(r['d_growth'] for r in c)} | {med(r['ni_growth'] for r in c)} | "
                     f"{med(r['share'] for r in c)} | {med((r['margin'] for r in c), 2)}배 |")
    return "\n".join(lines)


def diff_interval(rs: list[dict], reps: int) -> tuple[float, float, float, int, int]:
    """2024년엔 25% 미만이던 회사 중 '배당을 늘려서 넘김' 비율: 25~28% − 28% 이상. 회사를 다시 뽑아 오차 범위."""
    a = np.array([r["cat"] == pc.BY_DIVIDEND for r in rs if r["cat"] in pc.CROSSED and r["band"] == "25~28%"], dtype=float)
    b = np.array([r["cat"] == pc.BY_DIVIDEND for r in rs if r["cat"] in pc.CROSSED and r["band"] != "25~28%"], dtype=float)
    rng = np.random.default_rng(SEED)
    draws = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(reps)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return (a.mean() - b.mean()) * 100, lo * 100, hi * 100, len(a), len(b)


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        first = {r["corp_code"]: r["first_dt"] for r in db.fetch_dicts(conn, FIRST_FILING_SQL)}
        holder = {r["corp_code"]: r["largest_kind"] for r in db.fetch_dicts(conn, HOLDER_SQL)}
    rs, skipped = rows(comp, first, holder)
    d, lo, hi, na, nb = diff_interval(rs, reps)
    near = [r for r in rs if r["band"] == "25~28%" and r["cat"] in pc.CROSSED]
    tight = sum(1 for r in near if r["margin"] < 1.04)
    skipped_text = ", ".join(f"{k} {v}사" for k, v in skipped.items())

    text = f"""# 배당성향 변화 나눠 보기 — 25%를 배당을 늘려서 넘겼나, 순이익이 줄어서 넘겼나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_payout_change.py`, `source/core/payout_change.py` · 설계: `report/설계/데이터_분석_설계.md` A1
- 데이터: `core.v_dividend_year_verified`(DART 현금배당총액), `core.v_financial_year_verified`(지배주주 순이익, 팀 검토본 반영)
- 대상: 638사 중 2025 사업연도에 흑자이고 배당성향 25% 이상인 **{len(rs)}사**. 뺀 회사: {skipped_text}

## 한 줄 결과

{{summary}}

## 1. 나누는 방법

배당성향(배당 ÷ 순이익)이 오르는 길은 두 가지다. **배당을 늘리거나, 순이익이 줄거나.** 그래서 한 가지씩만 바꿔 본다.

- **배당만 바뀌었다면**: 2025년 배당 ÷ 2024년 순이익이 25% 이상인가?
- **순이익만 바뀌었다면**: 2024년 배당 ÷ 2025년 순이익이 25% 이상인가?

| 결과 | 뜻 |
|---|---|
| {pc.BY_DIVIDEND} | 배당만 바뀌어도 넘고, 순이익만 바뀌어서는 못 넘음 |
| {pc.BY_PROFIT} | 순이익만 바뀌어도 넘고, 배당만 바뀌어서는 못 넘음 |
| {pc.EITHER} | 어느 쪽만으로도 넘음 |
| {pc.BOTH_NEEDED} | 하나만으로는 못 넘고, 둘이 겹쳐서 넘음 |

비율은 나누지 않고 곱해서 비교했다(100 × 배당 ≥ 25 × 순이익).

## 2. 2025 배당성향 구간별로 어떻게 25% 이상이 됐나

{category_table(rs, "band", BANDS)}

## 3. 2024년엔 25% 미만이던 회사만 보기

{crossed_summary(rs)}

- '배당성향 상승 중 배당 몫'은 배당성향이 오른 폭을 배당 증가 몫과 순이익 감소 몫으로 나눈 것(로그로 나눠 둘의 합 = 100%). 100%면 순이익은 그대로이고 배당만 늘었다는 뜻이다. 100%를 넘으면 순이익은 오히려 늘었는데 배당을 더 크게 늘려 배당성향이 올랐다는 뜻이다.
- '실제 배당 ÷ 최소 배당'은 2025년 순이익으로 배당성향 25%를 맞추는 데 필요한 최소 배당 대비 실제 배당이다. 1.00배면 딱 25%다.
- 25~28% 구간에서 2024년엔 25% 미만이던 {len(near)}사 중 **{tight}사는 실제 배당이 최소 배당의 1.04배 미만**(배당성향 26% 미만)이다.

## 4. '배당을 늘려서 넘김' 비율 차이

2024년엔 25% 미만이던 회사 중 '배당을 늘려서 넘김' 비율: 25~28% 구간({na}사) − 28% 이상({nb}사) = **{d:+.1f}%p** (오차 범위 95%: {lo:+.1f} ~ {hi:+.1f}%p, 회사를 무작위로 다시 뽑아 {reps}번 계산, 시드 {SEED})

## 5. 공시 시기·최대주주 유형별 (2025 배당성향 25~28% 구간만)

{category_table([r for r in rs if r["band"] == "25~28%"], "timing", ("2025년까지 첫 공시", "2026년 첫 공시"))}

{category_table([r for r in rs if r["band"] == "25~28%"], "holder", ("개인", "법인"))}

## 6. 읽을 때 주의

- 배당은 보통 결산 숫자가 나온 뒤(2026년 2~3월) 정한다. 그래서 '배당을 늘려서 넘김'은 회사가 순이익을 보고 배당을 맞췄을 가능성과 들어맞지만, 그 자체로 의도를 증명하지는 않는다.
- 2024년 값이 없거나, 2024년에 적자·무배당이던 회사는 따로 셌다.
- 638사는 2025년에 25%를 넘긴 회사만이라, 배당을 늘렸는데도 못 넘긴 회사는 이 표에 없다.
"""
    by_div = sum(1 for r in near if r["cat"] == pc.BY_DIVIDEND)
    by_profit = sum(1 for r in near if r["cat"] == pc.BY_PROFIT)
    both = sum(1 for r in near if r["cat"] == pc.BOTH_NEEDED)
    summary = (f"2025 배당성향 25~28% 회사 중 2024년엔 25% 미만이던 {len(near)}사를 보면, **{by_div}사({by_div * 100 / len(near):.0f}%)는 "
               f"배당을 늘려서**, {both}사({both * 100 / len(near):.0f}%)는 배당 증가와 순이익 감소가 겹쳐서, "
               f"{by_profit}사는 순이익이 줄어든 것만으로 25%를 넘겼다. 이들 중 {tight}사는 배당성향이 25~26%로, "
               f"25%를 맞추는 데 필요한 최소 배당보다 4% 이내만 더 냈다.") if near else "해당 회사 없음."
    text = text.replace("{summary}", summary)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=1000)
    a = ap.parse_args()
    main(a.url, a.reps)
