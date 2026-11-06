"""원픽 API: 새 화면(app/web/)이 쓰는 JSON.

- 계산은 source/core/ 모듈을 그대로 부른다(source/api/data.py). 세법 해석을 만들지 않고, 조문은 원문 그대로만 돌려준다.
- 고객 입력(점검 답)은 저장하지 않고 기록하지 않는다. 실행할 때 접속 기록을 끈다(source/scripts/run_api.py).

실행: .venv/bin/python -m scripts.run_api  (http://127.0.0.1:8000/docs 에서 API 목록)
"""
import base64
import binascii
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import data
from core import chat_guard, isa_irp, keyboard, personas, term_dict
from core import sample_data as text

app = FastAPI(title="원픽 API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "companies": len(data.companies())}


@app.get("/api/companies")
def companies(q: str = Query("", max_length=40)) -> list[dict]:
    """회사 이름·종목코드 검색 (입력하는 동안 후보)."""
    return data.search(q)


@app.get("/api/companies/list")
def company_list() -> list[dict]:
    """조회 대상 기업 전체 목록(이름순), 이어서 계산할 수 있는 상장 우선주(pref_of: 보통주 회사 이름).
    점검 ① 입력창 옆 [조회 대상 기업 목록]이 쓴다. /{code}보다 먼저 둔다."""
    firms = [{"name": n, "code": getattr(c, "stock_code", ""), "pref_of": ""} for n, c in sorted(data.companies().items())]
    prefs = [{"name": n, "code": c.pref_code, "pref_of": c.pref_of} for n, c in sorted(data.prefs()[0].items())]
    return firms + prefs


@app.get("/api/companies/{code}")
def company(code: str) -> dict:
    """회사 한 곳: 2026 판정, 라운드별 근거 숫자, 2027 최소 필요 배당, 공시 원문 링크."""
    out = data.company(code)
    if out is None:
        raise HTTPException(404, "회사를 찾지 못했어요")
    return out


@app.get("/api/judgement/funnel")
def funnel() -> dict:
    """법 토너먼트: 638사가 라운드마다 어디로 갔는지 (core.core_judgement_2026)."""
    return data.funnel()


@app.get("/api/analysis")
def analysis() -> dict:
    """데이터 이야기: 다음 해 탈락률·탈락 이유·기준선 몰림·2027 최소액·공시 뒤 초과수익률. 회사 이름 없이 집계만."""
    return data.analysis()


@app.get("/api/chat/script")
def chat_script() -> dict:
    """점검 대화 문구. 앱(source/core/sample_data.py)과 같은 문장을 쓰고, 예시 칩만 실제 회사로 바꾼다."""
    questions = [dict(q) for q in text.QUESTIONS]
    questions[0]["chips"] = ["삼성전자 1천 주, 케이티앤지 300주", "삼성전자 100주", *text.HOLDINGS_SKIP_CHIPS]
    return {
        "title": text.ADDON_TITLE, "body": text.ADDON_BODY, "ai_note": text.WEB_ADDON_NOTE,
        "step_labels": text.STEP_LABELS, "questions": questions, "step_help": text.STEP_HELP,
        "dividend_types": text.DIVIDEND_TYPES, "dividend_amount_ask": text.DIVIDEND_AMOUNT_ASK,
        "dividend_amount_chips": text.DIVIDEND_AMOUNT_CHIPS, "other_income_note": text.OTHER_INCOME_NOTE,
        "receipt_chip": text.RECEIPT_CHIP, "receipt_guide": text.RECEIPT_GUIDE, "no_wage": text.NO_WAGE,
        "confirm_ask": text.CONFIRM_ASK, "confirm_chips": text.CONFIRM_CHIPS, "confirm_note": text.CONFIRM_NOTE,
        "edit_ask": text.EDIT_ASK, "parse_retry": text.PARSE_RETRY, "stuck_hint": text.STUCK_HINT,
        "max_chars": text.MAX_INPUT_CHARS, "ai_read_mark": text.AI_READ_MARK,
        "result_lead": text.RESULT_LEAD, "next_check": text.NEXT_CHECK, "result_actions": text.RESULT_ACTIONS,
        "result_footnote": text.RESULT_FOOTNOTE, "send_result": text.SEND_RESULT, "send_result_note": text.SEND_RESULT_NOTE,
        "law_notice": text.LAW_NOTICE, "condition": text.HOLDING_CONDITION_LISTED,
        "greeting": text.GREETING, "start_guide": text.WEB_START_GUIDE, "entry_fallback": text.TERM_FALLBACK,
        "entry_unclear": text.ENTRY_UNCLEAR, "entry_words": text.ENTRY_WORDS, "entry_replies": text.ENTRY_REPLIES,
        "scope_guide": text.SCOPE_GUIDE.format(n=len(data.companies())), "company_list_chip": text.COMPANY_LIST_CHIP,
        "base_image_chip": text.BASE_IMAGE_CHIP, "base_image_note": text.BASE_IMAGE_NOTE,
        "base_image_reading": text.BASE_IMAGE_READING,
        "image_chip": text.IMAGE_CHIP, "image_note": text.IMAGE_NOTE, "image_guide": text.IMAGE_GUIDE, "image_guide_pick": text.IMAGE_GUIDE_PICK, "image_reading": text.IMAGE_READING,
        "other_holding_added": text.OTHER_HOLDING_ADDED, "other_holding_dup": text.OTHER_HOLDING_DUP,
        "special_tax_label": text.SPECIAL_TAX_LABEL, "special_tax_tag": text.SPECIAL_TAX_TAG,
        "special_tax_note": text.SPECIAL_TAX_NOTE, "special_label": text.SPECIAL_LABEL, "no_target": text.NO_TARGET,
        "special_legal": text.SPECIAL_LEGAL, "special_explain_title": text.SPECIAL_EXPLAIN_TITLE,
        "special_explain": text.SPECIAL_EXPLAIN,
        "stock_text": {"shares": text.STOCK_SHARES, "special": text.STOCK_SPECIAL, "held": text.STOCK_HELD,
                       "general": text.STOCK_GENERAL, "next_up": text.STOCK_NEXT_UP, "next_keep": text.STOCK_NEXT_KEEP},
        "term_chip": text.TERM_CHIP, "term_scope": text.TERM_SCOPE.replace("{faq_n}", str(len(data.faq().faqs)))
        .replace("{fsc_n}", f"{term_dict.counts()['fsc']:,}").replace("{onepick_n}", f"{term_dict.counts()['onepick']:,}"),
        "term_examples": text.TERM_EXAMPLES,
        # 관련 조문 찾기는 결과 화면의 근거 서랍에 따로 있어 시작 칩에서는 뺀다
        "addon_chips": [*[c for c in text.ADDON_CHIPS if c != text.LAW_CHIP], text.TERM_CHIP],
        "addon_replies": text.ADDON_REPLIES,
        "docs_chip": text.DOCS_CHIP, "docs_guide": text.DOCS_GUIDE,
        "restart_words": text.RESTART_WORDS, "stop_words": text.STOP_WORDS, "stop_reply": text.STOP_REPLY,
        "confirm_yes": text.CONFIRM_YES, "confirm_no": text.CONFIRM_NO,
        "layout_fixed": text.LAYOUT_FIXED,
    }


@app.get("/api/analysis/events")
def analysis_events() -> dict:
    """공시 뒤 주가 반응: 조건별 곡선·요약과 통계 방법별 검정 결과."""
    return data.events()


@app.get("/api/analysis/movement")
def analysis_movement() -> dict:
    """8년 움직이는 산점도용 해마다의 배당성향·증가율 (회사 이름 없음)."""
    return data.movement()


class ParseIn(BaseModel):
    kind: Literal["holdings", "amount", "other_dividend", "yesno", "base"]
    text: str = Field(max_length=text.MAX_INPUT_CHARS)
    dividend_type: Literal["domestic", "foreign"] | None = None


def _hangul_retry(raw: str) -> str | None:
    """한/영 전환을 잊고 친 글이면 한글로 바꾼 글(core.keyboard). 회사 이름의 영문(KB·SK …)은 그대로 둔다."""
    return keyboard.fix_layout(raw, keyboard.latin_words(data.name_index()))


def _parse_once(kind: str, raw: str, dividend_type: str | None) -> dict:
    term = data.term_answer(raw)
    if term:  # '공매도란?'처럼 사전 용어 이름이 정확히 맞으면 풀이를 먼저 (가드의 '매도'에 걸리지 않게). 화면은 같은 질문을 다시 한다
        return {"ok": False, "question": True, "faq": term, "help": text.STEP_HELP[kind]}
    topic = chat_guard.check(raw)
    if topic:
        return {"ok": False, "guard": topic, "reply": chat_guard.FIXED_REPLY[topic],
                "consult": topic in chat_guard.CONSULT_TOPICS}
    chat = chat_guard.small_talk(raw)
    if chat:  # '너 뭐야'·'안녕'·'고마워' 같은 말: 정해 둔 답. 화면은 지금 질문을 다시 한다
        return {"ok": False, "chat": chat}
    chat = chat_guard.casual(raw)
    if chat:  # '야'·'ㅋㅋㅋ'·'답답해' 같은 말: 용어 사전 안내로 넘기지 않고 뜻에 맞는 정해 둔 답
        return {"ok": False, "chat": chat}
    if kind == "holdings" and re.fullmatch(r"[\d,\s]+", raw):  # '1'·'300'처럼 수만 적음: 목록에 없는 회사로 읽지 않는다
        return {"ok": False, "value": None, "error": text.HOLDINGS_NEED_NAME, "by": "규칙", "code": "missing_name"}
    if data.looks_like_question(raw):
        # 답이 아니라 질문이면: 금융 상식 고정 답변이 있으면 그대로, 없으면 이 단계 도움말. 화면은 같은 질문을 다시 한다
        return {"ok": False, "question": True, "faq": data.faq_answer(raw), "help": text.STEP_HELP[kind]}
    if data.looks_like_term(raw, kind):
        # '배당락'처럼 단어만 적어도 준비된 금융 상식 답이 있으면 보여 준다. 없으면 원래대로 답으로 읽는다
        hit = data.faq_answer(raw)
        if hit:
            return {"ok": False, "question": True, "faq": hit, "help": text.STEP_HELP[kind]}
    return data.parse(kind, raw, dividend_type)


def _useful(r: dict) -> bool:
    """다시 묻지 않고 화면이 바로 쓸 수 있는 답인가 (값·질문 답·고정 문구·되묻기)."""
    return bool(r.get("ok") or r.get("guard") or r.get("chat") or r.get("suggest_text") or r.get("faq") or r.get("add_holdings") or r.get("prompt")
                or r.get("code") in ("missing_shares", "bad_shares", "missing_name", "not_found"))


@app.post("/api/chat/parse")
def parse(body: ParseIn) -> dict:
    """점검 한 단계의 답을 값으로 읽는다. 세법·종목 질문이면 정해 둔 안내 문구로 답한다.
    영문으로 적었는데 그대로는 못 읽으면 한글 자판으로 바꿔 한 번 더 읽고, 바꾼 글을 fixed_text로 알려 준다."""
    alt = _hangul_retry(body.text)
    if alt and not chat_guard.check(body.text) and chat_guard.check(alt):  # 영문 자판으로 친 욕설·권유 질문도 같은 고정 문구로
        return {**_parse_once(body.kind, alt, body.dividend_type), "fixed_text": alt}
    if not alt:
        return _parse_once(body.kind, body.text, body.dividend_type)
    # 영문이 온전한 한글 글자로 바뀌면 한/영 전환을 잊은 글로 보고 바꾼 글을 먼저 읽는다
    # ('50aksdnjs'를 그대로 읽으면 50원, 바꾸면 '50만원'. 'C사 10wn' → 'C사 10주')
    r2 = {**_parse_once(body.kind, alt, body.dividend_type), "fixed_text": alt}
    if r2.get("ok"):
        return r2
    r = _parse_once(body.kind, body.text, body.dividend_type)
    return r if r.get("ok") or _useful(r) or not _useful(r2) else r2


MAX_IMAGE_B64 = 8_000_000  # 약 6MB 사진. 화면은 긴 변 1600px JPEG로 줄여 보낸다


class ImageIn(BaseModel):
    image: str = Field(max_length=MAX_IMAGE_B64)  # base64 (data:image/...;base64, 머리말이 있어도 됨)


def _photo(body: ImageIn) -> str | None:
    """data URL 머리말을 떼고, JPEG·PNG이면 base64 글자를 돌려준다. 아니면 None."""
    b64 = body.image.split(",", 1)[1] if body.image.startswith("data:") else body.image
    try:
        head = base64.b64decode(b64[:24], validate=True)
    except (binascii.Error, ValueError):
        return None
    return b64 if head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG") else None


@app.post("/api/chat/holdings-image")
def holdings_image(body: ImageIn) -> dict:
    """① 보유 종목 캡처를 서버 안 AI(Ollama)로 읽어 입력창에 채울 글을 돌려준다. 사진은 저장하지 않는다."""
    b64 = _photo(body)
    return data.holdings_from_image(b64) if b64 else {"ok": False, "error": text.IMAGE_BAD}


@app.post("/api/chat/base-image")
def base_image(body: ImageIn) -> dict:
    """⑤ 원천징수영수증 2쪽 사진에서 ㊼ 종합소득 과세표준만 읽어 입력창에 채울 글을 돌려준다. 사진은 저장하지 않는다."""
    b64 = _photo(body)
    return data.base_from_image(b64) if b64 else {"ok": False, "error": text.IMAGE_BAD}


@app.get("/api/terms")
def terms() -> dict:
    """금융 상식 칼럼 '용어 사전' 탭에 함께 보일 금융위원회 금융용어사전·원픽 보충 용어 전체 (원문 그대로, 출처 포함)."""
    return {"notice": text.TERM_NOTICE,
            "terms": [{"term": e.term, "aliases": list(e.aliases), "definition": e.definition, "source_name": e.source_name,
                       "source_url": e.source_url, "kind": e.kind} for e in term_dict.entries()]}


@app.get("/api/faq")
def faq(q: str = Query(..., min_length=1, max_length=text.MAX_INPUT_CHARS)) -> dict:
    """금융 상식 질문: 미리 써 둔 답 하나를 그대로 돌려준다(검색만, 생성 없음). 없으면 faq는 null."""
    alt = _hangul_retry(q)
    for query in [q, alt] if alt else [q]:
        term = data.term_answer(query)
        if term:
            return {"faq": term, "fallback": text.ENTRY_FALLBACK, **({"fixed_text": query} if query != q else {})}
        topic = chat_guard.check(query)
        if topic:
            return {"faq": None, "guard": topic, "reply": chat_guard.FIXED_REPLY[topic]}
        hit = data.faq_answer(query)
        if hit:
            return {"faq": hit, "fallback": text.ENTRY_FALLBACK, **({"fixed_text": query} if query != q else {})}
    return {"faq": None, "fallback": text.ENTRY_FALLBACK}


class HoldingIn(BaseModel):
    company: str
    shares: int = Field(gt=0, le=10**10)


class CheckupIn(BaseModel):
    holdings: list[HoldingIn] = Field(max_length=20)  # ①에서 '없음'·'모름'을 고르면 빈 목록
    interest: int | None = Field(None, ge=0)
    other_domestic: int | None = Field(None, ge=0)
    other_foreign: int | None = Field(None, ge=0)
    base: int | None = Field(None, ge=0)
    has_other_income: bool = False
    holdings_answer: Literal["없음", "모름"] | None = None  # ①을 건너뛴 이유
    outside: list[str] = Field(default_factory=list, max_length=20)  # ①에서 고배당기업 목록에 없어 뺀 종목 이름(계산에는 안 씀)


@app.post("/api/checkup")
def checkup(body: CheckupIn) -> dict:
    """세액 비교. 입력은 이 호출 안에서만 쓰고 저장하지 않는다."""
    if not body.holdings and body.holdings_answer is None:
        raise HTTPException(422, "보유 종목을 알려 주시거나 [없음]·[모름]을 골라 주세요")
    unknown = [h.company for h in body.holdings if h.company not in data.companies() and h.company not in data.prefs()[0]]
    if unknown:
        raise HTTPException(422, f"'{unknown[0]}'을(를) 찾지 못했어요")
    return data.checkup({h.company: h.shares for h in body.holdings}, body.interest, body.other_domestic,
                        body.other_foreign, body.base, body.has_other_income,
                        None if body.holdings else body.holdings_answer, [n[:40] for n in body.outside])


@app.get("/api/law/evidence")
def evidence() -> list[dict]:
    """[근거 보기] 조문 원문 그대로."""
    return data.evidence()


@app.get("/api/law/passages")
def law_passages() -> list[dict]:
    """세법 칼럼이 옆에 붙이는 조문 원문 전체(data/processed/law/articles.json, 국가법령정보센터)."""
    return [{"label": p.label, "text": p.text, "url": p.url, "effective": p.effective} for p in data.law().passages]


@app.get("/api/tax/separate")
def tax_separate(amount: int = Query(..., ge=0, le=10**12)) -> dict:
    """분리과세 세액 S(E)를 구간별로 (core.tax.separate_tax, core.tax_rates.SEPARATE). 참고용 계산."""
    return data.separate(amount)


@app.get("/api/isa-irp")
def isa_irp_guide(bracket: Literal["low", "mid", "high", "biz_low", "biz_mid", "biz_high"] | None = None,
                  profit: int = Query(3_000_000, ge=0, le=10**11),
                  irp: int = Query(9_000_000, ge=0, le=10**10),
                  pension_saving: int = Query(0, ge=0, le=10**10),
                  tax_due: int | None = Query(None, ge=0, le=10**11)) -> dict:
    """ISA·IRP 구간 안내와 단순 계산 (core.isa_irp). 추천 없이 혜택·제약을 함께 돌려준다."""
    return isa_irp.guide(bracket, profit, irp, pension_saving, tax_due)


@app.get("/api/personas")
def persona_list() -> list[dict]:
    """로그인한 고객으로 가정한 시연용 가상 인물 목록 (core.personas)."""
    return personas.summary()


@app.get("/api/personas/{pid}")
def persona_page(pid: str) -> dict:
    """개인 페이지: 소득·계좌·금융소득과, 코드로 계산한 점검 결과·ISA·IRP 판정."""
    p = data.persona(pid)
    if p is None:
        raise HTTPException(404, "없는 사용자예요")
    return p


@app.get("/api/column/race")
def column_race(pick: int = Query(0, ge=0)) -> dict:
    """금융 상식 칼럼 '달리기 시합': 실제 공시 한 건의 60거래일 주가·시장 누적 수익률 (회사 이름 없음)."""
    return data.race_example(pick)


@app.get("/api/column/spread")
def column_spread() -> dict:
    """금융 상식 칼럼 '평균과 가운데 값': 배당 증가 공시 뒤 60거래일 초과수익률 모든 사례(이름 없음)."""
    return data.spread_example()


@app.get("/api/law/search")
def law_search(q: str = Query(..., min_length=1, max_length=text.MAX_INPUT_CHARS)) -> dict:
    """질문과 가까운 조문 문단을 원문 그대로 최대 3개 (생성 없음)."""
    hits = data.law().search(q)
    return {"notice": text.LAW_NOTICE, "hits": [{"label": h.passage.label, "text": h.passage.text,
                                                 "url": h.passage.url, "by": h.by} for h in hits]}


# 화면을 빌드해 두었으면(cd app/web && npm run build) 이 서버 하나로 화면까지 띄운다. 없는 주소는 화면이 처리한다.
DIST = Path(__file__).resolve().parents[2] / "app" / "web" / "dist"
if DIST.is_dir():
    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> FileResponse:
        file = (DIST / path).resolve()
        if path.startswith("source/api/"):
            raise HTTPException(404)
        return FileResponse(file if file.is_file() and file.is_relative_to(DIST) else DIST / "index.html")
