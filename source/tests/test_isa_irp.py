"""ISA·IRP 계산이 발표 자료(ISA·IRP 2 · 계산 예시)의 숫자와 같은지."""
from core import isa_irp


def test_isa_dividend_3m_matches_slide():
    r = isa_irp.isa_compare(3_000_000)
    assert (r["normal"], r["general"], r["low_income"]) == (462_000, 99_000, 0)


def test_irp_9m_matches_slide():
    assert isa_irp.irp_credit(9_000_000, 0, 165)["credit"] == 1_485_000
    assert isa_irp.irp_credit(9_000_000, 0, 132)["credit"] == 1_188_000


def test_pension_saving_counts_only_6m_and_total_9m():
    r = isa_irp.irp_credit(0, 8_000_000, 165)
    assert r["counted"] == 6_000_000 and r["over"] == 2_000_000
    r = isa_irp.irp_credit(5_000_000, 6_000_000, 132)
    assert r["counted"] == 9_000_000 and r["over"] == 2_000_000


def test_refund_cannot_exceed_tax_due():
    assert isa_irp.irp_credit(9_000_000, 0, 165, tax_due=500_000)["refund"] == 500_000


def test_brackets_follow_slide():
    b = {x.key: (x.isa_free, x.irp_permil) for x in isa_irp.BRACKETS}
    assert b == {"low": (4_000_000, 165), "mid": (2_000_000, 165), "high": (2_000_000, 132),
                 "biz_low": (4_000_000, 165), "biz_mid": (2_000_000, 165), "biz_high": (2_000_000, 132)}


def test_business_brackets_match_profile():
    # 사업자 구간 버튼과 소득 종류별 판정(profile)이 같은 답을 내야 한다: 종합소득 5,300만 → 13.2%, 4,000만 → 일반형 16.5%
    by = {b.key: b for b in isa_irp.BRACKETS}
    assert isa_irp.irp_permil("business", 53_000_000) == by["biz_high"].irp_permil
    assert isa_irp.isa_type("business", 40_000_000) == by["biz_mid"].isa_type
    assert isa_irp.irp_permil("business", 40_000_000) == by["biz_mid"].irp_permil
    assert isa_irp.isa_type("business", 38_000_000) == by["biz_low"].isa_type


def test_unknown_bracket_shows_both_rates():
    g = isa_irp.guide(None, 3_000_000, 9_000_000)
    assert g["chosen"] is None and [x["credit"] for x in g["irp"]] == [1_485_000, 1_188_000]
    g = isa_irp.guide("high", 3_000_000, 9_000_000)
    assert g["chosen"]["key"] == "high" and len(g["irp"]) == 1


def test_early_exit_guides_are_in_the_page_data():
    g = isa_irp.guide(None, 0, 0)
    assert any("대출" in w["title"] for w in g["isa_early"]["ways"])
    assert len(g["irp_withdraw"]["reasons"]) == 5 and len(g["irp_withdraw"]["steps"]) == 3


def test_profile_wage_blocked_by_recent_comprehensive_tax():
    # 페르소나 김춘배: 2024·2025 종합과세 → 2026 ISA 가입 제한, 총급여 1.1억 → IRP 13.2%, 300만 원 → 396,000원
    p = isa_irp.profile("wage", 2026, 110_000_000, 110_000_000, [2024, 2025], 1_000_000, 3_000_000)
    assert p["isa"]["can_join"] is False and p["isa"]["blocked_years"] == [2024, 2025]
    assert p["irp"]["rate_permil"] == 132 and p["irp"]["credit"] == 396_000


def test_profile_business_uses_comprehensive_income_and_different_years():
    # 페르소나 고형식: 작년 종합소득 3,800만 → 서민형, 올해 4,200만 → 16.5%, 240만 원 → 396,000원
    p = isa_irp.profile("business", 2026, 38_000_000, 42_000_000, [], 1_000_000, 2_400_000,
                        what_if=[38_000_000, 45_000_000, 53_000_000])
    assert p["isa"]["can_join"] and p["isa"]["type"] == "서민형" and p["isa"]["normal_tax"] == 154_000
    assert p["irp"]["rate_permil"] == 165 and p["irp"]["credit"] == 396_000
    assert [w["credit"] for w in p["what_if"]] == [396_000, 396_000, 316_800]
    assert isa_irp.isa_type("business", 38_000_001) == "일반형" and isa_irp.isa_type("wage", 50_000_000) == "서민형"
    assert isa_irp.isa_blocked_years(2026, [2022]) == []


def test_wage_bracket_boundaries():
    from core.isa_irp import wage_bracket
    assert [wage_bracket(g) for g in (50_000_000, 50_100_000, 55_000_000, 55_100_000)] == ["low", "mid", "mid", "high"]


def test_rate_table_rows_follow_tax_rates():
    # 구간별 세율표: 종합소득세 8구간과 분리과세 4구간 경계를 합친 10행, 지방소득세 포함 천분율
    t = isa_irp.rate_table()
    assert [r["lower"] for r in t["rows"]] == [0, 14_000_000, 20_000_000, 50_000_000, 88_000_000, 150_000_000,
                                               300_000_000, 500_000_000, 1_000_000_000, 5_000_000_000]
    assert [r["basic_permil"] for r in t["rows"]] == [66, 165, 165, 264, 385, 418, 440, 462, 495, 495]
    assert [r["separate_permil"] for r in t["rows"]] == [154, 154, 220, 220, 220, 220, 275, 275, 275, 330]
    assert t["rows"][-1]["upper"] is None
    assert t["isa"]["over_permil"] == 99 and t["irp"]["over_permil"] == 165
