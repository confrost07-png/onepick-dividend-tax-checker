"""최소 필요 배당액: 최소액이면 통과, 1원 모자라면 미충족."""
import pytest

from core.min_dividend import (
    COMPUTED,
    HOLD,
    IMPOSSIBLE,
    MinInput,
    level,
    min_required,
    passes_2027,
    scenarios,
)

CASES = [
    # (B2024, D2025, NI2026)
    (100, 1_000, 4_000),  # 나목 10% 증가가 결정 (1,100)
    (100, 1_000, 2_000),  # 가목 40%가 더 작음 (800)
    (100, 1_000, 6_000),  # 25% 하한이 결정 (1,500)
    (5_000, 1_000, 10_000),  # 2024 배당소득이 결정
    (100, 333, 1_001),  # 올림이 생기는 금액
    (100, 0, 1_000),  # 2025 무배당 → 가목 기준
]


@pytest.mark.parametrize("b2024,d2025,ni", CASES)
def test_minimum_passes_and_one_won_less_fails(b2024, d2025, ni):
    x = MinInput(b2024, d2025, ni)
    r = min_required(x)
    assert r.status == COMPUTED
    assert passes_2027(r.amount, x)
    assert not passes_2027(r.amount - 1, x)


def test_known_values():
    assert min_required(MinInput(100, 1_000, 4_000)).amount == 1_100
    assert min_required(MinInput(100, 1_000, 2_000)).amount == 800
    assert min_required(MinInput(100, 1_000, 6_000)).amount == 1_500
    assert min_required(MinInput(100, 333, 1_001)).amount == 367  # 1.10×333 = 366.3 → 올림


def test_deficit_cases():
    ok = min_required(MinInput(100, 1_000, -5, liabilities=200, equity=100))
    assert (ok.status, ok.amount) == (COMPUTED, 1_100)
    assert passes_2027(1_100, MinInput(100, 1_000, -5, liabilities=200, equity=100))
    assert min_required(MinInput(100, 1_000, -5, liabilities=201, equity=100)).status == IMPOSSIBLE
    assert min_required(MinInput(100, 1_000, -5, liabilities=1, equity=0)).status == HOLD
    assert min_required(MinInput(100, 0, -5, liabilities=1, equity=10)).status == HOLD


def test_hold_when_b_differs_from_d_or_missing():
    assert min_required(MinInput(100, 1_000, 10_000, b_equals_d=False)).status == HOLD
    assert min_required(MinInput(None, 1_000, 10_000)).status == HOLD


def test_scenarios_dedupe_and_extras():
    rows = scenarios(100, 1_000, {2023: 2_000, 2024: 4_000, 2025: 4_000}, declared_2026=300)
    assert [s.label for s in rows] == ["최근 3년 최저", "2025년 (기본)"]  # 2025 = 최고라 합침
    base = rows[1]
    assert base.result.amount == 1_100
    assert base.ratio_to_2025_pct == 110.0
    assert base.additional_needed == 800
    assert base.pass_if_same_as_2025 is False  # 같은 금액이면 10% 증가가 없음


def test_higher_profit_can_need_more_dividend():
    low = min_required(MinInput(100, 1_000, 2_000)).amount
    high = min_required(MinInput(100, 1_000, 6_000)).amount
    assert high > low


def test_level():
    assert level(min_required(MinInput(100, 1_000, 2_000)), 1_000) == "유지로 충분"
    assert level(min_required(MinInput(100, 1_000, 4_000)), 1_000) == "늘려야 함"
    assert level(min_required(MinInput(100, 1_000, -5, liabilities=201, equity=100)), 1_000) == "어려움"
