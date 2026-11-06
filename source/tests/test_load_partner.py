"""4조참치 자료 → partner 스키마 (source/scripts/load_partner.py). 단위 풀이는 DB 없이, 적재는 시험 DB가 있을 때만."""
import pytest

from scripts import load_partner as lp
from tests.test_partner_workbook import make_src

TEST_URL = "postgresql://localhost/onepick_test"


def test_unit_factor_and_base_date():
    assert lp.unit_factor("(단위 : 주) [1]") == 1
    assert lp.unit_factor("(단위 : 천주, %) [2]") == 1_000
    assert lp.unit_factor("(단위 : 백만 주) [3]") == 1_000_000
    assert lp.unit_factor(None) == 1
    assert lp.base_date("2024년 12월 31일 [20241231] (단위 : 주) [1]") == "20241231" and lp.base_date("") is None


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
    yield c
    c.rollback()
    c.close()


def test_load_fills_partner_tables(conn, tmp_path):
    from core import db
    counts = lp.load(conn, make_src(tmp_path), {"00000001"}, log=lambda *_: None)
    assert counts["partner.company"] == 2 and counts["partner.report"] == 3
    q = lambda s: db.fetch_dicts(conn, s)
    assert q("SELECT corp_code, grp FROM partner.company ORDER BY 1") == [{"corp_code": "00000001", "grp": "겹침"},
                                                                         {"corp_code": "00000002", "grp": "대조군"}]
    fin = q("SELECT * FROM partner.financial_year WHERE corp_code='00000002' AND bsns_year=2023")[0]
    assert (fin["ni_owner_won"], fin["liabilities_won"], fin["fs_basis"], fin["ni_status"]) == (50, 100, "연결", "값 있음")
    div = q("SELECT * FROM partner.dividend_year WHERE corp_code='00000002' AND bsns_year=2023")[0]
    assert (div["d_won"], div["dps_common_won"], div["cf_paid_won"], div["nci_paid_won"]) == (1_200_000_000, 100, 30, 5)
    assert q("SELECT d_status FROM partner.dividend_year WHERE corp_code='00000002' AND bsns_year=2025")[0]["d_status"] == \
        "실재하지만 불러올 수 없음"
    share = q("SELECT se, share_class, ever_issued, decreased, stlm_dt, unit_factor FROM partner.share_total "
              "WHERE status='값 있음' ORDER BY se")
    assert [(r["se"], r["share_class"], r["ever_issued"], r["decreased"], r["stlm_dt"]) for r in share] == \
        [("보통주", "보통", 1000, 100, "20241231"), ("합계", "합계", 1000, 100, "20241231")]
    hold = q("SELECT nm, trmend_shares, trmend_pct, is_total FROM partner.major_holder WHERE status='값 있음' ORDER BY seq")
    assert [(r["nm"], r["trmend_shares"], r["trmend_pct"], r["is_total"]) for r in hold] == [("홍길동", 20, 3, False), ("계", 20, 3, True)]
    assert q("SELECT count(*) n FROM partner.dividend_item WHERE item='현금배당금총액(백만원)'")[0]["n"] == 3
    assert q("SELECT count(*) n FROM partner.fs_line WHERE sj_div='CF'")[0]["n"] == 3
    assert q("SELECT count(*) n FROM partner.filing WHERE pblntf_ty='I'")[0]["n"] == 3
    again = lp.load(conn, make_src(tmp_path / "again"), {"00000001"}, log=lambda *_: None)
    assert again == counts  # 다시 돌리면 비우고 새로 채움


def test_panel_view_has_ours_and_control_without_duplicates(conn, tmp_path):
    from core import db
    lp.load(conn, make_src(tmp_path / "panel"), {"00000001"}, log=lambda *_: None)
    db.replace_rows(conn, "core.core_company", [{"corp_code": "00000001", "corp_name": "겹침", "stock_code": "000001",
                                                 "market": "코스피", "fiscal_month": 12, "source_file": "t"}])
    db.replace_rows(conn, "core.core_financial_year", [{"corp_code": "00000001", "bsns_year": 2024, "fs_basis": "연결",
                                                       "ni_owner_won": 7, "liabilities_won": 8, "equity_won": 9, "unit": 1, "source": "t"}])
    q = lambda s: db.fetch_dicts(conn, s)  # noqa: E731
    rows = q("SELECT source, corp_code, bsns_year, ni_owner_won, ni_status FROM partner.v_panel ORDER BY source, corp_code, bsns_year")
    ours = [r for r in rows if r["source"] == "우리 638사"]
    assert ours == [{"source": "우리 638사", "corp_code": "00000001", "bsns_year": 2024, "ni_owner_won": 7, "ni_status": "확정"}]
    control = [r for r in rows if r["source"] == "4조 대조군"]
    assert {r["corp_code"] for r in control} == {"00000002"} and len(control) == 9  # 겹침 회사는 4조 쪽에서 빠짐
    assert next(r for r in control if r["bsns_year"] == 2023)["ni_owner_won"] == 50
    conn.rollback()
