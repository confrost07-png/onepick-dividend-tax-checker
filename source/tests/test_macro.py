"""한국은행 ECOS 거시지표 받기 테스트: 여러 쪽 이어 받기, 값 정리."""
from decimal import Decimal

import pytest

from core import macro as m

CPI = m.Series("cpi_m", "소비자물가지수 총지수", "901Y009", "0", "M")


def _row(time, value):
    return {"STAT_CODE": "901Y009", "STAT_NAME": "4.2.1. 소비자물가지수", "ITEM_CODE1": "0", "ITEM_NAME1": "총지수",
            "ITEM_CODE2": None, "ITEM_NAME2": None, "UNIT_NAME": "2020=100", "TIME": time, "DATA_VALUE": value}


def test_fetch_pages_until_total():
    pages = [[_row("201801", "1,000.5"), _row("201802", "-")], [_row("201803", "3")]]
    calls = []

    def get(address):
        calls.append(address)
        return {"StatisticSearch": {"list_total_count": 3, "row": pages[len(calls) - 1]}}

    m.PAGE, page = 2, m.PAGE
    try:
        rows = m.fetch("KEY", CPI, get=get)
    finally:
        m.PAGE = page
    assert [r["time"] for r in rows] == ["201801", "201802", "201803"]
    assert rows[0]["value"] == Decimal("1000.5") and rows[0]["value_raw"] == "1,000.5"
    assert rows[1]["value"] is None
    assert "/1/2/901Y009/M/201601/202610/0/?" in calls[0] and "/3/4/" in calls[1]


def test_fetch_error_hides_nothing_but_key():
    def get(address):
        return {"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}}

    with pytest.raises(RuntimeError) as e:
        m.fetch("SECRET", CPI, get=get)
    assert "INFO-100" in str(e.value) and "SECRET" not in str(e.value)


def test_api_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv(m.KEY_NAME, raising=False)
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nexport ECOS_API_KEY='abc'\n", encoding="utf-8")
    assert m.api_key([env]) == "abc"
    assert m.api_key([tmp_path / "없음"]) is None


def test_period_start_by_cycle():
    from datetime import date

    assert m.period_start("20260102", "D") == date(2026, 1, 2)
    assert m.period_start("202609", "M") == date(2026, 9, 1)
    assert m.period_start("2026Q3", "Q") == date(2026, 7, 1)


def test_db_rows_keeps_raw_and_blanks_as_null():
    csv_row = {"series": "cpi_m", "label": "소비자물가지수 총지수", "time": "201801", "value": "98.106",
               "value_raw": "98.106", "unit": "2020=100", "stat_code": "901Y009", "stat_name": "4.2.1. 소비자물가지수",
               "item_code1": "0", "item_name1": "총지수", "item_code2": "", "item_name2": "", "cycle": "M"}
    row = m.db_rows([csv_row], "cpi_m.csv")[0]
    assert row["value"] == Decimal("98.106") and row["value_raw"] == "98.106"
    assert row["item_code2"] is None and row["source_file"] == "cpi_m.csv"
