"""요건 판정 경계값: 25%·40%·10%의 바로 아래와 경계, 순이익 0원, 부채 정확히 2배, 자본잠식, 전전 무배당."""
import pytest

from core.judgement import HOLD, MET, NOT_MET, judge_2026

NI = 1_000_000_000  # 순이익 10억 원


def j(d2025, d2024=100_000_000, ni=NI, b2025=None, b2024=1, **kw):
    b2025 = d2025 if b2025 is None else b2025
    return judge_2026(b2025, b2024, d2025, d2024, ni, **kw)


def test_payout_40_boundary():
    assert j(400_000_000).route == "가목"
    r = j(399_999_999, d2024=399_999_999)  # 40% 1원 아래, 증가 없음
    assert r.status == NOT_MET


def test_payout_25_boundary_with_growth():
    r = j(250_000_000, d2024=227_272_727)  # 25% 경계, 10% 이상 증가
    assert (r.status, r.route) == (MET, "나목")
    assert j(249_999_999, d2024=100_000_000).status == NOT_MET  # 25% 1원 아래


def test_growth_10_boundary():
    assert j(330_000_000, d2024=300_000_000).route == "나목"  # 정확히 10% 증가
    assert j(329_999_999, d2024=300_000_000).status == NOT_MET  # 10% 1원 아래


def test_rule2_dividend_must_not_fall_below_2024():
    assert j(500_000_000, b2025=99, b2024=100).status == NOT_MET
    assert j(500_000_000, b2025=100, b2024=100).status == MET  # 같으면 통과


def test_zero_net_income_is_deficit():
    r = j(110, d2024=100, ni=0, liabilities=200, equity=100)  # 부채 정확히 2배 → 초과 아님 → 25% 간주
    assert (r.status, r.route) == (MET, "나목")


def test_deficit_debt_over_twice_equity():
    assert j(110, d2024=100, ni=-1, liabilities=201, equity=100).status == NOT_MET


def test_deficit_capital_impairment_is_hold():
    assert j(110, d2024=100, ni=-1, liabilities=300, equity=0).status == HOLD


def test_deficit_needs_balance_sheet():
    assert j(110, d2024=100, ni=-1).status == HOLD


def test_zero_prev_dividend_on_route_b_is_hold():
    r = j(300_000_000, d2024=0)
    assert r.status == HOLD and "무배당" in r.reasons[0]
    assert j(400_000_000, d2024=0).status == MET  # 가목이면 전전 무배당과 무관


def test_deficit_no_dividend_both_years_is_not_met():
    # 팀 확정 대응표(2026-10-26): 직전·전전 모두 무배당이면 증가 없음 → 나목 미충족
    r = j(0, d2024=0, ni=-1, b2025=1, liabilities=100, equity=100)
    assert r.status == NOT_MET and "증가 없음" in r.reasons[0]
    assert j(110, d2024=0, ni=-1, liabilities=100, equity=100).status == HOLD  # 직전 배당이 있으면 여전히 보류
    assert j(0, d2024=0, b2025=1).status == NOT_MET  # 흑자면 배당성향 0%로 이미 미충족


def test_deemed_payout_marks_deficit_judgements():
    # 시행령 제104조의24⑤: 적자로 간주한 배당성향을 실제 배당성향과 구분해 남긴다
    assert j(110, d2024=100, ni=-1, liabilities=200, equity=100).deemed_payout == 25
    assert j(100, d2024=100, ni=-1, liabilities=100, equity=100).deemed_payout == 25  # 증가 미달이어도 25% 간주
    assert j(110, d2024=100, ni=-1, liabilities=201, equity=100).deemed_payout == 0
    assert j(110, d2024=100, ni=-1).deemed_payout is None  # 부채 결측: 간주값 고르지 않음
    assert j(110, d2024=100, ni=-1, liabilities=300, equity=0).deemed_payout is None  # 자본잠식
    assert j(400_000_000).deemed_payout is None  # 흑자는 실제 배당성향


def test_missing_data_and_unconfirmed_reduction_hold():
    r = judge_2026(None, 1, 1, 1, 1)
    assert r.status == HOLD and "B(직전)" in r.reasons[0]
    assert j(400_000_000, reduction_unconfirmed=True).status == HOLD


MIL = 1_000_000  # 백만 원


def test_million_unit_near_boundary_asks_recheck():
    # 배당성향 40.0%: 백만 원 단위 오차로 가목/나목이 갈릴 수 있음
    r = judge_2026(400 * MIL, 1, 400 * MIL, 300 * MIL, 1_000 * MIL, d_unit=MIL, ni_unit=MIL)
    assert r.status == MET and r.needs_recheck
    assert "재확인" in r.reasons[-1]


def test_million_unit_far_from_boundary_no_recheck():
    r = judge_2026(500 * MIL, 1, 500 * MIL, 300 * MIL, 1_000 * MIL, d_unit=MIL, ni_unit=MIL)
    assert r.route == "가목" and not r.needs_recheck


def test_won_unit_never_asks_recheck():
    assert not j(400_000_000).needs_recheck


@pytest.mark.parametrize("status,tag", [(MET, "현재 해석 기준"), (HOLD, "판정 보류")])
def test_tag(status, tag):
    r = j(400_000_000) if status == MET else j(300_000_000, d2024=0)
    assert r.tag == tag
