"""F-06 재무 여력 규칙: 금융업 미적용, 최소액 없으면 미표시, 잉여현금 ÷ 최소액."""
from core import capacity as cp


def test_cover_ratio_and_metrics():
    x = cp.capacity("살균ㆍ살충제 및 농약 제조업", ocf=300, capex=-100, min_amount=50, ni=40, liabilities=200, equity=400)
    assert (x.status, x.fcf, x.cover, x.roe_pct, x.debt_pct) == (cp.SHOWN, 200, 4.0, 10.0, 50.0)


def test_financial_industry_and_missing_minimum():
    assert cp.capacity("은행 및 저축기관", 1, 1, 1, 1, 1, 1).status == cp.NOT_APPLIED
    assert cp.capacity("증권 중개업", 1, 1, 1, 1, 1, 1).status == cp.NOT_APPLIED
    assert cp.capacity("지주회사", 1, 1, 1, 1, 1, 1, name="KB금융").status == cp.NOT_APPLIED
    assert cp.capacity("지주회사", 1, 1, 1, 1, 1, 1, name="SK").status == cp.SHOWN
    assert cp.capacity("자동차 부품 제조업", 100, 10, None, 5, 10, 20).status == cp.NOT_SHOWN


def test_industry_median_falls_back_to_overall_when_few():
    vals = {"A": [1.0, 2.0, 3.0, 4.0, 5.0], "B": [9.0]}
    assert cp.industry_median(vals, "A", [1, 2, 3, 4, 5, 9]) == (3.0, "같은 업종 5곳 중앙값")
    v, basis = cp.industry_median(vals, "B", [1, 2, 3, 4, 5, 9])
    assert v == 3.5 and "전체 6곳" in basis
