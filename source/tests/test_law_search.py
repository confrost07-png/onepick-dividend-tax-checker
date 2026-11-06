"""관련 조문 찾기: 실제 Ollama 없이 가짜 임베딩과 저장된 원문으로 확인한다."""
import json
import urllib.request

import pytest

from core import law_search
from core.law_search import LawSearch, Passage, _clean_formula, _overlap, load, parse_article, select

HTML = """<div class="lawcon">
<p><label>제1조(시험 조문)</label> ① 첫째 항이다. </p>
<p>1. 첫째 호 </p>
<p>② 세율은 다음과 같다.<br /><img alt="세율표
2천만원 이하 @@LATEX@@100분의 14@@/LATEX@@" src="x" /></p>
<p><span>[본조신설 2025. 12. 23.]</span></p>
</div><span>[시행 2026. 9. 18.]</span>"""


def _p(text: str) -> Passage:
    return Passage("법", "제1조(가)", "", text, "u", "")


def test_parse_article_keeps_text_and_attaches_items_to_paragraph():
    ps = parse_article(HTML, "시험법", "url")
    assert [p.paragraph for p in ps] == ["①", "②"]
    assert ps[0].article == "제1조(시험 조문)" and ps[0].effective == "2026. 9. 18."
    assert ps[0].text == "① 첫째 항이다.\n1. 첫째 호"
    assert "2천만원 이하 100분의 14" in ps[1].text and "LATEX" not in ps[1].text
    assert ps[0].label == "시험법 제1조①"


def test_ai_search_ranks_by_similarity_and_returns_original_text():
    passages = [_p("배당성향 계산"), _p("세율표"), _p("공시 방법")]
    vectors = [[1, 0], [0, 1], [0.7, 0.7]]
    s = LawSearch(passages, vectors, embed=lambda texts: [[1, 0.1]])
    hits = s.search("배당성향은 어떻게 계산해요?")
    assert hits[0].passage.text == "배당성향 계산" and hits[0].by == "AI 검색"
    assert all(h.passage in passages for h in hits)  # 문장을 만들지 않고 저장된 원문만 돌려줌


def test_unrelated_question_returns_nothing():
    s = LawSearch([_p("배당성향 계산")], [[1, 0]], embed=lambda texts: [[0, 1]])
    assert s.search("오늘 점심 뭐 먹지") == []


def test_falls_back_to_text_search_when_embedding_fails():
    def broken(texts):
        raise ConnectionError("Ollama 꺼짐")

    s = LawSearch([_p("배당성향 계산 방법"), _p("공시 방법")], [[1, 0], [0, 1]], embed=broken)
    hits = s.search("배당성향 계산")
    assert hits and hits[0].by == "글자 검색" and hits[0].passage.text == "배당성향 계산 방법"


def test_saved_corpus_matches_embeddings_and_sources():
    passages, vectors = load()
    assert passages and vectors is not None and len(vectors) == len(passages)
    labels = {p.label for p in passages}
    assert "조세특례제한법 제104조의27①" in labels and "소득세법 시행령 제26조의3⑥" in labels
    assert all(p.url.startswith("https://www.law.go.kr/") and p.effective for p in passages)


# --- 호 고르기·빌드 안정성 ---

ITEMS = Passage("소득세법", "제14조(과세표준의 계산)", "③",
                "③ 다음 각 호에 따른 소득은 합산하지 아니한다.  <개정 2023. 12. 31.>\n"
                "5. 분리과세되는 소득\n6. 2천만원 이하인 소득\n7. 주택임대소득\n가. 첫째 목", "u", "e")


def test_select_picks_items_with_paragraph_head_and_keeps_text():
    ps = select([ITEMS], ("③6", "③7"), "시험")
    assert [p.label for p in ps] == ["소득세법 제14조③6호", "소득세법 제14조③7호"]
    assert ps[0].text == "③ 다음 각 호에 따른 소득은 합산하지 아니한다.  <개정 2023. 12. 31.>\n6. 2천만원 이하인 소득"
    assert ps[1].text.endswith("7. 주택임대소득\n가. 첫째 목")  # 딸린 목은 그 호에 붙음
    assert select([ITEMS], ("③",), "시험") == [ITEMS]


@pytest.mark.parametrize("keep", [("③9",), ("④",), ("③5", "③10")])
def test_select_fails_when_any_kept_paragraph_or_item_is_missing(keep):
    with pytest.raises(RuntimeError):
        select([ITEMS], keep, "시험")


def test_embed_text_adds_title_and_alias_but_not_history():
    p = Passage("조세특례제한법", "제91조의18(개인종합자산관리계좌에 대한 과세특례)", "②",
                "② 비과세 한도금액은 다음과 같다.  <개정 2021. 12. 28.>", "u", "e")
    t = p.embed_text
    assert "ISA" in t and "개인종합자산관리계좌에 대한 과세특례" in t and "<개정" not in t
    assert "ISA" not in p.text  # 화면 원문은 그대로


def test_clean_formula_removes_latex_marks():
    s = _clean_formula("@@LATEX@@2천만원 \\times \\left[1 + 연수\\right]- 누적@@/LATEX@@")
    assert s == "2천만원 × [1 + 연수]- 누적"
    with pytest.raises(ValueError):
        _clean_formula("\\frac{1}{2}")


def test_effective_date_notice_is_not_attached_to_paragraph():
    html = """<div class="lawcon"><p>제1조(시험) ① 첫째 항.</p><p>② 둘째 항.</p>
<p>[전문개정 2009. 12. 31.]</p><p>[시행일: 2027. 1. 1.] 제1조제2항(가에 관한 부분에 한정한다)</p></div>"""
    ps = parse_article(html, "시험법", "u")
    assert ps[-1].text == "② 둘째 항."


def test_text_search_does_not_favor_long_passages():
    short, long_ = "배당소득 원천징수 세율", "배당소득 원천징수 세율 " + "다른 소득 " * 300
    assert _overlap("배당소득 원천징수", short) > _overlap("배당소득 원천징수", long_)


def test_load_warns_when_embedding_labels_do_not_match(tmp_path, monkeypatch):
    a, e = tmp_path / "a.json", tmp_path / "e.json"
    monkeypatch.setattr(law_search, "ARTICLES_PATH", a)
    monkeypatch.setattr(law_search, "EMBEDDINGS_PATH", e)
    monkeypatch.setattr(law_search, "DATA_DIR", tmp_path)
    p1, p2 = Passage("법", "제1조(가)", "①", "가", "u", "e"), Passage("법", "제1조(가)", "②", "나", "u", "e")
    law_search.save([p1, p2], [[1.0, 0.0], [0.0, 1.0]])
    assert load() == ([p1, p2], [[1.0, 0.0], [0.0, 1.0]])
    assert not list(tmp_path.glob("*.tmp"))
    emb = json.loads(e.read_text(encoding="utf-8"))
    emb["labels"] = ["법 제1조②", "법 제1조①"]
    e.write_text(json.dumps(emb), encoding="utf-8")
    with pytest.warns(UserWarning):
        assert load()[1] is None
    assert law_search.diff([p1], [Passage("법", "제1조(가)", "①", "바뀜", "u", "e"), p2]) == \
        {"바뀜": ["법 제1조①"], "추가": ["법 제1조②"], "빠짐": []}


# --- 저장된 원문 ---

def test_saved_corpus_has_new_labels_and_clean_text():
    passages, _ = load()
    by = {p.label: p for p in passages}
    for label in ["소득세법 제14조③5호", "소득세법 제14조③6호", "소득세법 제129조①2호",
                  "조세특례제한법 제129조의2①", "지방세특례제한법 제167조의6", "조세특례제한법 제91조의18②"]:
        assert label in by, label
    assert "2천만원" in by["소득세법 제14조③6호"].text
    assert "100분의 14" in by["소득세법 제129조①2호"].text
    assert "100분의 10" in by["지방세특례제한법 제167조의6"].text
    assert "소득세법 제14조③" not in by and "소득세법 제129조①" not in by  # 긴 항 전체는 넣지 않음
    for p in passages:
        assert "\\" not in p.text and "＠＠" not in p.text and "@@" not in p.text and "\n\n" not in p.text, p.label
        assert "[시행일" not in p.text, p.label
    # 칼럼(app/web/src/columns/*.ts)이 쓰는 라벨은 그대로 있어야 함
    for label in ["조세특례제한법 제104조의27①", "조세특례제한법 제104조의27②", "조세특례제한법 제104조의27③",
                  "조세특례제한법 제104조의27④", "조세특례제한법 시행령 제104조의24②", "조세특례제한법 시행령 제104조의24③",
                  "조세특례제한법 시행령 제104조의24④", "조세특례제한법 시행령 제104조의24⑤",
                  "조세특례제한법 시행령 제104조의24⑥", "조세특례제한법 시행규칙 제47조의3", "소득세법 시행령 제26조의3⑥"]:
        assert label in by, label


def test_saved_embeddings_are_paired_by_label():
    passages, vectors = load()
    labels = json.loads(law_search.EMBEDDINGS_PATH.read_text(encoding="utf-8"))["labels"]
    assert vectors is not None and labels == [p.label for p in passages]


# --- 실제 저장 벡터로 도는 순위 회귀 (Ollama bge-m3가 없으면 건너뜀) ---

def _ollama_ready() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return any(m["name"].startswith("bge-m3") for m in json.loads(r.read())["models"])
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_ready(), reason="Ollama bge-m3가 켜져 있지 않음")
@pytest.mark.parametrize("query, want, within", [
    ("고배당 분리과세 신청", ("조세특례제한법 시행령 제104조의24⑥", "조세특례제한법 제104조의27③"), 2),  # 화면 예시 문구
    ("ISA 비과세 한도", ("조세특례제한법 제91조의18②",), 1),
    ("ISA 계좌에서 받은 배당도 고배당 분리과세가 되나요", ("조세특례제한법 제91조의18①", "조세특례제한법 제91조의18②"), 3),
    ("금융소득이 2천만 원 이하면 종합과세 안 하나요", ("소득세법 제14조③6호",), 1),
    ("배당소득 원천징수 세율", ("소득세법 제129조①2호",), 1),
    ("직전 3년 금융소득종합과세 대상이면 ISA 가입 못하나요", ("조세특례제한법 제129조의2①",), 1),
    ("지방소득세는 얼마인가요", ("지방세특례제한법 제167조의6",), 1),
    ("배당성향은 어떻게 계산해요?", ("조세특례제한법 시행령 제104조의24④",), 1),
    ("고배당기업 요건", ("조세특례제한법 제104조의27④",), 1),
    ("분리과세 세율은 얼마인가요", ("조세특례제한법 제104조의27②",), 1),
    ("감액배당도 배당소득인가요", ("소득세법 시행령 제26조의3⑥",), 1),
])
def test_real_ranking_regression(query, want, within):
    hits = LawSearch.from_files().search(query, top_k=3)
    assert hits and hits[0].by == "AI 검색"
    top = [h.passage.label for h in hits[:within]]
    if within == 2 and len(want) == 2:
        assert set(top) == set(want), top
    else:
        assert any(w in top for w in want), top
