"""무리별 주가 누적 수익률 (분석 설계 C2).

같은 날짜로 638사 안의 두 무리를 비교하면 시장 전체 움직임은 서로 상쇄된다. 그래서 2026년 지수를 다른 출처와
대조하지 않았어도 무리 간 차이는 볼 수 있다. 수익률은 수정 종가만 쓴 '주가 수익률'이다(배당은 넣지 않음).
"""
import bisect
from datetime import date


def cumulative(series: list[tuple[date, float]], start: date, checkpoints: list[date]) -> list[float | None]:
    """start 이후 첫 거래일 종가를 기준(0%)으로, 각 기준일(그날이나 그 전 마지막 거래일)의 누적 수익률(%).

    series는 날짜 순서. 기준 가격이 없거나 기준일 전에 값이 없으면 None.
    """
    days = [d for d, _ in series]
    i0 = bisect.bisect_left(days, start)
    if i0 == len(days):
        return [None] * len(checkpoints)
    base = series[i0][1]
    out = []
    for c in checkpoints:
        j = bisect.bisect_right(days, c) - 1
        out.append((series[j][1] / base - 1) * 100 if j >= i0 and base else None)
    return out


def month_ends(start: date, end: date) -> list[date]:
    """start가 속한 달부터 end까지 각 달의 마지막 날(달력 기준). 마지막은 end."""
    out, y, m = [], start.year, start.month
    while True:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = date.fromordinal(date(ny, nm, 1).toordinal() - 1)
        if last >= end:
            out.append(end)
            return out
        out.append(last)
        y, m = ny, nm


def equal_weight_index(prices: dict[str, dict[date, float]], days: list[date]) -> dict[date, float]:
    """회사마다 같은 무게로 평균한 지수(첫날 = 1). 그날과 전날 가격이 모두 있는 회사의 하루 수익률 평균을 쌓는다."""
    level, out = 1.0, {days[0]: 1.0}
    for prev, day in zip(days, days[1:]):
        rets = [p[day] / p[prev] - 1 for p in prices.values() if day in p and prev in p and p[prev]]
        level *= 1 + (sum(rets) / len(rets) if rets else 0.0)
        out[day] = level
    return out


def abnormal_return(stock: dict[date, float], bench: dict[date, float], days: list[date], event: date, n: int) -> float | None:
    """공시일(그날이나 그 뒤 첫 거래일 = 0일) 전날 종가부터 n일 뒤 종가까지 주가 수익률 − 기준 수익률(%).

    공시 시각을 모르므로 0일 하루를 통째로 넣는다. 필요한 날 값이 없으면 None.
    """
    i = bisect.bisect_left(days, event)
    if i == 0 or i + n >= len(days):
        return None
    a, b = days[i - 1], days[i + n]
    if a not in stock or b not in stock or a not in bench or b not in bench:
        return None
    return ((stock[b] / stock[a]) - (bench[b] / bench[a])) * 100
