"""금리·환율 노출도와 배당 결정 (회사×연도 패널, 노출도 차이 분석).

묻는 것: 같은 해 같은 금리·환율 변화를 겪어도, 그 변화를 더 크게 받는 회사가 배당을 다르게 정했나?
경기 값은 해마다 하나뿐이라 연도별 상관으로는 비교할 거리가 8개뿐이다. 대신 회사마다 받는 크기(노출도)가
다르다는 점을 쓴다. 연도 효과로 그해 모든 회사가 함께 겪은 분위기를 빼고, 회사 효과로 회사마다 원래 배당
성향을 뺀 뒤 '노출도 × 경기 변화' 계수를 본다.

  결과    dir_t = 주당배당금 전년 대비 방향 (줄임 −1 · 그대로 0 · 올림 +1)
  노출도  금리: 전년 말 차입금 ÷ 전년 말 자산총계 / 환율: 전년 외화 항목 절댓값 ÷ 전년 말 자산총계
          같은 해 회사끼리의 순위(0~1)로 바꿔 쓴다. 0 = 가장 적게 받는 회사, 1 = 가장 크게 받는 회사.
  경기    기준금리 연평균 변화(%p), 원/달러 연평균 변화율(%) — 배당의 사업연도 Y 값(배당은 Y+1년 초에 정한다)
  통제    Lintner(1956) 부분조정: 순이익 변화, 순이익, 전년 배당 (모두 전년 말 자산으로 나눔)

p값은 두 가지다. 회사 단위로 묶은 표준오차(정규 근사)와, 경기 값을 연도끼리 섞는 순열검정.
경기 값이 해마다 하나라 순열검정을 주 판단으로 쓴다. scipy·statsmodels 없이 numpy로 푼다.
"""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

SEED = 20261102
N_PERM = 2000
WINSOR = 0.01  # 통제 변수 위아래 1%를 그 경계값으로 눌러 극단값 영향을 줄인다

# 차입금: 재무상태표(BS) 계정 이름에 '차입금' 또는 '사채'가 든 줄. 할인·조정·이자처럼 차입 원금이 아닌 줄은 뺀다
BORROW_NAME = r"차입금|사채"
BORROW_EXCLUDE = r"상환|이자|할인|발행차금|충당|평가|전환권|조정|할증|파생|대여|매입|순증|미지급"
# 외화 항목: 현금흐름표(CF) 조정의 외화환산이익·손실, 포괄손익계산서(CIS)의 해외사업장 환산차이
FX_CF_IDS = (
    "dart_AdjustmentsForGainOnForeignExchangeTranslations",
    "dart_AdjustmentsForLossesOnForeignExchangeTranslations",
    "dart_AdjustmentsForLossOnForeignExchangeTranslations",
)
FX_CF_NAME = r"^외화환산(?:이익|손실|차익|차손)"
FX_CIS_IDS = (
    "ifrs-full_GainsLossesOnExchangeDifferencesOnTranslationNetOfTax",
    "ifrs_GainsLossesOnExchangeDifferencesOnTranslationNetOfTax",
    "ifrs-full_GainsLossesOnExchangeDifferencesOnTranslationBeforeTax",
    "ifrs_OtherComprehensiveIncomeNetOfTaxExchangeDifferencesOnTranslation",
    "ifrs-full_OtherComprehensiveIncomeNetOfTaxExchangeDifferencesOnTranslation",
)
FX_CIS_NAME = r"^해외사업장?환산"  # 표준계정코드를 안 쓴 줄. 재분류 조정 줄은 뺀다
BASIS_TO_DIV = {"연결": "CFS", "별도": "OFS"}

CONTROLS = ["ni_chg_a", "ni_a", "d_prev_a"]
CONTROL_LABELS = {"ni_chg_a": "순이익 변화 ÷ 전년 자산", "ni_a": "순이익 ÷ 전년 자산", "d_prev_a": "전년 배당 ÷ 전년 자산"}


# ---------------------------------------------------------------- 재무제표 줄 → 회사×연도 값

def borrowings(lines: pd.DataFrame) -> pd.DataFrame:
    """fs_line 줄(corp_code, bsns_year, fs_div, sj_div, account_nm, thstrm_amount) → 회사×연도×재무제표 종류별 차입금 합계."""
    bs = lines[lines["sj_div"] == "BS"]
    nm = bs["account_nm"].fillna("")
    hit = bs[nm.str.contains(BORROW_NAME) & ~nm.str.contains(BORROW_EXCLUDE)]
    out = hit.assign(v=hit["thstrm_amount"].astype(float).abs()).groupby(["corp_code", "bsns_year", "fs_div"])["v"].sum()
    return out.rename("borrow_won").reset_index()


def fx_items(lines: pd.DataFrame) -> pd.DataFrame:
    """회사×연도×재무제표 종류별 외화 항목 = |CF 외화환산이익| + |CF 외화환산손실| + |CIS 해외사업장 환산차이|.

    CIS 환산차이는 세후·세전 줄이 함께 있을 수 있어 그중 절댓값이 큰 한 줄만 쓴다.
    """
    v = lines.assign(v=lines["thstrm_amount"].astype(float).abs())
    nm = v["account_nm"].fillna("")
    cf = v[(v["sj_div"] == "CF") & (v["account_id"].isin(FX_CF_IDS) | nm.str.contains(FX_CF_NAME))]
    cis = v[(v["sj_div"].isin(["CIS", "IS"])) & (v["account_id"].isin(FX_CIS_IDS) | nm.str.contains(FX_CIS_NAME))
            & ~nm.str.contains("재분류")]
    keys = ["corp_code", "bsns_year", "fs_div"]
    a = cf.groupby(keys)["v"].sum().rename("cf")
    b = cis.groupby(keys)["v"].max().rename("cis")
    out = pd.concat([a, b], axis=1).fillna(0)
    return (out["cf"] + out["cis"]).rename("fx_won").reset_index()


def attach_lines(panel: pd.DataFrame, values: pd.DataFrame, present: pd.DataFrame, col: str) -> pd.Series:
    """패널의 재무제표 기준(연결→CFS, 별도→OFS, 빈칸→CFS 먼저)에 맞는 값을 붙인다.

    그 재무제표가 있는데(present: corp_code, bsns_year, fs_div, sj_div) 해당 줄이 없으면 0, 재무제표 자체가 없으면 빈칸.
    """
    v = values.set_index(["corp_code", "bsns_year", "fs_div"])[col]
    has = set(zip(present["corp_code"], present["bsns_year"], present["fs_div"]))
    out = []
    for corp, year, basis in zip(panel["corp_code"], panel["bsns_year"], panel["fs_basis"]):
        first = BASIS_TO_DIV.get(basis, "CFS")
        val = np.nan
        for div in (first, "OFS" if first == "CFS" else "CFS"):
            if (corp, year, div) in has:
                val = float(v.get((corp, year, div), 0.0))
                break
        out.append(val)
    return pd.Series(out, index=panel.index, name=col)


# ---------------------------------------------------------------- 패널 만들기

def _winsor(s: pd.Series, q: float = WINSOR) -> pd.Series:
    lo, hi = s.quantile([q, 1 - q])
    return s.clip(lo, hi)


def _rank(s: pd.Series, by: pd.Series) -> pd.Series:
    """같은 해 회사끼리 순위를 0~1로. 값이 같으면 평균 순위."""
    r = s.groupby(by).rank(method="average")
    n = s.groupby(by).transform("count")
    return (r - 1) / (n - 1).where(n > 1)


def build_panel(panel: pd.DataFrame, macro_year: pd.DataFrame) -> pd.DataFrame:
    """회사×연도 패널(corp_code, group, bsns_year, ni_owner_won, assets_won, d_won, dps_common_won, borrow_won, fx_won)
    + 연도별 거시(macro_year: 행 = 연도) → 분석용 표. 전년 값은 바로 앞 연도가 있을 때만 붙인다."""
    p = panel.sort_values(["corp_code", "bsns_year"]).copy()
    for c in ["ni_owner_won", "assets_won", "d_won", "dps_common_won", "borrow_won", "fx_won"]:
        p[c] = p[c].astype(float)
    g = p.groupby("corp_code")
    consecutive = (p["bsns_year"] - g["bsns_year"].shift(1)) == 1
    for c in ["ni_owner_won", "assets_won", "d_won", "dps_common_won", "borrow_won", "fx_won"]:
        p[f"{c}_prev"] = g[c].shift(1).where(consecutive)
    p["dir"] = np.sign(p["dps_common_won"] - p["dps_common_won_prev"])
    p["dir_total"] = np.sign(p["d_won"] - p["d_won_prev"])
    a = p["assets_won_prev"].where(p["assets_won_prev"] > 0)
    p["ni_chg_a"] = _winsor((p["ni_owner_won"] - p["ni_owner_won_prev"]) / a)
    p["ni_a"] = _winsor(p["ni_owner_won"] / a)
    p["d_prev_a"] = _winsor(p["d_won_prev"] / a)
    p["rate_exp_raw"] = p["borrow_won_prev"] / a
    p["fx_exp_raw"] = p["fx_won_prev"] / a
    p["rate_exp"] = _rank(p["rate_exp_raw"], p["bsns_year"])
    p["fx_exp"] = _rank(p["fx_exp_raw"], p["bsns_year"])
    m = macro_year
    for col in ["base_rate_chg", "ktb3y_chg", "usdkrw_growth"]:
        p[col] = p["bsns_year"].map(m[col])
        p[f"{col}_prev"] = p["bsns_year"].map(m[col].set_axis(m.index + 1))
        p[f"{col}_next"] = p["bsns_year"].map(m[col].set_axis(m.index - 1))
    return p


# ---------------------------------------------------------------- 고정효과 회귀

def demean(m: np.ndarray, groups: list[np.ndarray], tol: float = 1e-10, max_iter: int = 1000) -> np.ndarray:
    """여러 묶음(회사, 연도 …)의 평균을 번갈아 빼서 고정효과를 없앤다(불균형 패널도 됨)."""
    m = np.array(m, dtype=float, copy=True)
    if m.ndim == 1:
        m = m[:, None]
    counts = [np.bincount(gr) for gr in groups]
    for _ in range(max_iter):
        before = m.copy()
        for gr, cnt in zip(groups, counts):
            for j in range(m.shape[1]):
                m[:, j] -= (np.bincount(gr, weights=m[:, j], minlength=len(cnt)) / np.maximum(cnt, 1))[gr]
        if np.max(np.abs(m - before)) < tol * (1 + np.max(np.abs(m))):
            break
    return m


def _codes(s: pd.Series) -> np.ndarray:
    return pd.factorize(s)[0]


@dataclass(frozen=True)
class Fit:
    name: str          # 검정 이름
    outcome: str
    exposure: str
    macro: str
    coef: float        # 노출도 × 경기 변화 계수
    se: float          # 회사 단위 묶음 표준오차
    p_cluster: float   # 정규 근사
    p_perm: float | None
    n: int
    n_firms: int
    n_years: int
    exp_coef: float    # 노출도 자체 계수

    @property
    def low(self) -> float:
        return self.coef - 1.96 * self.se

    @property
    def high(self) -> float:
        return self.coef + 1.96 * self.se


def fit(df: pd.DataFrame, outcome: str, exposure: str, macro: str, name: str = "",
        fe: tuple[str, ...] = ("corp_code", "bsns_year"), n_perm: int = N_PERM, seed: int = SEED) -> Fit:
    """outcome ~ 노출도×경기 + 노출도 + 통제 + 고정효과. 계수는 FWL(나머지를 먼저 빼고 남은 부분끼리 회귀)로 구한다."""
    cols = [outcome, exposure, macro, *CONTROLS, *fe]
    d = df.dropna(subset=cols).reset_index(drop=True)
    groups = [_codes(d[c]) for c in fe]
    inter = (d[exposure] * d[macro]).to_numpy()
    others = d[[exposure, *CONTROLS]].to_numpy(float)
    y = d[outcome].to_numpy(float)
    yt, zt, it = demean(y, groups)[:, 0], demean(others, groups), demean(inter, groups)[:, 0]
    x = np.column_stack([it, zt])
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ yt
    u = yt - x @ beta
    firm = _codes(d["corp_code"])
    n_g = firm.max() + 1
    score = np.zeros((n_g, x.shape[1]))
    np.add.at(score, firm, x * u[:, None])
    n, k = x.shape
    scale = n_g / (n_g - 1) * (n - 1) / (n - k)
    v = xtx_inv @ (score.T @ score) @ xtx_inv * scale
    se = float(math.sqrt(v[0, 0]))
    coef = float(beta[0])
    p_perm = perm_p(d, exposure, macro, yt, zt, groups, coef, n_perm, seed) if n_perm else None
    return Fit(name, outcome, exposure, macro, coef, se, math.erfc(abs(coef / se) / math.sqrt(2)), p_perm,
               n, int(n_g), int(d["bsns_year"].nunique()), float(beta[1]))


def perm_p(d: pd.DataFrame, exposure: str, macro: str, yt: np.ndarray, zt: np.ndarray, groups: list[np.ndarray],
           coef: float, n_perm: int, seed: int) -> float:
    """경기 값을 연도끼리 섞어(어느 해의 경기 변화를 어느 해에 붙일지 무작위) 같은 크기 계수가 나오는 비율."""
    rng = np.random.default_rng(seed)
    years = np.sort(d["bsns_year"].unique())
    by_year = d.groupby("bsns_year")[macro].first().reindex(years).to_numpy()
    yi = np.searchsorted(years, d["bsns_year"].to_numpy())
    e = d[exposure].to_numpy(float)
    proj = np.linalg.pinv(zt)
    y_res = yt - zt @ (proj @ yt)
    hits = 0
    for _ in range(n_perm):
        m = rng.permutation(by_year)[yi]
        it = demean(e * m, groups)[:, 0]
        it = it - zt @ (proj @ it)
        b = float(it @ y_res / (it @ it))
        hits += abs(b) >= abs(coef) - 1e-12
    return (hits + 1) / (n_perm + 1)


def holm(ps: list[float]) -> list[float]:
    """Holm 보정: 작은 p부터 (남은 검정 수)를 곱하고, 앞보다 작아지지 않게 한다."""
    order = np.argsort(ps)
    out = [0.0] * len(ps)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, ps[i] * (len(ps) - rank)))
        out[i] = running
    return out


# ---------------------------------------------------------------- 쉬운 표: 노출도 위·아래 3분의 1의 행동 비율

def tercile_table(df: pd.DataFrame, exposure: str, macro: str, outcome: str = "dir") -> pd.DataFrame:
    """경기 변화가 오른 해·내린 해 × 노출도 아래 3분의 1·위 3분의 1에서 배당을 줄인·올린 회사 비율(%)."""
    d = df.dropna(subset=[exposure, macro, outcome])
    d = d.assign(band=np.where(d[exposure] <= 1 / 3, "적게 받는 회사(아래 1/3)",
                               np.where(d[exposure] >= 2 / 3, "크게 받는 회사(위 1/3)", None)),
                 when=np.where(d[macro] > 0, "오른 해", np.where(d[macro] < 0, "내린 해", None)))
    d = d.dropna(subset=["band", "when"])
    t = d.groupby(["when", "band"])[outcome].agg(
        n="count", cut=lambda s: (s < 0).mean() * 100, up=lambda s: (s > 0).mean() * 100)
    return t.reset_index()


def lintner(df: pd.DataFrame) -> dict:
    """Lintner 부분조정: ΔD/A = a + b·NI/A − c·D_prev/A + 연도 효과. 조정 속도 c, 목표 배당성향 b/c."""
    d = df.dropna(subset=["d_won", "d_won_prev", "ni_a", "d_prev_a", "assets_won_prev"])
    d = d[d["assets_won_prev"] > 0]
    y = _winsor((d["d_won"] - d["d_won_prev"]) / d["assets_won_prev"]).to_numpy()
    x = d[["ni_a", "d_prev_a"]].to_numpy(float)
    groups = [_codes(d["bsns_year"])]
    yt, xt = demean(y, groups)[:, 0], demean(x, groups)
    b, *_ = np.linalg.lstsq(xt, yt, rcond=None)
    speed = -float(b[1])
    return {"b": float(b[0]), "speed": speed, "target_payout": float(b[0]) / speed if speed else float("nan"), "n": len(d)}
