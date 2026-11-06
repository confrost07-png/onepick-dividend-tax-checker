"""PRD v0.2 테이블: 원천 → raw·core 변환(DB 없이)과, 작은 시험 데이터로 스키마·키 확인(DB 있을 때만)."""
from decimal import Decimal

import pandas as pd
import pytest

from core import core_tables as ct
from core import raw_tables as rt
from core.judgement import HOLD

MIL = 1_000_000

DF02 = pd.DataFrame([
    # 회사 A: 2024·2025, 회사 B: 2025만
    {"DART고유번호": "00126380", "회사명": "A사", "종목코드": "005930", "시장": "KOSPI", "결산월": "12",
     "KIND유형_2025": "우수형", "사업연도": y, "현금배당총액(백만원)": d, "주당배당금_보통주(원)": "1,000",
     "재무제표_기준": "연결", "지배주주순이익(백만원)": ni, "부채총계(백만원)": "500", "자본총계(백만원)": "1000"}
    for y, d, ni in [("2023", "100", "900"), ("2024", "100", "1000"), ("2025", "400", "1000")]
] + [
    {"DART고유번호": "164779", "회사명": "B사", "종목코드": "660", "시장": "KOSDAQ", "결산월": "3",
     "KIND유형_2025": "노력형", "사업연도": "2025", "현금배당총액(백만원)": "-", "주당배당금_보통주(원)": None,
     "재무제표_기준": None, "지배주주순이익(백만원)": None, "부채총계(백만원)": None, "자본총계(백만원)": None},
])
DF07 = pd.DataFrame([{"DART고유번호": "00126380", "상장우선주_코드": "005935", "상태": "정상"}])
KIND = [{"corp_name": "A사", "corp_code": "00126380", "is_high_dividend": "해당"},
        {"corp_name": "B사", "corp_code": None, "is_high_dividend": "-"}]
DECISIONS = [
    # 같은 배당의 원공시와 정정공시 → 정정(늦은 것)만
    {"rcept_no": "1", "corp_code": "00126380", "attributed_year": 2025, "div_kind": "결산배당", "record_date": "2025-12-31",
     "disclosed_on": "2026-02-01", "div_type": "현금배당", "total_won": Decimal("399999999")},
    {"rcept_no": "2", "corp_code": "00126380", "attributed_year": 2025, "div_kind": "결산배당", "record_date": "2025-12-31",
     "disclosed_on": "2026-02-10", "div_type": "현금배당", "total_won": Decimal("400123456")},
    {"rcept_no": "3", "corp_code": "00126380", "attributed_year": 2026, "div_kind": "분기배당", "record_date": "2026-03-31",
     "disclosed_on": "2026-04-20", "div_type": "현금배당", "total_won": Decimal("100000000")},
    {"rcept_no": "4", "corp_code": "00126380", "attributed_year": 2026, "div_kind": "중간배당", "record_date": "2026-06-30",
     "disclosed_on": "2026-07-20", "div_type": "현물배당", "total_won": Decimal("5")},
    {"rcept_no": "5", "corp_code": "99999999", "attributed_year": 2025, "div_kind": "결산배당", "record_date": "2025-12-31",
     "disclosed_on": "2026-02-01", "div_type": "현금배당", "total_won": Decimal("1")},  # 목록에 없는 회사
]
CF = [{"corp_code": "00126380", "bsns_year": 2025, "paid_mil": Decimal("380"), "status": "정상"}]


def test_number_and_code_helpers():
    assert rt.num("1,234") == Decimal("1234") and rt.num("-") is None and rt.num(None) is None
    assert rt.code8("164779") == "00164779" and rt.code6("660") == "000660"
    assert rt.integer("2025") == 2025 and rt.integer("1.5") is None


def test_raw_financial_maps_dart_codes():
    df = pd.DataFrame([{"DART고유번호": "126380", "회사명": "A사", "사업연도": "2025", "재무제표_기준": "연결",
                        "재무제표_종류": "재무상태표", "계정명": "부채총계", "계정ID": "ifrs_Liabilities",
                        "당기금액(원)": "500,000,000", "전기금액(원)": None, "기수": "제1기", "표시순서": "12",
                        "통화": "KRW", "DART접수번호_재무": "2026"}])
    r = rt.dart_financial(df)[0]
    assert (r["corp_code"], r["fs_div"], r["sj_div"], r["ord"]) == ("00126380", "CFS", "BS", 12)
    assert r["thstrm_amount"] == Decimal("500000000") and r["source_file"] == rt.FILES["04-2"]


def test_company_rows():
    rows = {r["corp_code"]: r for r in ct.company_rows(DF02, DF07, KIND)}
    a, b = rows["00126380"], rows["00164779"]
    assert (a["stock_code"], a["is_december_fye"], a["kind_listed"], a["pref_stock_codes"]) == ("005930", True, True, "005935")
    assert (b["stock_code"], b["fiscal_month"], b["is_december_fye"], b["kind_listed"]) == ("000660", 3, False, False)


def test_dividend_year_keeps_three_branches_side_by_side():
    codes = {"00126380", "00164779"}
    rows = {(r["corp_code"], r["bsns_year"]): r for r in ct.dividend_year_rows(DF02, DECISIONS, CF, codes)}
    a25 = rows[("00126380", 2025)]
    assert a25["d_dart_won"] == 400 * MIL and a25["d_dart_unit"] == MIL
    assert a25["d_decision_won"] == Decimal("400123456") and a25["decision_count"] == 1  # 정정공시만
    assert a25["cf_paid_won"] == 380 * MIL
    assert a25["b_won"] is None and a25["b_status"] == "미산출"
    assert a25["source"] == "02+05+04"
    a26 = rows[("00126380", 2026)]  # 02에 없는 2026 기결의 배당은 05만으로 행 추가, 현물배당 제외
    assert (a26["d_dart_won"], a26["d_decision_won"], a26["source"]) == (None, 100 * MIL, "05")
    assert rows[("00164779", 2025)]["d_dart_won"] is None
    assert not any(k[0] == "99999999" for k in rows)


def test_without_b_everything_is_on_hold():
    companies = ct.company_rows(DF02, DF07, KIND)
    div = ct.dividend_year_rows(DF02, DECISIONS, CF, {c["corp_code"] for c in companies})
    fin = ct.financial_rows(DF02)
    judge = {r["corp_code"]: r for r in ct.judgement_rows(companies, div, fin)}
    assert all(r["status"] == HOLD for r in judge.values())
    assert "B(직전)" in judge["00126380"]["reasons"] and judge["00126380"]["ni_prev_won"] == 1000 * MIL
    assert all("deemed_payout_pct" in r for r in judge.values())  # 적자 간주 배당성향 칸
    assert judge["00126380"]["deemed_payout_pct"] is None
    mins = [r for r in ct.min_dividend_rows(companies, div, fin) if r["corp_code"] == "00126380"]
    assert [r["scenario"] for r in mins] == ["최근 3년 최저", "2025년 (기본)"]  # 2025 = 최고라 합침
    assert all(r["status"] == HOLD and r["min_won"] is None for r in mins)


# --- DB가 있을 때만: 작은 시험 데이터로 스키마·PK·FK 확인 (시험 전용 DB onepick_test) ---

TEST_URL = "postgresql://localhost/onepick_test"


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from core import db
    try:
        db.create_database(TEST_URL)
        c = db.connect(TEST_URL)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL에 연결할 수 없음")
    db.apply_schema(c)
    c.commit()
    yield c
    c.rollback()
    c.close()


def test_schema_loads_and_keys_hold(conn):
    from core import db
    from scripts.load_raw import tax_rate_rows

    companies = ct.company_rows(DF02, DF07, KIND)
    div = ct.dividend_year_rows(DF02, DECISIONS, CF, {c["corp_code"] for c in companies})
    fin = ct.financial_rows(DF02)
    db.replace_rows(conn, "core.core_company", companies)
    db.replace_rows(conn, "core.core_dividend_year", div)
    db.replace_rows(conn, "core.core_financial_year", fin)
    db.replace_rows(conn, "core.core_judgement_2026", ct.judgement_rows(companies, div, fin))
    db.replace_rows(conn, "core.core_min_dividend_2027", ct.min_dividend_rows(companies, div, fin))
    assert db.replace_rows(conn, "ref.tax_rate", tax_rate_rows()) == 12

    count = lambda t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
    assert count("core.core_company") == 2 and count("core.core_judgement_2026") == 2
    assert count("core.core_dividend_year") == len(div)
    conn.commit()

    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation):  # PK: 회사×사업연도 중복 금지
        conn.execute("INSERT INTO core.core_financial_year (corp_code, bsns_year, source) VALUES ('00126380', 2025, 'x')")
    conn.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # FK: core_company에 없는 회사 금지
        conn.execute("INSERT INTO core.core_financial_year (corp_code, bsns_year, source) VALUES ('99999999', 2025, 'x')")
    conn.rollback()


# --- KRX 주가·지수 (가로형 → 세로형) ---

PRICES = pd.DataFrame(
    {"126380": ["70000", None, "71000.5"], "00164779": ["", "150000", "151000"]},
    index=pd.Index(["2026-01-02", "2026-01-05", "2026-01-06"], name="날짜"),
)


def test_krx_prices_wide_to_long_skips_blanks():
    rows = rt.krx_prices(PRICES, "prices.csv")
    assert len(rows) == 4  # 빈칸 2개(None, "")는 행을 만들지 않음 (상장 전·거래정지)
    first = rows[0]
    assert (first["corp_code"], str(first["trade_date"]), first["close_adj"]) == ("00126380", "2026-01-02", Decimal("70000"))
    assert {r["corp_code"] for r in rows} == {"00126380", "00164779"}
    assert rows[1]["close_adj"] == Decimal("71000.5")


def test_krx_prices_rejects_bad_values():
    bad = PRICES.copy()
    bad.iloc[0, 0] = "0"  # 가격 0은 거래정지 잔재일 수 있어 받지 않음
    with pytest.raises(ValueError, match="1개"):
        rt.krx_prices(bad, "prices.csv")
    bad_date = PRICES.rename(index={"2026-01-02": "2026/01/02"})
    with pytest.raises(ValueError):
        rt.krx_prices(bad_date, "prices.csv")


def test_krx_market_index_reads_market_from_header():
    df = pd.DataFrame({"KOSPI 종가": ["2500.1", "2510.2"]}, index=pd.Index(["2026-01-02", "2026-01-05"], name="날짜"))
    rows = rt.krx_market_index(df, "market.csv")
    assert [r["market"] for r in rows] == ["KOSPI", "KOSPI"] and rows[1]["close"] == Decimal("2510.2")


def test_krx_tables_keys(conn):
    from core import db

    db.replace_rows(conn, "raw.krx_price_daily", rt.krx_prices(PRICES, "prices.csv"))
    conn.commit()
    assert conn.execute("SELECT count(*) FROM raw.krx_price_daily").fetchone()[0] == 4
    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation):  # PK: 회사×거래일 중복 금지
        conn.execute("INSERT INTO raw.krx_price_daily VALUES ('00126380', '2026-01-02', 1, 'x')")
    conn.rollback()


TARGETS = pd.DataFrame({"종목코드": ["005930", "0008Z0"], "corp_code": ["126380", "01294110"]})


def test_krx_day_status_maps_codes_from_target_list():
    status = pd.DataFrame({"종목코드": ["5930", "0008Z0"], "거래일": ["2026-01-05", "2026-01-02"],
                           "종가": ["70000.0", None], "상태": ["거래정지", "상장 전"]})
    rows = rt.krx_day_status(status, TARGETS, "일별상태.csv")
    assert [(r["corp_code"], r["stock_code"], r["status"]) for r in rows] == [
        ("00126380", "005930", "거래정지"), ("01294110", "0008Z0", "상장 전")]  # 영문 포함 코드도 제 회사로
    assert rows[0]["close_last"] == Decimal("70000.0") and rows[1]["close_last"] is None
    with pytest.raises(ValueError, match="대상목록에 없는"):
        rt.krx_day_status(status.assign(종목코드=["000080", "0008Z0"]), TARGETS, "일별상태.csv")


def test_price_views_grade_days(conn):
    from core import db
    from core import price_quality as pq

    prices = pd.DataFrame({"00126380": ["1000", "1000", "1000", "1000", "1000", "2000"]},
                          index=pd.Index(pd.bdate_range("2026-01-02", periods=6).strftime("%Y-%m-%d"), name="날짜"))
    status = pd.DataFrame({"종목코드": ["005930"], "거래일": ["2026-01-12"], "종가": ["2000"], "상태": ["거래정지"]})
    db.replace_rows(conn, "raw.krx_price_daily", rt.krx_prices(prices, "prices.csv"))
    db.replace_rows(conn, "core.core_price_flag", pq.price_flags(prices))
    db.replace_rows(conn, "raw.krx_day_status", rt.krx_day_status(status, TARGETS, "일별상태.csv"))
    conn.commit()
    got = conn.execute("SELECT trade_date::text, grade, reasons FROM core.v_price_daily ORDER BY 1").fetchall()
    assert [g for _, g, _ in got] == ["주의"] * 5 + ["제외", "제외"]
    assert got[5][2].startswith("상한 초과 등락: +100.0%") and got[6][2] == "빈칸: 거래정지"
    raw = conn.execute("SELECT count(*), sum(close_adj) FROM raw.krx_price_daily").fetchone()
    assert raw == (6, Decimal("7000"))  # 원본은 그대로


def test_analysis_data_reads_only_verified_period(conn):
    from core import analysis_data, db
    from core.event_study import UNVERIFIED, VERIFIED

    base = {"window_days": 20, "n_cases": 12, "median_pct": 1.5, "p25_pct": -1, "p75_pct": 2, "shown": True,
            "n_caution": 0, "n_excluded": 1, "engine": "t"}
    db.replace_rows(conn, "core.core_event_summary", [{"kind": "주당배당금 증가", "period": VERIFIED, **base},
                                                      {"kind": "주당배당금 증가", "period": UNVERIFIED, **base}])
    db.replace_rows(conn, "core.core_event_curve", [
        {"kind": "주당배당금 증가", "period": p, "window_days": 20, "day": 0, "n_cases": 12,
         "median_pct": 0.1, "p25_pct": 0, "p75_pct": 0.2, "engine": "t"} for p in (VERIFIED, UNVERIFIED)])
    conn.commit()
    res = analysis_data.load(TEST_URL)
    assert len(res.summary) == 1 and len(res.curve) == 1 and res.summary.loc[0, "median_pct"] == 1.5
    assert analysis_data.load("postgresql://localhost:1/none") is None  # 연결 실패 → 예시 화면


def test_verified_view_uses_source_values_and_restated_policy(conn):
    from core import db

    db.replace_rows(conn, "core.core_company", [{"corp_code": "00000009", "corp_name": "가", "stock_code": "000009",
                                                 "market": "코스피", "fiscal_month": 12, "source_file": "t"}])
    db.replace_rows(conn, "core.core_financial_year", [
        {"corp_code": "00000009", "bsns_year": y, "fs_basis": "연결", "ni_owner_won": 100, "liabilities_won": 200,
         "equity_won": 300, "unit": 1, "source": "t"} for y in (2023, 2024)])
    db.replace_rows(conn, "core.core_dart_fill", [])
    base = {"target": "core_financial_year", "corp_code": "00000009", "basis": "연결", "db_value": 0, "result": "불일치",
            "src_rcept_no": "1", "src_title": "t", "src_period": "", "engine": "t"}
    db.replace_rows(conn, "core.core_dart_verify", [
        {**base, "bsns_year": 2023, "item": "ni_owner_won", "src_value": 111, "check_result": "검산",
         "note": "DB 값은 1년 뒤 보고서 비교기간(재작성) 값과 같음"},
        {**base, "bsns_year": 2024, "item": "equity_won", "src_value": 333, "check_result": "검산",
         "note": "DB 값과 같은 원문 값을 찾지 못함"}])
    conn.execute("UPDATE core.core_setting SET value = 'original' WHERE key = 'restated_policy'")
    conn.commit()
    q = "SELECT bsns_year, ni_owner_won, equity_won, corrected_items FROM core.v_financial_year_verified " \
        "WHERE corp_code = '00000009' ORDER BY 1"
    rows = conn.execute(q).fetchall()
    assert rows[0][1] == 111 and "재작성 선택" in rows[0][3]
    assert rows[1][2] == 333 and "사람 확인" in rows[1][3]
    conn.execute("UPDATE core.core_setting SET value = 'restated' WHERE key = 'restated_policy'")
    rows = conn.execute(q).fetchall()
    assert rows[0][1] == 100 and rows[0][3] is None  # 재작성 값 유지 설정이면 DB 값 그대로
    assert conn.execute("SELECT ni_owner_won FROM core.core_financial_year WHERE corp_code = '00000009' "
                        "AND bsns_year = 2023").fetchone()[0] == 100  # 원본은 그대로
    conn.rollback()


def test_ecos_macro_keys(conn):
    from core import db, macro

    row = {"series": "usdkrw_d", "label": "원/미국달러(매매기준율)", "time": "20260102", "value": "1400.5",
           "value_raw": "1,400.5", "unit": "원", "stat_code": "731Y001", "stat_name": "3.1.1.1.",
           "item_code1": "0000001", "item_name1": "원/미국달러(매매기준율)", "item_code2": "", "item_name2": "", "cycle": "D"}
    db.replace_rows(conn, "raw.ecos_macro", macro.db_rows([row], "usdkrw_d.csv"))
    conn.commit()
    got = conn.execute("SELECT period_start::text, value FROM raw.ecos_macro").fetchone()
    assert got == ("2026-01-02", Decimal("1400.5"))
    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation):  # PK: 지표×시점 중복 금지
        conn.execute(
            "INSERT INTO raw.ecos_macro (series, time, period_start, cycle, label, stat_code, item_code1, source_file) "
            "VALUES ('usdkrw_d', '20260102', '2026-01-02', 'D', 'x', 'x', 'x', 'x')")
    conn.rollback()
