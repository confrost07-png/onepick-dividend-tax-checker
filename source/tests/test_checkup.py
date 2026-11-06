"""가상 고객 5건으로 챗봇 점검 전체 흐름 검산 (기획안 10/29~11/01 '고정 가상 고객 5건')."""
from core.checkup import run_checkup
from core.judgement import HOLD, MET
from core.tax import COMPARED, NO_DIFFERENCE, SEPARATE_ONLY
from core.virtual_cases import CUSTOMERS


def _run(c):
    return run_checkup(c.holdings, c.interest, c.other_dividend, c.foreign_dividend,
                       c.base_without_financial, c.has_other_income)


def test_customer_branches():
    results = [_run(c) for c in CUSTOMERS]
    assert results[0].tax.status == NO_DIFFERENCE
    assert results[1].tax.t1.comprehensive is False and results[1].tax.direction == "감소"
    assert results[2].tax.t1.comprehensive is True
    assert results[3].tax.direction == "증가"
    assert results[4].tax_with_held is not None


def test_virtual_company_c_matches_design():
    r = _run(CUSTOMERS[1])
    c = r.stocks[0]
    assert (c.judgement.status, c.judgement.route) == (MET, "나목")
    assert [s.pass_if_same_as_2025 for s in c.scenarios] == [True, False, False]  # 피그마: 통과·미충족·미충족
    assert r.level == ("늘려야 함", "C사")
    assert c.valueup.status == "최소액 이상"
    base = c.base_scenario
    assert base.additional_needed == base.result.amount - c.company.declared_2026


def test_held_stock_goes_to_two_scenarios():
    r = _run(CUSTOMERS[4])
    e = next(s for s in r.stocks if s.company.name == "E사")
    assert e.judgement.status == HOLD and e.held > 0 and all(s.result.status == HOLD for s in e.scenarios)
    assert r.counts == {MET: 1, HOLD: 1, "미충족": 0}
    assert r.tax_with_held.separate_tax > r.tax.separate_tax


def test_unknown_answers_show_separate_tax_only():
    r = run_checkup({"C사": 3_000}, None, 0, 0, 60_000_000)
    assert r.tax.status == SEPARATE_ONLY and r.unknown_fields == ["이자"]
    # 다른 소득이 있어도 금융소득이 2천만 원 이하면 원천징수로 끝나 '차이 없음'(소득세법 제14조)
    r2 = run_checkup({"C사": 3_000}, 0, 0, 0, 60_000_000, has_other_income=True)
    assert r2.tax.status == NO_DIFFERENCE
    # 2천만 원을 넘으면 다른 소득이 있을 때 합산 세액을 알 수 없어 분리과세 세액만
    assert run_checkup({"C사": 3_000}, 10_000_000, 0, 0, 80_000_000, has_other_income=True).tax.status == SEPARATE_ONLY
    assert run_checkup({"C사": 3_000}, 10_000_000, 0, 0, 80_000_000).tax.status == COMPARED
