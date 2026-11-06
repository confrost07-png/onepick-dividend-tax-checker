"""과거 사례 리포트(데이터 분석 화면): 공시 뒤 주가 반응 이벤트 스터디.

- 이벤트: ① 배당 결정 공시(주당배당금 증가 / 유지·감소) ② KIND 고배당기업 공시 ③ 증자·감자·분할·병합 공시(방식별)
- 기준일(배당 결정만 셋): 공시일 / 주주총회 결의일(결산배당 액수가 확정되는 날) / 배당락일(기준일의 직전 거래일,
  기준일이 휴장일이면 그 전 마지막 거래일)
- 수익률: 주가만(수정주가는 현금배당 배당락을 보정하지 않음) / 배당 포함(창 안 배당락일에 주당배당금 ÷ 전일 종가를 더함)
- 표본: 전체 / 자본 변동 겹침 제외(관측 창 안에 같은 회사의 증자·감자·분할·병합 공시가 있으면 뺌)
- 측정: 공시 후 20·60거래일 누적 초과수익률 CAR = Σ(종목 수익률 − 시장지수 수익률), 수정주가 기준
- 이벤트일: 장 마감 후 공시는 다음 거래일. 관측 기간이 모자라거나 같은 회사의 이벤트가 겹치면 제외
- 표시: 공시 종류별 중앙값·25~75% 범위·사례 수. 사례 10건 미만은 표시하지 않음

[팀 해석] 누적 구간은 이벤트일(0)부터 N거래일 뒤까지(0~N)로 한다.
화면에는 집계 통계만 보여 주고 개별 회사의 반응은 보여 주지 않는다.
"""
import bisect
import re
from dataclasses import dataclass
from datetime import date, datetime, time

import pandas as pd

MARKET_CLOSE = time(15, 30)
MIN_CASES = 10
WINDOWS = (20, 60)


BASIS_DISCLOSED, BASIS_AGM, BASIS_EX = "공시일", "주주총회 결의일", "배당락일"
RET_PRICE, RET_TOTAL = "주가만", "배당 포함"
SAMPLE_ALL, SAMPLE_NO_CAPITAL = "전체", "자본 변동 겹침 제외"


@dataclass(frozen=True)
class Event:
    corp_code: str
    kind: str  # 공시 종류
    disclosed_at: datetime  # 이벤트일(기준일 종류에 따라 공시일·주총일·배당락일)
    rcept_no: str = ""
    basis: str = BASIS_DISCLOSED
    dps: float | None = None  # 배당 포함 수익률에 더할 주당배당금 (원)
    record_date: date | None = None  # 그 배당의 기준일 (배당락일을 찾는 데 씀)


def event_day_index(trading_days: list[date], disclosed_at: datetime) -> int | None:
    """이벤트일(거래일 목록의 위치). 장 마감 후·휴장일 공시는 다음 거래일로 민다."""
    d = disclosed_at.date()
    i = bisect.bisect_left(trading_days, d)
    if i < len(trading_days) and trading_days[i] == d and disclosed_at.time() >= MARKET_CLOSE:
        i += 1
    return i if i < len(trading_days) else None


def ex_dividend_index(trading_days: list[date], record: date) -> int | None:
    """배당락일 위치. 기준일이 거래일이면 그 직전 거래일, 휴장일(12월 31일 등)이면 그 전 마지막 거래일."""
    i = bisect.bisect_left(trading_days, record)  # 기준일이 거래일이면 그 자리, 휴장일이면 다음 거래일 자리
    return i - 1 if i >= 1 else None


def car(stock_prices: pd.Series, market_prices: pd.Series, event_idx: int, window: int) -> float | None:
    """이벤트일(0)부터 window 거래일 뒤까지의 누적 초과수익률(소수, 0.01 = 1%p).

    가격은 같은 거래일 인덱스를 가진 수정주가·지수. 관측 기간이 모자라면 None.
    """
    if event_idx < 1 or event_idx + window >= len(stock_prices):
        return None
    s = stock_prices.iloc[event_idx - 1: event_idx + window + 1]
    m = market_prices.iloc[event_idx - 1: event_idx + window + 1]
    if s.isna().any() or m.isna().any():
        return None
    excess = s.pct_change().iloc[1:].to_numpy() - m.pct_change().iloc[1:].to_numpy()
    return float(excess.sum())


def drop_overlapping(events: list[Event], trading_days: list[date], window: int) -> list[Event]:
    """같은 회사에서 앞 이벤트의 관측 기간 안에 들어온 이벤트를 뺀다."""
    kept: list[Event] = []
    last_end: dict[str, int] = {}
    for e in sorted(events, key=lambda e: (e.corp_code, e.disclosed_at)):
        idx = event_day_index(trading_days, e.disclosed_at)
        if idx is None:
            continue
        if e.corp_code in last_end and idx <= last_end[e.corp_code]:
            continue
        kept.append(e)
        last_end[e.corp_code] = idx + window
    return kept


def collect_cars(events: list[Event], prices: pd.DataFrame, market: pd.Series, window: int) -> dict[str, list[float]]:
    """공시 종류별 CAR 목록. prices는 거래일 인덱스 × 회사(corp_code) 열의 수정주가 표."""
    trading_days = [d.date() if isinstance(d, (datetime, pd.Timestamp)) else d for d in prices.index]
    out: dict[str, list[float]] = {}
    for e in drop_overlapping(events, trading_days, window):
        if e.corp_code not in prices.columns:
            continue
        idx = event_day_index(trading_days, e.disclosed_at)
        value = car(prices[e.corp_code], market, idx, window) if idx is not None else None
        if value is not None:
            out.setdefault(e.kind, []).append(value)
    return out


def summarize(cars_by_kind: dict[str, list[float]], window: int, min_cases: int = MIN_CASES) -> pd.DataFrame:
    """공시 종류별 사례 수·중앙값·25~75% 범위(%p). 사례가 min_cases 미만이면 통계를 비운다."""
    rows = []
    for kind, values in cars_by_kind.items():
        n = len(values)
        row = {"공시 종류": kind, "관측 기간": window, "사례 수": n, "중앙값": None, "25%": None, "75%": None, "표시": n >= min_cases}
        if n >= min_cases:
            s = pd.Series(values) * 100
            row.update({"중앙값": round(s.median(), 2), "25%": round(s.quantile(0.25), 2), "75%": round(s.quantile(0.75), 2)})
        rows.append(row)
    return pd.DataFrame(rows, columns=["공시 종류", "관측 기간", "사례 수", "중앙값", "25%", "75%", "표시"])


# --- 실제 데이터(onepick DB)로 돌리기: 이벤트 만들기와 이벤트 1건씩 판정 ---
# [팀 해석] 공시 시각이 없어 공시일을 이벤트일(0)로 둔다. 장 마감 뒤 공시여도 0~N 구간에 다음 날 반응이 들어간다.
# [팀 해석] 주가 사용 등급(source/core/price_quality.py)이 '제외'인 날이 창 안에 있으면 그 이벤트는 뺀다. '주의'는 남기고 센다.

DPS_UP, DPS_FLAT_DOWN, KIND_HIGH_DIV = "주당배당금 증가", "주당배당금 유지·감소", "고배당기업 공시(KIND)"
DPS_TYPES = {"현금배당", "현금ㆍ현물배당"}
COMPUTED, EXCLUDED = "산출", "제외"


def _event_time(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(0))


def _date(v) -> date | None:
    try:
        return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def dps_events(decisions: list[dict], basis: str = BASIS_DISCLOSED, trading_days: list[date] | None = None) -> list[Event]:
    """결산배당 결정 공시의 보통주 주당배당금을 직전 사업연도 결산배당과 비교한 이벤트.

    주당배당금·기준일·주총일은 정정까지 반영한 마지막 공시 값. 이벤트일은 basis에 따라
    공시일(시장이 처음 안 날 = 첫 공시일) / 주주총회 결의일(주총 예정일) / 배당락일(trading_days 필요).
    직전 연도 결산배당 공시가 없거나 그 기준일 값이 없으면 뺀다.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in decisions:
        if (r.get("div_kind") != "결산배당" or r.get("div_type") not in DPS_TYPES or r.get("attributed_year") is None
                or r.get("dps_common_won") is None or not r.get("disclosed_on")):
            continue
        groups.setdefault((r["corp_code"], r["attributed_year"]), []).append(r)
    first = {k: min(v, key=lambda r: (r["disclosed_on"], r["rcept_no"])) for k, v in groups.items()}
    last = {k: max(v, key=lambda r: (r["disclosed_on"], r["rcept_no"])) for k, v in groups.items()}
    events = []
    for (code, year), r in last.items():
        prev = last.get((code, year - 1))
        if prev is None:
            continue
        kind = DPS_UP if r["dps_common_won"] > prev["dps_common_won"] else DPS_FLAT_DOWN
        f = first[(code, year)]
        record = _date(r.get("record_date"))
        if basis == BASIS_DISCLOSED:
            day = _date(f["disclosed_on"])
        elif basis == BASIS_AGM:
            day = _date(r.get("agm_date"))
        else:
            ex = ex_dividend_index(trading_days, record) if record and trading_days else None
            day = trading_days[ex] if ex is not None else None
        if day is None:
            continue
        events.append(Event(code, kind, datetime.combine(day, time(0)), f["rcept_no"], basis,
                            float(r["dps_common_won"]), record))
    return sorted(events, key=lambda e: (e.disclosed_at, e.corp_code))


def kind_events(kind_rows: list[dict]) -> list[Event]:
    """KIND 고배당기업 공시(최종 공시일)."""
    return sorted((Event(r["corp_code"], KIND_HIGH_DIV, _event_time(r["final_disclosed_on"]), r["final_rcept_no"] or "")
                   for r in kind_rows if r.get("corp_code") and r.get("final_disclosed_on")),
                  key=lambda e: (e.disclosed_at, e.corp_code))


CAPITAL_KINDS = {"유상증자": "유상증자", "무상증자": "무상증자", "감자": "감자", "주식분할": "주식분할", "주식병합": "주식병합"}


def capital_kind(kind: str, method: str | None) -> str:
    """증자·감자 공시 → 화면의 공시 종류 (방식별로 반응이 달라 나눈다)."""
    m = (method or "").replace(" ", "")
    if kind == "유상증자":
        if "제3자" in m:
            return "유상증자(제3자배정)"
        if "주주배정" in m or "주주우선" in m:
            return "유상증자(주주배정)"
        if "일반공모" in m:
            return "유상증자(일반공모)"
        return "유상증자(그 밖)"
    if kind == "감자":
        return "감자(자기주식 소각)" if "자기주식" in m else "감자(그 밖)"
    return kind


def capital_events(capital_rows: list[dict], split_rows: list[dict]) -> list[Event]:
    """증자·감자(최종본, 이벤트일은 정정 묶음의 첫 공시일)와 액면분할·병합 공시."""
    first = {}
    for r in capital_rows:  # '앞선 판'은 check_result에 최종본 접수번호가 적혀 있음
        if r.get("version") in ("앞선 판", "첨부만 정정"):
            for final in re.findall(r"\d{14}", r.get("check_result") or ""):
                d = _date(r["rcept_dt"])
                if d and (final not in first or d < first[final]):
                    first[final] = d
    out = []
    for r in capital_rows:
        if r.get("version") not in ("API 최종본", "원문 최종본") or not r.get("corp_code"):
            continue
        d = min(x for x in (_date(r["rcept_dt"]), first.get(r["rcept_no"])) if x)
        out.append(Event(r["corp_code"], capital_kind(r["kind"], r.get("method")), datetime.combine(d, time(0)), r["rcept_no"]))
    for r in split_rows:
        if r.get("corp_code") and r.get("rcept_dt"):
            out.append(Event(r["corp_code"], r["kind"], datetime.combine(_date(r["rcept_dt"]), time(0)), r["rcept_no"]))
    return sorted(out, key=lambda e: (e.disclosed_at, e.corp_code))


def _dividend_add(e: Event, days: list[date], prices: pd.Series, idx: int, window: int) -> list[float]:
    """창(idx-1 ~ idx+window)의 날짜별 수익률에 더할 배당 몫. 배당락일이 창 밖이거나 배당 정보가 없으면 0."""
    add = [0.0] * (window + 1)
    if not e.dps or not e.record_date:
        return add
    ex = ex_dividend_index(days, e.record_date)
    if ex is None or not idx <= ex <= idx + window:
        return add
    prev = prices.iloc[ex - 1]
    if prev and not pd.isna(prev):
        add[ex - idx] = e.dps / float(prev)
    return add


def evaluate_events(events: list[Event], prices: pd.DataFrame, grades: pd.DataFrame, markets: pd.DataFrame,
                    index_grades: pd.DataFrame, market_of: dict[str, str], window: int,
                    capital_dates: dict[str, list[tuple[date, str]]] | None = None) -> list[dict]:
    """이벤트 1건마다 CAR(주가만·배당 포함) 또는 제외 사유, 그리고 자본 변동 겹침 여부.

    prices·grades: 거래일 × corp_code (가격 / '사용 가능'·'주의'·'제외'), markets·index_grades: 거래일 × 시장.
    빈 날은 prices가 비어 있고 grades는 '제외'다. capital_dates: 회사별 [(증자·감자·분할·병합 공시일, 접수번호)].
    증자·감자 이벤트 자신은 겹침으로 세지 않는다.
    """
    days = [d.date() if isinstance(d, (datetime, pd.Timestamp)) else d for d in prices.index]
    kept = set()
    for kind, basis in {(e.kind, e.basis) for e in events}:  # 겹침은 같은 공시 종류·기준일 안에서만 본다
        kept.update(drop_overlapping([e for e in events if e.kind == kind and e.basis == basis], days, window))
    rows = []
    for e in events:
        idx = event_day_index(days, e.disclosed_at)
        row = {"corp_code": e.corp_code, "rcept_no": e.rcept_no, "kind": e.kind, "basis": e.basis,
               "disclosed_on": e.disclosed_at.date(), "event_date": days[idx] if idx is not None else None,
               "window_days": window, "market": market_of.get(e.corp_code), "car": None, "car_total": None,
               "dps": e.dps, "record_date": e.record_date, "overlap_capital": False,
               "status": EXCLUDED, "reason": None, "caution": False}
        if e not in kept and idx is not None:
            row["reason"] = "같은 회사 앞 공시의 관측 기간과 겹침"
        elif e.corp_code not in prices.columns:
            row["reason"] = "주가 미수집"
        elif row["market"] not in markets.columns:
            row["reason"] = "시장 구분 없음"
        elif idx is None or idx < 1 or idx + window >= len(days):
            row["reason"] = "관측 기간 부족"
        else:
            span = slice(idx - 1, idx + window + 1)
            s, g = prices[e.corp_code].iloc[span], grades[e.corp_code].iloc[span]
            ig = index_grades[row["market"]].iloc[span]
            if s.isna().any():
                row["reason"] = "창 안에 빈칸(상장 전·거래정지·상장폐지)"
            elif (g == "제외").any():
                row["reason"] = "창 안에 이상 가격(상한 초과 등락·멈춘 가격)"
            else:
                row["car"] = car(s.reset_index(drop=True), markets[row["market"]].iloc[span].reset_index(drop=True), 1, window)
                row["car_total"] = row["car"] + sum(_dividend_add(e, days, prices[e.corp_code], idx, window))
                row["status"] = COMPUTED
                row["caution"] = bool((g == "주의").any() or (ig == "주의").any())
                lo, hi = days[idx - 1], days[idx + window]
                row["overlap_capital"] = any(lo <= d <= hi and rc != e.rcept_no for d, rc in (capital_dates or {}).get(e.corp_code, []))
        rows.append(row)
    return rows


VERIFIED, UNVERIFIED = "2025년까지", "2026년 (지수 미검증)"


def period_of(disclosed_on: date) -> str:
    """시장지수를 다른 출처와 대조하지 못한 기간(source/core/price_quality.INDEX_UNVERIFIED_FROM)의 공시는 따로 묶는다."""
    from core.price_quality import INDEX_UNVERIFIED_FROM
    return UNVERIFIED if disclosed_on >= date.fromisoformat(INDEX_UNVERIFIED_FROM) else VERIFIED


def _variants(grp: pd.DataFrame):
    """(수익률, 표본, 값 열, 그 표본 행). 배당 포함은 배당 정보가 있는 공시 종류에만 만든다."""
    has_dps = "dps" in grp and grp["dps"].notna().any()
    overlap = grp["overlap_capital"] if "overlap_capital" in grp else pd.Series(False, index=grp.index)
    for ret, col in ((RET_PRICE, "car"), (RET_TOTAL, "car_total")):
        if ret == RET_TOTAL and not has_dps:
            continue
        yield ret, SAMPLE_ALL, col, grp
        if overlap.any():
            yield ret, SAMPLE_NO_CAPITAL, col, grp[~overlap.astype(bool)]


def summarize_results(rows: list[dict], min_cases: int = MIN_CASES) -> pd.DataFrame:
    """evaluate_events 결과 → 공시 종류×기간×기준일×수익률×표본×관측 기간별 summarize 표에 제외·주의 건수를 붙인다."""
    df = pd.DataFrame(rows)
    df["기간"] = df["disclosed_on"].map(period_of)
    if "basis" not in df:
        df["basis"] = BASIS_DISCLOSED
    out = []
    for (kind, period, basis, window), grp in df.groupby(["kind", "기간", "basis", "window_days"]):
        for ret, sample, col, sub in _variants(grp):
            ok = sub[sub["status"] == COMPUTED]
            table = summarize({kind: list(ok[col])}, window, min_cases)
            table.insert(1, "기간", period)
            table["기준일"], table["수익률"], table["표본"] = basis, ret, sample
            table["주의 포함"] = int(ok["caution"].sum())
            table["제외"] = int((grp["status"] == EXCLUDED).sum()) + (len(grp) - len(sub))
            out.append(table)
    return pd.concat(out, ignore_index=True)


def curve_rows(rows: list[dict], prices: pd.DataFrame, markets: pd.DataFrame, window: int,
               min_cases: int = MIN_CASES) -> list[dict]:
    """산출된 이벤트의 날짜별 누적 초과수익률(0~window일) → 종류×기간×기준일×수익률×표본×날짜별 중앙값·25~75%(%p).

    마지막 날 값은 evaluate_events의 CAR(주가만)·car_total(배당 포함)과 같다. 사례가 min_cases 미만이면 통계를 비운다.
    """
    days = [d.date() if isinstance(d, (datetime, pd.Timestamp)) else d for d in prices.index]
    pos = {d: i for i, d in enumerate(days)}
    paths: dict[tuple, list] = {}
    for r in rows:
        if r["status"] != COMPUTED or r["window_days"] != window:
            continue
        i = pos[r["event_date"]]
        s = prices[r["corp_code"]].iloc[i - 1: i + window + 1].to_numpy()
        m = markets[r["market"]].iloc[i - 1: i + window + 1].to_numpy()
        price_path = (s[1:] / s[:-1] - m[1:] / m[:-1]).cumsum()
        e = Event(r["corp_code"], r["kind"], datetime.combine(r["event_date"], time(0)), r["rcept_no"],
                  r.get("basis", BASIS_DISCLOSED), r.get("dps"), r.get("record_date"))
        total_path = price_path + pd.Series(_dividend_add(e, days, prices[r["corp_code"]], i, window)).cumsum().to_numpy()
        basis, period = r.get("basis", BASIS_DISCLOSED), period_of(r["disclosed_on"])
        samples = [SAMPLE_ALL] + ([] if r.get("overlap_capital") else [SAMPLE_NO_CAPITAL])
        for ret, path in ((RET_PRICE, price_path), (RET_TOTAL, total_path)):
            if ret == RET_TOTAL and r.get("dps") is None:
                continue
            for sample in samples:
                paths.setdefault((r["kind"], period, basis, ret, sample), []).append(path)
    has_overlap = {(r["kind"], r.get("basis", BASIS_DISCLOSED)) for r in rows if r.get("overlap_capital")}
    out = []
    for (kind, period, basis, ret, sample), group in paths.items():
        if sample == SAMPLE_NO_CAPITAL and (kind, basis) not in has_overlap:
            continue  # 겹친 사례가 없으면 '전체'와 같아 따로 두지 않음
        table = pd.DataFrame(group) * 100
        shown = len(group) >= min_cases
        for day in range(window + 1):
            col = table[day]
            out.append({"kind": kind, "period": period, "basis": basis, "return_type": ret, "sample": sample,
                        "window_days": window, "day": day, "n_cases": len(group),
                        "median_pct": round(col.median(), 2) if shown else None,
                        "p25_pct": round(col.quantile(0.25), 2) if shown else None,
                        "p75_pct": round(col.quantile(0.75), 2) if shown else None})
    return out
