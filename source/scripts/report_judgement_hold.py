"""판정 보류인 회사와 사유를 report/분석/판정_보류_정리.md로 쓴다.

실행: .venv/bin/python -m scripts.report_judgement_hold [--url ...]
- 2026 판정: core.core_judgement_2026(source/scripts/build_judgement.py, source/core/judgement.py)
- 해석을 바꿔 다시 판정: 같은 엔진(core.judgement.judge_2026)에 숫자만 바꿔 넣는다
- 과거 소급 판정: core.p1_analysis.retro_status(B = D, 제2호 기준선 = 전년 배당)
회사 이름은 쓰지 않고 DART 고유번호·종목코드만 쓴다.
"""
import argparse
from collections import Counter
from datetime import date
from pathlib import Path

from core import db
from core import p1_analysis as p1
from core.judgement import HOLD, MET, NOT_MET, judge_2026

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "판정_보류_정리.md"
REDUCTION = "자료 결측: B(직전)"
ZERO_PREV = "전전 사업연도 무배당"

HOLD_SQL = """
SELECT j.corp_code, c.stock_code, c.market, j.reasons, j.deemed_payout_pct,
       j.b_prev_won, j.b_2024_won, j.d_prev_won, j.d_prevprev_won, j.ni_prev_won, j.liabilities_won, j.equity_won,
       d.b_status, p.d_dart_won AS d2024_dart_won, p.dps_common_won AS dps2024_won
FROM core.core_judgement_2026 j
JOIN core.core_company c USING (corp_code)
LEFT JOIN core.core_dividend_year d ON d.corp_code = j.corp_code AND d.bsns_year = 2025
LEFT JOIN core.core_dividend_year p ON p.corp_code = j.corp_code AND p.bsns_year = 2024
WHERE j.status = '판정 보류'
ORDER BY j.reasons, c.stock_code
"""
COUNT_SQL = "SELECT status, count(*) AS n, sum(needs_recheck::int) AS recheck FROM core.core_judgement_2026 GROUP BY status"
BUILT_SQL = "SELECT max(built_at)::date AS d FROM core.core_judgement_2026"
MIN_SQL = "SELECT status, count(*) AS rows, count(DISTINCT corp_code) AS firms FROM core.core_min_dividend_2027 GROUP BY status"


def _i(v) -> int | None:
    return int(v) if v is not None else None


def rejudge(r: dict, b_prev=None, d_prevprev=None):
    """같은 엔진에 B(직전)·D(전전)만 바꿔 넣어 다시 판정한다."""
    return judge_2026(_i(b_prev if b_prev is not None else r["b_prev_won"]), _i(r["b_2024_won"]), _i(r["d_prev_won"]),
                      _i(d_prevprev if d_prevprev is not None else r["d_prevprev_won"]), _i(r["ni_prev_won"]),
                      _i(r["liabilities_won"]), _i(r["equity_won"]))


def label(j) -> str:
    return f"{j.status} ({j.route})" if j.route else j.status


def free_share(r: dict) -> float:
    """2025 배당 중 비과세 감액배당이 몇 %를 넘으면 B2025 < B2024가 되는지. 음수면 이미 미달."""
    d, b24 = float(r["d_prev_won"]), float(r["b_2024_won"])
    return (d - b24) * 100 / d


def eok(v) -> str:
    return "-" if v is None else f"{float(v) / 1e8:,.1f}"


def main(url: str | None):
    with db.connect(url) as conn:
        holds = db.fetch_dicts(conn, HOLD_SQL)
        counts = {r["status"]: r for r in db.fetch_dicts(conn, COUNT_SQL)}
        built = db.fetch_dicts(conn, BUILT_SQL)[0]["d"]
        mins = {r["status"]: r for r in db.fetch_dicts(conn, MIN_SQL)}
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
    total = sum(r["n"] for r in counts.values())
    red = [r for r in holds if r["reasons"].startswith(REDUCTION)]
    zero = [r for r in holds if r["reasons"].startswith(ZERO_PREV)]
    other = [r for r in holds if r not in red and r not in zero]

    # 1. 감액배당: B2025 = D2025(감액배당이 모두 과세)로 두면
    red_alt = {r["corp_code"]: rejudge(r, b_prev=r["d_prev_won"]) for r in red}
    red_cnt = Counter(label(j) for j in red_alt.values())
    shares = [free_share(r) for r in red]
    bins = [("이미 2024보다 적음 (B = D여도 제2호 미충족)", lambda s: s < 0),
            ("0% (2024와 같음, 비과세가 조금만 있어도 미충족)", lambda s: s == 0),
            ("0% 초과 ~ 30%", lambda s: 0 < s <= 30),
            ("30% 초과 ~ 60%", lambda s: 30 < s <= 60),
            ("60% 초과 ~ 100% 미만", lambda s: 60 < s < 100),
            ("100% (2024 배당소득 0, 제2호는 늘 충족)", lambda s: s >= 100)]
    share_rows = "\n".join(f"| {name} | {sum(1 for s in shares if f(s))} |" for name, f in bins)

    # 2. 전전 무배당: 0 → 양수를 '10% 이상 증가'로 인정하면 / 안 하면
    tiny = 1  # D(전전)을 1원으로 두면 0이 아닌 어떤 증가도 10% 이상이 된다
    zero_yes = Counter(label(rejudge(r, d_prevprev=tiny)) for r in zero)
    zero_profit = [r for r in zero if r["ni_prev_won"] > 0]
    zero_deficit = [r for r in zero if r["ni_prev_won"] <= 0]
    pays = sorted(float(r["d_prev_won"]) * 100 / float(r["ni_prev_won"]) for r in zero_profit)
    conflict = [r for r in zero if r["dps2024_won"] and float(r["dps2024_won"]) > 0]

    # 3. 과거 소급 판정의 보류
    retro_rows = []
    for y in p1.YEARS:
        js = [p1.retro_status(d, ni, bs, y) for d, ni, bs in comp.values()]
        why = Counter(j.reasons[0].split(":")[0] for j in js if j.status == HOLD)
        retro_rows.append(f"| {y} → {y + 1} 배당 | {sum(1 for j in js if j.status == MET)} | "
                          f"{sum(1 for j in js if j.status == NOT_MET)} | **{sum(why.values())}** | {why['자료 결측']} | "
                          f"{why['전전 사업연도 무배당']} | {why['적자이면서 자본잠식']} |")

    # 부록: 65사 목록
    app = ["| 사유 | DART 고유번호 | 종목코드 | 시장 | D2025(억 원) | D2024(억 원) | B2024(억 원) | 순이익 2025(억 원) | 해석을 바꾸면 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in red:
        app.append(f"| 감액배당 확인 필요 | {r['corp_code']} | {r['stock_code']} | {r['market']} | {eok(r['d_prev_won'])} | "
                   f"{eok(r['d_prevprev_won'])} | {eok(r['b_2024_won'])} | {eok(r['ni_prev_won'])} | "
                   f"모두 과세면 {label(red_alt[r['corp_code']])} · 비과세 {free_share(r):.0f}% 넘으면 제2호 미충족 |")
    for r in zero:
        kind = "흑자" if r["ni_prev_won"] > 0 else "적자 25% 간주"
        app.append(f"| 전전 무배당 ({kind}) | {r['corp_code']} | {r['stock_code']} | {r['market']} | {eok(r['d_prev_won'])} | "
                   f"{eok(r['d_prevprev_won'])} | {eok(r['b_2024_won'])} | {eok(r['ni_prev_won'])} | "
                   f"증가 인정 시 {label(rejudge(r, d_prevprev=tiny))} · 불인정 시 미충족 |")

    n_hold = counts[HOLD]["n"]
    n_recheck = sum(r["recheck"] for r in counts.values())
    text = f"""# 판정 보류 정리 — 어느 회사가, 왜 보류됐나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/report_judgement_hold.py`
- 판정: `core.core_judgement_2026`(계산일 {built}, 엔진 `source/core/judgement.py`). 2026 사업연도 배당을 2025 숫자로 판정한 결과
- '해석을 바꾸면'은 같은 판정 엔진에 숫자만 바꿔 넣어 다시 계산한 값이다
- 근거 조문과 팀 해석은 `report/검증/조문_코드_대응표.md`의 '팀 해석·판정 보류'를 따른다
- 회사 이름은 쓰지 않았다. 목록은 맨 아래 부록에 DART 고유번호·종목코드로 적었다

## 한 줄 결과

638사 중 **{n_hold}사({n_hold * 100 / total:.0f}%)가 판정 보류**다. 사유는 두 가지뿐이다.
**감액배당 확인 필요 {len(red)}사**와 **전전 사업연도(2024) 무배당 {len(zero)}사**다.
둘 다 숫자가 모자라서가 아니라 **규칙 해석이 정해지지 않아서** 보류했다.
감액배당이 모두 과세된다고 보면 {len(red)}사 중 {sum(v for k, v in red_cnt.items() if k.startswith(MET))}사가 충족이다.
0원에서 늘어난 것을 '10% 이상 증가'로 인정하면 {len(zero)}사 중 {sum(v for k, v in zero_yes.items() if k.startswith(MET))}사가 충족이고, 인정하지 않으면 모두 미충족이다.

| 2026 판정 | 회사 수 |
|---|---|
| 충족 | {counts[MET]['n']} (그중 경계 근처라 원 단위 재확인 필요 {n_recheck}) |
| 미충족 | {counts[NOT_MET]['n']} |
| **판정 보류** | **{n_hold}** |
| ㄴ 감액배당 확인 필요 | {len(red)} |
| ㄴ 전전 사업연도 무배당 | {len(zero)} |
{f"| ㄴ 그 밖의 사유 | {len(other)} |" if other else ""}

## 1. 감액배당 확인 필요 — {len(red)}사

**무엇이 문제인가.** 제2호는 '2025 배당소득(B)이 2024 배당소득보다 줄지 않을 것'이다. 배당소득 B는 현금배당에서 **비과세 감액배당**을 뺀 금액이다. 감액배당은 자본준비금을 줄여서 주는 배당이라, 일부 또는 전부가 세금이 붙지 않는 돈일 수 있다.

**왜 보류했나.** 이 회사들은 KIND 고배당기업 공시 메모에 '감액배당'이 적혀 있다. 하지만 그중 **얼마가 비과세인지** 우리 데이터에는 없다. 그래서 B2025를 비워 두었고, 판정 엔진은 '자료 결측: B(직전)'으로 보류했다(`source/core/b_income.py`).

**감액배당이 모두 과세된다고 보면(B2025 = D2025)**

| 결과 | 회사 수 |
|---|---|
{chr(10).join(f"| {k} | {v} |" for k, v in red_cnt.most_common())}

'판정 보류'로 남는 회사는 전전 사업연도 무배당 사유에도 걸린 회사다.

**비과세 몫이 얼마면 결과가 뒤집히나.** 2025 배당 중 비과세 감액배당 비율이 아래 값을 넘으면, B2025가 B2024보다 작아져 제2호에서 미충족이 된다. 값이 낮을수록 작은 비과세 금액에도 결과가 바뀐다.

| 뒤집히는 비과세 비율 | 회사 수 |
|---|---|
{share_rows}

계산: (D2025 − B2024) ÷ D2025 × 100. 주식배당은 B에 더해지지만 이 회사들에 대해서는 따로 확인하지 않았다.

**보류를 풀려면.** 회사별 배당 결정 공시나 주주총회 안건에서 감액배당 금액과 비과세 여부를 확인해 `B2025 = D2025 + 주식배당 − 비과세 감액배당`을 채운다. 근거 조문은 소득세법 시행령 제26조의3 제6항이고, 대응표에는 '이번에 미대조'로 남아 있다.

## 2. 전전 사업연도(2024) 무배당 — {len(zero)}사

**무엇이 문제인가.** 나목은 '배당성향 25% 이상이고 이익배당금액이 전전 사업연도보다 10% 이상 늘 것'이다. 이 회사들은 2024년에 배당하지 않았다(D2024 = 0). 0원에서 늘어난 것은 증가율을 계산할 수 없다.

**왜 보류했나.** 0원에서 늘어난 것을 '10% 이상 증가'로 볼지 공식 해설을 찾지 못했다. 팀 해석으로 보류한다(`source/core/judgement.py`, 대응표 '전전 무배당'). 가목(배당성향 40% 이상)으로 충족하는 회사는 이 문제와 상관없이 이미 충족으로 판정했다. 그래서 여기 남은 회사는 모두 **나목에만 기대는** 회사다.

| 무리 | 회사 수 | 설명 |
|---|---|---|
| 흑자, 배당성향 25~40% | {len(zero_profit)} | 배당성향 {pays[0]:.1f}% ~ {pays[-1]:.1f}%, 중앙값 {pays[len(pays) // 2]:.1f}% |
| 적자, 배당성향 25%로 간주 | {len(zero_deficit)} | 순이익 0 이하이고 부채가 자본총액의 2배 이하라 25%로 간주(시행령 제104조의24 제5항). 간주값으로는 가목 불가 |

**해석에 따라**

| 해석 | 결과 |
|---|---|
| 0원 → 양수를 '10% 이상 증가'로 인정 | {", ".join(f"{k} {v}사" for k, v in zero_yes.most_common())} |
| 인정하지 않음 | 미충족 {len(zero)}사 |

이 {len(zero)}사는 해석 하나에 따라 한꺼번에 충족이나 미충족으로 간다. 충족 {counts[MET]['n']}사가 최대 {counts[MET]['n'] + len(zero)}사까지 늘 수 있다는 뜻이다.

**데이터 확인이 필요한 회사 {len(conflict)}사.** {"".join(f"DART 고유번호 {r['corp_code']}는 판정에 쓴 D2024가 0원이다(KIND 공시의 '전전 사업연도 이익배당금액'). 그런데 DART 사업보고서에는 2024 보통주 주당배당금 {float(r['dps2024_won']):,.0f}원, 현금배당총액 {eok(r['d2024_dart_won'])}억 원이 있다. 무배당이 맞는지 원문 확인이 필요하다. " for r in conflict) or "없음."}

## 3. 판정은 났지만 다시 볼 회사 — {n_recheck}사

보류는 아니지만, 충족 판정 중 {n_recheck}사는 경계에 너무 가깝다. 배당액·순이익이 백만 원 단위로 반올림된 값이라, ±1백만 원만 흔들어도 결과(충족 여부나 가목·나목)가 바뀐다. 원 단위 원값(배당 결정 공시 합계 등)으로 다시 확인해야 한다(`needs_recheck`).

## 4. 2027 최소 필요 배당액에는 보류가 없다

`core.core_min_dividend_2027`(회사 × 순이익 시나리오)에는 보류 행이 없다. 산출 {mins['산출']['rows']}행({mins['산출']['firms']}사), 충족 불가 {mins['충족 불가']['rows'] if '충족 불가' in mins else 0}행({mins['충족 불가']['firms'] if '충족 불가' in mins else 0}사, 적자 시나리오에서 부채가 자본총액의 2배 초과)이다. 최소액은 "2026 배당이 전부 과세되는 현금배당(B2026 = D2026)"이라고 가정하고 계산하기 때문이다. 2025 감액배당 문제는 2026 판정에만 걸린다. 다만 위 가정이 틀리면(2026에도 비과세 감액배당을 하면) 그 회사의 최소액도 다시 계산해야 한다.

## 5. 과거 숫자로 소급 판정할 때의 보류

B1(유지 가능성)은 2018~2025 숫자에 같은 엔진을 적용했다. 과거에는 감액배당 정보가 없어 B = D로 두었으므로 감액배당 보류는 생기지 않는다. 대신 아래 사유로 보류가 생겼고, **B1은 다음 해가 보류인 회사·연도를 유지·탈락 계산에서 뺐다.**

| 판정에 쓴 숫자 → 배당 | 충족 | 미충족 | 보류 | ㄴ 자료 결측 | ㄴ 전전 무배당 | ㄴ 적자·자본잠식 |
|---|---|---|---|---|---|---|
{chr(10).join(retro_rows)}

- 638사(2025에 고배당 공시를 낸 회사)만 센 것이다.
- 2018~2022년 보류는 대부분 **자료 결측**이다. 그해 배당·순이익 자료가 없는 회사·연도(상장 전이거나 DART 자료가 없는 해)다. 2023년부터는 자료 결측이 거의 없고 **전전 무배당**만 남는다.
- **적자·자본잠식**은 순이익이 0 이하이면서 자본총계도 0 이하인 경우다. 부채 기준(2배)을 어떻게 적용할지 정하지 않아 보류한다.
- 마지막 줄(2025 → 2026)의 전전 무배당은 위 2절의 {len(zero)}사와 다를 수 있다. 소급 판정은 D를 모두 DART 현금배당총액으로 쓰고, 2절은 KIND 공시값을 먼저 쓰기 때문이다(2절의 데이터 확인 필요 회사가 그 예).

## 6. 분석에서 보류를 어떻게 다뤘나

| 분석 | 보류 처리 |
|---|---|
| B1 유지 가능성 | 다음 해가 보류인 회사·연도는 유지·탈락 계산에서 뺐다 |
| A2·A3·C2 무리 비교 | '가목으로 충족' 비율은 충족 회사만 분모로 썼다. 보류·미충족은 빠진다 |
| A1 쏠림, B2 여력 지도, C1 주가 반응 | 판정 상태를 쓰지 않아 보류와 상관없다 |

## 부록. 판정 보류 {n_hold}사 목록

금액은 억 원. D는 판정에 쓴 이익배당금액(KIND 공시가 있으면 원 단위 공시값, 없으면 DART 현금배당총액), B2024는 KIND 공시의 2024 배당소득이다.

{chr(10).join(app)}
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    a = ap.parse_args()
    main(a.url)
