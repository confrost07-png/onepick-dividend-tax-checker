"""OpenDART 결측 보완: 가짜 응답(core.sources.samples)으로 인터넷·키 없이 검사한다."""
import pytest

from core.sources.base import API_ERROR, FROM_ORIGINAL, NO_DATA, OK, UNVERIFIED, Client, LimitReached, to_number
from core.sources.opendart import (
    ACCOUNTS,
    Dart,
    DartKeyError,
    find_account,
    find_in_tables,
    match_stock_codes,
    pick_dividend,
    table_rows,
)
from core.sources import samples
from core.sources.samples import CORP, DECISION_RCEPT, VALUEUP_RCEPT

import pandas as pd


@pytest.fixture
def dart():
    return Dart(key="test-key", client=Client(fetch=samples.fake_dart_fetch))


def test_statement_falls_back_to_separate_when_consolidated_missing(dart):
    got = dart.statement(CORP, 2024)
    assert got.status == OK and set(got.value["fs_div"]) == {"OFS"}
    assert got.attempts[0].startswith("연결 013")


def test_account_by_name_when_account_id_is_custom(dart):
    got = dart.account(CORP, 2024, "당기순이익_전체")
    assert (got.value, got.status) == (4_800_000_000, OK)
    assert "계정 이름 일치" in got.source.note and got.source.rcept_no == "20250315000111"


def test_owner_net_income_is_never_taken_from_separate_statement(dart):
    # 재무회계 검토: 지배주주순이익은 연결에서만. 별도 당기순이익으로 대체하지 않는다
    got = dart.account(CORP, 2024, "지배주주순이익")
    assert got.value is None and got.status == UNVERIFIED
    assert not any("별도" in a for a in got.attempts)
    only_ofs = dart.account(CORP, 2024, "지배주주순이익", fs_divs=("OFS",))
    assert only_ofs.status == UNVERIFIED and "연결재무제표에서만" in only_ofs.source.note


def test_dividends_paid_is_separate_only_and_absolute(dart):
    got = dart.account(CORP, 2024, "배당금지급_지급기준")
    assert got.value == 1_500_000_000 and "절댓값" in got.source.note
    assert dart.account(CORP, 2024, "배당금지급_지급기준", fs_divs=("CFS",)).status == UNVERIFIED


def test_owner_equity_is_not_replaced_by_total_equity(dart):
    assert dart.account(CORP, 2024, "지배주주자본").value is None


def test_account_falls_back_to_next_year_prior_period(dart):
    got = dart.account(CORP, 2023, "당기순이익_전체")
    assert got.value == 3_900_000_000
    assert "2024 사업보고서의 전기 값" in got.source.note


def test_negative_in_parentheses():
    assert to_number("(1,500,000,000)") == -1_500_000_000


def test_account_unverified_when_all_paths_empty(dart):
    got = dart.account(CORP, 2020, "부채총계")
    assert got.value is None and got.status == UNVERIFIED
    assert len(got.attempts) >= 4  # 연결·별도·주요계정·다음 해까지 시도


def test_dividend_dash_falls_back_to_next_year_prior(dart):
    got = dart.dividend_item(CORP, 2024, "현금배당금총액")
    assert (got.value, got.unit, got.won) == (1_400, 1_000_000, 1_400_000_000)
    assert "2025 사업보고서의 전기 값" in got.source.note


def test_dividend_picks_common_stock_row(dart):
    assert dart.dividend_item(CORP, 2025, "주당현금배당금").value == 500
    assert dart.dividend_item(CORP, 2025, "주당현금배당금", stock_knd="우선주").value == 505


def test_dividend_separate_basis_noted(dart):
    borrowed = dart.dividend_item(CORP, 2025, "현금배당성향", strict_basis=False)
    assert borrowed.value == 30.0 and "연결 값이 없어 별도" in borrowed.source.note
    assert dart.dividend_item(CORP, 2025, "현금배당성향").value is None  # 기본은 빌려 쓰지 않음


def test_dividend_all_dash_is_no_data_not_zero(dart):
    # 2023 보고서는 없고, 2024 보고서 전기 1,200 → 찾음. 전전기만 '-'인 경우를 직접 확인
    df = pd.DataFrame([{"se": "현금배당금총액(백만원)", "stock_knd": "", "thstrm": "-"}])
    pick = pick_dividend(df, "현금배당금총액")
    assert pick["status"] == NO_DATA and pick["value"] is None


def test_dividend_conflicting_rows_unverified():
    df = pd.DataFrame([
        {"se": "현금배당금총액(백만원)", "stock_knd": "", "thstrm": "100"},
        {"se": "현금배당금총액(백만원)", "stock_knd": "", "thstrm": "120"},
    ])
    assert pick_dividend(df, "현금배당금총액")["status"] == UNVERIFIED


def test_find_account_conflict_returns_none():
    df = pd.DataFrame([
        {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "10"},
        {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "11"},
    ])
    assert find_account(df, ACCOUNTS["자본총계"]) is None


def test_disclosures_pages_and_keywords(dart):
    got = dart.disclosures("20250101", "20261020", corp_code=CORP, keywords=("현금현물배당결정", "기업가치제고계획"))
    assert list(got.value["rcept_no"]) == [DECISION_RCEPT, VALUEUP_RCEPT]
    assert list(got.value["정정"]) == [False, True]


def test_disclosures_without_corp_split_by_quarter():
    seen = []

    def fetch(url, params):
        seen.append((params["bgn_de"], params["end_de"]))
        return samples.NO_DATA

    d = Dart(key="k", client=Client(fetch=fetch))
    got = d.disclosures("20250101", "20251231")
    assert got.status == NO_DATA
    assert seen == [("20250101", "20250331"), ("20250401", "20250630"), ("20250701", "20250930"), ("20251001", "20251231")]


def test_dividend_decision_from_original_tables(dart):
    got = dart.dividend_decision(DECISION_RCEPT)
    assert got["1주당배당금"].value == 1500 and got["1주당배당금"].status == FROM_ORIGINAL
    assert got["배당금총액"].value == 1_512_345_000
    assert got["시가배당율"].value == 3.2
    assert got["배당기준일"].value == "2025-12-31"
    assert "dsaf001" in got["배당금총액"].source.url


def test_missing_original_points_to_viewer(dart):
    got = dart.document(VALUEUP_RCEPT)
    assert got.status == NO_DATA and VALUEUP_RCEPT in got.source.url


def test_share_counts_computes_float_shares(dart):
    got = dart.share_counts(CORP, 2025)
    assert got["발행주식총수"].value == 1_000_000
    assert got["유통주식수"].value == 992_000 and "계산" in got["유통주식수"].source.note


def test_largest_holder_sum_when_no_total_row(dart):
    got = dart.largest_holder_stake(CORP, 2025)
    assert got.value == 35.35 and "개별 2행 합계" in got.source.note


def test_corp_codes_and_zero_padding(dart):
    codes = dart.corp_codes()
    m = match_stock_codes(codes, [12345, "A067890", "999999"])
    assert list(m["corp_code"][:2]) == [CORP, "00000002"] and pd.isna(m["corp_code"][2])
    assert list(m["상태"]) == [OK, OK, UNVERIFIED]


def test_limit_stops_and_is_not_cached(tmp_path):
    d = Dart(key="k", client=Client(fetch=lambda u, p: samples.LIMIT, cache_dir=tmp_path))
    with pytest.raises(LimitReached):
        d.dividends(CORP, 2025)
    assert not list(tmp_path.rglob("*.bin"))


def test_key_error_stops():
    d = Dart(key="k", client=Client(fetch=lambda u, p: b'{"status":"010","message":"x"}'))
    with pytest.raises(DartKeyError):
        d.dividends(CORP, 2025)


def test_maintenance_is_api_error_not_no_data():
    d = Dart(key="k", client=Client(fetch=lambda u, p: b'{"status":"800","message":"maintenance"}'))
    assert d.dividends(CORP, 2025).status == API_ERROR


def test_table_rows_reads_dart_and_html_cells():
    rows = table_rows("<table><tr><th>항목</th><td>1,000</td></tr><TR><TD>a</TD><TE>&lt;b&gt;</TE></TR></table>")
    assert rows == [["항목", "1,000"], ["a", "<b>"]]


def test_find_in_tables_conflict_is_unverified():
    files = {"a.xml": "<tr><td>배당금총액(원)</td><td>100</td></tr>", "b.xml": "<tr><td>배당금총액(원)</td><td>200</td></tr>"}
    assert find_in_tables(files, "배당금총액").status == UNVERIFIED


def test_no_data_answer_is_remembered_within_run(tmp_path):
    client = Client(fetch=samples.fake_dart_fetch, cache_dir=tmp_path)
    d = Dart(key="k", client=client)
    for item in ("당기순이익_전체", "부채총계", "자본총계"):
        d.account(CORP, 2024, item)
    first = client.calls
    d.account(CORP, 2024, "배당금지급_지급기준")
    assert client.calls == first  # 연결 013·별도 표 모두 다시 묻지 않음
    # 013은 파일로 남기지 않는다(나중에 공시가 올라오면 다시 받아야 하므로)
    new = Dart(key="k", client=Client(fetch=samples.fake_dart_fetch, cache_dir=tmp_path))
    new.statement(CORP, 2024)
    assert new.client.calls == 1


def test_consolidated_only_does_not_fall_back_to_separate(dart):
    got = dart.account(CORP, 2024, "당기순이익_전체", fs_divs=("CFS",))
    assert got.value is None and got.status == UNVERIFIED
    assert not any("별도" in a for a in got.attempts)


def test_separate_only(dart):
    got = dart.account(CORP, 2024, "당기순이익_전체", fs_divs=("OFS",))
    assert got.value == 4_800_000_000 and got.source.note.startswith("별도")


def test_strict_basis_dividend_does_not_borrow_other_basis(dart):
    assert dart.dividend_item(CORP, 2025, "현금배당성향", basis="연결", strict_basis=True).value is None
    assert dart.dividend_item(CORP, 2025, "현금배당성향", basis="별도", strict_basis=True).value == 30.0
    # 기준 표시가 없는 항목은 어느 쪽이든 같은 값
    assert dart.dividend_item(CORP, 2025, "주당현금배당금", basis="연결", strict_basis=True).value == 500


# --- 감사보고서 원문 ---

from core.sources.opendart import MATCH, cross_check, parse_financial_statements  # noqa: E402
from core.sources.samples import AUDIT_2024, CORP2  # noqa: E402


def test_audit_statement_reads_units_note_column_and_two_amount_columns(dart):
    st = dart.audit_statement(CORP, 2024, "OFS")
    assert st.status == FROM_ORIGINAL and st.source.rcept_no == AUDIT_2024
    df = st.value.set_index("account_nm")
    assert df.loc["부채총계", "thstrm_amount"] == 10_000_000_000  # 천원 × 1,000, 주석 '4,5'는 빠짐
    assert df.loc["부채총계", "frmtrm_amount"] == 9_000_000_000
    assert set(st.value["sj_div"]) == {"BS", "IS", "CF"}
    assert (st.value["account_nm"] == "부채총계").sum() == 1  # 주석 표는 읽지 않음


def test_audit_account_matches_api_and_flags_mismatch(dart):
    a = dart.audit_account(CORP, 2024, "당기순이익_전체", "OFS")
    assert (a.value, a.status) == (4_800_000_000, FROM_ORIGINAL)
    assert cross_check(a, dart.account(CORP, 2024, "당기순이익_전체", fs_divs=("OFS",))) == MATCH
    eq = dart.audit_account(CORP, 2025, "자본총계", "OFS")
    assert cross_check(eq, dart.account(CORP, 2025, "자본총계", fs_divs=("OFS",))).startswith("불일치")


def test_audit_dividends_paid_absolute(dart):
    got = dart.audit_account(CORP, 2024, "배당금지급_지급기준", "OFS")
    assert got.value == 1_500_000_000 and "절댓값" in got.source.note


def test_audit_missing_year_uses_next_year_prior_column(dart):
    got = dart.audit_account(CORP, 2023, "당기순이익_전체", "OFS")
    assert got.value == 3_900_000_000 and "2024 감사보고서의 전기 값" in got.source.note


def test_no_consolidated_audit_report_is_no_data_not_separate(dart):
    got = dart.audit_account(CORP, 2025, "부채총계", "CFS")
    assert got.value is None and "연결 미작성 회사일 수 있음" in got.source.note


def test_consolidated_audit_skips_comprehensive_income_owner_row(dart):
    got = dart.audit_account(CORP2, 2025, "지배주주순이익", "CFS")
    assert got.value == 1_700_000_000  # 총포괄이익 귀속 '지배기업 소유주지분'(1,850)이 아님
    assert dart.audit_account(CORP2, 2025, "지배주주자본", "CFS").value == 11_000_000_000
    assert dart.account(CORP2, 2025, "지배주주순이익", fs_divs=("CFS",)).value == 1_700_000_000


def test_cross_check_tolerates_table_rounding():
    from core.sources.base import Fetched, Source
    audit = Fetched(1_000_000_000, FROM_ORIGINAL, Source("감사보고서", {"표 단위": 1_000}))
    assert cross_check(audit, Fetched(1_000_000_400, OK)) == MATCH
    assert cross_check(audit, Fetched(1_000_001_000, OK)).startswith("불일치")
    assert cross_check(audit, Fetched(None, NO_DATA)) == "API 값 없음"


def test_odd_amount_columns_left_empty():
    xml = ("<P>재무상태표</P><P>(단위 : 원)</P><table><tr><td>과목</td><td>당기</td><td>전기</td><td>?</td></tr>"
           "<tr><td>부채총계</td><td>1</td><td>2</td><td>3</td></tr></table>")
    df = parse_financial_statements({"a.xml": xml})
    assert df["thstrm_amount"].isna().all()


def test_unknown_unit_is_unverified():
    xml = "<P>재무상태표</P><table><tr><td>과목</td><td>당기</td><td>전기</td></tr><tr><td>부채총계</td><td>1</td><td>2</td></tr></table>"
    df = parse_financial_statements({"a.xml": xml})
    assert df["unit"].isna().all() and df["thstrm_amount"].isna().all()
