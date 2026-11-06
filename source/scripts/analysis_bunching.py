"""25% 기준선 쏠림 분석 결과를 report/분석/기준선_몰림_분석_결과.md로 쓴다 (분석 설계 2절, source/core/bunching.py).

실행: .venv/bin/python -m scripts.analysis_bunching [--url ...] [--reps 1000]
데이터: core.v_dividend_year_verified(D) ÷ core.v_financial_year_verified(지배주주 순이익), 흑자 회사만.
"""
import argparse
from datetime import date
from pathlib import Path

from core import bunching as bn
from core import db
from core import p1_analysis as p1

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "기준선_몰림_분석_결과.md"
YEARS = range(2018, 2026)
HEAD = ("| 사업연도 | 기준선 | 5~75% 회사 수 | 기준선 바로 위 실제 | 예상 | 예상보다 많은 수 | 오차 범위(95%) | 확실히 많음 |\n"
        "|---|---|---|---|---|---|---|---|")


def _row(y, r: bn.BunchResult) -> str:
    sure = "예" if r.ci_low > 0 else "아니오"
    return (f"| {y} | {r.threshold:.0f}% | {r.n} | {r.above_actual} | {r.above_actual - r.excess:.1f} | {r.excess:.1f} | "
            f"{r.ci_low:.1f} ~ {r.ci_high:.1f} | {sure} |")


def histogram_table(values) -> str:
    left, hist = bn.counts(values)
    cf = bn.counterfactual(left, hist, bn.THRESHOLDS, degree=bn.DEGREE_ONE_SIDED, fit_range=bn.FIT_RANGE_25)
    lines = ["| 배당성향 | 실제 회사 수 | 예상 회사 수 | 차이 |", "|---|---|---|---|"]
    for a, h, c in zip(left, hist, cf):
        if 20 <= a < 50:
            lines.append(f"| {a:.0f}~{a + 1:.0f}% | {h} | {c:.1f} | {h - c:+.1f} |")
    return "\n".join(lines)


def below_25(values) -> str:
    return f"{sum(1 for v in values if v < 25)} / {len(values)}"


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
    pay = bn.payouts_by_year(comp, YEARS)

    real = [_row(y, bn.one_sided_25(pay[y], reps=reps)) for y in YEARS]
    fake = [_row(2025, bn.bootstrap(pay[2025], t, window_thresholds=bn.THRESHOLDS + bn.PLACEBO_THRESHOLDS, reps=reps,
                                    fit_range=bn.FIT_RANGE_25))
            for t in bn.PLACEBO_THRESHOLDS]
    robust = ["| 바꾼 조건 | 25~28%에 예상보다 많은 수 |", "|---|---|"]
    for label, kw in [(f"기본 ({bn.DEGREE_ONE_SIDED}차 곡선, 바로 위 {bn.ABOVE:.0f}%p, 28% 이상으로 예상)", {}),
                      ("2차 곡선", {"degree": 2}), ("4차 곡선", {"degree": 4}),
                      ("바로 위 2%p (27% 이상으로 예상)", {"above": 2.0, "fit_range": (27.0, bn.RANGE[1])}),
                      ("바로 위 5%p (30% 이상으로 예상)", {"above": 5.0, "fit_range": (30.0, bn.RANGE[1])})]:
        robust.append(f"| {label} | {bn.one_sided_25(pay[2025], **kw).excess:.1f} |")
    shares = "\n".join(f"| {y} | {below_25(pay[y])} |" for y in YEARS)

    text = f"""# 25% 기준선 쏠림 분석 결과 — 배당성향이 25% 바로 위에 몰렸나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_bunching.py`, `source/core/bunching.py` · 설계: `report/설계/데이터_분석_설계.md` 2절
- 데이터: `core.v_dividend_year_verified`의 DART 현금배당총액 ÷ `core.v_financial_year_verified`의 지배주주 순이익(팀 검토본 반영). 638사 중 **흑자 회사만**(적자 회사의 간주 배당성향 25%·0%는 뺌)

## 한 줄 결과

2025 사업연도에 배당성향 25~28%인 회사가 예상보다 **약 69사 더 많았다**. 제도 전 연도와 법에 없는 기준선에서는 이런 쏠림이 없었다.

## 0. 먼저 알아야 할 것: 처음부터 골라진 회사들이다

638사는 모두 **2026년 KIND에 '고배당기업'으로 공시한 회사**다(`raw.kind_list`, 공시일 2026-03-03 ~ 2026-10-20). 곧 2025 배당성향이 25% 이상인 회사만 들어 있다. 그래서

- 2025년에 25% 아래가 비어 있는 것은 **회사를 이렇게 골랐기 때문**이지, 회사가 배당을 올렸다는 증거가 아니다.
- 그래도 **25% 바로 위가 그 위보다 유난히 많은지**는 볼 수 있다. 회사를 고른 방식은 25% 아래를 잘라낼 뿐, 25~26%만 늘리지는 않기 때문이다.
- **40% 기준선은 이 638사로 판단할 수 없다.** 25~40% 회사는 '배당 10% 증가' 조건까지 갖춘 회사만 남았고, 40% 이상은 그 조건 없이 남았다. 40% 위아래의 조건이 달라서, 40% 위가 많아 보여도 고르는 방식 때문일 수 있다.

흑자 회사 중 배당성향 25% 미만 회사 수:

| 사업연도 | 25% 미만 / 전체 |
|---|---|
{shares}

## 1. 계산 방법

1. 배당성향 {bn.RANGE[0]:.0f}~{bn.RANGE[1]:.0f}%를 {bn.BIN_WIDTH:.0f}%p씩 나눠 구간마다 회사 수를 센다.
2. **28% 이상 구간의 회사 수만 보고**(40% 주변 37~43%는 뺌) 매끈한 곡선({bn.DEGREE_ONE_SIDED}차식)을 그린다. 이 곡선을 25~28%까지 늘여 "쏠림이 없었다면 있었을 회사 수"(예상 회사 수)로 쓴다. 25% 아래는 처음부터 비어 있어 쓰지 않는다.
3. 25~28%의 (실제 회사 수 − 예상 회사 수) = **예상보다 많은 회사 수**.
4. 회사를 무작위로 다시 뽑아 같은 계산을 {reps}번 반복하고(시드 {bn.SEED}), 그 결과의 가운데 95%를 **오차 범위**로 적는다. 오차 범위가 0보다 크면 '확실히 많음'이다.
5. 같은 계산을 제도 전인 2018~2024년에도 해 본다. 제도 전에는 쏠림이 없어야 정상이다.

## 2. 연도별 결과

{HEAD}
{chr(10).join(real)}

## 3. 법에 없는 기준선으로 같은 계산 (2025)

법에 없는 기준선(바로 아래·위 {bn.BELOW:.0f}%p씩, 같은 28% 이상 곡선 사용)에서는 쏠림이 없어야 한다.

{HEAD}
{chr(10).join(fake)}

## 4. 계산 조건을 바꿔도 같은가 (2025)

{chr(10).join(robust)}

## 5. 2025 배당성향 구간별 실제·예상 회사 수 (20~50%)

25% 아래의 예상 회사 수는 곡선을 범위 밖으로 늘인 값이라 참고만 한다.

{histogram_table(pay[2025])}

## 6. 읽을 때 주의

- **쏠림이 있다는 것이지, 회사가 일부러 맞췄다는 증거는 아니다.** 2025년에 순이익이 줄어 배당성향이 저절로 25%를 넘은 회사도 섞여 있다. 배당 총액을 늘려서 넘겼는지는 분석 A1에서 따로 본다.
- 기준선을 못 넘은 회사가 638사에 없어서, 25% 아래에서 몇 곳이 위로 옮겨 왔는지는 셀 수 없다. 이를 보려면 고배당기업 공시를 하지 않은 상장사까지 넣어야 한다.
- 638사는 지금 상장된 회사만이라 상장폐지된 회사(예: 에코마케팅)는 없다.
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=bn.BOOT_REPS)
    a = ap.parse_args()
    main(a.url, a.reps)
