"""고배당기업 배당소득 분리과세가 배당 결정을 바꿨나 (이중차분·사건연구).

제도 일정 (출처는 report/분석/배당_제도효과_분석_결과.md):
  2024-07-25 정부 세법개정안에 주주환원 촉진세제 → 2024-12-10 국회 의결에서 빠짐
  2025-07-31 세제개편안에 고배당기업 배당소득 분리과세 → 2025-12-02 국회 통과 → 2026-01-01 시행
  2026 요건 판정은 2025 사업연도 숫자로 한다(source/core/judgement.py). 그래서 2025 사업연도 배당(2026년 초 결정)이
  제도를 알고 정한 첫 배당이다. POST_YEAR = 2025.

주 검정 1 · 기준선까지의 거리: 해마다 전년 숫자로 '올해 요건을 맞추려면 배당을 몇 % 늘려야 하나'를 잰다
  (순이익이 전년과 같다고 가정). 필요 증가가 50% 이하면 '가까움', 넘으면 '멂'. 가까운 회사가 배당을 10% 이상
  늘리는 비율이 2025년에만 더 커졌는지 본다. 거리를 해마다 같은 기준으로 재므로, 배당성향이 낮던 회사가 원래
  다음 해에 배당을 올리기 쉬운 몫(평균으로 돌아가는 성질)은 다른 해와 비교할 때 빠진다.
주 검정 2 · 개인 최대주주 회사: 2024년 최대주주가 개인이고 최대주주+특수관계인 지분이 30% 이상인 회사.
  배당이 개인 최대주주에게 바로 가서 분리과세로 아끼는 세금이 가장 큰 무리다. 최대주주가 법인이면 배당이 그 법인으로 먼저 간다. 이 회사들이 2025년에만 배당을 더 늘렸는지 본다.

연도 효과가 그해 경기를 통째로 빼고, 금리·환율 노출도 × 경기 변화(source/core/exposure_dividend.py)와 밸류업 공시도 통제한다.
"""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from core import exposure_dividend as ex
from core import major_holder as mh

POST_YEAR = 2025
BASE_YEAR = 2023  # 사건연구 기준 해
CLOSE_MAX_GROWTH = 0.5
HOLDER_PCT = 30
SEED = 20261102
N_PERM = 1000

MET, CLOSE, FAR, OUT = "이미 충족", "가까움", "멂", "무배당·적자"

EXPOSURE_CONTROLS = ["rate_exp", "fx_exp", "rate_x_macro", "fx_x_macro"]
BASE_CONTROLS = [*ex.CONTROLS, "valueup"]


# ---------------------------------------------------------------- 요건까지의 거리

def needed_growth(d_prev: float, ni: float) -> float:
    """순이익이 ni일 때 요건(가목: 배당성향 40%·배당 안 줄임 / 나목: 25% 이상·배당 10% 증가)을 맞추는 가장 작은
    배당의 전년 대비 증가율. d_prev > 0, ni > 0일 때만."""
    need = min(max(0.40 * ni, d_prev), max(0.25 * ni, 1.10 * d_prev))
    return need / d_prev - 1


def distance_group(d_prev, ni_prev) -> str:
    if pd.isna(d_prev) or pd.isna(ni_prev) or d_prev <= 0 or ni_prev <= 0:
        return OUT
    if 100 * d_prev >= 40 * ni_prev:
        return MET
    return CLOSE if needed_growth(d_prev, ni_prev) <= CLOSE_MAX_GROWTH else FAR


def met_requirement(d: float, d_prev: float, ni: float) -> float:
    """그해 숫자로 요건을 맞췄나(흑자·전년 배당 있는 회사만, 제2호는 배당이 전년보다 안 줄었나로 근사)."""
    if any(pd.isna(v) for v in (d, d_prev, ni)) or ni <= 0 or d_prev <= 0:
        return np.nan
    if d < d_prev:
        return 0.0
    return float(100 * d >= 40 * ni or (100 * d >= 25 * ni and 10 * d >= 11 * d_prev))


# ---------------------------------------------------------------- 최대주주

def holder_table(rows: pd.DataFrame) -> pd.DataFrame:
    """partner.major_holder 행 → 회사별 최대주주 종류와 지분율(가장 늦은 보고서). source/core/major_holder.summarize 규칙 그대로."""
    out = []
    for corp, g in rows.groupby("corp_code"):
        g = g[g["rcept_no"] == g["rcept_no"].max()]
        h = mh.summarize(g.to_dict("records"))
        out.append({"corp_code": corp, "largest_kind": h.largest_kind,
                    "pct_common": float(h.pct_common) if h.pct_common is not None else np.nan})
    t = pd.DataFrame(out, columns=["corp_code", "largest_kind", "pct_common"])
    t["holder_high"] = ((t["largest_kind"] == mh.PERSON) & (t["pct_common"] >= HOLDER_PCT)).astype(float)
    return t


# ---------------------------------------------------------------- 분석용 표

def add_policy_columns(p: pd.DataFrame, holders: pd.DataFrame, valueup_first: pd.Series) -> pd.DataFrame:
    """core.exposure_dividend.build_panel 결과에 거리 무리(dist), 결과(10% 증가·요건 충족), 대주주, 밸류업 칸을 붙인다.

    valueup_first: 회사별 첫 '기업가치 제고 계획' 공시일. 사업연도 Y 배당은 Y+1년 3월 말까지 정하므로,
    그 전에 공시했으면 valueup = 1.
    """
    p = p.copy()
    p["dist"] = [distance_group(d, n) for d, n in zip(p["d_won_prev"], p["ni_owner_won_prev"])]
    p["close"] = (p["dist"] == CLOSE).astype(float)
    p["post"] = (p["bsns_year"] == POST_YEAR).astype(float)
    p["up10"] = np.where(p["d_won_prev"] > 0, (10 * p["d_won"] >= 11 * p["d_won_prev"]).astype(float), np.nan)
    p.loc[p["d_won"].isna(), "up10"] = np.nan
    p["met"] = [met_requirement(d, dp, n) for d, dp, n in zip(p["d_won"], p["d_won_prev"], p["ni_owner_won"])]
    p = p.merge(holders[["corp_code", "holder_high", "largest_kind", "pct_common"]], on="corp_code", how="left")
    deadline = pd.to_datetime((p["bsns_year"] + 1).astype(str) + "-03-31")
    first = pd.to_datetime(p["corp_code"].map(valueup_first))
    p["valueup"] = (first.notna() & (first <= deadline)).astype(float)
    p["rate_x_macro"] = p["rate_exp"] * p["base_rate_chg"]
    p["fx_x_macro"] = p["fx_exp"] * p["usdkrw_growth"]
    return p


# ---------------------------------------------------------------- 고정효과 회귀

@dataclass(frozen=True)
class Term:
    name: str
    coef: float
    se: float

    @property
    def p(self) -> float:
        return math.erfc(abs(self.coef / self.se) / math.sqrt(2)) if self.se > 0 else float("nan")

    @property
    def low(self) -> float:
        return self.coef - 1.96 * self.se

    @property
    def high(self) -> float:
        return self.coef + 1.96 * self.se


@dataclass(frozen=True)
class Result:
    terms: dict[str, Term]
    n: int
    n_firms: int


def fe_ols(d: pd.DataFrame, y: str, xs: list[str], fe=("corp_code", "bsns_year")) -> Result:
    """y ~ xs + 고정효과, 회사 단위 묶음 표준오차(CR1). d에는 빈칸이 없어야 한다."""
    groups = [pd.factorize(d[c])[0] for c in fe]
    yt = ex.demean(d[y].to_numpy(float), groups)[:, 0]
    xt = ex.demean(d[xs].to_numpy(float), groups)
    keep = np.abs(xt).max(axis=0) > 1e-12  # 고정효과에 다 흡수된 칸은 뺀다
    xt, names = xt[:, keep], [n for n, k in zip(xs, keep) if k]
    inv = np.linalg.pinv(xt.T @ xt)
    beta = inv @ xt.T @ yt
    u = yt - xt @ beta
    firm = pd.factorize(d["corp_code"])[0]
    g = firm.max() + 1
    score = np.zeros((g, xt.shape[1]))
    np.add.at(score, firm, xt * u[:, None])
    n, k = xt.shape
    v = inv @ (score.T @ score) @ inv * (g / (g - 1) * (n - 1) / (n - k))
    terms = {nm: Term(nm, float(b), float(math.sqrt(max(v[i, i], 0)))) for i, (nm, b) in enumerate(zip(names, beta))}
    return Result(terms, n, int(g))


def _sample(p: pd.DataFrame, y: str, cols: list[str], extra: pd.Series | None = None) -> pd.DataFrame:
    d = p.dropna(subset=[y, *cols])
    if extra is not None:
        d = d[extra.reindex(d.index).fillna(False)]
    return d.reset_index(drop=True)


@dataclass(frozen=True)
class DiD:
    name: str
    coef: float
    se: float
    p_cluster: float
    p_perm: float | None
    n: int
    n_firms: int
    n_treated_post: int  # 2025년 처리 무리 회사 수

    @property
    def low(self) -> float:
        return self.coef - 1.96 * self.se

    @property
    def high(self) -> float:
        return self.coef + 1.96 * self.se


def did_distance(p: pd.DataFrame, y: str = "up10", controls: list[str] | None = None, post_year: int = POST_YEAR,
                 years: tuple[int, int] = (2018, 2025), n_perm: int = N_PERM, seed: int = SEED, name: str = "") -> DiD:
    """가까움 vs 멂: y ~ close + close×post + 통제 + 회사·연도 효과. 순열: post_year 해의 '가까움' 이름을 섞는다."""
    controls = BASE_CONTROLS + EXPOSURE_CONTROLS if controls is None else controls
    q = p[p["bsns_year"].between(*years) & p["dist"].isin([CLOSE, FAR])].copy()
    q["post"] = (q["bsns_year"] == post_year).astype(float)
    q["close_post"] = q["close"] * q["post"]
    d = _sample(q, y, ["close", *controls])
    xs = ["close_post", "close", *controls]
    r = fe_ols(d, y, xs)
    t = r.terms["close_post"]
    p_perm = None
    if n_perm:
        rng = np.random.default_rng(seed)
        idx = np.flatnonzero(d["post"].to_numpy() == 1)
        hits = 0
        for _ in range(n_perm):
            s = d.copy()
            s.loc[idx, "close"] = rng.permutation(s.loc[idx, "close"].to_numpy())
            s["close_post"] = s["close"] * s["post"]
            b = fe_ols(s, y, xs).terms["close_post"].coef
            hits += abs(b) >= abs(t.coef) - 1e-12
        p_perm = (hits + 1) / (n_perm + 1)
    treated = int(d.loc[d["post"] == 1, "close"].sum())
    return DiD(name, t.coef, t.se, t.p, p_perm, r.n, r.n_firms, treated)


def did_holder(p: pd.DataFrame, y: str = "up10", controls: list[str] | None = None, post_year: int = POST_YEAR,
               years: tuple[int, int] = (2018, 2025), n_perm: int = N_PERM, seed: int = SEED, name: str = "") -> DiD:
    """대주주 혜택: y ~ high×post + 통제 + 회사·연도 효과. 순열: 회사 단위로 high 이름을 섞는다."""
    controls = BASE_CONTROLS + EXPOSURE_CONTROLS if controls is None else controls
    q = p[p["bsns_year"].between(*years)].copy()
    q["post"] = (q["bsns_year"] == post_year).astype(float)
    q["high_post"] = q["holder_high"] * q["post"]
    d = _sample(q, y, ["holder_high", *controls])
    xs = ["high_post", *controls]
    r = fe_ols(d, y, xs)
    t = r.terms["high_post"]
    p_perm = None
    if n_perm:
        rng = np.random.default_rng(seed)
        firms = d.groupby("corp_code")["holder_high"].first()
        hits = 0
        for _ in range(n_perm):
            shuffled = pd.Series(rng.permutation(firms.to_numpy()), index=firms.index)
            s = d.assign(holder_high=d["corp_code"].map(shuffled))
            s["high_post"] = s["holder_high"] * s["post"]
            b = fe_ols(s, y, xs).terms["high_post"].coef
            hits += abs(b) >= abs(t.coef) - 1e-12
        p_perm = (hits + 1) / (n_perm + 1)
    treated = int(d.loc[(d["post"] == 1) & (d["holder_high"] == 1), "corp_code"].nunique())
    return DiD(name, t.coef, t.se, t.p, p_perm, r.n, r.n_firms, treated)


def event_study(p: pd.DataFrame, treat: str, y: str = "up10", controls: list[str] | None = None,
                sample: pd.Series | None = None, years: tuple[int, int] = (2018, 2025)) -> pd.DataFrame:
    """처리 × 연도 계수(기준 BASE_YEAR = 0). 2025년 계수가 제도 뒤, 나머지는 제도 전 추세 확인."""
    controls = BASE_CONTROLS + EXPOSURE_CONTROLS if controls is None else controls
    q = p[p["bsns_year"].between(*years)].copy()
    if sample is not None:
        q = q[sample.reindex(q.index).fillna(False)]
    yrs = [yy for yy in range(years[0], years[1] + 1) if yy != BASE_YEAR]
    cols = []
    for yy in yrs:
        c = f"t_{yy}"
        q[c] = q[treat] * (q["bsns_year"] == yy)
        cols.append(c)
    extra = [treat] if treat == "close" else []
    d = _sample(q, y, [treat, *controls])
    r = fe_ols(d, y, [*cols, *extra, *controls])
    rows = [{"year": BASE_YEAR, "coef": 0.0, "low": 0.0, "high": 0.0, "p": np.nan}]
    for yy, c in zip(yrs, cols):
        t = r.terms.get(c)
        if t is not None:
            rows.append({"year": yy, "coef": t.coef, "low": t.low, "high": t.high, "p": t.p})
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def raw_rates(p: pd.DataFrame, by: str, y: str = "up10", years: tuple[int, int] = (2018, 2025)) -> pd.DataFrame:
    """연도 × 무리별 y 평균(%)과 회사 수. 회귀 전 눈으로 보는 표."""
    q = p[p["bsns_year"].between(*years)].dropna(subset=[y])
    t = q.groupby(["bsns_year", by])[y].agg(["mean", "count"]).reset_index()
    t["mean"] *= 100
    return t
