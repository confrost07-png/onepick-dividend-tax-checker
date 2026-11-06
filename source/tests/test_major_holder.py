"""최대주주 현황(OpenDART hyslrSttus): 응답 → 행, 지분율 합계·개인/법인 규칙, 기준선 근처 비교. 실제 API는 부르지 않는다."""
from decimal import Decimal

import pandas as pd
import pytest

from core import holder_analysis as ha
from core import major_holder as mh
from core import share_total as st

OK = {"status": "000", "message": "정상", "list": [
    {"rcept_no": "20260310000001", "stock_knd": "보통주", "nm": "가나㈜", "relate": "최대주주 본인",
     "bsis_posesn_stock_co": "1,000", "bsis_posesn_stock_qota_rt": "10.00",
     "trmend_posesn_stock_co": "1,200", "trmend_posesn_stock_qota_rt": "12.00", "rm": "-", "stlm_dt": "2025-12-31"},
    {"rcept_no": "20260310000001", "stock_knd": "보통주", "nm": "홍길동", "relate": "최대주주의 특수관계인",
     "bsis_posesn_stock_co": "500", "bsis_posesn_stock_qota_rt": "5.00",
     "trmend_posesn_stock_co": "-", "trmend_posesn_stock_qota_rt": "-", "rm": "매도", "stlm_dt": "2025-12-31"},
    {"rcept_no": "20260310000001", "stock_knd": "우선주", "nm": "홍길동", "relate": "최대주주의 특수관계인",
     "bsis_posesn_stock_co": "50", "bsis_posesn_stock_qota_rt": "1.00",
     "trmend_posesn_stock_co": "50", "trmend_posesn_stock_qota_rt": "1.00", "rm": "-", "stlm_dt": "2025-12-31"},
    {"rcept_no": "20260310000001", "stock_knd": "보통주", "nm": "계",
     "bsis_posesn_stock_co": "1,500", "bsis_posesn_stock_qota_rt": "15.00",
     "trmend_posesn_stock_co": "1,200", "trmend_posesn_stock_qota_rt": "12.00", "rm": "-", "stlm_dt": "2025-12-31"},
]}


def test_rows_keep_raw_text_and_read_numbers():
    rows = mh.rows_from_response("00126380", 2025, "11011", OK)
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]
    top, person, pref, total = rows
    assert (top["trmend_shares"], top["trmend_pct"]) == (Decimal(1200), Decimal("12.00"))
    assert person["trmend_shares"] is None and person["trmend_shares_raw"] == "-"  # '-'는 0이 아니라 빈칸
    assert pref["share_class"] == st.PREF and total["relate"] is None
    assert all(r["api_status"] == "000" and r["rcept_no"] == "20260310000001" for r in rows)


def test_no_data_response_leaves_one_row():
    rows = mh.rows_from_response("00126380", 2025, "11011", {"status": "013", "message": "조회된 데이타가 없습니다."})
    assert len(rows) == 1 and rows[0]["nm"] == st.NO_ROW and rows[0]["api_status"] == "013"
    h = mh.summarize(rows)
    assert (h.pct_common, h.pct_source, h.largest_kind) == (None, "자료 없음", None)


def test_summarize_prefers_total_row_and_skips_preferred():
    h = mh.summarize(mh.rows_from_response("x", 2025, "11011", OK))
    assert h.pct_common == Decimal("12.00") and h.pct_source == "'계' 행"
    assert (h.largest_kind, h.largest_rule, h.n_rows) == (mh.CORP, "관계 칸", 2)


def test_summarize_sums_common_rows_without_total():
    rows = [r for r in mh.rows_from_response("x", 2025, "11011", OK) if r["nm"] != "계"]
    rows[1] = {**rows[1], "trmend_pct": Decimal("3.5")}
    h = mh.summarize(rows)
    assert h.pct_common == Decimal("15.5") and h.pct_source == "행 합계"  # 우선주 1.00은 더하지 않음


def test_largest_falls_back_to_biggest_stake():
    rows = [{"nm": "김철수", "relate": "특수관계인", "share_class": st.COMMON, "trmend_pct": Decimal(3), "trmend_shares": None},
            {"nm": "이영희", "relate": "특수관계인", "share_class": st.COMMON, "trmend_pct": Decimal(20), "trmend_shares": None}]
    h = mh.summarize(rows)
    assert (h.largest_kind, h.largest_rule) == (mh.PERSON, "지분 가장 큰 행")


def test_largest_relate_names():
    for rel in ("최대주주", "최대주주 본인", "본인", "最大株主", "本人", "최대주주(본인)", "최대주주 법인"):
        assert mh.is_largest(rel), rel
    for rel in ("최대주주의 특수관계인", "특수관계인", "계열회사", None):
        assert not mh.is_largest(rel), rel


def test_holder_kind_rules():
    for nm in ("삼성생명보험㈜", "SK스퀘어(주)", "주식회사 가나", "삼성문화재단", "국민연금공단", "ABC Holdings Ltd.", "가나홀딩스",
               "삼성SDI", "가나전자", "LG화학"):
        assert mh.holder_kind(nm) == mh.CORP, nm
    assert mh.holder_kind("가나다", "계열회사") == mh.CORP
    for nm in ("홍길동", "남궁민수", "홍 길 동", "홍길동(주2)"):
        assert mh.holder_kind(nm, "최대주주 본인") == mh.PERSON, nm
    for nm in ("John Smith", "홍", "", None, "네오크레마", "나카지마히로카즈"):
        assert mh.holder_kind(nm) == mh.UNKNOWN, nm


def test_groups_use_plus_minus_band():
    rates = {"a": (22.0, None), "b": (28.0, 50.0), "c": (28.1, 13.0), "d": (40.0, 10.0), "e": (60.0, 30.0),
             "f": (None, None), "g": (None, 6.9)}
    g = ha.groups(rates)
    assert g["배당성향 25% 근처"] == {"a", "b"}
    assert g["배당성향 40% 근처"] == {"d"} and g["증가율 10% 근처"] == {"c", "d"}
    assert g[ha.NEAR_ANY] == {"a", "b", "c", "d"} and g[ha.REST] == {"e", "g"}  # f는 둘 다 없어 빠짐


def test_compare_hides_groups_under_ten_cases():
    rates = {f"n{i}": (25.0, None) for i in range(10)} | {f"r{i}": (70.0, None) for i in range(9)}
    holders = {f"n{i}": (float(i * 10), mh.PERSON if i < 3 else mh.CORP) for i in range(10)}
    holders |= {f"r{i}": (50.0, mh.CORP) for i in range(9)}
    t = ha.compare(rates, holders).set_index("묶음")
    near = t.loc["배당성향 25% 근처"]
    assert near["표시"] and near["지분 자료"] == 10 and near["중앙값"] == 45.0
    assert (near["1사분위"], near["3사분위"], near["개인 최대주주(%)"]) == (22.5, 67.5, 30.0)
    rest = t.loc[ha.REST]
    assert not rest["표시"] and rest["회사 수"] == 9 and pd.isna(rest["중앙값"])


# --- DB가 있을 때만: raw → core 만들기 (시험 전용 DB onepick_test) ---

TEST_URL = "postgresql://localhost/onepick_test"
FAKE = "T0000001"


def test_build_writes_core_without_names():
    psycopg = pytest.importorskip("psycopg")
    from core import db
    from scripts import collect_major_holder as cmh
    try:
        db.create_database(TEST_URL)
        conn = db.connect(TEST_URL)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL에 연결할 수 없음")
    with conn:
        db.apply_schema(conn)
        conn.execute("DELETE FROM raw.dart_major_holder WHERE corp_code = %s", (FAKE,))
        cmh._insert(conn, "raw.dart_major_holder", cmh.COLS,
                    [[r[c] for c in cmh.COLS] for r in mh.rows_from_response(FAKE, 2099, "11011", OK)])
    try:
        cmh.build(TEST_URL, 2099)
        with db.connect(TEST_URL) as c:
            got = db.fetch_dicts(c, "SELECT * FROM core.core_major_holder WHERE corp_code = %s", (FAKE,))
        assert len(got) == 1
        r = got[0]
        assert (r["pct_common"], r["pct_source"], r["largest_kind"], r["n_rows"]) == (Decimal("12.00"), "'계' 행", mh.CORP, 2)
        assert "가나" not in " ".join(str(v) for v in r.values())  # core에는 이름을 남기지 않음
    finally:
        with db.connect(TEST_URL) as c:
            c.execute("DELETE FROM raw.dart_major_holder WHERE corp_code = %s", (FAKE,))
            c.execute("DELETE FROM core.core_major_holder WHERE corp_code = %s", (FAKE,))
