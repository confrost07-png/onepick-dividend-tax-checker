"""PDF 전 쪽 OCR: 출력 읽기, 다시 읽은 결과 고르기, 검토 대상 가르기, 검토표 왕복."""
from scripts import check_ocr_quality as cq
from scripts import export_ocr_review as ex
from scripts import load_ocr_review as ld
from scripts import ocr_policy_docs as op

OUT = "1\t2\t0.300\t0.650\t1.000\x1f기업가치 제고 계획\n0.300\x1f또#포들\f2\t0\t1.000\t1.000\t"


def test_parse_reads_lines_confidence_and_blank_page():
    got = op.parse(OUT, 2.5)
    assert got[1].lines == [(1.0, "기업가치 제고 계획"), (0.3, "또#포들")]
    assert got[1].low == ["또#포들"] and got[1].chars == len("기업가치제고계획또#포들")
    assert got[2].lines == [] and got[2].chars == 0 and got[2].scale == 2.5


def test_better_prefers_fewer_low_lines_then_more_text():
    a = op.PageOCR(1, [(0.3, "깨짐"), (1.0, "배당")], 2.5)
    b = op.PageOCR(1, [(1.0, "배당 성향")], 4.0)
    c = op.PageOCR(1, [(1.0, "배당 성향 30%")], 4.0)
    assert op.better(a, b) is b
    assert op.better(b, c) is c


def test_classify_sends_ocr_only_and_low_pages_to_review():
    ok = op.PageOCR(1, [(1.0, "글자")], 2.5)
    low = op.PageOCR(1, [(0.3, "깨짐")], 4.0)
    blank = op.PageOCR(1, [], 4.0)
    assert op.classify(500, ok) == ("글자 있음", False, None)      # 글자층이 정답, OCR은 보충
    assert op.classify(500, low) == ("글자 있음", True, 1)         # 글자층이 있어도 낮은 줄이 남으면 검토
    assert op.classify(0, blank) == ("빈 쪽", True, 2)
    assert op.classify(10, ok) == ("글자 있음", True, 3)           # OCR만 출처
    assert op.classify(500, blank) == ("빈 쪽", False, None)
    assert op.classify(0, None) == ("실패", True, 1)


def test_review_roundtrip_checks_states_and_corrections(tmp_path):
    base = ["1 낮은 줄 남음", "가나다", "20260101000001", "11-1", 3, "../raw/ocr_pages/x.png", "https://x", 0, 20, 1, 4.0,
            "또#포들", "배당 또#포들"]
    data = [base + ["정정함", "김민지", "배당 성향 30%", None],
            base[:4] + [4] + base[5:] + ["확인완료", "조진영", None, "순서만 다름"],
            base[:4] + [5] + base[5:] + ["정정함", "박예지", None, None],       # 정정 글자 없음 → 넣지 않음
            base[:4] + [6] + base[5:] + ["확인완료", "아무개", None, None],       # 목록에 없는 검토자 → 넣지 않음
            base[:4] + [7] + base[5:] + [None, None, None, None]]               # 검토 전 → 건너뜀
    path = tmp_path / "ocr.xlsx"
    ex.write(data, path)
    items, problems = ld.rows_from(path)
    assert [(i["page"], i["review_status"], i["corrected_text"]) for i in items] == [
        (3, "정정함", "배당 성향 30%"), (4, "확인완료", None)]
    assert items[1]["review_note"] == "순서만 다름" and items[0]["dcm_no"] == "11-1"
    assert len(problems) == 2 and "정정 글자가 비어" in problems[0] and "목록에서" in problems[1]


def test_word_recall_ignores_reading_order():
    assert cq.word_recall("배당 성향 30% 목표", "목표\n30%\n배당 성향") == (4, 4)
    assert cq.word_recall("배당 성향", "배당") == (1, 2)


def test_ai_review_applies_exact_edits_and_rejects_bad_ones():
    from scripts import ocr_ai_review as ai
    page = {"text": "백화점업 영업이익 규모(*))\n(출처: 통계청)\n1.12"}
    good = {"key": "k", "status": "정정함", "edits": [{"from": "규모(*))", "to": "규모(*1)"}], "add": ["0.66"]}
    assert ai.check(page, good) == []
    assert ai.apply(page["text"], good["edits"], good["add"]) == "백화점업 영업이익 규모(*1)\n(출처: 통계청)\n1.12\n0.66"
    assert "from이 OCR 글자에 없음" in ai.check(page, {"status": "정정함", "edits": [{"from": "없는 글자", "to": "x"}]})[0]
    assert ai.check(page, {"status": "확인완료", "add": ["x"]}) == ["edits·add가 있으면 status는 정정함"]
    assert ai.check(page, {"status": "정정함"}) == ["정정함이면 edits나 add가 있어야 함"]
    assert ai.check(page, {"status": "확인완료"}) == []


def test_supplement_keeps_only_lines_missing_from_layer():
    from core.policy_docs import supplement_lines
    layer = "부채총계 1,234\n자본총계 5,678\n주주환원 정책을 강화합니다"
    ocr = "자본총계 5,678\n주주환원 정책을 강화함니다\n2,107\n('23~'27 CAGR 14.1%)\n그림 속 새 문장\n2,107\nㅁ"
    got = supplement_lines(layer, ocr)
    assert "자본총계 5,678" not in got  # 글자층에 그대로 있음
    assert "주주환원 정책을 강화함니다" not in got  # 숫자 없는 OCR 오타 줄
    assert got == ["2,107", "('23~'27 CAGR 14.1%)", "그림 속 새 문장"]  # 그래프 값·새 문장, 반복·한 글자는 뺌
    assert supplement_lines("1,234억", "1,284억") == ["1,284억"]  # 숫자 든 줄은 그대로 같을 때만 중복


def test_page_chunks_one_set_per_page():
    from core.policy_docs import page_chunks
    long_layer = "기업가치 제고 계획의 배당 목표와 자사주 소각 계획을 설명합니다 " * 2
    got = page_chunks(long_layer, "기업가치 제고 계획\n2,107", "기업가치 제고 계획\n2,104")
    assert [m for m, _ in got] == ["글자층", "OCR 정정 보충"] and "2,104" in got[1][1]
    assert page_chunks("03", "그림 속 글자 1,915", None) == [("OCR", "그림 속 글자 1,915")]  # 그림 쪽은 OCR 한 벌
    assert page_chunks("03", "", None) == [("글자층", "03")]  # OCR도 비면 짧은 글자층이라도 남김


def test_human_sample_is_stratified_and_reproducible():
    rows = [{"reviewer": "Claude(AI)", "review_priority": p, "review_status": s, "i": i}
            for i, (p, s) in enumerate([(1, "정정함")] * 80 + [(3, "확인완료")] * 20)]
    rows.append({"reviewer": "박예지", "review_priority": 1, "review_status": "정정함", "i": 999})  # 사람 검토는 뽑지 않음
    got = ex.sample(rows, 10, seed=0)
    assert [r["i"] for r in got] == [r["i"] for r in ex.sample(rows, 10, seed=0)]  # 시드 고정
    kinds = [(r["review_priority"], r["review_status"]) for r in got]
    assert kinds.count((1, "정정함")) == 8 and kinds.count((3, "확인완료")) == 2 and all(r["i"] != 999 for r in got)
