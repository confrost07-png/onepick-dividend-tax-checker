"""우리 638사(배당 기업)와 4조 대조군 비교 분석 → 마크다운 보고서 (partner.v_panel).

실행: .venv/bin/python -m scripts.analyze_panel [--out report/분석/대조군_비교분석_YYYYMMDD.md] [--url ...]
- 값은 상태가 '확정'(우리)·'값 있음'(4조)인 것만 쓴다. 업종 비교는 4조 업종 분류가 있는 회사만 (우리는 4조와 겹치는 435사).
- 고배당기업 요건 시뮬레이션은 source/core/judgement.py(우리 2026 판정 코드)를 그대로 쓰되, 대조군은 배당소득 B를
  현금배당총액 D로 갈음한다 (감액배당·주식배당 확인 안 함). 이 근사가 얼마나 맞는지는 우리 638사의 실제 판정과 견줘 보고서에 적는다.
- 인과 분석이 아니다: 우리 638사는 배당을 해서 뽑힌 회사들이라 두 집단은 처음부터 다르다.
"""
import argparse
import json
from bisect import bisect_left
import statistics as st
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from core import db
from core import event_study as es
from core import major_holder as mh
from core.event_stats import simple_t
from core.judgement import HOLD, MET, NOT_MET, judge_2026

ROOT = Path(__file__).resolve().parents[2]
OURS, CTRL = "우리 638사", "4조 대조군"
OK = ("확정", "값 있음")
INDUSTRIES = ["제조업", "도소매업", "건설업", "부동산임대업"]
LISTED = ("코스피", "코스닥", "유가증권")  # 우리 638사 시장 이름 · 4조 시장 이름 (코넥스·비상장·상장폐지 제외)
INDEX_OF = {"코스피": "KOSPI", "유가증권": "KOSPI", "코스닥": "KOSDAQ"}
YEARS = range(2017, 2026)


def ok(r, item, status):
    return r[item] if r[status] in OK and r[item] is not None else None


def load(conn) -> dict:
    """(source, corp_code) → {연도: 행}."""
    panel = defaultdict(dict)
    for r in db.fetch_dicts(conn, "SELECT * FROM partner.v_panel WHERE market = ANY(%s)", (list(LISTED),)):
        r = {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in r.items()}
        panel[(r["source"], r["corp_code"])][r["bsns_year"]] = r
    return panel


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "–"


def fmt(v, kind="pct"):
    if v is None:
        return "–"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "x":
        return f"{v:.2f}배"
    if kind == "eok":
        return f"{v / 1e8:,.0f}억"
    return f"{v:,.0f}"


def metrics(rows: list[dict]) -> dict:
    """회사·연도 행 목록 → 지표. 배당성향은 순이익 > 0이고 D가 있는 행, ROE·부채비율은 자본 > 0인 행."""
    d = [d_value(r) for r in rows]
    ni = [ok(r, "ni_owner_won", "ni_status") for r in rows]
    eq = [ok(r, "equity_won", "equity_status") for r in rows]
    li = [ok(r, "liabilities_won", "liabilities_status") for r in rows]
    has_d = [x for x in d if x is not None]
    payout = [100 * dd / nn for dd, nn in zip(d, ni) if dd is not None and nn and nn > 0 and dd > 0]
    roe = [100 * nn / ee for nn, ee in zip(ni, eq) if nn is not None and ee and ee > 0]
    debt = [100 * ll / ee for ll, ee in zip(li, eq) if ll is not None and ee and ee > 0]
    return {"rows": len(rows), "d_known": len(has_d), "paying": sum(1 for x in has_d if x > 0),
            "payout_med": med(payout), "payout_n": len(payout), "roe_med": med(roe), "debt_med": med(debt),
            "equity_med": med([e for e in eq if e and e > 0])}


def d_value(r):
    """배당 D: 값이 있으면 그 값. 4조 쪽이 '원문에 없음'이고 사유가 '원문 배당 표 값 '-''(배당 표에 '-')면 무배당 0.
    '그 해 사업보고서 없음' 등은 모름(None). 우리 쪽은 '-'가 이미 0으로 들어 있다."""
    if not r:
        return None
    v = ok(r, "d_won", "d_status")
    if v is not None:
        return v
    return 0.0 if r.get("d_status") == "원문에 없음" and (r.get("d_reason") or "").startswith("원문 배당 표 값") else None


def judge_row(y2025: dict | None, y2024: dict | None):
    """2026 판정 (2025 숫자). B는 D로 갈음."""
    if not y2025 or not y2024:
        return judge_2026(None, None, None, None, None)
    d25, d24 = d_value(y2025), d_value(y2024)
    to_int = lambda v: None if v is None else int(round(v))  # noqa: E731
    return judge_2026(to_int(d25), to_int(d24), to_int(d25), to_int(d24), to_int(ok(y2025, "ni_owner_won", "ni_status")),
                      to_int(ok(y2025, "liabilities_won", "liabilities_status")), to_int(ok(y2025, "equity_won", "equity_status")),
                      d_unit=1_000_000)


EXCLUDED_REIT = ("위탁관리부동산투자회사", "기업구조조정부동산투자회사")


def excluded_type(corp: str) -> str | None:
    """제104조의27①1호 단서 → 시행령 제104조의24② → 법인세법 제51조의2①4호: 위탁관리·기업구조조정 부동산투자회사는 제외.
    그 회사 최신 사업보고서 원문(4조 받은 파일) 앞부분에서 가장 먼저 나오는 리츠 종류로 본다. 자기관리 리츠는 제외 대상이 아님."""
    from core import dart_xml as dx
    from scripts import export_partner_workbook as pw
    p = _partner()
    if corp not in p.folder:
        return None
    rep = p.report(corp, 2025) or p.report(corp, 2024)
    if not rep or rep["status"] != "수집완료":
        return None
    text = pw.squash(dx.clean(dx.read_report(p.zip_path(corp, rep["rcept_no"]), rep["rcept_no"]) or ""))
    head = text[:20000]  # 표지·회사 개요: 회사 이름에 종류가 들어 있으므로 먼저 나오는 쪽
    found = [(head.find(k), k) for k in EXCLUDED_REIT + ("자기관리부동산투자회사",) if k in head]
    kind = min(found)[1] if found else None
    return kind if kind in EXCLUDED_REIT else None


_P = None


def _partner():
    global _P
    if _P is None:
        from scripts import export_partner_workbook as pw
        _P = pw.Partner(pw.SRC, set())
    return _P


def table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(head))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def prices(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(수정 종가: 거래일 × corp_code, 지수: 거래일 × KOSPI/KOSDAQ). 거래일은 지수가 있는 날."""
    idx = pd.DataFrame(db.fetch_dicts(conn, "SELECT market, trade_date, close::float AS close FROM raw.krx_market_index"))
    idx = idx.pivot(index="trade_date", columns="market", values="close").sort_index()
    rows = db.fetch_dicts(conn, """SELECT corp_code, trade_date, close_adj::float AS close FROM raw.krx_price_daily
                                   UNION ALL SELECT corp_code, trade_date, close_adj::float FROM partner.krx_price_daily""")
    px = pd.DataFrame(rows).pivot_table(index="trade_date", columns="corp_code", values="close", aggfunc="first")
    return px.reindex(idx.index), idx


def decision_events(conn, panel, ind) -> list[tuple]:
    """(집단, corp_code, 공시일, 증가/유지·감소, 시장). 1~4월 첫 배당 결정 공시 = 앞 사업연도 결산배당, 2023-01 ~ 2026-06."""
    out = []
    ours = db.fetch_dicts(conn, """SELECT corp_code, min(disclosed_on) d FROM raw.dividend_decision
                                   WHERE div_kind = '결산배당' AND NOT coalesce(is_correction, false)
                                     AND substr(disclosed_on, 6, 2) IN ('01','02','03','04') GROUP BY corp_code, substr(disclosed_on, 1, 4)""")
    ctrl = db.fetch_dicts(conn, """SELECT corp_code, min(rcept_dt)::text d FROM partner.filing f JOIN partner.company c USING (corp_code)
                                   WHERE c.grp = '대조군' AND f.pblntf_ty = 'I' AND replace(f.report_nm, ' ', '') LIKE '%%배당결정%%'
                                     AND f.report_nm NOT LIKE '[%%' AND extract(month FROM f.rcept_dt) <= 4
                                   GROUP BY corp_code, extract(year FROM f.rcept_dt)""")
    for src, rows in ((OURS, ours), (CTRL, ctrl)):
        for r in rows:
            d = date.fromisoformat(str(r["d"])[:10])
            if not (date(2023, 1, 1) <= d <= date(2026, 6, 30)):
                continue
            v = panel.get((src, r["corp_code"]))
            if not v or not ind.get((src, r["corp_code"])):
                continue
            y = d.year - 1
            a, b = (ok(v.get(y), "dps_common_won", "dps_status") if v.get(y) else None,
                    ok(v.get(y - 1), "dps_common_won", "dps_status") if v.get(y - 1) else None)
            if not a or b is None:
                continue
            market = next(iter(v.values()))["market"]
            out.append((src, r["corp_code"], d, "증가" if a > b else "유지·감소", market))
    return out


def price_sections(conn, panel, ind, out: dict) -> list[str]:
    px, idx = prices(conn)
    days = list(idx.index)
    L = ["## 6. 배당 결정 공시 뒤 주가 반응 (우리 vs 대조군, 같은 방법)", "",
         "1~4월 첫 배당 결정 공시(앞 사업연도 결산배당, 2023-01 ~ 2026-06)를 이벤트로, 공시일(0)부터 20·60거래일 누적 초과수익률 CAR = "
         "Σ(종목 − 코스피/코스닥 지수 수익률), 수정주가 기준·배당 미포함. 창 안에 하루 ±30%(가격제한폭)를 넘는 날이 있으면 뺌. 증가 = 그 사업연도 보통주 DPS가 앞 해보다 큼 (사업보고서 배당 표). "
         "우리 팀 공식 이벤트 스터디(`report/분석/이벤트스터디_방법별_결과.md`)와 방법이 달라 숫자가 같지 않다 — 두 집단을 같은 잣대로 견주는 용도.", ""]
    cars = defaultdict(list)
    for src, corp, d, kind, market in decision_events(conn, panel, ind):
        if corp not in px.columns or INDEX_OF.get(market) not in idx.columns:
            continue
        i = bisect_left(days, d)
        for w in (20, 60):
            c = es.car(px[corp], idx[INDEX_OF[market]], i, w)
            jump = px[corp].iloc[max(i - 1, 0): i + w + 1].pct_change().abs().max()
            if c is not None and not jump > 0.3:  # 가격제한폭(±30%)을 넘는 날이 창 안에 있으면 자료 이상으로 보고 뺌
                cars[(src, kind, w)].append(100 * c)
    rows = []
    for w in (20, 60):
        for kind in ("증가", "유지·감소"):
            for src in (OURS, CTRL):
                xs = np.array(cars[(src, kind, w)])
                if len(xs) < 10:
                    rows.append([f"{w}일", kind, src, len(xs), "–", "–", "–"])
                    out["car"].append([w, kind, src, len(xs), None, None, None])
                    continue
                t, p = simple_t(xs)
                rows.append([f"{w}일", kind, src, len(xs), f"{xs.mean():.2f}", f"{np.median(xs):.2f}", f"{p:.3f}"])
                out["car"].append([w, kind, src, len(xs), round(float(xs.mean()), 2), round(float(np.median(xs)), 2), round(float(p), 4)])
    L += table(["창", "DPS", "집단", "사례", "평균 CAR(%p)", "중앙값(%p)", "평균=0 t검정 p"], rows) + [""]

    L += ["## 7. 연도별 주가 수익률 (지수 대비, 중앙값)", "",
          "수익률 = 연말 종가 ÷ 앞 해 연말 종가 − 1 (수정주가, 배당 미포함). 초과 = 수익률 − 소속 시장 지수 수익률. 그해 처음과 끝에 주가가 있는 회사만. 2018은 1월 2일부터, 2026은 10월 20일까지.", ""]
    ends = {}
    for y in range(2017, 2027):
        sel = [dd for dd in days if dd.year == y]
        if sel:
            ends[y] = sel[-1]
    rows = []
    for y in range(2018, 2027):
        if y not in ends or y - 1 not in ends and y != 2018:
            continue
        start = ends.get(y - 1, days[0])
        line = [str(y) + (" (10.20까지)" if y == 2026 else "")]
        rec = [y]
        for src in (OURS, CTRL):
            ex, raw = [], []
            for k, v in panel.items():
                if k[0] != src or not ind[k] or k[1] not in px.columns:
                    continue
                m = INDEX_OF.get(next(iter(v.values()))["market"])
                a, b = px.at[start, k[1]], px.at[ends[y], k[1]]
                if m and pd.notna(a) and pd.notna(b) and a > 0:
                    raw.append(100 * (b / a - 1))
                    ex.append(100 * (b / a - 1 - (idx.at[ends[y], m] / idx.at[start, m] - 1)))
            line += [f"{len(ex):,}", fmt(med(raw)), fmt(med(ex))]
            rec += [len(ex), r1(med(raw)), r1(med(ex))]
        idx_ret = [100 * (idx.at[ends[y], mk] / idx.at[start, mk] - 1) for mk in ("KOSPI", "KOSDAQ")]
        line += [fmt(v) for v in idx_ret]
        rows.append(line)
        out["returns"].append(rec + [r1(v) for v in idx_ret])
    out["returns_end"] = ends[2026].isoformat() if 2026 in ends else None
    L += table(["연도", "우리 회사", "우리 수익률", "우리 초과", "대조군 회사", "대조군 수익률", "대조군 초과", "코스피", "코스닥"], rows) + [""]
    L += ["초과수익률이 크게 마이너스인 해(2020·2023·2025)는 대형주가 지수를 끌어올린 해다 (예: 2025 코스피 +75.6%, 우리 KRX 지수 자료). "
          "두 집단을 견줄 때는 같은 해의 두 집단 값끼리 본다.", ""]
    return L


SUMMARY = """## 핵심 요약 (2026-11-02 결과를 보고 쓴 글 — 다시 돌려 숫자가 바뀌면 이 부분도 고칠 것)

1. **같은 업종이면 우리 638사가 대조군보다 배당을 많이 하고, 돈을 더 잘 벌고, 빚이 적고, 크다.** 2025 제조업 중앙값: 배당성향 44.9% vs 15.0%, ROE 4.6% vs 0.6%, 부채비율 42.7% vs 73.1%, 자본 2,007억 vs 1,047억.
2. **대조군은 배당하는 회사가 줄고 있다.** 4개 업종 대조군 중 배당한 회사 비율 2017 45.0% → 2025 35.0%. 우리 638사는 77.2% → 99.5% (2025는 뽑힌 기준이 섞여 튐).
3. **2025에만 배당 증액 비율이 크게 벌어졌다.** 배당을 10% 이상 늘린 회사 비율이 2018~2024는 두 집단 모두 28~48%로 비슷했는데, 2024→2025는 우리 66.5% vs 대조군 34.8%. 제도 대응인지, 우리 638사를 뽑은 기준 때문인지는 이 자료로 가를 수 없다.
4. **대조군 상장사 1,414사에 우리 판정 코드를 돌리면, 배당 숫자로 요건을 맞추는 회사는 17곳이고 그중 12곳은 위탁관리·기업구조조정 리츠라 법으로 제외된다** (조세특례제한법 제104조의27 ①1호 단서 → 시행령 제104조의24 ② → 법인세법 제51조의2 ①4호). 그래서 실제로 고배당기업이 될 수 있는 대조군 회사는 **5곳**(HD건설기계·유비쿼스·일월지엠엘·방림·풍강)뿐이다. 근사(B = D)는 우리 638사에서 실제 판정과 97.7% 같았다. 우리 638사에 리츠가 없는 것도 이 제외 규정과 맞는다.
5. **배당을 유지·줄인다는 공시 뒤 60거래일 주가는 대조군이 더 약했다.** 시장 대비 평균 우리 −2.25%p vs 대조군 −5.04%p (둘 다 0과 다름, p 0.007·0.000). 배당을 늘린다는 공시는 두 집단 모두 0과 뚜렷이 다르지 않았다.
6. **해마다 시장 대비 주가 수익률은 9년 중 7년 우리 638사가 대조군보다 좋았다** (2019·2020 제외). 단, 우리 638사는 2026 기준 고배당기업이라 '나중에 잘된 회사'가 뽑혔을 수 있다 (사후 선택 편향) → 수익률 차이를 배당 효과로 읽으면 안 된다.

"""


def r1(v):
    return None if v is None else round(float(v), 1)


def report(conn, out: dict | None = None) -> str:
    """마크다운 보고서. out을 주면 화면(데이터 이야기)에 쓸 숫자를 함께 채운다 (save()가 DB에 저장)."""
    out = {} if out is None else out
    for key in ("industry_2025", "trend", "increase", "car", "returns", "holder"):
        out[key] = []
    panel = load(conn)
    ind = {k: next(iter(v.values()))["industry_4jo"] for k, v in panel.items()}
    names = {k: next(iter(v.values()))["corp_name"] for k, v in panel.items()}
    L = [f"# 우리 638사 vs 4조 대조군 비교 분석", "",
         f"- 만든 날: {date.today().isoformat()} · `source/scripts/analyze_panel.py` · 원천 `partner.v_panel` (우리: core 확정 값, 대조군: 4조참치 협조 자료)",
         "- 값은 상태가 '확정'(우리)·'값 있음'(4조)인 것만. 업종 비교는 4조 업종 분류가 있는 회사만 (우리 638사 중 4조와 겹치는 435사).",
         "- **인과 분석이 아님**: 우리 638사는 배당을 해서 뽑힌 회사라 두 집단은 처음부터 다르다. 아래는 차이를 보여 주는 기술 통계.",
         "  특히 2025 값은 우리 638사가 최근 배당 실적으로 뽑혔기 때문에 크게 튄다 (뽑힌 기준이 결과에 섞임). 2024 이전 추이와 함께 본다.",
         "- 무배당: 배당 표에 '-'로 적힌 해는 D = 0으로 센다. 그 해 사업보고서가 없는 회사·연도는 빼고 센다.",
         "- 두 집단 모두 유가증권(코스피)·코스닥 상장사만 (4조 대조군의 코넥스 73사·비상장·상장폐지 355사는 뺌).",
         "- 대조군 주가: 네이버 금융 차트 수정주가 (`partner.krx_price_daily`, 우리 KRX 수정 종가와 표본 8개사 모든 거래일 같음).", ""]

    L += SUMMARY.splitlines()
    # 1. 표본
    L += ["## 1. 표본", ""]
    rows = []
    for src in (OURS, CTRL):
        for i in INDUSTRIES + [None]:
            ks = [k for k in panel if k[0] == src and ind[k] == i]
            if not ks:
                continue
            cy = sum(len(panel[k]) for k in ks)
            rows.append([src, i or "업종 분류 없음 (지주회사 등)", f"{len(ks):,}", f"{cy:,}"])
            out.setdefault("sample", []).append([src, i, len(ks), cy])
    L += table(["집단", "4조 업종", "회사", "회사·연도"], rows) + [""]

    # 2. 2025 비교
    L += ["## 2. 2025 사업연도 비교 (같은 업종끼리)", "",
          "배당한 비율 = D가 알려진 회사 중 D > 0 · 배당성향 = D ÷ 지배주주 순이익 (순이익 > 0, D > 0) · ROE = 순이익 ÷ 자본 · 부채비율 = 부채 ÷ 자본 (자본 > 0). 모두 중앙값.", ""]
    rows = []
    for i in INDUSTRIES:
        for src in (OURS, CTRL):
            m = metrics([v[2025] for k, v in panel.items() if k[0] == src and ind[k] == i and 2025 in v])
            if not m["rows"]:
                continue
            rows.append([i, src, f"{m['rows']:,}", pct(m["paying"], m["d_known"]), fmt(m["payout_med"]), fmt(m["roe_med"]),
                         fmt(m["debt_med"]), fmt(m["equity_med"], "eok")])
            out["industry_2025"].append([i, src, m["rows"], r1(100 * m["paying"] / m["d_known"]) if m["d_known"] else None,
                                         r1(m["payout_med"]), r1(m["roe_med"]), r1(m["debt_med"]),
                                         round(m["equity_med"] / 1e8) if m["equity_med"] else None])
    L += table(["업종", "집단", "회사", "배당한 비율", "배당성향", "ROE", "부채비율", "자본 규모"], rows) + [""]

    # 3. 추이
    L += ["## 3. 연도별 추이 (4개 업종 합계)", ""]
    rows = []
    for y in YEARS:
        line, rec = [str(y)], [y]
        for src in (OURS, CTRL):
            m = metrics([v[y] for k, v in panel.items() if k[0] == src and ind[k] and y in v])
            line += [pct(m["paying"], m["d_known"]), fmt(m["payout_med"])]
            rec += [r1(100 * m["paying"] / m["d_known"]) if m["d_known"] else None, r1(m["payout_med"])]
        rows.append(line)
        out["trend"].append(rec)
    L += table(["연도", "우리 배당한 비율", "우리 배당성향", "대조군 배당한 비율", "대조군 배당성향"], rows) + [""]

    # 4. 증가
    L += ["## 4. 배당을 10% 이상 늘린 회사 비율 (4개 업종 합계)", "",
          "전년과 올해 모두 D > 0인 회사 중, 올해 D가 전년의 110% 이상인 비율. 고배당기업 요건 나목('10% 이상 증가')과 같은 기준.", ""]
    rows = []
    for y in range(2018, 2026):
        line, rec = [f"{y - 1}→{y}"], [y]
        for src in (OURS, CTRL):
            pairs = []
            for k, v in panel.items():
                if k[0] != src or not ind[k] or y not in v or y - 1 not in v:
                    continue
                a, b = d_value(v[y - 1]), d_value(v[y])
                if a and b and a > 0 and b > 0:
                    pairs.append(b >= 1.1 * a)
            line += [f"{len(pairs):,}", pct(sum(pairs), len(pairs))]
            rec += [len(pairs), r1(100 * sum(pairs) / len(pairs)) if pairs else None]
        rows.append(line)
        out["increase"].append(rec)
    L += table(["기간", "우리 회사 수", "우리 10%↑", "대조군 회사 수", "대조군 10%↑"], rows) + [""]

    # 5. 요건 시뮬레이션
    L += ["## 5. 고배당기업 요건 시뮬레이션 (2026 판정, 2025 숫자)", "",
          "`source/core/judgement.py`의 판정 함수를 그대로 쓰고, 배당소득 B는 현금배당총액 D로 갈음 (감액배당·주식배당은 보지 않음).", ""]
    actual = {r["corp_code"]: r["status"] for r in db.fetch_dicts(conn, "SELECT corp_code, status FROM core.core_judgement_2026")}
    agree, cmp_n, conf = 0, 0, Counter()
    for k, v in panel.items():
        if k[0] != OURS or k[1] not in actual:
            continue
        j = judge_row(v.get(2025), v.get(2024))
        conf[(actual[k[1]], j.status)] += 1
        if actual[k[1]] != HOLD and j.status != HOLD:
            cmp_n += 1
            agree += actual[k[1]] == j.status
    L += [f"**근사가 맞는지 (우리 638사)**: 실제 판정(B 사용)과 근사 판정(B = D)이 둘 다 보류가 아닌 {cmp_n}사 중 "
          f"{agree}사({pct(agree, cmp_n)})가 같은 결과.", ""]
    L += table(["실제 판정 \\ 근사 판정", MET, NOT_MET, HOLD],
               [[a] + [conf[(a, b)] for b in (MET, NOT_MET, HOLD)] for a in (MET, NOT_MET, HOLD)]) + [""]
    res = {k: judge_row(v.get(2025), v.get(2024)) for k, v in panel.items() if k[0] == CTRL}
    excluded = {}
    for k, r in res.items():  # 요건 숫자를 맞춘 회사만 원문으로 회사 종류 확인 (리츠 제외 규정)
        if r.status == MET:
            t = excluded_type(k[1])
            if t:
                excluded[k] = t
    rows = []
    for i in INDUSTRIES:
        c = Counter((r.status, r.route) for k, r in res.items() if ind[k] == i)
        n = sum(c.values())
        rows.append([i, f"{n:,}", c[(MET, "가목")], c[(MET, "나목")], sum(v for (s, _), v in c.items() if s == NOT_MET),
                     sum(v for (s, _), v in c.items() if s == HOLD)])
    tot = Counter((r.status, r.route) for r in res.values())
    rows.append(["합계", f"{sum(tot.values()):,}", tot[(MET, "가목")], tot[(MET, "나목")],
                 sum(v for (s, _), v in tot.items() if s == NOT_MET), sum(v for (s, _), v in tot.items() if s == HOLD)])
    L += ["**대조군 (우리 638사 밖 상장사)**", ""]
    L += table(["업종", "회사", "충족 (가목 40%↑)", "충족 (나목 25%↑·10% 증가)", "미충족", "판정 보류"], rows) + [""]
    holds = Counter(r.reasons[0].split(":")[0] if r.reasons else "" for r in res.values() if r.status == HOLD)
    L += ["판정 보류 사유: " + " · ".join(f"{k} {v:,}" for k, v in holds.most_common(4)), ""]
    met = sorted(((k, panel[k][2025]) for k, r in res.items() if r.status == MET and 2025 in panel[k]),
                 key=lambda t: -(d_value(t[1]) or 0))
    L += [f"**배당 숫자로는 요건을 맞추는 대조군 회사 {len(met)}곳** — 이 중 {len(excluded)}곳은 위탁관리·기업구조조정 리츠라 "
          "고배당기업에서 처음부터 빠진다: 조세특례제한법 제104조의27 ①1호 단서 → 시행령 제104조의24 ② "
          "('「법인세법」 제51조의2제1항 각 호의 어느 하나에 해당하는 내국법인') → 법인세법 제51조의2 ①4호 "
          "('「부동산투자회사법」에 따른 기업구조조정 부동산투자회사 및 위탁관리 부동산투자회사'). 회사 종류는 각 회사 사업보고서 원문으로 확인. "
          f"**제외 대상이 아닌 회사는 {len(met) - len(excluded)}곳.**", ""]
    L += table(["회사", "업종", "2025 D", "2025 순이익", "배당성향", "경로", "제1호 단서"],
               [[names[k], ind[k], fmt(d_value(r), "eok"), fmt(ok(r, "ni_owner_won", "ni_status"), "eok"),
                 fmt(100 * d_value(r) / ok(r, "ni_owner_won", "ni_status")) if (ok(r, "ni_owner_won", "ni_status") or 0) > 0 else "적자 간주",
                 res[k].route, f"제외 ({excluded[k]})" if k in excluded else "해당 없음"] for k, r in met]) + [""]

    out["simulation"] = {
        "approx_n": cmp_n, "approx_agree": agree, "control_n": sum(tot.values()), "met": len(met), "reit_excluded": len(excluded),
        "eligible": len(met) - len(excluded), "not_met": sum(v for (s, _), v in tot.items() if s == NOT_MET),
        "hold": sum(v for (s, _), v in tot.items() if s == HOLD),
        "by_industry": [[i] + [sum(1 for k, r in res.items() if ind[k] == i and r.status == st) for st in (MET, NOT_MET, HOLD)]
                        + [sum(1 for k in excluded if ind[k] == i)] for i in INDUSTRIES]}
    L += price_sections(conn, panel, ind, out)
    L += holder_section(conn, panel, ind, out)
    L += ["## 읽을 때 주의", "",
          "- 대조군 D·순이익은 사람 검토를 거치지 않은 값이다 (기계 검증만). 순이익 '검산 안 맞음' 표시 행이 있다.",
          "- D 기준: 우리는 다음 해 보고서가 고쳐 적은 값을 쓴 해가 있고, 대조군은 그 해 보고서 당기 칸이다 (겹침 435사 대조에서 63칸 차이).",
          "- 요건 시뮬레이션의 B = D 근사는 감액배당(비과세)·주식배당을 반영하지 않는다. 결과는 '요건을 맞출 가능성이 큰 회사' 목록으로 읽는다.",
          "- 대조군은 4조가 고른 4개 업종(제조·도소매·건설·부동산임대)뿐이다. 지금 상장된 회사만 남겨서, 기간 중 상장폐지된 회사가 빠진 생존 편향이 있다 (우리 638사도 마찬가지).",
          "- 주가 반응의 증가·유지 구분은 배당 결정 공시 본문이 아니라 사업보고서 연간 보통주 DPS로 했다 (중간·분기배당이 섞인 회사는 결산배당만의 증감과 다를 수 있음).", ""]
    return "\n".join(L)


HOLDER_BINS = [("20% 미만", 0, 20), ("20~30%", 20, 30), ("30~40%", 30, 40), ("40~50%", 40, 50), ("50% 이상", 50, None)]


def holder_pcts(conn, panel) -> dict:
    """(source, corp_code) → (2025 최대주주+특수관계인 보통주 지분율, 최대주주 개인/법인).
    우리는 core.core_major_holder, 대조군은 partner.major_holder('값 있음' 행)에 같은 규칙(source/core/major_holder.py summarize)."""
    out = {}
    for r in db.fetch_dicts(conn, "SELECT corp_code, pct_common, largest_kind FROM core.core_major_holder WHERE bsns_year = 2025"):
        out[(OURS, r["corp_code"])] = (float(r["pct_common"]) if r["pct_common"] is not None else None, r["largest_kind"])
    rows = defaultdict(list)
    for r in db.fetch_dicts(conn, "SELECT * FROM partner.major_holder WHERE bsns_year = 2025 AND status = '값 있음' ORDER BY corp_code, seq"):
        rows[r["corp_code"]].append(r)
    for corp, rs in rows.items():
        h = mh.summarize(rs)
        out[(CTRL, corp)] = (float(h.pct_common) if h.pct_common is not None else None, h.largest_kind)
    return {k: v for k, v in out.items() if k in panel}


def holder_section(conn, panel, ind, out: dict) -> list[str]:
    """2025 최대주주+특수관계인 보통주 지분율: 같은 업종끼리 가운데 값·사분위, 지분 구간 분포, 최대주주가 개인인 비율."""
    hp = holder_pcts(conn, panel)
    L = ["## 7. 최대주주·특수관계인 지분 (2025 사업보고서)", "",
         "지분율 = 최대주주 + 특수관계인 보통주 기말 지분율 합계 ('계' 행 우선, 없으면 보통주 행 합). 두 집단 모두 `source/core/major_holder.py` 같은 규칙.",
         "개인/법인은 이름·관계 칸 글자 규칙이라 '판단 불가'가 있다. 같은 업종(4조 업종 분류가 있는 회사)끼리.", ""]
    rows = []
    for i in INDUSTRIES + [None]:
        for src in (OURS, CTRL):
            vals = [v for k, v in hp.items() if k[0] == src and ind[k] and (i is None or ind[k] == i)]
            xs = sorted(p for p, _ in vals if p is not None)
            if len(xs) < 5:
                continue
            q1, q2, q3 = np.percentile(xs, [25, 50, 75])
            kinds = Counter(kd for _, kd in vals)
            person = r1(100 * kinds[mh.PERSON] / len(vals))
            name = i or "4개 업종 합계"
            rows.append([name, src, f"{len(xs):,}", fmt(q2), f"{fmt(q1)} ~ {fmt(q3)}", f"{person}%"])
            out["holder"].append({"industry": name, "group": src, "n": len(xs), "median": r1(q2), "p25": r1(q1), "p75": r1(q3),
                                  "person_pct": person,
                                  "bins": [[b, sum(1 for x in xs if x >= lo and (hi is None or x < hi))] for b, lo, hi in HOLDER_BINS]})
    return L + table(["업종", "집단", "회사", "지분율 가운데 값", "가운데 절반", "최대주주 개인"], rows) + [""]


def save(conn, out: dict) -> None:
    """화면(데이터 이야기 '대조군과 비교' 장)이 읽을 결과를 partner.analysis_result에 저장 (분석이 1~2분 걸려 화면에서 계산하지 않음)."""
    db.apply_schema(conn)
    conn.execute("DELETE FROM partner.analysis_result WHERE key = 'panel'")
    conn.execute("INSERT INTO partner.analysis_result (key, payload) VALUES ('panel', %s)", (json.dumps(out, ensure_ascii=False),))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="우리 638사 vs 대조군 비교 분석 보고서 + 화면용 결과 저장")
    ap.add_argument("--out", type=Path, default=ROOT / "report" / "분석" / f"대조군_비교분석_{date.today():%Y%m%d}.md")
    ap.add_argument("--url", default=db.database_url())
    a = ap.parse_args()
    out = {}
    with db.connect(a.url) as conn:
        text = report(conn, out)
        save(conn, out)
    a.out.write_text(text, encoding="utf-8")
    print(a.out, "· partner.analysis_result 저장")
