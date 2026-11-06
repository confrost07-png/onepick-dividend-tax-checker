"""공시 시기별 비교(A2)와 최대주주 유형과 기준선 쏠림의 관계(A3)를 report/분석/공시시기_최대주주_비교_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_groups [--url ...] [--reps 1000]
기준 시점: 2025 사업연도(재무·배당), 2025-12-30 종가, 2025년 말 주식 수·최대주주.
"""
import argparse
import math
from datetime import date
from pathlib import Path

import numpy as np

from core import db
from core import group_compare as gc
from core import p1_analysis as p1
from core import payout_change as pc

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "공시시기_최대주주_비교_결과.md"
EARLY, LATE = "2025년까지 첫 공시", "2026년 첫 공시"
BS_IDS = {"ifrs-full_CurrentAssets": "ca", "ifrs-full_CurrentLiabilities": "cl",
          "ifrs-full_CashAndCashEquivalents": "cash", "ifrs-full_Assets": "assets"}
SQL = {
    "first": """SELECT corp_code, min(rcept_dt) AS first_dt FROM raw.policy_filing
                WHERE report_nm NOT LIKE '%%예고%%' GROUP BY corp_code""",
    "company": "SELECT corp_code, market FROM core.core_company",
    "holder": "SELECT corp_code, largest_kind, pct_common FROM core.core_major_holder",
    "judge": "SELECT corp_code, status, route FROM core.core_judgement_2026",
    "cap": "SELECT corp_code, cover_x FROM core.core_capacity_2025 WHERE status = '표시'",
    "shares": "SELECT corp_code, issued FROM core.v_share_total_checked",
    "price": "SELECT corp_code, close_adj FROM core.v_price_daily WHERE trade_date = '2025-12-30' AND close_adj IS NOT NULL",
    "dps": "SELECT corp_code, dps_common_won FROM core.v_dividend_year_verified WHERE bsns_year = 2025",
    "bs": f"""SELECT f.corp_code, f.account_id, f.thstrm_amount FROM raw.dart_financial f
              JOIN core.v_financial_year_verified v ON v.corp_code = f.corp_code AND v.bsns_year = 2025
               AND f.fs_div = CASE v.fs_basis WHEN '연결' THEN 'CFS' ELSE 'OFS' END
              WHERE f.bsns_year = 2025 AND f.sj_div = 'BS' AND f.account_id IN ({", ".join(f"'{k}'" for k in BS_IDS)})
              ORDER BY f.ord""",
}


def ratio(a, b, scale=100.0):
    return a * scale / b if a is not None and b not in (None, 0) else None


def features(data: dict, comp: dict) -> list[dict]:
    first = {r["corp_code"]: r["first_dt"] for r in data["first"]}
    one = {k: {r["corp_code"]: r for r in data[k]} for k in ("company", "holder", "judge", "cap", "shares", "price", "dps")}
    bs = {}
    for r in data["bs"]:
        bs.setdefault(r["corp_code"], {}).setdefault(BS_IDS[r["account_id"]], float(r["thstrm_amount"]) if r["thstrm_amount"] is not None else None)
    out = []
    for corp, (d, ni, bal) in comp.items():
        d25, d24, n25 = d.get(2025), d.get(2024), ni.get(2025)
        liab, eq = bal.get(2025, (None, None))
        h, sh, pr = one["holder"].get(corp, {}), one["shares"].get(corp, {}), one["price"].get(corp, {})
        mcap = float(sh["issued"]) * float(pr["close_adj"]) if sh.get("issued") and pr.get("close_adj") else None
        b = bs.get(corp, {})
        profit = n25 is not None and n25 > 0
        payout = d25 * 100 / n25 if d25 and profit else None
        dps = one["dps"].get(corp, {}).get("dps_common_won")
        out.append({
            "timing": EARLY if first.get(corp) and first[corp].year < 2026 else LATE,
            "payout": payout,
            "band_25_28": (payout is not None and 25 <= payout < 28) if payout is not None and payout >= 25 else None,
            "d_growth": ratio(d25 - d24, d24) if d25 is not None and d24 else None,
            "route_ga": one["judge"].get(corp, {}).get("route") == "가목" if one["judge"].get(corp, {}).get("status") == "충족" else None,
            "roe": ratio(n25, eq) if eq and eq > 0 else None,
            "debt": ratio(liab, eq) if eq and eq > 0 else None,
            "current": ratio(b.get("ca"), b.get("cl")),
            "cash_share": ratio(b.get("cash"), b.get("assets")),
            "cover": float(one["cap"][corp]["cover_x"]) if corp in one["cap"] and one["cap"][corp]["cover_x"] is not None else None,
            "holder_kind": h.get("largest_kind"),
            "holder_person": {"개인": True, "법인": False}.get(h.get("largest_kind")),
            "holder_pct": float(h["pct_common"]) if h.get("pct_common") is not None else None,
            "mcap_eok": mcap / 1e8 if mcap else None,
            "pbr": mcap / eq if mcap and eq and eq > 0 else None,
            "yield": ratio(float(dps), float(pr["close_adj"])) if dps and pr.get("close_adj") else None,
            "kosdaq": one["company"].get(corp, {}).get("market") == "코스닥",
            "profit": profit,
        })
    return out


MEDIANS = [("배당성향(%)", "payout"), ("배당 증가율(%)", "d_growth"), ("ROE(%)", "roe"), ("부채비율(%)", "debt"),
           ("유동비율(%)", "current"), ("현금 비중(자산 대비 %)", "cash_share"), ("잉여현금흐름 ÷ 2027 최소 배당(배)", "cover"),
           ("최대주주 지분율(%)", "holder_pct"), ("시가총액(억 원)", "mcap_eok"), ("주가순자산배율(PBR, 배)", "pbr"),
           ("시가배당률(%)", "yield")]
SHARES = [("배당성향 25~28%에 있는 비율", "band_25_28"), ("가목(40% 이상)으로 충족한 비율", "route_ga"),
          ("최대주주가 개인인 비율", "holder_person"), ("코스닥 비율", "kosdaq"), ("2025 흑자 비율", "profit")]


def fmt_diff(d: gc.Diff, digits=1) -> str:
    sure = "예" if d.low > 0 or d.high < 0 else "아니오"
    f = f"{{:.{digits}f}}"
    return (f"| {f.format(d.a)} ({d.n_a}) | {f.format(d.b)} ({d.n_b}) | {d.diff:+.{digits}f} | "
            f"{d.low:+.{digits}f} ~ {d.high:+.{digits}f} | {sure} |")


def compare_table(rs, key, ga, gb, reps, skip=()) -> str:
    head = (f"| 항목 | {ga} (회사 수) | {gb} (회사 수) | 차이 | 오차 범위(95%) | 확실한 차이 |\n|---|---|---|---|---|---|")
    lines = [head]
    for label, k in MEDIANS:
        d = gc.median_diff([r[k] for r in rs if r[key] == ga], [r[k] for r in rs if r[key] == gb], reps)
        lines.append(f"| {label} · 중앙값 " + fmt_diff(d, 2 if k in ("pbr", "cover", "yield") else 0 if k == "mcap_eok" else 1))
    for label, k in SHARES:
        if k in skip:
            continue
        d = gc.share_diff([r[k] for r in rs if r[key] == ga], [r[k] for r in rs if r[key] == gb], reps)
        lines.append(f"| {label}(%) " + fmt_diff(d))
    return "\n".join(lines)


MODEL = [("최대주주가 개인", "holder_person", 1.0), ("최대주주 지분율 10%p 높을 때", "holder_pct", 10.0),
         ("2026년 첫 공시", "late", 1.0), ("ROE 10%p 높을 때", "roe", 10.0), ("부채비율 100%p 높을 때", "debt", 100.0),
         ("코스닥", "kosdaq", 1.0), ("시가총액 10배 클 때", "log_mcap", 1.0)]


def model_table(rs) -> tuple[str, int]:
    rows = []
    for r in rs:
        if r["band_25_28"] is None:
            continue
        v = {**r, "late": r["timing"] == LATE, "log_mcap": math.log10(r["mcap_eok"]) if r["mcap_eok"] else None}
        x = [v[k] for _, k, _ in MODEL]
        if any(e is None for e in x):
            continue
        rows.append(([float(e) / s for e, (_, _, s) in zip(x, MODEL)], float(r["band_25_28"])))
    x = np.array([a for a, _ in rows])
    y = np.array([b for _, b in rows])
    terms = gc.logistic(x, y, [n for n, _, _ in MODEL])
    lines = ["| 특징 | 가능성 배수(오즈비) | 오차 범위(95%) | 우연일 확률(p) |", "|---|---|---|---|"]
    for t in terms[1:]:
        lines.append(f"| {t.name} | {t.odds:.2f}배 | {t.odds_low:.2f} ~ {t.odds_high:.2f} | {t.p:.3f} |")
    return "\n".join(lines), len(rows)


def cross_table(rs) -> str:
    sub = [r for r in rs if r["band_25_28"] is not None and r["holder_person"] is not None and r["holder_pct"] is not None]
    cuts = np.percentile([r["holder_pct"] for r in sub], [33.3, 66.7])
    labels = [f"{cuts[0]:.0f}% 미만", f"{cuts[0]:.0f}~{cuts[1]:.0f}%", f"{cuts[1]:.0f}% 이상"]
    lines = ["| 최대주주 | " + " | ".join(f"지분율 {l}" for l in labels) + " |", "|---|---|---|---|"]
    for kind, flag in (("개인", True), ("법인", False)):
        cells = []
        for i in range(3):
            g = [r for r in sub if r["holder_person"] == flag and (i == 0 and r["holder_pct"] < cuts[0] or
                 i == 1 and cuts[0] <= r["holder_pct"] < cuts[1] or i == 2 and r["holder_pct"] >= cuts[1])]
            hit = sum(1 for r in g if r["band_25_28"])
            cells.append(f"{hit}/{len(g)} ({hit * 100 / len(g):.0f}%)" if g else "-")
        lines.append(f"| {kind} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(url: str | None, reps: int):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        data = {k: db.fetch_dicts(conn, q) for k, q in SQL.items()}
    rs = features(data, comp)
    n_early = sum(1 for r in rs if r["timing"] == EARLY)
    model, n_model = model_table(rs)
    hk = [r for r in rs if r["holder_kind"] in ("개인", "법인")]
    for r in hk:
        r["holder_group"] = "최대주주 개인" if r["holder_kind"] == "개인" else "최대주주 법인"

    text = f"""# 공시 시기·최대주주 비교 — 누가 25% 기준선에 맞췄나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_groups.py`, `source/core/group_compare.py` · 설계: `report/설계/데이터_분석_설계.md` A2·A3
- 기준 시점: 2025 사업연도 재무·배당(`v_*_verified`, 팀 검토본 반영), 2025-12-30 종가(`v_price_daily`), 2025년 말 보통주 수(`v_share_total_checked`)·최대주주(`core_major_holder`), 재무상태표(`raw.dart_financial`, 판정과 같은 연결·별도 기준), 배당 여력(`core_capacity_2025`)
- 무리 나누기: 밸류업 계획 첫 공시일(`raw.policy_filing`, 예고 공시 제외). {EARLY} {n_early}사, {LATE} {len(rs) - n_early}사
- 오차 범위: 무리마다 회사를 무작위로 다시 뽑아 {reps}번 계산한 값의 가운데 95%(시드 {gc.SEED}). 0을 포함하지 않으면 '확실한 차이'
- 값이 없는 회사는 그 항목에서만 빠진다(괄호 안 회사 수). 배당성향·25~28% 비율은 흑자 회사만, ROE·부채비율·PBR은 자본이 양수인 회사만

## 한 줄 결과

{{summary}}

## 1. 공시 시기별 비교 (A2)

{compare_table(rs, "timing", EARLY, LATE, reps)}

## 2. 최대주주 유형별 비교 (A3)

{compare_table(hk, "holder_group", "최대주주 개인", "최대주주 법인", reps, skip=("holder_person",))}

## 3. 다른 조건이 같아도 차이가 남나 — 예측 모델 (A3)

결과: 2025 배당성향이 25~28%인가(1) 아니면 28% 이상인가(0). 대상: 2025 흑자·배당성향 25% 이상이고 모든 특징 값이 있는 **{n_model}사**.
'가능성 배수'는 다른 특징이 같을 때 그 특징이 25~28%에 있을 가능성(오즈)을 몇 배로 바꾸는지다. 1보다 크면 25~28%에 있기 쉽고, 오차 범위가 1을 포함하면 확실하지 않다.

{model}

## 4. 최대주주 유형 × 지분율별 25~28%에 있는 비율

지분율은 2025 흑자·배당성향 25% 이상 회사를 셋으로 나눈 구간이다.

{cross_table(rs)}

## 5. 읽을 때 주의

- **관계이지 원인이 아니다.** 예를 들어 최대주주가 개인인 회사가 25~28%에 많다는 것은 "개인 대주주 때문에 배당을 맞췄다"는 증거가 아니다. 회사 규모나 업종처럼 모델에 없는 특징이 함께 움직였을 수 있다.
- 최대주주 지분율은 특수관계인을 포함한 보통주 기준, 2025년 말 한 시점 값이다. 법인 최대주주 뒤의 개인은 알 수 없다.
- 시가총액은 2025년 말 보통주 수 × 2025-12-30 수정 종가다. 2026년에 분할·병합한 회사는 수정 종가가 바뀌어 조금 어긋날 수 있다.
- ROE가 높을수록 25~28%에 있기 쉬운 것은 자연스럽다. 순이익이 크면 같은 배당이라도 배당성향이 낮아지므로, 버는 만큼 다 주기보다 기준선만 맞춘 회사가 여기에 모인다.
- 일찍 공시한 회사의 부채비율이 높고 유동비율이 낮은 것은 은행·보험 같은 금융업이 이 무리에 많기 때문으로 보인다(`core_capacity_2025` 기준 금융업 비율: 일찍 공시 18/90사 = 20%, 2026년 첫 공시 30/548사 = 5.5%). 금융업은 부채비율이 원래 높다. 업종을 나눈 비교는 B3에서 한다.
- 638사는 2025년에 고배당기업 요건을 넘긴 회사만이다.
"""

    def d_of(key, ga, gb, k, share=False, pool=rs):
        f = gc.share_diff if share else gc.median_diff
        return f([r[k] for r in pool if r[key] == ga], [r[k] for r in pool if r[key] == gb], reps)

    t25 = d_of("timing", EARLY, LATE, "band_25_28", True)
    h25 = d_of("holder_group", "최대주주 개인", "최대주주 법인", "band_25_28", True, hk)
    summary = (f"배당성향 25~28%에 있는 비율은 일찍 공시한 회사 {t25.a:.1f}% vs 2026년에 처음 공시한 회사 {t25.b:.1f}%"
               f"(차이 {t25.diff:+.1f}%p, 오차 범위 {t25.low:+.1f} ~ {t25.high:+.1f}), "
               f"최대주주가 개인인 회사 {h25.a:.1f}% vs 법인인 회사 {h25.b:.1f}%(차이 {h25.diff:+.1f}%p, 오차 범위 {h25.low:+.1f} ~ {h25.high:+.1f})다.")
    text = text.replace("{summary}", summary)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--reps", type=int, default=gc.REPS)
    a = ap.parse_args()
    main(a.url, a.reps)
