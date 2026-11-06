"""서버 안의 Ollama로 챗봇 입력 문장에서 값만 뽑는다 (core.chat_parse.Parser의 llm 자리).

기획안: 고객 입력은 서버 내 Ollama로만 처리하고 외부 LLM API로 보내지 않는다.
- 주소는 localhost만 허용한다. 다른 주소를 주면 만들 때 거절한다.
- JSON 형식(format)을 지정해 값만 받고, 결과는 Parser가 같은 검사(validate_*)를 다시 거친다.
- 꺼져 있거나 늦거나 JSON이 깨지면 빈 dict를 돌려준다 → 챗봇은 "다시 알려 주세요"로 돌아간다.
- 입력 문장은 어디에도 남기지 않는다.

모델: 기본 qwen3.5:4b (Apache 2.0, 상업 이용 가능). 바꾸려면 환경변수 ONEPICK_OLLAMA_MODEL.
생각(thinking) 단계는 끈다(think: false) — 값 하나 뽑는 데 필요 없고 느려진다.
모델이 설치되어 있지 않으면 꺼진 것으로 보고 규칙만 쓴다(설치: ollama pull qwen3.5:4b).
끄기: 환경변수 ONEPICK_OLLAMA=0 (테스트는 source/tests/conftest.py에서 끈다).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlparse

OLLAMA_URL = os.environ.get("ONEPICK_OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("ONEPICK_OLLAMA_MODEL", "qwen3.5:4b")
TIMEOUT_SEC = 8
IMAGE_TIMEOUT_SEC = 90  # 사진 읽기는 글자 해석보다 오래 걸린다
RECHECK_SEC = 60  # 꺼져 있던 Ollama를 다시 확인하는 간격
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

SCHEMAS = {
    "amount": {
        "type": "object",
        "properties": {"amount": {"type": ["integer", "null"]}, "unknown": {"type": "boolean"}},
        "required": ["amount", "unknown"],
    },
    "holdings": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"company": {"type": "string"}, "shares": {"type": "integer"}},
                    "required": ["company", "shares"],
                },
            }
        },
        "required": ["holdings"],
    },
}

SYSTEM_PROMPTS = {
    "amount": (
        "너는 한국어 문장에서 금액 하나만 뽑아 JSON으로 돌려주는 도구다. "
        "금액은 원 단위 정수로 바꾼다(예: '오백만 원쯤' → 5000000, '천오백 정도' → 15000000). "
        "모른다는 말이면 unknown을 true, amount를 null로 한다. 없다는 말이면 amount를 0으로 한다. "
        "금액이 없으면 amount를 null, unknown을 false로 한다. 설명이나 조언은 쓰지 않는다."
    ),
    # 회사 이름은 바꾸지 않고 문장 글자 그대로 받는다. 'LG'↔'엘지' 같은 이름 맞추기는
    # core.chat_parse.match_company가 회사 목록으로 한다 (모델이 이름을 줄이거나 영어로 바꾸지 않게).
    "holdings": (
        "너는 한국어 문장에서 보유 종목 이름과 주식 수만 뽑아 JSON으로 돌려주는 도구다. "
        "company에는 고객이 쓴 회사 이름 글자를 그대로 옮긴다. 줄이거나, 영어나 한글로 바꾸거나, "
        "다른 회사 이름으로 고치지 않는다. '주식', '약', '쯤' 같은 말은 이름에 넣지 않는다. "
        "shares는 주식 수를 정수로 바꾼다. 한글 숫자도 정확히 읽는다(이백 → 200, 백오십 → 150, 열 → 10). "
        "예: '삼성전자 주식을 한 삼백주쯤' → company '삼성전자', shares 300. "
        "'엘지전자 오십 주' → company '엘지전자', shares 50. "
        "'케이티앤지 이백주하고 삼성전기 백주' → [company '케이티앤지', shares 200], [company '삼성전기', shares 100]. "
        "종목이 없으면 빈 목록을 돌려준다. 설명이나 조언은 쓰지 않는다."
    ),
}


# 보유 종목 캡처(증권사 앱 잔고 화면)에서 종목과 주식 수만 읽는다. 결과는 고객이 확인·고친 뒤에야 쓴다
IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_holdings_screen": {"type": "boolean"},
        "holdings": SCHEMAS["holdings"]["properties"]["holdings"],
    },
    "required": ["is_holdings_screen", "holdings"],
}
IMAGE_PROMPT = (
    "먼저 이 사진이 증권사 앱·홈페이지의 주식 보유 종목(잔고) 화면인지 판단해 is_holdings_screen에 적는다. "
    "원천징수영수증·급여명세서·세금 서류·통장·영수증·문서 사진처럼 잔고 화면이 아니면 false로 하고 holdings는 빈 목록으로 한다. "
    "잔고 화면이면 보유한 국내 주식의 종목 이름과 보유 주식 수(보유수량)만 "
    "JSON으로 옮긴다. company에는 화면에 적힌 종목 이름 글자를 그대로 옮기고, 줄이거나 다른 이름으로 고치지 않는다. "
    "shares에는 보유 수량을 정수로 적는다. 평가금액·매입가·수익률·현재가는 주식 수가 아니니 옮기지 않는다. "
    "화면에 보이지 않는 종목은 지어내지 않는다. 보유 종목 화면이 아니면 빈 목록을 돌려준다. 설명이나 조언은 쓰지 않는다."
)


# 근로소득 원천징수영수증 2쪽에서 ㊼ 종합소득 과세표준 칸만 읽는다. 다른 칸은 읽지 않는다.
# 금액은 글자 그대로(쉼표 포함) 받아 코드가 숫자로 바꾼다 — 숫자로 받으면 자릿수를 빠뜨리는 일이 있었다.
# 쪽 표시 '(9쪽 중 제2쪽)'을 함께 읽어 2쪽이 아니면 버린다 — 1쪽을 주면 없는 금액을 지어냈다.
# 견본 22장(원천징수영수증_R01-R22_견본.pdf): 2쪽 22/22 맞음, 1쪽 22/22 거절 (2026-11-02)
# ㉑ 총급여(ISA·IRP 구간용)를 함께 읽게 바꾼 뒤: ㊼ 22/22, ㉑ 22/22(5,000만·5,500만 경계 포함), 1쪽 22/22 거절 (2026-11-03)
BASE_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {"page_text": {"type": ["string", "null"]}, "box47_text": {"type": ["string", "null"]},
                   "box21_text": {"type": ["string", "null"]}},
    "required": ["page_text", "box47_text", "box21_text"],
}
BASE_IMAGE_PROMPT = (
    "근로소득 원천징수영수증 사진에서 필요한 값만 옮긴다. "
    "page_text: 오른쪽 위의 '(9쪽 중 제○쪽)' 글자를 그대로 옮긴다. 안 보이면 null. "
    "box47_text: 오른쪽 위 '㊼ 종합소득 과세표준' 칸의 금액 글자를 쉼표까지 그대로 옮긴다(예: '35,830,000'). "
    "같은 줄 왼쪽의 '㉑ 총급여' 금액이 아니다. 자릿수를 빠뜨리지 않는다. ㊼ 칸이 없거나 비었으면 null. "
    "box21_text: 왼쪽 위 '㉑ 총급여' 칸의 금액 글자를 쉼표까지 그대로 옮긴다. ㊼ 금액이 아니다. 없거나 비었으면 null. "
    "다른 칸은 옮기지 않는다."
)
NOT_PAGE2 = "not_page2"
_WON_TEXT = re.compile(r"\d{1,3}(?:,\d{3})*")


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


def _http_post(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (localhost만 허용)
        return json.loads(resp.read().decode("utf-8"))


def _as_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def sanitize(kind: str, data) -> dict:
    """모델 출력을 Parser가 기대하는 모양으로만 남긴다. 모양이 틀리면 빈 dict."""
    if not isinstance(data, dict):
        return {}
    if kind == "amount":
        if data.get("unknown") is True:
            return {"amount": "모름"}
        amount = _as_int(data.get("amount"))
        return {"amount": amount} if amount is not None else {}
    if kind == "holdings":
        items = data.get("holdings")
        if not isinstance(items, list):
            return {}
        clean = []
        for h in items:
            if not isinstance(h, dict):
                return {}
            company, shares = h.get("company"), _as_int(h.get("shares"))
            if not isinstance(company, str) or shares is None:
                return {}
            clean.append({"company": company.strip(), "shares": shares})
        return {"holdings": clean}
    return {}


def make_llm(url: str = OLLAMA_URL, model: str = MODEL, timeout: float = TIMEOUT_SEC,
             post: Callable[[str, dict, float], dict] | None = None) -> Callable[[str, str], dict]:
    """Parser(llm=...)에 넣을 함수를 만든다. post는 테스트에서 가짜 응답을 넣는 자리."""
    if not _is_local(url):
        raise ValueError("Ollama 주소는 localhost만 허용합니다 (고객 입력 외부 전송 금지)")
    post = post or _http_post

    def llm(text: str, kind: str) -> dict:
        if kind not in SCHEMAS:
            return {}
        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "format": SCHEMAS[kind],
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS[kind]},
                {"role": "user", "content": text},
            ],
        }
        try:
            resp = post(url.rstrip("/") + "/api/chat", payload, timeout)
            content = resp["message"]["content"]
            return sanitize(kind, json.loads(content))
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError):
            return {}

    return llm


def read_holdings_image(image_b64: str, url: str = OLLAMA_URL, model: str = MODEL,
                        timeout: float = IMAGE_TIMEOUT_SEC,
                        post: Callable[[str, dict, float], dict] | None = None) -> list[dict] | None:
    """보유 종목 캡처(base64 JPEG·PNG)에서 [{company, shares}]를 읽는다. 실패하면 None, 종목이 없으면 [].
    사진은 이 호출 안에서만 쓰고 어디에도 남기지 않는다."""
    if not _is_local(url):
        raise ValueError("Ollama 주소는 localhost만 허용합니다 (고객 입력 외부 전송 금지)")
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": IMAGE_SCHEMA,
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": IMAGE_PROMPT, "images": [image_b64]}],
    }
    try:
        resp = (post or _http_post)(url.rstrip("/") + "/api/chat", payload, timeout)
        raw = json.loads(resp["message"]["content"])
        out = sanitize("holdings", raw)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError):
        return None
    if not out:
        return None
    # 잔고 화면이 아니라고 하면 읽은 것을 모두 버린다(서류의 번호·날짜를 종목으로 읽는 일 방지)
    if raw.get("is_holdings_screen") is not True:
        return []
    # 글자 없이 숫자·기호뿐인 이름(사업자번호·날짜 등)은 종목 이름이 아니다
    return [h for h in out["holdings"] if re.search(r"[가-힣A-Za-z]", h["company"])]


def read_tax_base_image(image_b64: str, url: str = OLLAMA_URL, model: str = MODEL,
                        timeout: float = IMAGE_TIMEOUT_SEC,
                        post: Callable[[str, dict, float], dict] | None = None) -> int | str | None:
    """원천징수영수증 2쪽 사진에서 ㊼ 종합소득 과세표준(원)을 읽는다.
    2쪽이 아니면 NOT_PAGE2, 읽지 못하면 None. 사진은 이 호출 안에서만 쓰고 남기지 않는다."""
    r = read_receipt_image(image_b64, url, model, timeout, post)
    return r if not isinstance(r, dict) else r["base"]


def _won(text) -> int | None:
    return int(text.strip().replace(",", "")) if isinstance(text, str) and _WON_TEXT.fullmatch(text.strip()) else None


def read_receipt_image(image_b64: str, url: str = OLLAMA_URL, model: str = MODEL,
                       timeout: float = IMAGE_TIMEOUT_SEC,
                       post: Callable[[str, dict, float], dict] | None = None) -> dict | str | None:
    """원천징수영수증 2쪽 사진에서 ㊼ 종합소득 과세표준(base)과 ㉑ 총급여(gross, ISA·IRP 구간용)를 읽는다.
    ㊼을 못 읽으면 None(총급여만으로는 점검에 쓰지 않는다), 2쪽이 아니면 NOT_PAGE2.
    총급여가 과세표준보다 작으면 두 칸을 바꿔 읽은 것이라 총급여는 버린다."""
    if not _is_local(url):
        raise ValueError("Ollama 주소는 localhost만 허용합니다 (고객 입력 외부 전송 금지)")
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": BASE_IMAGE_SCHEMA,
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": BASE_IMAGE_PROMPT, "images": [image_b64]}],
    }
    try:
        raw = json.loads((post or _http_post)(url.rstrip("/") + "/api/chat", payload, timeout)["message"]["content"])
        page, base, gross = raw.get("page_text"), _won(raw.get("box47_text")), _won(raw.get("box21_text"))
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError, AttributeError):
        return None
    if not isinstance(page, str) or "제2쪽" not in page.replace(" ", ""):
        return NOT_PAGE2
    if base is None:
        return None
    if gross is not None and (gross < base or gross == 0):
        gross = None
    return {"base": base, "gross": gross}


def is_available(url: str = OLLAMA_URL, model: str = MODEL, timeout: float = 1.0) -> bool:
    """Ollama가 켜져 있고 model이 설치되어 있으면 True."""
    if not _is_local(url):
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout) as resp:  # noqa: S310
            names = {m.get("name") for m in json.loads(resp.read().decode("utf-8")).get("models", [])}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
    return model in names or f"{model}:latest" in names


_state = {"llm": None, "checked_at": 0.0}


def get_llm() -> Callable[[str, str], dict] | None:
    """켜져 있으면 Ollama 함수를, 꺼져 있거나 ONEPICK_OLLAMA=0이면 None을 돌려준다."""
    if os.environ.get("ONEPICK_OLLAMA", "1") == "0":
        return None
    now = time.monotonic()
    if _state["llm"] is None and now - _state["checked_at"] >= RECHECK_SEC:
        _state["checked_at"] = now
        if is_available():
            _state["llm"] = make_llm()
    return _state["llm"]


def reset() -> None:
    """테스트용: 연결 상태 기억을 지운다."""
    _state["llm"] = None
    _state["checked_at"] = 0.0
