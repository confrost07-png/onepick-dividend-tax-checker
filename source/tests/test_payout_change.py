"""배당성향 변화 분해 테스트: 이미 기준을 넘은 회사, 이익·배당 몫 나누기."""
import pytest

from core import payout_change as pc


def test_already_above():
    assert pc.classify(30, 30, 100, 100) == pc.ALREADY


def test_by_dividend():  # 20% → 26%: 순이익 그대로, 배당만 늘림
    assert pc.classify(20, 26, 100, 100) == pc.BY_DIVIDEND


def test_by_profit():  # 20% → 25%: 배당 그대로, 순이익만 줄어듦
    assert pc.classify(20, 20, 100, 80) == pc.BY_PROFIT


def test_either():  # 배당만으로 25%, 순이익만으로도 25%
    assert pc.classify(20, 25, 100, 80) == pc.EITHER


def test_both_needed():  # 배당만이면 22%, 순이익만이면 24.4%, 둘 다면 26.8%
    assert pc.classify(20, 22, 100, 82) == pc.BOTH_NEEDED


def test_edge_cases():
    assert pc.classify(None, 30, 100, 100) == pc.UNKNOWN
    assert pc.classify(10, 30, -5, 100) == pc.FROM_LOSS
    assert pc.classify(0, 30, 100, 100) == pc.FROM_ZERO


def test_exact_25_counts_as_met():
    assert pc.at_least(25, 100) and not pc.at_least(24, 100)


def test_dividend_share():
    assert pc.dividend_share(20, 26, 100, 100) == pytest.approx(100)
    assert pc.dividend_share(20, 20, 100, 80) == pytest.approx(0)
    assert pc.dividend_share(20, 25, 100, 80) == pytest.approx(50)
    assert pc.dividend_share(30, 20, 100, 100) is None


def test_payout_band():
    assert pc.payout_band(26, 100) == "25~28%"
    assert pc.payout_band(28, 100) == "28~40%"
    assert pc.payout_band(40, 100) == "40% 이상"
