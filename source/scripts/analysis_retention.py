"""고배당기업 유지 가능성(B1)을 report/분석/유지가능성_분석_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_retention [--url ...]
데이터: core.v_dividend_year_verified, core.v_financial_year_verified(팀 검토본 반영), core.core_min_dividend_2027, core.core_capacity_2025.
"""
import argparse
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from core import db
from core import group_compare as gc
from core import p1_analysis as p1
from core import retention as rt

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "유지가능성_분석_결과.md"
YEARS = range(2019, 2024)          # 결과 연도 2020~2024 (2025는 638사를 고른 기준이라 뺌)
TRAIN, TEST = range(2019, 2022), range(2022, 2024)
TIERS = ("낮음", "중간", "높음")


def matrix(rows):
    return np.array([[r[k] / s for _, k, s in rt.FEATURES] for r in rows])


def predict(terms, x):
    beta = np.array([t.coef for t in terms])
    return 1 / (1 + np.exp(-(beta[0] + x @ beta[1:])))


def fit(rows):
    return gc.logistic(matrix(rows), np.array([r["drop"] for r in rows]), [n for n, _, _ in rt.FEATURES])


def tier(p, cuts):
    return TIERS[0] if p < cuts[0] else TIERS[1] if p < cuts[1] else TIERS[2]


def main(url: str | None):
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        need = {r["corp_code"]: r["pass_if_same_as_2025"] for r in db.fetch_dicts(conn, """
            SELECT m.corp_code, m.pass_if_same_as_2025 FROM core.core_min_dividend_2027 m
            JOIN core.v_financial_year_verified f ON f.corp_code = m.corp_code AND f.bsns_year = 2025  -- 최소액 계산과 같은 확정 값(원문 대조로 고친 순이익 포함)
            WHERE m.status = '산출' AND (m.scenario = '2025년 (기본)' OR m.ni2026_won = f.ni_owner_won)""")}
        cover = {r["corp_code"]: float(r["cover_x"]) for r in db.fetch_dicts(
            conn, "SELECT corp_code, cover_x FROM core.core_capacity_2025 WHERE status = '표시' AND cover_x IS NOT NULL")}
    rows = rt.panel(comp, YEARS)

    # 1. 과거 유지·탈락
    hist = ["| 충족한 해 → 다음 해 | 충족 회사 | 가목 탈락률 | 나목 탈락률 | 전체 탈락률 |", "|---|---|---|---|---|"]
    for y in YEARS:
        g = [r for r in rows if r["year"] == y]
        ga = [r["drop"] for r in g if not r["route_na"]]
        na = [r["drop"] for r in g if r["route_na"]]
        hist.append(f"| {y} → {y + 1} | {len(g)} | {np.mean(ga) * 100:.1f}% ({len(ga)}) | {np.mean(na) * 100:.1f}% ({len(na)}) | "
                    f"{np.mean([r['drop'] for r in g]) * 100:.1f}% |")
    reasons = Counter(r["reason"] for r in rows if r["drop"])
    n_drop = sum(reasons.values())
    reason_lines = "\n".join(f"| {k} | {v} ({v * 100 / n_drop:.0f}%) |" for k, v in reasons.most_common())

    # 2. 과거로 만들고 그 뒤 연도로 확인
    train = [r for r in rows if r["year"] in TRAIN]
    test = [r for r in rows if r["year"] in TEST]
    t_terms = fit(train)
    p_train = predict(t_terms, matrix(train))
    cuts = np.percentile(p_train, [33.3, 66.7])
    p_test = predict(t_terms, matrix(test))
    auc_model = rt.auc(p_test, [r["drop"] for r in test])
    auc_route = rt.auc([r["route_na"] for r in test], [r["drop"] for r in test])
    calib = ["| 위험 등급 (만든 해 기준으로 3등분) | 확인 연도 회사 수 | 예측 탈락률 평균 | 실제 탈락률 |", "|---|---|---|---|"]
    for t in TIERS:
        idx = [i for i, p in enumerate(p_test) if tier(p, cuts) == t]
        if idx:
            calib.append(f"| {t} | {len(idx)} | {np.mean(p_test[idx]) * 100:.1f}% | {np.mean([test[i]['drop'] for i in idx]) * 100:.1f}% |")

    # 3. 전체 기간으로 다시 만든 모델
    terms = fit(rows)
    coef = ["| 특징 | 탈락 가능성 배수(오즈비) | 오차 범위(95%) | 우연일 확률(p) |", "|---|---|---|---|"]
    coef += [f"| {t.name} | {t.odds:.2f}배 | {t.odds_low:.2f} ~ {t.odds_high:.2f} | {t.p:.3f} |" for t in terms[1:]]
    all_cuts = np.percentile(predict(terms, matrix(rows)), [33.3, 66.7])

    # 4. 2025 숫자에 적용 → 2026 숫자로도 충족할까(2027년 분리과세)
    now = []
    for corp, (d, ni, bs) in comp.items():
        f = rt.features(d, ni, bs, 2025)
        if f:
            now.append({"corp": corp, **f})
    p_now = predict(terms, matrix(now))
    for r, p in zip(now, p_now):
        r["p"], r["tier"] = p, tier(p, all_cuts)
    risk = ["| 위험 등급 | 회사 수 | 예측 탈락률 평균 | 나목 비율 | 2025만큼 배당하면 2027 최소액 못 채움 | 잉여현금흐름이 최소 배당보다 적음 |",
            "|---|---|---|---|---|---|"]
    for t in TIERS:
        g = [r for r in now if r["tier"] == t]
        short = [r for r in g if r["corp"] in need]
        weak = [r for r in g if r["corp"] in cover]
        risk.append(f"| {t} | {len(g)} | {np.mean([r['p'] for r in g]) * 100:.1f}% | {np.mean([r['route_na'] for r in g]) * 100:.0f}% | "
                    f"{sum(1 for r in short if not need[r['corp']])}/{len(short)} | {sum(1 for r in weak if cover[r['corp']] < 1)}/{len(weak)} |")
    def rule(c):
        if c not in need:
            return "최소액 계산 안 됨"
        if need[c]:
            return "① 2025만큼만 배당해도 충분"
        if c not in cover:
            return "④ 부족, 여력 계산 안 됨(금융업 등)"
        return "② 더 내야 하지만 잉여현금흐름은 충분" if cover[c] >= 1 else "③ 더 내야 하고 잉여현금흐름도 부족"
    groups = Counter(rule(r["corp"]) for r in now)
    rule_lines = ["| 규칙으로 나눈 무리 | 회사 수 | 모델 예측 탈락률 평균 |", "|---|---|---|"]
    for g in sorted(groups):
        ps = [r["p"] for r in now if rule(r["corp"]) == g]
        rule_lines.append(f"| {g} | {groups[g]} | {np.mean(ps) * 100:.1f}% |")
    high_short = sum(1 for r in now if r["tier"] == "높음" and r["corp"] in need and not need[r["corp"]]
                     and r["corp"] in cover and cover[r["corp"]] < 1)

    ga_rate = np.mean([r["drop"] for r in rows if not r["route_na"]]) * 100
    na_rate = np.mean([r["drop"] for r in rows if r["route_na"]]) * 100
    text = f"""# 고배당기업 유지 가능성 — 올해 충족한 회사가 내년에도 충족할까

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_retention.py`, `source/core/retention.py` · 설계: `report/설계/데이터_분석_설계.md` B1
- 판정: 지금 판정 엔진을 과거 숫자에 그대로 적용(`core.p1_analysis.retro_status`, 배당소득 = 배당 총액, 제2호 기준선 = 전년 배당). 데이터: `v_*_verified`(팀 검토본 반영)
- 대상: {min(YEARS)}~{max(YEARS)}년 숫자로 충족하고 예측 특징 값이 모두 있는 회사·연도 {len(rows)}건. 다음 해가 판정 보류면 뺌

## 한 줄 결과

제도가 없던 때에는 고배당기업 요건을 충족한 회사의 **{np.mean([r['drop'] for r in rows]) * 100:.0f}%가 다음 해에 탈락**했다(가목 {ga_rate:.0f}%, 나목 {na_rate:.0f}%). 탈락 이유는 대부분 **배당을 전년보다 줄인 것(제2호)**이다. 다만 재무 특징(ROE, 부채비율 등)으로 만든 예측 모델은 **그 뒤 연도의 탈락을 거의 맞히지 못했다**(맞힘 점수 {auc_model:.2f}, 0.5 = 동전 던지기, '나목인가'만 볼 때 {auc_route:.2f}). 탈락은 회사의 재무 상태보다 **다음 해 배당을 얼마나 내기로 하느냐**에 달려 있기 때문이다. 그래서 회사별 위험은 모델 점수보다 **규칙 계산(2027 최소 배당액과 현금 여력)** 으로 나누는 편이 낫다. 2025 숫자로 충족한 {len(now)}사 중 **{groups['③ 더 내야 하고 잉여현금흐름도 부족']}사는 2025보다 배당을 더 내야 하는데 잉여현금흐름도 그만큼 없다.**

## 0. 먼저 알아야 할 것

- 과거에는 이 제도가 없어서 회사들이 기준선을 의식하지 않았다. 그래서 아래 과거 탈락률은 **"제도가 없을 때의 기본 탈락률"** 이다. 제도가 생긴 뒤에는 회사들이 기준선을 지키려 해서 실제 탈락률은 더 낮을 수 있다.
- 638사는 2025 숫자로 고배당기업이 된 회사만이다. 그래서 2024 → 2025 유지율은 실제보다 높게 나온다(이 분석에서 뺌). 상장폐지된 회사도 없다.

## 1. 과거 유지·탈락

{chr(10).join(hist)}

탈락 이유 ({n_drop}건):

| 다음 해 탈락 이유 | 건수 |
|---|---|
{reason_lines}

## 2. 예측 모델이 맞히나 — 과거로 만들고 그 뒤 연도로 확인

- 만든 자료: {min(TRAIN)}~{max(TRAIN)}년 충족 → 다음 해 결과 ({len(train)}건)
- 확인 자료: {min(TEST)}~{max(TEST)}년 충족 → 다음 해 결과 ({len(test)}건). 모델은 이 자료를 보지 않았다.
- 맞힘 점수(탈락한 회사의 예측 점수가 유지한 회사보다 높을 확률): 예측 모델 **{auc_model:.2f}**, '나목인가'만 볼 때 {auc_route:.2f}. 0.5면 동전 던지기, 1이면 완벽.

{chr(10).join(calib)}

## 3. 무엇이 탈락과 관련 있나 ({min(YEARS)}~{max(YEARS)} 전체로 다시 만든 모델)

'탈락 가능성 배수'는 다른 특징이 같을 때 그 특징이 다음 해 탈락 가능성(오즈)을 몇 배로 바꾸는지다. 1보다 크면 탈락하기 쉽다.

{chr(10).join(coef)}

## 4. 2025 숫자에 적용 — 2026 숫자로도 충족할까 (2027년 분리과세)

### 4-1. 규칙으로 나누기 (추천)

2027 최소 배당액(`core_min_dividend_2027`, 2025년 순이익 가정)과 배당 여력(`core_capacity_2025`)으로 나눈다. 판정 규칙을 그대로 계산한 값이라 모델보다 믿을 만하다.

{chr(10).join(rule_lines)}

### 4-2. 예측 모델 등급 (참고)

2025 숫자로 충족한 {len(now)}사(지금 판정 엔진, 특징 값이 모두 있는 회사)에 모델을 적용했다. 등급은 과거 회사·연도의 예측값을 셋으로 나눈 경계(낮음 < {all_cuts[0] * 100:.0f}% ≤ 중간 < {all_cuts[1] * 100:.0f}% ≤ 높음)로 매겼다.

{chr(10).join(risk)}

- '2025만큼 배당하면 2027 최소액 못 채움'은 `core_min_dividend_2027`(2025년 순이익 가정)에서 2025 배당으로는 부족한 회사 / 최소액이 계산된 회사.
- '잉여현금흐름이 최소 배당보다 적음'은 `core_capacity_2025`의 여력 배수가 1배 미만인 회사 / 표시된 회사(금융업 제외).

## 5. 읽을 때 주의

- 예측 모델의 맞힘 점수가 낮고, 확인 연도에서 '높음' 등급의 예측 탈락률(평균)이 실제보다 높았다. 모델 등급은 회사별 판단에 쓰지 말고, 특징별 관계(3절)를 보는 데만 쓴다.
- 예측 점수는 과거 패턴에 기댄 것이다. 제도가 생겨 회사들의 행동이 바뀌었으므로(2절 쏠림, A1), 실제 탈락률은 이보다 낮을 수 있다. 등급의 **순서**(누가 더 위험한가)를 쓰고, 탈락률 숫자 자체는 참고로만 쓴다.
- 과거 판정은 감액배당 정보가 없어 배당소득 = 배당 총액으로 두었고, 제2호 기준선을 '2024년' 대신 '전년'으로 보았다.
- 회사 이름은 이 문서에 적지 않는다(분석 화면 P1과 같은 원칙).
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    a = ap.parse_args()
    main(a.url)
