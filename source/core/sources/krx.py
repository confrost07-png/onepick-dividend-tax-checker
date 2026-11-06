"""KRX 수정주가·시장지수(pykrx) 수집과 결측 구분.

화면(KRX 정보데이터시스템)에는 보이는데 코드에서 비는 흔한 원인과 대응:
- 종목코드 앞자리 0이 빠짐(5930) 또는 'A005930'·'005930.KS' 형식 → normalize_ticker로 6자리
- 휴장일 → 결측이 아님. 거래일 달력을 시장지수 날짜로 만들어 휴장일은 아예 행을 만들지 않음
- 거래정지일 → pykrx는 시가·고가·저가 0, 거래량 0, 종가는 전날 값으로 줌. 정상 가격으로 쓰면 수익률이 0으로 왜곡되므로 비워 둠
- 상장 전·마지막 거래 이후 → '값 없음'과 나눠 표시
- KRX 응답 자체가 비는 경우 → 지수까지 비면 '조회 실패'(데이터 없음과 구분)

비워 둔 날이 관측 기간에 들어간 이벤트는 core.event_study.car가 None을 돌려 사례에서 빠진다(값을 채우지 않음).
자료는 한국거래소(KRX) 시세를 pykrx로 받는다. 실서비스로 바꿀 때 시세 이용계약은 PRD 6.1을 따른다.
"""
import re
from typing import Protocol

import pandas as pd

from core.sources.base import API_ERROR, NO_DATA, OK, Fetched, Source, scrub

MARKET_INDEX = {"KOSPI": "1001", "KOSDAQ": "2001"}
MARKET_NAMES = {"유가": "KOSPI", "유가증권": "KOSPI", "코스피": "KOSPI", "KOSPI": "KOSPI",
                "코스닥": "KOSDAQ", "KOSDAQ": "KOSDAQ"}  # KIND·DART 시장 표기 → pykrx 시장 이름

NORMAL = "정상"
BEFORE_LISTING = "상장 전"
AFTER_LAST_TRADE = "마지막 거래 이후"
HALTED = "거래정지"
MISSING = "값 없음"
DAY_STATUSES = [NORMAL, HALTED, MISSING, BEFORE_LISTING, AFTER_LAST_TRADE]


class PriceProvider(Protocol):
    name: str

    def prices(self, ticker: str, start: str, end: str) -> pd.DataFrame: ...

    def index(self, code: str, start: str, end: str) -> pd.DataFrame: ...

    def tickers(self, date: str, market: str) -> dict[str, str]: ...


class PykrxProvider:
    """pykrx로 수정주가(adjusted=True)와 지수 일별 시세를 받는다. 열: 시가·고가·저가·종가·거래량."""

    name = "pykrx"

    def prices(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        from pykrx import stock

        return stock.get_market_ohlcv(start, end, ticker, adjusted=True)

    def index(self, code: str, start: str, end: str) -> pd.DataFrame:
        from pykrx import stock

        return stock.get_index_ohlcv(start, end, code)

    def tickers(self, date: str, market: str) -> dict[str, str]:
        """그날 상장 종목 {종목코드: 종목 약칭}. market: KOSPI·KOSDAQ."""
        from pykrx import stock

        return {t: stock.get_market_ticker_name(t) for t in stock.get_market_ticker_list(date, market=market)}


def normalize_ticker(code) -> str:
    """5930 · 'A005930' · '005930.KS' → '005930'."""
    digits = re.sub(r"\D", "", str(code).split(".")[0])
    if not digits or len(digits) > 6:
        raise ValueError(f"종목코드로 볼 수 없음: {code!r}")
    return digits.zfill(6)


def _ymd(value) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def fetch_ohlcv(ticker, start, end, provider: PriceProvider | None = None,
                fallback: PriceProvider | None = None) -> Fetched:
    """한 종목의 일별 시세. 비거나 실패하면 fallback 공급자로 한 번 더 받는다."""
    code = normalize_ticker(ticker)
    attempts: list[str] = []
    status = NO_DATA
    for p in [x for x in (provider or PykrxProvider(), fallback) if x is not None]:
        try:
            df = p.prices(code, _ymd(start), _ymd(end))
        except Exception as error:  # noqa: BLE001 - 공급자마다 예외가 다르다
            attempts.append(f"{p.name} {code}: 조회 실패 {scrub(error)}")
            status = API_ERROR
            continue
        if df is None or df.empty:
            attempts.append(f"{p.name} {code}: 기간 안에 거래 기록 없음")
            continue
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        attempts.append(f"{p.name} {code}: {len(df)}일")
        return Fetched(df, OK, Source(p.name, {"ticker": code, "start": _ymd(start), "end": _ymd(end)}), attempts)
    return Fetched(None, status, Source("prices", {"ticker": code}), attempts)


def trading_calendar(start, end, provider: PriceProvider | None = None, market: str = "KOSPI") -> Fetched:
    """시장지수에 값이 있는 날 = 거래일. 지수까지 비면 KRX 응답 문제로 본다."""
    p = provider or PykrxProvider()
    code = MARKET_INDEX[market]
    params = {"index": code, "start": _ymd(start), "end": _ymd(end)}
    try:
        df = p.index(code, _ymd(start), _ymd(end))
    except Exception as error:  # noqa: BLE001
        return Fetched(None, API_ERROR, Source(p.name, params), [f"{market} 지수: 조회 실패 {scrub(error)}"])
    if df is None or df.empty:
        return Fetched(None, API_ERROR, Source(p.name, params, note="지수가 비면 KRX 응답 문제(접속 차단·점검)일 가능성이 큼"),
                       [f"{market} 지수: 빈 응답"])
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    return Fetched(df, OK, Source(p.name, params), [f"{market} 지수: {len(df)}거래일"])


def classify_days(ohlcv: pd.DataFrame | None, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """거래일마다 종가와 상태. 정상이 아닌 날의 '사용 종가'는 비워 둔다."""
    out = pd.DataFrame(index=calendar)
    if ohlcv is None or ohlcv.empty:
        out["종가"] = float("nan")
        out["상태"] = MISSING
        out["사용 종가"] = float("nan")
        return out
    df = ohlcv.reindex(calendar)
    present = df["종가"].notna()  # 거래정지일도 행은 있다. 행이 처음·마지막으로 있는 날로 상장 기간을 본다
    first, last = (present[present].index.min(), present[present].index.max()) if present.any() else (None, None)
    status = []
    for day, row in df.iterrows():
        if first is None or day < first:
            status.append(BEFORE_LISTING if first is not None else MISSING)
        elif day > last:
            status.append(AFTER_LAST_TRADE)
        elif pd.isna(row["종가"]):
            status.append(MISSING)
        elif row["거래량"] == 0 and row.get("시가", 0) == 0:
            status.append(HALTED)
        elif row["종가"] <= 0:
            status.append(MISSING)
        else:
            status.append(NORMAL)
    out["종가"] = df["종가"]
    out["상태"] = status
    out["사용 종가"] = df["종가"].where(out["상태"] == NORMAL)
    return out


def price_panel(tickers, start, end, provider: PriceProvider | None = None, market: str = "KOSPI",
                fallback: PriceProvider | None = None, key_map: dict | None = None) -> dict:
    """이벤트 스터디용 표. 반환:

    - prices: 거래일 × 종목(key_map이 있으면 corp_code) 수정 종가. 정상이 아닌 날은 비어 있음
    - market: 같은 거래일의 시장지수 종가
    - report: 종목별 상태 일수(수집 현황표)
    - fetched: 종목별 Fetched(시도 경로 확인용)
    """
    cal = trading_calendar(start, end, provider, market)
    if not cal.found:
        raise RuntimeError(f"거래일 달력을 만들지 못함: {' → '.join(cal.attempts)}")
    calendar = cal.value.index
    columns, rows, fetched = {}, [], {}
    for t in tickers:
        code = normalize_ticker(t)
        f = fetch_ohlcv(code, start, end, provider, fallback)
        fetched[code] = f
        days = classify_days(f.value, calendar)
        key = (key_map or {}).get(code, code)
        columns[key] = days["사용 종가"]
        counts = days["상태"].value_counts()
        rows.append({"종목코드": code, "열 이름": key, "수집 상태": f.status,
                     **{s: int(counts.get(s, 0)) for s in DAY_STATUSES}, "시도 경로": " → ".join(f.attempts)})
    return {
        "prices": pd.DataFrame(columns, index=calendar),
        "market": cal.value["종가"],
        "report": pd.DataFrame(rows),
        "fetched": fetched,
    }


def listing(date, markets=("KOSPI", "KOSDAQ"), provider: PriceProvider | None = None) -> Fetched:
    """그날 상장 종목표(종목코드·종목명·시장). 시장 하나라도 비면 KRX 응답 문제로 본다."""
    p = provider or PykrxProvider()
    frames, attempts = [], []
    for m in markets:
        try:
            names = p.tickers(_ymd(date), m)
        except Exception as error:  # noqa: BLE001
            return Fetched(None, API_ERROR, Source(p.name, {"date": _ymd(date)}), attempts + [f"{m}: 조회 실패 {scrub(error)}"])
        if not names:
            return Fetched(None, API_ERROR, Source(p.name, {"date": _ymd(date)}, note="휴장일이면 직전 거래일로 다시"),
                           attempts + [f"{m}: 빈 응답"])
        attempts.append(f"{m}: {len(names)}종목")
        frames.append(pd.DataFrame({"종목코드": list(names), "종목명": list(names.values()), "시장": m}))
    return Fetched(pd.concat(frames, ignore_index=True), OK, Source(p.name, {"date": _ymd(date)}), attempts)


def market_panels(tickers_by_market: dict[str, list], start, end, provider: PriceProvider | None = None,
                  fallback: PriceProvider | None = None, key_map: dict | None = None) -> dict:
    """시장별로 price_panel을 돌려 합친다. 코스닥 종목은 코스닥 지수, 코스피 종목은 코스피 지수와 짝짓는다.

    반환: prices(거래일 × 종목), markets({시장: 지수 종가}), market_of({열 이름: 시장}), report, fetched
    """
    prices, markets, market_of, reports, fetched = [], {}, {}, [], {}
    for market, codes in tickers_by_market.items():
        if not codes:
            continue
        panel = price_panel(codes, start, end, provider, market, fallback, key_map)
        prices.append(panel["prices"])
        markets[market] = panel["market"]
        market_of.update({col: market for col in panel["prices"].columns})
        reports.append(panel["report"].assign(시장=market))
        fetched.update(panel["fetched"])
    return {
        "prices": pd.concat(prices, axis=1).sort_index() if prices else pd.DataFrame(),
        "markets": markets,
        "market_of": market_of,
        "report": pd.concat(reports, ignore_index=True) if reports else pd.DataFrame(),
        "fetched": fetched,
    }
