"""인터넷·키 없이 결측 보완 흐름을 보여 주는 가짜 응답. 테스트와 팀 공유 노트북이 함께 쓴다.

회사 '00000001'(가상 회사 가나다)은 실제 응답에서 자주 보던 결측 모양을 일부러 담았다.
- 연결재무제표 없음(013) → 별도만 있음, 계정 이름이 '당기순이익(손실)', account_id가 '-표준계정코드 미사용-'
- 2024 사업보고서 배당 표: 현금배당금총액 행이 '-' , 주당 현금배당금은 보통주·우선주 두 행
- 2025 사업보고서 배당 표의 전기(frmtrm) 칸에 2024 현금배당금총액이 있음
- 배당 결정 공시 원문: DART XML 표(TD·TE)로만 숫자가 있음
- 기업가치 제고 계획 공시: 원문 파일 없음(014)
- 감사보고서(별도) 2024·2025: 단위 천원, 둘째 칸이 주석 번호, 한 기간에 금액 칸 두 개(내역·합계),
  감사의견 문단에 재무제표 이름이 나열됨, 주석 표에도 '부채총계'가 있음. 2023 감사보고서는 없음.
  2025 자본총계는 사업보고서 API 값과 일부러 다르게 넣음(대조 불일치 예시)

회사 '00000002'(가상 회사 라마바)는 연결 작성 회사다.
- 2025 연결감사보고서: 단위 백만원, 포괄손익계산서에 '지배기업 소유주지분'이 순이익 귀속·총포괄이익 귀속 두 번 나옴
- 2025 사업보고서 연결 API: account_id가 있음
숫자는 모두 가상이다.
"""
import io
import json
import zipfile

import pandas as pd

CORP = "00000001"
STOCK = "012345"
CORP2 = "00000002"
AUDIT_2024 = "20250310000901"
AUDIT_2025 = "20260309000902"
CONSOL_AUDIT_2025 = "20260311000903"
DECISION_RCEPT = "20260210800123"
VALUEUP_RCEPT = "20250530800456"


def _ok(rows, **extra) -> bytes:
    return json.dumps({"status": "000", "message": "정상", "list": rows, **extra}, ensure_ascii=False).encode()


NO_DATA = json.dumps({"status": "013", "message": "조회된 데이타가 없습니다."}, ensure_ascii=False).encode()
LIMIT = json.dumps({"status": "020", "message": "요청 제한을 초과하였습니다."}, ensure_ascii=False).encode()


def _statement_rows(year: int, net: str, prev: str, liab: str, eq: str, rcept: str) -> list[dict]:
    common = {"rcept_no": rcept, "bsns_year": str(year), "corp_code": CORP, "currency": "KRW"}
    return [
        {**common, "sj_div": "BS", "account_id": "ifrs-full_Liabilities", "account_nm": "부채총계",
         "thstrm_amount": liab, "frmtrm_amount": "", "ord": "1"},
        {**common, "sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계",
         "thstrm_amount": eq, "frmtrm_amount": "", "ord": "2"},
        {**common, "sj_div": "IS", "account_id": "-표준계정코드 미사용-", "account_nm": "당기순이익(손실)",
         "thstrm_amount": net, "frmtrm_amount": prev, "ord": "3"},
        {**common, "sj_div": "CF", "account_id": "dart_DividendsPaid", "account_nm": "배당금의 지급",
         "thstrm_amount": "(1,500,000,000)", "frmtrm_amount": "", "ord": "4"},
    ]


def _dividend_rows(rcept: str, cash_total: tuple[str, str, str]) -> list[dict]:
    t, f, lw = cash_total
    base = {"rcept_no": rcept, "corp_code": CORP, "corp_name": "가나다"}
    return [
        {**base, "se": "(별도)당기순이익(백만원)", "stock_knd": "", "thstrm": "5,000", "frmtrm": "4,000", "lwfr": "3,000"},
        {**base, "se": "현금배당금총액(백만원)", "stock_knd": "", "thstrm": t, "frmtrm": f, "lwfr": lw},
        {**base, "se": "(별도)현금배당성향(%)", "stock_knd": "", "thstrm": "30.0", "frmtrm": "-", "lwfr": "-"},
        {**base, "se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "500", "frmtrm": "450", "lwfr": "400"},
        {**base, "se": "주당 현금배당금(원)", "stock_knd": "우선주", "thstrm": "505", "frmtrm": "455", "lwfr": "405"},
    ]


DECISION_XML = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY><TABLE>
<TR><TD>1. 배당구분</TD><TD>결산배당</TD></TR>
<TR><TD>2. 배당종류</TD><TD>현금배당</TD></TR>
<TR><TD ROWSPAN="2">3. 1주당 배당금(원)</TD><TD>보통주식</TD><TE>1,500</TE></TR>
<TR><TD>종류주식</TD><TE>1,505</TE></TR>
<TR><TD ROWSPAN="2">4. 시가배당율(%)</TD><TD>보통주식</TD><TE>3.2</TE></TR>
<TR><TD>종류주식</TD><TE>3.4</TE></TR>
<TR><TD>5. 배당금총액(원)</TD><TE>1,512,345,000</TE></TR>
<TR><TD>6. 배당기준일</TD><TE>2025-12-31</TE></TR>
</TABLE></BODY></DOCUMENT>"""


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


CORPCODE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<result>
<list><corp_code>{CORP}</corp_code><corp_name>가나다</corp_name><stock_code>{STOCK}</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000002</corp_code><corp_name>라마바</corp_name><stock_code>067890</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000003</corp_code><corp_name>비상장사</corp_name><stock_code> </stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000004</corp_code><corp_name>인지디스플레이</corp_name><stock_code>037330</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000005</corp_code><corp_name>현대자동차</corp_name><stock_code>005380</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000006</corp_code><corp_name>GS</corp_name><stock_code>078930</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000007</corp_code><corp_name>GS리테일</corp_name><stock_code>007070</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000008</corp_code><corp_name>신영증권</corp_name><stock_code>001720</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00000009</corp_code><corp_name>인지디스플레이테크</corp_name><stock_code>099990</stock_code><modify_date>20260101</modify_date></list>
</result>"""

# 기업개황(company.json): 법인구분 Y 유가·K 코스닥, 결산월, 업종코드(64~66 금융업)
COMPANY = {
    CORP: ("가나다", "가나다", STOCK, "K", "264", "12"),
    "00000002": ("라마바", "라마바", "067890", "Y", "301", "12"),
    "00000004": ("인지디스플레이", "인지디스플레", "037330", "K", "262", "12"),
    "00000005": ("현대자동차", "현대차", "005380", "Y", "301", "12"),
    "00000006": ("GS", "GS", "078930", "Y", "701", "12"),
    "00000007": ("GS리테일", "GS리테일", "007070", "Y", "471", "12"),
    "00000008": ("신영증권", "신영증권", "001720", "Y", "661", "03"),
    "00000009": ("인지디스플레이테크", "인지디스테크", "099990", "Y", "262", "12"),  # 이름은 비슷하지만 유가
}


_HEAD = ("<TR><TD>과 목</TD><TD>주 석</TD><TD>제 {n}(당) 기</TD><TD></TD>"
         "<TD>제 {p}(전) 기</TD><TD></TD></TR>")


def _audit_xml(n: int, debt: str, equity: str, net: str, prev_net: str, paid: str) -> str:
    head = _HEAD.format(n=n, p=n - 1)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY>
<P>독립된 감사인의 감사보고서</P>
<P>우리는 재무상태표, 손익계산서, 자본변동표, 현금흐름표 그리고 주석으로 구성된 재무제표를 감사하였습니다.</P>
<P>재 무 상 태 표</P><P>제 {n} 기 {2014 + n}년 12월 31일 현재</P><P>(단위 : 천원)</P>
<TABLE>{head}
<TR><TD>자산총계</TD><TD></TD><TD></TD><TD>30,000,000</TD><TD></TD><TD>28,000,000</TD></TR>
<TR><TD>부채총계</TD><TD>4,5</TD><TD></TD><TD>{debt}</TD><TD></TD><TD>9,000,000</TD></TR>
<TR><TD>자본총계</TD><TD>17</TD><TD></TD><TD>{equity}</TD><TD></TD><TD>19,000,000</TD></TR>
</TABLE>
<P>첨부된 주석은 본 재무제표의 일부입니다.</P>
<P>손 익 계 산 서</P><P>(단위 : 천원)</P>
<TABLE>{head}
<TR><TD>Ⅰ. 매출액</TD><TD>20</TD><TD></TD><TD>50,000,000</TD><TD></TD><TD>45,000,000</TD></TR>
<TR><TD>Ⅹ. 당기순이익(손실)</TD><TD></TD><TD></TD><TD>{net}</TD><TD></TD><TD>{prev_net}</TD></TR>
</TABLE>
<P>현 금 흐 름 표</P><P>(단위 : 천원)</P>
<TABLE>{head}
<TR><TD>배당금의 지급</TD><TD>25</TD><TD>{paid}</TD><TD></TD><TD>(1,200,000)</TD><TD></TD></TR>
</TABLE>
<P>주석</P><P>1. 일반사항</P>
<TABLE><TR><TD>부채총계</TD><TD>999</TD></TR></TABLE>
</BODY></DOCUMENT>"""


CONSOL_AUDIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY>
<P>연 결 재 무 상 태 표</P><P>(단위 : 백만원)</P>
<TABLE><TR><TD>과 목</TD><TD>주 석</TD><TD>당기</TD><TD>전기</TD></TR>
<TR><TD>부채총계</TD><TD>10</TD><TD>8,000</TD><TD>7,500</TD></TR>
<TR><TD>지배기업 소유주지분</TD><TD></TD><TD>11,000</TD><TD>10,000</TD></TR>
<TR><TD>비지배지분</TD><TD></TD><TD>1,000</TD><TD>900</TD></TR>
<TR><TD>자본총계</TD><TD></TD><TD>12,000</TD><TD>10,900</TD></TR>
</TABLE>
<P>연 결 포 괄 손 익 계 산 서</P><P>(단위 : 백만원)</P>
<TABLE><TR><TD>과 목</TD><TD>주 석</TD><TD>당기</TD><TD>전기</TD></TR>
<TR><TD>당기순이익</TD><TD></TD><TD>2,000</TD><TD>1,800</TD></TR>
<TR><TD>지배기업의 소유주에게 귀속되는 당기순이익</TD><TD></TD><TD>1,700</TD><TD>1,500</TD></TR>
<TR><TD>비지배지분에 귀속되는 당기순이익</TD><TD></TD><TD>300</TD><TD>300</TD></TR>
<TR><TD>총포괄이익</TD><TD></TD><TD>2,200</TD><TD>1,900</TD></TR>
<TR><TD>지배기업 소유주지분</TD><TD></TD><TD>1,850</TD><TD>1,580</TD></TR>
</TABLE>
</BODY></DOCUMENT>"""


def _consol_rows() -> list[dict]:
    common = {"rcept_no": "20260316000333", "bsns_year": "2025", "corp_code": CORP2, "currency": "KRW"}
    rows = [
        ("BS", "ifrs-full_Liabilities", "부채총계", "8,000,000,000"),
        ("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", "11,000,000,000"),
        ("BS", "ifrs-full_Equity", "자본총계", "12,000,000,000"),
        ("CIS", "ifrs-full_ProfitLoss", "당기순이익", "2,000,000,000"),
        ("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분", "1,700,000,000"),
        ("CIS", "ifrs-full_ComprehensiveIncomeAttributableToOwnersOfParent", "지배기업 소유주지분", "1,850,000,000"),
    ]
    return [{**common, "sj_div": sj, "account_id": i, "account_nm": n, "thstrm_amount": v, "frmtrm_amount": ""}
            for sj, i, n, v in rows]


def _audit_list(corp: str, detail: str) -> bytes:
    rows = []
    if corp == CORP and detail == "F001":
        rows = [
            {"corp_code": CORP, "report_nm": "감사보고서 (2024.12)", "rcept_no": AUDIT_2024, "rcept_dt": "20250310"},
            {"corp_code": CORP, "report_nm": "감사보고서 (2025.12)", "rcept_no": AUDIT_2025, "rcept_dt": "20260309"},
        ]
    if corp == CORP2 and detail == "F002":
        rows = [{"corp_code": CORP2, "report_nm": "연결감사보고서 (2025.12)", "rcept_no": CONSOL_AUDIT_2025,
                 "rcept_dt": "20260311"}]
    return _ok(rows, page_no=1, total_page=1, total_count=len(rows)) if rows else NO_DATA


def fake_dart_fetch(url: str, params: dict) -> bytes:
    """OpenDART 주소·파라미터를 보고 가짜 응답을 고른다. 모르는 요청은 013."""
    endpoint = url.rsplit("/", 1)[-1]
    year = str(params.get("bsns_year", ""))
    if endpoint == "corpCode.xml":
        return _zip({"CORPCODE.xml": CORPCODE_XML})
    if endpoint == "company.json":
        if params["corp_code"] not in COMPANY:
            return NO_DATA
        name, short, code, cls, induty, month = COMPANY[params["corp_code"]]
        return json.dumps({"status": "000", "message": "정상", "corp_name": name, "stock_name": short, "stock_code": code,
                           "corp_cls": cls, "induty_code": induty, "acc_mt": month}, ensure_ascii=False).encode()
    if endpoint == "list.json" and params.get("pblntf_ty") == "F":
        return _audit_list(params.get("corp_code"), params.get("pblntf_detail_ty"))
    if endpoint == "document.xml":
        audits = {AUDIT_2024: _audit_xml(10, "10,000,000", "20,000,000", "4,800,000", "3,900,000", "(1,500,000)"),
                  AUDIT_2025: _audit_xml(11, "11,000,000", "21,500,000", "5,100,000", "4,750,000", "(1,500,000)"),
                  CONSOL_AUDIT_2025: CONSOL_AUDIT_XML}
        if params["rcept_no"] in audits:
            return _zip({f"{params['rcept_no']}.xml": audits[params["rcept_no"]]})
    if params.get("corp_code") == CORP2:
        if endpoint == "fnlttSinglAcntAll.json" and params["fs_div"] == "CFS" and year == "2025":
            return _ok(_consol_rows())
        return NO_DATA
    if params.get("corp_code") not in (CORP, None):
        return NO_DATA
    if endpoint == "fnlttSinglAcntAll.json":
        if params["fs_div"] == "CFS":
            return NO_DATA  # 자회사가 없어 연결재무제표가 없다
        if year == "2024":
            return _ok(_statement_rows(2024, "4,800,000,000", "3,900,000,000", "10,000,000,000", "20,000,000,000",
                                       "20250315000111"))
        if year == "2025":
            return _ok(_statement_rows(2025, "5,100,000,000", "4,750,000,000", "11,000,000,000", "21,000,000,000",
                                       "20260316000222"))
        return NO_DATA
    if endpoint == "fnlttSinglAcnt.json":
        return NO_DATA
    if endpoint == "alotMatter.json":
        if year == "2024":
            return _ok(_dividend_rows("20250315000111", ("-", "1,200", "1,000")))
        if year == "2025":
            return _ok(_dividend_rows("20260316000222", ("1,512", "1,400", "-")))
        return NO_DATA
    if endpoint == "stockTotqySttus.json":
        rows = [
            {"rcept_no": "20260316000222", "se": "보통주", "istc_totqy": "1,000,000", "tesstk_co": "8,000", "distb_stock_co": "-"},
            {"rcept_no": "20260316000222", "se": "우선주", "istc_totqy": "10,000", "tesstk_co": "0", "distb_stock_co": "10,000"},
            {"rcept_no": "20260316000222", "se": "합계", "istc_totqy": "1,010,000", "tesstk_co": "8,000", "distb_stock_co": "-"},
        ]
        return _ok(rows)
    if endpoint == "hyslrSttus.json":
        rows = [
            {"rcept_no": "20260316000222", "nm": "홍길동", "relate": "본인", "stock_knd": "보통주", "trmend_posesn_stock_qota_rt": "30.10"},
            {"rcept_no": "20260316000222", "nm": "홍길순", "relate": "친인척", "stock_knd": "보통주", "trmend_posesn_stock_qota_rt": "5.25"},
            {"rcept_no": "20260316000222", "nm": "홍길동", "relate": "본인", "stock_knd": "우선주", "trmend_posesn_stock_qota_rt": "1.00"},
        ]
        return _ok(rows)
    if endpoint == "list.json":
        rows = [
            {"corp_code": CORP, "corp_name": "가나다", "report_nm": "현금ㆍ현물배당결정", "rcept_no": DECISION_RCEPT,
             "rcept_dt": "20260210", "rm": "유"},
            {"corp_code": CORP, "corp_name": "가나다", "report_nm": "[기재정정]기업가치 제고 계획(자율공시)",
             "rcept_no": VALUEUP_RCEPT, "rcept_dt": "20250530", "rm": "유"},
            {"corp_code": CORP, "corp_name": "가나다", "report_nm": "사업보고서 (2025.12)", "rcept_no": "20260316000222",
             "rcept_dt": "20260316", "rm": ""},
        ]
        page = int(params.get("page_no", 1))
        return _ok(rows[:2] if page == 1 else rows[2:], page_no=page, total_page=2, total_count=3)
    if endpoint == "document.xml":
        if params["rcept_no"] == DECISION_RCEPT:
            return _zip({f"{DECISION_RCEPT}.xml": DECISION_XML})
        return b'<?xml version="1.0" encoding="UTF-8"?><result><status>014</status><message>file not found</message></result>'
    return NO_DATA


class FakePrices:
    """pykrx 대신 쓰는 가짜 시세. 012345는 1월 6~7일 거래정지, 067890은 1월 8일 상장."""

    name = "가짜 시세"

    def __init__(self):
        self.days = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"])

    def index(self, code, start, end):
        return pd.DataFrame({"시가": 2500.0, "고가": 2510.0, "저가": 2490.0,
                             "종가": [2500.0, 2510.0, 2490.0, 2520.0, 2530.0, 2540.0], "거래량": 1_000_000}, index=self.days)

    def tickers(self, date, market):
        return {"012345": "가나다"} if market == "KOSDAQ" else {"067890": "라마바"}

    def prices(self, ticker, start, end):
        if ticker == "012345":
            return pd.DataFrame({
                "시가": [10000, 10100, 0, 0, 10300, 10400], "고가": [10100, 10200, 0, 0, 10400, 10500],
                "저가": [9900, 10000, 0, 0, 10200, 10300], "종가": [10000, 10100, 10100, 10100, 10350, 10450],
                "거래량": [500, 600, 0, 0, 700, 800]}, index=self.days)
        if ticker == "067890":
            d = self.days[4:]
            return pd.DataFrame({"시가": [5000, 5100], "고가": [5200, 5200], "저가": [4900, 5000],
                                 "종가": [5100, 5150], "거래량": [9000, 8000]}, index=d)
        return pd.DataFrame()


# 국가법령정보센터 응답: 검색 결과가 하나라 law가 dict, 항이 하나라 dict, 호는 목록
LAW_SEARCH = {"LawSearch": {"law": {"법령일련번호": "999999", "법령명한글": "조세특례제한법", "시행일자": "20260918",
                                    "현행연혁코드": "현행"}}}
LAW_BODY = {"법령": {"기본정보": {"법령명_한글": "조세특례제한법"}, "조문": {"조문단위": [
    {"조문번호": "104", "조문가지번호": "26", "조문여부": "조문", "조문제목": "다른 조문", "조문내용": "제104조의26(다른 조문)"},
    {"조문번호": "104", "조문여부": "전문", "조문내용": "제5절 ..."},
    {"조문번호": "104", "조문가지번호": "27", "조문여부": "조문", "조문제목": "고배당기업 주식 배당소득에 대한 과세특례",
     "조문내용": "제104조의27(고배당기업 주식 배당소득에 대한 과세특례)",
     "항": {"항번호": "①", "항내용": [["① 다음 각 호의 요건을 모두 갖춘 내국법인 ..."]],
            "호": [{"호번호": "1.", "호내용": "1. 가상 요건 하나"}, {"호번호": "2.", "호내용": "2. 가상 요건 둘",
                                                                "목": {"목번호": "가.", "목내용": "가. 가상 세부 요건"}}]}},
]}}}


def fake_law_fetch(url: str, params: dict) -> bytes:
    if params.get("OC") == "wrong":
        return "<html>인증 오류</html>".encode()
    if url.endswith("lawSearch.do"):
        return json.dumps(LAW_SEARCH, ensure_ascii=False).encode()
    return json.dumps(LAW_BODY, ensure_ascii=False).encode()


# KIND '밸류업 고배당기업' 내려받기와 같은 모양(HTML 표, 종목코드 열 없음, 회사명은 KRX 약칭)
KIND_HTML = """<html><body><table>
<tr><th>번호</th><th>시장구분</th><th>회사명</th><th>공시제목</th><th>사업연도</th><th>결산월</th><th>배당성향(%)</th><th>이익배당금증가율(%)</th></tr>
<tr><td>1</td><td>코스닥</td><td>인지디스플레</td><td>기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>27.76</td><td>52.36</td></tr>
<tr><td>2</td><td>유가</td><td>현대차</td><td>기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>25.1</td><td>10.2</td></tr>
<tr><td>3</td><td>유가</td><td>GS</td><td>기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>40.2</td><td>0</td></tr>
<tr><td>4</td><td>유가</td><td>신영증권</td><td>기업가치 제고 계획(자율공시)</td><td>2026</td><td>03</td><td>40.3</td><td>5</td></tr>
<tr><td>5</td><td>코스닥</td><td>가나다</td><td>[정정] 기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>30.0</td><td>12</td></tr>
<tr><td>6</td><td>유가</td><td>라마바</td><td>기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>45.0</td><td>10</td></tr>
<tr><td>7</td><td>코스닥</td><td>없는회사</td><td>기업가치 제고 계획(자율공시)</td><td>2025</td><td>12</td><td>-</td><td>-</td></tr>
</table></body></html>"""
