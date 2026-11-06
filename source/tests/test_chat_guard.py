"""챗봇 고정 안내 테스트: 세법 해석·종목 추천 질문에는 정해 둔 문구로만 답하는지."""
import pytest

from core import chat_guard
from core import sample_data as data


@pytest.mark.parametrize("text,topic", [
    ("분리과세 신청해야 하나요?", chat_guard.TAX_ADVICE),
    ("어떻게 하면 절세할 수 있어요", chat_guard.TAX_ADVICE),
    ("종합과세가 더 유리한가요", chat_guard.TAX_ADVICE),
    ("C사 지금 사야 할까요?", chat_guard.STOCK_ADVICE),
    ("배당주 추천해 주세요", chat_guard.STOCK_ADVICE),
    ("C사 주가 전망은?", chat_guard.STOCK_ADVICE),
    # 팀원 질문 목록(report/설계/챗봇_질문목록.md)에서 빠져나가던 판단·예측 질문
    ("이거 사도 돼요?", chat_guard.STOCK_ADVICE),
    ("배당금을 받자마자 주식을 팔아도 돼?", chat_guard.STOCK_ADVICE),
    ("현재 배당을 가지고 다음 배당을 예측할 수 있어?", chat_guard.STOCK_ADVICE),
    ("배당을 많이 주는 회사는 좋은 회사야?", chat_guard.STOCK_ADVICE),
    ("배당을 안주는 회사는 나쁜 회사야?", chat_guard.STOCK_ADVICE),
    ("C사 주가 어때?", chat_guard.STOCK_ADVICE),
])
def test_advice_questions_get_fixed_reply(text, topic):
    assert chat_guard.check(text) == topic
    assert chat_guard.FIXED_REPLY[topic]


@pytest.mark.parametrize("text", [
    # 주가·회사라는 말이 들어 있어도 개념을 묻는 질문은 막지 않는다
    "배당락일에는 주가가 왜 떨어지는 거야?",
    "주가가 오르면 내가 받는 배당금도 늘어나는 거야?",
    "C사는 어떤 회사야?",
    "배당수익률이 뭐야?",
    "감액배당과 적자배당의 차이는 뭐야?",
])
def test_concept_questions_are_not_blocked(text):
    assert chat_guard.check(text) is None


def test_normal_answers_are_not_blocked():
    answers = [c for q in data.QUESTIONS for c in q["chips"]]
    answers += data.DIVIDEND_AMOUNT_CHIPS + data.CONFIRM_CHIPS + data.ADDON_CHIPS
    answers += ["C사 300주", "이자 한 500만 원", "국내 주식 500만 원", "종합소득세", "분리과세", "배당 세금"]
    assert [a for a in answers if chat_guard.check(a)] == []


def test_fixed_replies_do_not_recommend():
    for reply in chat_guard.FIXED_REPLY.values():
        assert "신청하세요" not in reply and "유리" not in reply


def test_fixed_replies_are_plain_words_without_law_names():
    # 기획안: 오인을 줄이기 위한 설계이며 법률 적합성을 확정하지 않음 → 고객 문구에 법 이름·조문을 쓰지 않는다
    for reply in chat_guard.FIXED_REPLY.values():
        assert not any(w in reply for w in ("세무사법", "자본시장법", "법률", "의거", "제2조", "조문"))
    assert "세무 전문가" in chat_guard.FIXED_REPLY[chat_guard.TAX_ADVICE]


def test_consult_chip_only_for_tax_topic():
    assert chat_guard.CONSULT_TOPICS == {chat_guard.TAX_ADVICE}


def test_abusive_words_get_their_own_reply():
    for t in ("이 ㅈ같은놈아", "씨발", "병신같네"):
        assert chat_guard.check(t) == chat_guard.ABUSE
    assert chat_guard.check("삼성전자 100주") is None and chat_guard.check("500만 원") is None
    assert chat_guard.ABUSE not in chat_guard.CONSULT_TOPICS


def test_small_talk_gets_fixed_reply_not_glossary():
    for t in ("너 뭐야", "넌 누구야?", "안녕", "고마워요", "뭘 할 수 있어?"):
        assert chat_guard.small_talk(t), t
    for t in ("삼성전자 100주", "500만 원", "없음", "배당락이란?", "하이브 10주"):
        assert chat_guard.small_talk(t) is None, t
