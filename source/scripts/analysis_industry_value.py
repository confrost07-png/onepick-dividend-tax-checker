"""업종 안 수익성·안정성 위치(B3)와 배당수익률·PBR 비교(C3)를 report/분석/업종_위치_주가수준_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_industry_value [--url ...] [--reps 1000]
- B3: 같은 업종(638사 안, 3사 이상) 안에서의 순위(0~100, 50이 가운데). 업종 차이를 뺀 뒤에도 무리 간 차이가 남는지 본다. 금융업 제외.
- C3: 2025-12-30 기준 주가순자산배율(PBR)·시가배당률. 밸류업 계획에 PBR 목표를 적은 회사(D1 규칙)와 아닌 회사 비교.
"""
import argparse
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

from core import capacity as cp
from core import db
from core import group_compare as gc
from core import p1_analysis as p1
from core import policy_promise as pp
from scripts import analysis_groups as ag
from scripts import analysis_policy_promise as apr

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "업종_위치_주가수준_결과.md"
MIN_PEERS = 3
METRICS = [("ROE(%p)", "roe"), ("부채비율(%p)", "debt"), ("유동비율(%p)", "current"), ("현금 비중(%p)", "cash_share")]


def industry_rank(rows: list[dict], key: str) -> None:
    """회사마다 같은 업종 안 순위(0~100, 값이 클수록 높음, 같은 값은 가운데 순위)를 key + '_rank'에 적는다.
    업종 회사가 MIN_PEERS 미만이면 None."""
    by = defaultdict(list)
    for r in rows:
        if r[key] is not None and r["industry"]:
            by[r["industry"]].append(r[key])
    for r in rows:
        peers = by.get(r["industry"], [])
        if r[key] is None or len(peers) < MIN_PEERS:
            r[key + "_rank"] = None
            continue
        below = sum(1 for v in peers if v < r[key])
        same = sum(1 for v in peers if v == r[key])
        r[key + "_rank"] = (below + same / 2) * 100 / len(peers)


def table(rows, gkey, ga, gb, items, reps, share_items=(), mean=False):
    lines = [f"| 항목 | {ga} (회사 수) | {gb} (회사 수) | 차이 | 오차 범위(95%) | 확실한 차이 |", "|---|---|---|---|---|---|"]
    for label, k in items:
        d = (gc.mean_diff if mean else gc.median_diff)([r[k] for r in rows if r[gkey] == ga], [r[k] for r in rows if r[gkey] == gb], reps)
        lines.append(f"| {label} · {'평균' if mean else '중앙값'} " + ag.fmt_diff(d, 2 if k in ("pbr", "yield") else 1))
    for label, k in share_items:
        d = gc.share_diff([r[k] for r in rows if r[gkey] == ga], [r[k] for r in rows if r[gkey] == gb], reps)
        lines.append(f"| {label}(%) " + ag.fmt_diff(d))
    return "\n".join(lines)


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        data = {k: db.fetch_dicts(conn, q) for k, q in ag.SQL.items()}
        info = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT corp_code, industry, status FROM core.core_capacity_2025")}
        names = {r["corp_code"]: r["corp_name"] for r in db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_company")}
        chunks = db.fetch_dicts(conn, apr.CHUNK_SQL)
    pbr_goal = {c["corp_code"] for c in chunks for p in pp.find(c["text"]) if p.kind == "PBR"}
    rows = []
    for corp, f in zip(comp, ag.features(data, comp)):
        i = info.get(corp, {})
        rows.append({**f, "corp": corp, "industry": i.get("industry"),
                     "financial": cp.is_financial(i.get("industry"), names.get(corp, "")),
                     "pbr_goal": "PBR 목표 적음" if corp in pbr_goal else "PBR 목표 없음",
                     "pbr_below1": f["pbr"] < 1 if f["pbr"] is not None else None,
                     "holder_group": {"개인": "최대주주 개인", "법인": "최대주주 법인"}.get(f["holder_kind"])})
    nonfin = [r for r in rows if not r["financial"]]
    for _, k in METRICS:
        industry_rank(nonfin, k)
    gap_items = [(f"{label.split('(')[0]} 업종 안 순위", k + "_rank") for label, k in METRICS]
    n_ind = len({r["industry"] for r in nonfin if r["roe_rank"] is not None})
    n_gap = sum(1 for r in nonfin if r["roe_rank"] is not None)

    all_pbr = [r["pbr"] for r in rows if r["pbr"] is not None]
    all_yield = [r["yield"] for r in rows if r["yield"] is not None]
    below1 = sum(1 for v in all_pbr if v < 1)

    timing_b3 = table(nonfin, "timing", ag.EARLY, ag.LATE, gap_items, reps, mean=True)
    holder_b3 = table([r for r in nonfin if r["holder_group"]], "holder_group", "최대주주 개인", "최대주주 법인", gap_items, reps, mean=True)
    c3_items = [("주가순자산배율(PBR, 배)", "pbr"), ("시가배당률(%)", "yield")]
    c3_share = [("PBR 1배 미만 비율", "pbr_below1")]
    goal_c3 = table(rows, "pbr_goal", "PBR 목표 적음", "PBR 목표 없음", c3_items, reps, c3_share)
    timing_c3 = table(rows, "timing", ag.EARLY, ag.LATE, c3_items, reps, c3_share)

    text = f"""# 업종 안 위치와 주가 수준 — 수익성·안정성(B3), 배당수익률·PBR(C3)

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_industry_value.py` · 설계: `report/설계/데이터_분석_설계.md` B3·C3
- 값의 정의와 출처는 A2·A3(`report/분석/공시시기_최대주주_비교_결과.md`)와 같다. 2025 사업연도 재무, 2025-12-30 종가, 2025년 말 보통주 수
- 업종: `core.core_capacity_2025.industry`(DART 기업개황). 금융업은 부채비율 등의 뜻이 달라 B3에서 뺐다
- 오차 범위: 무리마다 회사를 무작위로 다시 뽑아 {reps}번 계산한 값의 가운데 95%(시드 {gc.SEED})

## 한 줄 결과

{{summary}}

## 1. B3 — 업종 차이를 빼도 무리 간 차이가 남나

회사마다 **같은 업종 안에서의 순위**(0~100, 값이 클수록 높음, 50이 가운데)를 매기고 무리별 평균을 비교한다. 업종 차이가 빠지므로, 평균 순위가 50보다 높으면 '같은 업종 회사들보다 그 값이 높은 편'이다. 같은 업종 회사가 {MIN_PEERS}사 이상인 {n_ind}개 업종, {n_gap}사만 계산된다. 순위는 전체 상장사가 아니라 **638사 안의 같은 업종 회사** 사이의 순위다.

### 공시 시기별

{timing_b3}

### 최대주주 유형별

{holder_b3}

## 2. C3 — 배당수익률과 주가순자산배율(PBR)

- 638사 PBR 중앙값 {statistics.median(all_pbr):.2f}배({len(all_pbr)}사), **1배 미만 {below1}사({below1 * 100 / len(all_pbr):.0f}%)**. 시가배당률 중앙값 {statistics.median(all_yield):.2f}%({len(all_yield)}사).

### 밸류업 계획에 PBR 목표를 적은 회사 vs 아닌 회사

PBR 목표 여부는 D1 규칙(`source/core/policy_promise.py`)으로 찾은 후보다(사람 확인 전).

{goal_c3}

### 공시 시기별

{timing_c3}

## 3. 읽을 때 주의

- 업종 중앙값이 638사(고배당기업) 안에서 낸 값이라, "업종 평균보다 낫다"가 아니라 "같은 업종 고배당기업 중에서 어디쯤"이다.
- PBR = 2025년 말 보통주 수 × 2025-12-30 수정 종가 ÷ 자본총계(지배주주 몫이 아닌 전체 자본). 우선주는 넣지 않았다.
- PBR 목표를 적은 회사의 PBR이 낮은 것은 "PBR이 낮아서 목표를 세웠다"는 순서일 가능성이 크다. 목표를 세워서 낮아진 것이 아니다.
"""
    t = gc.mean_diff([r["roe_rank"] for r in nonfin if r["timing"] == ag.EARLY], [r["roe_rank"] for r in nonfin if r["timing"] == ag.LATE], reps)
    dr = gc.mean_diff([r["debt_rank"] for r in nonfin if r["timing"] == ag.EARLY], [r["debt_rank"] for r in nonfin if r["timing"] == ag.LATE], reps)
    g = gc.median_diff([r["pbr"] for r in rows if r["pbr_goal"] == "PBR 목표 적음"], [r["pbr"] for r in rows if r["pbr_goal"] == "PBR 목표 없음"], reps)
    summary = (f"같은 업종 안 순위(50이 가운데)로 보면, ROE 평균 순위는 일찍 공시한 회사 {t.a:.0f}, 2026년에 처음 공시한 회사 {t.b:.0f}"
               f"(차이 {t.diff:+.0f}, 오차 범위 {t.low:+.0f} ~ {t.high:+.0f}), 부채비율 평균 순위는 {dr.a:.0f} vs {dr.b:.0f}"
               f"(차이 {dr.diff:+.0f}, 오차 범위 {dr.low:+.0f} ~ {dr.high:+.0f})다. **업종을 맞추면 2026년에 처음 공시한 회사가 재무적으로 더 약하다는 근거는 없다.** 638사의 {below1 * 100 / len(all_pbr):.0f}%는 PBR이 1배 미만이고, "
               f"밸류업 계획에 PBR 목표를 적은 회사의 PBR 중앙값은 {g.a:.2f}배로 아닌 회사({g.b:.2f}배)보다 {abs(g.diff):.2f}배 {'낮다' if g.diff < 0 else '높다'}"
               f"(오차 범위 {g.low:+.2f} ~ {g.high:+.2f}).")
    text = text.replace("{summary}", summary)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=gc.REPS)
    a = ap.parse_args()
    main(a.url, a.reps)
