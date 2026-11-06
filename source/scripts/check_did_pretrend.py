"""이중차분(9장 '개인 최대주주 회사 × 2025년')의 평행추세 가정을 숫자로 점검한다. 결과 파일은 만들지 않고 화면에만 찍는다.

실행: .venv/bin/python -m scripts.check_did_pretrend [--url ...]
(값만 필요하면 compute()를 부른다.)

자료와 모형은 source/scripts/analyze_policy_did.py와 똑같다(같은 SQL·같은 prepare·같은 통제·회사와 연도 고정효과·회사 묶음 표준오차).
그 위에서 네 가지를 본다.
  1) 회귀 전 단순 비율: 해마다 '배당을 10% 이상 늘린 회사 비율'의 두 무리 차이(개인 최대주주 회사 − 나머지). 2018~2024 평균·범위와 2025.
  2) 해마다 본 계수(사건연구, 기준 해 2023)를 다시 구하고, 제도 전 6개 계수(2018~2022, 2024)가 모두 0이라는 가정을
     한꺼번에 검정한다(Wald 카이제곱, 회사 묶음 공분산).
  3) 제도 전 2018~2024만 써서 '개인 최대주주 회사 × 연도(직선 추세)' 기울기를 잰다. 기울기가 0과 다르면 두 무리가 원래 다른 속도로 움직였다는 뜻.
  4) 위 직선 추세를 모형에 넣고(개인 최대주주 회사마다 따로 기울기) 2025년 효과가 얼마나 남는지 본다.
DB 값, docs 결과 파일, core.core_behavior_* 표는 고치지 않는다.
"""
import argparse
import math

import numpy as np
import pandas as pd

from core import db
from core import exposure_dividend as ex
from core import policy_did as pd_
from scripts import analyze_exposure_dividend as ae
from scripts import analyze_policy_did as apd

PRE_YEARS = [2018, 2019, 2020, 2021, 2022, 2024]  # 2023은 기준 해(0)


def fe_ols_vcov(d: pd.DataFrame, y: str, xs: list[str]):
    """core.policy_did.fe_ols와 같은 계산(회사·연도 고정효과, CR1)인데 공분산 행렬까지 돌려준다."""
    groups = [pd.factorize(d[c])[0] for c in ("corp_code", "bsns_year")]
    yt = ex.demean(d[y].to_numpy(float), groups)[:, 0]
    xt = ex.demean(d[xs].to_numpy(float), groups)
    keep = np.abs(xt).max(axis=0) > 1e-12
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
    return names, beta, v, n, int(g)


def chi2_sf(x: float, k: int) -> float:
    """카이제곱 오른쪽 꼬리 확률(자유도 k가 짝수일 때 닫힌 식, 홀수면 급수)."""
    if k % 2 == 0:
        s, t = 0.0, 1.0
        for i in range(k // 2):
            t = 1.0 if i == 0 else t * (x / 2) / i
            s += t
        return math.exp(-x / 2) * s
    # 홀수: erfc + 급수
    s = math.erfc(math.sqrt(x / 2))
    t = math.sqrt(2 * x / math.pi) * math.exp(-x / 2)
    for i in range(1, (k - 1) // 2 + 1):
        s += t
        t *= x / (2 * i + 1)
    return s


def p_norm(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def load(url: str | None = None):
    with db.connect(url) as conn:
        panel = pd.DataFrame(db.fetch_dicts(conn, ae.PANEL_SQL))
        lines = pd.DataFrame(db.fetch_dicts(conn, ae.LINES_SQL, {
            "borrow": ex.BORROW_NAME, "fx_cf": list(ex.FX_CF_IDS), "fx_cf_name": ex.FX_CF_NAME,
            "fx_cis": list(ex.FX_CIS_IDS), "fx_cis_name": ex.FX_CIS_NAME}))
        present = pd.DataFrame(db.fetch_dicts(conn, ae.PRESENT_SQL))
        macro = pd.DataFrame(db.fetch_dicts(conn, ae.MACRO_SQL))
        universe = pd.DataFrame(db.fetch_dicts(conn, apd.UNIVERSE_SQL))
        holders = pd.DataFrame(db.fetch_dicts(conn, apd.HOLDER_SQL))
        valueup = pd.DataFrame(db.fetch_dicts(conn, apd.VALUEUP_SQL, {"announced": apd.ANNOUNCED}))
    panel = panel[panel["corp_code"].isin(universe["corp_code"])]
    base = ae.prepare(panel, lines, present, macro)
    return pd_.add_policy_columns(base, pd_.holder_table(holders), valueup.set_index("corp_code")["first_dt"])


def compute(url: str | None = None) -> dict:
    """네 가지 점검 값을 모아 돌려준다(%p 단위). 데이터 이야기 분석 보고서(source/scripts/report_story_pdf.py)도 이 값을 쓴다."""
    p = load(url)
    controls = pd_.BASE_CONTROLS + pd_.EXPOSURE_CONTROLS

    # 1) 단순 비율 차이
    t = pd_.raw_rates(p, "holder_high")
    w = t.pivot(index="bsns_year", columns="holder_high", values="mean")
    gap = (w[1.0] - w[0.0])
    out = {"gap": {int(k): float(v) for k, v in gap.items()},
           "rate_owner_pre": float(w.loc[2018:2024, 1.0].mean()), "rate_owner_2025": float(w.loc[2025, 1.0]),
           "rate_other_pre": float(w.loc[2018:2024, 0.0].mean()), "rate_other_2025": float(w.loc[2025, 0.0])}

    # 2) 사건연구 + 제도 전 계수 한꺼번에 0 검정
    q = p[p["bsns_year"].between(2018, 2025)].copy()
    cols = []
    for yy in [2018, 2019, 2020, 2021, 2022, 2024, 2025]:
        c = f"t_{yy}"
        q[c] = q["holder_high"] * (q["bsns_year"] == yy)
        cols.append(c)
    d = pd_._sample(q, "up10", ["holder_high", *controls])
    names, beta, v, n, g = fe_ols_vcov(d, "up10", [*cols, *controls])
    idx = [names.index(f"t_{yy}") for yy in PRE_YEARS]
    b = beta[idx]
    vv = v[np.ix_(idx, idx)]
    wald = float(b @ np.linalg.solve(vv, b))
    out |= {"es": {int(nm[2:]): float(beta[names.index(nm)] * 100) for nm in cols}, "wald": wald, "wald_p": chi2_sf(wald, 6),
            "n": n, "firms": g}

    # 3) 제도 전만: 개인 최대주주 회사 × 연도 직선 기울기
    q3 = p[p["bsns_year"].between(2018, 2024)].copy()
    q3["trend"] = q3["holder_high"] * (q3["bsns_year"] - 2021)
    d3 = pd_._sample(q3, "up10", ["holder_high", *controls])
    names3, beta3, v3, n3, g3 = fe_ols_vcov(d3, "up10", ["trend", *controls])
    k = names3.index("trend")
    se3 = math.sqrt(v3[k, k])
    out |= {"slope": float(beta3[k] * 100), "slope_low": float((beta3[k] - 1.96 * se3) * 100),
            "slope_high": float((beta3[k] + 1.96 * se3) * 100), "slope_p": p_norm(beta3[k] / se3), "slope_n": n3}

    # 4) 무리별 직선 추세를 넣은 이중차분
    q4 = p[p["bsns_year"].between(2018, 2025)].copy()
    q4["post"] = (q4["bsns_year"] == 2025).astype(float)
    q4["high_post"] = q4["holder_high"] * q4["post"]
    q4["trend"] = q4["holder_high"] * (q4["bsns_year"] - 2021)
    d4 = pd_._sample(q4, "up10", ["holder_high", *controls])
    for key, xs in [("plain", ["high_post", *controls]), ("trend", ["high_post", "trend", *controls])]:
        nm4, b4, v4, n4, _ = fe_ols_vcov(d4, "up10", xs)
        j = nm4.index("high_post")
        se4 = math.sqrt(v4[j, j])
        out[f"did_{key}"] = {"coef": float(b4[j] * 100), "low": float((b4[j] - 1.96 * se4) * 100),
                             "high": float((b4[j] + 1.96 * se4) * 100), "p": p_norm(b4[j] / se4), "n": n4}
    return out


def main(url: str | None = None) -> None:
    r = compute(url)
    gap = r["gap"]
    pre = pd.Series({y: v for y, v in gap.items() if y <= 2024})
    print("1) 단순 비율 차이(개인 최대주주 회사 − 나머지, %p):", {y: round(v, 1) for y, v in gap.items()})
    print(f"   2018~2024 평균 {pre.mean():.1f} · 범위 {pre.min():.1f} ~ {pre.max():.1f} · 표준편차 {pre.std(ddof=1):.1f} · 2025 {gap[2025]:.1f}"
          f" · 2025 − 제도 전 평균 = {gap[2025] - pre.mean():.1f}")
    print(f"   개인 최대주주 회사 2018~2024 평균 비율 {r['rate_owner_pre']:.1f}% → 2025 {r['rate_owner_2025']:.1f}%;"
          f" 나머지 {r['rate_other_pre']:.1f}% → {r['rate_other_2025']:.1f}%")
    pre_es = [v for y, v in r["es"].items() if y in PRE_YEARS]
    print("2) 사건연구 계수(%p, 기준 2023):", {f"t_{y}": round(v, 1) for y, v in r["es"].items()})
    print(f"   제도 전 6개 계수가 모두 0인지: Wald 카이제곱 = {r['wald']:.2f}, 자유도 6, p = {r['wald_p']:.3f} (회사·연도 {r['n']:,}, 회사 {r['firms']:,})")
    print(f"   제도 전 6개 계수 평균 {sum(pre_es) / len(pre_es):.1f}%p")
    print(f"3) 제도 전(2018~2024) 개인 최대주주 회사 추가 기울기 = {r['slope']:+.2f}%p/년 (95% {r['slope_low']:.2f} ~ {r['slope_high']:.2f}),"
          f" p = {r['slope_p']:.3f} (회사·연도 {r['slope_n']:,})")
    for key, label in [("plain", "추세 없이(원래 모형)"), ("trend", "개인 최대주주 회사 직선 추세 넣고")]:
        d = r[f"did_{key}"]
        print(f"4) {label}: 2025 효과 {d['coef']:+.1f}%p (95% {d['low']:.1f} ~ {d['high']:.1f}), 묶음 p = {d['p']:.4f}, n = {d['n']:,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    main(ap.parse_args().url)
