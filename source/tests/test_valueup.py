"""밸류업 배당 약속과 최소 필요 배당 비교 테스트 (화면에서는 뺀 기능의 계산)."""
from core.min_dividend import MinInput, min_required
from core.valueup import AT_LEAST, BELOW, MET, NOT_COMPARABLE, SHORT, DividendTarget, PastTarget, compare, implementation

MIN_1100 = min_required(MinInput(100, 1_000, 4_000))  # 1,100원


def test_total_target():
    assert compare(DividendTarget("총액", 1_100), MIN_1100).status == AT_LEAST
    assert compare(DividendTarget("총액", 1_099), MIN_1100).status == BELOW


def test_dps_target_uses_outstanding_shares():
    t = DividendTarget("주당배당금", 10, issued_shares=120, treasury_shares=10)  # 10원 × 110주
    r = compare(t, MIN_1100)
    assert (r.status, r.target_amount) == (AT_LEAST, 1_100)
    assert compare(DividendTarget("주당배당금", 10), MIN_1100).status == NOT_COMPARABLE


def test_payout_target_with_fraction_and_denominator_note():
    t = DividendTarget("배당성향", "27.4875", denominator=4_000, denominator_is_tax_basis=False)
    r = compare(t, MIN_1100)
    assert r.status == BELOW  # 1,099.5 < 1,100
    assert r.target_amount == 1_099
    assert any("분모" in n for n in r.notes)


def test_not_comparable_cases():
    assert compare(None, MIN_1100).status == NOT_COMPARABLE
    hold = min_required(MinInput(None, 1_000, 10_000))
    assert compare(DividendTarget("총액", 5_000), hold).status == NOT_COMPARABLE


def test_implementation_default_unverified():
    assert compare(DividendTarget("총액", 1_100), MIN_1100).implementation == "이행 내역 미확인"


def test_past_target_against_actual_dividend():
    # 배당성향: 그해 D ÷ 지배주주 순이익, 같으면 목표 이상
    assert implementation(PastTarget(2025, "배당성향", "40"), 400, 1_000, None) == \
        f"2025 사업연도 배당성향 목표 40.0% → 실제 40.0% ({MET})"
    assert SHORT in implementation(PastTarget(2025, "배당성향", "40"), 399, 1_000, None)
    assert "분모" in implementation(PastTarget(2025, "배당성향", "40", basis_note="별도 기준"), 500, 1_000, None)
    assert implementation(PastTarget(2025, "배당성향", "40"), 400, 0, None) is None  # 적자·0이면 대조 안 함
    # 주당배당금: 보통주 주당 현금배당금, 총액: D
    assert implementation(PastTarget(2024, "주당배당금", "5000"), None, None, 5_400) == \
        f"2024 사업연도 주당배당금 목표 5,000원 → 실제 5,400원 ({MET})"
    assert implementation(PastTarget(2024, "주당배당금", "5000"), None, None, None) is None
    assert SHORT in implementation(PastTarget(2024, "총액", 1_000), 999, None, None)


def test_implementation_survives_missing_target():
    assert compare(None, MIN_1100, "x 목표 이상 배당").implementation == "x 목표 이상 배당"
