"""API가 돌려줄 값 만들기. 계산은 source/core/ 모듈을 그대로 부르고, 여기서는 JSON 모양만 맞춘다."""
import json
import re
import statistics
from functools import lru_cache
from pathlib import Path

from core import behavior_data, company_alias, term_dict, isa_irp, personas, company_repo, db, holder_analysis, macro_dividend, p1_analysis, tax, tax_rates
from core import sample_data as text
from core.chat_parse import NONE_WORDS, UNKNOWN, UNKNOWN_WORDS, Parser, match_company, mentions_shares, object_josa, parse_amount, topic_josa
from core.checkup import Checkup, StockCheck, check_stock, run_checkup
from core.faq_search import FaqSearch
from core.judgement import HOLD, MET
from core.law_search import LawSearch
from core.llm_ollama import NOT_PAGE2, get_llm, read_holdings_image, read_receipt_image
from core.tax import COMPARED, NO_DIFFERENCE
from ui.components import won

# 공시 뒤 주가 반응: 주 분석 조건 (report/분석/이벤트스터디_방법별_결과.md '주 분석')
EVENT_KINDS = ("주당배당금 증가", "주당배당금 유지·감소")
EVENT_WHERE = ("period='2025년까지' and window_days=60 and basis='공시일' and return_type='배당 포함' "
               "and sample='자본 변동 겹침 제외'")


@lru_cache(maxsize=1)
def companies() -> dict:
    """DB의 실제 회사 638곳 {회사명: RealCompany}. 서버가 켜질 때 한 번 읽는다."""
    return company_repo.load()


@lru_cache(maxsize=1)
def prefs() -> tuple[dict, dict]:
    """상장 우선주 ({우선주 이름: 회사}, {계산하지 못한 우선주: 이유}). 요건 판정은 보통주 회사와 같고 주당배당금만 우선주 값."""
    return company_repo.load_prefs(companies())


@lru_cache(maxsize=1)
def name_index() -> dict[str, str]:
    return {**company_repo.name_index(companies()), **company_repo.pref_index(prefs()[0])}


@lru_cache(maxsize=1)
def law() -> LawSearch:
    return LawSearch.from_files()


@lru_cache(maxsize=1)
def faq() -> FaqSearch:
    return FaqSearch.from_files()


def looks_like_question(answer: str) -> bool:
    """숫자가 없고 질문하는 말이 있으면 답이 아니라 질문으로 본다. 앱(app_pages/chatbot.py `_looks_like_question`)과 같은 규칙."""
    if any(ch.isdigit() for ch in answer):
        return False
    if any(w in answer for w in UNKNOWN_WORDS + NONE_WORDS + ("있",)):
        return False
    return any(w in answer for w in text.QUESTION_WORDS)


def looks_like_term(answer: str, kind: str) -> bool:
    """'배당락', '과세표준이란'처럼 숫자 없이 단어만 적은 말. 답(없음·모름·있음·회사 이름·배당 종류)이면 아니다.
    맞으면 금융 상식 답을 찾아 보고, 없으면 원래대로 답으로 읽는다."""
    t = answer.strip()
    if not t or len(t) > 20 or any(ch.isdigit() for ch in t):
        return False
    if any(w in t for w in UNKNOWN_WORDS + NONE_WORDS + ("있",)):
        return False
    if kind == "other_dividend" and any(w in t for w in text.FOREIGN_WORDS + text.DOMESTIC_WORDS):
        return False
    return match_company(t, name_index())[0] is None


_SKIP_ANSWERS = {"없음": ("없음", "없어요", "없어", "없습니다", "종목 없음", "보유 종목 없음"),
                 "모름": ("모름", "몰라요", "몰라", "모르겠어요", "잘 모르겠어요")}


def holdings_skip(answer: str) -> str | None:
    """① 보유 종목에 '없음'·'모름'만 적었으면 그 말. '배당락 모르겠어요' 같은 문장은 해당하지 않는다."""
    t = re.sub(r"[\s.!?~]", "", answer)
    t = re.sub(r"^(?:보유|가진|갖고있는)?(?:주식|종목)(?:은|이|도)?", "", t) or t  # '주식 없음', '보유 주식은 없어요'
    return next((k for k, words in _SKIP_ANSWERS.items() if t in {w.replace(" ", "") for w in words}), None)


def faq_answer(question: str) -> dict | None:
    """금융 상식 질문과 가장 가까운 고정 답변을 그대로 돌려준다. 답을 만들지 않는다. 없으면 None."""
    hit = faq().search(question)
    if hit is None:
        return None
    f = hit.faq
    return {"id": f.id, "title": f.title, "answer": f.answer, "source_label": f.source_label, "source_url": f.source_url,
            "notice": text.FAQ_NOTICE, "by": text.FAQ_BY[hit.by]}


def term_answer(question: str) -> dict | None:
    """금융위원회 금융용어사전·원픽 보충 용어에서 용어 이름이 정확히 맞는 항목을 그대로 돌려준다(생성 없음). 없으면 None."""
    e = term_dict.find(question)
    if e is None:
        return None
    # 팀이 미리 쓴 금융 상식 답에 같은 용어가 있으면 그쪽을 쓴다(ETF·PER·우선주 …)
    asked = term_dict.key(term_dict.term_of(question))
    if any(asked in term_dict.keys_of(f.title) for f in faq().faqs):
        return None
    return {"id": f"term-{e.kind}-{term_dict.key(e.term)}", "title": e.term, "answer": e.definition,
            "source_label": e.source_name, "source_url": e.source_url, "notice": text.TERM_NOTICE[e.kind], "by": text.TERM_BY}


def by_code(code: str):
    return next((c for c in companies().values() if getattr(c, "stock_code", "") == code), None)


# --- 회사 ---

def search(q: str, limit: int = 8) -> list[dict]:
    q = re.sub(r"[\s'\"‘’“”`.,·]", "", q).upper()  # 띄어쓰기·따옴표·문장부호는 빼고 찾는다("삼성전자'"도 찾게)
    if not q:
        return []
    out = []
    for name, c in companies().items():
        key = name.replace(" ", "").upper()
        if q in key or c.stock_code.startswith(q):
            out.append((not key.startswith(q), len(name), name, c.stock_code))
    return [{"name": n, "code": code} for _, _, n, code in sorted(out)[:limit]]


def _link(html: str) -> dict | None:
    m = re.match(r'<a href="([^"]+)"[^>]*>([^<]+)</a>(.*)', html)
    return {"url": m.group(1), "label": m.group(2), "note": m.group(3).strip(" ·")} if m else None


def stock_view(s: StockCheck) -> dict:
    c, j, base = s.company, s.judgement, s.base_scenario
    return {
        "name": c.name, "code": getattr(c, "stock_code", ""), "pref_of": getattr(c, "pref_of", "") or None, "status": j.status, "route": j.route,
        "reasons": j.reasons, "deemed_payout": j.deemed_payout, "listed_2025": c.kind_2025,
        "b2024": c.b2024, "b2025": c.b2025, "d2024": c.d2024, "d2025": c.d2025,
        "b_growth_pct": round((c.b2025 / c.b2024 - 1) * 100, 1) if c.b2024 and c.b2025 is not None else None,
        "d_growth_pct": s.growth_2025_pct, "payout_pct": s.payout_2025_pct,
        "need_2027": base.result.amount if base and base.result.amount is not None else None,
        "need_status": base.result.status if base else None,
        "ratio_to_2025_pct": base.ratio_to_2025_pct if base else None,
        "sources": [x for x in (_link(h) for h in getattr(c, "sources", ())) if x],
    }


def company(code: str) -> dict | None:
    c = by_code(code)
    return stock_view(check_stock(c, 1)) if c else None


# --- 판정 흐름 (법 토너먼트) ---

def funnel() -> dict:
    """core.core_judgement_2026을 라운드별로 센다. 1라운드 자료 확인 → 2라운드 제2호 → 3라운드 제3호."""
    with db.connect() as conn:
        rows = conn.execute("select status, route, reasons, deemed_payout_pct from core.core_judgement_2026").fetchall()
    f = dict(total=len(rows), hold_missing=0, fail2=0, ga=0, na=0, na_deficit=0, hold_zero=0, fail3=0)
    for status, route, reasons, deemed in rows:
        first = (reasons[0] if isinstance(reasons, list) else str(reasons)) if reasons else ""
        if status == HOLD:
            f["hold_zero" if first.startswith("전전") else "hold_missing"] += 1
        elif status == MET:
            f["ga" if route == "가목" else "na_deficit" if deemed is not None else "na"] += 1
        else:
            f["fail2" if first.startswith("제2호") else "fail3"] += 1
    return f


# --- 데이터 이야기 ---

def _records(df) -> list[list]:
    return [[None if v != v else v for v in row] for row in df.itertuples(index=False)]  # NaN → None


EVENT_METHODS = Path(__file__).resolve().parents[2] / "data" / "processed" / "analysis" / "event_methods.json"
PROFIT_DIVIDEND = Path(__file__).resolve().parents[2] / "data" / "processed" / "analysis" / "profit_dividend.json"  # source/scripts/analyze_profit_dividend.py
COVER_BINS = [("1배 미만", None, 1), ("1~2배", 1, 2), ("2~5배", 2, 5), ("5배 이상", 5, None)]


def analysis() -> dict:
    p = p1_analysis.load()
    with db.connect() as conn:
        rows = conn.execute(f"select kind, day, n_cases, median_pct, p25_pct, p75_pct from core.core_event_curve "
                            f"where {EVENT_WHERE} and kind = any(%s) order by kind, day", (list(EVENT_KINDS),)).fetchall()
    curves: dict = {}
    for kind, day, n, med, p25, p75 in rows:
        curves.setdefault(kind, []).append([int(day), int(n), float(med), float(p25), float(p75)])
    return {
        "retro": [r for r in _records(p.retro) if r[2]],  # 사업연도, 충족, 다음 해 판정 가능, 다음 해 탈락, 탈락률(%)
        "drop_reasons": _records(p.drop_reasons),
        "payout": [r for r in _records(p.payout) if 10 <= r[0] <= 59],
        "growth": _records(p.growth),  # 증가율(%) 구간 하한, 회사 수
        "min_ratio": _records(p.min_ratio),
        "notes": {k: v for k, v in p.notes.items() if isinstance(v, (int, float, str))},
        "event": {"basis": "공시일 · 배당 포함 · 시장조정(종목 − 시장지수) · 60거래일 · 2025년까지 · 자본 변동 겹침 제외", "curves": curves},
        "holder": holder(),
        "macro": macro(),
        "behavior": behavior(),
        "capacity": capacity(),
        "trust": trust(),
        "control": control(),
    }


def events() -> dict:
    """공시 뒤 주가 반응 탐색: 2025년까지의 모든 조건(공시 종류·기준일·수익률·표본·창)별 곡선과 요약, 방법별 검정."""
    with db.connect() as conn:
        summary = conn.execute("select kind, basis, return_type, sample, window_days, n_cases, median_pct, p25_pct, p75_pct "
                               "from core.core_event_summary where period = '2025년까지' and shown").fetchall()
        rows = conn.execute("select kind, basis, return_type, sample, window_days, day, n_cases, median_pct, p25_pct, p75_pct "
                            "from core.core_event_curve where period = '2025년까지' order by day").fetchall()
    curves: dict = {}
    for kind, basis, ret, sample, w, day, n, med, p25, p75 in rows:
        if med is not None:
            curves.setdefault("|".join([kind, basis, ret, sample, str(w)]), []).append(
                [int(day), int(n), float(med), float(p25), float(p75)])
    methods = json.loads(EVENT_METHODS.read_text(encoding="utf-8")) if EVENT_METHODS.exists() else None
    return {
        "summary": [{"kind": k, "basis": b, "ret": r, "sample": s, "window": int(w), "n": int(n),
                     "median": float(m), "p25": float(a), "p75": float(c)} for k, b, r, s, w, n, m, a, c in summary],
        "curves": curves,
        "methods": methods,  # source/scripts/event_methods.py 결과 (report/분석/이벤트스터디_방법별_결과.md와 같은 값)
    }


LAST_FULL_YEAR = 2025  # 2026 사업연도는 아직 끝나지 않아 뺀다


def movement() -> dict:
    """8년 움직이는 산점도: 해마다 회사별 배당성향과 이익배당금액(D) 증가율. 회사는 번호로만(이름 없음)."""
    with db.connect() as conn:
        rows = conn.execute("""select d.corp_code, d.bsns_year::int, d.d_dart_won, f.ni_owner_won
                               from core.v_dividend_year_verified d join core.v_financial_year_verified f using (corp_code, bsns_year)
                               order by d.corp_code, d.bsns_year""").fetchall()
        status = dict(conn.execute("select corp_code, status from core.core_judgement_2026").fetchall())
        # 3장 근거: 칸 그림의 '배당 감소'(배당 총액)와 법 제2호(배당소득)가 2025년에 몇 곳에서 갈리나
        dec = conn.execute("""select (d.d_dart_won < p.d_dart_won) as d_down, (j.b_prev_won < j.b_2024_won) as b_down
                              from core.core_judgement_2026 j
                              join core.v_dividend_year_verified d on d.corp_code = j.corp_code and d.bsns_year = 2025
                              join core.v_dividend_year_verified p on p.corp_code = j.corp_code and p.bsns_year = 2024
                              join core.v_financial_year_verified f on f.corp_code = j.corp_code and f.bsns_year = 2025
                              where d.d_dart_won > 0 and f.ni_owner_won > 0 and p.d_dart_won > 0""").fetchall()
    by: dict = {}
    for code, year, d, ni in rows:
        by.setdefault(code, {})[year] = (float(d) if d is not None else None, float(ni) if ni is not None else None)
    ids = {code: i for i, code in enumerate(sorted(by))}
    grid = grid_3x3(rows)
    frames: dict = {}
    for code, years in by.items():
        for y, (d, ni) in years.items():
            prev = years.get(y - 1, (None, None))[0]
            if y <= LAST_FULL_YEAR and d and ni and ni > 0 and prev and prev > 0:
                frames.setdefault(y, []).append([ids[code], round(d / ni * 100, 1), round((d / prev - 1) * 100, 1), status.get(code)])
    both = [r for r in dec if r[1] is not None]
    return {"frames": {y: frames[y] for y in sorted(frames)}, "grid": grid,
            "decrease_check": {"year": 2025, "n": len(dec), "both": len(both), "differ": sum(1 for d, b in both if d != b)},
            "basis": "흑자이고 전년에도 배당한 회사만. 배당성향 = 이익배당금액 ÷ 지배주주 순이익, 증가율 = 전년 대비 이익배당금액. 색은 2026 판정"}


def grid_3x3(rows) -> dict[int, list[list[int]]]:
    """데이터 이야기 3장 칸 그림: 해마다 [증가율 10% 이상 / 0~10% / 감소] × [배당성향 25% 미만 / 25~40% / 40% 이상] 회사 수.
    표본은 산점도와 같다(흑자이고 전년에도 배당한 회사). 경계는 판정 엔진(core.judgement)과 같은 정수 비교라
    반올림한 %로 나눌 때 생기는 경계 오차가 없다: 100·D ≥ 40·NI, 100·D ≥ 25·NI, 10·D ≥ 11·D(전년), D ≥ D(전년)."""
    by: dict = {}
    for code, year, d, ni in rows:
        by.setdefault(code, {})[year] = (d, ni)
    out: dict = {}
    for years in by.values():
        for y, (d, ni) in years.items():
            prev = years.get(y - 1, (None, None))[0]
            if y > LAST_FULL_YEAR or not (d and ni and ni > 0 and prev and prev > 0):
                continue
            col = 2 if 100 * d >= 40 * ni else 1 if 100 * d >= 25 * ni else 0
            row = 0 if 10 * d >= 11 * prev else 1 if d >= prev else 2
            out.setdefault(y, [[0] * 3 for _ in range(3)])[row][col] += 1
    return {y: out[y] for y in sorted(out)}


MACRO_YEAR_COLS = ["payer_share", "dps_up_share", "yield_median", "base_rate", "ktb3y", "usdkrw", "gdp_growth",
                   "cpi_growth", "unemployment", "current_account_chg"]


def macro() -> dict | None:
    """경기와 배당: scripts.analyze_macro_dividend가 저장한 결과(core.core_macro_dividend_*)만 읽는다. 다시 계산하지 않는다."""
    m = macro_dividend.load()
    if m is None:
        return None
    y = m.year.reindex(columns=MACRO_YEAR_COLS)

    def num(v):
        return None if v != v else round(float(v), 4)  # NaN → None
    return {
        "year_cols": MACRO_YEAR_COLS,
        "years": [[int(yr), *[num(v) for v in row]] for yr, row in zip(y.index, y.to_numpy())],
        "corr": [[r.lag, r.kind, r.dividend, r.macro, num(r.spearman), num(r.p), num(r.n), num(r.rows)] for r in m.corr.itertuples()],
        # 산점도용: 항목별 연도 값. 시차 거시 값은 '항목@prev'·'항목@decision' (상관을 낸 그 값)
        "series": {c: {int(yr): num(v) for yr, v in m.year[c].items()} for c in m.year.columns},
        "lags": [list(x) for x in macro_dividend.LAGS],
        "dividend_names": macro_dividend.DIVIDEND_SHORT,
        "macro_names": {k: macro_dividend.macro_short(k) for k in m.corr["macro"].unique()},
        "built_at": m.built_at,
        "profit": json.loads(PROFIT_DIVIDEND.read_text(encoding="utf-8")) if PROFIT_DIVIDEND.exists() else None,
    }


def behavior() -> dict | None:
    """회사 행동 분석: 금리·환율 노출도(exposure)와 분리과세 이중차분(policy). 저장한 결과(core.core_behavior_*)만 읽는다."""
    b = behavior_data.load()
    if b is None:
        return None

    def num(v):
        return None if v is None else round(float(v), 4)
    fits: dict = {}
    for f in b.fits:
        fits.setdefault(f["analysis"], []).append({
            "name": f["name"], "role": f["role"], "coef": num(f["coef"]), "low": num(f["low"]), "high": num(f["high"]),
            "p_cluster": num(f["p_cluster"]), "p_perm": num(f["p_perm"]), "p_holm": num(f["p_holm"]),
            "n": f["n"], "n_firms": f["n_firms"], "n_treated": f["n_treated"]})
    series: dict = {}
    for r in b.series:  # [무리, 연도, 값, 아래, 위, 회사·연도 수]
        series.setdefault(r["analysis"], {}).setdefault(r["series"], []).append(
            [r["label"], r["year"], num(r["value"]), num(r["low"]), num(r["high"]), r["n"]])
    return {"fits": fits, "series": series, "built_at": b.built_at}


def holder() -> dict | None:
    h = holder_analysis.load()
    return {"table": h.table.to_dict("records"), "notes": h.notes, "near_pp": holder_analysis.NEAR_PP} if h else None


def capacity() -> dict:
    """재무 여력: 2025 잉여현금흐름 ÷ 2027 최소 필요 배당 (core.core_capacity_2025.cover_x)."""
    with db.connect() as conn:
        rows = conn.execute("select status, cover_x from core.core_capacity_2025").fetchall()
    shown = [float(x) for s, x in rows if x is not None]
    bins = [[name, sum(1 for x in shown if (lo is None or x >= lo) and (hi is None or x < hi))] for name, lo, hi in COVER_BINS]
    other: dict = {}
    for s, x in rows:
        if x is None:
            other[s] = other.get(s, 0) + 1
    return {"bins": bins, "n": len(shown), "median": round(statistics.median(shown), 2) if shown else None, "other": other}


ROOT = Path(__file__).resolve().parents[2]
PARTNER_DIR = ROOT / "data" / "partner" / "4조참치_20261030"
CTRL_LABEL = {"4조 대조군": "대조군"}
RESOLUTION = ROOT / "data" / "processed" / "analysis" / "verify_resolution.json"  # source/scripts/verify_resolution.py: 불일치 칸이 그 뒤 어떻게 처리됐는지  # 화면에서는 다른 팀 자료를 '대조군 데이터'로 부른다


def _csv_rows(pattern: Path) -> list[dict]:
    files = sorted(pattern.parent.glob(pattern.name))
    if not files:
        return []
    import csv
    with open(files[-1], encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def control() -> dict | None:
    """우리 638사 vs 대조군 비교 (source/scripts/analyze_panel.py가 partner.analysis_result에 저장한 값). 회사 이름은 넣지 않는다."""
    with db.connect() as conn:
        try:
            row = conn.execute("select payload, built_at from partner.analysis_result where key = 'panel'").fetchone()
        except Exception:  # partner 스키마가 없는 DB (대조군 자료를 넣지 않은 팀원 PC)
            conn.rollback()
            return None
    if not row:
        return None
    payload, built = row
    relabel = lambda r: [CTRL_LABEL.get(v, v) if isinstance(v, str) else v for v in r]  # noqa: E731
    for key in ("industry_2025", "car", "sample"):
        payload[key] = [relabel(r) for r in payload.get(key, [])]
    for h in payload.get("holder", []):
        h["group"] = CTRL_LABEL.get(h["group"], h["group"])
    payload["built_at"] = built.date().isoformat()
    return payload


def trust() -> dict:
    """데이터를 믿을 수 있게 한 일: 원문 대조·검토·수집 규모 (모두 DB에서 센다)."""
    with db.connect() as conn:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        source = dict(conn.execute("select result, count(*) from core.core_source_verify group by 1").fetchall())
        dart = dict(conn.execute("select result, count(*) from core.core_dart_verify group by 1").fetchall())
        review = dict(conn.execute("select status, count(*) from core.core_review_value group by 1").fetchall())
        return {
            "source_verify": source, "dart_verify": dart, "review": review,
            "policy_filings": one("select count(*) from raw.policy_filing"),
            "policy_documents": one("select count(*) from raw.policy_document"),
            "ocr_pages": one("select count(*) from raw.policy_page_ocr"),
            "price_rows": one("select count(*) from raw.krx_price_daily"),
            "event_cases": one("select count(*) from core.core_event_car where status = '산출'"),
            "companies": one("select count(*) from core.core_judgement_2026"),
            "holder": {"rows": one("select count(*) from raw.dart_major_holder where api_status = '000'"),
                       "companies": one("select count(distinct corp_code) from raw.dart_major_holder where api_status = '000'"),
                       "pct": one("select count(*) from core.core_major_holder where pct_common is not null")},
            "control": control_trust(conn),
            "totals": totals(conn),
            "resolution": json.loads(RESOLUTION.read_text(encoding="utf-8")) if RESOLUTION.exists() else None,
        }


def totals(conn) -> dict | None:
    """고배당기업 638곳 + 대조군을 합친 데이터 총계. 겹치는 회사는 대조군에 넣지 않았으므로 두 번 세지 않는다."""
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        ctrl = "join partner.company c using (corp_code) where c.grp = '대조군'"
        rows = {sch: [one(f"select count(*) from {sch}.{t}") for (t,) in conn.execute(
            "select table_name from information_schema.tables where table_schema = %s and table_type = 'BASE TABLE'", (sch,)).fetchall()]
            for sch in ("raw", "partner", "core")}
        return {
            # 수집한 원천 자료(raw: 공시·KRX·한국은행 원천, partner: 대조군 자료)의 모든 표 행 수. 분석 결과(core)는 따로 센다
            "source_rows": sum(rows["raw"]) + sum(rows["partner"]),
            "source_tables": len(rows["raw"]) + len(rows["partner"]),
            "result_rows": sum(rows["core"]),
            "result_tables": len(rows["core"]),
            "companies": one("select count(*) from core.core_judgement_2026") + one("select count(*) from partner.company where grp = '대조군'"),
            "fin_rows": one("select count(*) from core.v_financial_year_verified") + one(f"select count(*) from partner.financial_year f {ctrl}"),
            "price_rows": one("select count(*) from raw.krx_price_daily") + one("select count(*) from partner.krx_price_daily"),
            "price_companies": one("select count(*) from (select corp_code from raw.krx_price_daily union select corp_code from partner.krx_price_daily) u"),
            "holder_rows": one("select count(*) from raw.dart_major_holder where api_status = '000'")
            + one("select count(*) from partner.major_holder m join partner.company c using (corp_code) where c.grp = '대조군' and m.status = '값 있음'"),
        }
    except Exception:  # noqa: BLE001 대조군 표가 없으면 총계는 빼고 보여 준다
        conn.rollback()
        return None


def control_trust(conn) -> dict | None:
    """대조군 데이터의 규모와, 겹치는 회사로 우리 값과 맞춰 본 결과."""
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        out = {"companies": one("select count(*) from partner.company where grp = '대조군'"),
               "overlap": one("select count(*) from partner.company where grp = '겹침'"),
               "fin_rows": one("select count(*) from partner.financial_year f join partner.company c using (corp_code) where c.grp = '대조군'"),
               "price_companies": one("select count(distinct corp_code) from partner.krx_price_daily"),
               "price_rows": one("select count(*) from partner.krx_price_daily"),
               # 최대주주·특수관계인 지분: 원문에서 값을 읽은 줄만 ('원문에 없음' 등은 뺌)
               "holder_rows": one("select count(*) from partner.major_holder m join partner.company c using (corp_code) where c.grp = '대조군' and m.status = '값 있음'"),
               "holder_companies": one("select count(distinct m.corp_code) from partner.major_holder m join partner.company c using (corp_code) where c.grp = '대조군' and m.status = '값 있음'")}
    except Exception:
        conn.rollback()
        return None
    diffs = _csv_rows(PARTNER_DIR / "겹침_차이_원인_*.csv")
    out["overlap_diff"] = len(diffs)
    out["overlap_unexplained"] = sum(1 for r in diffs if (r.get("분류") or "").startswith(("미분류", "8.")))
    out["corrected"] = len(_csv_rows(ROOT / "data" / "processed" / "review" / "원문대조_*.csv"))
    return out


# --- 점검 (챗봇 add-on) ---

def parser() -> Parser:
    return Parser(name_index(), llm=get_llm())


YES_WORDS = re.compile(r"^(응|어|네|넵|예|ㅇㅇ|ㅇ|그래|맞아|맞아요|있음|있어|있어요|있습니다|yes|y)[.!~ ]*$", re.I)
NO_WORDS = re.compile(r"^(아니|아니요|아뇨|아니오|노|ㄴㄴ|ㄴ|없음|없어|없어요|없습니다|no|n)[.!~ ]*$", re.I)


def yes_no(answer: str) -> tuple[bool, bool]:
    """④ 다른 소득 있음/없음. '응'·'아니'처럼 짧은 대답도 읽는다."""
    a = answer.strip()
    yes = bool(YES_WORDS.match(a)) or ("있" in a and not NO_WORDS.match(a))
    no = bool(NO_WORDS.match(a)) or "없" in a
    return yes, no


def outside_note(excluded: list[tuple[str, list[str]]]) -> str:
    """① 보유 종목에서 뺀 조회 대상 밖 종목 안내. 이름이 비슷한 대상 기업이 있으면 고치는 길도 알려 준다."""
    names = ", ".join(f"'{n}'" for n, _ in excluded)
    last = excluded[-1][0]
    note = text.OUTSIDE_SKIPPED.format(names=names, josa=topic_josa(last))
    near = [s for _, ss in excluded for s in ss[:2]]
    if near:
        note += text.OUTSIDE_NEAR.format(near="·".join(dict.fromkeys(near)), eul=object_josa(near[-1]))
    return note


def parse(kind: str, answer: str, dividend_type: str | None = None) -> dict:
    """한 단계 답을 값으로 읽는다. 앱(app_pages/chatbot.py `_parse`)과 같은 규칙."""
    if kind == "holdings":
        skip = holdings_skip(answer)
        if skip:  # ① '없음'·'모름': 종목 없이 ②로 넘어간다
            return {"ok": True, "value": [], "skip": skip, "reply": text.HOLDINGS_SKIP_REPLY[skip], "error": "", "by": "규칙"}
        r = parser().holdings(answer, skip_outside=True)
        # 목록에 없어 뺀 종목이 있어도, 줄임말·옛 이름·오타 표에 있으면 빼기 전에 바꾼 이름으로 되묻는다
        if not r.ok or r.excluded:
            # 줄임말·옛 이름·오타 표(data/processed/chat/company_alias.csv)나 '삼성전자 10'처럼 '주'를 빠뜨린 숫자를
            # 바꾼 글로 되묻는다(바로 계산하지 않음)
            fixed, used = company_alias.replace(answer)
            fixed2 = shares_unit_added(fixed)
            if used or fixed2 != fixed:
                r2 = parser().holdings(fixed2, skip_outside=True)
                if r2.ok or (used and r2.code == "missing_shares"):
                    ask = company_alias.ask_text(used) if used else text.SHARES_UNIT_ASK
                    return {"ok": False, "value": None, "suggest_text": fixed2, "reply": ask,
                            "error": "", "by": "별칭 표" if used else "규칙"}
                if r2.code == "not_found" and not r.code:  # 숫자에 '주'를 붙이니 목록에 없는 회사가 드러남
                    r = r2
        value = [{"company": h.company, "shares": h.shares} for h in r.value] if r.ok else None
        out = {"ok": r.ok, "value": value, "error": r.error, "by": r.by, "code": r.code}
        if r.ok and r.excluded:
            out["excluded"] = [n for n, _ in r.excluded]
            out["note"] = outside_note(r.excluded)
        return out
    if kind == "other_dividend":
        # ③에 '종목 + 주식 수'를 적었으면 금액(100주 → 100원)으로 읽지 않는다.
        # 조회 대상 회사면 ①에 더할 종목으로 돌려주고, 아니면 배당 금액으로 다시 묻는다
        if mentions_shares(answer):
            r = parser().holdings(answer)
            if r.ok:
                return {"ok": False, "add_holdings": [{"company": h.company, "shares": h.shares} for h in r.value],
                        "error": "", "by": r.by}
            error = f"{r.error} {text.OTHER_HOLDING_OUTSIDE}" if r.code == "not_found" else r.error
            return {"ok": False, "value": None, "error": error, "by": r.by, "code": r.code}
        company_only = match_company(answer.strip(), name_index())[0]
        if company_only:
            return {"ok": False, "value": None, "prompt": text.OTHER_NEED_SHARES.format(company=company_only),
                    "error": "", "by": "규칙"}
    if kind == "other_dividend" and re.search(r"있", answer) and not re.search(r"\d|없", answer):
        # '있어'만 적으면 0원으로 읽지 않고 종류(→ 금액)를 묻는다
        return {"ok": False, "value": None, "prompt": text.OTHER_HAS_ASK, "error": "", "by": "규칙"}
    if kind == "yesno":
        yes, no = yes_no(answer)
        if yes and no:
            return {"ok": False, "value": None, "error": "있음 또는 없음 하나로 알려 주세요.", "by": "규칙"}
        if yes or no:
            return {"ok": True, "value": yes, "error": "", "by": "규칙"}
        if any(w in answer for w in ("모르", "몰라", "모름")):
            return {"ok": False, "value": None, "error": text.YESNO_UNKNOWN, "by": "규칙"}
        return {"ok": False, "value": None, "error": "있음 또는 없음으로 알려 주세요.", "by": "규칙"}
    if kind == "base" and text.NO_WAGE in answer:
        return {"ok": True, "value": 0, "error": "", "by": "규칙"}
    if kind == "other_dividend" and dividend_type is None:
        split = split_other_dividend(answer)
        if split:
            return {"ok": True, "value": split, "error": "", "by": "규칙"}
    r = parser().amount(answer)
    if not r.ok:
        return {"ok": False, "value": None, "error": r.error, "by": r.by}
    value = None if r.value == UNKNOWN else r.value
    if kind == "base" and isinstance(value, int) and value > 0:
        ask = base_suggest(answer, value)
        if ask:
            return {"ok": False, "value": None, **ask, "error": "", "by": "규칙"}
    if kind == "other_dividend":
        foreign = dividend_type == "foreign" or (dividend_type is None and any(w in answer for w in text.FOREIGN_WORDS))
        value = {"domestic": 0 if foreign else value, "foreign": value if foreign else 0}
    return {"ok": True, "value": value, "error": "", "by": r.by}


# 숫자 하나를 통째로 본다: '3,000주'의 '3'이나 '3,000만 원'의 '3'에 '주'를 붙이지 않게 뒤에 ',숫자'가 오면 건너뛴다
_BARE_SHARES = re.compile(r"(?<![\d,.A-Za-z])(\d(?:[\d,]*\d)?)(?!,?\d)\s*(?:개|株)?(?=\s*(?:[,·/;]|$|\s+[^\d\s주원만억천백]))")


def shares_unit_added(answer: str) -> str:
    """'삼성전자 10, SK하이닉스: 3' → '삼성전자 10주, SK하이닉스 3주'. '주'를 빠뜨린 숫자에 붙인다."""
    t = re.sub(r"\s*[:：=]\s*", " ", answer)
    return _BARE_SHARES.sub(lambda m: f"{m.group(1)}주", t)


def split_other_dividend(answer: str) -> dict | None:
    """'미국 주식 50만원 국내 30만원' → 해외·국내를 나눠 읽는다. 두 종류 낱말이 다 있을 때만."""
    words = [(m.start(), "foreign") for w in text.FOREIGN_WORDS for m in re.finditer(re.escape(w), answer)]
    words += [(m.start(), "domestic") for w in text.DOMESTIC_WORDS for m in re.finditer(re.escape(w), answer)]
    if len({k for _, k in words}) < 2:
        return None
    words.sort()
    out = {"domestic": 0, "foreign": 0}
    for i, (pos, k) in enumerate(words):
        end = words[i + 1][0] if i + 1 < len(words) else len(answer)
        part = answer[pos:end]
        if not re.search(r"\d|[십백천만억]", part):
            continue
        r = parse_amount(part)
        if not r.ok or r.value == UNKNOWN:
            return None
        out[k] += r.value
    return out


def base_suggest(answer: str, value: int) -> dict | None:
    """총급여에 '월급 300'·'연봉 5000'처럼 적으면 원 단위로 읽지 않고, 바꾼 글로 되묻는다."""
    has_unit = re.search(r"[원만억천]", answer)
    monthly = re.search(r"월급|월\s*\d|한\s*달|매달", answer)
    man = value if has_unit else value * 10_000 if value < 100_000 else value
    if monthly and man < 100_000_000:
        year = man * 12
        return {"suggest_text": f"{year // 10_000:,}만 원",
                "reply": text.BASE_MONTHLY_ASK.format(month=f"{man // 10_000:,}만 원", year=f"{year // 10_000:,}만 원")}
    if not has_unit and value < 100_000:
        return {"suggest_text": f"{value:,}만 원", "reply": text.BASE_MAN_ASK.format(raw=f"{value:,}", man=f"{value:,}만 원")}
    return None


def holdings_from_image(image_b64: str) -> dict:
    """① 보유 종목 캡처를 서버 안 AI로 읽어 입력창에 채울 글을 만든다. 값을 바로 쓰지 않고,
    고객이 확인·고쳐 보낸 글을 다시 parse('holdings')로 읽는다. 회사 이름은 조회 대상 목록으로 맞춘다."""
    if get_llm() is None:
        return {"ok": False, "error": text.IMAGE_OFF}
    items = read_holdings_image(image_b64)
    if items is None:
        return {"ok": False, "error": text.IMAGE_FAIL}
    items = [h for h in items if h["company"] and h["shares"] > 0]
    if not items:
        return {"ok": False, "error": text.IMAGE_EMPTY}
    rows, missing = [], []
    for h in items:
        company = match_company(h["company"], name_index())[0]
        alias = None if company else company_alias.lookup(h["company"])
        if alias:  # 'KB국민은행'·'롯데제과'처럼 표에 있는 이름은 대상 기업으로 바꿔 채운다(고객이 입력창에서 확인)
            company = alias.company
        if company is None:
            missing.append(h["company"])
        rows.append(f"{company or h['company']} {h['shares']:,}주")
    reply = text.IMAGE_READ + (" " + text.IMAGE_NOT_FOUND.format(names=", ".join(missing)) if missing else "")
    return {"ok": True, "text": ", ".join(rows), "count": len(rows), "missing": missing, "reply": reply}


def base_from_image(image_b64: str) -> dict:
    """⑤ 원천징수영수증 2쪽 사진에서 ㊼ 종합소득 과세표준만 읽어 입력창에 채울 글을 만든다.
    고객이 확인·고쳐 보낸 글을 다시 parse('base')로 읽는다."""
    if get_llm() is None:
        return {"ok": False, "error": text.IMAGE_OFF}
    r = read_receipt_image(image_b64)
    if r == NOT_PAGE2:
        return {"ok": False, "error": text.BASE_IMAGE_NOT_PAGE2}
    if r is None:
        return {"ok": False, "error": text.BASE_IMAGE_EMPTY}
    amount, gross = r["base"], r["gross"]
    shown = won(amount)
    out = {"ok": True, "text": shown, "amount": amount, "reply": text.BASE_IMAGE_READ.format(amount=shown)}
    if gross is not None:  # ㉑ 총급여: 결과의 ISA·IRP 구간을 미리 고르는 데만 쓴다(세액 계산에는 안 씀)
        out.update(gross=gross, bracket=isa_irp.wage_bracket(gross))
    return out


def no_target_reason(r: Checkup, holdings_answer: str | None, outside: list[str] = ()) -> str | None:
    """특례 대상 배당이 하나도 없으면(판정 보류로 나눠 볼 금액도 없으면) 그 이유. 있으면 None."""
    if r.special_total or any(s.held for s in r.stocks):
        return None
    if not r.stocks and outside:
        return text.NO_TARGET_REASON["목록 밖"]
    if not r.stocks:
        return text.NO_TARGET_REASON[holdings_answer or "없음"]
    return text.NO_TARGET_REASON["미해당"]


def headline(r: Checkup, no_target: str | None = None, has_other_income: bool = False, outside: list[str] = ()) -> str:
    """결과 맨 위 한 줄 요약. 앱(app_pages/chatbot.py `_headline`)과 같은 문구에, 웹은 '대상 없음'과 바뀐 말을 쓴다.
    비교하지 않은 이유: 다른 소득이 있으면 모르는 칸이 있어도 그것이 결정적 이유라 그쪽을 말한다."""
    listed = sum(1 for s in r.stocks if s.company.kind_2025)
    n = len(r.stocks) + len(outside)  # ①에서 목록에 없어 뺀 종목도 보유 종목으로 센다
    line = text.HEADLINE_STOCKS.format(n=n, listed=listed) if n else ""
    if outside:
        names = ", ".join(f"'{x}'" for x in outside)
        line += " " + text.HEADLINE_OUTSIDE.format(names=names, josa=topic_josa(outside[-1]))
    t = r.tax
    if no_target:
        return f"{line} {text.NO_TARGET} {no_target}".strip()
    if t.status == COMPARED:
        return f"{line} {text.HEADLINE_COMPARED.format(diff=won(abs(t.difference)))}"
    if t.status == NO_DIFFERENCE:
        return f"{line} {text.HEADLINE_NO_DIFFERENCE}"
    reason = text.HEADLINE_REASON_UNKNOWN if r.unknown_fields and not has_other_income else text.HEADLINE_REASON_OTHER_INCOME
    return f"{line} {text.HEADLINE_SPECIAL_ONLY.format(special=won(r.special_total), tax=won(t.separate_tax), reason=reason)}"


def checkup(holdings: dict[str, int], interest, domestic, foreign, base, has_other_income: bool,
            holdings_answer: str | None = None, outside: list[str] = ()) -> dict:
    # 다른 소득이 있으면 ⑤를 묻지 않았고 세액 비교도 하지 않는다 → '모르는 항목'으로 세지 않도록 0
    if has_other_income and base is None:
        base = 0
    r = run_checkup(holdings, interest, domestic, foreign, base, has_other_income, {**companies(), **prefs()[0]})
    t = r.tax
    no_target = no_target_reason(r, holdings_answer, outside)
    rows = [[text.SPECIAL_LABEL, r.special_total],
            [f"{text.SPECIAL_TAX_LABEL} ({text.SPECIAL_TAX_TAG})", t.separate_tax]]
    if no_target:
        rows = [[text.SPECIAL_LABEL, 0]]
    elif t.status == COMPARED:
        rows += [[text.ROW_BEFORE, t.t0.tax], [text.ROW_AFTER, t.t1.tax + t.separate_tax]]
    return {
        "headline": headline(r, no_target, has_other_income, outside),
        "no_target": no_target,
        "tax": {"status": t.status, "rows": rows, "difference": None if no_target else t.difference,
                "direction": None if no_target else t.direction,
                "separate_tax": t.separate_tax, "reasons": t.reasons, "notice": t.notice},
        "stocks": [{**stock_view(s), "shares": s.shares, "special": s.special, "held": s.held} for s in r.stocks],
        "special_total": r.special_total,
        "unknown_fields": r.unknown_fields,
        "notes": ([text.HOLDING_ASSUMPTION] if r.stocks else []) + [f"{t.notice} {text.TAX_NOTE}"],  # 보유 종목이 없으면 수량 가정은 해당 없음
    }


def evidence() -> list[dict]:
    """[근거 보기]: 조세특례제한법 제104조의27 ①~③ 원문 그대로."""
    return [{"label": p.label, "text": p.text, "url": p.url} for p in law().passages
            if "제104조의27" in p.label and p.label.endswith(("①", "②", "③"))]


def separate(amount: int) -> dict:
    """분리과세 세액과 구간별 계산 (세율표 core.tax_rates.SEPARATE, 계산 core.tax.separate_tax)."""
    rows = sorted(tax_rates.SEPARATE, key=lambda b: b.lower_bound)
    steps = []
    for i, b in enumerate(rows):
        upper = rows[i + 1].lower_bound if i + 1 < len(rows) else None
        part = max(0, min(amount, upper if upper is not None else amount) - b.lower_bound)
        steps.append({"from": b.lower_bound, "to": upper, "rate_pct": b.rate_pct, "part": part,
                      "tax": part * b.rate_pct // 100})
    total = tax.separate_tax(amount)
    return {"amount": amount, "tax": total, "effective_pct": round(total / amount * 100, 2) if amount else 0,
            "steps": steps, "source": rows[0].source, "notice": tax.NOTICE}


def race_example(pick: int) -> dict:
    """칼럼 '달리기 시합'용 실제 사례 하나: 배당을 늘린다는 공시 뒤 60거래일 동안 그 회사 주가와 시장지수의 누적 수익률.
    회사 이름은 보내지 않는다. 기준은 공시 전날 종가, 주가만(배당 제외), 초과수익률 = 회사 누적 − 시장 누적."""
    with db.connect() as conn:
        events = conn.execute(
            "select rcept_no, corp_code, event_date, market, car from core.core_event_car "
            "where status = '산출' and kind = '주당배당금 증가' and basis = '공시일' and window_days = 60 "
            "and event_date < '2026-01-01' order by rcept_no").fetchall()
        rcept, code, day0, market, car = events[pick % len(events)]
        stock = conn.execute("select trade_date, close_adj::float from core.v_price_daily where corp_code = %s "
                             "and trade_date >= %s - interval '15 days' order by trade_date limit 90", (code, day0)).fetchall()
        index = dict(conn.execute("select trade_date, close::float from core.v_index_daily where market = %s "
                                  "and trade_date >= %s - interval '15 days' order by trade_date limit 90", (market, day0)).fetchall())
    before = [r for r in stock if r[0] < day0]
    after = [r for r in stock if r[0] >= day0 and r[0] in index][:61]
    base_d, base_s = before[-1]
    base_m = index[base_d]
    path = [[i, round((s / base_s - 1) * 100, 2), round((index[d] / base_m - 1) * 100, 2)] for i, (d, s) in enumerate(after)]
    return {"n_events": len(events), "pick": pick % len(events), "year": day0.year, "market": market,
            "path": path, "car_pct": round(float(car) * 100, 2) if car is not None else None}


def spread_example() -> dict:
    """칼럼 '평균과 가운데 값'용: 배당을 늘린다는 공시 뒤 60거래일 초과수익률(배당 포함, 자본 변동 겹침 제외) 모든 사례.
    데이터 이야기 6장 주 조건과 같은 표본이다(core.core_event_curve와 같은 387건). 회사 이름은 보내지 않는다."""
    with db.connect() as conn:
        rows = conn.execute(
            "select car_total from core.core_event_car where status = '산출' and kind = '주당배당금 증가' "
            "and basis = '공시일' and window_days = 60 and event_date < '2026-01-01' "
            "and car_total is not null and not coalesce(overlap_capital, false)").fetchall()
    return {"values": sorted(round(float(r[0]) * 100, 2) for r in rows),
            "basis": "배당을 늘린다는 공시 · 공시일 기준 60거래일 · 배당 포함 · 자본 변동 겹침 제외"}


def persona(pid: str) -> dict | None:
    """로그인했다고 가정한 페르소나의 개인 페이지. 금융소득 합계·점검 결과·ISA·IRP 판정은 여기서 코드로 계산한다."""
    p = personas.PERSONAS.get(pid)
    if p is None:
        return None
    c = p["checkup"]
    fin = p["financial"]
    totals = {k: sum(r[2] for r in fin if r[3] == k) for k in ("interest", "stock", "fund")}
    result = checkup(c["holdings"], c["interest"], c["domestic"], c["foreign"], c["base"], c["has_other_income"],
                     c.get("holdings_answer"))
    i = p["isa_irp"]
    prof = isa_irp.profile(i["kind"], i["join_year"], i["last_year_income"], i["this_year_income"], i["taxed_years"],
                           i["isa_profit"], i["irp"], i.get("pension_saving", 0), i.get("what_if"))
    return {**{k: v for k, v in p.items() if k not in ("checkup", "isa_irp")},
            "financial_total": sum(totals.values()), "financial_totals": totals,
            "withheld_after": sum(totals.values()) * (1000 - isa_irp.NORMAL_ACCOUNT_PERMIL) // 1000,
            "checkup": result, "isa_irp": prof, "source": personas.SOURCE}
