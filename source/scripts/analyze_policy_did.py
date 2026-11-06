"""고배당기업 배당소득 분리과세의 배당 결정 효과(이중차분)를 계산해 report/분석/배당_제도효과_분석_결과.md와 CSV로 남긴다.

실행: .venv/bin/python -m scripts.analyze_policy_did [--url ...] [--perm 1000]
- 회사 범위: partner.company의 4개 업종(제조·도소매·건설·부동산임대) 상장사 전체 = 우리 435사(겹침) + 4조 대조군.
  우리 638사 중 다른 업종 203곳은 비교할 대조군이 없어 뺀다.
- 패널·노출도·통제: source/scripts/analyze_exposure_dividend.prepare 그대로.
- 최대주주: partner.major_holder 2024 사업연도. 밸류업: partner.filing '기업가치제고계획' 첫 공시일.
DB 값은 고치지 않는다.
"""
import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from core import behavior_data as bd
from core import db
from core import exposure_dividend as ex
from core import macro_dividend as md
from core import policy_did as pd_
from scripts import analyze_exposure_dividend as ae

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report" / "분석" / "배당_제도효과_분석_결과.md"
CSV = ROOT / "report" / "분석" / "배당_제도효과_분석_결과.csv"
ANNOUNCED = "2025-07-31"  # 세제개편안 발표일. 밸류업 통제는 그 전 공시만 센다(제도 때문에 한 공시를 통제하지 않게)

UNIVERSE_SQL = "SELECT corp_code, grp, industry, listed_now FROM partner.company"
HOLDER_SQL = """
SELECT corp_code, rcept_no, nm, relate, share_class, trmend_shares, trmend_pct
FROM partner.major_holder WHERE bsns_year = 2024
"""
VALUEUP_SQL = """
SELECT corp_code, min(rcept_dt) AS first_dt FROM partner.filing
WHERE report_nm ~ '기업가치제고계획' AND report_nm !~ '예고' AND report_nm !~ '고배당기업' AND rcept_dt < %(announced)s
GROUP BY corp_code
"""

TIMELINE = [
    ("2024-07-25", "정부 2024 세법개정안에 '주주환원 촉진세제'(배당 증가분 저율 과세 등) 포함", "기획재정부 2024 세법개정안 (https://mofe.go.kr/2024/taxlaw.do)"),
    ("2024-12-10", "국회 의결에서 주주환원 촉진세제는 반영하지 않기로 수정 의결", "국회예산정책처 「2024년 개정세법 심의 결과 및 주요 내용」 (https://www.nabo.go.kr/ko/notice/releasesView.do?idx=8588)"),
    ("2025-07-31", "2025 세제개편안에 고배당기업 배당소득 분리과세 신설(정부안 최고세율 35%)", "연합뉴스 2025-08-01 (https://v.daum.net/v/20250801005500034)"),
    ("2025-12-02", "국회 통과: 14·20·25·30%(최고 30%), 2026~2028 한시", "뉴시스 2025-12-02 (https://www.newsis.com/view/NISX20251202_0003425833)"),
    ("2026-01-01", "시행. 2026 요건 판정은 2025 사업연도 숫자로(source/core/judgement.py)", "조세특례제한법 제104조의27 (report/검증/조문_코드_대응표.md)"),
]


def fmt(v, d=3) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{d}f}"


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(str(c) for c in df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False))


def did_rows(fits: list[pd_.DiD], holm_p: dict[str, float] | None = None) -> pd.DataFrame:
    return pd.DataFrame([{
        "검정": f.name, "효과(%p)": fmt(f.coef * 100, 1), "95% 범위(%p)": f"{fmt(f.low * 100, 1)} ~ {fmt(f.high * 100, 1)}",
        "p (회사 묶음)": fmt(f.p_cluster, 4), "p (무리 섞기)": fmt(f.p_perm, 4),
        **({"Holm 보정 p": fmt(holm_p.get(f.name), 4)} if holm_p is not None else {}),
        "회사·연도": f"{f.n:,}", "회사": f"{f.n_firms:,}", "2025 처리 회사": f"{f.n_treated_post:,}",
    } for f in fits])


def rate_table(p: pd.DataFrame, by: str, labels: dict) -> pd.DataFrame:
    t = pd_.raw_rates(p, by)
    t = t[t[by].isin(labels)]
    t["무리"] = t[by].map(labels)
    wide = t.pivot(index="bsns_year", columns="무리", values="mean").round(1)
    cnt = t.pivot(index="bsns_year", columns="무리", values="count")
    cols = list(labels.values())
    out = pd.DataFrame({"사업연도": wide.index})
    for c in cols:
        out[f"{c} %"] = wide[c].to_numpy()
        out[f"{c} 회사"] = cnt[c].astype(int).to_numpy()
    out["차이(%p)"] = (wide[cols[0]] - wide[cols[1]]).round(1).to_numpy()
    return out


def es_table(es: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"사업연도": es["year"], "계수(%p)": (es["coef"] * 100).round(1),
                         "95% 범위(%p)": [f"{l * 100:.1f} ~ {h * 100:.1f}" for l, h in zip(es["low"], es["high"])],
                         "p": [fmt(v, 3) for v in es["p"]]})


def verdict(prim: list[pd_.DiD], hp: dict[str, float]) -> str:
    lines = []
    for f in prim:
        sig = hp[f.name] < 0.05
        word = "늘렸어요" if f.coef > 0 else "덜 늘렸어요"
        if sig:
            lines.append(f"- **{f.name}: 2025년에 다른 해보다 {fmt(abs(f.coef) * 100, 1)}%p 더 {word}.** Holm 보정 p = {fmt(hp[f.name], 4)}로 우연이라 보기 어려워요.")
        else:
            lines.append(f"- **{f.name}: 우연과 구별되지 않아요** (효과 {fmt(f.coef * 100, 1)}%p, Holm 보정 p = {fmt(hp[f.name], 4)}).")
    return "\n".join(lines)


def main(url: str, n_perm: int) -> None:
    with db.connect(url) as conn:
        panel = pd.DataFrame(db.fetch_dicts(conn, ae.PANEL_SQL))
        lines = pd.DataFrame(db.fetch_dicts(conn, ae.LINES_SQL, {
            "borrow": ex.BORROW_NAME, "fx_cf": list(ex.FX_CF_IDS), "fx_cf_name": ex.FX_CF_NAME,
            "fx_cis": list(ex.FX_CIS_IDS), "fx_cis_name": ex.FX_CIS_NAME}))
        present = pd.DataFrame(db.fetch_dicts(conn, ae.PRESENT_SQL))
        macro = pd.DataFrame(db.fetch_dicts(conn, ae.MACRO_SQL))
        universe = pd.DataFrame(db.fetch_dicts(conn, UNIVERSE_SQL))
        holders = pd.DataFrame(db.fetch_dicts(conn, HOLDER_SQL))
        valueup = pd.DataFrame(db.fetch_dicts(conn, VALUEUP_SQL, {"announced": ANNOUNCED}))
    panel = panel[panel["corp_code"].isin(universe["corp_code"])]
    base = ae.prepare(panel, lines, present, macro)
    p = pd_.add_policy_columns(base, pd_.holder_table(holders), valueup.set_index("corp_code")["first_dt"])

    prim = [pd_.did_distance(p, n_perm=n_perm, name="기준선 거리: 가까움 vs 멂"),
            pd_.did_holder(p, n_perm=n_perm, name="개인 최대주주 회사: 최대주주가 개인, 특수관계인 포함 지분 30% 이상")]
    hp = dict(zip([f.name for f in prim], ex.holm([f.p_perm for f in prim])))
    rob = [
        pd_.did_distance(p, controls=pd_.BASE_CONTROLS, n_perm=0, name="기준선 거리 · 노출도 통제 빼고(표본 큼)"),
        pd_.did_distance(p, y="met", n_perm=0, name="기준선 거리 · 결과를 '요건 충족'으로"),
        pd_.did_distance(p, y="dir", n_perm=0, name="기준선 거리 · 결과를 주당배당금 방향(−1/0/+1, 값×100)으로"),
        pd_.did_holder(p, controls=pd_.BASE_CONTROLS, n_perm=0, name="개인 최대주주 회사 · 노출도 통제 빼고(표본 큼)"),
        pd_.did_holder(p, y="dir", n_perm=0, name="개인 최대주주 회사 · 결과를 주당배당금 방향(−1/0/+1, 값×100)으로"),
    ]
    fake = []
    for yy in range(2019, 2025):
        fake.append(pd_.did_distance(p, post_year=yy, years=(2018, 2024), n_perm=0, name=f"기준선 거리 · 가짜 제도 해 {yy}"))
        fake.append(pd_.did_holder(p, post_year=yy, years=(2018, 2024), n_perm=0, name=f"개인 최대주주 회사 · 가짜 제도 해 {yy}"))
    es_close = pd_.event_study(p, "close", sample=p["dist"].isin([pd_.CLOSE, pd_.FAR]))
    es_holder = pd_.event_study(p, "holder_high")

    allfits = prim + rob + fake
    pd.DataFrame([f.__dict__ for f in allfits]).to_csv(CSV, index=False, encoding="utf-8-sig")

    s = p.dropna(subset=["up10"])
    groups = s.groupby(["bsns_year", "dist"]).size().unstack(fill_value=0).reset_index().rename(columns={"bsns_year": "사업연도"})
    h = pd_.holder_table(holders)
    univ = universe.assign(우리=universe["corp_code"].isin(set(panel.loc[panel["group"] == "우리 638사", "corp_code"])))
    report = f"""# 고배당기업 배당소득 분리과세는 배당 결정을 바꿨나 (이중차분)

계산일 {date.today():%Y-%m-%d} · 코드 `source/core/policy_did.py`, `source/scripts/analyze_policy_did.py` · 무리 섞기 {n_perm:,}번

## 한눈에

{verdict(prim, hp)}

효과는 "배당을 10% 이상 늘린 회사 비율"이 2025년에 처리 무리에서 다른 해보다 몇 %p 더 올랐는지예요.
연도 효과가 그해 경기를 통째로 빼고, 금리·환율 노출도 × 경기 변화, Lintner 통제(순이익 변화·순이익·전년 배당), 밸류업 공시도 함께 뺐어요.

## 제도 일정

{md_table(pd.DataFrame(TIMELINE, columns=["날짜", "일", "출처"]))}

2025 사업연도 배당(2026년 1~3월 결정)이 제도를 알고 정한 첫 배당이에요. 2024 사업연도 배당은 2025년 초에 정했으니
주주환원 촉진세제가 무산된 뒤, 분리과세 발표 전이에요. 그래서 2024년 계수는 '미리 움직였나'를 보는 확인용이에요.

## 미리 정한 주 검정 2개

{md_table(did_rows(prim, hp))}

- 주 판단은 **무리 섞기 p**예요. 기준선 거리 검정은 2025년 회사들의 '가까움' 이름을, 개인 최대주주 회사 검정은 회사들의 무리 이름을 무작위로 바꿔 같은 크기 효과가 우연히 나오는 비율을 셌어요.
- Holm 보정은 이 2개에만 했어요.

## 해마다 본 계수 (사건연구, 기준 해 {pd_.BASE_YEAR} = 0)

제도 전(2018~2024) 계수가 0 근처면 두 무리가 제도 전에는 비슷하게 움직였다는 뜻이에요(평행 추세). 2025년만 튀어야 제도 효과로 읽을 수 있어요.

**기준선 거리: 가까움 − 멂**

{md_table(es_table(es_close))}

**개인 최대주주 회사 − 나머지 회사**

{md_table(es_table(es_holder))}

## 보조 검정 (참고)

{md_table(did_rows(rob))}

- **'요건 충족' 결과는 미리 정한 검정이 아니에요.** 그해 순이익에도 달려 있어서(순이익이 줄면 배당성향이 오름) 배당 결정만의 효과로 읽기 어려워요.
- **'대조군만'·'우리 회사만'으로 나눠 보지 않았어요.** 우리 회사는 2026년에 고배당기업이 된 회사, 곧 2025년 배당 결과로 뽑힌 회사예요. 둘로 나누면 결과로 무리를 고르는 셈이라 효과가 저절로 커지거나 작아져요(시험 계산에서 대조군만 보면 거리 효과가 −27%p로 튀었어요). 그래서 4개 업종 상장사 전체를 한 표본으로만 봐요.

## 가짜 제도 해 (위약 검정)

2025년을 빼고, 2019~2024년 중 한 해에 제도가 생겼다고 치고 같은 계산을 했어요. 여기서 2025년만큼 큰 효과가 자주 나오면 2025년 결과도 의심해야 해요.

{md_table(did_rows(fake))}

## 쉬운 표: 배당을 10% 이상 늘린 회사 비율 (회귀 전 단순 비율)

**기준선 거리 무리별**

{md_table(rate_table(p, "dist", {pd_.CLOSE: "가까움", pd_.FAR: "멂"}))}

**개인 최대주주 회사 무리별**

{md_table(rate_table(p.assign(hh=p["holder_high"].map({1.0: "개인 최대주주 회사", 0.0: "나머지 회사"})), "hh", {"개인 최대주주 회사": "개인 최대주주 회사", "나머지 회사": "나머지 회사"}))}

## 자료

- 회사 범위: 4개 업종 상장사 {len(universe):,}곳 (우리 {int(univ['우리'].sum()):,}곳 + 대조군 {int((~univ['우리']).sum()):,}곳, 상장폐지 포함). 원천 partner.company, partner.v_panel.
- 2024 최대주주: {len(h):,}곳 중 개인 {int((h['largest_kind'] == '개인').sum()):,}곳, 그중 지분 30% 이상 {int(h['holder_high'].sum()):,}곳. 원천 partner.major_holder (규칙 source/core/major_holder.summarize).
- 밸류업 공시: 2025-07-31 전 첫 '기업가치제고계획' 공시 {len(valueup):,}곳. 원천 partner.filing.

연도별 거리 무리 회사 수 (10% 증가 여부를 알 수 있는 회사·연도):

{md_table(groups)}

## 만든 방법

| 항목 | 정의 |
|---|---|
| 요건까지의 거리 | 전년 배당 D, 전년 순이익 NI로 '올해 순이익이 NI와 같을 때 요건을 맞추는 가장 작은 배당'을 구해 필요 증가율을 냄. 가목: 배당성향 40% 이상이고 배당이 안 줄 것 / 나목: 25% 이상이고 배당 10% 이상 증가. 둘 중 작은 쪽 |
| 무리 | 이미 충족(배당성향 40% 이상) / 가까움(필요 증가 {int(pd_.CLOSE_MAX_GROWTH * 100)}% 이하) / 멂(초과) / 무배당·적자. 해마다 다시 나눔 |
| 개인 최대주주 회사 | 2024 사업연도 최대주주가 사람(개인)이고, 최대주주+특수관계인 보통주 지분이 {pd_.HOLDER_PCT}% 이상. 회사마다 고정. 최대주주가 지주회사 같은 법인이면 배당이 그 법인으로 먼저 가서 개인 최대주주의 세금 혜택이 한 번 걸러지므로 나머지 회사로 둠 |
| 결과 | 배당총액(D)을 전년보다 10% 이상 늘렸나(0/1). 전년 배당이 있는 회사만 |
| 통제 | 순이익 변화·순이익·전년 배당(÷ 전년 자산), 금리·환율 노출도와 노출도 × 경기 변화, 밸류업 공시(2025-07-31 전 첫 공시가 그해 배당 결정 기한인 다음 해 3월 말 전이면 1) |
| 고정효과 | 회사, 연도 |
| 표준오차 | 회사 단위 묶음(CR1) |

## 한계

- **제도 뒤 연도가 2025 하나뿐이에요.** 그 해 다른 일이 처리 무리에 몰렸다면 섞여요. 가장 걸리는 후보는 2025년 상법 개정(이사가 주주 전체의 이익을 살피도록 한 개정)이에요. 개인 대주주가 지배하는 회사일수록 이 개정의 압력도 컸을 수 있어서, 대주주 검정의 효과에는 세금 말고 이 몫이 섞였을 수 있어요. 이 자료로는 둘을 가를 수 없어요.
- **거리는 '순이익이 그대로'라는 가정으로 쟀어요.** 회사는 2025년 이익을 미리 짐작하고 움직였을 거예요.
- **4개 업종 상장사만 봤어요.** 금융·서비스 등 다른 업종에는 넓혀 말할 수 없어요.
- **개인 최대주주 회사는 최대주주 한 사람 기준이에요.** 지분 30%에는 계열 법인 몫도 섞여 있어요. 실제로 아끼는 세금은 그 사람의 다른 소득과 배당 규모에 따라 달라요.
- 노출도 통제가 있는 회사(재무제표 줄이 있는 회사)만 주 검정에 들어가요. 통제를 뺀 결과는 보조 검정에 있어요.
- 상관관계를 넘어 인과로 읽으려면 '처리 무리와 나머지가 제도가 없었다면 2025년에도 같은 차이로 움직였을 것'이라는 가정이 필요해요. 위 사건연구 표가 그 가정을 확인하는 근거예요.
"""
    REPORT.write_text(report, encoding="utf-8")
    fit_recs = [{"name": f.name, "role": role, "coef": f.coef, "low": f.low, "high": f.high, "p_cluster": f.p_cluster,
                 "p_perm": f.p_perm, "p_holm": hp.get(f.name), "n": f.n, "n_firms": f.n_firms, "n_treated": f.n_treated_post}
                for role, group in [("primary", prim), ("robust", rob), ("placebo", fake)] for f in group]
    series = [{"series": key, "label": "계수", "year": int(r.year), "value": r.coef, "low": r.low, "high": r.high}
              for key, es in [("es_close", es_close), ("es_holder", es_holder)] for r in es.itertuples()]
    for key, by, labels in [("rate_close", "dist", {pd_.CLOSE: "가까움", pd_.FAR: "멂"}),
                            ("rate_holder", "holder_high", {1.0: "개인 최대주주 회사", 0.0: "나머지 회사"})]:
        t = pd_.raw_rates(p, by)
        series += [{"series": key, "label": labels[g], "year": int(y), "value": v, "n": int(n)}
                   for y, g, v, n in zip(t["bsns_year"], t[by], t["mean"], t["count"]) if g in labels]
    with db.connect(url) as conn:
        db.apply_schema(conn)
        nf, ns = bd.save(conn, "policy", fit_recs, series)
    print(f"core.core_behavior_fit {nf}행 · core.core_behavior_series {ns}행 (policy)")
    for f in allfits:
        print(f"{f.name:40s} coef={f.coef * 100:+6.2f}%p se={f.se * 100:5.2f} p_cl={f.p_cluster:.4f} p_perm={f.p_perm} n={f.n} treated={f.n_treated_post}")
    print("거리 사건연구", es_close.round(3).to_dict("records"))
    print("개인 최대주주 회사 사건연구", es_holder.round(3).to_dict("records"))
    print(f"→ {REPORT.relative_to(ROOT)}, {CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--perm", type=int, default=pd_.N_PERM)
    a = ap.parse_args()
    main(a.url, a.perm)
