"""이벤트 스터디 결과가 우연인지 본다 (core.core_event_car, 2025년까지 공시). scipy 없이 표준 라이브러리·numpy로 계산.

실행: .venv/bin/python -m scripts.event_significance [--url ...]
1) 0과 다른가: 부호 검정(양수 비율, 정확 이항) + 중앙값 부트스트랩 95% 구간(5,000번, 씨앗 0)
2) 두 묶음이 다른가: 주당배당금 증가 vs 유지·감소, 만-위트니 U(정규 근사, 동점 보정 없음)
3) 크기와 관련 있나: 주당배당금 변화율(%) ↔ CAR 스피어만 순위 상관(t 근사로 p값)
여러 조합을 한꺼번에 보므로 p < 0.05가 몇 개 나오는 것만으로는 근거가 약하다(다중 비교). 결과에 함께 적는다.
"""
import argparse
import math
from datetime import date

import numpy as np
import pandas as pd

from core import db
from core.event_study import VERIFIED, period_of

RNG = np.random.default_rng(0)


def sign_test(x: np.ndarray) -> float:
    """양쪽 정확 이항 p값 (0은 뺌)."""
    x = x[x != 0]
    n, k = len(x), int((x > 0).sum())
    if n == 0:
        return float("nan")
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def boot_median_ci(x: np.ndarray, b: int = 5000) -> tuple[float, float]:
    meds = np.median(RNG.choice(x, size=(b, len(x)), replace=True), axis=1)
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def _norm_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def mann_whitney(a: np.ndarray, b: np.ndarray) -> float:
    ranks = pd.Series(np.concatenate([a, b])).rank().to_numpy()
    u = ranks[: len(a)].sum() - len(a) * (len(a) + 1) / 2
    mu, sd = len(a) * len(b) / 2, math.sqrt(len(a) * len(b) * (len(a) + len(b) + 1) / 12)
    return _norm_p((u - mu) / sd)


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    r = float(pd.Series(x).rank().corr(pd.Series(y).rank()))
    n = len(x)
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return r, _norm_p(t)  # n이 커서 t ≈ 정규


def main(url: str):
    with db.connect(url) as conn:
        car = pd.DataFrame(db.fetch_dicts(conn, """SELECT kind, basis, window_days, rcept_no, corp_code, disclosed_on,
                                                  car, car_total, overlap_capital FROM core.core_event_car WHERE status = '산출'"""))
        dec = pd.DataFrame(db.fetch_dicts(conn, """SELECT rcept_no, corp_code, attributed_year, dps_common_won, disclosed_on
                                                  FROM raw.dividend_decision WHERE div_kind = '결산배당' AND dps_common_won IS NOT NULL"""))
    car = car[car["disclosed_on"].map(lambda d: period_of(d if isinstance(d, date) else date.fromisoformat(str(d)))) == VERIFIED]

    print("## 1) 누적 초과수익률이 0과 다른가 (중앙값 %p, 95% 구간, 양수 비율, 부호 검정 p)")
    rows = []
    for (kind, basis, w), g in car.groupby(["kind", "basis", "window_days"]):
        for ret, col in (("주가만", "car"), ("배당 포함", "car_total")):
            x = g[col].dropna().to_numpy() * 100
            if len(x) < 10 or (ret == "배당 포함" and np.allclose(g["car"].to_numpy(), g["car_total"].fillna(g["car"]).to_numpy())):
                continue
            lo, hi = boot_median_ci(x)
            rows.append({"공시 종류": kind, "기준일": basis, "창": w, "수익률": ret, "사례": len(x),
                         "중앙값": round(float(np.median(x)), 2), "95% 구간": f"{lo:+.2f} ~ {hi:+.2f}",
                         "양수 비율": f"{(x > 0).mean() * 100:.0f}%", "p": round(sign_test(x), 4),
                         "0 포함 안 함": "예" if lo > 0 or hi < 0 else ""})
    t1 = pd.DataFrame(rows)
    print(t1.to_string(index=False))

    print("\n## 2) 주당배당금 증가 vs 유지·감소 차이 (만-위트니 p)")
    rows = []
    for (basis, w), g in car[car["kind"].str.startswith("주당배당금")].groupby(["basis", "window_days"]):
        for col in ("car", "car_total"):
            a = g[g["kind"] == "주당배당금 증가"][col].dropna().to_numpy()
            b = g[g["kind"] == "주당배당금 유지·감소"][col].dropna().to_numpy()
            rows.append({"기준일": basis, "창": w, "수익률": "주가만" if col == "car" else "배당 포함",
                         "증가 중앙값": round(np.median(a) * 100, 2), "유지·감소 중앙값": round(np.median(b) * 100, 2),
                         "차이": round((np.median(a) - np.median(b)) * 100, 2), "p": round(mann_whitney(a, b), 4)})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n## 3) 주당배당금 변화율(%)과 CAR의 순위 상관 (스피어만 ρ, p)")
    dec["disclosed_on"] = dec["disclosed_on"].astype(str)
    last = dec.sort_values("rcept_no").groupby(["corp_code", "attributed_year"]).last().reset_index()
    prev = last.set_index(["corp_code", "attributed_year"])["dps_common_won"]
    first = dec.sort_values(["disclosed_on", "rcept_no"]).groupby(["corp_code", "attributed_year"]).first().reset_index()
    change = {}
    for r in first.itertuples():
        p0 = prev.get((r.corp_code, r.attributed_year - 1))
        now = prev.get((r.corp_code, r.attributed_year))
        if p0 and now is not None and float(p0) > 0:
            change[r.rcept_no] = (float(now) / float(p0) - 1) * 100
    rows = []
    d = car[car["kind"].str.startswith("주당배당금")].copy()
    d["chg"] = d["rcept_no"].map(change)
    for (basis, w), g in d.dropna(subset=["chg"]).groupby(["basis", "window_days"]):
        for col in ("car", "car_total"):
            r, p = spearman(g["chg"].to_numpy(), g[col].to_numpy())
            rows.append({"기준일": basis, "창": w, "수익률": "주가만" if col == "car" else "배당 포함", "사례": len(g),
                         "ρ": round(r, 3), "p": round(p, 4)})
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\n비교한 조합 수: 1) {len(t1)}개 → p < 0.05가 우연히 나올 기대 개수 약 {len(t1) * 0.05:.1f}개")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="이벤트 스터디 결과의 통계적 유의성")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    main(ap.parse_args().url)
