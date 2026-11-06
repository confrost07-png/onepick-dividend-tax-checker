"""밸류업 약속과 실제(D2)를 report/분석/밸류업_약속_실제_결과.md로 쓴다.

실행: .venv/bin/python -m scripts.analysis_promise_actual [--url ...]
약속: 2025-12-31까지 공시한 계획(정정은 최신 판)에서 D1 규칙(source/core/policy_promise.py)이 찾은 숫자 목표 후보.
실제: 2025 사업연도 배당성향·주당배당금·ROE(`v_*_verified`, 팀 검토본 반영).
한 회사에 같은 종류 후보가 여럿이면 가장 낮은 값을 약속으로 본다('○% 이상'이 많고, 지키기 쉬운 쪽으로 판단).
"""
import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path

from core import db
from core import p1_analysis as p1
from core import policy_promise as pp
from scripts import analysis_policy_promise as apr

OUT = Path(__file__).resolve().parents[2] / "report" / "분석" / "밸류업_약속_실제_결과.md"
CUTOFF = date(2025, 12, 31)
DPS_SQL = "SELECT corp_code, dps_common_won FROM core.v_dividend_year_verified WHERE bsns_year = 2025"


def actuals(comp: dict, dps: dict) -> dict:
    out = {}
    for corp, (d, ni, bs) in comp.items():
        d25, n25 = d.get(2025), ni.get(2025)
        _, eq = bs.get(2025, (None, None))
        out[corp] = {"배당성향": d25 * 100 / n25 if d25 is not None and n25 and n25 > 0 else None,
                     "ROE": n25 * 100 / eq if n25 is not None and eq and eq > 0 else None,
                     "주당배당금": float(dps[corp]) if dps.get(corp) is not None else None}
    return out


def main(url: str | None):
    with db.connect(url) as conn:
        chunks = [c for c in db.fetch_dicts(conn, apr.CHUNK_SQL) if c["rcept_dt"] <= CUTOFF]
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
        dps = {r["corp_code"]: r["dps_common_won"] for r in db.fetch_dicts(conn, DPS_SQL)}
    promised = defaultdict(dict)
    for c in chunks:
        for p in pp.find(c["text"]):
            if p.kind in ("배당성향", "주당배당금", "ROE") and p.value:
                v = float(p.value)
                promised[c["corp_code"]][p.kind] = min(v, promised[c["corp_code"]].get(p.kind, v))
    act = actuals(comp, dps)
    firms = len({c["corp_code"] for c in chunks})

    lines = ["| 약속 종류 | 약속한 회사 | 2025 실제 값이 있는 회사 | 약속 이상 달성 | 약속 미달 | 약속 값 중앙값 | 실제 값 중앙값 |",
             "|---|---|---|---|---|---|---|"]
    detail = {}
    for kind, unit in (("배당성향", "%"), ("주당배당금", "원"), ("ROE", "%")):
        pairs = [(v[kind], act[c][kind]) for c, v in promised.items() if kind in v and c in act and act[c][kind] is not None]
        n_prom = sum(1 for v in promised.values() if kind in v)
        met = sum(1 for t, a in pairs if a >= t)
        miss = len(pairs) - met
        tm = sorted(t for t, _ in pairs)
        am = sorted(a for _, a in pairs)
        fmt = (lambda x: f"{x:,.0f}") if unit == "원" else (lambda x: f"{x:.1f}")
        lines.append(f"| {kind} | {n_prom} | {len(pairs)} | **{met} ({met * 100 / len(pairs):.0f}%)** | {miss} | "
                     f"{fmt(tm[len(tm) // 2])}{unit} | {fmt(am[len(am) // 2])}{unit} |" if pairs else f"| {kind} | {n_prom} | 0 | - | - | - | - |")
        detail[kind] = (met, len(pairs))

    # 배당성향 약속이 2027 고배당기업 요건과 맞나
    pay = [v["배당성향"] for v in promised.values() if "배당성향" in v]
    ge40 = sum(1 for v in pay if v >= 40)
    b25 = sum(1 for v in pay if 25 <= v < 40)
    lt25 = sum(1 for v in pay if v < 25)

    met_p, n_p = detail["배당성향"]
    met_r, n_r = detail["ROE"]
    text = f"""# 밸류업 약속과 실제 — 2025년 말까지 한 약속을 2025 사업연도에 지켰나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_promise_actual.py` · 설계: `report/설계/데이터_분석_설계.md` D2
- 약속: {CUTOFF.isoformat()}까지 공시한 밸류업 계획 {len({c['rcept_no'] for c in chunks})}건({firms}사, 정정은 최신 판)의 문단에서 D1 규칙(`source/core/policy_promise.py`)이 찾은 숫자 목표 **후보**. 사람 확인 전이다
- 실제: 2025 사업연도 배당성향(배당 총액 ÷ 지배주주 순이익, 흑자만)·보통주 주당배당금·ROE(`v_*_verified`)
- 한 회사에 같은 종류 후보가 여럿이면 **가장 낮은 값**을 약속으로 봤다. 대부분 '○% 이상' 약속이라, 가장 낮은 값을 넘으면 지킨 것으로 친다

## 한 줄 결과

2025년 말까지 배당성향 목표를 적은 회사 {n_p}사 중 **{met_p}사({met_p * 100 / n_p:.0f}%)가 2025년에 그 이상을 배당**했다. ROE 목표는 {n_r}사 중 **{met_r}사({met_r * 100 / n_r:.0f}%)만** 달성했다. 배당은 회사가 정하는 숫자라 지키기 쉽고, ROE는 실적에 달려 있어 어렵다.

## 1. 약속 종류별 달성

{chr(10).join(lines)}

## 2. 배당성향 약속이 고배당기업 요건에 맞나

2025년 말까지 적은 배당성향 목표(회사별 가장 낮은 값) {len(pay)}사:

| 약속한 배당성향 | 회사 수 | 뜻 |
|---|---|---|
| 40% 이상 | {ge40} | 지키기만 하면 가목으로 충족 |
| 25~40% | {b25} | 지켜도 배당을 해마다 10% 늘려야 나목으로 충족 |
| 25% 미만 | {lt25} | 지켜도 요건에 못 미침 |

## 3. 읽을 때 주의

- 약속은 사람 확인 전 후보다. D1에서 사람이 확인한 9사 기준으로는 규칙이 낸 배당 후보가 모두 맞았지만, 표본이 작다. 과거 실적 문장을 목표로 잘못 읽었다면 '달성'이 부풀려진다.
- 638사는 2025 배당성향이 25% 이상인 회사만이라, 배당성향 약속 달성률은 전체 상장사보다 높게 나온다.
- 목표 연도를 따지지 않았다. "2027년까지 ROE 10%"처럼 아직 기한이 남은 약속도 2025 값으로 비교했으므로, ROE 미달은 '아직 못 했다'로 읽어야 한다.
- 배당성향은 회사가 정한 기준(별도·연결, 조정 순이익)과 우리가 쓴 기준(연결 지배주주 순이익)이 다를 수 있다.
- 자사주 소각 약속의 이행은 소각 공시(`raw.dart_policy_filing`)를 10사만 받아서 아직 볼 수 없다.
"""
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    a = ap.parse_args()
    main(a.url)
