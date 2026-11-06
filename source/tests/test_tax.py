"""세액 비교: 세율 구간 경계, 기획안 예시, 가상 고객 5건."""
import pytest

from core import tax_rates as r
from core.tax import (
    COMPARED,
    NO_DIFFERENCE,
    SEPARATE_ONLY,
    TaxInput,
    compare,
    compare_with_held,
    comprehensive_tax,
    separate_tax,
)

MAN = 10_000  # 만 원


@pytest.mark.parametrize("brackets", [r.SEPARATE, r.BASIC])
def test_bracket_base_tax_is_cumulative(brackets):
    for prev, cur in zip(brackets, brackets[1:]):
        assert cur.base_tax == prev.base_tax + (cur.lower_bound - prev.lower_bound) * prev.rate_pct // 100


@pytest.mark.parametrize("e,expected", [
    (20_000_000 - 1, (20_000_000 - 1) * 14 // 100),
    (20_000_000, 2_800_000),
    (20_000_000 + 1, 2_800_000),  # 1원 × 20% = 0.2원 → 버림
    (20_000_005, 2_800_001),
    (300_000_000, 58_800_000),
    (300_000_004, 58_800_001),
    (5_000_000_000, 1_233_800_000),
    (5_000_000_010, 1_233_800_003),
])
def test_separate_tax_brackets(e, expected):
    assert separate_tax(e) == expected


def test_plan_example_financial_income_only_tax_rises_4_8m():
    """기획안: 금융소득만 있고 본인 기본공제만, 특례배당 1억 원 → 소득세 약 480만 원 증가."""
    res = compare(TaxInput(0, 0, 0, 100_000_000, base_without_financial=-150 * MAN))
    assert res.status == COMPARED
    assert res.t0.tax == 1_400 * MAN
    assert res.separate_tax == 1_880 * MAN
    assert res.difference == -480 * MAN
    assert res.direction == "증가"


def test_gross_up_fills_threshold_in_order():
    # 이자 1,500만 + 비대상 배당 300만 → 남은 200만만 대상 배당으로 채움
    t = comprehensive_tax(15_000_000, 3_000_000, 10_000_000, 50_000_000)
    assert t.gross_up == (10_000_000 - 2_000_000) * 10 // 100


# --- 가상 고객 5건 (기획안 2절 '세액 계산 데이터') ---

def test_customer1_financial_income_under_threshold_no_difference():
    res = compare(TaxInput(5_000_000, 0, 0, 10_000_000, base_without_financial=40_000_000))
    assert (res.status, res.difference) == (NO_DIFFERENCE, 0)


def test_customer2_switches_to_14pct_after_excluding_special():
    x = TaxInput(10_000_000, 0, 5_000_000, 30_000_000, base_without_financial=80_000_000)
    res = compare(x)
    assert res.t0.comprehensive is True
    assert res.t1.comprehensive is False  # 특례를 빼면 1,500만 원 → 14% 원천징수
    assert res.t1.tax == r.apply(r.BASIC, 80_000_000) + 15_000_000 * 14 // 100


def test_customer3_still_over_threshold_recomputes_credit():
    x = TaxInput(15_000_000, 0, 20_000_000, 50_000_000, base_without_financial=120_000_000)
    res = compare(x)
    assert res.t0.comprehensive and res.t1.comprehensive
    assert res.t1.gross_up < res.t0.gross_up
    assert res.t1.dividend_credit <= res.t1.gross_up


def test_customer4_little_other_income_tax_increases():
    res = compare(TaxInput(0, 0, 0, 60_000_000, base_without_financial=-150 * MAN))
    assert res.difference < 0 and res.direction == "증가"


def test_customer5_held_stock_two_scenarios():
    x = TaxInput(10_000_000, 0, 0, 40_000_000, base_without_financial=150_000_000)
    both = compare_with_held(x, held_dividend=20_000_000)
    assert set(both) == {"포함", "제외"}
    assert both["포함"].separate_tax == separate_tax(60_000_000)
    assert both["제외"].separate_tax == separate_tax(40_000_000)


def test_stop_conditions_show_separate_tax_only():
    res = compare(TaxInput(0, 0, 0, 50_000_000, base_without_financial=None))
    assert res.status == SEPARATE_ONLY and res.separate_tax == separate_tax(50_000_000)
    assert res.difference is None
    assert compare(TaxInput(0, 0, 0, 50_000_000, 10_000_000, has_other_income=True)).status == SEPARATE_ONLY


def test_high_earner_tax_decreases():
    res = compare(TaxInput(0, 0, 0, 100_000_000, base_without_financial=400_000_000))
    assert res.difference > 0 and res.direction == "감소"


# --- 국세청 보도자료(2026.3.9) 참고 2: 근로소득공제·소득공제·세액공제·기납부세액 없다고 가정 ---
# 그림의 세액: 사례1 종합과세 2,586만 원 / 분리과세 선택 2,104만 원, 사례2 904만 원 / 960만 원.
# 국세청 사례는 배당가산·배당세액공제를 넣지 않아 gross_up=False로 맞춘다.

@pytest.mark.parametrize("wage,t0_expected,t1_expected", [
    (7_000 * MAN, 2_586 * MAN, 2_104 * MAN),
    (1_000 * MAN, 904 * MAN, 960 * MAN),
])
def test_nts_press_release_cases(wage, t0_expected, t1_expected):
    high, general = 3_000 * MAN, 3_000 * MAN
    t0 = comprehensive_tax(0, 0, high + general, wage, gross_up=False).tax
    t1 = comprehensive_tax(0, 0, general, wage, gross_up=False).tax + separate_tax(high)
    assert (t0, t1) == (t0_expected, t1_expected)


def test_rate_table_status_recorded():
    assert all(b.status == r.CONFIRMED for b in r.SEPARATE)
    assert all(b.status == r.CONFIRMED for b in r.BASIC)  # 2026. 1. 1. 시행본 원문 대조(11-03)
    assert r.CONSTANT_SOURCES["GROSS_UP_PCT"][1] == r.CONFIRMED
