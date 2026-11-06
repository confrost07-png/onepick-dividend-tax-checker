"""금융 상식 찾기: 미리 써 둔 답만 돌려주고, 상관없는 말에는 답하지 않는다."""
from core.faq_search import Faq, FaqSearch, load


def _f(id_: str, title: str, *examples: str) -> Faq:
    return Faq(id_, title, list(examples), f"{title} 답", "출처", "https://example.com")


FAQS = [_f("etf", "ETF", "ETF가 뭐예요"), _f("per", "PER", "주가수익비율 뜻")]


def test_ai_search_returns_saved_answer():
    vectors = [[[1, 0], [1, 0]], [[0, 1], [0, 1]]]
    hit = FaqSearch(FAQS, vectors, embed=lambda texts: [[0.1, 1]]).search("퍼가 뭐야")
    assert hit.faq is FAQS[1] and hit.by == "AI 검색"  # 문장을 만들지 않고 저장된 문항을 돌려줌


def test_ai_search_below_floor_returns_nothing():
    vectors = [[[1, 0, 0]], [[0, 1, 0]]]
    assert FaqSearch(FAQS, vectors, embed=lambda texts: [[0.3, 0.3, 1]]).search("점심 뭐 먹지") is None


def test_text_search_ignores_question_endings():
    s = FaqSearch(FAQS, None, embed=None)
    assert s.search("ETF가 뭐야?").faq.id == "etf"
    assert s.search("오늘 뭐예요?") is None  # '뭐예요'만 겹치는 말은 답하지 않음


def test_falls_back_to_text_search_when_embedding_fails():
    def broken(texts):
        raise ConnectionError("Ollama 꺼짐")

    hit = FaqSearch(FAQS, [[[1, 0]], [[0, 1]]], embed=broken).search("주가수익비율 뜻")
    assert hit.faq.id == "per" and hit.by == "글자 검색"


def test_saved_faq_matches_embeddings_and_has_sources():
    faqs, vectors = load()
    assert faqs and vectors is not None and len(vectors) == len(faqs)
    assert len({f.id for f in faqs}) == len(faqs)
    assert all(f.answer and f.source_label and f.source_url.startswith("https://") for f in faqs)
    for f, vs in zip(faqs, vectors):
        assert len(vs) == len(f.texts())


def test_isa_and_irp_have_saved_answers_with_law_sources():
    s = FaqSearch.from_files(embed=None)
    isa, irp = s.search("ISA가 뭐야?").faq, s.search("개인형퇴직연금 뜻").faq
    assert isa.id == "isa" and isa.source_label == "조세특례제한법 제91조의18"
    assert irp.id == "irp" and irp.source_label == "소득세법 제59조의3"
    # 조문에서 확인한 숫자만 적는다: ISA 비과세 200만·400만 원, 9%; 연금계좌 600만·900만 원, 12%·15%
    assert all(x in isa.answer for x in ("200만 원", "400만 원", "9%"))
    assert all(x in irp.answer for x in ("600만 원", "900만 원", "12%", "15%"))


def test_deposit_cma_ima_have_saved_answers():
    # 글자 검색으로도 예금·적금·CMA·IMA 답을 찾고, 보호 여부는 예금보험공사 안내·금융위원회 보도자료대로 적는다
    s = FaqSearch.from_files(embed=None)
    ids = {q: s.search(q).faq.id for q in ("정기예금이 뭐야", "적금과 예금 차이", "CMA가 뭐예요", "IMA 원금 보장되나요")}
    assert ids == {"정기예금이 뭐야": "deposit", "적금과 예금 차이": "installment", "CMA가 뭐예요": "cma", "IMA 원금 보장되나요": "ima"}
    cma, ima = s.search("CMA가 뭐예요").faq, s.search("IMA가 뭐예요").faq
    assert "종금형 CMA만" in cma.answer and "보호 대상이 아니에요" in cma.answer
    assert all(x in ima.answer for x in ("8조 원", "70%", "중도해지", "예금자보호 대상이 아니에요"))
