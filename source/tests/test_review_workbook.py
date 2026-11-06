"""전수 검산표: 주식 종류 구분과 수식 규칙(파이썬 판)."""
from scripts import check_review_workbook as ck
from scripts.export_review_workbook import same, stock_kind


def test_stock_kind_groups_common_and_preferred():
    assert [stock_kind(k) for k in ("보통주", "보통주식", "의결권있는주식", "우선주", "종류주식", "의결권없는주식", "-", "")] == \
        ["보통", "보통", "보통", "우선", "우선", "우선", "-", "-"]


def test_same_formula_text_uses_tolerance():
    assert same("A2", "B2", 1000) == "OR(AND(ISBLANK(A2),ISBLANK(B2)),AND(ISNUMBER(A2),ISNUMBER(B2),ABS(A2-B2)<1000))"


def test_cash_rule_accepts_change_with_or_without_fx():
    row = {"기초 현금(원)": 100.0, "현금 순증감(원)": -20.0, "환율변동효과(원)": 5.0, "기말 현금(원)": 80.0}
    assert ck.cash(row) == "일치"  # 순증감에 환율효과 포함
    assert ck.cash({**row, "기말 현금(원)": 85.0}) == "일치"  # 순증감 + 환율효과
    assert ck.cash({**row, "기말 현금(원)": 90.0}) == "불일치"


def test_ratio_and_min_rules():
    r = ck.ratio("p", "t", "n")
    assert r({"p": 25.0, "t": 25.0, "n": 100.0}) == "일치" and r({"p": 30.0, "t": 25.0, "n": 100.0}) == "불일치"
    assert r({"p": 30.0, "t": 25.0, "n": -1.0}) == "계산 대상 아님"
    base = {"2023 순이익(원)": 10.0, "2024 순이익(원)": 30.0, "2025 순이익(원)": 20.0}
    assert ck.min_div({**base, "시나리오": "최근 3년 최저", "가정한 2026 순이익(원)": 10.0}) == "일치"
    assert ck.min_div({**base, "시나리오": "2025년 (기본)", "가정한 2026 순이익(원)": 20.0}) == "일치"
    assert ck.min_div({**base, "시나리오": "최근 3년 최고", "가정한 2026 순이익(원)": 20.0}) == "불일치"
