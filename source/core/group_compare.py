"""두 무리 비교와 예측 모델(로지스틱 회귀) 계산 (분석 설계 A2·A3).

- 중앙값·비율 차이의 오차 범위: 무리마다 회사를 무작위로 다시 뽑아 반복 계산하고 가운데 95%를 쓴다.
- 로지스틱 회귀: 0/1 결과(예: 배당성향 25~28%에 있나)를 여러 특징으로 함께 설명한다. 다른 특징이 같을 때
  한 특징이 가능성을 몇 배로 바꾸는지(오즈비)를 낸다. scipy·statsmodels 없이 numpy로 푼다(반복 가중 최소제곱).
"""
import math
from dataclasses import dataclass

import numpy as np

SEED = 20261029
REPS = 1000


@dataclass(frozen=True)
class Diff:
    a: float        # 무리 A 값(중앙값 또는 비율 %)
    b: float        # 무리 B 값
    diff: float     # A − B
    low: float      # 오차 범위(95%) 아래
    high: float     # 오차 범위(95%) 위
    n_a: int
    n_b: int


def _clean(xs) -> np.ndarray:
    return np.array([x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))], dtype=float)


def median_diff(a, b, reps: int = REPS, seed: int = SEED) -> Diff:
    a, b = _clean(a), _clean(b)
    rng = np.random.default_rng(seed)
    draws = [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(reps)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return Diff(float(np.median(a)), float(np.median(b)), float(np.median(a) - np.median(b)), float(lo), float(hi), len(a), len(b))


def share_diff(a, b, reps: int = REPS, seed: int = SEED) -> Diff:
    """a, b: 참/거짓 목록. 값은 %."""
    a, b = _clean(a), _clean(b)
    rng = np.random.default_rng(seed)
    draws = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(reps)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return Diff(a.mean() * 100, b.mean() * 100, (a.mean() - b.mean()) * 100, lo * 100, hi * 100, len(a), len(b))


@dataclass(frozen=True)
class Term:
    name: str
    coef: float
    se: float

    @property
    def odds(self) -> float:
        return math.exp(self.coef)

    @property
    def odds_low(self) -> float:
        return math.exp(self.coef - 1.96 * self.se)

    @property
    def odds_high(self) -> float:
        return math.exp(self.coef + 1.96 * self.se)

    @property
    def p(self) -> float:
        """양쪽 유의확률(정규 근사)."""
        return math.erfc(abs(self.coef / self.se) / math.sqrt(2))


def logistic(x: np.ndarray, y: np.ndarray, names: list[str], iters: int = 50) -> list[Term]:
    """x: 회사 × 특징(상수항은 여기서 붙임), y: 0/1. 반복 가중 최소제곱으로 푼다."""
    xx = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(xx.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-xx @ beta))
        w = p * (1 - p)
        info = xx.T @ (xx * w[:, None])
        step = np.linalg.solve(info, xx.T @ (y - p))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = 1 / (1 + np.exp(-xx @ beta))
    cov = np.linalg.inv(xx.T @ (xx * (p * (1 - p))[:, None]))
    se = np.sqrt(np.diag(cov))
    return [Term(n, float(b), float(s)) for n, b, s in zip(["상수항"] + names, beta, se)]


def mean_diff(a, b, reps: int = REPS, seed: int = SEED) -> Diff:
    """평균 차이(값 단위 그대로)."""
    a, b = _clean(a), _clean(b)
    rng = np.random.default_rng(seed)
    draws = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(reps)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return Diff(float(a.mean()), float(b.mean()), float(a.mean() - b.mean()), float(lo), float(hi), len(a), len(b))


def cluster_mean_diff(a, b, ca, cb, reps: int = REPS, seed: int = SEED) -> Diff:
    """평균 차이의 오차 범위를 회사가 아니라 묶음(예: 공시 날짜)째로 다시 뽑아 낸다.

    같은 묶음의 회사들은 같은 날 시장 분위기를 함께 타므로 서로 따로 움직이지 않는다. ca, cb는 a, b 값마다의 묶음 이름.
    두 무리가 묶음을 공유하면 함께 뽑힌다. b가 비어 있으면 a 평균 하나의 오차 범위(diff = a 평균).
    값이 None·NaN인 항목은 뺀다.
    """
    pa = [(x, c) for x, c in zip(a, ca) if x is not None and not (isinstance(x, float) and math.isnan(x))]
    pb = [(x, c) for x, c in zip(b, cb) if x is not None and not (isinstance(x, float) and math.isnan(x))]
    keys = sorted({c for _, c in pa} | {c for _, c in pb}, key=str)
    pos = {k: i for i, k in enumerate(keys)}
    sa, na, sb, nb = (np.zeros(len(keys)) for _ in range(4))
    for x, c in pa:
        sa[pos[c]] += x
        na[pos[c]] += 1
    for x, c in pb:
        sb[pos[c]] += x
        nb[pos[c]] += 1
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), (reps, len(keys)))
    da, db = na[idx].sum(1), nb[idx].sum(1)
    ma = np.divide(sa[idx].sum(1), da, out=np.full(reps, np.nan), where=da > 0)
    mb = np.divide(sb[idx].sum(1), db, out=np.full(reps, np.nan), where=db > 0) if pb else np.zeros(reps)
    draws = (ma - mb)[~np.isnan(ma - mb)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    mean_a = sa.sum() / na.sum()
    mean_b = sb.sum() / nb.sum() if pb else 0.0
    return Diff(float(mean_a), float(mean_b), float(mean_a - mean_b), float(lo), float(hi), len(pa), len(pb))


def adjusted_diff(y, group, controls, reps: int = REPS, seed: int = SEED) -> tuple[float, float, float, int]:
    """다른 특징(controls: 회사 × 특징)이 같을 때 group(1/0)에 따른 y 차이. 최소제곱 직선 맞추기 + 회사 다시 뽑기.

    돌려주는 값: (차이, 오차 범위 아래, 위, 회사 수). 값이 하나라도 없는 회사는 뺀다.
    """
    x = np.column_stack([np.ones(len(y)), np.asarray(group, dtype=float), np.asarray(controls, dtype=float)])
    y = np.asarray(y, dtype=float)
    ok = ~np.isnan(x).any(axis=1) & ~np.isnan(y)
    x, y = x[ok], y[ok]
    est = np.linalg.lstsq(x, y, rcond=None)[0][1]
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        i = rng.integers(0, len(y), len(y))
        draws.append(np.linalg.lstsq(x[i], y[i], rcond=None)[0][1])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(est), float(lo), float(hi), int(len(y))
