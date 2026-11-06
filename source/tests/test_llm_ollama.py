"""Ollama 연결: 실제 Ollama 없이 가짜 응답으로 확인한다 (꺼짐·시간 초과·깨진 JSON·이상한 값)."""
import json
import urllib.error

import pytest

from core import llm_ollama
from core.chat_parse import UNKNOWN, Holding, Parser

KNOWN = {"C사": "C사", "E사": "E사"}


def _reply(content) -> dict:
    return {"message": {"content": json.dumps(content) if not isinstance(content, str) else content}}


def _llm(response=None, error=None, calls=None):
    def post(url, payload, timeout):
        if calls is not None:
            calls.append((url, payload))
        if error is not None:
            raise error
        return response

    return llm_ollama.make_llm(post=post)


def test_amount_and_holdings_are_extracted():
    assert _llm(_reply({"amount": 5_000_000, "unknown": False}))("오백만 원쯤", "amount") == {"amount": 5_000_000}
    assert _llm(_reply({"amount": None, "unknown": True}))("잘 몰라", "amount") == {"amount": UNKNOWN}
    out = _llm(_reply({"holdings": [{"company": "C사", "shares": 300}]}))("씨사 삼백 주", "holdings")
    assert out == {"holdings": [{"company": "C사", "shares": 300}]}


def test_request_is_local_json_format_and_deterministic():
    calls = []
    _llm(_reply({"amount": 1, "unknown": False}), calls=calls)("한 주", "amount")
    url, payload = calls[0]
    assert url.startswith("http://localhost:11434/")
    assert payload["format"] == llm_ollama.SCHEMAS["amount"]
    assert payload["options"]["temperature"] == 0 and payload["stream"] is False


@pytest.mark.parametrize("error", [
    urllib.error.URLError("connection refused"),  # Ollama 꺼짐
    TimeoutError("timed out"),  # 응답 늦음
])
def test_connection_problems_return_empty(error):
    assert _llm(error=error)("오백만 원", "amount") == {}


@pytest.mark.parametrize("response", [
    _reply("{깨진 json"),  # 깨진 JSON
    {"unexpected": True},  # 응답 모양 다름
    _reply({"amount": "오백만", "unknown": False}),  # 숫자가 아닌 값
    _reply({"amount": True, "unknown": False}),  # bool
    _reply({"holdings": [{"company": 3, "shares": 10}]}),  # 회사 이름이 문자열 아님
    _reply({"holdings": "C사 300주"}),  # 목록 아님
])
def test_strange_outputs_return_empty(response):
    kind = "holdings" if "holdings" in json.dumps(response, ensure_ascii=False) else "amount"
    assert _llm(response)("문장", kind) == {}


def test_unknown_kind_returns_empty():
    assert _llm(_reply({"amount": 1, "unknown": False}))("문장", "주소") == {}


def test_non_local_url_is_refused():
    with pytest.raises(ValueError):
        llm_ollama.make_llm(url="https://api.example.com")


def test_parser_still_validates_ai_values():
    """AI가 뽑은 값도 Parser의 검사를 거친다: 목록에 없는 회사·음수 금액은 통과 못 함."""
    p = Parser(KNOWN, llm=_llm(_reply({"holdings": [{"company": "Z사", "shares": 10}]})))
    assert not p.holdings("제트사 열 주").ok
    p = Parser(KNOWN, llm=_llm(_reply({"amount": -5, "unknown": False})))
    assert not p.amount("마이너스 오 원").ok
    p = Parser(KNOWN, llm=_llm(_reply({"holdings": [{"company": "C사", "shares": 300}]})))
    r = p.holdings("씨사꺼 삼백개 있어요")  # "주" 없이 "개"로 써서 규칙으로는 못 읽는 문장
    assert r.ok and r.by == "AI" and r.value == [Holding("C사", 300)]


def test_parser_rejects_company_name_not_in_the_sentence():
    """AI가 문장에 없는 회사 이름을 돌려주면(목록에 있는 이름이어도) 받지 않고 다시 묻는다."""
    p = Parser(KNOWN, llm=_llm(_reply({"holdings": [{"company": "E사", "shares": 15}]})))
    r = p.holdings("씨사꺼 열다섯개")
    assert not r.ok and "확인하지 못했어요" in r.error


def test_failure_makes_parser_ask_again():
    p = Parser(KNOWN, llm=_llm(error=urllib.error.URLError("off")))
    assert not p.amount("오백만쯤").ok


def test_get_llm_is_off_when_disabled(monkeypatch):
    monkeypatch.setenv("ONEPICK_OLLAMA", "0")
    assert llm_ollama.get_llm() is None


def test_get_llm_off_when_ollama_not_running(monkeypatch):
    monkeypatch.setenv("ONEPICK_OLLAMA", "1")
    monkeypatch.setattr(llm_ollama, "is_available", lambda *a, **k: False)
    llm_ollama.reset()
    assert llm_ollama.get_llm() is None


def test_thinking_is_off_and_default_model_is_commercial_ok():
    calls = []
    _llm(_reply({"amount": 1, "unknown": False}), calls=calls)("한 주", "amount")
    payload = calls[0][1]
    assert payload["think"] is False
    assert llm_ollama.MODEL == "qwen3.5:4b"  # Apache 2.0


def test_available_only_when_model_is_installed(monkeypatch):
    import io
    import json as _json

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    tags = {"models": [{"name": "bge-m3:latest"}]}
    monkeypatch.setattr(llm_ollama.urllib.request, "urlopen", lambda *a, **k: Resp(_json.dumps(tags).encode()))
    assert llm_ollama.is_available(model="qwen3.5:4b") is False  # 조문 찾기 모델만 있으면 꺼진 것으로
    assert llm_ollama.is_available(model="bge-m3") is True


def _image_reply(content):
    return lambda url, payload, timeout: {"message": {"content": json.dumps(content)}}


def test_holdings_image_is_sent_locally_and_sanitized():
    sent = {}

    def post(url, payload, timeout):
        sent.update(url=url, payload=payload)
        return {"message": {"content": json.dumps(
            {"is_holdings_screen": True, "holdings": [{"company": " 삼성전자 ", "shares": 100}]})}}

    assert llm_ollama.read_holdings_image("AAAA", post=post) == [{"company": "삼성전자", "shares": 100}]
    assert sent["url"].startswith("http://localhost") and sent["payload"]["messages"][0]["images"] == ["AAAA"]
    assert sent["payload"]["format"] == llm_ollama.IMAGE_SCHEMA
    assert llm_ollama.read_holdings_image("AAAA", post=lambda *a: {"message": {"content": "깨진 글"}}) is None
    with pytest.raises(ValueError):
        llm_ollama.read_holdings_image("AAAA", url="http://example.com")


def test_holdings_image_drops_everything_when_not_a_holdings_screen():
    """원천징수영수증의 사업자번호·날짜를 종목으로 읽은 실제 사례(2026-11-02): 잔고 화면이 아니면 모두 버린다."""
    read = [{"company": "128-82-01486", "shares": 128}, {"company": "한국중금속", "shares": 12882}]
    assert llm_ollama.read_holdings_image("AAAA", post=_image_reply({"is_holdings_screen": False, "holdings": read})) == []
    assert llm_ollama.read_holdings_image("AAAA", post=_image_reply({"holdings": read})) == []


def test_holdings_image_drops_number_only_names():
    read = [{"company": "208-82-00400", "shares": 208}, {"company": "2018-09-01-12-31", "shares": 2018},
            {"company": "KT&G", "shares": 80}]
    assert llm_ollama.read_holdings_image("AAAA", post=_image_reply({"is_holdings_screen": True, "holdings": read})) \
        == [{"company": "KT&G", "shares": 80}]


@pytest.mark.parametrize("content, expected", [
    ({"page_text": "(9쪽 중 제2쪽)", "box47_text": "35,830,000"}, 35_830_000),
    ({"page_text": "(9쪽 중 제2쪽)", "box47_text": "0"}, 0),
    # 1쪽에는 ㊼ 칸이 없는데 금액을 지어낸 실제 사례: 2쪽이 아니면 버린다
    ({"page_text": "(9쪽 중 제1쪽)", "box47_text": "9,830,560"}, llm_ollama.NOT_PAGE2),
    ({"page_text": None, "box47_text": "9,830,560"}, llm_ollama.NOT_PAGE2),
    # 쉼표 자리가 맞지 않는 글자(자릿수 빠짐 의심)나 빈칸은 읽지 못한 것으로 본다
    ({"page_text": "(9쪽 중 제2쪽)", "box47_text": "3,58300"}, None),
    ({"page_text": "(9쪽 중 제2쪽)", "box47_text": None}, None),
])
def test_tax_base_image_reads_only_box47_on_page2(content, expected):
    sent = {}

    def post(url, payload, timeout):
        sent.update(payload=payload)
        return {"message": {"content": json.dumps(content)}}

    assert llm_ollama.read_tax_base_image("AAAA", post=post) == expected
    assert sent["payload"]["format"] == llm_ollama.BASE_IMAGE_SCHEMA
    assert set(llm_ollama.BASE_IMAGE_SCHEMA["properties"]) == {"page_text", "box47_text", "box21_text"}  # 필요한 값만


def test_tax_base_image_failure_returns_none():
    assert llm_ollama.read_tax_base_image("AAAA", post=lambda *a: {"message": {"content": "깨진 글"}}) is None


@pytest.mark.parametrize("box21, gross", [("52,000,000", 52_000_000), (None, None), ("3,000,000", None), ("52,00", None)])
def test_receipt_image_reads_gross_pay_for_isa_irp(box21, gross):
    """㉑ 총급여도 읽되, ㊼보다 작으면(두 칸을 바꿔 읽음) 버린다. ㊼을 못 읽으면 총급여만으로는 돌려주지 않는다."""
    content = {"page_text": "(9쪽 중 제2쪽)", "box47_text": "35,830,000", "box21_text": box21}
    post = lambda *a: {"message": {"content": json.dumps(content)}}  # noqa: E731
    assert llm_ollama.read_receipt_image("AAAA", post=post) == {"base": 35_830_000, "gross": gross}
    content["box47_text"] = None
    assert llm_ollama.read_receipt_image("AAAA", post=post) is None
