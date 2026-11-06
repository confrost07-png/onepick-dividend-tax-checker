"""회사 이익 변화와 주당배당금 변화가 같이 움직였는지 → data/processed/analysis/profit_dividend.json.

실행: .venv/bin/python -m scripts.analyze_profit_dividend [--perm 5000] [--url ...]
- 8장 '경기와 배당'과 같은 Spearman 순위 상관. 대상은 고배당기업 638곳의 2018~2025 회사·연도.
- 회사마다: p값은 같은 해 안에서만 이익 값을 섞는 순열검정. 그해 모두가 함께 겪은 분위기는 그대로 두고 회사끼리의 짝만 깬다.
- 해마다 모은 값(점 8개)도 같이 재서, 8장 경기 분석과 같은 모양으로 견줄 수 있게 둔다.
- 2025는 2025년 숫자로 고른 명단이라, 2025를 뺀 값도 같이 둔다.
데이터 이야기 8장이 읽는다.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from core import db, macro_dividend as md
from scripts.analyze_macro_dividend import DIV_SQL

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "analysis" / "profit_dividend.json"
FIN_SQL = "SELECT corp_code, bsns_year, ni_owner_won FROM core.v_financial_year_verified WHERE bsns_year BETWEEN 2016 AND 2025"
YEARS = (2018, 2025)
PAIRS = [  # (이익 쪽, 배당 쪽, 화면 이름)
    ("ni_change", "dps_change", "순이익 증감 ↔ 주당배당금 증감"),
    ("ni_growth", "dps_growth", "순이익 증가율 ↔ 주당배당금 증가율 (두 해 모두 흑자·배당)"),
    ("ni_change", "dps_up", "순이익 증감 ↔ 주당배당금을 올렸나"),
    ("ni_change_prev", "dps_change", "1년 전 순이익 증감 ↔ 주당배당금 증감"),
]


def profit_panel(fin: pd.DataFrame) -> pd.DataFrame:
    """회사×연도 지배주주 순이익 전년 대비 증감·증가율과 1년 전 증감."""
    f = fin.sort_values(["corp_code", "bsns_year"]).copy()
    f["ni"] = f["ni_owner_won"].astype(float)
    prev = f.groupby("corp_code")["ni"].shift()
    gap = f["bsns_year"] - f.groupby("corp_code")["bsns_year"].shift()
    f["ni_change"] = (f["ni"] - prev).where(gap == 1)
    f["ni_growth"] = ((f["ni"] / prev - 1) * 100).where((gap == 1) & (prev > 0) & (f["ni"] > 0))
    f["ni_change_prev"] = f.groupby("corp_code")["ni_change"].shift().where(gap == 1)
    return f[["corp_code", "bsns_year", "ni_change", "ni_growth", "ni_change_prev"]]


def rank_corr(a, b) -> float:
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


def within_year_perm(t: pd.DataFrame, x: str, y: str, n_perm: int, rng) -> dict:
    t = t.sort_values("bsns_year")
    xs, ys = t[x].to_numpy(), t[y].to_numpy()
    r = rank_corr(xs, ys)
    bounds = np.flatnonzero(np.diff(t["bsns_year"].to_numpy())) + 1
    slices = np.split(np.arange(len(t)), bounds)
    hits = 0
    for _ in range(n_perm):
        s = np.concatenate([rng.permutation(xs[ix]) for ix in slices])
        hits += abs(rank_corr(s, ys)) >= abs(r) - 1e-12
    return {"r": round(r, 4), "p": (hits + 1) / (n_perm + 1), "rows": len(t), "companies": int(t["corp_code"].nunique())}


def analyze(div: pd.DataFrame, fin: pd.DataFrame, n_perm: int) -> dict:
    j = md.panel(div).merge(profit_panel(fin), on=["corp_code", "bsns_year"])
    j = j[j["bsns_year"].between(*YEARS)].copy()
    j["dps_up"] = (j["dps_change"] > 0).astype(float)
    j["dps_cut"] = (j["dps_change"] < 0).astype(float)
    rng = np.random.default_rng(0)

    def pairs(d: pd.DataFrame) -> list[dict]:
        return [{"profit": x, "dividend": y, "name": name, **within_year_perm(d.dropna(subset=[x, y]), x, y, n_perm, rng)}
                for x, y, name in PAIRS]

    def updown(d: pd.DataFrame) -> list[list]:
        d = d.dropna(subset=["ni_change"])
        return [[k, len(g), round(g["dps_up"].mean() * 100, 1), round(g["dps_cut"].mean() * 100, 1)]
                for k, g in (("이익이 늘었을 때", d[d["ni_change"] > 0]), ("이익이 줄었을 때", d[d["ni_change"] < 0]))]

    ex = j[j["bsns_year"] < YEARS[1]]
    by_year = []
    for yr, g in j.dropna(subset=["ni_change"]).groupby("bsns_year"):
        a, b = g[g["ni_change"] > 0], g[g["ni_change"] < 0]
        by_year.append([int(yr), round(a["dps_up"].mean() * 100, 1), len(a), round(b["dps_up"].mean() * 100, 1), len(b)])
    yr = j.groupby("bsns_year").agg(ni_up=("ni_change", lambda s: (s.dropna() > 0).mean() * 100), dps_up=("dps_up", "mean"))
    agg = md.corr(yr["ni_up"], yr["dps_up"] * 100, "spearman")
    return {
        "built": date.today().isoformat(), "years": list(YEARS), "n_perm": n_perm,
        "firm": pairs(j), "firm_ex_last": pairs(ex),
        "updown": updown(j), "updown_ex_last": updown(ex),
        "by_year": by_year,  # 사업연도, 이익 는 회사 중 올린 비율, 그 수, 이익 준 회사 중 올린 비율, 그 수
        "year_agg": {"name": "이익이 는 회사 비율 ↔ 주당배당금을 올린 회사 비율 (해마다)", "r": round(agg["r"], 4), "p": agg["p"], "n": agg["n"]},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="회사 이익 변화와 배당 변화의 상관")
    ap.add_argument("--perm", type=int, default=5000)
    ap.add_argument("--url", default=db.database_url())
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        div = pd.DataFrame(db.fetch_dicts(conn, DIV_SQL))
        fin = pd.DataFrame(db.fetch_dicts(conn, FIN_SQL))
    res = analyze(div, fin, a.perm)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
