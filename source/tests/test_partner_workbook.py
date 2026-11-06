"""4조참치 대조군 검산표: 값 읽기와 '원문에 없음' / '실재하지만 불러올 수 없음' 구분."""
import csv
import json
import zipfile

from openpyxl import load_workbook

from scripts import export_partner_workbook as pw
from scripts import stream_book as sb
from tests.test_dart_xml import DOC

COMPANY_COLS = ["corp_code", "corp_name", "stock_code", "corp_cls", "acc_mt", "ksic_code", "ksic_name", "method", "reason"]
MANIFEST_COLS = ["corp_code", "corp_name", "period", "report_nm", "rcept_no", "rcept_dt", "version", "is_first",
                 "is_latest_full", "status", "zip_bytes", "n_xml", "zip_error", "notes_sections", "last_api_status", "last_api_time"]


def _csv(path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in rows])


def _line(sj, aid, nm, cur, prev=""):
    return {"rcept_no": "", "sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": cur, "frmtrm_amount": prev}


def _fs(d, year, fs, lines, rcept):
    d.mkdir(parents=True, exist_ok=True)
    body = {"status": "000", "list": [x | {"rcept_no": rcept} for x in lines]} if lines else {"status": "013", "list": []}
    (d / f"{year}_11011_{fs}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _doc(d, rcept, text, enc="utf-8"):
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(d / f"{rcept}.zip", "w") as z:
        z.writestr(f"{rcept}.xml", f'<?xml version="1.0" encoding="utf-8"?><DOCUMENT>{text}</DOCUMENT>'.encode(enc))


def make_src(tmp_path):
    src = tmp_path / "원본"
    _csv(src / "common" / "industry_classification.csv", ["corp_code", "industry"], [])
    _csv(src / "common" / "company_status.csv", ["corp_code", "listed_now", "delist_date", "delist_reason"],
         [{"corp_code": "00000002", "listed_now": "Y"}])
    for folder in pw.INDUSTRIES:
        comps = []
        if folder == "manufacturing":
            comps = [{"corp_code": "00000001", "corp_name": "겹침", "stock_code": "000001", "corp_cls": "Y", "acc_mt": "12"},
                     {"corp_code": "00000002", "corp_name": "대조", "stock_code": "000002", "corp_cls": "K", "acc_mt": "12",
                      "ksic_code": "292", "method": "KSIC자동"}]
        _csv(src / folder / "lists" / "companies.csv", COMPANY_COLS, comps)
        man = []
        if folder == "manufacturing":
            base = {"corp_code": "00000002", "corp_name": "대조", "version": "최초", "is_first": "Y", "is_latest_full": "Y",
                    "status": "수집완료", "last_api_status": "000"}
            man = [base | {"period": "2023.12", "rcept_no": "R2023", "report_nm": "사업보고서 (2023.12)"},
                   base | {"period": "2024.12", "rcept_no": "R2024", "report_nm": "사업보고서 (2024.12)"},
                   base | {"period": "2025.12", "rcept_no": "R2025", "report_nm": "사업보고서 (2025.12)", "status": "미수집",
                           "is_latest_full": "", "last_api_status": "014"}]
        _csv(src / folder / "verify" / "report_manifest.csv", MANIFEST_COLS, man)
    raw = src / "manufacturing" / "raw"
    fn = raw / "fnltt" / "00000002"
    # 2023: 연결, 모든 항목 있음 + 배당금 지급(지배·비지배)
    _fs(fn, 2023, "CFS", [_line("BS", "ifrs-full_Assets", "자산총계", "300"),
                          _line("BS", "ifrs-full_Liabilities", "부채총계", "100"),
                          _line("BS", "ifrs-full_Equity", "자본총계", "200"),
                          _line("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익", "50"),
                          _line("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "배당금의 지급", "-30"),
                          _line("CF", "dart_x", "비지배지분에 대한 배당금 지급", "-5"),
                          _line("CF", "dart_y", "배당금의 수취", "7")], "R2023")
    # 2024: 별도만, 배당 줄 없음 / 원문에도 '배당금 지급' 글자 없음
    _fs(fn, 2024, "CFS", [], "")
    _fs(fn, 2024, "OFS", [_line("BS", "ifrs-full_Assets", "자산총계", "310"),
                          _line("BS", "ifrs-full_Liabilities", "부채총계", "110"),
                          _line("BS", "ifrs-full_Equity", "자본총계", "200"),
                          _line("IS", "ifrs-full_ProfitLoss", "당기순이익", "-9")], "R2024")
    _doc(raw / "documents" / "00000002", "R2023", "배당금의 지급" + DOC)
    _doc(raw / "documents" / "00000002", "R2024", "현금흐름표 자 본 총 계 배당 없음", enc="cp949")
    (raw / "events" / "filings").mkdir(parents=True)
    (raw / "events" / "filings" / "00000002_I.json").write_text(json.dumps({"pages": [{"list": [
        {"rcept_no": "D1", "rcept_dt": "20240215", "report_nm": "현금ㆍ현물배당결정", "flr_nm": "대조"},
        {"rcept_no": "D1", "rcept_dt": "20240215", "report_nm": "현금ㆍ현물배당결정", "flr_nm": "대조"},
        {"rcept_no": "D0", "rcept_dt": "20160215", "report_nm": "현금ㆍ현물배당결정", "flr_nm": "대조"},
        {"rcept_no": "X1", "rcept_dt": "20240301", "report_nm": "유상증자결정", "flr_nm": "대조"}]}]}, ensure_ascii=False), encoding="utf-8")
    return src


def by_year(rows):
    return {r["사업연도"]: r for r in rows}


def test_excludes_our_companies_and_reads_financials(tmp_path):
    p = pw.Partner(make_src(tmp_path), {"00000001"})
    assert [r["corp_code"] for _, r in p.companies] == ["00000002"]
    _, rows, _ = pw.sheet_fin(p)
    assert len(rows) == len(pw.YEARS)
    y = by_year(rows)
    assert (y[2023]["지배주주 순이익(원)"], y[2023]["부채총계(원)"], y[2023]["재무 기준"], y[2023]["원천 열"]) == (50, 100, "연결", "당기")
    assert y[2024]["지배주주 순이익(원)"] == -9 and y[2024]["재무 기준"] == "별도"  # 별도는 당기순이익
    assert y[2023]["사업보고서"].endswith("R2023") and y[2023]["받은 파일"].endswith("documents/00000002/R2023.zip")


def test_missing_values_split_into_two_kinds(tmp_path):
    p = pw.Partner(make_src(tmp_path), {"00000001"})
    y = by_year(pw.sheet_fin(p)[1])
    assert y[2017]["부채총계 상태"] == pw.NO_SOURCE and "사업보고서 없음" in y[2017]["부채총계 사유"]
    assert y[2025]["부채총계 상태"] == pw.CANNOT and "못 받음" in y[2025]["부채총계 사유"]
    assert y[2025]["받은 파일"] is None and y[2025]["사업보고서"].endswith("R2025")


def test_dividends_paid_sums_parent_only_and_checks_document(tmp_path):
    p = pw.Partner(make_src(tmp_path), {"00000001"})
    y = by_year(pw.sheet_cf(p)[1])
    assert (y[2023]["배당금 지급(원)"], y[2023]["비지배지분 배당(원)"], y[2023]["계정 수"]) == (30, 5, 1)
    assert y[2024]["배당금 지급 상태"] == pw.NO_SOURCE and "글자 없음" in y[2024]["배당금 지급 사유"]  # cp949 원문도 읽음


def test_account_lookup_handles_old_codes_other_names_and_totals():
    lines = [_line("BS", "ifrs_Liabilities", "부채총계", "100"),
             _line("BS", "-표준계정코드 미사용-", "부채와자본총계", "300"),
             _line("BS", "-표준계정코드 미사용-", "자본총계", "200"),
             _line("CIS", "-표준계정코드 미사용-", "지배기업소유지분", "40"),
             _line("CIS", "ifrs_ComprehensiveIncomeAttributableToOwnersOfParent", "지배기업소유지분", "45")]
    item = {it[0]: it for it in pw.FIN_ITEMS}
    assert pw.fin_item_line(lines, "CFS", item["부채총계"])["thstrm_amount"] == "100"  # ifrs_ 옛 코드
    assert pw.fin_item_line(lines, "CFS", item["자본총계"])["thstrm_amount"] == "200"  # '부채와자본총계' 건너뜀
    assert pw.fin_item_line(lines, "CFS", item["지배주주 순이익"])["thstrm_amount"] == "40"  # 포괄손익 줄 아님
    paid, _ = pw.dividend_lines([_line("CF", "ifrs_DividendsPaidClassifiedAsFinancingActivities", "배당금", "-3"),
                                 _line("CF", "-표준계정코드 미사용-", "미지급배당금의 증가(감소)", "9")])
    assert [x["account_nm"] for x in paid] == ["배당금"]


def test_blank_amount_on_existing_account_is_no_source(tmp_path):
    src = make_src(tmp_path)
    fn = src / "manufacturing" / "raw" / "fnltt" / "00000002"
    _fs(fn, 2023, "CFS", [_line("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "배당금의 지급", "-")], "R2023")
    y = by_year(pw.sheet_cf(pw.Partner(src, set()))[1])
    assert y[2023]["배당금 지급 상태"] == pw.NO_SOURCE and "비어 있음" in y[2023]["배당금 지급 사유"]


def test_api_gap_with_word_in_document_is_cannot():
    report = {"status": "수집완료", "last_api_status": "000"}
    st, why = pw.missing_status(report, True, "배당금의지급1,000", pw.DIV_WORDS, "배당금 지급")
    assert st == pw.CANNOT and "원문 확인 필요" in why
    assert pw.missing_status(report, True, "", pw.DIV_WORDS, "배당금 지급")[0] == pw.NO_SOURCE
    words_only = pw.missing_status(report, True, "배당금지급은자본에서차감", pw.DIV_WORDS, "배당금 지급", pw.DIV_AMOUNT)
    assert words_only[0] == pw.NO_SOURCE and "금액이 붙은 줄 없음" in words_only[1]
    assert pw.missing_status(report, True, "배당금지급(2,191,157,000)", pw.DIV_WORDS, "배당금 지급", pw.DIV_AMOUNT)[0] == pw.CANNOT
    assert pw.missing_status(None, False, None, pw.DIV_WORDS, "배당금 지급")[0] == pw.NO_SOURCE


def test_decision_list_dedups_and_keeps_period(tmp_path):
    p = pw.Partner(make_src(tmp_path), {"00000001"})
    rows = pw.sheet_decision(p)[1]
    assert [(r["접수번호"], r["공시일"], r["배당금총액 상태"]) for r in rows] == [("D1", "2024-02-15", pw.CANNOT)]


def test_extract_reads_dividend_share_holder_and_status(tmp_path):
    p = pw.Partner(make_src(tmp_path), {"00000001"})
    ex = pw.Extract(p)
    ex.run()
    y = by_year(pw.sheet_div(p, ex)[1])
    assert (y[2023]["현금배당총액 D(원)"], y[2023]["D 원문 값(백만원)"], y[2023]["보통주 주당배당금(원)"]) == (1_200_000_000, 1200, 100)
    assert (y[2021]["현금배당총액 D(원)"], y[2021]["원천 열"]) == (-30_000_000, "전전기")  # 원문 (30) = 음수
    assert y[2022]["D 상태"] == pw.NO_SOURCE and "'-'" in y[2022]["D 사유"]  # 전기 열 '-' = 배당 없음
    assert y[2024]["D 상태"] == pw.NO_SOURCE and "글자도 없음" in y[2024]["D 사유"]  # 받은 원문에 배당 표·글자 없음
    assert y[2025]["D 상태"] == pw.CANNOT  # 원문 못 받음
    items = pw.sheet_div_items(p, ex)[1]
    assert {(r["사업연도"], r["보고서 열"]) for r in items} == {(2023, "당기"), (2022, "전기"), (2021, "전전기")}
    assert next(r for r in items if r["보고서 열"] == "당기")["주당 현금배당금 우선(원)"] == 110
    share = [r for r in pw.sheet_share(p, ex)[1] if r["상태"] == pw.HAS]
    assert [(r["주식 종류"], r["Ⅱ. 현재까지 발행한 주식의 총수"], r["Ⅲ. 현재까지 감소한 주식의 총수"]) for r in share] == \
        [("보통주", 1000, 100), ("합계", 1000, 100)]
    holders = [r for r in pw.sheet_holder(p, ex)[1] if r["상태"] == pw.HAS]
    assert [(r["성명"], r["기말 지분율(%)"], r["합계 행"]) for r in holders] == [("홍길동", 3.0, ""), ("계", 3.0, "Y")]
    missing = [r for r in pw.sheet_holder(p, ex)[1] if r["사업연도"] == 2025]
    assert missing[0]["상태"] == pw.CANNOT


def test_stream_book_splits_and_links(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "MAX_ROWS", 2)
    b = sb.Book(tmp_path / "s.xlsx", link_text={"받은 파일": "받은 파일 열기"})
    cols = [sb.Col("이름", 10, "뜻"), sb.Col("값", 10, "뜻", kind="num"), sb.Col("검산", 10, "뜻", kind="formula"),
            sb.Col("원문", 10, "뜻", kind="link"), sb.Col("받은 파일", 10, "뜻", kind="link")]
    n = b.put("표", "설명", cols, ({"이름": f"r{i}", "값": i, "원문": "https://x/" + str(i), "받은 파일": "원본/a.zip" if i else None}
                                 for i in range(5)), {"검산": lambda L, i: f"={L['값']}{i}*2"})
    b.save([("제목", None), ("고칠 칸", "노란 칸")])
    assert n == 5 and b.counts() == {"표": 2, "표 (2)": 2, "표 (3)": 1}
    wb = load_workbook(tmp_path / "s.xlsx")
    assert wb.sheetnames == ["안내", "진행현황", "항목_설명", "표", "표 (2)", "표 (3)"]
    ws = wb["표 (2)"]
    assert [c.value for c in ws[1]][-3:] == ["검토 상태", "검토자", "메모"]
    assert ws["C2"].value == "=B2*2" and ws["D2"].value == '=HYPERLINK("https://x/2","원문 열기")'
    assert ws["E2"].value == '=HYPERLINK("원본/a.zip","받은 파일 열기")'
    assert len(ws.data_validations.dataValidation) == 2 and ws.freeze_panes == "D2"
    assert wb["진행현황"]["A3"].value == "표 (2)" and wb["진행현황"]["B3"].value == 2


def test_build_writes_all_books(tmp_path):
    src = make_src(tmp_path)
    result = pw.build(src, {"00000001"}, tmp_path, stamp="T", sample=5)
    names = sorted(result)
    assert names == sorted(["4조참치_대조군_검산표_T.xlsx", "4조참치_대조군_재무제표전체_T.xlsx",
                            "4조참치_대조군_공시목록_T.xlsx", "4조참치_대조군_사업보고서표_1_T.xlsx"])
    main = result["4조참치_대조군_검산표_T.xlsx"]
    assert main["02_재무"] == len(pw.YEARS) and main["01_사업보고서목록"] == 3 and main["06_주식총수"] == 4
    assert result["4조참치_대조군_재무제표전체_T.xlsx"]["03-3_현금흐름표"] == 3
    assert result["4조참치_대조군_공시목록_T.xlsx"]["10-3_거래소공시"] == 3  # 같은 접수번호는 한 번
    generic = result["4조참치_대조군_사업보고서표_1_T.xlsx"]
    assert {"표_목록", "DIVIDEND", "TOT_STK", "BSH_SPCL"} <= set(generic)
    wb = load_workbook(tmp_path / "4조참치_대조군_검산표_T.xlsx")
    assert wb.sheetnames[:4] == ["안내", "진행현황", "항목_설명", "00_회사목록"]
    ws = wb["02_재무"]
    head = [c.value for c in ws[1]]
    cell = ws.cell(2 + list(pw.YEARS).index(2023), head.index("받은 파일") + 1)
    assert cell.value.startswith('=HYPERLINK("원본/manufacturing/raw/documents/') and "받은 파일 열기" in cell.value


def test_overlap_group_keeps_only_our_companies(tmp_path):
    src = make_src(tmp_path)
    result = pw.build(src, {"00000001", "99999999"}, tmp_path, stamp="T", sample=5, group="겹침")
    main = result["4조참치_겹침_검산표_T.xlsx"]
    assert main["00_회사목록"] == 1 and main["02_재무"] == len(pw.YEARS)
    wb = load_workbook(tmp_path / "4조참치_겹침_검산표_T.xlsx", read_only=True)
    assert [r[1] for r in wb["00_회사목록"].iter_rows(min_row=2, values_only=True)] == ["00000001"]
    guide = [r[1] for r in wb["안내"].iter_rows(values_only=True) if r[0] == "대상"][0]
    assert "겹치는 1사" in guide and "우리 값" in guide


def test_won_written_in_million_row():
    assert pw.won_written(1_246_337_200, 100, 12_463_372)  # 포인트모바일 2021: 원 단위를 백만원 칸에 적음
    assert not pw.won_written(1_246, 100, 12_463_372)  # 정상 (백만 원)
    assert not pw.won_written(149_369, 17, 24_470_706) and not pw.won_written(None, 100, 1)


def test_profit_split_into_continuing_and_discontinued():
    item = {it[0]: it for it in pw.FIN_ITEMS}["지배주주 순이익"]
    lines = [_line("CIS", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속될 계속영업손익", "-5487666511"),
             _line("CIS", "ifrs-full_IncomeFromDiscontinuedOperationsAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속될 중단영업손익", "9762518207"),
             _line("CIS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분에 귀속되는 당기순이익(손실)", "-155254342")]
    assert pw.fin_item_line(lines, "CFS", item) is None  # 계속영업 줄을 당기순이익으로 고르지 않음
    v, why = pw.split_profit(lines, "CFS", "thstrm_amount")
    assert v == 4274851696 and "계속영업" in why and "중단영업" in why  # 신세계인터내셔날 2025, 우리 팀 값과 같음
    whole = lines + [_line("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분", "4274851696")]
    assert pw.fin_item_line(whole, "CFS", item)["thstrm_amount"] == "4274851696"


def test_owner_profit_labeled_continuing_uses_total_minus_nci():
    item = {it[0]: it for it in pw.FIN_ITEMS}["지배주주 순이익"]
    lines = [_line("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", "-7158078395"),
             _line("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주(계속)", "-6101573232"),
             _line("CIS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분", "-207663333")]
    assert pw.fin_item_line(lines, "CFS", item) is None
    v, why = pw.split_profit(lines, "CFS", "thstrm_amount")
    assert v == -7158078395 + 207663333 and "비지배" in why


def test_continuing_only_nci_is_not_subtracted():
    lines = [_line("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", "-100"),
             _line("CIS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "계속사업손익비지배지분", "-30"),
             _line("CIS", "-표준계정코드 미사용-", "계속사업손익지배기업소유주", "-60"),
             _line("CIS", "-표준계정코드 미사용-", "중단사업손익지배기업소유주", "-5")]
    v, why = pw.split_profit(lines, "CFS", "thstrm_amount")
    assert v == -65 and "계속영업" in why  # 비지배 줄도 계속사업만이라 빼지 않고 계속 + 중단


def test_nci_equal_to_total_is_not_subtracted():
    lines = [_line("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", "37485626338"),
             _line("CIS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분에 귀속되는 당기순이익(손실)", "37485626338")]
    assert pw.split_profit(lines, "CFS", "thstrm_amount") is None  # 화천기공 2022: 0원으로 만들지 않음


def test_owner_profit_rejects_mistagged_lines():
    def L(o, aid, nm, v):
        return _line("CIS", aid, nm, v) | {"ord": str(o)}
    # 신흥 2022: 총포괄손익 뒤 '지배 귀속 당기순이익' 코드 줄(값도 총포괄손익), 비지배 없음 → 당기순이익 전체
    shinheung = [L(19, "ifrs-full_ProfitLoss", "당기순이익(손실)", "8463560875"), L(23, "ifrs-full_ComprehensiveIncome", "총포괄손익", "8230366888"),
                 L(25, "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익(손실)", "8230366888")]
    assert pw.owner_profit(shinheung, "thstrm_amount")[0] == 8463560875
    # 삼성전기 2022: 코드 붙은 줄은 계속영업 몫, 이름만 있는 줄이 검산에 맞음
    sem = [L(15, "ifrs-full_ProfitLoss", "당기순이익", "993519182170"), L(24, "ifrs-full_ComprehensiveIncome", "총포괄이익", "983918103008"),
           L(26, "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분", "1009738691180"),
           L(27, "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분", "12967540043"),
           L(29, "-표준계정코드 미사용-", "지배기업 소유주지분", "980551642127")]
    assert pw.owner_profit(sem, "thstrm_amount")[0] == 980551642127
    # 사조산업 2022: 지배 줄이 10억 틀림(지배+비지배≠당기순이익) → 원문 줄 그대로 쓰고 '검산 안 맞음' 표시
    sajo = [L(12, "ifrs-full_ProfitLoss", "당기순이익(손실)", "80131865013"), L(23, "ifrs-full_ComprehensiveIncome", "총포괄손익", "79436980901"),
            L(25, "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익(손실)", "68890699663"),
            L(26, "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분에 귀속되는 당기순이익(손실)", "10241165350")]
    v, why = pw.owner_profit(sajo, "thstrm_amount")
    assert v == 68890699663 and "검산 안 맞음" in why
    # 삼아제약 2024: 당기순이익 뒤 지배 줄, 비지배 줄 없음 → 그 줄 (검산 안 맞음 표시)
    sama = [L(12, "ifrs-full_ComprehensiveIncome", "총포괄손익", "24083061587"), L(32, "ifrs-full_ProfitLoss", "당기순이익(손실)", "22079574395"),
            L(35, "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업소유주지분", "22085766635")]
    v, why = pw.owner_profit(sama, "thstrm_amount")
    assert v == 22085766635 and "검산 안 맞음" in why
    # JW생명과학 2024: 앞쪽 총포괄손익 귀속 '지배기업의 소유주지분'은 버리고 당기순이익 귀속 줄
    jw = [L(9, "ifrs-full_ComprehensiveIncome", "총포괄손익", "49138818416"), L(12, "dart_x", "지배기업의 소유주지분", "49138818416"),
          L(31, "ifrs-full_ProfitLoss", "당기순이익(손실)", "43987530998"), L(34, "-표준계정코드 미사용-", "지배기업의 소유주지분", "43987530998")]
    assert pw.owner_profit(jw, "thstrm_amount")[0] == 43987530998