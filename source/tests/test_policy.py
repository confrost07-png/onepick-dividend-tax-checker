"""F-03·F-07: 정책 문장 뽑기, 검토표 왕복, 확인완료만 목표로."""
from core import company_repo as cr
from core import policy_extract as pe
from scripts import export_policy_review as ex
from scripts import load_policy_review as ld

LINES = ["1. 계획서 명칭 | 2026년 가나다 기업가치 제고 계획 |",
         "2. 주요 내용 | <목표설정> - 배당성향 20% 이상으로 주주환원 정책 지속 유지 - 자사주 100만주 소각 - 설비 투자 확대 |"]


def test_extract_reads_categories_and_targets():
    items = pe.extract(LINES)
    assert [(i.category, i.target_kind, i.target_value) for i in items] == [
        ("배당 목표", "배당성향", "20"), ("자사주", "", ""), ("투자 계획", "", "")]
    assert pe.read_target("주주환원 : 배당성향 30% 이상(별도 재무제표상 당기순이익 기준)")[2].startswith("별도 기준")
    assert pe.read_target("DPS 3,500원 이상 배당") == ("주당배당금", "3500", "유통주식 수가 있어야 총액으로 환산")


def test_review_roundtrip_keeps_only_confirmed(tmp_path):
    row = [1, "가나다", "00000001", "기업가치제고계획", "20260101000001", "2026-01-01", 1, "2. 주요 내용", "본문", "배당 목표",
           "배당성향 20% 이상", "배당성향", "20", "", 1_000.0, "https://x", None, "확인완료", "박예지", "예", "2025", None]
    other = row[:6] + [2] + row[7:17] + ["확인불가", "박예지", "아니오", None, None]
    path = tmp_path / "r.xlsx"
    ex.write([row, other], path)
    got = ld.rows_from(path)
    assert len(got) == 1 and got[0]["use_as_target"] and got[0]["target_value"] == "20" and got[0]["reviewer"] == "박예지"
    assert got[0]["target_year"] == 2025
    t = cr._target({**got[0], "rcept_no": "20260101000001"}, 5_000)
    assert (t.kind, t.value, t.denominator, t.denominator_is_tax_basis) == ("배당성향", "20", 5_000, True)


def test_review_file_prefills_reviewer_and_counts_progress(tmp_path):
    from openpyxl import load_workbook
    row = [1, "가나다", "00000001", "기업가치제고계획", "20260101000001", "2026-01-01", 1, "첨부 계획.pdf 3쪽", "OCR",
           "배당 목표", "DPS 3,500원 이상", "주당배당금", "3500", "", None, "https://x", None, None, None, None, None, None]
    path = tmp_path / "r.xlsx"
    ex.write([row], path, reviewer="박예지")
    wb = load_workbook(path)
    assert wb.sheetnames == ["안내", "검토표", "진행현황"]
    ws = wb["검토표"]
    assert ws.cell(2, ex.NAMES.index("검토자") + 1).value == "박예지"
    assert ws.cell(1, ex.YELLOW_FROM).value == "검토 상태"
    p = wb["진행현황"]
    assert p["B2"].value == "가나다" and p["C2"].value.startswith("=COUNTIFS(검토표!$B$2:$B$2")
    assert ld.rows_from(path) == []  # 검토 상태를 비워 두면 아무것도 들어가지 않는다


def test_attachment_paragraph_category():
    assert ex.category("2025년부터 배당성향 50% 이상을 목표로") == "배당 목표"
    assert ex.category("자기주식 1조 원 매입 후 전량 소각") == "자사주"
    assert ex.category("회사 연혁 소개") is None


def test_past_target_implementation_from_repo():
    from core.valueup import PastTarget
    dv = {("C", 2025): {"d_dart_won": 600}, ("C", 2024): {"d_dart_won": 400}}
    fin = {("C", 2025): {"ni_owner_won": 1_000}, ("C", 2024): {"ni_owner_won": 1_000}}
    text = cr._implementation([PastTarget(2024, "배당성향", "50", "", "R1"), PastTarget(2025, "배당성향", "50", "", "R2")],
                              dv, fin, {}, "C")
    assert text.startswith("2025 사업연도 배당성향 목표 50.0% → 실제 60.0% (목표 이상 배당) (계획 R2)")
    assert "2024 사업연도 배당성향 목표 50.0% → 실제 40.0% (목표 미만 배당)" in text
    assert cr._implementation([PastTarget(2023, "주당배당금", "100", "", "R0")], dv, fin, {}, "C") is None


def test_bundle_zips_review_file_with_page_images(tmp_path, monkeypatch):
    import zipfile
    from io import BytesIO

    from openpyxl import load_workbook
    from PIL import Image
    data_root = tmp_path / "data"
    pages = data_root / "raw" / "ocr_pages"
    pages.mkdir(parents=True)
    Image.new("RGB", (2000, 1000), "white").save(pages / "20260101000001_111-1_003.png")
    monkeypatch.setattr(ex, "DATA_ROOTS", [data_root])
    page = {"rcept_no": "20260101000001", "dcm_no": "111-1", "page": 3, "file_path": "raw/policy_docs/x.pdf"}
    row = [1, "가나다", "00000001", "기업가치제고계획", "20260101000001", "2026-01-01", 1, "첨부 계획.pdf 3쪽", "OCR",
           "배당 목표", "DPS 3,500원 이상", "주당배당금", "3500", "", None, "https://x", page, None, None, None, None, None]
    body = row[:6] + [2, "2. 주요 내용", "본문"] + row[9:16] + [None] + row[17:]
    out = tmp_path / "묶음.zip"
    assert ex.bundle([row, body, row], out, "박예지") == {"기존 그림": 1, "새로 그림": 0}
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert sorted(names) == ["묶음/묶음.xlsx", "묶음/쪽그림/20260101000001_111-1_003.jpg"]
        assert Image.open(BytesIO(z.read(names[1]))).width == ex.MAX_WIDTH  # 넓은 쪽은 줄인다
        ws = load_workbook(BytesIO(z.read("묶음/묶음.xlsx")))["검토표"]
    link = ws.cell(2, ex.PAGE_COL)
    assert link.value == "쪽 그림 열기" and link.hyperlink.target == "쪽그림/20260101000001_111-1_003.jpg"
    assert ws.cell(3, ex.PAGE_COL).value is None  # 본문 행은 쪽 그림 없음


def test_plain_review_file_has_no_page_links(tmp_path):
    from openpyxl import load_workbook
    page = {"rcept_no": "R", "dcm_no": "1-1", "page": 1, "file_path": "x.pdf"}
    row = [1, "가나다", "00000001", "공시", "R", "2026-01-01", 1, "첨부 1쪽", "OCR", "배당 목표", "글", "", "", "", None,
           "https://x", page, None, None, None, None, None]
    ex.write([row], tmp_path / "r.xlsx")
    assert load_workbook(tmp_path / "r.xlsx")["검토표"].cell(2, ex.PAGE_COL).value is None


def test_root_rcept_no_from_dart_page_and_latest_versions():
    from core.policy_docs import latest_versions, root_rcept_no
    page = 'alertInvestNotice("20260305900603", "11010190", "20260303901449", "3", "99998" ,"HTML");'
    assert root_rcept_no(page, "20260305900603") == "20260303901449"  # 정정 공시 → 처음 낸 공시
    assert root_rcept_no(page, "20260303901449") is None  # 다른 공시 화면이면 읽지 않음
    assert root_rcept_no("<html></html>", "1") is None
    # 코메론처럼 정정이 두 번이면 가장 늦은 판이 최신, 최초 번호를 모르면 자기 묶음
    got = latest_versions([("20260303901449", "20260303901449"), ("20260305900603", "20260303901449"),
                           ("20261007900308", "20260303901449"), ("20250101000001", None)])
    assert set(got.values()) == {"20261007900308", "20250101000001"}
    assert got["20260303901449"] == "20261007900308"
