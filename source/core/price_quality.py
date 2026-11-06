"""KRX 주가·지수의 날짜별 사용 등급 (사용 가능 / 주의 / 제외). 원본 행은 지우지 않고 표시만 만든다.

기준값은 팀 결정 전 임시값이다 → report/검증/데이터_교체_예정.md
- 상한 초과 등락: 국내 주식 하루 가격제한폭 ±30%. 호가 단위 반올림을 감안해 ±30.5%를 넘으면 '제외'
- 같은 가격 연속: 관측된 거래일 기준 5일 이상 '주의', 20일 이상 '제외' (거래정지 표시가 빠진 구간으로 의심)
- 지수 급등락: 2026년 이후 하루 ±8%를 넘는 날은 다른 출처와 대조 전이라 '주의'
"""
import pandas as pd

OK, CAUTION, EXCLUDE = "사용 가능", "주의", "제외"

PRICE_LIMIT = 0.30
TICK_TOLERANCE = 0.005
STALE_CAUTION_DAYS = 5
STALE_EXCLUDE_DAYS = 20
INDEX_MOVE = 0.08
INDEX_UNVERIFIED_FROM = "2026-01-01"

JUMP, STALE, INDEX_JUMP = "상한 초과 등락", "같은 가격 연속", "지수 급등락 미검증"


def _numeric(df: pd.DataFrame) -> pd.DataFrame:
    """가로형 표(행: 날짜 글자, 열: 코드)를 숫자로. 날짜는 date로 바꾼다."""
    out = df.apply(pd.to_numeric, errors="coerce")
    out.index = pd.to_datetime(out.index, format="%Y-%m-%d").date
    return out


def jump_flags(prices: pd.DataFrame) -> list[dict]:
    """직전 관측일 대비 등락이 ±(30% + 반올림 여유)를 넘는 날 → '제외'."""
    rows = []
    for code, col in _numeric(prices).items():
        x = col.dropna()
        ret = x / x.shift(1) - 1
        for day, r in ret[ret.abs() > PRICE_LIMIT + TICK_TOLERANCE].items():
            prev = x.shift(1)[day]
            rows.append({"corp_code": str(code).zfill(8), "trade_date": day, "kind": JUMP, "grade": EXCLUDE,
                         "detail": f"{r:+.1%} ({prev:,.0f} → {x[day]:,.0f})",
                         "rule": f"|등락| > {PRICE_LIMIT + TICK_TOLERANCE:.1%}"})
    return rows


def stale_flags(prices: pd.DataFrame) -> list[dict]:
    """같은 가격이 관측일 기준 5일 이상 이어지는 구간의 모든 날 → 20일 미만 '주의', 이상 '제외'."""
    rows = []
    for code, col in _numeric(prices).items():
        x = col.dropna()
        run_id = (x != x.shift(1)).cumsum()
        for _, run in x.groupby(run_id):
            n = len(run)
            if n < STALE_CAUTION_DAYS:
                continue
            grade = EXCLUDE if n >= STALE_EXCLUDE_DAYS else CAUTION
            detail = f"{run.iloc[0]:,.0f}원 {n}거래일 연속 ({run.index[0]} ~ {run.index[-1]})"
            rows += [{"corp_code": str(code).zfill(8), "trade_date": day, "kind": STALE, "grade": grade,
                      "detail": detail, "rule": f"{STALE_CAUTION_DAYS}일 이상 주의, {STALE_EXCLUDE_DAYS}일 이상 제외"}
                     for day in run.index]
    return rows


def price_flags(prices: pd.DataFrame) -> list[dict]:
    return jump_flags(prices) + stale_flags(prices)


def index_flags(market: pd.DataFrame) -> list[dict]:
    """market.csv(열: 'KOSPI 종가' 등): 미검증 기간에 하루 ±8%를 넘는 날 → '주의'."""
    df = _numeric(market.rename(columns=lambda c: str(c).replace("종가", "").strip()))
    since = pd.Timestamp(INDEX_UNVERIFIED_FROM).date()
    rows = []
    for name, col in df.items():
        ret = col / col.shift(1) - 1
        hit = ret[(ret.abs() > INDEX_MOVE) & (ret.index >= since)]
        rows += [{"market": name, "trade_date": day, "kind": INDEX_JUMP, "grade": CAUTION,
                  "detail": f"{r:+.1%}, 다른 출처와 대조 전", "rule": f"{INDEX_UNVERIFIED_FROM} 이후 |등락| > {INDEX_MOVE:.0%}"}
                 for day, r in hit.items()]
    return rows
