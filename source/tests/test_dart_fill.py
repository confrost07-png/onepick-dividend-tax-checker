"""DART 원문 읽기·검산과 빈칸 채우기 규칙. 원문 받기는 가짜로 바꿔 네트워크 없이 시험한다."""
import pytest

from core import dart_doc as dd
from core import dart_fill as df

BS_HTML = """<table><tr><td>재 무 상 태 표</td></tr></table>
<table><tr><td>제 6(당) 기말 2023년 12월 31일 현재</td></tr><tr><td>제 5(전) 기말 2022년 12월 31일 현재</td></tr>
<tr><td>주식회사 가나다</td><td>(단위 : 천원)</td></tr></table>
<table><tr><td>과 목</td><td>주석</td><td>제 6(당)</td><td>제 5(전)</td></tr>
<tr><td>자산총계</td><td></td><td>3,000</td><td>2,500</td></tr>
<tr><td>부 채 총 계</td><td>12</td><td>1,200</td><td>(1,000)</td></tr>
<tr><td>자본총계</td><td></td><td>1,800</td><td>1,500</td></tr>
<tr><td>부채와자본총계</td><td></td><td>3,000</td><td>2,500</td></tr></table>
<table><tr><td>연 결 손 익 계 산 서</td></tr><tr><td>제 6 기 2023.01.01 부터 2023.12.31 까지</td></tr>
<tr><td>(단위 : 원)</td></tr></table>
<table><tr><td>Ⅸ. 당기순이익</td><td>5,000</td></tr><tr><td>지배주주순이익</td><td>4,200</td></tr>
<tr><td>비지배주주순이익</td><td>800</td></tr><tr><td>총포괄손익 합계</td><td>6,000</td></tr>
<tr><td>지배주주포괄이익</td><td>5,100</td></tr></table>"""


def test_table_lines_and_statement_reading():
    lines = dd.table_lines(BS_HTML)
    bs = dd.pick(dd.statements(lines, "BS"), False)
    assert (bs.years, bs.unit, bs.entity) == ([2023, 2022], 1000, "주식회사 가나다")
    assert bs.value(dd.L_LIAB, 2023) == 1_200_000 and bs.value(dd.L_LIAB, 2022) == -1_000_000  # 주석 '12'는 건너뜀
    ok, msg = dd.check_balance(bs, 2023)
    assert ok and "1,200,000 + 자본 1,800,000 = 3,000,000" in msg
    assert not dd.check_balance(bs, 2022)[0]  # (1,000) + 1,500 ≠ 2,500


def test_owner_net_income_reads_attribution_before_comprehensive_income():
    st = dd.pick(dd.statements(dd.table_lines(BS_HTML), "IS"), True)
    assert st.consolidated and st.years == [2023]
    v, msg = dd.owner_net_income(st, 2023)
    assert v == 4200 and "4,200 + 비지배 800 = 당기순이익 5,000" in msg


def test_cell_value_keeps_small_dividends_but_drops_note_refs_in_statements():
    assert dd.cell_value("20") == 20 and dd.cell_value("-") == 0 and dd.cell_value("") is None
    assert dd.cell_value("20", notes=True) is None and dd.cell_value("(1,234)") == -1234


def test_decision_fields():
    lines = ["1. 배당구분 | 결산배당 |", "2. 배당종류 | 현금배당 |", "3. 1주당 배당금(원) | 보통주식 | 1,150 |",
             "종류주식 | 1,200 |", "5. 배당금총액(원) | 87,022,015,200 |", "6. 배당기준일 | 2023-12-31 |"]
    assert df.decision_fields(lines) == {"div_kind": "결산배당", "div_type": "현금배당", "dps_common_won": 1150,
                                         "total_won": 87022015200, "record_date": "2023-12-31"}


def _fake_report(monkeypatch, div_lines, title="가나다/사업보고서/2026.03.20", year=2025):
    node = dd.Node("6. 배당에 관한 사항", "1", "2", "3", "4", "5", "dart4.xsd")
    monkeypatch.setattr(dd, "filing", lambda rcp: (title, [node]))
    monkeypatch.setattr(dd, "section_lines", lambda nodes: div_lines)
    monkeypatch.setattr(df, "report_year", lambda nodes: year)


@pytest.mark.parametrize("lines, value, how", [
    (["주당 현금배당금(원) | 보통주 | 50 | 30 |", "우선주 | 60 | 40 |"], 50, "보통주 행"),
    (["주당 현금배당금(원) | 의결권있는주식수 | 500 | 500 |", "의결권없는주식수 | - | - |"], 500, "보통주 행"),
    (["주당 현금배당금(원) | 결산배당 | 150 | 150 |", "중간배당 | 100 | - |"], 250, "결산·중간·분기 행 합계"),
    (["주당 현금배당금(원) | 대주주 | 200 | 200 |", "소액주주 | 200 | 200 |"], 200, "차등배당"),
])
def test_common_dps_rules(monkeypatch, lines, value, how):
    _fake_report(monkeypatch, lines)
    r = df.common_dps("00000001", "가나다", 2025, ["1"])
    assert (r["value_won"], r["status"]) == (value, df.FILLED) and how in r["check_result"]


def test_common_dps_previous_year_column_and_unclear_rows(monkeypatch):
    _fake_report(monkeypatch, ["주당 현금배당금(원) | 보통주 | 50 | 30 |", "우선주 | 60 | 40 |"])
    r = df.common_dps("00000001", "가나다", 2024, ["1"])
    assert r["value_won"] == 30 and r["column_kind"].startswith("비교기간")
    _fake_report(monkeypatch, ["주당 현금배당금(원) | 대주주 | 300 |", "소액주주 | 200 |"])
    assert df.common_dps("00000001", "가나다", 2025, ["1"])["status"] == df.NEEDS_REVIEW  # 차등 금액이 다르면 사람 확인
    _fake_report(monkeypatch, ["주당 현금배당금(원) | 보통주 | - |", "우선주 | 700 |"])
    assert df.common_dps("00000001", "가나다", 2025, ["1"])["status"] == df.EMPTY_SOURCE  # 보통주 '-'는 채우지 않음


def test_other_company_report_is_skipped(monkeypatch):
    _fake_report(monkeypatch, ["주당 현금배당금(원) | 보통주 | 50 |"], title="다른회사/사업보고서/2026.03.20")
    r = df.common_dps("00000001", "가나다", 2025, ["1"])
    assert r["status"] == df.NEEDS_REVIEW and "못 찾음" in r["note"]


def test_financial_fill_requires_balance_check(monkeypatch):
    node = dd.Node("4. 재무제표", "1", "2", "3", "4", "5", "dart4.xsd")
    monkeypatch.setattr(dd, "filing", lambda rcp: ("가나다/사업보고서/2024.03.20", [node]))
    monkeypatch.setattr(dd, "section_lines", lambda nodes: dd.table_lines(BS_HTML))
    rows = {r["item"]: r for r in df.financial("00000001", "가나다", 2023, ["liabilities_won", "equity_won"], False, ["1"])}
    assert rows["liabilities_won"]["value_won"] == 1_200_000 and rows["liabilities_won"]["status"] == df.FILLED
    rows = {r["item"]: r for r in df.financial("00000001", "가나다", 2022, ["liabilities_won"], False, ["1"])}
    assert rows["liabilities_won"]["status"] == df.NEEDS_REVIEW  # 검산 안 맞으면 채우지 않음
    assert rows["liabilities_won"]["column_kind"].startswith("비교기간")


@pytest.mark.parametrize("lines, year, value", [
    (["현금배당금총액(백만원) | 7,146 | 6,253 | 4,466 |"], 2024, 6_253_000_000),  # 종류 칸 없는 표, 전기 열
    (["현금배당금총액(백만원) | - | 7,146 | 6,253 | 4,466 |"], 2025, 7_146_000_000),  # 종류 칸 '-' 있는 표, 당기 열
    (["현금배당금총액(백만원) | - | - | - |"], 2024, 0),  # 무배당은 0
])
def test_dividend_total_reads_the_year_column(monkeypatch, lines, year, value):
    _fake_report(monkeypatch, lines)
    r = df.dividend_total("00000001", "가나다", year, ["20260320000001"])
    assert (r["status"], r["value_won"], r["item"]) == (df.FILLED, value, "d_dart_won")


def test_dividend_total_without_report_or_row(monkeypatch):
    assert df.dividend_total("00000001", "가나다", 2019, [])["status"] == df.NEEDS_REVIEW
    _fake_report(monkeypatch, ["주당 현금배당금(원) | 보통주 | 50 |"])
    r = df.dividend_total("00000001", "가나다", 2025, ["20260320000001"])
    assert r["status"] == df.NEEDS_REVIEW and "행 못 찾음" in r["note"]


def test_no_report_marks_years_without_annual_report(monkeypatch):
    from scripts import fill_from_dart as ff
    ff.annual.cache_clear()
    monkeypatch.setattr(dd, "annual_reports", lambda corp: [("20240320000001", "사업보고서 (2023.12)", "2023.12")])
    rows = [df.row("00000001", 2019, "ni_owner_won", note="연결 재무제표에서 2019년 열을 못 찾음"),
            df.row("00000001", 2023, "ni_owner_won", note="못 읽음")]
    out = ff.no_report(rows)
    assert out[0]["status"] == df.NO_REPORT and "2019년 보고서 없음" in out[0]["note"]
    assert out[1]["status"] == df.NEEDS_REVIEW  # 그 해 보고서가 있으면 사람 확인으로 남김
    ff.annual.cache_clear()


def test_from_audit_uses_separate_audit_when_no_consolidated_that_year(monkeypatch):
    from scripts import fill_from_dart as ff
    ff.annual.cache_clear()
    ff.audits.cache_clear()
    monkeypatch.setattr(dd, "annual_reports", lambda corp: [("20240320000001", "사업보고서 (2023.12)", "2023.12")])
    monkeypatch.setattr(dd, "audit_reports", lambda corp: [("20200330000002", "감사보고서 (2019.12)", "2019.12", False)])
    seen = {}

    def fake_financial(corp, name, year, need, consolidated, rcepts):
        seen["args"] = (consolidated, rcepts)
        return [df.row(corp, year, k, 1.0, df.FILLED, rcept=rcepts[0]) for k in need]

    monkeypatch.setattr(df, "financial", fake_financial)
    rows = [df.row("00000001", 2019, "equity_won", note="연결 재무제표에서 2019년 열을 못 찾음")]
    out = ff.from_audit(rows, "00000001", "가나다", 2019, True)
    assert seen["args"] == (False, ["20200330000002"])
    assert out[0]["status"] == df.FILLED and "연결감사보고서 없음" in out[0]["note"]
    assert ff.from_audit(rows, "00000001", "가나다", 2023, True) == rows  # 사업보고서 있는 해는 그대로
    ff.annual.cache_clear()
    ff.audits.cache_clear()


@pytest.mark.parametrize("title, tag", [
    ("가나다/사업보고서/2020.03.30", ""),
    ("[기재정정]사업보고서 (2018.12)", ""),
    ("가나다/연결감사보고서/2020.04.29", "출처: 연결감사보고서 (사업보고서 아님)"),
    ("감사보고서제출 첨부 감사보고서", "출처: 감사보고서제출 첨부 감사보고서 (첨부파일, 사업보고서 본문 아님)"),
    ("분기보고서 (2021.03) 첨부 사업보고서", "출처: 분기보고서 첨부 사업보고서 (첨부파일, 사업보고서 본문 아님)"),
    (None, ""),
])
def test_source_tag_marks_values_not_from_annual_report(title, tag):
    assert df.source_tag(title) == tag
