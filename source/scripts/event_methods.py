"""이벤트 스터디를 여러 통계 방법으로 다시 계산해 결론이 같은지 본다 → report/분석/이벤트스터디_방법별_결과.md.

실행: .venv/bin/python -m scripts.event_methods [--url ...]   (scripts.build_events를 먼저 돌려야 함)
방법은 source/core/event_stats.py. 대상은 core.core_event_car의 산출 사례 중 2025년까지 공시.
주 분석(미리 정함): 배당 결정 · 공시일 · 배당 포함 · 60거래일 · 시장모형 · Kolari–Pynnönen 보정 BMP.
나머지는 강건성 확인이며, 'CAR이 0과 다른가'의 p값은 모든 묶음에 걸쳐 Benjamini–Hochberg로 보정한다.
"""
import argparse
import json
import math
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from core import db
from core import event_stats as st
from core import event_study as es
from scripts.build_events import MARKET_NAMES, _wide

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "이벤트스터디_방법별_결과.md"
# 새 화면(source/api/data.py)이 읽는 같은 결과의 JSON판
OUT_JSON = Path(__file__).resolve().parents[2] / "data" / "processed" / "analysis" / "event_methods.json"
MODELS = ("시장모형", "시장조정")
EARN = r"영업\(잠정\)실적|매출액또는손익구조"


def load(url: str):
    with db.connect(url) as conn:
        daily = db.fetch_dicts(conn, "SELECT corp_code, trade_date, close_adj::float AS close FROM core.v_price_daily")
        index = db.fetch_dicts(conn, "SELECT market, trade_date, close::float AS close FROM core.v_index_daily")
        ev = pd.DataFrame(db.fetch_dicts(conn, """SELECT * FROM core.core_event_car WHERE status = '산출'"""))
        dec = pd.DataFrame(db.fetch_dicts(conn, """SELECT rcept_no, corp_code, attributed_year, dps_common_won, disclosed_on
                                                  FROM raw.dividend_decision WHERE div_kind = '결산배당' AND dps_common_won IS NOT NULL"""))
        earn = db.fetch_dicts(conn, f"SELECT corp_code, rcept_dt FROM raw.dart_filing_list WHERE report_nm ~ '{EARN}'")
        size = {r["corp_code"]: float(r["shares"]) for r in db.fetch_dicts(conn, """
            WITH par AS (SELECT corp_code, max(value)::numeric AS par FROM raw.dart_dividend_item
                         WHERE bsns_year = 2025 AND item LIKE '주당액면가액%%' AND value ~ '^[0-9.]+$' GROUP BY 1),
                 cap AS (SELECT DISTINCT ON (corp_code) corp_code, thstrm_amount FROM raw.dart_financial
                         WHERE bsns_year = 2025 AND account_id = 'ifrs-full_IssuedCapital' ORDER BY corp_code, ord)
            SELECT corp_code, cap.thstrm_amount / par.par AS shares FROM cap JOIN par USING (corp_code)
            WHERE par.par > 0 AND cap.thstrm_amount > 0""")}
    prices = _wide(daily, "corp_code", "close")
    markets = _wide(index, "market", "close").reindex(prices.index)
    return prices, markets, ev, dec, earn, size


def dps_change(dec: pd.DataFrame) -> dict:
    dec = dec.copy()
    dec["disclosed_on"] = dec["disclosed_on"].astype(str)
    last = dec.sort_values("rcept_no").groupby(["corp_code", "attributed_year"]).last()["dps_common_won"]
    first = dec.sort_values(["disclosed_on", "rcept_no"]).groupby(["corp_code", "attributed_year"]).first().reset_index()
    out = {}
    for r in first.itertuples():
        p0, now = last.get((r.corp_code, r.attributed_year - 1)), last.get((r.corp_code, r.attributed_year))
        if p0 and now is not None and float(p0) > 0:
            out[r.rcept_no] = (float(now) / float(p0) - 1) * 100
    return out


def compute(prices, markets, ev):
    """사례 × 모형 × 수익률 → CAR·σ·잔차. 반환: 행 목록."""
    days = [d.date() for d in prices.index]
    pos = {d: i for i, d in enumerate(days)}
    ev = ev[ev["disclosed_on"].map(lambda d: es.period_of(d)) == es.VERIFIED]
    rows = []
    for r in ev.itertuples():
        idx = pos.get(r.event_date)
        if idx is None or r.corp_code not in prices or r.market not in markets:
            continue
        s, m = prices[r.corp_code].to_numpy(), markets[r.market].to_numpy()
        e = es.Event(r.corp_code, r.kind, datetime.combine(r.event_date, time(0)), r.rcept_no, r.basis,
                     float(r.dps) if r.dps is not None and not pd.isna(r.dps) else None, r.record_date)
        add = np.array(es._dividend_add(e, days, prices[r.corp_code], idx, r.window_days))
        for model in MODELS:
            for ret, a in (("주가만", None), ("배당 포함", add)):
                if ret == "배당 포함" and e.dps is None:
                    continue
                x = st.event_ar(s, m, idx, r.window_days, model, a)
                if x is None:
                    continue
                rows.append({"kind": r.kind, "basis": r.basis, "window": r.window_days, "model": model, "ret": ret,
                             "corp_code": r.corp_code, "rcept_no": r.rcept_no, "event_date": r.event_date,
                             "overlap": bool(r.overlap_capital), "car": float(x.ar.sum()), "sigma": x.sigma,
                             "resid": x.est_resid, "pos": x.est_pos_share, "dps": e.dps,
                             "price0": float(s[idx - 1]) if idx >= 1 else None})
    return pd.DataFrame(rows)


def tests(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for key, g in df.groupby(["kind", "basis", "window", "model", "ret"]):
        g = g[~g["overlap"]]
        if len(g) < 10:
            continue
        car = g["car"].to_numpy()
        row = dict(zip(["공시 종류", "기준일", "창", "모형", "수익률"], key))
        row.update({"사례": len(g), "평균(%p)": round(car.mean() * 100, 2), "중앙값(%p)": round(float(np.median(car)) * 100, 2)})
        row["단순 t p"] = st.simple_t(car)[1]
        row["공시일 군집 t p"] = st.clustered_t(car, g["event_date"].astype(str).to_numpy())[1]
        h = g.dropna(subset=["sigma"])
        if len(h) >= 10:
            row["BMP p"] = st.bmp(h["car"].to_numpy(), h["sigma"].to_numpy(), key[2])[1]
            rbar = st.mean_residual_corr(list(h["resid"]))
            row["잔차 상관 r̄"] = round(rbar, 4)
            row["KP 보정 BMP p"] = st.bmp(h["car"].to_numpy(), h["sigma"].to_numpy(), key[2], max(rbar, 0.0))[1]
            row["일반화 부호 p"] = st.generalized_sign(h["car"].to_numpy(), float(h["pos"].mean()))[1]
        row["윌콕슨 p"] = st.wilcoxon(car)[1]
        out.append(row)
    t = pd.DataFrame(out)
    ok = t["KP 보정 BMP p"].notna()
    t.loc[ok, "KP p BH 보정 q"] = st.benjamini_hochberg(list(t.loc[ok, "KP 보정 BMP p"]))
    return t


def regression(df, change, earn, size, basis, window, model, ret):
    g = df[(df["kind"].str.startswith("주당배당금")) & (df["basis"] == basis) & (df["window"] == window)
           & (df["model"] == model) & (df["ret"] == ret) & (~df["overlap"])].copy()
    earn_set = {(r["corp_code"], pd.Timestamp(r["rcept_dt"])) for r in earn}
    g["chg"] = g["rcept_no"].map(change)
    g = g.dropna(subset=["chg"])
    lo, hi = g["chg"].quantile([0.01, 0.99])
    g["chg"] = g["chg"].clip(lo, hi)
    g["up"] = (g["kind"] == es.DPS_UP).astype(float)
    g["earn"] = [float(any((c, d - pd.Timedelta(days=k)) in earn_set for k in (0, 1)))
                 for c, d in zip(g["corp_code"], pd.to_datetime(g["event_date"]))]
    g["lsize"] = [math.log(size[c] * p) if c in size and p else np.nan for c, p in zip(g["corp_code"], g["price0"])]
    g["dy"] = [d / p * 100 if d and p else np.nan for d, p in zip(g["dps"], g["price0"])]
    years = sorted(pd.to_datetime(g["event_date"]).dt.year.unique())
    for y in years[1:]:
        g[f"y{y}"] = (pd.to_datetime(g["event_date"]).dt.year == y).astype(float)
    g = g.dropna(subset=["lsize", "dy"])
    specs = {"배당 변화만": ["up", "chg"], "+ 실적 공시 겹침": ["up", "chg", "earn"],
             "+ 규모·배당수익률·연도": ["up", "chg", "earn", "lsize", "dy"] + [f"y{y}" for y in years[1:]]}
    out = []
    for name, cols in specs.items():
        X = np.column_stack([np.ones(len(g))] + [g[c].to_numpy() for c in cols])
        beta, se = st.ols_cluster(X, g["car"].to_numpy() * 100, g["event_date"].astype(str).to_numpy())
        for i, c in enumerate(["상수"] + cols):
            if c.startswith("y"):
                continue
            out.append({"모형": name, "변수": {"up": "배당 증가(0/1)", "chg": "주당배당금 변화율(%)", "earn": "실적 공시 겹침(0/1)",
                                              "lsize": "log 시가총액(추정)", "dy": "배당수익률(%)"}.get(c, c),
                        "계수(%p)": round(beta[i], 3), "군집 표준오차": round(se[i], 3), "p": round(st.norm_p(beta[i] / se[i]), 4)})
    return pd.DataFrame(out), len(g)


def calendar_time(df, prices, markets, ev, window, ret):
    """달력시간 포트폴리오: 매일 창 안 사례의 초과수익(시장조정, 배당 포함 선택) 평균 → 창 길이 환산."""
    days = [d.date() for d in prices.index]
    pos = {d: i for i, d in enumerate(days)}
    market_of = dict(zip(ev["rcept_no"] + ev["basis"], ev["market"]))
    rows = []
    for kind in (es.DPS_UP, es.DPS_FLAT_DOWN):
        g = df[(df["kind"] == kind) & (df["basis"] == es.BASIS_DISCLOSED) & (df["window"] == window)
               & (df["model"] == "시장조정") & (df["ret"] == ret) & (~df["overlap"])]
        by_day: dict = {}
        for r in g.itertuples():
            i = pos[r.event_date]
            s = prices[r.corp_code].to_numpy()
            m = markets[market_of[r.rcept_no + es.BASIS_DISCLOSED]].to_numpy()
            add = np.zeros(window + 1)
            if ret == "배당 포함" and r.dps:
                e = es.Event(r.corp_code, kind, datetime.combine(r.event_date, time(0)), r.rcept_no, es.BASIS_DISCLOSED, r.dps,
                             ev.loc[(ev["rcept_no"] == r.rcept_no) & (ev["basis"] == es.BASIS_DISCLOSED), "record_date"].iloc[0])
                add = np.array(es._dividend_add(e, days, prices[r.corp_code], i, window))
            for k in range(window + 1):
                d = i + k
                ex = s[d] / s[d - 1] - m[d] / m[d - 1] + add[k]
                if not np.isnan(ex):
                    by_day.setdefault(days[d], []).append(ex)
        car, p, n = st.calendar_time(by_day, window)
        rows.append({"공시 종류": kind, "수익률": ret, "창": window, "포트폴리오 날 수": n,
                     "창 환산 CAR(%p)": round(car, 2), "p (뉴이-웨스트)": round(p, 4)})
    return pd.DataFrame(rows)


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(v, float) and pd.isna(v)) else
                                       (f"{v:.4f}" if isinstance(v, float) and abs(v) < 1 and v != 0 else str(v)) for v in r) + " |")
    return "\n".join(lines)


def main(url: str):
    prices, markets, ev, dec, earn, size = load(url)
    df = compute(prices, markets, ev)
    t = tests(df)
    change = dps_change(dec)
    reg, n_reg = regression(df, change, earn, size, es.BASIS_DISCLOSED, 60, "시장모형", "배당 포함")
    reg20, n20 = regression(df, change, earn, size, es.BASIS_DISCLOSED, 20, "시장모형", "배당 포함")
    rega, na = regression(df, change, earn, size, es.BASIS_DISCLOSED, 60, "시장조정", "배당 포함")
    cal = pd.concat([calendar_time(df, prices, markets, ev, w, "배당 포함") for w in (20, 60)], ignore_index=True)
    primary = t[(t["공시 종류"].str.startswith("주당배당금")) & (t["기준일"] == "공시일") & (t["창"] == 60)
                & (t["모형"] == "시장모형") & (t["수익률"] == "배당 포함")]
    show = t.copy()
    for c in [c for c in show.columns if c.endswith(" p") or c.endswith(" q")]:
        show[c] = show[c].map(lambda v: "" if pd.isna(v) else f"{v:.4f}")
    text = f"""# 이벤트 스터디 방법별 결과

- 실행: `.venv/bin/python -m scripts.event_methods` (방법: `source/core/event_stats.py`, 사례: `core.core_event_car` 2025년까지, 자본 변동 겹침 제외)
- **주 분석(미리 정함)**: 배당 결정 공시 · 공시일 · 배당 포함 · 60거래일 · 시장모형 · Kolari–Pynnönen 보정 BMP. 나머지는 강건성 확인.
- 'CAR이 0과 다른가'의 KP p값은 아래 모든 묶음에 걸쳐 Benjamini–Hochberg로 보정(q).
- 한계: 실적 '서프라이즈 크기'(예상 대비)는 자료가 없어 실적 공시 겹침 여부만 통제. 시가총액은 (자본금 ÷ 액면가) × 전일 주가 추정. 대상은 2026 고배당기업 638곳(생존 편향).

## 주 분석

{md(primary.drop(columns=[c for c in primary.columns if c in ("모형", "수익률")]))}

## 1. CAR이 0과 다른가 — 방법별 p값

{md(show)}

## 2. 무엇이 CAR을 설명하나 — 횡단면 회귀 (공시일 군집 표준오차, 시장모형·배당 포함)

60거래일 ({n_reg}건):

{md(reg)}

20거래일 ({n20}건):

{md(reg20)}

같은 회귀를 시장조정 수익률로 (60거래일, {na}건):

{md(rega)}

## 3. 달력시간 포트폴리오 (공시일, 시장조정, 배당 포함)

매일 창 안에 있는 사례들의 초과수익을 동일가중 평균해, 날짜 몰림·겹침을 구조적으로 없앤 방법입니다.

{md(cal)}
"""
    OUT.write_text(text, encoding="utf-8")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    clean = lambda d: json.loads(d.to_json(orient="records", force_ascii=False))  # NaN → null
    OUT_JSON.write_text(json.dumps({"tests": clean(t), "regression_60": clean(reg), "n_regression_60": n_reg,
                                    "calendar": clean(cal)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="이벤트 스터디를 여러 통계 방법으로 다시 계산")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    main(ap.parse_args().url)
