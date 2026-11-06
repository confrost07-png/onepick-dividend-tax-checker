"""주식 총수 이상치 판정: 자본금 대조와 PBR로 API 1,000배 오류를 가려내고, 나머지는 사유만 남긴다."""
from decimal import Decimal

from core import share_check as sc


def facts(**kw):
    base = dict(has_common=True, issued_all=Decimal("1000000"), floating=Decimal("900000"), par=Decimal("500"),
                capital=Decimal("500000000"), close=Decimal("10000"), equity=Decimal("10000000000"))
    return sc.Facts(**{**base, **kw})


def test_capital_match_is_not_an_anomaly():
    assert sc.judge(facts()) is None
    assert sc.judge(facts(capital=Decimal("505000000"))) is None  # 1% 안


def test_thousand_times_needs_both_capital_and_pbr():
    # 발행 × 액면 = 자본금 × 1,000, PBR 900 → ÷1,000 하면 0.9
    f = facts(issued_all=Decimal("1000000000"), floating=Decimal("900000000"))
    got = sc.judge(f)
    assert got.check == sc.UNIT_1000 and got.action == sc.FIX and got.factor == Decimal("0.001")
    assert got.ratio == Decimal("1000") and got.pbr_api > 100 and got.pbr_fixed < 100
    assert "1,000" in got.reason
    # 자본금은 1,000배인데 PBR이 정상 범위면 보정하지 않고 확인 필요로만
    f2 = facts(issued_all=Decimal("1000000000"), floating=Decimal("900000000"), equity=Decimal("1e13"))
    got2 = sc.judge(f2)
    assert got2.check == sc.CAPITAL_GAP and got2.action == sc.MARK and got2.factor == 1


def test_other_capital_gaps_are_marked_only():
    got = sc.judge(facts(capital=Decimal("600000000")))  # 비율 0.833 (이익소각 등)
    assert got.check == sc.CAPITAL_GAP and got.action == sc.MARK and got.factor == 1
    assert got.ratio == Decimal("0.833")


def test_cannot_compare_without_par_or_capital_or_common_row():
    assert sc.judge(facts(par=None)).check == sc.NO_COMPARE
    assert sc.judge(facts(capital=None)).check == sc.NO_COMPARE
    got = sc.judge(facts(has_common=False))
    assert got.check == sc.NO_COMMON and got.action == sc.MARK


def test_pbr_skipped_when_price_or_equity_missing():
    got = sc.judge(facts(issued_all=Decimal("1000000000"), floating=Decimal("900000000"), close=None))
    assert got.check == sc.CAPITAL_GAP and got.pbr_api is None  # 두 조건을 다 확인 못 하면 보정하지 않음
