"""밸류업 계획 첫 공시·고배당기업 공시 뒤 주가 반응(C1)을 report/분석/밸류업_고배당공시_주가반응_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_event_valueup [--url ...] [--reps 1000]
초과수익률 = 공시 전날 종가 → n거래일 뒤 종가의 주가 수익률 − 같은 기간 기준 수익률. 기준은 두 가지:
  ① 시장지수(코스피·코스닥, `core.v_index_daily`) — 2026년 값은 다른 출처와 대조하지 않았다
  ② 638사 평균 주가(회사마다 같은 무게) — 지수 대조와 무관하지만 '다른 고배당기업 대비'라는 뜻이 된다
'제외' 등급 주가는 쓰지 않는다. 배당은 넣지 않는다.
"""
import argparse
import bisect
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from core import db
from core import group_compare as gc
from core import p1_analysis as p1
from core import price_groups as pg
from scripts import analysis_groups as ag

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "밸류업_고배당공시_주가반응_결과.md"
WINDOWS = (1, 5, 20)
START = date(2024, 1, 1)
PRICE_SQL = """SELECT corp_code, trade_date, close_adj FROM core.v_price_daily
               WHERE trade_date >= %s AND close_adj IS NOT NULL AND grade <> '제외'"""
INDEX_SQL = "SELECT market, trade_date, close FROM core.v_index_daily WHERE trade_date >= %s ORDER BY trade_date"
KIND_SQL = "SELECT corp_code, final_disclosed_on::date AS final_disclosed_on FROM raw.kind_list WHERE final_disclosed_on IS NOT NULL"
FILING_SQL = "SELECT corp_code, rcept_dt FROM raw.policy_filing WHERE report_nm NOT LIKE '%%예고%%'"


def mean_ci(xs, reps):
    d = gc.mean_diff(xs, [0.0], reps)
    return d.a, d.low, d.high, d.n_a


def week(d: date) -> tuple[int, int]:
    return d.isocalendar()[:2]


def sure(lo, hi):
    return "예" if lo > 0 or hi < 0 else "아니오"


def within_day(pa, pb):
    """같은 날 공시한 두 무리끼리의 평균 차이를, 그날 앞 무리 회사 수로 가중 평균. (차이, 두 무리가 함께 있는 날 수,
    그중 앞 무리가 더 오른 날 수, 그날들의 앞 무리 회사 수, 앞 무리 회사 수가 가장 많은 날들 [(날짜, 앞 수, 뒤 수, 차이)])"""
    by = {}
    for i, group in enumerate((pa, pb)):
        for x, t in group:
            by.setdefault(t, ([], []))[i].append(x)
    mixed = {t: (sum(a) / len(a) - sum(b) / len(b), len(a), len(b)) for t, (a, b) in by.items() if a and b}
    n = sum(v[1] for v in mixed.values())
    est = sum(v[0] * v[1] for v in mixed.values()) / n if n else float("nan")
    top = sorted(((t, v[1], v[2], v[0]) for t, v in mixed.items()), key=lambda r: -r[1])[:5]
    return est, len(mixed), sum(1 for v in mixed.values() if v[0] > 0), n, top


def row(label, pairs, reps):
    """pairs: (초과수익률, 0일 거래일). 오차 범위를 회사 따로·같은 날 묶음·같은 주 묶음 세 가지로 낸다."""
    pairs = [(x, d) for x, d in pairs if x is not None]
    xs = [x for x, _ in pairs]
    if len(xs) < 10:
        return f"| {label} | {len(xs)} | | 회사가 10곳 미만이라 생략 | | | |"
    m, lo, hi, n = mean_ci(xs, reps)
    day = gc.cluster_mean_diff(xs, [], [d for _, d in pairs], [], reps)
    wk = gc.cluster_mean_diff(xs, [], [week(d) for _, d in pairs], [], reps)
    n_day = len({d for _, d in pairs})
    return (f"| {label} | {n} | {n_day} | {m:+.2f}% | {lo:+.2f} ~ {hi:+.2f} ({sure(lo, hi)}) | "
            f"{day.low:+.2f} ~ {day.high:+.2f} ({sure(day.low, day.high)}) | {wk.low:+.2f} ~ {wk.high:+.2f} ({sure(wk.low, wk.high)}) |")


HEAD = ("| 무리 · 기간 | 회사 수 | 공시 날짜 수 | 평균 초과수익률 | 오차 범위: 회사 따로 (0과 다름) | 같은 날 묶음 | 같은 주 묶음 |\n"
        "|---|---|---|---|---|---|---|")


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        prices = {}
        for r in db.fetch_dicts(conn, PRICE_SQL, (START - timedelta(days=10),)):
            prices.setdefault(r["corp_code"], {})[r["trade_date"]] = float(r["close_adj"])
        index = {"KOSPI": {}, "KOSDAQ": {}}
        for r in db.fetch_dicts(conn, INDEX_SQL, (START - timedelta(days=10),)):
            index[r["market"]][r["trade_date"]] = float(r["close"])
        kind = {r["corp_code"]: r["final_disclosed_on"] for r in db.fetch_dicts(conn, KIND_SQL)}
        filings = db.fetch_dicts(conn, FILING_SQL)
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        data = {k: db.fetch_dicts(conn, q) for k, q in ag.SQL.items()}
    days = sorted(index["KOSPI"])
    ew = pg.equal_weight_index(prices, days)
    feats = dict(zip(comp, ag.features(data, comp)))
    first = {}
    for f in filings:
        first[f["corp_code"]] = min(f["rcept_dt"], first.get(f["corp_code"], f["rcept_dt"]))
    filing_days = {}
    for f in filings:
        filing_days.setdefault(f["corp_code"], set()).add(f["rcept_dt"])
    same_day = sum(1 for c, d in kind.items() if any(abs((d - x).days) <= 2 for x in filing_days.get(c, ())))

    def ar(corp, event, n, bench):
        if corp not in prices:
            return None
        b = ew if bench == "ew" else index["KOSDAQ" if feats[corp]["kosdaq"] else "KOSPI"]
        return pg.abnormal_return(prices[corp], b, days, event, n)

    def day0(event):
        i = bisect.bisect_left(days, event)
        return days[i] if i < len(days) else event

    def arp(corp, event, n, bench):
        return ar(corp, event, n, bench), day0(event)

    # 1. 밸류업 계획 첫 공시
    v_lines = [HEAD]
    for label, lo, hi in (("2024년 첫 공시", date(2024, 1, 1), date(2024, 12, 31)), ("2025년 첫 공시", date(2025, 1, 1), date(2025, 12, 31)),
                          ("2026년 첫 공시", date(2026, 1, 1), date(2026, 12, 31))):
        ev = [(c, d) for c, d in first.items() if lo <= d <= hi]
        for n in WINDOWS:
            for bench, bname in (("index", "지수 대비"), ("ew", "638사 평균 대비")):
                v_lines.append(row(f"{label} · {n}거래일 · {bname}", [arp(c, d, n, bench) for c, d in ev], reps))

    # 2. KIND 고배당기업 공시 (2026)
    k_lines = [HEAD]
    for n in WINDOWS:
        for bench, bname in (("index", "지수 대비"), ("ew", "638사 평균 대비")):
            k_lines.append(row(f"전체 · {n}거래일 · {bname}", [arp(c, d, n, bench) for c, d in kind.items()], reps))

    # 3. KIND 공시 반응을 무리별로 (638사 평균 대비, 20거래일)
    def split(key, a, b, n=20):
        pa = [(x, t) for x, t in (arp(c, d, n, "ew") for c, d in kind.items() if c in feats and key(feats[c]) == a) if x is not None]
        pb = [(x, t) for x, t in (arp(c, d, n, "ew") for c, d in kind.items() if c in feats and key(feats[c]) == b) if x is not None]
        xa, xb = [x for x, _ in pa], [x for x, _ in pb]
        d = gc.mean_diff(xa, xb, reps)
        day = gc.cluster_mean_diff(xa, xb, [t for _, t in pa], [t for _, t in pb], reps)
        wk = gc.cluster_mean_diff(xa, xb, [week(t) for _, t in pa], [week(t) for _, t in pb], reps)
        split_res[a] = (d, day, wk, within_day(pa, pb), len(pa))
        return (f"| {a} − {b} | {d.a:+.2f}% ({d.n_a}) | {d.b:+.2f}% ({d.n_b}) | {d.diff:+.2f}%p | "
                f"{d.low:+.2f} ~ {d.high:+.2f} ({sure(d.low, d.high)}) | {day.low:+.2f} ~ {day.high:+.2f} ({sure(day.low, day.high)}) | "
                f"{wk.low:+.2f} ~ {wk.high:+.2f} ({sure(wk.low, wk.high)}) |")

    split_res = {}
    g_lines = ["| 비교 | 앞 무리 평균 (회사 수) | 뒤 무리 평균 (회사 수) | 차이 | 오차 범위: 회사 따로 (확실한 차이) | 같은 날 묶음 | 같은 주 묶음 |",
               "|---|---|---|---|---|---|---|",
               split(lambda f: None if f["band_25_28"] is None else ("배당성향 25~28%" if f["band_25_28"] else "배당성향 28% 이상"),
                     "배당성향 25~28%", "배당성향 28% 이상"),
               split(lambda f: {"개인": "최대주주 개인", "법인": "최대주주 법인"}.get(f["holder_kind"]), "최대주주 개인", "최대주주 법인"),
               split(lambda f: f["timing"], ag.EARLY, ag.LATE)]

    text = f"""# 밸류업 계획·고배당기업 공시 뒤 주가 반응

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_event_valueup.py`, `source/core/price_groups.py` · 설계: `report/설계/데이터_분석_설계.md` C1
- 초과수익률: 공시 전날 종가부터 n거래일 뒤 종가까지 주가 수익률 − 같은 기간 기준 수익률. 공시 시각을 몰라 공시일(0일) 하루를 통째로 넣었다
- 기준 ① **지수 대비**: 코스피·코스닥 지수(`core.v_index_daily`). **2026년 값은 다른 출처와 대조하지 않았다**(예: 2026-07-31 코스피 하루 +17.9%)
- 기준 ② **638사 평균 대비**: 638사 주가를 회사마다 같은 무게로 평균한 값. 지수 대조와 무관하지만, 다른 고배당기업과 비교한 값이 된다
- 오차 범위(95%, {reps}번 다시 뽑기, 시드 {gc.SEED}) 세 가지. 회사가 10곳 미만이면 생략
  - **회사 따로**: 회사를 하나씩 무작위로 다시 뽑는다. 회사들이 서로 따로 움직인다고 보는 계산
  - **같은 날 묶음**: 공시일(0일 거래일)이 같은 회사들을 한 덩어리로 다시 뽑는다. 같은 날 시장 분위기를 함께 타는 몫을 반영
  - **같은 주 묶음**: 같은 주에 공시한 회사들을 한 덩어리로. 5·20거래일 창은 가까운 날끼리 기간이 겹치므로 더 넓게 묶어 본다
  - 세 가지 모두 0을 넘지 않을 때(또는 모두 0 아래일 때) 확실한 차이로 읽는다
- 배당은 넣지 않은 주가 수익률, '제외' 등급 주가는 뺌

## 한 줄 결과

{{summary}}

## 1. 밸류업 계획 첫 공시 뒤 (예고 공시 제외, 회사마다 첫 공시 1건)

{chr(10).join(v_lines)}

## 2. KIND 고배당기업 공시 뒤 (2026년, 회사마다 최종 공시 1건)

KIND 공시 {len(kind)}건 중 {same_day}건은 같은 회사의 밸류업 계획 공시와 ±2일 안에 겹친다(고배당기업 표시를 위한 재공시). 그래서 두 공시의 반응은 서로 섞여 있다.

{chr(10).join(k_lines)}

## 3. KIND 고배당기업 공시 반응을 무리별로 (638사 평균 대비, 20거래일)

{chr(10).join(g_lines)}

{{within}}

## 4. 읽을 때 주의

- **2026년 '지수 대비' 값은 지수 대조 전이라 믿기 어렵다.** 2026년 결과는 '638사 평균 대비'를 기준으로 읽는다.
- 638사 평균 대비는 "다른 고배당기업보다 더 올랐나"다. 2026년 2~4월에는 638사 대부분이 고배당기업 공시를 해서, 모두가 함께 오른 몫은 이 기준에서 빠진다. 그래서 공시 효과가 실제보다 작게 보일 수 있다.
- 공시가 특정 날짜에 몰려 있다(2026년 첫 공시 545사가 54개 날짜에). 그래서 '회사 따로' 오차 범위는 실제보다 좁다. **'같은 날 묶음'·'같은 주 묶음'에서도 0과 다른 값만 믿는다.** 다만 묶음 수가 적으면(수십 개) 묶음 오차 범위 자체도 거칠다.
- 기존 이벤트 계산(`source/core/event_study.py`, `core_event_summary`)의 'KIND 고배당기업 공시'는 지수 대비만 있어 2026년 결과를 화면에서 뺐다. 이 문서의 638사 평균 대비 값이 그 빈자리를 메울 후보다.
"""
    k20 = [ar(c, d, 20, "ew") for c, d in kind.items()]
    k20 = [x for x in k20 if x is not None]
    m, lo, hi, n = mean_ci(k20, reps)
    v24 = [x for x in (ar(c, d, 20, "index") for c, d in first.items() if d.year == 2024) if x is not None]
    vm, vlo, vhi, vn = mean_ci(v24, reps)
    d, day, wk, (wd, n_mixed, n_up, n_in, top), _ = split_res["배당성향 25~28%"]
    v1 = [x for x in (arp(c, d0, 1, "index") for c, d0 in first.items() if d0.year in (2024, 2025)) if x[0] is not None]
    v1d = gc.cluster_mean_diff([x for x, _ in v1], [], [week(t) for _, t in v1], [], reps)
    top_txt = ", ".join(f"{t:%m/%d} {na}사 대 {nb}사 {x:+.1f}%p" for t, na, nb, x in top)
    summary = (f"2024~2025년에 밸류업 계획을 처음 공시한 {len(v1)}사는 공시 다음 날까지(1거래일) 지수보다 평균 {v1d.a:+.2f}% 올랐고, "
               f"같은 주 공시를 한 덩어리로 묶어 계산해도 오차 범위가 {v1d.low:+.2f} ~ {v1d.high:+.2f}로 0을 넘지 않는다. "
               f"2026년 KIND 고배당기업 공시 뒤 20거래일은 638사 평균 대비 {m:+.2f}%(오차 범위 {lo:+.2f} ~ {hi:+.2f}, {n}사)로 차이가 없다. "
               f"배당성향 25~28% 회사가 28% 이상 회사보다 20거래일 동안 {d.diff:+.2f}%p 더 올랐지만, 같은 날 공시한 회사를 묶어 계산하면 오차 범위가 "
               f"{day.low:+.2f} ~ {day.high:+.2f}로 0을 포함한다. **회사 따로 계산할 때는 확실해 보였지만, 날짜 효과를 감안하면 확실하다고 말할 수 없다.**")
    within = (f"같은 날 공시한 회사끼리만 비교하면(두 무리가 함께 있는 {n_mixed}개 날짜, 25~28% 회사 {n_in}사) 차이는 {wd:+.2f}%p이고, "
              f"{n_mixed}개 날짜 중 {n_up}개 날짜에서 25~28% 회사가 더 올랐다. 25~28% 회사가 많은 날짜: {top_txt}. "
              f"더 오른 날이 더 많아 방향은 대체로 같지만, 차이의 크기는 몇몇 날짜에서 크게 나고 가장 많은 회사가 공시한 날에는 방향이 반대다. "
              f"그래서 '더 오른 편'이라는 방향까지는 말할 수 있어도, 크기(+{d.diff:.1f}%p 안팎)는 날짜 몇 개에 기대고 있다.")
    text = text.replace("{summary}", summary).replace("{within}", within)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=gc.REPS)
    a = ap.parse_args()
    main(a.url, a.reps)
