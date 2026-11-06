"""무리끼리 주가 비교(C2)를 report/분석/무리별_주가_비교_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_price_groups [--url ...] [--reps 1000]
기준일 2025-07-01(그 뒤 첫 거래일 종가 = 0%)부터 2026-10-20까지, 수정 종가만 쓴 주가 수익률(배당 제외).
'제외' 등급 주가(`core.v_price_daily.grade`)는 쓰지 않는다.
"""
import argparse
import math
from datetime import date
from pathlib import Path

import numpy as np

from core import db
from core import group_compare as gc
from core import p1_analysis as p1
from core import price_groups as pg
from scripts import analysis_groups as ag

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "무리별_주가_비교_결과.md"
START, END = date(2025, 7, 1), date(2026, 10, 20)
KEY_DATES = [date(2025, 12, 30), date(2026, 3, 31), END]
PRICE_SQL = """SELECT corp_code, trade_date, close_adj FROM core.v_price_daily
               WHERE trade_date BETWEEN %s AND %s AND close_adj IS NOT NULL AND grade <> '제외'
               ORDER BY corp_code, trade_date"""
NEED_SQL = """SELECT m.corp_code, m.pass_if_same_as_2025 FROM core.core_min_dividend_2027 m
              JOIN core.v_financial_year_verified f ON f.corp_code = m.corp_code AND f.bsns_year = 2025  -- 최소액 계산과 같은 확정 값(원문 대조로 고친 순이익 포함)
              WHERE m.status = '산출' AND (m.scenario = '2025년 (기본)' OR m.ni2026_won = f.ni_owner_won)"""
COVER_SQL = "SELECT corp_code, cover_x FROM core.core_capacity_2025 WHERE status = '표시' AND cover_x IS NOT NULL"


def rule_group(corp, need, cover):
    if need.get(corp) is True:
        return "① 2025만큼만 배당해도 충분"
    if need.get(corp) is False and corp in cover and cover[corp] < 1:
        return "③ 더 내야 하고 잉여현금흐름도 부족"
    return None


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        data = {k: db.fetch_dicts(conn, q) for k, q in ag.SQL.items()}
        prices = {}
        for r in db.fetch_dicts(conn, PRICE_SQL, (START.replace(day=1), END)):
            prices.setdefault(r["corp_code"], []).append((r["trade_date"], float(r["close_adj"])))
        need = {r["corp_code"]: r["pass_if_same_as_2025"] for r in db.fetch_dicts(conn, NEED_SQL)}
        cover = {r["corp_code"]: float(r["cover_x"]) for r in db.fetch_dicts(conn, COVER_SQL)}
    corps = list(comp)
    feats = dict(zip(corps, ag.features(data, comp)))
    shares = {r["corp_code"]: float(r["issued"]) for r in data["shares"] if r["issued"]}
    checks = pg.month_ends(START, END)
    all_days = sorted(set(checks) | set(KEY_DATES))
    rets = {c: dict(zip(all_days, pg.cumulative(prices.get(c, []), START, all_days))) for c in corps}

    rows = []
    for c in corps:
        f = feats[c]
        base = next(((d, p) for d, p in prices.get(c, []) if d >= START), None)
        mcap0 = shares[c] * base[1] if base and c in shares else None
        rows.append({"corp": c, "ret": rets[c], "log_mcap": math.log10(mcap0) if mcap0 else float("nan"),
                     "kosdaq": float(f["kosdaq"]),
                     "timing": f["timing"],
                     "holder": {"개인": "최대주주 개인", "법인": "최대주주 법인"}.get(f["holder_kind"]),
                     "band": None if f["band_25_28"] is None else ("배당성향 25~28%" if f["band_25_28"] else "배당성향 28% 이상"),
                     "rule": rule_group(c, need, cover)})

    comparisons = [("timing", ag.EARLY, ag.LATE, "밸류업 첫 공시 시기"),
                   ("holder", "최대주주 개인", "최대주주 법인", "최대주주 유형"),
                   ("band", "배당성향 25~28%", "배당성향 28% 이상", "2025 배당성향"),
                   ("rule", "③ 더 내야 하고 잉여현금흐름도 부족", "① 2025만큼만 배당해도 충분", "2027 배당 부담(B1)")]

    monthly = ["| 기준일 | " + " | ".join(f"{t}: {a} − {b}" for _, a, b, t in comparisons) + " |",
               "|---" * (len(comparisons) + 1) + "|"]
    for d in checks:
        cells = []
        for key, a, b, _ in comparisons:
            va = [r["ret"][d] for r in rows if r[key] == a and r["ret"][d] is not None]
            vb = [r["ret"][d] for r in rows if r[key] == b and r["ret"][d] is not None]
            cells.append(f"{np.mean(va) - np.mean(vb):+.1f}%p")
        monthly.append(f"| {d.isoformat()} | " + " | ".join(cells) + " |")

    detail = []
    summary_bits = []
    for key, a, b, title in comparisons:
        detail.append(f"### {title}: {a} vs {b}\n")
        detail.append("| 기준일 | " + a + " 평균 (회사 수) | " + b + " 평균 (회사 수) | 평균 차이 (오차 범위 95%) | 중앙값 차이 (오차 범위 95%) | 규모·시장이 같다고 볼 때 평균 차이 (오차 범위 95%) |")
        detail.append("|---|---|---|---|---|---|")
        for d in KEY_DATES:
            sub = [r for r in rows if r[key] in (a, b) and r["ret"][d] is not None]
            raw = gc.mean_diff([r["ret"][d] for r in sub if r[key] == a], [r["ret"][d] for r in sub if r[key] == b], reps)
            mid = gc.median_diff([r["ret"][d] for r in sub if r[key] == a], [r["ret"][d] for r in sub if r[key] == b], reps)
            adj = gc.adjusted_diff([r["ret"][d] for r in sub], [float(r[key] == a) for r in sub],
                                   [[r["log_mcap"], r["kosdaq"]] for r in sub], reps)
            detail.append(f"| {d.isoformat()} | {raw.a:+.1f}% ({raw.n_a}) | {raw.b:+.1f}% ({raw.n_b}) | "
                          f"{raw.diff:+.1f}%p ({raw.low:+.1f} ~ {raw.high:+.1f}) | {mid.diff:+.1f}%p ({mid.low:+.1f} ~ {mid.high:+.1f}) | {adj[0]:+.1f}%p ({adj[1]:+.1f} ~ {adj[2]:+.1f}, {adj[3]}사) |")
            if d == END:
                sure = "확실한 차이" if adj[1] > 0 or adj[2] < 0 else "확실한 차이 아님"
                msure = "확실" if mid.low > 0 or mid.high < 0 else "확실하지 않음"
                summary_bits.append(f"{title}: {a} − {b} = 평균 {raw.diff:+.1f}%p, 중앙값 {mid.diff:+.1f}%p({msure}), "
                                    f"규모·시장 맞춘 뒤 평균 {adj[0]:+.1f}%p({sure})")
        detail.append("")

    text = f"""# 무리별 주가 비교 — 638사 안에서 어느 쪽 주가가 더 올랐나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_price_groups.py`, `source/core/price_groups.py` · 설계: `report/설계/데이터_분석_설계.md` C2
- 기간: {START.isoformat()} 이후 첫 거래일 종가를 0%로 놓고 {END.isoformat()}까지. 회사마다 누적 수익률을 낸 뒤 무리 안에서 단순 평균(회사마다 같은 무게)
- 주가: `core.v_price_daily` 수정 종가, '제외' 등급 날은 뺌(그 전 마지막 거래일 값을 씀). **배당은 넣지 않은 주가 수익률**이다
- 무리: 공시 시기·최대주주·배당성향은 `report/분석/공시시기_최대주주_비교_결과.md`, 2027 배당 부담은 `report/분석/유지가능성_분석_결과.md`와 같은 기준
- 규모·시장이 같다고 볼 때 차이: 누적 수익률을 무리 여부 + 시작일 시가총액(로그) + 코스닥 여부로 맞춘 직선의 무리 계수. 오차 범위는 회사를 무작위로 다시 뽑아 {reps}번 계산(시드 {gc.SEED})

## 한 줄 결과

{chr(10).join("- " + s for s in summary_bits)}

몇몇 회사가 몇 배씩 오르면 평균이 크게 흔들리므로, 중앙값 차이를 함께 본다. 평균과 중앙값이 같은 방향이고 둘 다 확실할 때만 '차이가 있다'고 읽는다.

## 0. 왜 무리끼리 비교하나

2026년 시장지수는 다른 출처와 대조하지 않았다(예: 2026-07-31 코스피 지수 하루 +17.9%인데 638사 주가는 평균 +5.5%). 같은 날짜에 638사 안의 두 무리를 비교하면 시장 전체 움직임은 양쪽에 똑같이 들어가 빠진다. 그래서 지수 없이도 무리 간 차이는 볼 수 있다. 다만 두 무리의 규모·시장이 크게 다르면(A2: 일찍 공시한 회사는 대형 코스피사가 많음) 그 차이가 섞이므로, 규모·시장을 맞춘 차이를 함께 적었다.

## 1. 달마다 무리 간 평균 누적 수익률 차이 (단순 차이)

{chr(10).join(monthly)}

## 2. 주요 기준일 자세히

기준일: 2025-12-30(2025 사업연도 마지막 거래일, 배당 기준일 무렵), 2026-03-31(배당 결정·고배당기업 공시가 대부분 끝난 뒤), {END.isoformat()}(자료 마지막 날).

{chr(10).join(detail)}
## 3. 읽을 때 주의

- 배당성향 25~28% 회사의 주가가 더 오른 것은 이 회사들의 ROE가 더 높은 것(A3)과 함께 볼 일이다. 돈을 잘 버는 회사의 주가가 오른 것일 수 있고, 기준선에 맞춰 배당을 늘린 것(A1)이 시장에서 좋게 받아들여진 것일 수도 있다. 이 표만으로는 둘을 가를 수 없다.
- 2027 배당 부담 무리는 2025 숫자로 충족한 회사 전체에 규칙을 적용해 B1 문서(특징 값이 모두 있는 521사)보다 회사 수가 많다.
- **관계이지 원인이 아니다.** 예를 들어 2026년에 처음 공시한 회사의 주가가 덜 올랐어도, 고배당기업 공시 때문이라고 말할 수 없다. 업종, 2026년 실적 같은 다른 이유가 섞여 있다.
- 배당을 넣지 않은 주가 수익률이다. 배당락일(대개 연말) 뒤에는 배당을 많이 준 회사의 주가가 그만큼 떨어져 보인다. 무리 간 시가배당률 중앙값 차이는 1%p 안쪽이다(A2·A3 결과).
- 시작일(2025-07-01)은 분석 기간을 고르려고 정한 날이다. 분리과세 제도의 발표·국회 통과·공포 날짜는 이 DB에 없어서 기준일로 쓰지 않았다. 공식 날짜를 확인하면 그날을 기준으로 다시 계산해야 한다.
- 2026년 주가 자료(KRX 시세, pykrx로 받음)는 아직 다른 출처와 대조하지 않았다. 무리 비교는 시장 전체 오류에는 강하지만 개별 종목 오류에는 약하다.
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=gc.REPS)
    a = ap.parse_args()
    main(a.url, a.reps)
