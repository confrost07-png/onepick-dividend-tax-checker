"""주식의 총수 현황(OpenDART stockTotqySttus): 숫자 읽기, 응답 → 행, 키 찾기. 실제 API는 부르지 않는다."""
from decimal import Decimal

from core import share_total as st


def test_number_reads_commas_dash_and_parentheses():
    assert st.number("1,234,567") == Decimal("1234567")
    assert st.number(" 100 ") == Decimal("100")
    assert st.number("(1,000)") == Decimal("-1000")
    assert st.number("-") is None
    assert st.number("") is None
    assert st.number(None) is None
    assert st.number("해당없음") is None


OK = {"status": "000", "message": "정상", "list": [
    {"rcept_no": "20260310000001", "corp_code": "00126380", "se": "보통주", "istc_totqy": "1,000",
     "tesstk_co": "100", "distb_stock_co": "900", "stlm_dt": "2025-12-31"},
    {"rcept_no": "20260310000001", "corp_code": "00126380", "se": "우선주", "istc_totqy": "200",
     "tesstk_co": "-", "distb_stock_co": "-", "stlm_dt": "2025-12-31"},
    {"rcept_no": "20260310000001", "corp_code": "00126380", "se": "합계", "istc_totqy": "1,200",
     "tesstk_co": "50", "distb_stock_co": "-", "stlm_dt": "2025-12-31"},
]}


def test_rows_keep_values_and_fill_float_only_when_blank():
    rows = st.rows_from_response("00126380", 2025, "11011", OK)
    assert [r["se"] for r in rows] == ["보통주", "우선주", "합계"]
    common, pref, total = rows
    assert (common["issued"], common["treasury"], common["floating"]) == (1000, 100, 900)
    assert common["floating_note"] is None
    # 자기주식이 '-'면 유통주식수를 계산하지 않는다(0으로 채우지 않음)
    assert pref["treasury"] is None and pref["floating"] is None
    # 유통이 비고 발행·자기가 있으면 발행 − 자기, 메모를 남긴다
    assert total["floating"] == 1150 and "발행 − 자기" in total["floating_note"]
    assert total["floating_raw"] == "-"
    assert common["rcept_no"] == "20260310000001" and common["stlm_dt"] == "2025-12-31"
    assert all(r["api_status"] == "000" for r in rows)


def test_share_class_groups_company_specific_names():
    for se in ("보통주", "보통주식", "기명식보통주", "의결권 있는 주식\n(보통주)", "보통주(의결권 있는 주식)", "의결권있는 주식"):
        assert st.share_class(se) == st.COMMON, se
    for se in ("우선주", "종류주식", "의결권 없는 주식", "의결권이 없는주식(우선주)", "의결권 없는 주식(종류주식)",
               "배당우선 상환주식(3종 종류주식)", "1종 종류주(우선주식)", "무의결권부우선주", "전환상환우선주"):
        assert st.share_class(se) == st.PREF, se
    assert st.share_class("합계") == st.TOTAL and st.share_class("비고") == st.NOTE
    for se in ("기타주식", "보통주 외", "유통주식"):
        assert st.share_class(se) == st.OTHER, se
    rows = st.rows_from_response("00126380", 2025, "11011", OK)
    assert [r["share_class"] for r in rows] == [st.COMMON, st.PREF, st.TOTAL]


def test_no_data_response_leaves_one_row_with_reason():
    rows = st.rows_from_response("00126380", 2025, "11011", {"status": "013", "message": "조회된 데이타가 없습니다."})
    assert len(rows) == 1
    r = rows[0]
    assert r["se"] == st.NO_ROW and r["api_status"] == "013" and r["issued"] is None
    assert "조회된 데이타가 없습니다" in r["api_message"]


def test_api_key_prefers_environment(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nDART_API_KEY='from-file'\n", encoding="utf-8")
    monkeypatch.setenv("DART_API_KEY", "from-env")
    assert st.api_key([env]) == "from-env"
    monkeypatch.delenv("DART_API_KEY")
    assert st.api_key([tmp_path / "없음.env", env]) == "from-file"
    assert st.api_key([tmp_path / "없음.env"]) is None


def test_api_key_also_reads_opendart_name(monkeypatch, tmp_path):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENDART_API_KEY=open-key\n", encoding="utf-8")
    assert st.api_key([env]) == "open-key"
    env.write_text("OPENDART_API_KEY=open-key\nDART_API_KEY=dart-key\n", encoding="utf-8")
    assert st.api_key([env]) == "dart-key"
    monkeypatch.setenv("OPENDART_API_KEY", "env-open")
    assert st.api_key([env]) == "env-open"


def test_cache_name_never_contains_key():
    path = st.cache_path("00126380", 2025, "11011")
    assert path.name == "00126380_2025_11011.json"
