"""모아의 금융 상식 칼럼 (웹 app/web/src/pages/Column.tsx, /column · /column/:id).

글·용어 사전·단원·묶음은 web_text.json(app/web/src/column.ts 그대로)에서, {이름} 자리 숫자는 웹과 같은 API(funnel·analysis)에서 가져온다.
글 하나는 ?id=글이름 으로 연다. 읽은 글 표시는 웹은 브라우저(localStorage)에, Streamlit은 이 세션에만 기억한다.
"""
import json
import re
from functools import lru_cache

import streamlit as st

from column_toys import TOYS, svg_img, toy
from common import HERE, api, esc, fixed, fmt, html, load, moa, run_js, web_text

PAGES = st.session_state["_pages"]
C = web_text()["column"]
EPISODES, GLOSSARY, UNITS, THEMES = C["EPISODES"], C["GLOSSARY"], C["UNITS"], C["THEMES"]
READ_ORDER, START_HERE, COLUMN_NOTE = C["READ_ORDER"], C["START_HERE"], C["COLUMN_NOTE"]
EP = {e["id"]: e for e in EPISODES}

# Column.tsx 화면 문구
SRC_CLASS = {"조문": "src--law", "팀 해석": "src--team", "데이터": "src--data", "쉬운 설명": "src--easy"}
TOY_NAMES = {
    "pizza": "피자 나눠 먹기", "stairs": "세율 계단", "gates": "문 세 개 열기", "balance": "빚 저울", "wallet": "용돈 지갑", "race": "실제 공시 달리기",
    "lineup": "실제 사례 점 찍기", "coins": "동전 던지기", "stockbond": "가게 주인과 빌려준 사람", "votes": "100주짜리 회사", "taxhelper": "누가 무엇을 하나",
    "wealth": "배당 받는 1년", "fincome": "2천만 원 선", "withhold": "배당 받는 날 통장", "kinds": "소득 주머니", "grossup": "두 번 내지 않게", "savings": "복리 저금통",
    "fx": "환율 다이얼", "account": "나라 가계부", "basket": "장바구니", "yields": "수익률 vs 성향", "divcal": "배당 달력", "recordday": "언제 사야 받을까",
    "payback": "주주환원 바구니", "taxflow": "세금 계산 길",
    "index": "지수 만들기", "knockin": "ELS 길 따라가기", "eld": "ELD 저금통 나누기", "etn": "ETF와 ETN 견주기", "meeting": "주주총회 표 세기",
    "splitter": "피자 다시 자르기", "merger": "두 가게 합치기", "ipo": "공모주 나눠 받기", "delistpath": "상장폐지 가는 길", "waterfall": "남은 돈 나눠 갖기 순서", "capital": "주식 늘리고 줄이기",
    "ledger": "가게 장부 써 보기", "disclosure": "이 소식은 어느 공시?", "ratemachine": "기준금리 손잡이", "brakes": "시장 브레이크 걸기",
    "isabox": "ISA 바구니에 담아 보기", "pension": "연금 세액공제 계산", "deposit": "예금 vs 적금 이자 견주기", "shelf": "돈 맡길 곳 견주기",
}
assert set(TOY_NAMES) == set(TOYS)

# 웹에서는 용어를 누르면 뜻이 열린다. Streamlit은 마우스를 올리거나 눌러(포커스) 연다.
# 줄 전체를 누르는 링크는 HTML 줄 위에 투명한 버튼(칼럼 안)이나 st.page_link(다른 화면)를 덮어 만든다(세션이 끊기지 않게).
EXTRA_CSS = """<style>
.term-wrap .term-pop { display: none; }
.term-wrap:hover .term-pop, .term-wrap:focus-within .term-pop { display: block; }
[class*="st-key-lnk_"] { position: relative; }
[class*="st-key-lnk_"] [data-testid="stElementContainer"]:is(:has(.stPageLink), :has(.stButton)) { position: absolute; inset: 0; z-index: 3; margin: 0; opacity: 0; }
[class*="st-key-lnk_"] [data-testid="stElementContainer"]:is(:has(.stPageLink), :has(.stButton)) * { width: 100% !important; height: 100% !important; max-width: none !important; }
[class*="st-key-lnk_"]:hover .ep-row, [class*="st-key-lnk_"]:hover .start-card { border-color: var(--u); }
[class*="st-key-lnk_"]:hover .next-stone { filter: brightness(.98); }
[class*="st-key-epcol_"] { gap: 8px; }
.stHtml .col-ep .ep-hero { margin: 0 -32px 24px; }
</style>"""
html(EXTRA_CSS)


@lru_cache(maxsize=1)
def icons() -> dict:
    """글마다 붙는 그림 기호 (app/web/src/components/columnIcons.tsx 그대로, export_column_assets.mjs)."""
    return json.loads((HERE / "column_icons.json").read_text(encoding="utf-8"))


def icon(eid: str, size: int) -> str:
    """st.html은 <svg>를 지우므로 같은 SVG를 그림 주소로 넣는다."""
    svg = icons().get(eid)
    return svg_img(svg, cls="", style=f"width:{size}px;height:{size}px;display:block") if svg else ""


def unit_of(eid: str) -> dict:
    return next(u for u in UNITS if eid in u["ids"])


def theme_units(t: dict) -> list[dict]:
    return [next(u for u in UNITS if u["no"] == n) for n in t["units"]]


def theme_of(eid: str) -> dict:
    return next(t for t in THEMES if any(eid in u["ids"] for u in theme_units(t)))


def toy_of(eid: str):
    return next((b["toy"] for b in EP[eid]["blocks"] if b["t"] == "toy"), None)


def uvars(color: str, tint: str) -> str:
    return f"--u:{color};--ut:{tint}"


# ── 읽은 글 (웹 localStorage 'onepick-column-read' 대신 세션) ──────────────────
def read_set() -> set:
    return st.session_state.setdefault("column_read", set())


def mark_read(eid: str) -> None:
    read_set().add(eid)


# ── {이름} 자리 값 (웹 useFacts) ────────────────────────────────────────────
def facts() -> dict:
    f, _ = load(api.funnel)
    a, _ = load(api.analysis)
    up = a["event"]["curves"].get("주당배당금 증가") if a else None
    end = up[-1] if up else None
    pay = lambda v: next((r[1] for r in a["payout"] if r[0] == v), None) if a else None  # noqa: E731
    ko = lambda v: fmt(v) if v is not None else None  # noqa: E731
    med = a["capacity"]["median"] if a else None
    return {
        "fail2": ko(f and f["fail2"]), "na_deficit": ko(f and f["na_deficit"]), "hold_missing": ko(f and f["hold_missing"]),
        "p24": ko(pay(24)), "p25": ko(pay(25)),
        "cap_median": (str(int(med)) if isinstance(med, float) and med.is_integer() else str(med)) if med is not None else None,
        "cap_low": ko(a["capacity"]["bins"][0][1]) if a and a["capacity"]["bins"] else None,
        "policy_filings": ko(a and a["trust"]["policy_filings"]),
        "car_up": f"{'+' if end[2] > 0 else ''}{fixed(end[2], 2)}" if end else None, "car_n": ko(end[1]) if end else None,
    }


FACTS = facts()


def term(word: str) -> str:
    g = GLOSSARY.get(word)
    if not g:
        return esc(word)
    like = f'<em> 비유하면: {esc(g["like"])}</em>' if g.get("like") else ""
    return (f'<span class="term-wrap"><button class="term">{esc(word)}</button>'
            f'<span class="term-pop" role="tooltip"><b>{esc(word)}</b> {esc(g["easy"])}{like}</span></span>')


def rich(text: str) -> str:
    """{{용어}}는 뜻이 열리는 단어로, {이름}은 API 값으로 (웹 Rich)."""
    out = []
    for p in re.split(r"(\{\{[^}]+\}\}|\{\w+\})", text):
        if m := re.fullmatch(r"\{\{(.+)\}\}", p):
            out.append(term(m[1]))
        elif m := re.fullmatch(r"\{(\w+)\}", p):
            out.append(f"<b>{esc(FACTS.get(m[1]) or '…')}</b>")
        else:
            out.append(esc(p))
    return "".join(out)


def plain_hook(hook: str) -> str:
    hook = re.sub(r"\{\{([^}]+)\}\}", r"\1", hook)
    return re.sub(r"\{(\w+)\}", lambda m: FACTS.get(m[1]) or "…", hook)


def _go(query: dict) -> None:
    query = dict(query)
    if "read" in query:  # 웹: [다음 글]을 누르면 지금 글을 읽음으로 남긴다
        mark_read(query.pop("read"))
    st.query_params.from_dict(query)


def go_button(label: str, query: dict, key: str, **kw) -> None:
    """칼럼 안에서 옮겨 가기(웹 <Link to="/column/...">). 같은 페이지 안 이동은 page_link가 주소를 바꾸지 못해 버튼으로 주소를 바꾼다."""
    st.button(label, key=key, on_click=_go, args=(query,), **kw)


def linked(key: str, body: str, page: str, query: dict | None = None, label: str = "열기") -> None:
    """HTML 한 덩어리 전체를 누르면 page로 가게 한다 (웹 <Link>). 위에 투명한 버튼·링크를 덮는다."""
    with st.container(key=f"lnk_{key}"):
        html(body)
        if page == "column":
            go_button(label, query or {}, key=f"go_{key}")
        else:
            st.page_link(PAGES[page], label=label, query_params=query)


def go_link(to: str) -> tuple[str, dict | None]:
    """글 안 링크 주소(웹 경로)를 Streamlit 페이지로. '#장' 위치는 Streamlit에서 따라가지 못한다."""
    path, _, query = to.partition("?")
    path = path.split("#")[0]
    if path.startswith("/column/"):
        return "column", {"id": path.split("/")[2]}
    if path.startswith("/company/"):
        return "company", {"code": path.split("/")[2]}
    qp = dict(x.split("=", 1) for x in query.split("&")) if query else None
    return {"/analysis": "analysis", "/check": "check", "/wealth": "wealth", "/isa-irp": "isa-irp", "/consult": "consult"}[path], qp


# ── 목록 ──────────────────────────────────────────────────────────────────
def ep_row(eid: str, is_read: bool, is_next: bool, key: str) -> None:
    e, u, t = EP[eid], unit_of(eid), toy_of(eid)
    state = "🐾 읽음" if is_read else "다음 차례" if is_next else ""
    body = (f'<div class="ep-row {"read" if is_read else ""} {"next" if is_next else ""}" style="{uvars(u["color"], u["tint"])}">'
            f'<span class="ep-row-art">{icon(eid, 40)}</span>'
            f'<span class="ep-row-body"><b><span class="ep-row-no">{e["no"]}</span>{esc(e["title"])}</b>'
            f'<span class="ep-row-hook">{esc(plain_hook(e["hook"]))}</span>'
            + (f'<span class="ep-row-toy">🖐 {TOY_NAMES[t]}</span>' if t else "")
            + f'</span><span class="ep-row-state">{state}</span></div>')
    linked(f"{key}_{eid}", body, "column", {"id": eid}, label=f"{e['no']}. {e['title']}")


CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def initial(w: str) -> str:
    c = ord(w[0]) - 0xAC00
    if 0 <= c < 11172:
        ch = CHOSUNG[c // 588]
        return {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}.get(ch, ch)
    return "A–Z"


def glossary() -> None:
    # 웹 localeCompare('ko')처럼 한글 먼저, 영문은 뒤에
    words = sorted(GLOSSARY, key=lambda w: (not ("\uac00" <= w[0] <= "\ud7a3"), w.casefold(), w))
    groups = list(dict.fromkeys(initial(w) for w in words))
    parts = ['<section class="glossary" id="glossary" aria-label="용어 사전"><h2>모아의 용어 사전</h2>',
             '<nav class="gl-index" aria-label="첫 글자로 찾기">' + "".join(f'<a href="#gl-{g}">{g}</a>' for g in groups) + "</nav>"]
    for g in groups:
        items = []
        for w in (x for x in words if initial(x) == g):
            d = GLOSSARY[w]
            where = next((e for e in EPISODES if w in e["terms"]), None)
            items.append(f'<div><dt>{esc(w)}</dt><dd>{esc(d["easy"])}'
                         + (f'<em>비유하면: {esc(d["like"])}</em>' if d.get("like") else "")
                         + (f'<a class="gl-ep" href="?id={where["id"]}" target="_self">{where["no"]}. {esc(where["title"])}</a>' if where else "")
                         + "</dd></div>")
        parts.append(f'<div class="gl-group" id="gl-{g}"><span class="gl-letter">{g}</span><dl>{"".join(items)}</dl></div>')
    html("".join(parts) + "</section>")


def index_view() -> None:
    read = read_set()
    next_id = next((x for x in READ_ORDER if x not in read), READ_ORDER[0])
    next_ep = EP[next_id]
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        html(f'<header class="col-hero" style="padding-bottom:0"><div><h1>모아의 금융 상식 칼럼</h1>'
             f'<p>주식과 배당부터 세금, 경제 이야기까지 {len(EPISODES)}편이에요. 팀원들이 실제로 궁금해한 질문 66개를 풀었고, 글마다 손으로 움직여 보는 그림이 있어요.</p></div></header>')
        q = st.text_input("칼럼 찾기", placeholder="제목·용어로 찾기 (예: 배당락)", label_visibility="collapsed", key="col_q")
    with right:
        bars = "".join(
            f'<li style="--u:{t["color"]}"><span>{esc(t["name"])}</span><b>{done} / {len(ids)}</b>'
            f'<i aria-hidden="true"><i style="width:{done / len(ids) * 100}%"></i></i></li>'
            for t in THEMES
            for ids in [[x for u in theme_units(t) for x in u["ids"]]]
            for done in [sum(x in read for x in ids)])
        with st.container(key="trail"):
            html(f'<div class="trail-card" style="margin-top:40px"><div class="trail-head"><img src="{moa("happy")}" alt="" />'
                 f'<span>모아와 함께 <b>{len(read)}</b> / {len(EPISODES)}편 읽었어요</span></div>'
                 f'<ul class="theme-bars" aria-label="묶음별로 읽은 편수">{bars}</ul></div>')
            go_button(f"{'이어서 읽기' if read else '첫 편부터 읽기'}: {next_ep['no']}. {next_ep['title']}", {"id": next_id},
                      key="trail_next", type="primary", use_container_width=True)
            if read and st.button("읽은 기록 지우기", type="tertiary"):
                read.clear()
                st.rerun()

    word = (q or "").strip()
    row = lambda eid, k: ep_row(eid, eid in read, eid == next_id, k)  # noqa: E731
    if word:
        found = [e for e in EPISODES if any(word in s for s in [e["title"], plain_hook(e["hook"]), *e["terms"]])]
        html(f'<h2 class="col-list-h" style="margin-top:24px">‘{esc(word)}’ 찾은 글 {len(found)}편</h2>')
        if found:
            for e in found:
                row(e["id"], "found")
        else:
            html('<p class="small">맞는 글이 없어요. 다른 말로 찾거나 아래 묶음에서 골라 보세요.</p>')
    else:
        html(f'<section class="col-start"><h2 id="col-start-h">처음이라면 이 {len(START_HERE)}편</h2></section>')
        for col, eid in zip(st.columns(len(START_HERE)), START_HERE):
            e, u = EP[eid], unit_of(eid)
            with col:
                linked(f"start_{eid}",
                       f'<div class="start-card {"read" if eid in read else ""}" style="{uvars(u["color"], u["tint"])};min-height:150px">'
                       f'{icon(eid, 44)}<span>{esc(e["title"])}</span>'
                       + ('<span class="paw" aria-label="읽음">🐾</span>' if eid in read else "") + "</div>",
                       "column", {"id": eid}, label=e["title"])

        tabs = {t["key"]: t["name"] for t in THEMES} | {"glossary": "📖 용어 사전"}
        cur = st.query_params.get("t", THEMES[0]["key"])
        cur = cur if cur in tabs else THEMES[0]["key"]
        st.write("")
        pick = st.segmented_control("묶음", list(tabs), format_func=tabs.get, default=cur, key="col_tab", label_visibility="collapsed")
        if pick and pick != cur:
            st.query_params["t"] = pick
            cur = pick
        theme = next((t for t in THEMES if t["key"] == cur), None)
        if theme:
            html(f'<section class="col-list" style="{uvars(theme["color"], theme["tint"])}"><p class="col-list-line">{esc(theme["line"])}</p></section>')
            for u in theme_units(theme):
                html(f'<div class="unit-block" style="{uvars(u["color"], u["tint"])}"><h3>{esc(u["name"])} '
                     f'<span>{sum(x in read for x in u["ids"])} / {len(u["ids"])}</span></h3></div>')
                for eid in u["ids"]:
                    row(eid, f"u{u['no']}")
        else:
            glossary()
    html(f'<p class="small col-note">{esc(COLUMN_NOTE)}</p>')


# ── 글 하나 ────────────────────────────────────────────────────────────────
def laws(labels: list[str]) -> str:
    passages, _ = load(api.lawPassages)
    arts = "".join(
        f'<article class="law"><b>{esc(p["label"])}</b><span class="small"> · 시행 {esc(p["effective"])}</span>'
        f'<p>{esc(p["text"])}</p><a href="{esc(p["url"])}" target="_blank" rel="noreferrer" class="small">국가법령정보센터에서 보기 ↗</a></article>'
        for lab in labels for p in (passages or []) if p["label"] == lab)
    loading_p = '<p class="small">불러오는 중…</p>'
    return (f'<details class="col-laws"><summary>📜 조문 원문 보기 <span class="small">({len(labels)}개 · 원문 그대로예요. AI가 쓴 문장이 아니에요.)</span></summary>'
            f'{arts if passages is not None else loading_p}</details>')


def block_html(b: dict) -> str:
    t = b["t"]
    if t == "h":
        return f'<h2 class="col-h">{esc(b["text"])}</h2>'
    if t == "box":
        mark = "🙅 " if b["kind"] == "myth" else "📌 " if b["kind"] == "sum" else "💡 "
        return (f'<aside class="col-box col-box--{b["kind"]}"><b>{mark}{esc(b["title"])}</b>'
                f'<ul>{"".join(f"<li>{rich(x)}</li>" for x in b["items"])}</ul></aside>')
    if t == "p":
        src = f'<span class="src {SRC_CLASS[b["src"]]}">{b["src"]}</span>' if b.get("src") else ""
        return f'<p class="col-p">{src}{rich(b["text"])}</p>'
    if t == "say":
        if b["who"] == "moa":
            return f'<div class="msg with col-say"><img src="{moa(b.get("mood") or "base")}" alt="모아" /><div>{rich(b["text"])}</div></div>'
        return f'<div class="col-say col-say--me"><div class="msg me">{rich(b["text"])}</div></div>'
    raise ValueError(t)


def quiz(b: dict, key: str) -> None:
    html(f'<div class="quiz" style="margin-bottom:0;border-bottom:0;border-radius:24px 24px 0 0;padding-bottom:4px">'
         f'<span class="col-no">QUIZ</span><p class="quiz-q">{esc(b["q"])}</p></div>')
    pick = st.pills("퀴즈", list(range(len(b["options"]))), format_func=lambda i: b["options"][i], key=key, label_visibility="collapsed")
    tail = ""
    if pick is not None:
        right = pick == b["answer"]
        tail = (f'<div class="moa-say" style="margin-top:14px" aria-live="polite"><img src="{moa("happy" if right else "sad")}" alt="" class="moa-pop" />'
                f'<p>{"정답이에요! " if right else "아쉬워요. "}{rich(b["why"])}</p></div>')
    html(f'<div class="quiz" style="margin-top:0;border-top:0;border-radius:0 0 24px 24px;padding-top:0">{tail}</div>')


def episode_view(eid: str) -> None:
    ep, u, theme = EP[eid], unit_of(eid), theme_of(eid)
    k = u["ids"].index(eid)
    i = READ_ORDER.index(eid)
    nxt = EP.get(READ_ORDER[i + 1]) if i + 1 < len(READ_ORDER) else None
    st.set_page_config(page_title=f"{ep['title']} · 원픽 금융 상식 칼럼")
    uv = uvars(u["color"], u["tint"])

    c1, c2, _ = st.columns([1.2, 1.4, 4])
    with c1:
        go_button("← 금융 상식 칼럼", {}, key="crumb_all", type="tertiary")
    with c2:
        go_button(theme["name"], {"t": theme["key"]}, key="crumb_theme", type="tertiary")
    # 웹처럼 새 글은 맨 위부터 보여 준다
    run_js(f"if(window.__opEp!=={json.dumps(eid)}){{window.__opEp={json.dumps(eid)};"
           "document.querySelectorAll('[data-testid=stMain],[data-testid=stAppViewContainer],section.main').forEach(e=>e.scrollTo(0,0));window.scrollTo(0,0)}")
    steps = "".join(f'<i class="{"on" if j <= k else ""}"></i>' for j, _ in enumerate(u["ids"]))
    terms = "".join(term(t) for t in ep["terms"])
    html(f'<div class="col-ep" style="{uv}"><header class="ep-hero"><div class="wrap ep-hero-in" style="padding:0 32px"><div>'
         f'<nav class="ep-crumb" aria-label="위치"><span style="color:var(--gray)">금융 상식 칼럼</span><span>{esc(theme["name"])}</span><span>{esc(u["name"])}</span>'
         f'<span class="ep-steps" aria-label="{len(u["ids"])}칸 중 {k + 1}번째">{steps}</span></nav>'
         f'<h1>{esc(ep["title"])}</h1><p class="ep-hook">{rich(ep["hook"])}</p></div>'
         f'<div class="ep-icon">{icon(eid, 120)}</div></div>'
         f'<div class="wrap" style="padding:0 32px"><div class="col-terms col-terms--big" aria-label="이 글에서 배우는 말"><span>이 글에서 배우는 말</span>{terms}</div></div>'
         f'</header></div>')

    _, mid, _ = st.columns([1, 6, 1])
    with mid, st.container(key=f"epcol_{eid}"):
        head = ""
        if ep.get("qs"):
            lis = "".join(f'<li><span class="qs-no">{esc(q.split(" ")[0])}</span>{esc(q[q.index(" ") + 1:])}</li>' for q in ep["qs"])
            head += (f'<aside class="qs-box" style="{uv}" aria-label="이 글이 답하는 질문"><b>이 글이 답하는 질문</b><ul>{lis}</ul>'
                     f'<span class="small">팀원들이 모은 질문 목록에서 가져왔어요.</span></aside>')
        expl = {"쉬운 설명": "비유로 푼 설명", "조문": "법에 적힌 내용", "팀 해석": "원픽 팀이 정한 해석·표시", "데이터": "원픽 분석 결과"}
        head += ('<details class="src-help"><summary>문단 앞 표시 읽는 법</summary>'
                 + "".join(f'<span><span class="src {SRC_CLASS[s]}">{s}</span>{w}</span>' for s, w in expl.items()) + "</details>")
        buf = [head]

        def flush():
            if buf:
                html(f'<div class="col-read" style="{uv};max-width:none">{"".join(buf)}</div>')
                buf.clear()

        for j, b in enumerate(ep["blocks"]):
            if b["t"] in ("h", "box", "p", "say"):
                buf.append(block_html(b))
                continue
            flush()
            if b["t"] == "quiz":
                quiz(b, f"quiz_{eid}_{j}")
            elif b["t"] == "toy":
                toy(b["toy"], f"{eid}_{j}")
            elif b["t"] == "link":
                page, qp = go_link(b["to"])
                if page == "column":
                    go_button(b["text"], qp, key=f"lnk_in_{eid}_{j}")
                else:
                    st.page_link(PAGES[page], label=b["text"], query_params=qp)
        if ep["laws"]:
            buf.append(laws(ep["laws"]))
        buf.append(f'<p class="small col-note">{esc(COLUMN_NOTE)}</p>')
        flush()
        if nxt:
            nu = unit_of(nxt["id"])
            linked(f"next_{eid}",
                   f'<div class="next-stone" style="{uvars(nu["color"], nu["tint"])}"><span class="stone-disc">{icon(nxt["id"], 52)}</span>'
                   f'<span><span class="small">다음 글 · {esc(theme_of(nxt["id"])["name"])} › {esc(nu["name"])}</span><b style="display:block;font:400 24px/1.25 \'Do Hyeon\'">{esc(nxt["title"])}</b></span></div>',
                   "column", {"id": nxt["id"], "read": eid}, label=f"다음 글: {nxt['title']}")
        else:
            linked(f"next_{eid}",
                   f'<div class="next-stone"><span class="stone-disc"><img src="{moa("happy")}" alt="" width="52" /></span>'
                   f'<span><span class="small">마지막 글까지 왔어요</span><b style="display:block;font:400 24px/1.25 \'Do Hyeon\'">칼럼 목록으로 돌아가기</b></span></div>',
                   "column", {"read": eid}, label="칼럼 목록으로 돌아가기")


# 웹: 글을 85% 넘게 내려 읽거나 [다음 글]을 누르면 읽음. Streamlit은 스크롤을 알 수 없어 [다음 글]을 누를 때만 센다(_go)
eid = st.query_params.get("id")
if eid and eid not in EP:
    html('<div class="loading">찾는 글이 없어요.</div>')
    go_button("칼럼 목록으로", {}, key="back_list")
elif eid:
    episode_view(eid)
else:
    index_view()
