"""4조 대조군 주가 받기 (source/scripts/collect_partner_prices.py): 응답 읽기."""
from datetime import date

from scripts import collect_partner_prices as cp

SAMPLE = '''<?xml version="1.0" encoding="EUC-KR" ?><protocol><chartdata symbol="005500" name="삼진제약">
<item data="20171229|20000|20500|19800|20300|12345" />
<item data="20180102|20300|20600|20100|20450|23456" />
<item data="20180103|20450|20450|20450|0|0" />
</chartdata></protocol>'''


def test_parse_reads_adjusted_close_and_skips_empty():
    assert cp.parse(SAMPLE) == [(date(2017, 12, 29), 20300.0, 12345), (date(2018, 1, 2), 20450.0, 23456)]


def test_rows_start_at_our_price_start():
    rows = list(cp.rows_for({"corp_code": "00000001"}, SAMPLE))
    assert [r["trade_date"] for r in rows] == [date(2018, 1, 2)] and rows[0]["close_adj"] == 20450.0
