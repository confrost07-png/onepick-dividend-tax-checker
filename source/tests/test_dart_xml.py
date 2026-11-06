"""사업보고서 원문 XML 정형 표 읽기 (source/core/dart_xml.py)."""
from core import dart_xml as dx

DIVIDEND = """<TITLE ATOC="Y">6. 배당에 관한 사항 등</TITLE>
<TABLE-GROUP ACLASS="DIVIDEND"><TABLE><THEAD>
<TR><TH ROWSPAN="2">구 분</TH><TH ROWSPAN="2">주식의 종류</TH><TH>당기</TH><TH>전기</TH><TH>전전기</TH></TR>
<TR><TH>제10기</TH><TH>제9기</TH><TH>제8기</TH></TR></THEAD><TBODY>
<TR><TD COLSPAN="2">현금배당금총액(백만원)</TD><TE ACODE="X24">1,200</TE><TE ACODE="X24">-</TE><TE ACODE="X24">(30)</TE></TR>
<TR><TD ROWSPAN="2">주당 현금배당금(원)</TD><TE ACODE="XQ3">보통주</TE><TE ACODE="X33">100</TE><TE>-</TE><TE>50</TE></TR>
<TR><TE ACODE="XQ3">우선주</TE><TE ACODE="X33">110</TE><TE>-</TE><TE>-</TE></TR>
<TR><TD>현금배당수익률(%)</TD><TD>보통주</TD><TE>1.5</TE><TE>-</TE><TE>-</TE></TR>
</TBODY></TABLE></TABLE-GROUP>"""

TOT_STK = """<TITLE>4. 주식의 총수 등</TITLE><TABLE-GROUP ACLASS="TOT_STK">
<TABLE><TBODY><TR><TD>(기준일 : </TD><TU AUNIT="BASE_DT" AUNITVALUE="20241231">2024년 12월 31일</TU></TR></TBODY></TABLE>
<TABLE><THEAD><TR><TH ROWSPAN="2" COLSPAN="2">구 분</TH><TH COLSPAN="2">주식의 종류</TH><TH ROWSPAN="2">비고</TH></TR>
<TR><TE>보통주</TE><TH>합계</TH></TR></THEAD><TBODY>
<TR><TD COLSPAN="2">Ⅱ. 현재까지 발행한 주식의 총수</TD><TE ACODE="ISU_STK2">1,000</TE><TE ACODE="SUM_ISU_STK2">1,000</TE><TE ACODE="NOTE1">-</TE></TR>
<TR><TD ROWSPAN="2"></TD><TD>1. 감자</TD><TE ACODE="RDC_CNT">100</TE><TE ACODE="SUM_RDC_CNT">100</TE><TE ACODE="NOTE3">무상감자</TE></TR>
<TR><TD>4. 기타</TD><TE ACODE="ETC_CNT">-</TE><TE ACODE="SUM_ETC_CNT">-</TE><TE>-</TE></TR>
<TR><TD COLSPAN="2">Ⅲ. 현재까지 감소한 주식의 총수</TD><TE ACODE="TOT_RST">100</TE><TE ACODE="SUM_RST">100</TE><TE>-</TE></TR>
</TBODY></TABLE></TABLE-GROUP>"""

HOLDER = """<TABLE-GROUP ACLASS="BSH_SPCL"><TABLE><THEAD>
<TR><TH ROWSPAN="3">성 명</TH><TH ROWSPAN="3">관 계</TH><TH ROWSPAN="3">주식의&cr;종류</TH><TH COLSPAN="4">소유주식수 및 지분율</TH><TH ROWSPAN="3">비고</TH></TR>
<TR><TH COLSPAN="2">기 초</TH><TH COLSPAN="2">기 말</TH></TR>
<TR><TH>주식수</TH><TH>지분율</TH><TH>주식수</TH><TH>지분율</TH></TR></THEAD><TBODY>
<TR><TE ACODE="SH5_NM_T">홍길동</TE><TE>최대주주 본인</TE><TE>보통주</TE><TE>10</TE><TE>1.5</TE><TE>20</TE><TE>3.0</TE><TE>-</TE></TR>
<TR><TD COLSPAN="2">계</TD><TE>보통주</TE><TE>10</TE><TE>1.5</TE><TE>20</TE><TE>3.0</TE><TE>-</TE></TR>
</TBODY></TABLE></TABLE-GROUP>
<TABLE-GROUP ACLASS="{XBRL}BS"><TABLE><TBODY><TR><TE>1</TE></TR></TBODY></TABLE></TABLE-GROUP>"""

DOC = DIVIDEND + TOT_STK + HOLDER


def test_groups_skip_xbrl_and_keep_titles():
    gs = dx.groups(DOC)
    assert [g.aclass for g in gs] == ["DIVIDEND", "TOT_STK", "BSH_SPCL"]
    assert gs[0].title == "6. 배당에 관한 사항 등" and gs[1].title == "4. 주식의 총수 등"
    assert len(dx.groups(DOC, skip_xbrl=False)) == 4


def test_rowspan_and_colspan_are_filled():
    g = dx.first(dx.groups(DOC), "DIVIDEND")
    assert dx.header(g) == ["구 분", "주식의 종류", "당기 제10기", "전기 제9기", "전전기 제8기"]
    rows = dx.value_rows(g)
    assert [c.text for c in rows[2]] == ["주당 현금배당금(원)", "우선주", "110", "-", "-"]  # 위 행 rowspan을 채움
    assert rows[2][0].spanned and not rows[1][0].spanned


def test_dividend_items_by_column():
    items = dx.dividend_items(dx.first(dx.groups(DOC), "DIVIDEND"))
    assert ("현금배당금총액(백만원)", "-", 0, "1,200") in items and ("현금배당금총액(백만원)", "-", 2, "(30)") in items
    assert ("주당 현금배당금(원)", "우선주", 0, "110") in items
    assert ("현금배당수익률(%)", "보통주", 0, "1.5") in items  # 종류 칸이 TD여도 읽음
    assert dx.number("(30)") == -30 and dx.number("-") is None and dx.number("1,200") == 1200


def test_share_totals_and_holders():
    kinds, data, notes = dx.share_totals(dx.first(dx.groups(DOC), "TOT_STK"))
    assert kinds == ["보통주", "합계"]
    assert data["보통주"]["ISU_STK2"] == ("Ⅱ. 현재까지 발행한 주식의 총수", "1,000")
    assert data["합계"]["RST"] == ("Ⅲ. 현재까지 감소한 주식의 총수", "100")  # SUM_ 앞붙임 뗌
    assert data["보통주"]["RDC_CNT"][0] == "1. 감자" and notes == {"1. 감자": "무상감자"}
    assert dx.first(dx.groups(DOC), "TOT_STK").unit_cells() == {"BASE_DT": "2024년 12월 31일 [20241231]"}
    hs = dx.holders(dx.first(dx.groups(DOC), "BSH_SPCL"))
    assert hs[0] == {"성명": "홍길동", "관계": "최대주주 본인", "주식 종류": "보통주", "기초 주식수": "10", "기초 지분율": "1.5",
                     "기말 주식수": "20", "기말 지분율": "3.0", "비고": "-"}
    assert hs[1]["성명"] == "계"


def test_grid_lists_every_row():
    rows = list(dx.grid(dx.first(dx.groups(DOC), "TOT_STK")))
    assert rows[0][:3] == (1, 1, "본문") and rows[1][2] == "머리"
    assert rows[-1][3][:3] == ["Ⅲ. 현재까지 감소한 주식의 총수", "Ⅲ. 현재까지 감소한 주식의 총수", "100"]
    assert rows[-1][4] == ["TOT_RST", "SUM_RST"]  # 값 칸 코드 (빈 ACODE 칸은 빠짐)
