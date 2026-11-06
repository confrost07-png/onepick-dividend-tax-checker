"""Streamlit 화면이 함께 쓰는 것: 웹과 같은 디자인(app/web/src/index.css), 웹과 같은 숫자(source/api/main.py 함수), 숫자 표시 규칙.

- 숫자는 웹이 부르는 FastAPI 함수를 그대로 부른다. 응답은 FastAPI가 JSON으로 바꾸는 규칙(jsonable_encoder)을 거쳐
  웹이 받는 값과 똑같은 모양으로 만든다. 계산을 새로 짜지 않는다.
- 문구는 app/web/src의 TS 파일에서 뽑은 web_text.json(export_web_text.mjs)과 API 응답에서 가져온다.
"""
from __future__ import annotations

import base64
import html as _html
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

HERE = Path(__file__).resolve().parent  # app/ (Streamlit 화면 폴더)
ROOT = HERE.parent  # 저장소 맨 위
WEB = HERE / "web"  # React 웹 화면 (문구·디자인을 여기서 가져옴)
SOURCE = ROOT / "source"  # core·api 같은 계산 코드가 있는 곳
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from fastapi import HTTPException  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402

from api import main as api_main  # noqa: E402


# ── 웹 문구 ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def web_text() -> dict:
    """app/web/src의 bank.ts·legal.ts·column.ts 값 그대로 (export_web_text.mjs가 만든 파일)."""
    return json.loads((HERE / "web_text.json").read_text(encoding="utf-8"))


# ── 웹과 같은 데이터 ─────────────────────────────────────────────────────────
def _json(x: Any) -> Any:
    """FastAPI 응답과 같은 JSON 값으로 (웹 화면이 받는 값과 똑같게)."""
    return json.loads(json.dumps(jsonable_encoder(x), ensure_ascii=False))


class ApiError(Exception):
    pass


def _call(fn, *args, **kwargs):
    try:
        return _json(fn(*args, **kwargs))
    except HTTPException as e:  # 웹 api.ts의 call()처럼 detail 문구를 그대로 보여 준다
        raise ApiError(e.detail if isinstance(e.detail, str) else f"요청이 실패했어요 ({e.status_code})") from e


class api:
    """app/web/src/api.ts의 `api` 객체와 같은 이름·같은 응답. 서버를 따로 띄우지 않고 source/api/main.py 함수를 바로 부른다."""

    @staticmethod
    @st.cache_data(show_spinner=False)
    def personas():
        return _call(api_main.persona_list)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def persona(pid: str):
        return _call(api_main.persona_page, pid)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def companyList():
        return _call(api_main.company_list)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def search(q: str):
        return _call(api_main.companies, q)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def company(code: str):
        return _call(api_main.company, code)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def funnel():
        return _call(api_main.funnel)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def analysis():
        return _call(api_main.analysis)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def events():
        return _call(api_main.analysis_events)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def movement():
        return _call(api_main.analysis_movement)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def script():
        return _call(api_main.chat_script)

    @staticmethod
    def parse(kind: str, text: str, dividend_type: str | None = None):
        return _call(api_main.parse, api_main.ParseIn(kind=kind, text=text, dividend_type=dividend_type))

    @staticmethod
    def checkup(body: dict):
        return _call(api_main.checkup, api_main.CheckupIn(**body))

    @staticmethod
    def holdingsImage(image: str):
        return _call(api_main.holdings_image, api_main.ImageIn(image=image))

    @staticmethod
    def baseImage(image: str):
        return _call(api_main.base_image, api_main.ImageIn(image=image))

    @staticmethod
    @st.cache_data(show_spinner=False)
    def evidence():
        return _call(api_main.evidence)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def race(pick: int):
        return _call(api_main.column_race, pick)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def spread():
        return _call(api_main.column_spread)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def lawPassages():
        return _call(api_main.law_passages)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def separate(amount: int):
        return _call(api_main.tax_separate, amount)

    @staticmethod
    @st.cache_data(show_spinner=False)
    def isaIrp(bracket: str | None, profit: int, irp: int, pension_saving: int):
        return _call(api_main.isa_irp_guide, bracket, profit, irp, pension_saving, None)

    @staticmethod
    def lawSearch(q: str):
        return _call(api_main.law_search, q)

    @staticmethod
    def faq(q: str):
        return _call(api_main.faq, q)


def load(fn, *args):
    """웹 useLoad처럼 (data, error)를 돌려준다."""
    try:
        return fn(*args), None
    except Exception as e:  # noqa: BLE001 - 화면에 이유를 그대로 보여 준다
        return None, str(e)


# ── 숫자 표시 (JS toLocaleString('ko-KR')·toFixed·Math.round와 같은 결과) ─────────
def _round_dec(x: float, digits: int) -> Decimal:
    # JS는 숫자의 정확한 이진값에서 반올림하고, 딱 절반이면 큰 쪽(Number.prototype.toFixed, ECMA-402 halfExpand)
    return Decimal(x).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def fixed(x: float, digits: int = 0) -> str:
    """JS x.toFixed(digits)"""
    return f"{_round_dec(float(x), digits):f}"


def fmt(x: float | int | None, max_frac: int = 3, min_frac: int = 0) -> str:
    """JS x.toLocaleString('ko-KR', { maximumFractionDigits, minimumFractionDigits })"""
    if x is None:
        return ""
    d = _round_dec(float(x), max_frac)
    sign = "-" if d < 0 else ""
    d = abs(d)
    whole, _, frac = f"{d:f}".partition(".")
    frac = frac.rstrip("0")
    if len(frac) < min_frac:
        frac = frac + "0" * (min_frac - len(frac))
    s = f"{int(whole):,}"
    return sign + s + (f".{frac}" if frac else "")


def js_round(x: float) -> int:
    """JS Math.round (절반은 위로)"""
    import math
    return math.floor(x + 0.5)


def won(amount: float) -> str:
    """app/web/src/util.ts won(): 1억 원 이상은 억 원(소수 첫째 자리)."""
    if abs(amount) >= 100_000_000:
        return f"{fmt(amount / 100_000_000, 1, 1)}억 원".replace(".0억", "억")
    return f"{fmt(amount)}원"


def pct(v: float | None, sign: bool = False) -> str:
    """app/web/src/util.ts pct()"""
    if v is None:
        return "–"
    return f"{'+' if sign and v > 0 else ''}{fmt(v, 1)}%"


def mood_of(status: str | None) -> str:
    return "happy" if status == "충족" else "sad" if status == "미충족" else "curious" if status else "base"


def badge_class(status: str) -> str:
    return "badge--ok" if status == "충족" else "badge--no" if status == "미충족" else "badge--hold"


# ── 화면 꾸미기 ───────────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def moa(mood: str = "base") -> str:
    """마스코트 모아 그림 (app/web/public/moa) data URL."""
    b = (WEB / "public" / "moa" / f"moa_{mood}.webp").read_bytes()
    return "data:image/webp;base64," + base64.b64encode(b).decode()


def esc(s: Any) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


# Streamlit 기본 틀을 웹 화면에 맞추는 덧칠. 웹 디자인 토큰·부품은 app/web/src/index.css를 그대로 읽어 쓴다.
_ST_FIX = """
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stMarkdownContainer"], .stApp,
button, input, textarea, select { font-family: "Gothic A1", system-ui, sans-serif; }
.stApp { background: #fff; color: var(--ink); }
[data-testid="stMainBlockContainer"], .block-container { max-width: 1184px; padding-top: 4.2rem; padding-left: 32px; padding-right: 32px; }
.wrap { max-width: none; padding: 0; margin: 0; }
[data-testid="stHeader"] { background: rgba(255,255,255,.92); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
[data-testid="stHeader"] a, [data-testid="stHeader"] span { font-weight: 700; }
[data-testid="stElementContainer"]:has(> .stHtml), .stHtml { width: 100%; }
.stHtml h1, .stHtml h2, .stHtml h3, .stHtml h4 { padding: 0; scroll-margin-top: 80px; }
div[data-testid="stExpander"] details summary p { font-weight: 800; }
.st-key-topbar { margin-bottom: 4px; }
.op-brand { display: flex; align-items: center; gap: 8px; font: 400 26px "Do Hyeon"; color: var(--ink); }
.op-brand i { width: 22px; height: 22px; border-radius: 50%; background: var(--coin); box-shadow: inset 0 -3px 0 var(--coin-deep); display: inline-block; }
button[kind="primary"] { background: var(--sea); border-color: var(--sea); }
.stButton button, .stDownloadButton button { border-radius: 16px; font-weight: 800; }
.stPageLink a { border-radius: 999px; }
</style>
"""

FONTS = '<link href="https://fonts.googleapis.com/css2?family=Do+Hyeon&family=Gothic+A1:wght@400;500;700;800&display=swap" rel="stylesheet" />'


@lru_cache(maxsize=1)
def _css() -> str:
    return (WEB / "src" / "index.css").read_text(encoding="utf-8")


def setup(title: str) -> None:
    """모든 화면 맨 위: 탭 제목(웹 App.tsx와 같은 'OO · 원픽'), 글꼴, 웹 CSS."""
    st.set_page_config(page_title=f"{title} · 원픽")
    st.html(f"{FONTS}<style>{_css()}</style>{_ST_FIX}")


def html(body: str, **kw) -> None:
    """웹과 같은 class 이름을 쓴 HTML을 그대로 그린다 (app/web/src/index.css가 꾸민다)."""
    st.html(body, **kw)


def judge_year_html(open_: bool = False) -> str:
    """'2026 판정'이 어떤 배당의 판정인지 펼쳐 보는 칸 (웹 components/JudgeYear.tsx와 같은 문장, legal.ts JUDGE_YEAR)."""
    j = web_text()["legal"]["JUDGE_YEAR"]
    rows = "".join(f"<li><b>{esc(what)}</b> → {esc(when)}</li>" for what, when in j["rows"])
    return (f'<details class="basis judge-year"{" open" if open_ else ""}><summary>{esc(j["title"])}</summary>'
            f'<p>{esc(j["lead"])}</p><ul>{rows}</ul><p>{esc(j["not_this"])}</p><p>{esc(j["basis"])}</p></details>')


def error(msg: str) -> None:
    html(f'<p class="error">{esc(msg)}</p>')


def loading(msg: str = "불러오는 중…") -> None:
    html(f'<div class="loading">{esc(msg)}</div>')


def moa_say(text_html: str, mood: str = "curious", img_first: bool = True, style: str = "") -> str:
    img = f'<img src="{moa(mood)}" alt="" />'
    p = f"<p>{text_html}</p>"
    return f'<div class="moa-say" style="{style}">{img + p if img_first else p + img}</div>'


# ── 로그인(시연용 고객) ─────────────────────────────────────────────────────
def persona_id() -> str | None:
    """웹 persona.tsx: 로그인한 시연용 고객. 웹은 브라우저(localStorage)에, Streamlit은 이 세션에만 기억한다."""
    return st.session_state.get("persona")


def set_persona(pid: str | None) -> None:
    st.session_state["persona"] = pid


# ── 브라우저 스크립트 ─────────────────────────────────────────────────────────
def run_js(code: str, body: str = "") -> None:
    """HTML과 함께 스크립트를 돌린다. st.html의 정화기(DOMPurify)는 글 안에 '<태그'가 든 스크립트를 지우므로
    코드를 base64로 감싸 넘기고 브라우저에서 풀어 전역으로 실행한다."""
    b64 = base64.b64encode(code.encode("utf-8")).decode()
    st.html(f"{body}<script>(0,eval)(new TextDecoder().decode(Uint8Array.from(atob('{b64}'),c=>c.charCodeAt(0))))</script>",
            unsafe_allow_javascript=True)


# ── 법 토너먼트 (웹 Tournament.tsx와 같은 그림 엔진) ─────────────────────────────
@lru_cache(maxsize=1)
def _tournament_js() -> str:
    return (HERE / "web_tournament.js").read_text(encoding="utf-8")


def tournament(f: dict, compact: bool = False, autoplay: str = "none", key: str = "tour") -> None:
    """웹 Tournament.tsx: app/web/src/components/tournamentEngine.ts를 묶은 web_tournament.js를 그대로 돌린다.
    동전 수는 api.funnel() 값이다."""
    met, fail, hold = f["ga"] + f["na"] + f["na_deficit"], f["fail2"] + f["fail3"], f["hold_missing"] + f["hold_zero"]
    moas = json.dumps({m: moa(m) for m in ("base", "happy", "sad", "curious")})
    label = f"법 토너먼트: {f['total']}곳 중 충족 {met}, 미충족 {fail}, 판정 보류 {hold}"
    hid = f"op-{key}"
    run_js(
        f"window.ONEPICK_MOA={moas};if(!window.OnePickTournament){{{_tournament_js()}\nwindow.OnePickTournament=OnePickTournament}}\n"
        f"(function(){{var h=document.getElementById({json.dumps(hid)});if(!h||h.dataset.on)return;h.dataset.on='1';"
        f"window.OnePickTournament.mountTournament(h,{json.dumps(f)},{{autoplay:{json.dumps(autoplay)},still:matchMedia('(prefers-reduced-motion: reduce)').matches}});}})();",
        body=f'<div id="{hid}" class="tour{" tour--compact" if compact else ""}" role="group" aria-label="{esc(label)}"></div>',
    )
