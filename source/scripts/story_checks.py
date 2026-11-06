"""데이터 이야기 보고서의 '확인하는 법': 독자가 그대로 돌려 볼 SQL·명령과, 화면 숫자와 같은지 맞춰 보는 규칙.

각 확인은 (장, 무엇을 확인하나, SQL 또는 파이썬 명령, 화면 값을 꺼내는 함수, 결과에서 같은 값을 꺼내는 함수)로 이뤄진다.
보고서를 만들 때마다 모두 실제로 돌려서, 화면 API 값과 같을 때만 '같음'으로 적는다(source/scripts/report_story_pdf.py).
"""
from dataclasses import dataclass
from typing import Any, Callable

from core import db

PAYOUT_SQL = """-- 2025 배당성향(%) 1%p 구간별 회사 수: 흑자이고 2025 배당이 있는 회사
WITH x AS (
  SELECT d.corp_code, d.d_dart_won::numeric * 100 / f.ni_owner_won AS payout
  FROM core.v_dividend_year_verified d
  JOIN core.v_financial_year_verified f USING (corp_code, bsns_year)
  WHERE d.bsns_year = 2025 AND d.d_dart_won > 0 AND f.ni_owner_won > 0)
SELECT floor(payout)::int AS 구간, count(*) AS 회사수
FROM x WHERE payout >= 24 AND payout < 26
GROUP BY 1 ORDER BY 1;"""

GROWTH_SQL = """-- 2025 이익배당금액 증가율(%) 9%대·10%대 회사 수: 2024·2025 모두 배당, 2025 순이익을 아는 회사
WITH x AS (
  SELECT (d25.d_dart_won - d24.d_dart_won)::numeric * 100 / d24.d_dart_won AS growth
  FROM core.v_dividend_year_verified d25
  JOIN core.v_dividend_year_verified d24 ON d24.corp_code = d25.corp_code AND d24.bsns_year = 2024
  JOIN core.v_financial_year_verified f ON f.corp_code = d25.corp_code AND f.bsns_year = 2025
  WHERE d25.bsns_year = 2025 AND d25.d_dart_won > 0 AND d24.d_dart_won > 0 AND f.ni_owner_won IS NOT NULL)
SELECT floor(growth)::int AS 구간, count(*) AS 회사수
FROM x WHERE growth >= 9 AND growth < 11
GROUP BY 1 ORDER BY 1;"""

FUNNEL_SQL = """-- 2026 요건 판정 결과 (1장 토너먼트)
SELECT status AS 판정, route AS 경로, deemed_payout_pct IS NOT NULL AS 적자간주,
       left(reasons, 14) AS 첫이유, count(*) AS 회사수
FROM core.core_judgement_2026
GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;"""

GRID_SQL = """-- 3장 칸 그림: 해마다 증가율 줄 × 배당성향 칸 회사 수 (흑자이고 전년에도 배당한 회사)
WITH j AS (
  SELECT d.corp_code, d.bsns_year AS y, d.d_dart_won AS d, f.ni_owner_won AS ni,
         lag(d.d_dart_won) OVER w AS prev, lag(d.bsns_year) OVER w AS py
  FROM core.v_dividend_year_verified d
  JOIN core.v_financial_year_verified f USING (corp_code, bsns_year)
  WINDOW w AS (PARTITION BY d.corp_code ORDER BY d.bsns_year))
SELECT y AS 사업연도,
       CASE WHEN 10 * d >= 11 * prev THEN '1 증가 10% 이상' WHEN d >= prev THEN '2 0~10%' ELSE '3 감소' END AS 증가율,
       CASE WHEN 100 * d >= 40 * ni THEN '3 40% 이상' WHEN 100 * d >= 25 * ni THEN '2 25~40%' ELSE '1 25% 미만' END AS 배당성향,
       count(*) AS 회사수
FROM j WHERE py = y - 1 AND y <= 2025 AND d > 0 AND ni > 0 AND prev > 0
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;"""

CAPACITY_SQL = """-- 5장 재무 여력: 2025 잉여현금흐름 ÷ 2027 최소 필요 배당(배)
SELECT count(*) FILTER (WHERE cover_x < 1) AS "1배 미만",
       count(*) FILTER (WHERE cover_x >= 1 AND cover_x < 2) AS "1~2배",
       count(*) FILTER (WHERE cover_x >= 2 AND cover_x < 5) AS "2~5배",
       count(*) FILTER (WHERE cover_x >= 5) AS "5배 이상",
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY cover_x)::numeric, 2) AS 가운데값
FROM core.core_capacity_2025 WHERE cover_x IS NOT NULL;"""

EVENT_SQL = """-- 6장 대표 조건: 배당을 늘린다는 공시 · 공시일 · 배당 포함 · 자본 변동 겹침 제외 · 60거래일
SELECT kind, basis, return_type, sample, window_days, n_cases, median_pct, p25_pct, p75_pct
FROM core.core_event_summary
WHERE period = '2025년까지' AND kind = '주당배당금 증가' AND basis = '공시일'
  AND return_type = '배당 포함' AND sample = '자본 변동 겹침 제외' AND window_days = 60;"""

HOLDER_SQL = """-- 7장 2025 최대주주 종류 (OpenDART 최대주주 현황, source/core/major_holder.py 규칙)
SELECT largest_kind AS 최대주주종류, count(*) AS 회사수
FROM core.core_major_holder GROUP BY 1 ORDER BY 1;"""

MACRO_SQL = """-- 8장 변화끼리 본 상관 168칸 중 p < 0.05인 칸
SELECT count(*) AS 전체, count(*) FILTER (WHERE p < 0.05) AS "p<0.05"
FROM core.core_macro_dividend_corr WHERE kind = 'diff';"""

BEHAVIOR_SQL = """-- 8·9장 미리 정한 주 검정 4개 (노출도·제도 효과)
SELECT analysis, name, round(coef::numeric, 4) AS 계수, round(p_perm::numeric, 4) AS 순열p,
       round(p_holm::numeric, 4) AS 보정p, n, n_firms
FROM core.core_behavior_fit WHERE role = 'primary' ORDER BY analysis, name;"""

CONTROL_SQL = """-- 10장 대조군 요건 시뮬레이션 결과 (source/scripts/analyze_panel.py가 저장)
SELECT payload -> 'simulation' -> 'control_n' AS 대조군상장사, payload -> 'simulation' -> 'met' AS 요건맞춤,
       payload -> 'simulation' -> 'reit_excluded' AS 리츠제외, payload -> 'simulation' -> 'eligible' AS 될수있는곳
FROM partner.analysis_result WHERE key = 'panel';"""

TRUST_SQL = """-- 11장 원문 대조 결과
SELECT 'core_source_verify' AS 표, result, count(*) FROM core.core_source_verify GROUP BY 1, 2
UNION ALL
SELECT 'core_dart_verify', result, count(*) FROM core.core_dart_verify GROUP BY 1, 2
ORDER BY 1, 3 DESC;"""

RETRO_CMD = """# 4장 다음 해 탈락률: 판정 엔진(source/core/judgement.py)을 해마다 다시 돌려야 해서 SQL 대신 파이썬으로 확인
.venv/bin/python -c "from core import p1_analysis as p; r = p.load(); print(r.retro[r.retro['다음 해 판정 가능'] > 0].to_string()); print(r.drop_reasons.to_string())\""""


@dataclass(frozen=True)
class Check:
    ch: int
    what: str
    code: str                       # 독자에게 보여 줄 SQL이나 명령
    screen: Callable[[dict], Any]   # 화면 API 자료 → 비교할 값
    actual: Callable[[Any], Any]    # SQL 결과 행(또는 파이썬 결과) → 같은 모양 값
    run_python: Callable[[], Any] | None = None  # SQL이 아니면 이것을 돌린다


def _grid_rows(rows):
    out: dict = {}
    for y, g, p, n in rows:
        r = int(g[0]) - 1
        c = int(p[0]) - 1
        out.setdefault(int(y), [[0] * 3 for _ in range(3)])[r][c] += int(n)
    return out


def _funnel_rows(rows):
    f = dict(total=0, ga=0, na=0, na_deficit=0)
    for status, route, deemed, _, n in rows:
        f["total"] += n
        if status == "충족":
            f["ga" if route == "가목" else "na_deficit" if deemed else "na"] += n
    return f


def _retro():
    from core import p1_analysis
    r = p1_analysis.load()
    # 화면처럼 다음 해를 판정할 수 있는 해만 (2025는 다음 해가 아직 없음)
    return [[int(a), int(b), int(c), int(d), float(e)] for a, b, c, d, e in r.retro.itertuples(index=False) if c]


CHECKS = [
    Check(1, "판정 결과 회사 수(전체·가목·나목·적자 간주 나목)", FUNNEL_SQL,
          lambda s: {k: s["funnel"][k] for k in ("total", "ga", "na", "na_deficit")}, _funnel_rows),
    Check(2, "2025 배당성향 24%대·25%대 회사 수", PAYOUT_SQL,
          lambda s: {24: dict(s["analysis"]["payout"])[24], 25: dict(s["analysis"]["payout"])[25]},
          lambda rows: {24: 0, **{int(a): int(b) for a, b in rows}}),
    Check(2, "2025 배당 증가율 9%대·10%대 회사 수", GROWTH_SQL,
          lambda s: {9: dict(s["analysis"]["growth"])[9], 10: dict(s["analysis"]["growth"])[10]},
          lambda rows: {int(a): int(b) for a, b in rows}),
    Check(3, "해마다 9칸 회사 수(2018~2025 전부)", GRID_SQL,
          lambda s: {int(k): v for k, v in s["movement"]["grid"].items()}, _grid_rows),
    Check(4, "해마다 충족·다음 해 탈락·탈락률", RETRO_CMD,
          lambda s: [[r[0], r[1], r[2], r[3], r[4]] for r in s["analysis"]["retro"]], lambda x: x, run_python=_retro),
    Check(5, "재무 여력 구간별 회사 수와 가운데 값", CAPACITY_SQL,
          lambda s: [*[n for _, n in s["analysis"]["capacity"]["bins"]], s["analysis"]["capacity"]["median"]],
          lambda rows: [*[int(v) for v in rows[0][:4]], float(rows[0][4])]),
    Check(6, "대표 조건의 사례 수(공시 날)", EVENT_SQL,
          lambda s: s["analysis"]["event"]["curves"]["주당배당금 증가"][0][1], lambda rows: int(rows[0][5])),
    Check(7, "2025 최대주주 개인·법인·판단 불가 회사 수", HOLDER_SQL,
          lambda s: s["analysis"]["holder"]["notes"]["kinds"], lambda rows: {k: int(n) for k, n in rows if k}),
    Check(8, "변화끼리 본 상관 168칸과 p < 0.05 칸 수", MACRO_SQL,
          lambda s: [len([c for c in s["analysis"]["macro"]["corr"] if c[1] == "diff"]),
                     len([c for c in s["analysis"]["macro"]["corr"] if c[1] == "diff" and c[5] is not None and c[5] < 0.05])],
          lambda rows: [int(rows[0][0]), int(rows[0][1])]),
    Check(9, "주 검정 4개의 계수와 보정 p", BEHAVIOR_SQL,
          lambda s: sorted((f["name"], round(f["coef"], 4), round(f["p_holm"], 4))
                           for k in ("exposure", "policy") for f in s["analysis"]["behavior"]["fits"][k] if f["role"] == "primary"),
          lambda rows: sorted((r[1], round(float(r[2]), 4), round(float(r[4]), 4)) for r in rows)),
    Check(10, "대조군 요건 시뮬레이션(상장사·요건 맞춤·리츠 제외·될 수 있는 곳)", CONTROL_SQL,
          lambda s: [s["analysis"]["control"]["simulation"][k] for k in ("control_n", "met", "reit_excluded", "eligible")],
          lambda rows: [int(v) for v in rows[0]]),
    Check(11, "원문 대조 결과 칸 수", TRUST_SQL,
          lambda s: {**{f"source|{k}": v for k, v in s["analysis"]["trust"]["source_verify"].items()},
                     **{f"dart|{k}": v for k, v in s["analysis"]["trust"]["dart_verify"].items()}},
          lambda rows: {f"{'source' if t == 'core_source_verify' else 'dart'}|{r}": int(n) for t, r, n in rows}),
]


@dataclass(frozen=True)
class Outcome:
    check: Check
    screen: Any
    actual: Any

    @property
    def same(self) -> bool:
        return self.screen == self.actual


def run(screen: dict, url: str | None = None) -> list[Outcome]:
    """모든 확인을 돌린다. screen = {'funnel', 'analysis', 'movement', 'events'} 화면 API 응답."""
    out = []
    with db.connect(url) as conn:
        for c in CHECKS:
            raw = c.run_python() if c.run_python else conn.execute(c.code).fetchall()
            out.append(Outcome(c, c.screen(screen), c.actual(raw)))
    return out
