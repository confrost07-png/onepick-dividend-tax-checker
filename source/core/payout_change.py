"""2025 배당성향이 25%를 넘은 이유를 회사별로 나눈다 (분석 설계 A1).

배당성향 = 배당 총액(D) ÷ 지배주주 순이익(NI). 2024 → 2025에 배당성향이 오르는 길은 두 가지다.
배당을 늘리거나, 순이익이 줄거나. 그래서 두 가지를 하나씩만 바꿔 본다.
- 배당만 바뀌었다면: 2025 배당 ÷ 2024 순이익 ≥ 25%?
- 순이익만 바뀌었다면: 2024 배당 ÷ 2025 순이익 ≥ 25%?
비율은 나누지 않고 곱해서 비교한다(100 × D ≥ 25 × NI). 금액은 원 단위 정수.
"""
import math

ALREADY = "2024년에도 이미 25% 이상"
BY_DIVIDEND = "배당을 늘려서 넘김"
BY_PROFIT = "순이익이 줄어서 넘김"
EITHER = "둘 중 하나만으로도 넘김"
BOTH_NEEDED = "둘이 겹쳐서 넘김"
FROM_LOSS = "2024년 적자에서 흑자로 바뀜"
FROM_ZERO = "2024년 무배당에서 배당 시작"
UNKNOWN = "2024년 값 없음"
CROSSED = (BY_DIVIDEND, BY_PROFIT, EITHER, BOTH_NEEDED)
ORDER = (ALREADY, BY_DIVIDEND, BY_PROFIT, EITHER, BOTH_NEEDED, FROM_LOSS, FROM_ZERO, UNKNOWN)


def at_least(d: int, ni: int, pct: int = 25) -> bool:
    """d ÷ ni ≥ pct% (ni > 0)."""
    return 100 * d >= pct * ni


def classify(d24: int | None, d25: int, ni24: int | None, ni25: int) -> str:
    """2025 배당성향이 25% 이상인 흑자 회사(d25 > 0, ni25 > 0)가 어떻게 25% 이상이 됐는지."""
    if d24 is None or ni24 is None:
        return UNKNOWN
    if ni24 <= 0:
        return FROM_LOSS
    if d24 == 0:
        return FROM_ZERO
    if at_least(d24, ni24):
        return ALREADY
    div_alone = at_least(d25, ni24)
    profit_alone = at_least(d24, ni25)
    if div_alone and profit_alone:
        return EITHER
    if div_alone:
        return BY_DIVIDEND
    if profit_alone:
        return BY_PROFIT
    return BOTH_NEEDED


def dividend_share(d24: int, d25: int, ni24: int, ni25: int) -> float | None:
    """배당성향 상승 가운데 배당 증가가 차지한 몫(%). 로그로 나눠 배당 몫 + 순이익 몫 = 100.

    ln(배당성향 변화) = ln(배당 변화) − ln(순이익 변화). 배당성향이 오르지 않았거나 값이 0 이하면 None.
    """
    if min(d24, d25, ni24, ni25) <= 0:
        return None
    total = math.log(d25 / d24) - math.log(ni25 / ni24)
    if total <= 0:
        return None
    return 100 * math.log(d25 / d24) / total


def payout_band(d25: int, ni25: int) -> str:
    """2025 배당성향 구간: 25~28%(기준선 바로 위) / 28~40% / 40% 이상."""
    if not at_least(d25, ni25, 28):
        return "25~28%"
    if not at_least(d25, ni25, 40):
        return "28~40%"
    return "40% 이상"
