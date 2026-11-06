"""밸류업 약속 읽기 테스트: 배당성향 목표 같은 약속 문장을 숫자로 바꾸기."""
from core import policy_promise as pp


def kinds(text):
    return {(p.kind, p.value) for p in pp.find(text)}


def test_dividend_payout_target():
    assert ("배당성향", "30") in kinds("향후 3년간 연결 기준 배당성향 30% 이상을 목표로 합니다.")


def test_roe_and_return_ratio_targets():
    k = kinds("• 향후 3년간 평균 ROE 9% 지향 • 총주주환원율 50% 이상 달성 • PBR 1배 이상 회복 추진")
    assert {("ROE", "9"), ("주주환원율", "50"), ("PBR", "1")} <= k


def test_needs_target_word():
    assert kinds("2024년 배당성향 35.2%, ROE 7.1%") == set()


def test_out_of_range_values_are_dropped():
    assert ("ROE", "120") not in kinds("ROE 120% 달성 목표")


def test_long_chart_text_is_skipped():
    chart = "ROE 목표 " + " ".join(f"{i}%" for i in range(200))
    assert not any(p.kind == "ROE" for p in pp.find(chart))


def test_actions():
    k = kinds("보유 자기주식 전량 소각 예정이며, 분기배당 도입을 검토합니다. 배당소득 분리과세 요건을 충족하도록 하겠습니다.")
    assert {("자사주 소각", ""), ("분기·중간배당", ""), ("분리과세 언급", "")} <= k


def test_dps_target_with_comma():
    assert ("주당배당금", "3500") in kinds("주당배당금 3,500원 이상 유지")


def test_same_value():
    assert pp.same_value("30", "30.0") and not pp.same_value("30", "31")
