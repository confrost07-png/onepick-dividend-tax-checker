"""배당과 거시지표의 상관 (사업연도 단위).

거시지표(raw.ecos_macro)를 달력 연도로 모으고, 배당(core.v_dividend_year_verified·raw.dart_dividend_item)을 연도별로 모아
두 갈래로 상관을 본다.
  ① 연도 집계: 배당 지표 9개 연도(2017~2025) × 그 해 거시지표. 점이 9개뿐이라 참고용.
  ② 회사×연도: 회사마다 주당배당금의 전년 대비 변화 × 그 해 거시지표의 전년 대비 변화.
     거시지표는 모든 회사에 같은 값이라, 실제로 움직이는 값은 연도 수(8개)만큼이다.
p값은 순열검정(값을 섞어 같은 크기 상관이 우연히 나올 비율)으로 구한다. 정규분포 가정을 두지 않는다.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

# 거시지표 연 단위: (열 이름, 원천 지표, 모으는 법, 사람이 읽는 이름, 단위)
ANNUAL = [
    ("current_account", "current_account_m", "sum", "경상수지 연간 합계", "백만달러"),
    ("base_rate", "base_rate_m", "mean", "기준금리 연평균", "%"),
    ("ktb3y", "ktb3y_m", "mean", "국고채 3년 연평균", "%"),
    ("usdkrw", "usdkrw_m", "mean", "원/달러 연평균", "원"),
    ("gdp_real", "gdp_real_level_q", "sum", "실질 GDP(4개 분기 합)", "십억원"),
    ("cpi", "cpi_m", "mean", "CPI 연평균", "2020=100"),
    ("unemployment", "unemployment_rate_m", "mean", "실업률 연평균", "%"),
    ("employment", "employment_rate_m", "mean", "고용률 연평균", "%"),
]
# 상관에 쓰는 거시 변수: (열 이름, 사람이 읽는 이름). *_growth는 전년 대비 %, *_chg는 전년 대비 %p 차이
MACRO_VARS = [
    ("current_account", "경상수지(연간, 백만달러)"),
    ("base_rate", "기준금리(연평균 %)"),
    ("ktb3y", "국고채 3년(연평균 %)"),
    ("usdkrw", "원/달러(연평균)"),
    ("gdp_growth", "실질 GDP 성장률(%)"),
    ("cpi_growth", "물가상승률(%)"),
    ("unemployment", "실업률(연평균 %)"),
    ("employment", "고용률(연평균 %)"),
]
PANEL_VARS = [
    ("current_account_chg", "경상수지 증감(백만달러)"),
    ("base_rate_chg", "기준금리 변화(%p)"),
    ("ktb3y_chg", "국고채 3년 변화(%p)"),
    ("usdkrw_growth", "원/달러 변화율(%)"),
    ("gdp_growth", "실질 GDP 성장률(%)"),
    ("cpi_growth", "물가상승률(%)"),
    ("unemployment_chg", "실업률 변화(%p)"),
    ("employment_chg", "고용률 변화(%p)"),
]
PERIODS_PER_YEAR = {"M": 12, "Q": 4}
SAMSUNG = "00126380"  # 삼성전자: 배당총액의 약 1/3, 2020 특별배당


def macro_annual(macro: pd.DataFrame) -> pd.DataFrame:
    """raw.ecos_macro 행(series, cycle, period_start, value) → 연도×거시지표. 열두 달(네 분기)이 다 있는 해만 남긴다."""
    return macro_window(macro, range(1, 13))


def macro_window(macro: pd.DataFrame, months: range) -> pd.DataFrame:
    """연도마다 months에 든 달(분기 자료는 첫 달이 months에 든 분기)만 모은다. 그 기간 자료가 다 있는 해만 남긴다.

    성장률·변화는 전년의 같은 기간과 비교한다 (예: 1~3월이면 올해 1분기 vs 작년 1분기).
    """
    start = pd.to_datetime(macro["period_start"])
    df = macro.assign(year=start.dt.year, month=start.dt.month, value=macro["value"].astype(float))
    df = df[df["month"].isin(months)]
    cols = {}
    for name, series, how, _, _ in ANNUAL:
        s = df[df["series"] == series]
        need = len(months) if s["cycle"].iloc[0] == "M" else sum(1 for m in months if m % 3 == 1)
        g = s.groupby("year")["value"]
        cols[name] = g.agg(how)[g.count() == need]
    out = pd.DataFrame(cols).sort_index()
    out = out.reindex(range(out.index.min(), out.index.max() + 1))  # 빠진 해가 있어도 전년 비교가 어긋나지 않게
    out["gdp_growth"] = out["gdp_real"].pct_change() * 100
    out["cpi_growth"] = out["cpi"].pct_change() * 100
    out["usdkrw_growth"] = out["usdkrw"].pct_change() * 100
    for c in ["current_account", "base_rate", "ktb3y", "unemployment", "employment"]:
        out[f"{c}_chg"] = out[c].diff()
    out.index.name = "year"
    return out


LAGS = [
    ("same", "같은 해 (Y년 1~12월)"),
    ("prev", "1년 전 (Y−1년 1~12월)"),
    ("decision", "결의 시점 (Y+1년 1~3월)"),
]


def macro_lagged(macro: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """사업연도 Y에 붙일 거시 값을 시차별로. 행 번호(year)는 모두 배당의 사업연도 Y."""
    annual = macro_annual(macro)
    q1 = macro_window(macro, range(1, 4))
    return {
        "same": annual,
        "prev": annual.set_axis(annual.index + 1),
        "decision": q1.set_axis(q1.index - 1),
    }


def dividend_annual(div: pd.DataFrame, yields: pd.DataFrame, exclude: set[tuple[str, int]] = frozenset()) -> pd.DataFrame:
    """회사×연도 배당(corp_code, bsns_year, d_dart_won, dps_common_won)과 시가배당률(corp_code, bsns_year, yield_pct) → 연도별 지표.

    exclude: 배당총액 합계에서만 뺄 (corp_code, bsns_year). 원천 오류로 보이는 값.
    """
    d = div.copy()
    d["d_dart_won"] = d["d_dart_won"].astype(float)
    d["dps_common_won"] = d["dps_common_won"].astype(float)
    total = d[~d.apply(lambda r: (r["corp_code"], r["bsns_year"]) in exclude, axis=1)]
    g = d.groupby("bsns_year")
    out = pd.DataFrame({
        "companies": g["d_dart_won"].count(),
        "payer_share": g["d_dart_won"].apply(lambda s: (s.dropna() > 0).mean() * 100),
        "total_tril": total.groupby("bsns_year")["d_dart_won"].sum() / 1e12,
        "total_ex_samsung_tril": total[total["corp_code"] != SAMSUNG].groupby("bsns_year")["d_dart_won"].sum() / 1e12,
    })
    p = panel(d)
    pg = p.groupby("bsns_year")
    out["dps_growth_median"] = pg["dps_growth"].median()
    out["dps_up_share"] = pg["dps_change"].apply(lambda s: (s > 0).mean() * 100)
    out["dps_cut_share"] = pg["dps_change"].apply(lambda s: (s < 0).mean() * 100)
    out["yield_median"] = yields.assign(y=yields["yield_pct"].astype(float)).groupby("bsns_year")["y"].median()
    out.index.name = "year"
    return out


DIV_VARS = [
    ("payer_share", "배당한 회사 비율(%)"),
    ("total_tril", "현금배당총액(조 원)"),
    ("total_ex_samsung_tril", "현금배당총액(삼성전자 제외, 조 원)"),
    ("dps_growth_median", "주당배당금 증가율 중앙값(%)"),
    ("dps_up_share", "주당배당금 올린 회사 비율(%)"),
    ("dps_cut_share", "주당배당금 줄인 회사 비율(%)"),
    ("yield_median", "시가배당률 중앙값(%)"),
]


def panel(div: pd.DataFrame) -> pd.DataFrame:
    """회사×연도 주당배당금 전년 대비 변화. dps_change: 증감(원), dps_growth: 두 해 모두 배당한 회사의 증가율(%)."""
    d = div.sort_values(["corp_code", "bsns_year"])[["corp_code", "bsns_year", "dps_common_won"]].copy()
    d["dps"] = d["dps_common_won"].astype(float)
    prev = d.groupby("corp_code")["dps"].shift()
    gap = d["bsns_year"] - d.groupby("corp_code")["bsns_year"].shift()
    d["dps_change"] = (d["dps"] - prev).where(gap == 1)
    d["dps_growth"] = ((d["dps"] / prev - 1) * 100).where((gap == 1) & (prev > 0) & (d["dps"] > 0))
    return d.dropna(subset=["dps_change"])[["corp_code", "bsns_year", "dps", "dps_change", "dps_growth"]]


def _rank(a: np.ndarray) -> np.ndarray:
    return pd.Series(a).rank().to_numpy()


def corr(x, y, method: str = "spearman", n_perm: int = 20000, seed: int = 0) -> dict:
    """상관계수와 순열검정 p값(양쪽). 빈 값이 있는 짝은 뺀다."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 3 or x.std() == 0 or y.std() == 0:
        return {"n": n, "r": np.nan, "p": np.nan}
    if method == "spearman":
        x, y = _rank(x), _rank(y)
    r = float(np.corrcoef(x, y)[0, 1])
    rng = np.random.default_rng(seed)
    perm = np.array([np.corrcoef(x, rng.permutation(y))[0, 1] for _ in range(n_perm)])
    p = float((np.sum(np.abs(perm) >= abs(r) - 1e-12) + 1) / (n_perm + 1))
    return {"n": n, "r": r, "p": p}


def year_table(div_year: pd.DataFrame, macro_year: pd.DataFrame, years: range) -> pd.DataFrame:
    """① 연도 집계: 배당 지표 × 거시 변수 상관 (Pearson·Spearman)."""
    j = div_year.join(macro_year, how="inner").loc[lambda t: t.index.isin(years)]
    rows = []
    for dv, dlabel in DIV_VARS:
        for mv, mlabel in MACRO_VARS:
            pe, sp = corr(j[dv], j[mv], "pearson"), corr(j[dv], j[mv], "spearman")
            rows.append({"dividend": dv, "dividend_label": dlabel, "macro": mv, "macro_label": mlabel, "n": sp["n"],
                         "pearson": pe["r"], "pearson_p": pe["p"], "spearman": sp["r"], "spearman_p": sp["p"]})
    return pd.DataFrame(rows)


def diff_table(div_year: pd.DataFrame, macro_year: pd.DataFrame, years: range) -> pd.DataFrame:
    """① 추세 제거: 배당 지표와 거시 변수 모두 전년 대비 차이로 바꿔 상관 (n=연도 수-1).

    두 값이 함께 꾸준히 오르기만 해도 수준끼리는 상관이 크게 나온다. 차이끼리 보면 그 몫이 빠진다.
    """
    j = div_year.join(macro_year[[m for m, _ in MACRO_VARS]], how="inner").loc[lambda t: t.index.isin(years)]
    d = j.sort_index().diff().iloc[1:]
    rows = []
    for dv, dlabel in DIV_VARS:
        for mv, mlabel in MACRO_VARS:
            sp = corr(d[dv], d[mv], "spearman")
            rows.append({"dividend": dv, "dividend_label": dlabel, "macro": mv, "macro_label": mlabel,
                         "n": sp["n"], "spearman": sp["r"], "spearman_p": sp["p"]})
    return pd.DataFrame(rows)


def panel_table(p: pd.DataFrame, macro_year: pd.DataFrame, n_perm: int = 2000) -> pd.DataFrame:
    """② 회사×연도: 주당배당금 증가율(두 해 모두 배당) · 올림 여부 × 그 해 거시 변화.

    p값은 연도 단위로 섞는다: 회사들은 같은 해 거시 값을 함께 받으므로 행 단위로 섞으면 p값이 지나치게 작아진다.
    """
    j = p.join(macro_year, on="bsns_year", how="inner")
    j["dps_up"] = (j["dps_change"] > 0).astype(float)
    years = np.sort(j["bsns_year"].unique())
    rng = np.random.default_rng(0)
    rows = []
    for target, tlabel in [("dps_growth", "주당배당금 증가율(%)"), ("dps_up", "주당배당금 올림(1/0)")]:
        t = j.dropna(subset=[target])
        for mv, mlabel in PANEL_VARS:
            t2 = t.dropna(subset=[mv])
            r = _spearman(t2[target], t2[mv])
            by_year = macro_year[mv].reindex(years).to_numpy()
            idx = np.searchsorted(years, t2["bsns_year"].to_numpy())
            perm = []
            for _ in range(n_perm):
                shuffled = rng.permutation(by_year)
                perm.append(_spearman(t2[target], shuffled[idx]))
            perm = np.array(perm)
            pval = float((np.sum(np.abs(perm) >= abs(r) - 1e-12) + 1) / (n_perm + 1))
            rows.append({"target": target, "target_label": tlabel, "macro": mv, "macro_label": mlabel,
                         "rows": len(t2), "companies": t2["corp_code"].nunique(), "years": t2["bsns_year"].nunique(),
                         "spearman": r, "p_by_year": pval})
    return pd.DataFrame(rows)


def _spearman(a, b) -> float:
    a, b = pd.Series(np.asarray(a, float)).rank(), pd.Series(np.asarray(b, float)).rank()
    return float(np.corrcoef(a, b)[0, 1])


# 화면용 짧은 이름. 화면에는 회사 이름을 쓰지 않는다(삼성전자는 2017~2025 해마다 배당총액 1위라 '가장 큰 1곳'). 회사×연도 갈래의 거시 변수(*_chg·*_growth)도 같은 이름으로 보인다
MACRO_SHORT = {"current_account": "경상수지", "base_rate": "기준금리", "ktb3y": "국고채 3년 금리", "usdkrw": "원/달러 환율",
               "gdp": "GDP 성장률", "cpi": "물가상승률", "unemployment": "실업률", "employment": "고용률"}
DIVIDEND_SHORT = {"payer_share": "배당한 회사 비율", "total_tril": "배당총액", "total_ex_samsung_tril": "배당총액(가장 큰 1곳 제외)",
                  "dps_growth_median": "주당배당금 증가율 중앙값", "dps_up_share": "주당배당금을 올린 회사 비율",
                  "dps_cut_share": "주당배당금을 줄인 회사 비율", "yield_median": "시가배당률 중앙값",
                  "dps_growth": "주당배당금 증가율", "dps_up": "주당배당금을 올렸나(1/0)"}


def macro_short(key: str) -> str:
    base = key.split("_")[0] if key.startswith(("gdp", "cpi")) else key.removesuffix("_chg").removesuffix("_growth")
    return MACRO_SHORT.get(base, key)


def year_rows(t: pd.DataFrame) -> list[dict]:
    """연도표(행=연도, 열=항목) → core.core_macro_dividend_year 행. 빈 값은 NULL."""
    return [{"year": int(y), "item": c, "value": None if pd.isna(v) else float(v)}
            for y, row in t.iterrows() for c, v in row.items()]


def corr_rows(t: pd.DataFrame) -> list[dict]:
    """scripts.analyze_macro_dividend.lag_tables 결과 → core.core_macro_dividend_corr 행."""
    def val(v, cast):
        return None if pd.isna(v) else cast(v)
    return [{"lag": r["lag"], "kind": r["kind"], "dividend": r["dividend"], "macro": r["macro"],
             "dividend_label": r["dividend_label"], "macro_label": r["macro_label"],
             "n": val(r["n"], int), "rows": val(r["rows"], int),
             "spearman": val(r["spearman"], float), "p": val(r["spearman_p"], float)} for _, r in t.iterrows()]


@dataclass(frozen=True)
class MacroResults:
    year: pd.DataFrame   # 행=사업연도, 열=항목 (payer_share, dps_up_share, current_account_chg 등)
    corr: pd.DataFrame   # lag, kind, dividend, macro, dividend_label, macro_label, n, rows, spearman, p
    built_at: str


def load(url: str | None = None) -> MacroResults | None:
    """화면용: 저장해 둔 결과만 읽는다. 표가 없거나 비었으면 None."""
    from core import db
    try:
        with db.connect(url) as conn:
            year = db.fetch_dicts(conn, "SELECT year, item, value FROM core.core_macro_dividend_year")
            corr = db.fetch_dicts(conn, "SELECT * FROM core.core_macro_dividend_corr")
    except Exception:  # noqa: BLE001 DB·표가 없으면 화면은 안내만
        return None
    if not year or not corr:
        return None
    y = pd.DataFrame(year).pivot(index="year", columns="item", values="value").sort_index()
    c = pd.DataFrame(corr)
    built = max(r["built_at"] for r in corr).strftime("%Y-%m-%d")
    return MacroResults(y, c.drop(columns=["built_at"]), built)
