"""챗봇 입력 해석 테스트: 금액·종목·주식 수를 규칙으로 읽는지 (한글 숫자, '거의·얼추' 같은 말 포함)."""
import pytest

from core.chat_parse import UNKNOWN, Holding, Parser, korean_number, parse_amount, parse_holdings

KNOWN = {"C사": "C사", "E사": "E사"}


@pytest.mark.parametrize("text,expected", [
    ("이자 한 500만 원", 5_000_000),
    ("500만", 5_000_000),
    ("5,000,000원", 5_000_000),
    ("1억 2천", 120_000_000),
    ("1억 2천만 원", 120_000_000),
    ("1억 3500만", 135_000_000),
    ("1.5억", 150_000_000),
    ("3천만", 30_000_000),
    ("6,000만 원", 60_000_000),
    ("없음", 0),
    ("그런 거 없어요", 0),
])
def test_parse_amount(text, expected):
    r = parse_amount(text)
    assert r.ok and r.value == expected


def test_parse_amount_unknown_and_errors():
    assert parse_amount("잘 모르겠어요").value == UNKNOWN
    assert not parse_amount("글쎄요").ok
    assert not parse_amount("2조 원").ok  # 1조 원 초과는 입력 실수로 봄
    assert parse_amount("500원").value == 500  # '0원'을 '없음'으로 읽지 않음


def test_parse_holdings():
    r = parse_holdings("C사 300주 · E사 1,200주", KNOWN)
    assert r.ok and r.value == [Holding("C사", 300), Holding("E사", 1200)]
    assert parse_holdings("C사300주 그리고 C사 100주", KNOWN).value == [Holding("C사", 400)]
    assert "KIND 고배당기업 목록" in parse_holdings("Z사 10주", KNOWN).error
    assert not parse_holdings("C사 많이", KNOWN).ok
    assert not parse_holdings("C사 0주", KNOWN).ok


REAL = {n: n for n in ["C사", "E사", "삼성전자", "삼성전기", "LG전자", "LG", "케이티앤지", "케이티", "KB금융", "신한지주",
                       "SK가스", "카카오뱅크"]}


@pytest.mark.parametrize("text,expected", [
    ("삼성전자 주식을 한 삼백주쯤 갖고 있어요", [("삼성전자", 300)]),  # 군말·한글 숫자
    ("삼성전자 주식 300주", [("삼성전자", 300)]),  # '주식'을 이름으로 잡지 않음
    ("엘지전자 오십 주요", [("LG전자", 50)]),  # 한글 읽기 ↔ 영문
    ("LG 전자 50주", [("LG전자", 50)]),  # 띄어쓰기
    ("KT&G 200주", [("케이티앤지", 200)]),
    ("에스케이 가스 사십 주", [("SK가스", 40)]),  # '에'로 시작하는 이름을 연결어로 자르지 않음
    ("케이티앤지 이백주하고 삼성전기 백주", [("케이티앤지", 200), ("삼성전기", 100)]),
    ("KB금융 100주랑 신한지주 50주", [("KB금융", 100), ("신한지주", 50)]),
    ("삼성전기를 열다섯 주쯤", [("삼성전기", 15)]),  # 조사 떼기, 고유어 숫자
    ("씨사 삼백 주", [("C사", 300)]),
    ("삼성전자 거의 백 주", [("삼성전자", 100)]),  # '거의'를 회사 이름으로 읽어 빼지 않음
    ("씨사는 얼추 오십 주 가까이", [("C사", 50)]),
])
def test_parse_holdings_real_names(text, expected):
    r = parse_holdings(text, REAL)
    assert r.ok, r.error
    assert sorted((h.company, h.shares) for h in r.value) == sorted(expected)


def test_similar_name_is_suggested_not_chosen():
    r = parse_holdings("카카오 백 주", REAL)
    assert not r.ok and "비슷한 대상 기업: 카카오뱅크" in r.error  # 비슷한 이름은 안내만, 자동으로 고르지 않음
    assert not parse_holdings("애플 10주", REAL).ok
    assert parse_holdings("케이티 오백 주", REAL).value == [Holding("케이티", 500)]  # 케이티 ≠ 케이티앤지


@pytest.mark.parametrize("word,n", [("삼백", 300), ("이천오백", 2500), ("백오십", 150), ("천", 1000), ("삼만오천", 35000),
                                    ("열", 10), ("열다섯", 15), ("스무", 20), ("마흔다섯", 45), ("삼사", None), ("이사", None)])
def test_korean_number(word, n):
    assert korean_number(word) == n


def test_llm_fallback_is_validated_and_logs_no_input():
    calls = []

    def fake_llm(text, kind):
        calls.append(kind)
        return {"amount": 7_000_000} if kind == "amount" else {"holdings": [{"company": "C사", "shares": 50}]}

    p = Parser(KNOWN, llm=fake_llm)
    assert p.amount("오백만쯤").value == 7_000_000 and p.amount("오백만쯤").by == "AI"  # 규칙이 못 읽는 말
    assert p.holdings("씨사는 거의 오십 주 가까이").value == [Holding("C사", 50)]  # 규칙이 못 읽는 문장
    assert p.amount("300만").by == "규칙"  # 규칙이 되면 AI를 부르지 않음
    assert all("오백" not in line for line in p.log)


def test_llm_output_still_checked():
    p = Parser(KNOWN, llm=lambda t, k: {"amount": -5} if k == "amount" else {"holdings": [{"company": "Z사", "shares": 1}]})
    assert not p.amount("이상한 말").ok
    assert not p.holdings("이상한 말").ok


def test_without_llm_failure_stays_failure():
    assert not Parser(KNOWN).amount("글쎄요").ok


def test_ai_amount_needs_number_or_unit_in_sentence():
    # 근거 대조: 문장에 숫자도 금액 단위도 없는데 AI가 금액을 돌려주면 받지 않는다
    p = Parser(KNOWN, llm=lambda t, k: {"amount": 5_000_000})
    r = p.amount("글쎄요 그 정도")
    assert not r.ok and r.by == "AI"
    assert p.amount("오백만 원쯤").value == 5_000_000  # 단위(백·만)가 있으면 받음
    assert p.amount("한 오십쯤 돼요").value == 5_000_000  # 십


def test_preferred_share_gets_its_own_message():
    known = {"삼성전자": "삼성전자", "C사": "C사"}
    r = parse_holdings("삼성전자우 100주", known)
    assert not r.ok
    assert "우선주" in r.error
    assert parse_holdings("삼성전자 100주", known).ok


def test_company_without_shares_is_asked_not_dropped():
    """'C사, E사 100주'처럼 수를 빠뜨린 회사를 조용히 빼지 않고 수를 묻는다(목록에서 여러 회사를 이어 붙일 때)."""
    for text in ("C사, E사 100주", "C사 100주, E사 "):
        r = parse_holdings(text, KNOWN)
        assert r.ok is False and r.code == "missing_shares" and "주식 수도" in r.error
    assert parse_holdings("C사 100주, E사 30주", KNOWN).ok


def test_name_only_input_is_asked_or_explained():
    """첫 화면에서 회사 이름만 적으면 용어 풀이로 넘기지 않고, 수를 묻거나 조회 대상에 없다고 알린다."""
    p = Parser(KNOWN, llm=lambda t, k: {"holdings": []})
    r = p.holdings("C사")
    assert r.code == "missing_shares" and "주식 수도" in r.error
    r = p.holdings("C사스")  # 비슷한 이름만 있는 경우
    assert r.code == "not_found"
    assert p.holdings("배당락이란?").code == ""
    assert parse_holdings("C사", KNOWN).code == "missing_shares"  # 규칙 단계에서 바로 묻는다(AI가 수를 짐작하지 않게)


def test_not_found_says_kind_list_and_rule_beats_empty_ai():
    """목록에 없는 회사는 KIND 고배당기업 목록에 없다고 알리고, AI가 아무것도 못 읽어도 그 안내를 지킨다."""
    p = Parser(KNOWN, llm=lambda t, k: {"holdings": []})
    r = p.holdings("Z사 10주")
    assert r.code == "not_found" and "KIND 고배당기업 목록" in r.error and "분리과세 대상이 아니에요" in r.error
    assert "'Z사'는" in r.error


def test_negative_or_nameless_shares_are_asked_again():
    assert not parse_holdings("C사 -5주", KNOWN).ok
    p = Parser(KNOWN, llm=lambda t, k: {"holdings": [{"company": "10", "shares": 10}]})
    assert "종목 이름도" in p.holdings("10주").error


def test_ai_value_without_number_or_unit_is_not_taken():
    """'그만'·'처음부터'를 AI가 모름·0원으로 읽어 다음 질문으로 넘어가지 않는다."""
    for out in ({"amount": "모름"}, {"amount": 0}, {"amount": 5_000_000}):
        assert not Parser(KNOWN, llm=lambda t, k, o=out: o).amount("그만").ok


@pytest.mark.parametrize("text, want", [
    ("삼십만원", 300_000), ("오십만 원", 500_000), ("백만원", 1_000_000), ("3십만원", 300_000),
    ("1억 오천만", 150_000_000), ("이천오백만원", 25_000_000), ("이자 30만원", 300_000), ("30 만원", 300_000),
    ("1억 2천", 120_000_000),
    # 붙여 쓴 단위: 예전에는 '1억2천만'을 3억 1천만으로 읽었음
    ("1억2천만", 120_000_000), ("1억5천만원", 150_000_000), ("2만5천원", 25_000), ("5천5백만원", 55_000_000),
    ("2천5백만", 25_000_000), ("3억5천", 350_000_000), ("1억오천만", 150_000_000), ("1억 2천 5백", 125_000_000),
])
def test_korean_number_amount_read_by_rule(text, want):
    # 한글 숫자를 AI에 맡기면 '삼십만원'을 300만 원으로 읽은 적이 있어 규칙으로 읽는다
    r = parse_amount(text)
    assert r.ok and r.value == want and r.by == "규칙"


@pytest.mark.parametrize("text", ["-100", "마이너스 5만"])
def test_negative_amount_rejected(text):
    assert not parse_amount(text).ok


def test_preferred_and_fractional_shares_skip_ai():
    calls = []
    p = Parser({"C사": "C사"}, llm=lambda t, k: calls.append(t) or {"holdings": [{"company": "C사", "shares": 10}]})
    assert p.holdings("C사우 10주").code == "preferred"
    assert p.holdings("C사 우선주 10주").code == "preferred"
    assert p.holdings("C사 1.5주").code == "bad_shares"
    assert calls == []  # AI가 우선주를 보통주로 읽지 않게 넘기지 않는다


@pytest.mark.parametrize("text,company", [
    ("C사 -10주", "C사"), ("C사 −10주", "C사"), ("C사 마이너스 10주", "C사"), ("C사 0주", "C사"), ("C사 100주, E사 -5주", "E사"),
])
def test_zero_or_negative_shares_ask_again_with_company(text, company):
    """'삼성전자 -10주'를 용어 질문으로 넘기거나 짐작하지 않고, 회사 이름을 넣어 가진 주식 수를 다시 묻는다."""
    calls = []
    r = Parser(KNOWN, llm=lambda t, k: calls.append(t) or {}).holdings(text)
    assert r.code == "bad_shares" and f"{company}를 몇 주 가지고 계신가요?" in r.error and f"(예: {company} 10주)" in r.error
    assert calls == []


def test_negative_shares_of_unlisted_company_says_not_in_list_first():
    assert parse_holdings("없는회사 -10주", KNOWN).code == "not_found"
    assert parse_holdings("-10주", KNOWN).code == "bad_shares"


@pytest.mark.parametrize("text,want", [
    ("C사 2만 주, E사 3천 주", [("C사", 20000), ("E사", 3000)]),  # 첫 화면 예시처럼 숫자 + 만·천
    ("C사 1만 5천주", [("C사", 15000)]), ("C사 1만5000주", [("C사", 15000)]), ("C사2만주", [("C사", 20000)]),
    ("C사 2천5백 주", [("C사", 2500)]), ("C사 3,000주", [("C사", 3000)]),
])
def test_shares_with_korean_units(text, want):
    r = parse_holdings(text, KNOWN)
    assert r.ok, r.error
    assert [(h.company, h.shares) for h in r.value] == want


QUOTED_KNOWN = {"삼성전자": "삼성전자", "KB금융": "KB금융", "신한지주": "신한지주"}


@pytest.mark.parametrize("text,want", [
    ("'삼성전자' 100주", [Holding("삼성전자", 100)]),
    ('"삼성전자" 100주', [Holding("삼성전자", 100)]),
    ("“삼성전자” 100주", [Holding("삼성전자", 100)]),
    ("‘삼성전자’100주", [Holding("삼성전자", 100)]),
    ("「삼성전자」 10주", [Holding("삼성전자", 10)]),
    ("'KB금융' 10주, '신한지주' 5주", [Holding("KB금융", 10), Holding("신한지주", 5)]),
])
def test_quoted_company_names_are_read(text, want):
    r = parse_holdings(text, QUOTED_KNOWN)
    assert r.ok and r.value == want


def test_quoted_company_without_shares_asks_shares():
    r = parse_holdings("'삼성전자'", QUOTED_KNOWN)
    assert r.code == "missing_shares" and "'" not in r.error
    assert Parser(QUOTED_KNOWN)._name_only("“삼성전자”").code == "missing_shares"


OUTSIDE_KNOWN = {"삼성전자": "삼성전자", "우리금융지주": "우리금융지주", "디와이": "디와이"}


def test_outside_name_drops_particle_when_it_gives_suggestions():
    r = parse_holdings("삼성전자 100주 우리금융도 20주", OUTSIDE_KNOWN, skip_outside=True)
    assert r.ok and r.value == [Holding("삼성전자", 100)]
    assert r.excluded == [("우리금융", ["우리금융지주"])]


def test_outside_name_keeps_last_letter_without_suggestions():
    r = parse_holdings("삼성전자 10주 코스모이 5주", OUTSIDE_KNOWN, skip_outside=True)
    assert r.excluded[0][0] == "코스모이"
