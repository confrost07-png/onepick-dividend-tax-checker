"""DB 값 ↔ DART 원문 대조 규칙: 단위 반올림, 기간 고르기, 불일치 설명. 원문 읽기는 가짜로 바꾼다."""
from core import dart_verify as dv


def test_compare_tolerates_unit_rounding_only():
    assert dv.compare(1_234_000_000, 1_234_000_000) == dv.MATCH
    assert dv.compare(1_234_000_000, 1_234_456_789) == dv.ROUNDING  # DB가 백만 원 단위
    assert dv.compare(1_234_000_000, 1_236_000_000) == dv.MISMATCH
    assert dv.compare(1_234_000_000, None) == dv.UNREADABLE


def test_periods_for_non_december():
    assert dv.periods_for(2024, 12) == ["2024.12"]
    assert dv.periods_for(2024, 3) == ["2024.03", "2025.03"]


class FakeReader:
    """(접수번호, 연결여부, 항목, 연도) → 값"""

    def __init__(self, values):
        self.values = values

    def statements(self, rcp, consolidated):
        return "", {"BS": type("BS", (), {"years": [2024]})(), "IS": None, "CF": None}

    def value(self, rcp, consolidated, item, year):
        return self.values.get((rcp, consolidated, item, year)), "검산"


REPORTS = {"2024.12": [("r24b", "[기재정정] 사업보고서 (2024.12)"), ("r24a", "사업보고서 (2024.12)")],
           "2025.12": [("r25", "사업보고서 (2025.12)")]}


def cell(reader, db_value, cons=True):
    return dv.verify_cell(reader, REPORTS, "00000001", "가나다", 2024, 12, "equity_won", cons, db_value, "core_financial_year")


def test_verify_uses_latest_filing_and_reports_match():
    r = cell(FakeReader({("r24b", True, "equity_won", 2024): 5_000_000_000.0}), 5_000_000_000.0)
    assert (r["result"], r["src_rcept_no"], r["src_period"]) == (dv.MATCH, "r24b", "2024.12")


def test_mismatch_is_explained_by_other_sources():
    vals = {("r24b", True, "equity_won", 2024): 5e9, ("r24b", False, "equity_won", 2024): 4e9}
    assert "다른 기준(별도)" in cell(FakeReader(vals), 4e9)["note"]
    vals = {("r24b", True, "equity_won", 2024): 5e9, ("r24a", True, "equity_won", 2024): 4e9}
    assert "정정 전 원공시" in cell(FakeReader(vals), 4e9)["note"]
    vals = {("r24b", True, "equity_won", 2024): 5e9, ("r25", True, "equity_won", 2024): 4e9}
    assert "1년 뒤 보고서 비교기간" in cell(FakeReader(vals), 4e9)["note"]
    r = cell(FakeReader({("r24b", True, "equity_won", 2024): 5e9}), 3e9)
    assert r["result"] == dv.MISMATCH and "찾지 못함" in r["note"]


def test_missing_report_period():
    r = dv.verify_cell(FakeReader({}), {}, "00000001", "가나다", 2024, 12, "equity_won", True, 1e9, "core_financial_year")
    assert r["result"] == dv.NO_REPORT and "(2024.12) 없음" in r["note"]
