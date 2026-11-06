"""기준선 쏠림 계산: 배당성향이 25%·40% 기준선 바로 위에 유난히 몰렸는지 센다.

방법 (Chetty 외 2011, Kleven 2016의 기본형, 영어로는 bunching estimation):
1. 배당성향을 BIN_WIDTH(%p)씩 나눠 구간마다 회사 수를 센다.
2. 기준선 바로 아래(BELOW)·위(ABOVE) 구간을 빼고 나머지 구간으로 매끈한 곡선(DEGREE차식)을 그려
   '쏠림이 없었다면 있었을 회사 수'(예상 회사 수)를 만든다.
3. 기준선 바로 위 (실제 − 예상) 합 = 예상보다 많은 회사 수, 바로 아래 (예상 − 실제) 합 = 예상보다 적은 회사 수.
4. 회사를 무작위로 다시 뽑아 반복 계산해 예상보다 많은 회사 수의 오차 범위(95%)를 낸다.
배당성향은 분석용 비율이라 실수로 계산한다(판정 엔진의 금액 계산과는 별개).

[회사를 고른 방식 주의] 638사는 모두 2026년 KIND에 '고배당기업'으로 공시한 회사다(2025 배당성향 25% 이상만 있음).
그래서 2025년 25% 아래는 회사 행동이 아니라 고르는 방식 때문에 비어 있다. 25% 기준선은 28% 이상 구간
(FIT_RANGE_25)만으로 예상 회사 수를 만들어 바로 위의 쏠림만 본다. 40% 기준선은 아래(25~40%)에 '10% 증가' 회사만
남아 위아래 조건이 달라서 이 638사로는 판단할 수 없다.
"""
from dataclasses import dataclass

import numpy as np

BIN_WIDTH = 1.0
RANGE = (5.0, 75.0)
BELOW = 3.0
ABOVE = 3.0
DEGREE = 5
DEGREE_ONE_SIDED = 3  # 곡선을 범위 밖으로 늘여 쓰므로 낮은 차수
THRESHOLDS = (25.0, 40.0)
FIT_RANGE_25 = (25.0 + ABOVE, RANGE[1])  # 25% 기준선: 28% 이상 구간만으로 예상
PLACEBO_THRESHOLDS = (32.0, 50.0)  # 법에 없는 기준선: 28% 이상 범위 안, 실제 기준선 구간과 겹치지 않게 고름
BOOT_REPS = 1000
SEED = 20261029


@dataclass(frozen=True)
class BunchResult:
    threshold: float
    n: int              # 5~75% 안 회사 수
    excess: float       # 기준선 바로 위에서 예상보다 많은 회사 수 (실제 − 예상)
    missing: float      # 기준선 바로 아래에서 예상보다 적은 회사 수 (예상 − 실제)
    above_actual: int   # 기준선 바로 위 실제 회사 수
    below_actual: int   # 기준선 바로 아래 실제 회사 수
    ci_low: float | None = None
    ci_high: float | None = None


def counts(values, lo: float = RANGE[0], hi: float = RANGE[1], width: float = BIN_WIDTH) -> tuple[np.ndarray, np.ndarray]:
    """구간 왼쪽 끝과 구간별 회사 수. 범위 밖 값은 버린다."""
    edges = np.arange(lo, hi + width / 2, width)
    hist, _ = np.histogram([v for v in values if lo <= v < hi], bins=edges)
    return edges[:-1], hist


def counterfactual(left: np.ndarray, hist: np.ndarray, thresholds, width: float = BIN_WIDTH,
                   below: float = BELOW, above: float = ABOVE, degree: int = DEGREE,
                   fit_range: tuple[float, float] | None = None) -> np.ndarray:
    """기준선 주변 구간을 뺀 나머지(fit_range가 있으면 그 안만)로 곡선을 그려 모든 구간의 예상 회사 수를 돌려준다."""
    centers = left + width / 2
    keep = np.ones(len(left), dtype=bool) if fit_range is None else (left >= fit_range[0]) & (left < fit_range[1])
    for t in thresholds:
        keep &= ~((left >= t - below) & (left < t + above))
    x = (centers - centers.mean()) / centers.std()  # 고차식 계산이 흔들리지 않게 크기를 맞춤
    coef = np.polyfit(x[keep], hist[keep], degree)
    return np.polyval(coef, x)


def estimate(values, threshold: float, window_thresholds=THRESHOLDS, **kw) -> BunchResult:
    """window_thresholds: 예상 회사 수를 만들 때 주변 구간을 뺄 기준선들(검사하는 기준선은 늘 함께 뺀다).
    kw: below, above, degree, fit_range. fit_range로 한쪽만 쓰면 missing은 의미가 없다(곡선을 범위 밖으로 늘인 값)."""
    below, above = kw.get("below", BELOW), kw.get("above", ABOVE)
    left, hist = counts(values)
    ts = tuple(sorted(set(window_thresholds) | {threshold}))
    cf = counterfactual(left, hist, ts, below=below, above=above, degree=kw.get("degree", DEGREE),
                        fit_range=kw.get("fit_range"))
    up = (left >= threshold) & (left < threshold + above)
    down = (left >= threshold - below) & (left < threshold)
    return BunchResult(threshold, int(hist.sum()), float((hist[up] - cf[up]).sum()), float((cf[down] - hist[down]).sum()),
                       int(hist[up].sum()), int(hist[down].sum()))


def bootstrap(values, threshold: float, window_thresholds=THRESHOLDS, reps: int = BOOT_REPS, seed: int = SEED,
              **kw) -> BunchResult:
    """회사를 무작위로 다시 뽑아 반복 계산하고, 예상보다 많은 회사 수의 가운데 95%(2.5~97.5%)를 붙인다. kw는 estimate와 같다."""
    base = estimate(values, threshold, window_thresholds, **kw)
    arr = np.asarray(list(values), dtype=float)
    rng = np.random.default_rng(seed)
    draws = [estimate(rng.choice(arr, size=len(arr), replace=True), threshold, window_thresholds, **kw).excess
             for _ in range(reps)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return BunchResult(**{**base.__dict__, "ci_low": float(lo), "ci_high": float(hi)})


def one_sided_25(values, reps: int | None = None, **kw) -> BunchResult:
    """25% 기준선: 28% 이상 구간만으로 예상 회사 수를 만든다(25% 아래는 고르는 방식 때문에 비어 있어 쓰지 않음)."""
    opts = {"fit_range": FIT_RANGE_25, "degree": DEGREE_ONE_SIDED} | kw
    if reps is None:
        return estimate(values, 25.0, (40.0,), **opts)
    return bootstrap(values, 25.0, (40.0,), reps=reps, **opts)


def payouts_by_year(comp: dict, years) -> dict[int, list[float]]:
    """comp: core.p1_analysis.companies 모양. 흑자 회사의 실제 배당성향(%)만(적자 간주 배당성향은 뺀다)."""
    out = {y: [] for y in years}
    for d, ni, _ in comp.values():
        for y in years:
            if d.get(y) is not None and ni.get(y) and ni[y] > 0:
                out[y].append(d[y] * 100 / ni[y])
    return out
