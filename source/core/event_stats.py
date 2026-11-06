"""이벤트 스터디 통계 방법 모음 (numpy만 사용). 여러 방법의 결론이 같은지 보려고 둔다.

초과수익률 모형
- 시장조정: AR = R − R_시장
- 시장모형: 이벤트 전 250~30거래일(최소 100일)로 α·β 추정, AR = R − (α + β·R_시장)

"CAR이 0과 다른가" 검정
- 단순 t: 사례 CAR의 평균 ÷ 표준오차 (사례끼리 독립 가정)
- 공시일 군집 t: 같은 날 공시를 한 묶음으로 본 표준오차 (날짜 몰림 보정)
- BMP(Boehmer·Musumeci·Poulsen 1991): 추정기간 잔차 표준편차로 표준화한 CAR의 t (이벤트로 커진 변동성 보정)
- Kolari·Pynnönen(2010) 보정 BMP: 사례 간 평균 잔차 상관 r̄로 BMP t를 √((1−r̄)/(1+(n−1)r̄))배 (날짜 몰림 보정)
- 일반화 부호 검정(Cowan 1992): CAR 양수 비율을 추정기간 양수 비율과 비교 (두꺼운 꼬리에 강함)
- 윌콕슨 부호순위(정규 근사)

묶음 비교·크기 관계
- 횡단면 회귀(OLS) + 공시일 군집 표준오차: CAR = a + Σ b·x
- 달력시간 포트폴리오: 매일 창 안에 있는 사례를 동일가중 → R_p − R_시장의 평균(일) × 창 길이, 뉴이-웨스트 표준오차(5일)
- 다중 비교: Benjamini–Hochberg
"""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

EST_START, EST_END, EST_MIN = 250, 30, 100


def norm_p(z: float) -> float:
    """양쪽 정규 p값."""
    return math.erfc(abs(z) / math.sqrt(2)) if np.isfinite(z) else float("nan")


@dataclass
class EventAR:
    """사례 하나의 창 안 일별 초과수익률과 추정기간 정보."""

    ar: np.ndarray          # 창(0..W) 일별 AR
    sigma: float | None     # 추정기간 잔차 표준편차 (시장모형일 때)
    est_resid: np.ndarray | None
    est_pos_share: float | None  # 추정기간 AR 양수 비율


def event_ar(stock: np.ndarray, market: np.ndarray, idx: int, window: int, model: str,
             add: np.ndarray | None = None) -> EventAR | None:
    """stock·market: 거래일 순 가격. idx: 이벤트일 위치. add: 창 날짜별로 더할 배당 몫(배당 포함 수익률)."""
    if idx - EST_START - 1 < 0 or idx + window >= len(stock):
        est = None
    else:
        est = slice(idx - EST_START, idx - EST_END)
    rs = stock[1:] / stock[:-1] - 1
    rm = market[1:] / market[:-1] - 1
    win = slice(idx - 1, idx + window)  # 수익률 배열은 하루 밀림 (rs[i] = i+1일 수익률)
    r_win, m_win = rs[win], rm[win]
    if len(r_win) != window + 1 or np.isnan(r_win).any() or np.isnan(m_win).any():
        return None
    if add is not None:
        r_win = r_win + add
    if model == "시장조정":
        sigma, resid, pos = None, None, None
        if est is not None:
            e = rs[est] - rm[est]
            e = e[~np.isnan(e)]
            if len(e) >= EST_MIN:
                sigma, resid, pos = float(e.std(ddof=1)), e, float((e > 0).mean())
        return EventAR(r_win - m_win, sigma, resid, pos)
    if est is None:
        return None
    x, y = rm[est], rs[est]
    ok = ~(np.isnan(x) | np.isnan(y))
    if ok.sum() < EST_MIN:
        return None
    beta, alpha = np.polyfit(x[ok], y[ok], 1)
    resid = y[ok] - (alpha + beta * x[ok])
    return EventAR(r_win - (alpha + beta * m_win), float(resid.std(ddof=2)), resid, float((resid > 0).mean()))


def simple_t(car: np.ndarray) -> tuple[float, float]:
    t = car.mean() / (car.std(ddof=1) / math.sqrt(len(car)))
    return float(t), norm_p(t)


def clustered_t(car: np.ndarray, cluster: np.ndarray) -> tuple[float, float]:
    """평균의 t, 표준오차는 cluster(공시일)로 묶음."""
    beta, se = ols_cluster(np.ones((len(car), 1)), car, cluster)
    t = beta[0] / se[0]
    return float(t), norm_p(t)


def bmp(cars: np.ndarray, sigmas: np.ndarray, window: int, rbar: float = 0.0) -> tuple[float, float]:
    """BMP 검정. rbar > 0이면 Kolari·Pynnönen 보정."""
    scar = cars / (sigmas * math.sqrt(window + 1))
    n = len(scar)
    t = scar.mean() / (scar.std(ddof=1) / math.sqrt(n))
    if rbar:
        t *= math.sqrt((1 - rbar) / (1 + (n - 1) * rbar))
    return float(t), norm_p(t)


def mean_residual_corr(resids: list[np.ndarray], max_pairs: int = 3000, seed: int = 0) -> float:
    """사례들의 추정기간 잔차 사이 평균 상관(같은 길이 끝부분만, 무작위 쌍)."""
    rng = np.random.default_rng(seed)
    L = min(len(r) for r in resids)
    m = np.vstack([r[-L:] for r in resids])
    n = len(m)
    if n < 3:
        return 0.0
    i = rng.integers(0, n, max_pairs)
    j = rng.integers(0, n, max_pairs)
    keep = i != j
    c = [np.corrcoef(m[a], m[b])[0, 1] for a, b in zip(i[keep], j[keep])]
    return float(np.nanmean(c))


def generalized_sign(car: np.ndarray, p_hat: float) -> tuple[float, float]:
    n, w = len(car), int((car > 0).sum())
    z = (w - n * p_hat) / math.sqrt(n * p_hat * (1 - p_hat))
    return float(z), norm_p(z)


def wilcoxon(car: np.ndarray) -> tuple[float, float]:
    x = car[car != 0]
    n = len(x)
    r = pd.Series(np.abs(x)).rank().to_numpy()
    w = r[x > 0].sum()
    mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (w - mu) / sd
    return float(z), norm_p(z)


def ols_cluster(X: np.ndarray, y: np.ndarray, cluster: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS 계수와 군집 강건 표준오차(CR1)."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    groups = pd.Series(range(len(y))).groupby(pd.Series(cluster).astype(str).to_numpy()).indices
    for idx in groups.values():
        s = X[idx].T @ u[idx]
        meat += np.outer(s, s)
    g, n, k = len(groups), len(y), X.shape[1]
    adj = (g / max(g - 1, 1)) * ((n - 1) / max(n - k, 1))
    cov = adj * xtx_inv @ meat @ xtx_inv
    return beta, np.sqrt(np.clip(np.diag(cov), 0, None))


def newey_west_mean(x: np.ndarray, lags: int = 5) -> tuple[float, float]:
    """평균과 뉴이-웨스트 표준오차."""
    x = x[~np.isnan(x)]
    n = len(x)
    e = x - x.mean()
    s = (e @ e) / n
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        s += 2 * w * (e[lag:] @ e[:-lag]) / n
    return float(x.mean()), math.sqrt(s / n)


def calendar_time(excess_by_day: dict, window: int) -> tuple[float, float, int]:
    """{날짜: [그날 창 안 사례들의 R−R_시장]} → (창 길이 환산 CAR %, p, 포트폴리오 날 수)."""
    daily = np.array([np.mean(v) for _, v in sorted(excess_by_day.items()) if v])
    m, se = newey_west_mean(daily)
    return m * (window + 1) * 100, norm_p(m / se) if se else float("nan"), len(daily)


def benjamini_hochberg(p: list[float]) -> list[float]:
    """BH 보정 q값."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return list(q)
