"""금리·환율 노출도와 배당 결정을 계산해 report/분석/배당_노출도_분석_결과.md와 CSV로 남긴다 (source/core/exposure_dividend.py).

실행: .venv/bin/python -m scripts.analyze_exposure_dividend [--url ...] [--perm 2000]
- 회사×연도: partner.v_panel (우리 638사 + 4조 대조군). 배당 칸이 '원문 배당 표 값 - (배당 없음)'이면 0으로 본다.
- 차입금·외화 항목·자산총계: partner.fs_line (DART 전체 재무제표 줄).
- 거시: raw.ecos_macro → core.macro_dividend.macro_annual (기준금리·국고채 3년 연평균 변화, 원/달러 연평균 변화율).
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

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report" / "분석" / "배당_노출도_분석_결과.md"
CSV = ROOT / "report" / "분석" / "배당_노출도_분석_결과.csv"
NO_DIVIDEND = "배당 없음"

PANEL_SQL = """
SELECT v.source AS "group", v.corp_code, v.corp_name, v.bsns_year, v.fs_basis, v.ni_owner_won, v.assets_won,
       v.d_won, v.dps_common_won, v.d_reason, left(c.ksic_code, 2) AS ksic2
FROM partner.v_panel v LEFT JOIN partner.company c USING (corp_code)
WHERE v.bsns_year BETWEEN 2016 AND 2025
"""
LINES_SQL = """
SELECT corp_code, bsns_year, fs_div, sj_div, account_id, account_nm, thstrm_amount
FROM partner.fs_line
WHERE bsns_year BETWEEN 2016 AND 2025 AND thstrm_amount IS NOT NULL AND (
     (sj_div = 'BS' AND (account_nm ~ %(borrow)s OR account_id IN ('ifrs-full_Assets', 'ifrs_Assets') OR account_nm = '자산총계'))
  OR (sj_div = 'CF' AND (account_id = ANY(%(fx_cf)s) OR account_nm ~ %(fx_cf_name)s))
  OR (sj_div IN ('CIS', 'IS') AND (account_id = ANY(%(fx_cis)s) OR account_nm ~ %(fx_cis_name)s)))
"""
PRESENT_SQL = "SELECT DISTINCT corp_code, bsns_year, fs_div, sj_div FROM partner.fs_line WHERE bsns_year BETWEEN 2016 AND 2025"
MACRO_SQL = "SELECT series, cycle, period_start, value FROM raw.ecos_macro"

PRIMARY = [
    ("금리 × 차입", "dir", "rate_exp", "base_rate_chg"),
    ("환율 × 외화 노출", "dir", "fx_exp", "usdkrw_growth"),
]
LABEL = {"rate_exp": "차입금 노출", "fx_exp": "외화 노출", "base_rate_chg": "기준금리 변화(%p)",
         "usdkrw_growth": "원/달러 변화율(%)", "ktb3y_chg": "국고채 3년 변화(%p)", "dir": "주당배당금 방향",
         "dir_total": "배당총액 방향"}
SHORT = {"base_rate_chg": "기준금리", "usdkrw_growth": "원/달러"}


def assets_from_lines(lines: pd.DataFrame) -> pd.DataFrame:
    bs = lines[(lines["sj_div"] == "BS") & (lines["account_id"].isin(["ifrs-full_Assets", "ifrs_Assets"])
                                           | (lines["account_nm"] == "자산총계"))]
    out = bs.assign(v=bs["thstrm_amount"].astype(float)).groupby(["corp_code", "bsns_year", "fs_div"])["v"].max()
    return out.rename("assets_line").reset_index()


def prepare(panel: pd.DataFrame, lines: pd.DataFrame, present: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    none = p["d_reason"].fillna("").str.contains(NO_DIVIDEND)
    p["d_won"] = p["d_won"].astype(float).where(p["d_won"].notna() | ~none, 0.0)
    p["dps_common_won"] = p["dps_common_won"].astype(float).where(p["dps_common_won"].notna() | ~none, 0.0)
    bs_present = present[present["sj_div"] == "BS"]
    cf_present = present[present["sj_div"].isin(["CF", "CIS", "IS"])]
    p["borrow_won"] = ex.attach_lines(p, ex.borrowings(lines), bs_present, "borrow_won")
    p["fx_won"] = ex.attach_lines(p, ex.fx_items(lines), cf_present, "fx_won")
    a = ex.attach_lines(p, assets_from_lines(lines), bs_present, "assets_line")
    p["assets_won"] = a.where(a > 0, p["assets_won"].astype(float))
    out = ex.build_panel(p, md.macro_annual(macro))
    out["ind_year"] = out["ksic2"].fillna("??") + "_" + out["bsns_year"].astype(str)
    return out[out["bsns_year"].between(2018, 2025)]


def run(df: pd.DataFrame, n_perm: int) -> list[ex.Fit]:
    fits = [ex.fit(df, y, e, m, name=n, n_perm=n_perm) for n, y, e, m in PRIMARY]
    ours, ctrl = df[df["group"] == "우리 638사"], df[df["group"] == "4조 대조군"]
    for n, y, e, m in PRIMARY:
        fits += [
            ex.fit(ctrl, y, e, m, name=f"{n} · 대조군만", n_perm=n_perm),
            ex.fit(ours, y, e, m, name=f"{n} · 우리 638사만", n_perm=n_perm),
            ex.fit(df, "dir_total", e, m, name=f"{n} · 결과를 배당총액 방향으로", n_perm=n_perm),
            ex.fit(df, y, e, m, name=f"{n} · 업종×연도 효과", fe=("corp_code", "ind_year"), n_perm=n_perm),
            ex.fit(df, y, e, f"{m}_prev", name=f"{n} · 1년 전 경기", n_perm=n_perm),
            ex.fit(df, y, e, f"{m}_next", name=f"{n} · 위약: 다음 해 경기", n_perm=n_perm),
        ]
    fits.append(ex.fit(df, "dir", "rate_exp", "ktb3y_chg", name="금리 × 차입 · 국고채 3년으로", n_perm=n_perm))
    return fits


def fmt(v, d=3) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{d}f}"


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False))


def fit_rows(fits: list[ex.Fit], holm_p: dict[str, float] | None = None) -> pd.DataFrame:
    return pd.DataFrame([{
        "검정": f.name, "계수": fmt(f.coef), "95% 범위": f"{fmt(f.low)} ~ {fmt(f.high)}",
        "p (회사 묶음)": fmt(f.p_cluster, 4), "p (연도 섞기)": fmt(f.p_perm, 4),
        **({"Holm 보정 p": fmt(holm_p.get(f.name), 4)} if holm_p is not None else {}),
        "회사·연도": f"{f.n:,}", "회사": f"{f.n_firms:,}", "연도": f.n_years,
    } for f in fits])


def verdict(prim: list[ex.Fit], hp: dict[str, float]) -> str:
    if all(hp[f.name] >= 0.05 for f in prim):
        return ("**두 검정 모두 우연과 구별되지 않아요.** 금리·환율 변화를 더 크게 받는 회사가 배당을 다르게 정했다는 근거를 "
                "이 자료에서 찾지 못했어요.")
    hit = [f.name for f in prim if hp[f.name] < 0.05]
    return f"**보정 뒤에도 우연이라 보기 어려운 검정: {', '.join(hit)}.** 아래 보조 검정과 위약 검정으로 흔들리지 않는지 함께 봐야 해요."


def report(df: pd.DataFrame, fits: list[ex.Fit], macro_year: pd.DataFrame, n_perm: int) -> str:
    prim = fits[:2]
    hp = dict(zip([f.name for f in prim], ex.holm([f.p_perm for f in prim])))
    rest = fits[2:]
    sample = df.dropna(subset=["dir", *ex.CONTROLS])
    cover = pd.DataFrame([{
        "무리": g, "회사·연도 (결과·통제 있음)": f"{len(s):,}",
        "차입금 노출 있음": f"{s['rate_exp'].notna().sum():,}", "외화 노출 있음": f"{s['fx_exp'].notna().sum():,}",
        "줄임 %": fmt((s['dir'] < 0).mean() * 100, 1), "그대로 %": fmt((s['dir'] == 0).mean() * 100, 1),
        "올림 %": fmt((s['dir'] > 0).mean() * 100, 1),
    } for g, s in [("전체", sample), *sample.groupby("group")]])
    mac = macro_year.loc[2018:2025, ["base_rate_chg", "usdkrw_growth", "ktb3y_chg"]].round(2).reset_index()
    mac.columns = ["연도", "기준금리 변화(%p)", "원/달러 변화율(%)", "국고채 3년 변화(%p)"]
    terc = []
    for e, m in [("rate_exp", "base_rate_chg"), ("fx_exp", "usdkrw_growth")]:
        t = ex.tercile_table(df, e, m)
        for r in t.itertuples():
            terc.append({"경기": f"{SHORT[m]} {r.when}", "회사": r.band, "회사·연도": r.n,
                         "줄인 비율 %": fmt(r.cut, 1), "올린 비율 %": fmt(r.up, 1)})
    lt = [{"무리": g, **{k: (fmt(v) if k != "n" else f"{v:,}") for k, v in ex.lintner(s).items()}}
          for g, s in [("전체", df), *df.groupby("group")]]
    lt = pd.DataFrame(lt).rename(columns={"b": "순이익 계수 b", "speed": "조정 속도 c", "target_payout": "목표 배당성향 b/c", "n": "회사·연도"})
    rate, fx = prim
    return f"""# 금리·환율 노출도와 배당 결정 (회사×연도 패널)

계산일 {date.today():%Y-%m-%d} · 코드 `source/core/exposure_dividend.py`, `source/scripts/analyze_exposure_dividend.py` · 순열 {n_perm:,}번

## 묻는 것

같은 해 같은 금리·환율 변화를 겪어도, **그 변화를 더 크게 받는 회사가 배당을 다르게 정했나?**
8장 연도별 상관은 경기 값이 해마다 하나라 비교할 거리가 8개뿐이었어요. 여기서는 회사마다 받는 크기(노출도)가
다르다는 점을 써요. 연도 효과로 그해 모든 회사가 함께 겪은 분위기를 빼고, 회사 효과로 회사마다 원래 배당 성향을 뺀 뒤
'노출도 × 경기 변화' 계수를 봐요.

## 한 줄 결론

- 금리 × 차입: 계수 {fmt(rate.coef)} (95% 범위 {fmt(rate.low)} ~ {fmt(rate.high)}), 연도 섞기 p = {fmt(rate.p_perm, 4)}, Holm 보정 p = {fmt(hp[rate.name], 4)}
- 환율 × 외화 노출: 계수 {fmt(fx.coef)} (95% 범위 {fmt(fx.low)} ~ {fmt(fx.high)}), 연도 섞기 p = {fmt(fx.p_perm, 4)}, Holm 보정 p = {fmt(hp[fx.name], 4)}

{verdict(prim, hp)}

계수 읽는 법: 노출도가 가장 적은 회사(0)에서 가장 큰 회사(1)로 갈 때, 경기 변화 1단위(기준금리 1%p, 원/달러 1%)마다
배당 방향 점수(줄임 −1 · 그대로 0 · 올림 +1)가 얼마나 달라지는지예요. 음수면 '그 변화를 크게 받는 회사일수록 배당을 덜 올렸다'는 뜻이에요.

## 미리 정한 주 검정 2개

{md_table(fit_rows(prim, hp))}

- 주 판단은 **연도 섞기 p**예요. 경기 값은 해마다 하나라, 회사 단위로 묶은 표준오차는 같은 해 회사들이 함께 받는 충격을 다 담지 못해요.
- 연도가 8개라 연도 섞기로 나올 수 있는 경우의 수가 많지 않아요(8! = 40,320가지). p가 아주 작게는 잘 나오지 않아요.
- Holm 보정은 이 2개에만 했어요. 아래 보조 검정은 결론을 바꾸지 않고, 결과가 흔들리지 않는지 보는 용도예요.

## 보조 검정 (참고)

{md_table(fit_rows(rest))}

- **위약: 다음 해 경기**는 배당을 정한 뒤에 일어난 경기 변화예요. 여기서 관계가 나오면 앞의 결과도 우연이나 다른 원인일 수 있다고 봐야 해요. 2025년은 다음 해 연간 값이 없어 빠져요.
- **업종×연도 효과**는 같은 해 같은 업종(KSIC 앞 두 자리) 회사끼리만 비교해요. 노출도가 업종과 얽힌 몫을 빼는 확인이에요.
- **우리 638사만**은 2025년에 배당을 많이 한 회사만 골라 만든 무리라, 결과를 보고 고른 무리예요. 대조군만으로 본 값과 함께 읽어요.

## 쉬운 표: 노출도 위·아래 3분의 1 회사의 행동

연도·회사 효과를 빼지 않은 단순 비율이에요. 위 회귀의 방향을 눈으로 확인하는 용도예요.

{md_table(pd.DataFrame(terc))}

## Lintner 부분조정 (기본 행동)

ΔD/A = a + b·(순이익/A) − c·(전년 배당/A) + 연도 효과. c는 목표 배당 쪽으로 한 해에 얼마나 다가가는지(조정 속도), b/c는 목표 배당성향이에요.
배당은 이익을 따라 천천히 움직인다는 게 Lintner(1956)의 관찰이에요. 위 회귀에서는 이 몫(순이익 변화·순이익·전년 배당)을 통제로 넣었어요.

{md_table(lt)}

## 자료

{md_table(cover)}

연도별 경기 값 (raw.ecos_macro, 연평균의 전년 대비):

{md_table(mac)}

## 만든 방법

| 항목 | 정의 | 출처 |
|---|---|---|
| 결과 | 주당배당금(보통주) 전년 대비 방향 −1/0/+1. 보조로 배당총액 방향 | partner.v_panel `dps_common_won`, `d_won` |
| 무배당 | 배당 칸이 비어 있고 이유가 '원문 배당 표 값 - (배당 없음)'이면 0. 그해 사업보고서가 없으면 빈칸 | partner.v_panel `d_reason` |
| 차입금 노출 | 전년 말 재무상태표에서 이름에 '차입금'·'사채'가 든 줄 합계 ÷ 전년 말 자산총계. 할인·조정·이자 줄은 뺌. 재무상태표가 있는데 그런 줄이 없으면 0 | partner.fs_line (BS) |
| 외화 노출 | 전년 \\|현금흐름표 외화환산이익\\| + \\|외화환산손실\\| + \\|포괄손익계산서 해외사업장 환산차이\\| ÷ 전년 말 자산총계 | partner.fs_line (CF, CIS) |
| 노출도 순위 | 같은 해 회사끼리 순위를 0~1로 바꿈 (극단값과 계정 중복의 영향을 줄임) | 계산 |
| 자산총계 | fs_line `ifrs-full_Assets`·'자산총계', 없으면 v_panel `assets_won` | partner.fs_line, partner.v_panel |
| 재무제표 기준 | 패널 기준(연결→CFS, 별도→OFS)을 먼저, 없으면 다른 쪽 | |
| 통제 | 순이익 변화, 순이익, 전년 배당 (모두 ÷ 전년 자산, 위아래 1% 눌러 씀) | partner.v_panel |
| 고정효과 | 회사, 연도 (보조: 회사, 업종×연도) | |
| 표준오차 | 회사 단위 묶음(CR1), 정규 근사 | |
| 순열검정 | 연도별 경기 값을 연도끼리 섞고 다시 계산, {n_perm:,}번 | |

## 한계

- **연도가 8개뿐이에요(2018~2025).** 노출도 차이를 써도 경기 충격 자체는 8번이에요. 한 해(2020 코로나, 2022 금리 급등, 2025 세제 개편)가 결과를 크게 흔들 수 있어요.
- **노출도는 대략적인 값이에요.** 차입금은 계정 이름으로 모아서 합계와 세부 줄이 겹치는 회사가 있을 수 있어요. 외화 항목은 수출 비중이 아니라 환율이 움직였을 때 장부에 잡힌 크기예요. 수출 비중은 사업보고서 본문에만 있어 쓰지 못했어요.
- **우리 638사 중 203곳은 재무제표 줄(fs_line)이 없어** 노출도를 구하지 못했어요. 그래서 '우리 638사만' 결과는 435곳 기준이에요.
- **주당배당금은 액면분할·병합 때 크게 바뀌어요.** 그래서 배당총액 방향으로도 확인했어요.
- 상관관계이고 인과가 아니에요. 노출도가 큰 회사는 다른 점(규모, 업종, 성장성)도 다를 수 있어요.
"""


def fit_records(fits: list[ex.Fit]) -> list[dict]:
    holm_p = dict(zip([f.name for f in fits[:2]], ex.holm([f.p_perm for f in fits[:2]])))
    return [{"name": f.name, "role": "primary" if i < 2 else "placebo" if "위약" in f.name else "robust",
             "coef": f.coef, "low": f.low, "high": f.high, "p_cluster": f.p_cluster, "p_perm": f.p_perm,
             "p_holm": holm_p.get(f.name), "n": f.n, "n_firms": f.n_firms, "n_treated": None} for i, f in enumerate(fits)]


def series_records(df: pd.DataFrame) -> list[dict]:
    """노출도 위·아래 3분의 1 × 경기 오른 해·내린 해의 배당 올린·줄인 비율(%). label = '금리|오른 해|크게 받는 회사(위 1/3)'"""
    out = []
    for e, m in [("rate_exp", "base_rate_chg"), ("fx_exp", "usdkrw_growth")]:
        for r in ex.tercile_table(df, e, m).itertuples():
            label = f"{SHORT[m]}|{r.when}|{r.band}"
            out.append({"series": "tercile_up", "label": label, "year": 0, "value": r.up, "n": r.n})
            out.append({"series": "tercile_cut", "label": label, "year": 0, "value": r.cut, "n": r.n})
    return out


def main(url: str, n_perm: int) -> None:
    with db.connect(url) as conn:
        panel = pd.DataFrame(db.fetch_dicts(conn, PANEL_SQL))
        lines = pd.DataFrame(db.fetch_dicts(conn, LINES_SQL, {
            "borrow": ex.BORROW_NAME, "fx_cf": list(ex.FX_CF_IDS), "fx_cf_name": ex.FX_CF_NAME, "fx_cis": list(ex.FX_CIS_IDS), "fx_cis_name": ex.FX_CIS_NAME}))
        present = pd.DataFrame(db.fetch_dicts(conn, PRESENT_SQL))
        macro = pd.DataFrame(db.fetch_dicts(conn, MACRO_SQL))
    df = prepare(panel, lines, present, macro)
    fits = run(df, n_perm)
    pd.DataFrame([f.__dict__ for f in fits]).to_csv(CSV, index=False, encoding="utf-8-sig")
    REPORT.write_text(report(df, fits, md.macro_annual(macro), n_perm), encoding="utf-8")
    with db.connect(url) as conn:
        db.apply_schema(conn)
        nf, ns = bd.save(conn, "exposure", fit_records(fits), series_records(df))
    print(f"core.core_behavior_fit {nf}행 · core.core_behavior_series {ns}행 (exposure)")
    for f in fits:
        print(f"{f.name:40s} coef={f.coef:+.4f} se={f.se:.4f} p_cl={f.p_cluster:.4f} p_perm={f.p_perm:.4f} n={f.n}")
    print(f"→ {REPORT.relative_to(ROOT)}, {CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--perm", type=int, default=ex.N_PERM)
    a = ap.parse_args()
    main(a.url, a.perm)
