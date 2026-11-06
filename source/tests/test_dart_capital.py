"""증자·감자 API 응답 해석, 분할·병합 원문 읽기·검산, 키 처리. 네트워크 없이 시험한다.

분할 원문 줄은 실제 공시(2026년 주식분할 결정 3건, KIND 공개 화면)를 table_lines로 바꾼 것을 줄였다.
"""
import json
from decimal import Decimal

import pytest

from core import dart_capital as dc

SPLIT_LINES = [
    "1. 주식분할 내용 | 구분 | 분할 전 | 분할 후 |",
    "1주당 가액(원) | 5,000 | 1,000 |",
    "발행주식총수 | 보통주식(주) | 5,700,000 | 28,500,000 |",
    "종류주식(주) | - | - |",
    "2. 주식분할 일정 | 주주총회예정일 | 2026-03-18 |",
    "구주권제출기간 | 시작일 | - |",
    "종료일 | - |",
    "신주의 효력발생일 | 2026-04-08 |",
    "매매거래정지기간 | 시작일 | 2026-04-06 |",
    "종료일 | 2026-04-16 |",
    "명의개서정지기간 | 시작일 | - |",
    "종료일 | - |",
    "신주권상장예정일 | 2026-04-17 |",
    "3. 주식분할목적 | 유통주식수 확대 |",
    "4. 이사회결의일(결정일) | 2026-02-23 |",
    "- 사외이사 참석여부 | 참석(명) | 3 |",
    "5. 기타 투자판단과 관련한 중요사항 | - 당사의 주식 액면분할 비율은 5:1 입니다. |",
    "※ 관련공시 | - |",
]

# 정정공시: 정정 내역표에 '정정전' 숫자가 먼저 나오고, 본문은 뒤에 있다
CORRECTION_LINES = [
    "정정일자 | 2026-04-15 |",
    "정정항목 | 정정전 | 정정후 |",
    "1. 주식분할 내용 - 발행주식총수 분할전 보통주식(주) | 11,110,545 | 10,110,545 |",
    "주식분할 결정",
    "1. 주식분할 내용 | 구분 | 분할전 | 분할후 |",
    "1주당 가액 (원) | 1,000 | 500 |",
    "발행주식총수 | 보통주식(주) | 10,110,545 | 20,221,090 |",
    "종류주식(주) | - | - |",
    "2. 주식분할 일정 | 주주총회예정일 | 2026-03-27 |",
    "신주의 효력발생일 | 2026-04-14 |",
    "매매거래정지예정기간 | 시작일 | 2026-04-10 |",
    "종료일 | 2026-04-28 |",
    "명의개서정지기간 | - |",
    "신주권상장예정일 | 2026-04-29 |",
    "4. 이사회결의일 | 2026-03-12 |",
    "※관련공시 | - |",
]


def test_split_fields_reads_every_value():
    f = dc.split_fields(SPLIT_LINES)
    assert f == {"par_before_won": 5000, "par_after_won": 1000, "shares_before_common": 5_700_000,
                 "shares_after_common": 28_500_000, "shares_before_pref": None, "shares_after_pref": None,
                 "agm_date": "2026-03-18", "effective_date": "2026-04-08", "halt_start": "2026-04-06",
                 "halt_end": "2026-04-16", "listing_date": "2026-04-17", "board_date": "2026-02-23",
                 "purpose": "유통주식수 확대"}
    check, status = dc.check_split("주식분할", f)
    assert status == "읽음" and check.startswith("일치") and "5배 분할" in check


def test_split_correction_reads_body_not_correction_table():
    f = dc.split_fields(CORRECTION_LINES)
    assert (f["par_before_won"], f["par_after_won"]) == (1000, 500)
    assert (f["shares_before_common"], f["shares_after_common"]) == (10_110_545, 20_221_090)  # 정정 후 본문
    assert (f["halt_start"], f["halt_end"], f["board_date"]) == ("2026-04-10", "2026-04-28", "2026-03-12")
    assert dc.check_split("주식분할", f)[1] == "읽음"


def test_check_split_flags_mismatch_and_merge():
    bad = dc.split_fields([ln.replace("28,500,000", "28,000,000") for ln in SPLIT_LINES])
    check, status = dc.check_split("주식분할", bad)
    assert status == "확인 필요" and check.startswith("안 맞음")
    merge = {"par_before_won": Decimal(100), "par_after_won": Decimal(1000),
             "shares_before_common": Decimal(12_345_678), "shares_after_common": Decimal(1_234_567)}
    check, status = dc.check_split("주식병합", merge)  # 10주→1주, 단주 처리로 0.8주 차이
    assert status == "읽음" and "10주→1주" in check
    assert dc.check_split("주식분할", dc.split_fields([]))[1] == "확인 필요"


def test_split_row_without_document():
    row = dc.split_row({"rcept_no": "20260223800123", "corp_code": "00123456", "report_nm": "[기재정정]주식분할결정"},
                       "주식분할", None, "원문을 받지 못함")
    assert row["status"] == "원문 못 받음" and row["is_correction"] and row["rcept_dt"] == "2026-02-23"


@pytest.mark.parametrize("title, expected", [
    ("주요사항보고서(유상증자결정)", ("유상증자", "piicDecsn")),
    ("[기재정정]주요사항보고서(무상증자결정)", ("무상증자", "fricDecsn")),
    ("주요사항보고서(유무상증자결정)", ("유무상증자", "pifricDecsn")),
    ("주요사항보고서(감자결정)", ("감자", "crDecsn")),
    ("주식분할결정", ("주식분할", "doc")),
    ("주식병합 결정", ("주식병합", "doc")),
    ("유상증자결정(자회사의 주요경영사항)", None),
    ("주식분할결정(종속회사의주요경영사항)", None),
    ("현금ㆍ현물배당결정", None),
])
def test_classify(title, expected):
    assert dc.classify(title) == expected


def test_capital_rows_paid_free_both_and_reduction():
    paid = {"rcept_no": "20240315000123", "corp_code": "00111111", "corp_name": "가사", "nstk_ostk_cnt": "1,000,000",
            "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "10,000,000", "fdpp_op": "3,000,000,000",
            "fdpp_fclt": "2,000,000,000", "fdpp_etc": "-", "ic_mthn": "주주배정후 실권주 일반공모"}
    (r,) = dc.capital_rows(paid, "piicDecsn", "주요사항보고서(유상증자결정)")
    assert (r["kind"], r["shares_common"], r["shares_pref"], r["funds_won"]) == ("유상증자", 1_000_000, None, 5_000_000_000)
    assert r["rcept_dt"] == "2024-03-15" and not r["is_correction"] and json.loads(r["payload"])["fv_ps"] == "500"

    both = {"rcept_no": "20240401000001", "corp_code": "00111111", "piic_nstk_ostk_cnt": "100",
            "fric_nstk_ostk_cnt": "50", "fric_nstk_ascnt_ps_ostk": "0.5", "fric_nstk_asstd": "2024년 05월 01일"}
    a, b = dc.capital_rows(both, "pifricDecsn")
    assert (a["kind"], a["shares_common"], b["kind"], b["shares_common"]) == ("유무상증자(유상)", 100, "유무상증자(무상)", 50)
    assert b["per_share_common"] == Decimal("0.5") and b["record_date"] == "2024년 05월 01일"

    cut = {"rcept_no": "20250110000009", "corp_code": "00222222", "crstk_ostk_cnt": "9,000,000",
           "bfcr_tisstk_ostk": "10,000,000", "atcr_tisstk_ostk": "1,000,000", "cr_rt_ostk": "90",
           "bfcr_cpt": "5,000,000,000", "atcr_cpt": "500,000,000", "cr_mth": "10주를 1주로 병합", "cr_rs": "결손금 보전"}
    (c,) = dc.capital_rows(cut, "crDecsn", "주요사항보고서(감자결정)")
    assert c["check_result"] == "일치" and c["ratio_common_pct"] == 90 and c["capital_after_won"] == 500_000_000
    cut["atcr_tisstk_ostk"] = "2,000,000"
    assert dc.capital_rows(cut, "crDecsn")[0]["check_result"].startswith("안 맞음")


def test_num_and_text():
    assert dc.num("1,234") == 1234 and dc.num("(1,000)") == -1000 and dc.num("-") is None and dc.num("해당없음") is None
    assert dc.text(" - ") is None and dc.text("보통") == "보통"


def test_call_uses_cache_and_never_puts_key_in_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "API_CACHE", tmp_path)
    sent = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    def fake_urlopen(req, timeout):
        sent.append(req.full_url)
        return Resp(json.dumps({"status": "000", "list": [{"rcept_no": "1"}], "total_page": 1}).encode())

    monkeypatch.setattr(dc.urllib.request, "urlopen", fake_urlopen)
    rows, msg = dc.filing_list("SECRETKEY", "00111111", "B")
    rows2, _ = dc.filing_list("SECRETKEY", "00111111", "B")
    assert msg == "성공" and rows == rows2 == [{"rcept_no": "1"}] and len(sent) == 1  # 두 번째는 캐시
    assert all("SECRETKEY" not in p.name and "SECRETKEY" not in p.read_text() for p in tmp_path.iterdir())


def test_call_stops_on_key_error_without_caching(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "API_CACHE", tmp_path)

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"status": "020", "message": "요청 제한"}).encode()

    monkeypatch.setattr(dc.urllib.request, "urlopen", lambda req, timeout: Resp())
    with pytest.raises(dc.StopRun, match="요청 제한 초과"):
        dc.decision_rows("K", "00111111", "crDecsn")
    assert not list(tmp_path.iterdir())


def test_api_key_from_env_or_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv(dc.KEY_NAME, " abc ")
    assert dc.api_key() == "abc"
    monkeypatch.delenv(dc.KEY_NAME)
    root = tmp_path / "repo" / "sub"
    root.mkdir(parents=True)
    (tmp_path / "repo" / ".env").write_text("OTHER=1\nOPENDART_API_KEY='xyz'\n")
    monkeypatch.setattr(dc, "ROOT", root)
    assert dc.api_key() == "xyz"


def test_versions_marks_superseded_corrections():
    # 고려아연 2024·2025 유상증자처럼 원공시 뒤에 정정이 이어지고 API는 묶음의 마지막 판만 준다
    titles = {"20230830001131": "주요사항보고서(유상증자결정)",
              "20241030000098": "주요사항보고서(유상증자결정)",
              "20241113000148": "[기재정정]주요사항보고서(유상증자결정)",
              "20241114000001": "[기재정정]주요사항보고서(유상증자결정)",
              "20251215000398": "[첨부추가]주요사항보고서(유상증자결정)",
              "20251216000401": "[기재정정]주요사항보고서(유상증자결정)",
              "20260301000001": "주요사항보고서(유상증자결정)"}
    v = dc.versions(titles, {"20230830001131", "20241114000001", "20251216000401"})
    assert v["20230830001131"] == ("API 최종본", "20230830001131")
    assert v["20241030000098"] == ("앞선 판", "20241114000001") and v["20241113000148"][0] == "앞선 판"
    assert v["20251215000398"] == ("앞선 판", "20251216000401")  # [첨부추가]로 시작한 묶음도 같은 묶음
    assert v["20260301000001"] == ("API 응답 없음", "20260301000001")
    row = dc.listed_only_row({"rcept_no": "20241030000098", "corp_code": "00102858", "report_nm": titles["20241030000098"]},
                             "유상증자", "앞선 판", "20241114000001", "piicDecsn")
    assert row["payload"] == "{}" and row["shares_common"] is None and "20241114000001" in row["check_result"]


def test_all_dash_response_is_flagged():
    (r,) = dc.capital_rows({"rcept_no": "20241114000001", "corp_code": "00102858", "fv_ps": "-", "nstk_ostk_cnt": "-",
                            "ic_mthn": "일반공모증자"}, "piicDecsn", "[기재정정]주요사항보고서(유상증자결정)")
    assert r["version"] == "API 최종본" and "모두 '-'" in r["check_result"]


def test_merge_with_ui_heading():
    # 남성 2026 주식병합 결정: '1. 주식병합의 내용', '3. 주식병합목적'
    lines = [ln.replace("주식분할 내용", "주식병합의 내용").replace("분할 전", "병합 전").replace("분할 후", "병합 후")
             .replace("주식분할목적 | 유통주식수 확대", "주식병합목적 | 적정 유통주식수 유지")
             .replace("5,000 | 1,000", "500 | 5,000").replace("5,700,000 | 28,500,000", "36,212,160 | 3,621,216")
             for ln in SPLIT_LINES]
    f = dc.split_fields(lines)
    assert (f["par_before_won"], f["shares_after_common"], f["purpose"]) == (500, 3_621_216, "적정 유통주식수 유지")
    assert dc.check_split("주식병합", f)[1] == "읽음"


def test_versions_gap_and_attachment_only():
    # LS증권: 2023년 정정(기간 전 원공시)과 2024년 묶음은 다른 일
    titles = {"20230209000635": "[기재정정]주요사항보고서(유상증자결정)",
              "20240201000657": "[기재정정]주요사항보고서(유상증자결정)",
              "20240201000681": "[기재정정]주요사항보고서(유상증자결정)"}
    v = dc.versions(titles, {"20240201000681"})
    assert v["20230209000635"] == ("API 응답 없음", "20230209000635") and v["20240201000657"] == ("앞선 판", "20240201000681")
    # 스톰테크: API는 첨부정정 앞의 공시를 준다
    v = dc.versions({"20240816000089": "주요사항보고서(무상증자결정)",
                     "20240819000287": "[첨부정정]주요사항보고서(무상증자결정)"}, {"20240816000089"})
    assert v["20240819000287"] == ("첨부만 정정", "20240816000089")


def test_reduction_check_pref_only_and_par_cut():
    base = {"rcept_no": "20241210000165", "corp_code": "00160588", "crstk_ostk_cnt": "-", "crstk_estk_cnt": "3,095,629",
            "bfcr_tisstk_ostk": "74,958,735", "atcr_tisstk_ostk": "74,958,735", "bfcr_tisstk_estk": "22,946,407",
            "atcr_tisstk_estk": "19,850,778", "fv_ps": "5,000", "cr_mth": "자기주식 소각"}
    assert dc.capital_rows(base, "crDecsn")[0]["check_result"] == "종류주식 일치"  # 한화 2024 우선주 소각
    par = {"rcept_no": "20250312000430", "corp_code": "00000001", "crstk_ostk_cnt": "45,235,478", "fv_ps": "5,000",
           "bfcr_tisstk_ostk": "45,235,478", "atcr_tisstk_ostk": "45,235,478", "cr_mth": "액면가 감액 무상감자"}
    assert dc.capital_rows(par, "crDecsn")[0]["check_result"].startswith("일치 (액면가 감액")


def test_decision_rows_keeps_only_period(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "call", lambda key, ep, params: {"status": "000", "list": [
        {"rcept_no": "20190423000428"}, {"rcept_no": "20240215001136"}]})
    rows, msg = dc.decision_rows("K", "00330424", "piicDecsn")
    assert [r["rcept_no"] for r in rows] == ["20240215001136"] and msg == "성공"


# 유상증자 결정 원문 3가지 서식 (실제 공시를 table_lines로 바꾼 것을 줄임)
PAID_THIRD = [  # 지아이텍 2023: 제3자배정, 기타주식만 발행
    "유상증자 결정",
    "1. 신주의 종류와 수 | 보통주식 (주) | - |", "기타주식 (주) | 6,741,575 |",
    "2. 1주당 액면가액 (원) | 100 |",
    "3. 증자전 발행주식총수 (주) | 보통주식 (주) | 39,357,140 |", "기타주식 (주) | - |",
    "4. 자금조달의 목적 | 시설자금 (원) | 20,000,000,000 |", "영업양수자금 (원) | - |", "운영자금 (원) | 10,000,008,750 |",
    "5. 증자방식 | 제3자배정증자 |",
    "※ 기타주식에 관한 사항", "전환으로 발행할 주식수 | 6,741,575 |",
    "6. 신주 발행가액 | 보통주식 (원) | - |", "기타주식 (원) | 4,450 |",
    "12. 신주의 상장 예정일 | - |",
    "17. 이사회결의일(결정일) | 2023년 04월 27일 |",
]
PAID_IPO = [  # HD현대마린솔루션 2024: 상장 공모, '보통주 (주)' / '우선주 (주)'
    "유상증자 결정",
    "기업집단명 | HD현대 | 회사명 | 에이치디현대마린솔루션(주) |",
    "1. 신주의 종류와 수 | 보통주 (주) | 4,450,000 |", "우선주 (주) | - |",
    "2. 1주당 액면가액 (원) | 500 |",
    "3. 증자전 발행주식총수 (주) | 보통주 (주) | 40,000,000 |", "우선주 (주) | - |",
    "4. 자금조달의 목적 | 시설자금 (원) | 54,410,000,000 |", "운영자금 (원) | 22,174,000,000 |",
    "타법인증권 취득자금 (원) | 203,600,000,000 |", "기타자금 (원) | 42,400,000,000 |",
    "5. 증자방식 | 일반공모증자 |",
    "6. 신주 발행가액 | 보통주 (원) | 73,300 |",
    "13. 이사회결의일(결정일) | 2024.03.25 |",
    "14. 증권신고서 제출대상 여부 및 면제시 그 사유 | 제출 대상 |",
    "15. 기타 투자판단에 참고할 사항 | 이사회결의일 2099.01.01 |",
]
PAID_RIGHTS = [  # 한화에어로스페이스 2025 정정: 정정 내역표 뒤 본문, 주주배정
    "정정항목 | 정정전 | 정정후 |",
    "1. 신주의 종류와 수 - 보통주식 | 5,000,000 | 4,267,200 |",
    "유상증자 결정",
    "1. 신주의 종류와 수 | 보통주식 (주) | 4,267,200 |", "기타주식 (주) | - |",
    "2. 1주당 액면가액 (원) | 5,000 |",
    "3. 증자전 발행주식총수 (주) | 보통주식 (주) | 45,581,161 |", "기타주식 (주) | - |",
    "4. 자금조달의 목적 | 시설자금 (원) | 700,020,800,000 |", "타법인 증권 취득자금 (원) | 1,600,000,000,000 |",
    "5. 증자방식 | 주주배정후 실권주 일반공모 |",
    "6. 신주 발행가액 | 확정발행가 | 보통주식 (원) | - |",
    "8. 신주배정기준일 | 2025년 04월 24일 |",
    "9. 1주당 신주배정주식수 (주) | 0.0750828939 |",
    "16. 신주의 상장예정일 | 2025년 06월 25일 |",
    "19. 이사회결의일(결정일) | 2025년 04월 08일 |",
]


def test_paid_fields_third_party_pref_only():
    f = dc.paid_fields(PAID_THIRD)
    assert (f["shares_common"], f["shares_pref"], f["par_won"], f["before_common"]) == (None, 6_741_575, 100, 39_357_140)
    assert f["funds_won"] == 30_000_008_750 and f["method"] == "제3자배정증자"  # '전환으로 발행할 주식수'는 무시
    assert (f["listing_date"], f["board_date"]) == (None, "2023년 04월 27일")


def test_paid_fields_ipo_and_stops_before_notes():
    f = dc.paid_fields(PAID_IPO)
    assert (f["shares_common"], f["shares_pref"], f["par_won"], f["before_common"]) == (4_450_000, None, 500, 40_000_000)
    assert f["funds_won"] == 322_584_000_000 and f["method"] == "일반공모증자" and f["board_date"] == "2024.03.25"


def test_paid_fields_correction_reads_body():
    f = dc.paid_fields(PAID_RIGHTS)
    assert f["shares_common"] == 4_267_200 and f["funds_won"] == 2_300_020_800_000  # 정정전 5,000,000이 아님
    assert (f["record_date"], f["listing_date"], f["board_date"]) == ("2025년 04월 24일", "2025년 06월 25일", "2025년 04월 08일")


def test_paid_doc_row_versions():
    base = dc.listed_only_row({"rcept_no": "20250408002848", "corp_code": "00126566",
                               "report_nm": "[기재정정]주요사항보고서(유상증자결정)"}, "유상증자", "API 응답 없음", None, "piicDecsn")
    row = dc.paid_doc_row(base, PAID_RIGHTS)
    assert row["version"] == "원문 최종본" and row["source"] == "DART 원문" and row["shares_common"] == 4_267_200
    assert dc.paid_doc_row(base, ["유상증자 결정"])["check_result"].startswith("원문 읽었으나")
    failed = dc.paid_doc_row(base, None, "원문을 받지 못함")
    assert failed["version"] == "API 응답 없음" and failed["check_result"].startswith("원문 못 받음")
