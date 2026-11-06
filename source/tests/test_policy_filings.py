"""4층 배당 정책 상세: 자사주·투자·인수 공시 응답 → 행, 뷰의 숫자·날짜 읽기, 카드 ⑥ '관련 공시' 표시."""
import datetime as dt
import json
from decimal import Decimal

import pytest

from core import policy_filings as pf

AQ = {"status": "000", "message": "정상", "list": [{
    "rcept_no": "20260129000003", "corp_code": "00126380", "corp_name": "삼성전자",
    "aqpln_stk_ostk": "22,000,000", "aqpln_stk_estk": "-", "aqpln_prc_ostk": "3,572,800,000,000", "aqpln_prc_estk": "-",
    "aqexpd_bgd": "2026년 01월 30일", "aqexpd_edd": "2026년 04월 29일", "aq_pp": "임직원 주식보상",
    "aq_mth": "유가증권시장을 통한 장내 매수", "aq_dd": "2026년 01월 28일"}]}
TRUST_CC = {"status": "000", "list": [{
    "rcept_no": "20240417000353", "corp_code": "00161383", "corp_name": "한미반도체", "bddd": "-",
    "ctr_prc_bfcc": "30,000,000,000", "ctr_prc_atcc": "-", "cc_pp": "신탁계약 기간 만료에 의한 해지",
    "cc_int": "현대차증권", "cc_prd": "2024년 04월 17일"}]}


def test_buyback_response_keeps_original_text():
    [r] = pf.rows_from_response("tsstkAqDecsn", AQ, {"20260129000003": "주요사항보고서(자기주식취득결정)"})
    assert r["kind"] == "자기주식 취득" and r["report_nm"] == "주요사항보고서(자기주식취득결정)"
    assert r["amount_raw"] == "3,572,800,000,000" and r["amount_etc_raw"] is None  # '-'는 비움, 쉼표는 그대로
    assert r["shares_raw"] == "22,000,000" and r["purpose_raw"] == "임직원 주식보상"
    assert r["decision_date_raw"] == "2026년 01월 28일" and r["period_end_raw"] == "2026년 04월 29일"
    assert r["source"] == "OpenDART tsstkAqDecsn" and json.loads(r["item"])["aq_mth"] == "유가증권시장을 통한 장내 매수"
    assert set(r) == set(pf.COLS)


def test_blank_board_date_falls_back_to_next_field():
    [r] = pf.rows_from_response("tsstkAqTrctrCcDecsn", TRUST_CC)
    assert r["decision_date_raw"] == "2024년 04월 17일" and r["amount_raw"] == "30,000,000,000"
    assert r["kind"] == "자기주식 취득 신탁 해지" and r["report_nm"] is None


def test_no_data_or_error_gives_no_rows():
    assert pf.rows_from_response("tsstkAqDecsn", {"status": "013", "message": "조회된 데이타가 없습니다."}) == []
    assert pf.rows_from_response("tsstkAqDecsn", {"status": "020", "list": AQ["list"]}) == []


def test_filing_list_fills_only_titles_without_api_and_own_company():
    filings = [
        {"rcept_no": "1", "corp_code": "00117212", "corp_name": "두산", "report_nm": "주식소각결정"},
        {"rcept_no": "2", "corp_code": "00117212", "corp_name": "두산", "report_nm": "[기재정정]주식소각결정(자회사의 주요경영사항)"},
        {"rcept_no": "3", "corp_code": "00117212", "corp_name": "두산", "report_nm": "타법인주식및출자증권처분결정"},
        {"rcept_no": "4", "corp_code": "00117212", "corp_name": "두산", "report_nm": "신규시설투자등(자율공시)"},
        {"rcept_no": "5", "corp_code": "00117212", "corp_name": "두산", "report_nm": "타법인주식및출자증권취득결정"},
    ]
    rows = pf.rows_from_filing_list(filings, have={"5"})
    assert [(r["rcept_no"], r["kind"]) for r in rows] == [("1", "주식 소각"), ("4", "신규 시설투자")]
    assert rows[0]["api"] == pf.FILING_LIST and rows[0]["amount_raw"] is None and set(rows[0]) == set(pf.COLS)


def test_cache_name_has_no_key():
    p = pf.cache_path("tsstkAqDecsn", "00126380", "20240101", "20261027")
    assert p.parent.name == "tsstkAqDecsn" and p.name == "00126380_20240101_20261027.json"


# --- 뷰: 시험 전용 DB onepick_test (DB 있을 때만) ---

@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from core import db
    url = "postgresql://localhost/onepick_test"
    try:
        db.create_database(url)
        c = db.connect(url)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL에 연결할 수 없음")
    db.apply_schema(c)
    yield c
    c.rollback()
    c.close()


def test_view_reads_numbers_dates_and_link(conn):
    from core import db
    rows = pf.rows_from_response("tsstkAqDecsn", AQ) + pf.rows_from_filing_list(
        [{"rcept_no": "20260331800004", "corp_code": "00126380", "corp_name": "삼성전자", "report_nm": "[기재정정]주식소각결정"}], set())
    db.replace_rows(conn, "raw.dart_policy_filing", rows)
    got = {r["rcept_no"]: r for r in db.fetch_dicts(conn, "SELECT * FROM core.v_policy_filing")}
    a, b = got["20260129000003"], got["20260331800004"]
    assert a["amount_won"] == Decimal("3572800000000") and a["shares"] == Decimal("22000000")
    assert a["decision_date"] == dt.date(2026, 1, 28) and a["rcept_dt"] == dt.date(2026, 1, 29)
    assert a["url"].endswith("rcpNo=20260129000003") and not a["is_correction"]
    assert b["amount_won"] is None and b["decision_date"] is None and b["is_correction"]
