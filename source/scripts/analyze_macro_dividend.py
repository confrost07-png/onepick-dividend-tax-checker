"""배당과 거시지표의 상관을 계산해 report/분석/배당_거시지표_상관_결과.md와 CSV로 남긴다 (source/core/macro_dividend.py).

실행: .venv/bin/python -m scripts.analyze_macro_dividend [--url ...]
먼저 scripts.collect_macro → scripts.load_macro로 raw.ecos_macro를 채워 둔다.
배당은 core.v_dividend_year_verified(검토 확정 값 우선), 시가배당률은 raw.dart_dividend_item '현금배당수익률(%)' 보통주.
DB 값은 고치지 않는다. 배당총액이 같은 회사 다른 해 중앙값의 1,000배를 넘는 칸은 원천 오류로 보고 합계에서만 뺀다.
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from core import db
from core import macro_dividend as md

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report" / "분석" / "배당_거시지표_상관_결과.md"
YEARS = range(2017, 2026)  # 2026 사업연도는 7사뿐이라 뺀다
OUTLIER_RATIO = 1000

DIV_SQL = """
SELECT v.corp_code, k.corp_name, v.bsns_year, v.d_dart_won, v.dps_common_won
FROM core.v_dividend_year_verified v JOIN core.core_company k USING (corp_code)
WHERE v.bsns_year BETWEEN 2017 AND 2025
"""
YIELD_SQL = """
SELECT DISTINCT ON (corp_code, bsns_year) corp_code, bsns_year, value::numeric AS yield_pct
FROM raw.dart_dividend_item
WHERE item = '현금배당수익률(%)' AND stock_kind IN ('보통주', '보통주식') AND value ~ '^-?[0-9]+(\\.[0-9]+)?$'
  AND bsns_year BETWEEN 2017 AND 2025
ORDER BY corp_code, bsns_year, (stock_kind = '보통주') DESC
"""
MACRO_SQL = "SELECT series, cycle, period_start, value FROM raw.ecos_macro"


def outliers(div: pd.DataFrame) -> pd.DataFrame:
    d = div.assign(v=div["d_dart_won"].astype(float))
    med = d[d["v"] > 0].groupby("corp_code")["v"].median()
    d["company_median"] = d["corp_code"].map(med)
    return d[d["v"] > d["company_median"] * OUTLIER_RATIO]


def fmt(v, digits=2) -> str:
    return "" if pd.isna(v) else f"{v:,.{digits}f}"


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False))


def main(url: str) -> None:
    with db.connect(url) as conn:
        div = pd.DataFrame(db.fetch_dicts(conn, DIV_SQL))
        yields = pd.DataFrame(db.fetch_dicts(conn, YIELD_SQL))
        macro = pd.DataFrame(db.fetch_dicts(conn, MACRO_SQL))
    bad = outliers(div)
    exclude = set(zip(bad["corp_code"], bad["bsns_year"]))
    macro_year = md.macro_annual(macro)
    div_year = md.dividend_annual(div, yields, exclude)
    p = md.panel(div)
    yt = md.year_table(div_year, macro_year, YEARS)
    dt = md.diff_table(div_year, macro_year, YEARS)
    pt = md.panel_table(p, macro_year)
    lagged_macro = md.macro_lagged(macro)
    lagged = lag_tables(div_year, p, lagged_macro)

    out = ROOT / "report" / "분석"
    div_year.join(macro_year).loc[list(YEARS)].round(4).to_csv(out / "배당_거시지표_연도표.csv", encoding="utf-8-sig")
    yt.round(4).to_csv(out / "배당_거시지표_상관_연도.csv", index=False, encoding="utf-8-sig")
    dt.round(4).to_csv(out / "배당_거시지표_상관_연도차이.csv", index=False, encoding="utf-8-sig")
    pt.round(4).to_csv(out / "배당_거시지표_상관_회사연도.csv", index=False, encoding="utf-8-sig")
    lagged.round(4).to_csv(out / "배당_거시지표_상관_시차.csv", index=False, encoding="utf-8-sig")
    REPORT.write_text(report(div_year, macro_year, yt, dt, pt, bad) + lag_report(lagged), encoding="utf-8")
    with db.connect(url) as conn:
        db.apply_schema(conn)
        year = div_year.join(macro_year)
        for key in ("prev", "decision"):  # 시차 거시 값도 같이 둔다: 화면 산점도가 상관을 낸 그 값을 그대로 쓴다
            year = year.join(lagged_macro[key].add_suffix(f"@{key}"))
        n_year = db.replace_rows(conn, "core.core_macro_dividend_year", md.year_rows(year.loc[list(YEARS)]))
        n_corr = db.replace_rows(conn, "core.core_macro_dividend_corr", md.corr_rows(lagged))
    print(f"  {REPORT.relative_to(ROOT)} 외 CSV 5개 · core.core_macro_dividend_year {n_year:,}행 · _corr {n_corr:,}행")


def lag_tables(div_year: pd.DataFrame, p: pd.DataFrame, lagged: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """시차별 세 갈래(수준·차이·회사×연도) 상관을 한 표로. kind: level / diff / panel"""
    parts = []
    for key, label in md.LAGS:
        m = lagged[key]
        for kind, t in [("level", md.year_table(div_year, m, YEARS)), ("diff", md.diff_table(div_year, m, YEARS)),
                        ("panel", md.panel_table(p, m)),
                        ("panel_ex2025", md.panel_table(p[p["bsns_year"] != 2025], m))]:
            t = t.rename(columns={"target": "dividend", "target_label": "dividend_label", "p_by_year": "spearman_p"})
            parts.append(t.assign(lag=key, lag_label=label, kind=kind))
    cols = ["lag", "lag_label", "kind", "dividend", "dividend_label", "macro", "macro_label", "n", "rows", "years",
            "spearman", "spearman_p"]
    return pd.concat(parts, ignore_index=True).reindex(columns=cols)


KIND_LABEL = {"level": "연도 수준", "diff": "연도 차이(추세 제거)", "panel": "회사×연도",
              "panel_ex2025": "회사×연도(2025 제외)"}


def lag_report(t: pd.DataFrame) -> str:
    lag_labels = dict(md.LAGS)
    count = (t.assign(sig=t["spearman_p"] < 0.05).groupby(["kind", "lag"])["sig"].agg(["sum", "count"]).reset_index())
    cshow = pd.DataFrame({
        "갈래": [KIND_LABEL[k] for k in count["kind"]], "시차": [lag_labels[l] for l in count["lag"]],
        "p < 0.05 짝": [f"{int(a)} / {int(b)}" for a, b in zip(count["sum"], count["count"])],
    })
    pairs = int(count["count"].iloc[0])
    sig = t[(t["spearman_p"] < 0.05) & t["kind"].isin(["diff", "panel"])].sort_values(["kind", "lag", "spearman_p"])
    ex = t[t["kind"] == "panel_ex2025"].set_index(["lag", "dividend", "macro"])
    sig_ex = [ex.loc[(r.lag, r.dividend, r.macro)] if r.kind == "panel" else None for r in sig.itertuples()]
    diff_sig = sig[sig["kind"] == "diff"]
    n_total = int(diff_sig["dividend"].isin(["total_tril"]).sum())
    n_ex_samsung = int(diff_sig["dividend"].isin(["total_ex_samsung_tril"]).sum())
    sshow = pd.DataFrame({
        "갈래": [KIND_LABEL[k] for k in sig["kind"]], "시차": [lag_labels[l] for l in sig["lag"]],
        "배당": sig["dividend_label"], "거시": sig["macro_label"],
        "Spearman": [fmt(v, 2) for v in sig["spearman"]], "p": [fmt(v, 3) for v in sig["spearman_p"]],
        "2025 빼면": ["" if e is None else f"{fmt(e['spearman'], 2)} (p {fmt(e['spearman_p'], 3)})" for e in sig_ex],
    })
    pn = t[t["kind"] == "panel"].pivot_table(index=["dividend_label", "macro_label"], columns="lag",
                                             values="spearman", sort=False)
    pp = t[t["kind"] == "panel"].pivot_table(index=["dividend_label", "macro_label"], columns="lag",
                                             values="spearman_p", sort=False)
    pshow = pn.reset_index()[["dividend_label", "macro_label"]].rename(columns={"dividend_label": "배당", "macro_label": "거시 변화"})
    for key, label in md.LAGS:
        pshow[label] = [f"{fmt(r, 3)} (p {fmt(q, 2)})" for r, q in zip(pn[key], pp[key])]
    return f"""
## ③ 시차 비교

배당은 사업연도 Y가 끝난 뒤 이듬해 초에 결의합니다. 그래서 거시 값을 세 시점에서 붙여 같은 계산을 다시 했습니다.

- 같은 해: Y년 1~12월 (①·②와 같음)
- 1년 전: Y−1년 1~12월. 작년 경기가 올해 배당에 늦게 반영되는지 봅니다.
- 결의 시점: Y+1년 1~3월. 경상수지는 석 달 합계, 실질 GDP 성장률은 1분기끼리 전년 대비, 나머지는 석 달 평균입니다.

### 시차별로 p < 0.05가 나온 짝 수

같은 데이터로 짝을 많이 시험하면 우연히 p < 0.05가 나오는 짝도 생깁니다. 연도 갈래는 짝 {pairs}개라, 아무 관계가 없어도 {pairs * 0.05:.1f}개쯤은 나올 수 있습니다.

{md_table(cshow)}

### 추세를 빼고도 남은 짝 (연도 차이·회사×연도, p < 0.05)

{md_table(sshow) if len(sshow) else "없음"}

- 연도 차이 갈래에서 남은 짝 {len(diff_sig)}개 중 {n_total}개가 현금배당총액입니다. 배당총액은 삼성전자 몫이 커서(2020 특별배당) 한 회사·한 해가 좌우합니다. 삼성전자를 뺀 합계로 남은 짝은 {n_ex_samsung}개입니다.
- 회사×연도는 2025 사업연도를 뺀 값도 함께 적었습니다. 2025년에는 주당배당금을 올린 회사가 유독 많았는데, 거시 경기보다 배당 세제 변화의 영향일 수 있습니다(이 분석으로는 가려낼 수 없음).

### 회사×연도 Spearman, 시차별

{md_table(pshow)}
"""


def report(div_year, macro_year, yt, dt, pt, bad) -> str:
    years = list(YEARS)
    t1 = div_year.loc[years].join(macro_year.loc[years])
    show = pd.DataFrame({
        "연도": years,
        "배당 회사 비율(%)": [fmt(v, 1) for v in t1["payer_share"]],
        "배당총액(조 원)": [fmt(v, 1) for v in t1["total_tril"]],
        "삼성전자 제외(조 원)": [fmt(v, 1) for v in t1["total_ex_samsung_tril"]],
        "DPS 증가율 중앙값(%)": [fmt(v, 1) for v in t1["dps_growth_median"]],
        "DPS 올린 회사(%)": [fmt(v, 1) for v in t1["dps_up_share"]],
        "시가배당률 중앙값(%)": [fmt(v, 2) for v in t1["yield_median"]],
        "기준금리(%)": [fmt(v, 2) for v in t1["base_rate"]],
        "국고채3년(%)": [fmt(v, 2) for v in t1["ktb3y"]],
        "원/달러": [fmt(v, 1) for v in t1["usdkrw"]],
        "GDP 성장률(%)": [fmt(v, 1) for v in t1["gdp_growth"]],
        "물가상승률(%)": [fmt(v, 1) for v in t1["cpi_growth"]],
        "실업률(%)": [fmt(v, 2) for v in t1["unemployment"]],
        "경상수지(억$)": [fmt(v / 100, 0) for v in t1["current_account"]],
    })
    mshow, dshow = matrix_show(yt), matrix_show(dt)
    strong = yt[yt["spearman_p"] < 0.05].sort_values("spearman_p")
    dstrong = dt[dt["spearman_p"] < 0.05].sort_values("spearman_p")
    dsshow = pd.DataFrame({
        "배당 지표(전년 대비 차이)": dstrong["dividend_label"], "거시지표(전년 대비 차이)": dstrong["macro_label"],
        "n": dstrong["n"], "Spearman": [fmt(v, 2) for v in dstrong["spearman"]],
        "p": [fmt(v, 3) for v in dstrong["spearman_p"]]})
    sshow = pd.DataFrame({
        "배당 지표": strong["dividend_label"], "거시지표": strong["macro_label"], "n": strong["n"],
        "Spearman": [fmt(v, 2) for v in strong["spearman"]], "p": [fmt(v, 3) for v in strong["spearman_p"]],
        "Pearson": [fmt(v, 2) for v in strong["pearson"]], "Pearson p": [fmt(v, 3) for v in strong["pearson_p"]],
    })
    pshow = pd.DataFrame({
        "배당 쪽": pt["target_label"], "거시 변화": pt["macro_label"], "행": pt["rows"].map("{:,}".format),
        "회사": pt["companies"], "연도": pt["years"],
        "Spearman": [fmt(v, 3) for v in pt["spearman"]], "p(연도 섞기)": [fmt(v, 3) for v in pt["p_by_year"]],
    })
    badshow = pd.DataFrame({"회사": bad["corp_name"], "사업연도": bad["bsns_year"],
                            "DB 배당총액(원)": [fmt(v, 0) for v in bad["v"]],
                            "같은 회사 다른 해 중앙값(원)": [fmt(v, 0) for v in bad["company_median"]]})
    return f"""# 배당과 거시지표의 상관 결과

만든 날: {date.today().isoformat()} · 코드: `source/scripts/analyze_macro_dividend.py`, `source/core/macro_dividend.py`

## 먼저 알아 둘 점

- **연도 점이 9개(2017~2025 사업연도)뿐입니다.** 상관계수가 커 보여도 우연일 수 있고, 인과를 말할 수 없습니다. 탐색용으로만 봅니다.
- 배당은 사업연도 Y의 값(이듬해 초 결의)이고, 거시지표는 같은 달력 연도 Y의 연평균·합계입니다.
- p값은 순열검정입니다. 값의 순서를 2만 번 섞어 같은 크기 이상의 상관이 몇 번 나오는지 센 비율입니다.
- 회사×연도 분석에서 거시지표는 모든 회사에 같은 값이라, 실제로 다른 값은 연도 수만큼입니다. 그래서 p값도 **연도 단위로 섞어** 구했습니다.

## 해석할 때 주의

- 회사 명단은 지금의 638사입니다. 값이 있는 회사가 {int(t1["companies"].iloc[0])}사(2017) → {int(t1["companies"].iloc[-1])}사(2025)로 늘어난 것처럼, 그 뒤 상장한 회사는 앞 연도 값이 없고 중간에 사라진 회사는 처음부터 빠져 있습니다. 배당한 회사 비율이 해마다 오르는 데는 이 명단 효과가 섞여 있을 수 있습니다.
- 배당총액은 삼성전자 몫이 큽니다(2020 사업연도 {fmt(t1.loc[2020, "total_tril"] - t1.loc[2020, "total_ex_samsung_tril"], 1)}조 원, 특별배당). 삼성전자를 뺀 합계도 함께 봤습니다.
- 연도 점이 적어 한 해(특히 2020 코로나 해)가 상관을 크게 좌우할 수 있습니다.

## 출처

- 배당: `core.v_dividend_year_verified` (팀 검토 확정 값 우선) — 현금배당총액 `d_dart_won`, 보통주 주당배당금 `dps_common_won`
- 시가배당률: `raw.dart_dividend_item` 항목 '현금배당수익률(%)', 보통주
- 거시지표: `raw.ecos_macro` (한국은행 ECOS). 실질 GDP 성장률 = 계절조정 실질 GDP 4개 분기 합의 전년 대비, 물가상승률 = CPI 연평균의 전년 대비
- 배당 회사 비율 = 현금배당총액이 0보다 큰 회사 / 값이 있는 회사. DPS 증가율은 두 해 모두 배당한 회사만.

## 배당총액 합계에서 뺀 값

같은 회사 다른 해 중앙값의 {OUTLIER_RATIO:,}배를 넘는 값입니다. 원천 오류로 보여 **합계에서만** 뺐고, DB는 고치지 않았습니다. 원문 확인이 필요합니다.

{md_table(badshow)}

## ① 연도별 값

{md_table(show)}

## ① 연도 집계 상관 (Spearman, n=9)

{md_table(mshow)}

### p < 0.05인 짝

{md_table(sshow) if len(sshow) else "없음"}

## ①-2 추세를 뺀 상관 (전년 대비 차이끼리, Spearman, n=8)

수준끼리의 상관은 두 값이 같이 꾸준히 오르기만 해도 크게 나옵니다. 그래서 둘 다 전년 대비 차이로 바꿔 다시 봤습니다.

{md_table(dshow)}

### p < 0.05인 짝

{md_table(dsshow) if len(dsshow) else "없음"}

## ② 회사×연도 (2018~2025, 주당배당금 전년 대비 × 그 해 거시 변화)

{md_table(pshow)}
"""


def matrix_show(t: pd.DataFrame) -> pd.DataFrame:
    m = t.pivot(index="dividend_label", columns="macro_label", values="spearman")
    m = m.loc[[l for _, l in md.DIV_VARS], [l for _, l in md.MACRO_VARS]]
    return m.map(lambda v: fmt(v, 2)).reset_index().rename(columns={"dividend_label": "배당 지표 \\ 거시"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="배당과 거시지표의 상관 계산")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    main(ap.parse_args().url)
