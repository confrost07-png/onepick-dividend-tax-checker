"""내 배당 점검 (웹 app/web/src/pages/Check.tsx): ①~⑤ 문답 → ⑥ 확인 → 결과.

답은 api.parse(= /api/chat/parse)가 읽고, 계산은 api.checkup(= /api/checkup)이 한다. 문구는 api.script()와 Check.tsx 그대로.
입력은 이 세션(st.session_state)에만 두고 저장하지 않는다. 대화 흐름은 Check.tsx의 함수(ask·confirm·start·submit·onEntry·onImage·onChip)를
같은 이름·같은 분기로 옮겼다.
"""
from __future__ import annotations

import base64
import io
import re

import streamlit as st

from common import api, badge_class, esc, fmt, html, moa, mood_of, persona_id, web_text, won

PAGES = st.session_state["_pages"]
ENTRY, CONFIRM, RESULT = -1, 5, 6
UNSET = object()  # 웹 Answers의 undefined (None은 '모름'= null)

# ── 웹과 같은 class를 Streamlit 부품에 입히는 덧칠 ─────────────────────────
html("""<style>
.st-key-chk_chips button, .st-key-chk_outlinks button[kind="tertiary"] { border-radius: 999px; background: var(--wave); color: var(--sea); border: 0; padding: 6px 14px; min-height: 0; font-size: 14px; font-weight: 700; }
.st-key-chk_chips button:hover { background: #DCE4FF; color: var(--sea); }
.st-key-chk_chips button[kind="primary"] { box-shadow: inset 0 0 0 2px var(--sea); }
.st-key-chk_tools button { border: 0; background: none; padding: 2px 4px; min-height: 0; color: var(--sea); font-size: 14px; font-weight: 700; text-decoration: underline; text-underline-offset: 3px; }
.st-key-chk_mine { background: var(--paper); border-radius: var(--r-lg); padding: 20px; position: sticky; top: 88px; }
.st-key-chk_mine button { justify-content: flex-start; text-align: left; width: 100%; border: 0; background: #fff; border-radius: 14px; padding: 10px 14px; }
.st-key-chk_mine button p { text-align: left; }
.st-key-chk_result { background: #fff; border: 1px solid var(--line); border-radius: var(--r-xl); padding: 32px; }
.st-key-chk_drawer { background: #fff; border-radius: var(--r-lg); box-shadow: -10px 0 40px rgba(25,31,40,.14); padding: 22px; border: 1px solid var(--line); }
.st-key-chk_list { background: #fff; border: 1px solid var(--line); border-radius: var(--r-md); padding: 14px; box-shadow: 0 12px 32px rgba(25,31,40,.12); }
</style>""")


# ── 상태 ────────────────────────────────────────────────────────────────
def S() -> dict:
    return st.session_state["chk"]


def new_state() -> dict:
    return {"msgs": [], "step": ENTRY, "ans": {}, "chips": [], "divType": None, "fails": 0, "editing": False,
            "fresh": -1, "result": None, "drawer": False, "listOpen": False, "photo": None, "send": False,
            "who": None, "auto": False, "fired": "", "hits": None, "pick": None, "isa": None, "isa_err": ""}


s, s_err = None, None
try:
    s = api.script()
except Exception as e:  # noqa: BLE001
    s_err = str(e)

pid = persona_id()
who = None
if pid:
    try:
        who = api.persona(pid)
    except Exception:  # noqa: BLE001
        who = None

if "chk" not in st.session_state:
    st.session_state["chk"] = new_state()

GLOSSARY = web_text()["column"]["GLOSSARY"]
GLOSSARY_N = len(GLOSSARY)
# app/web/src/checkFlow.ts termKey·sameTerm과 같은 규칙: 질문하는 끝말을 떼고 남은 말이 용어 사전에 글자 그대로 있어야 용어로 본다
TERM_TAILS = [
    "알려주세요", "알려줘요", "알려줄래", "알려줘", "설명해주세요", "설명해줘요", "설명해줘", "궁금해요", "궁금해",
    "무엇인가요", "무엇이에요", "무엇이야", "무엇", "뭐예요", "뭐에요", "뭔가요", "뭔데", "뭐야", "뭐지", "뭐죠", "뭐임", "뭐",
    "이라는게", "라는게", "이라는건", "라는건", "이란", "란", "뜻이", "뜻은", "뜻", "의미가", "의미는", "의미",
    "인가요", "이에요", "예요", "에대해서", "에대해",
]
TERM_PARTICLES = ["은", "는", "이", "가", "을", "를"]


def term_norm(t: str) -> str:
    return re.sub(r"\s", "", t).upper()


def term_key(text: str, keys) -> str | None:
    """용어 하나만 물었으면 용어 사전의 그 용어, 아니면 None (checkFlow.ts termKey)"""
    index = {term_norm(k): k for k in keys}
    t = re.sub(r"[?？.!~]+$", "", term_norm(text))
    seen = [t]
    while True:
        w = next((x for x in TERM_TAILS if t.endswith(x) and len(t) > len(x)), None)
        if not w:
            break
        t = t[: -len(w)]
        seen.append(t)
    for c in seen:  # 덜 뗀 말부터: '공모가'처럼 끝 글자가 조사처럼 보이는 용어를 지키려고
        if c in index:
            return index[c]
    for c in seen:
        for p in TERM_PARTICLES:
            if c.endswith(p) and c[: -len(p)] in index:
                return index[c[: -len(p)]]
    return None


def same_term(faq_title: str, key: str) -> bool:
    k = term_norm(key)
    return term_norm(faq_title) == k or any(term_norm(p) == k for p in re.split(r"[·()]", faq_title))


def glossary_faq(t: str) -> dict | None:
    """금융 상식 칼럼 용어 사전에서 찾기 (Check.tsx glossaryFaq)"""
    key = term_key(t, GLOSSARY)
    if not key:
        return None
    g = GLOSSARY[key]
    return {"id": f"glossary-{key}", "title": key, "answer": f"{g['easy']} (비유하면: {g['like']})" if g.get("like") else g["easy"],
            "notice": "원픽 팀이 쓴 쉬운 풀이 초안이에요(팀 검토 전). 내 경우에 맞는 세무·투자 조언은 아니에요",
            "by": "금융 상식 칼럼 용어 사전에서 찾음", "source_label": "원픽 금융 상식 칼럼", "source_url": "/column"}


# ── app/web/src/checkFlow.ts (흐름 판단: 챗봇이 말한 값 = '내 답'에 보이는 값 = 계산에 보내는 값) ──
BASE_UNUSED_TAG = "계산에 안 씀"
NOT_ASKED = "묻지 않음"


def base_unused(a: dict) -> bool:
    """④에 다른 소득이 있으면 ⑤ 과세표준은 묻지도, 계산에 쓰지도 않는다"""
    return bool(a.get("otherIncome"))


def next_after(frm: int, nxt: dict, editing: bool) -> dict:
    """한 칸에 답한 뒤 갈 곳 (checkFlow.ts nextAfter)"""
    r = next_step(frm, nxt, editing)
    # ⑥으로 가려는데 아직 답하지 않은 칸이 있으면(질문 도중 앞 칸을 고친 경우 등) 그 칸부터 묻는다
    missing = first_missing(nxt) if r["step"] == CONFIRM else None
    return r if missing is None else {**r, "step": missing, "reuseBase": False}


def first_missing(a: dict) -> int | None:
    """아직 답하지 않은 첫 칸. 모두 답했으면 None (⑤는 ④가 '있음'이면 묻지 않음) (checkFlow.ts firstMissing)"""
    if "holdings" not in a:
        return 0
    if "interest" not in a:
        return 1
    if "other" not in a:
        return 2
    if "otherIncome" not in a:
        return 3
    if not base_unused(a) and "base" not in a:
        return 4
    return None


def next_step(frm: int, nxt: dict, editing: bool) -> dict:
    note = frm == 3 and bool(nxt.get("otherIncome"))
    if frm == 3 and not nxt.get("otherIncome"):
        if "base" not in nxt:
            return {"step": 4, "otherIncomeNote": note, "reuseBase": False}
        if not editing:
            return {"step": CONFIRM, "otherIncomeNote": note, "reuseBase": nxt["base"] is not None}
    if editing or frm >= 4 or note:
        return {"step": CONFIRM, "otherIncomeNote": note, "reuseBase": False}
    return {"step": frm + 1, "otherIncomeNote": note, "reuseBase": False}


def edit_block(i: int, a: dict) -> str | None:
    if i == 4 and base_unused(a):
        return "④에서 사업·연금·기타소득이 있다고 하셔서 ⑤ 과세표준은 계산에 쓰지 않아요. 다른 소득이 없으면 먼저 ④를 눌러 고쳐 주세요."
    return None


def checkup_body(a: dict) -> dict:
    holdings = a.get("holdings") or []
    other = a.get("other") or {}
    return {"holdings": holdings, "interest": a.get("interest"),
            "other_domestic": other.get("domestic"), "other_foreign": other.get("foreign"),
            "base": None if base_unused(a) else a.get("base"), "has_other_income": bool(a.get("otherIncome")),
            "holdings_answer": None if holdings else (a.get("holdingsSkip") or "없음"), "outside": a.get("outside") or []}


def base_photo(step: int, a: dict, amount: int) -> dict:
    if step == 4:
        return {"mode": "fill", "answers": a, "say": ""}
    answers = {**a, "base": amount}
    say_ = (f"⑤ 과세표준을 영수증 사진에서 읽은 {won(amount)}으로 넣어 두었어요. 다만 ④에서 사업·연금·기타소득이 있다고 하셔서 세금 비교에는 쓰지 않아요. 다른 소득이 없으면 오른쪽 '내 답'에서 ④를 눌러 고쳐 주세요."
            if base_unused(a) else
            f"⑤ 과세표준을 영수증 사진에서 읽은 {won(amount)}으로 넣어 두었어요. 영수증의 ㊼ 칸과 다르면 오른쪽 '내 답'에서 ⑤를 눌러 고쳐 주세요.")
    return {"mode": "store", "answers": answers, "say": say_}


def amount_text(v) -> str:
    return "모름" if v is None else "없음" if v == 0 else won(v)


def answer_text(i: int, a: dict) -> str | None:
    if i == 0:
        if "holdings" not in a:
            return None
        out = f"{', '.join(a['outside'])} (목록에 없어 뺌)" if a.get("outside") else ""
        if not a["holdings"]:
            return out or a.get("holdingsSkip") or "없음"
        return " · ".join([*(f"{h['company']} {fmt(h['shares'])}주" for h in a["holdings"]), *([out] if out else [])])
    if i == 1:
        return None if "interest" not in a else amount_text(a["interest"])
    if i == 2:
        if "other" not in a:
            return None
        d, f = a["other"].get("domestic"), a["other"].get("foreign")
        # 계산은 한쪽이라도 '모름'이면 모르는 항목으로 본다 → 화면도 '모름'으로 보인다
        if not d and not f:
            return "모름" if d is None or f is None else "없음"
        return " · ".join(t for t in (d != 0 and f"국내 {amount_text(d)}", f != 0 and f"해외·ETF·펀드 {amount_text(f)}") if t)
    if i == 3:
        return None if "otherIncome" not in a else "있음" if a["otherIncome"] else "없음"
    if i == 4:
        if base_unused(a):
            return NOT_ASKED if a.get("base") is None else f"{amount_text(a['base'])} ({BASE_UNUSED_TAG})"
        if "base" not in a:
            return None
        return s["no_wage"] if a["base"] == 0 else amount_text(a["base"])
    return None


# ── Check.tsx 함수들 ───────────────────────────────────────────────────────
def mine_at(i: int) -> str | None:
    return (who["answers"][i] if who else None) if 0 <= i < 5 else None


def chips_for(i: int) -> list[str]:
    qs = s["questions"][i]["chips"]
    mine = mine_at(i)
    return [mine, *[c for c in qs if c != mine]] if mine else qs


def say(text: str, mood: str = "base", note: str | None = None, **extra) -> None:
    S()["msgs"].append({"from": "bot", "text": text, "mood": mood, "note": note, **extra})


def me(text: str, note: str | None = None) -> None:
    S()["msgs"].append({"from": "me", "text": text, "note": note})


def term_answer(t: str, r: dict) -> dict | None:
    """용어 사전에 그대로 있는 용어를 물었으면 그 풀이. 서버가 같은 용어의 기본 금융 용어 답을 골랐으면 그 답 (Check.tsx termAnswer)"""
    g = glossary_faq(t)
    if not g:
        return None
    f = r.get("faq")
    return f if f and same_term(f["title"], g["title"]) else g


def show_faq(f: dict) -> None:
    say(f["answer"], "happy", faq=f)


def set_text(t: str) -> None:
    st.session_state["chk_text"] = t


def add_company(name: str) -> None:
    t = st.session_state.get("chk_text", "")
    set_text(f"{re.sub(r'[,·]$', '', t.strip())}, {name} " if t.strip() else f"{name} ")


def term_scope() -> str:
    return s["term_scope"].replace("{glossary_n}", fmt(GLOSSARY_N))


def ask(i: int) -> None:
    c = S()
    c.update(step=i, fails=0, divType=None)
    say(s["questions"][i]["ask"], "base", s["scope_guide"] if i == 0 else s["receipt_guide"] if i == 4 else None)
    c["chips"] = chips_for(i)


def confirm() -> None:
    c = S()
    c.update(step=CONFIRM, editing=False)
    say(f"{s['confirm_ask']} 오른쪽 '내 답'에서 확인해 주세요. {s['confirm_note']}", "curious")
    c["chips"] = s["confirm_chips"]


def start() -> None:
    c = S()
    c.update(msgs=[], ans={}, result=None, drawer=False, step=ENTRY, fails=0, divType=None, hits=None, pick=None, isa=None, preset_done=None, send=False, editing=False)
    greet = re.sub(r"^안녕하세요\.\s*", f"안녕하세요, {who['name']}님! 모아예요. " if who else "안녕하세요, 모아예요! ", s["greeting"], count=1)
    say(greet, "happy", s["ai_note"])
    say(s["start_guide"])
    c["chips"] = s["addon_chips"]


def advance(frm: int, nxt: dict) -> None:
    n = next_after(frm, nxt, S()["editing"])
    if n["otherIncomeNote"]:
        say(s["other_income_note"], "curious")
    if n["reuseBase"] and nxt.get("base") is not None:  # ⑤는 영수증 사진 등으로 먼저 받아 두었으면 다시 묻지 않는다
        say(f"⑤ 과세표준은 앞서 받은 {won(nxt['base'])}을 쓸게요.")
    if n["step"] == CONFIRM:
        confirm()
        return
    ask(n["step"])


def run_checkup() -> None:
    c, a = S(), S()["ans"]
    if "holdings" not in a:
        return
    c["chips"] = []
    say("계산해 볼게요…", "curious")
    try:
        r = api.checkup(checkup_body(a))
        c.update(result=r, step=RESULT)
        say(r["headline"], "curious" if r["no_target"] else "happy" if r["tax"]["direction"] == "감소" else "base")
    except Exception as e:  # noqa: BLE001
        say(f"계산하지 못했어요: {e}", "sad")
        c["chips"] = s["confirm_chips"]


def edit(i: int) -> None:
    c = S()
    if c["step"] == RESULT:
        return
    block = edit_block(i, c["ans"])
    if block:
        say(block, "curious")
        return
    c["editing"] = True
    say(f"{s['step_labels'][i]} 항목을 다시 여쭐게요.", "base")
    c.update(step=i, fails=0, divType=None)
    say(s["questions"][i]["ask"], "base", s["scope_guide"] if i == 0 else None)
    c["chips"] = chips_for(i)


def retry_text(error: str | None) -> str:
    if error and re.search(r"주세요\.?$", error.strip()):
        return error
    return s["parse_retry"].replace("{error}", error or "")


def mark_fixed(fixed: str | None) -> None:
    if fixed:
        msgs = S()["msgs"]
        idx = [i for i, m in enumerate(msgs) if m["from"] == "me"]
        if idx:
            msgs[idx[-1]]["note"] = s["layout_fixed"].replace("{text}", fixed)


def suggest(text: str, reply: str | None) -> None:
    say(reply or "", "curious")
    set_text(text)


def stop() -> None:
    c = S()
    c.update(step=ENTRY, ans={}, fails=0, divType=None, editing=False)
    say(s["stop_reply"], "base")
    c["chips"] = s["addon_chips"]


def submit(raw: str) -> None:
    c = S()
    t = raw.strip()
    if not t:
        return
    set_text("")
    if len(t) > s["max_chars"]:
        say(f"{s['max_chars']}자까지만 받을 수 있어요. 짧게 다시 알려 주세요.", "curious")
        return
    me(t)
    word = re.sub(r"[.!~?\s]+$", "", t)
    step = c["step"]
    if word in s["restart_words"]:
        start()
        return
    if word in s["stop_words"] and step != ENTRY:
        stop()
        return
    if step == RESULT:
        return
    if step == CONFIRM:
        if t == s["confirm_chips"][0] or word in s["confirm_yes"]:
            run_checkup()
            return
        if t == s["confirm_chips"][1] or word in s["confirm_no"]:
            say(f"{s['edit_ask']} 오른쪽 '내 답'에서 고칠 칸을 누르거나 아래에서 골라 주세요.", "curious")
            c["chips"] = s["step_labels"][:5]
            return
        if t in s["step_labels"] and s["step_labels"].index(t) < 5:
            edit(s["step_labels"].index(t))
            return
        say("[맞아요]나 [고칠게요]를 눌러 주세요.", "curious")
        c["chips"] = s["confirm_chips"]
        return
    if step == ENTRY:
        on_entry(t)
        return
    q = s["questions"][step]
    if q["kind"] == "other_dividend" and not c["divType"] and not re.search(r"\d", t) and s["dividend_types"].get(t):
        c["divType"] = s["dividend_types"][t]
        say(s["dividend_amount_ask"].replace("{kind}", t))
        c["chips"] = s["dividend_amount_chips"]
        return
    if q["kind"] == "base" and t == s["receipt_chip"]:
        say(s["receipt_guide"], "curious")
        return
    try:
        r = api.parse(q["kind"], t, c["divType"])
    except Exception as e:  # noqa: BLE001
        say(f"잠시 연결이 안 돼요: {e}", "sad")
        return
    mark_fixed(r.get("fixed_text"))
    term = term_answer(t, r)
    if term:
        show_faq(term)
        say(q["ask"])
        c["chips"] = chips_for(step)
        return
    if r.get("guard"):
        say(r.get("reply") or "", "curious")
        if r.get("consult"):
            c["chips"] = ["세무상담 예약신청", *q["chips"]]
        return
    if r.get("chat"):
        say(r["chat"], "happy")
        say(q["ask"])
        c["chips"] = chips_for(step)
        return
    if r.get("suggest_text"):
        suggest(r["suggest_text"], r.get("reply"))
        return
    if r.get("question"):
        f = r.get("faq")
        if f:
            show_faq(f)
        else:
            say(r.get("help") or s["step_help"][q["kind"]], "curious")
        say(q["ask"])
        c["chips"] = chips_for(step)
        return
    if r.get("add_holdings"):
        cur = c["ans"].get("holdings") or []
        added = [h for h in r["add_holdings"] if not any(x["company"] == h["company"] for x in cur)]
        dup = [h for h in r["add_holdings"] if any(x["company"] == h["company"] for x in cur)]
        if added:
            c["ans"] = {**c["ans"], "holdings": [*cur, *added]}
            c["ans"].pop("holdingsSkip", None)
            c["fresh"] = 0
            say(s["other_holding_added"].replace("{names}", ", ".join(h["company"] for h in added)), "happy")
        if dup:
            say(s["other_holding_dup"].replace("{names}", ", ".join(h["company"] for h in dup)), "curious")
        c["divType"] = None
        say(q["ask"])
        c["chips"] = chips_for(step)
        return
    if r.get("prompt"):
        say(r["prompt"], "curious")
        return
    if not r.get("ok"):
        c["fails"] += 1
        say(retry_text(r.get("error")), "curious", s["stuck_hint"] if c["fails"] >= 3 else None)
        return
    if r.get("by") == "AI":
        c["msgs"][-1]["note"] = s["ai_read_mark"]
    nxt = dict(c["ans"])
    kind = q["kind"]
    if kind == "holdings":
        nxt["holdings"] = r["value"]
        nxt["holdingsSkip"] = r.get("skip")
        nxt["outside"] = r.get("excluded")
        if r.get("skip") and r.get("reply"):
            say(r["reply"])
        if r.get("note"):  # 목록에 없는 종목은 빼고 넘어감
            say(r["note"], "curious")
    elif kind == "amount":
        nxt["interest"] = r["value"]
    elif kind == "other_dividend":
        nxt["other"] = r["value"]
    elif kind == "yesno":
        nxt["otherIncome"] = r["value"]
    else:
        nxt["base"] = r["value"]
    c["ans"] = nxt
    c["fresh"] = step
    advance(step, nxt)


def on_entry(t: str) -> None:
    c = S()
    try:
        r = api.parse("holdings", t)
    except Exception as e:  # noqa: BLE001
        say(f"잠시 연결이 안 돼요: {e}", "sad")
        return
    mark_fixed(r.get("fixed_text"))
    term = term_answer(t, r)
    if term:
        show_faq(term)
        c["chips"] = s["addon_chips"]
        return
    f = None if (r.get("guard") or r.get("chat") or r.get("ok")) else r.get("faq")
    if r.get("guard"):
        say(r.get("reply") or "", "curious")
    elif r.get("chat"):
        say(r["chat"], "happy")
    elif r.get("suggest_text"):
        suggest(r["suggest_text"], r.get("reply"))
        return
    elif f:
        show_faq(f)
    elif r.get("ok"):
        nxt = {**c["ans"], "holdings": r["value"], "holdingsSkip": r.get("skip"), "outside": r.get("excluded")}
        if r.get("skip") and r.get("reply"):
            say(r["reply"])
        if r.get("note"):
            say(r["note"], "curious")
        c["ans"] = nxt
        c["fresh"] = 0
        advance(0, nxt)
        return
    elif r.get("code") == "not_found":
        say(retry_text(r.get("error")), "curious")
    elif r.get("code") == "missing_shares":
        say(r.get("error") or "", "curious")
    else:
        say(s["entry_fallback"], "curious")
    c["chips"] = s["addon_chips"]


def shrink(data: bytes, mx: int = 1600) -> str:
    """사진을 긴 변 1600px 이하 JPEG(data URL)로 줄인다 (Check.tsx shrink와 같은 크기·품질)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    k = min(1, mx / max(im.width, im.height))
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def on_image(kind: str) -> None:
    c = S()
    up = st.session_state.get(f"chk_photo_{kind}_{c.get('photo_n', 0)}")
    if up is None:
        return
    base = kind == "base"
    here = c["step"] == 4 if base else c["step"] in (ENTRY, 0)
    c.update(listOpen=False, photo=None, photo_n=c.get("photo_n", 0) + 1)
    me("📷 원천징수영수증 2쪽" if base else "📷 보유 종목 사진", s["base_image_note"] if base else s["image_note"])
    say(s["base_image_reading"] if base else s["image_reading"])
    try:
        photo = shrink(up.getvalue())
        r = api.baseImage(photo) if base else api.holdingsImage(photo)
        if not r.get("ok") or not r.get("text"):
            say(r.get("error") or "", "curious")
            return
        if base and r.get("bracket"):  # 결과의 ISA·IRP 구간을 미리 고르는 데만 쓴다
            c["ans"] = {**c["ans"], "receiptBracket": r["bracket"]}
        if here:
            say(r.get("reply") or "", "curious" if r.get("missing") else "happy")
            set_text(r["text"])
        elif base:
            amount = r.get("amount")
            if amount is None:
                say(r.get("error") or "", "curious")
                return
            b = base_photo(c["step"], c["ans"], amount)
            c["ans"] = b["answers"]  # c["ans"]에서 만들어 receiptBracket도 그대로 남는다
            c["fresh"] = 4
            say(b["say"], "curious" if b["answers"].get("otherIncome") else "happy")
        else:
            p = api.parse("holdings", r["text"])
            if not p.get("ok"):
                say(f"사진에서 {r['text']}로 읽었는데, {p.get('error') or '확인이 필요해요'}. 오른쪽 '내 답'에서 ①을 눌러 고쳐 주세요.", "curious")
                return
            c["ans"] = {**c["ans"], "holdings": p["value"], "outside": p.get("excluded")}
            c["ans"].pop("holdingsSkip", None)
            say(f"① 보유 종목을 사진에서 읽은 대로 넣어 두었어요: {r['text']}. 틀리면 오른쪽 '내 답'에서 ①을 눌러 고쳐 주세요.", "happy")
    except Exception as e:  # noqa: BLE001
        say(f"잠시 연결이 안 돼요: {e}", "sad")


def on_chip(ch: str) -> None:
    c = S()
    if ch == s["docs_chip"]:
        me(ch)
        say(s["docs_guide"]["text"], "happy", docs=s["docs_guide"])
        return
    if ch == s["term_chip"]:
        me(ch)
        say(term_scope(), "curious")
        c["chips"] = [*s["term_examples"], s["addon_chips"][0]] if c["step"] == ENTRY else s["term_examples"]
        return
    if c["step"] == ENTRY and ch == s["addon_chips"][0]:
        me(ch)
        ask(0)
        return
    if c["step"] == ENTRY and s["addon_replies"].get(ch) and ch != "세무상담 예약신청":
        me(ch)
        say(s["addon_replies"][ch])
        return
    if ch == "세무상담 예약신청":
        me(ch)
        say("점검을 마치면 결과 아래 버튼으로 세무상담 신청 화면(모형)에 결과를 함께 가져갈 수 있어요. 바로 가려면 위 메뉴의 '자산관리'를 눌러 주세요.")
        return
    submit(ch)


def on_form() -> None:
    submit(st.session_state.get("chk_text", ""))


def toggle(key: str) -> None:
    S()[key] = not S()[key]


def set_photo(kind: str) -> None:
    S()["photo"] = None if S()["photo"] == kind else kind


def on_list_pick() -> None:
    v = st.session_state.get("chk_list_pick")
    if v:
        add_company(v.split(" · ")[0])
        st.session_state["chk_list_pick"] = None


def run_auto() -> None:
    """내 정보의 [이 답으로 점검 챗봇 돌려 보기](/check?auto=1): 답을 차례로 넣고 ⑥ 확인에서 멈춘다(맞아요는 고객이 누름).
    웹은 0.7초 간격으로 넣고, Streamlit은 한 번에 넣는다."""
    c = S()
    while c["auto"] and who:
        if c["step"] in (CONFIRM, RESULT):
            c["auto"] = False
            st.query_params.clear()
            return
        key = f"{who['id']}:{c['step']}"
        nxt = s["addon_chips"][0] if c["step"] == ENTRY else mine_at(c["step"])
        if not nxt or nxt not in c["chips"] or c["fired"] == key:
            c["auto"] = False
            return
        c["fired"] = key
        on_chip(nxt)


# ── 화면 ────────────────────────────────────────────────────────────────
if s_err:
    html(f'<p class="error">{esc(s_err)}</p>')
    st.stop()

c = S()
if c["who"] != (who["id"] if who else None) or not c["msgs"]:  # 웹: 대본이 오거나 로그인한 사람이 바뀌면 새로 시작
    c["who"] = who["id"] if who else None
    start()
if st.query_params.get("auto") == "1" and who:
    if not c.get("auto_seen"):  # 내 정보에서 새로 들어오면 처음부터 시작해 답을 넣는다 (웹은 화면을 새로 연다)
        start()
        c.update(auto=True, auto_seen=True, fired="")
else:
    c["auto_seen"] = False
run_auto()

step, ans = c["step"], c["ans"]
html(f'<div class="check-head"><h1>{esc(s["title"])}</h1>'
     f'<p class="small" style="margin:0">{esc(s["result_lead"])} 입력은 계산에만 쓰고 저장하지 않아요(개인정보 처리 안내).</p></div>')
done = [answer_text(i, ans) is not None for i in range(5)]
bars = "".join(
    f'<span title="{esc(l)}" class="{"done" if i < step or (i < 5 and done[i] and step >= CONFIRM) else "now" if i == step else ""}"></span>'
    for i, l in enumerate(s["step_labels"]))
html(f'<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="6" aria-valuenow="{min(step, 6)}" aria-label="점검 진행">{bars}</div>')


def msg_html(m: dict) -> str:
    if m["from"] == "me":
        note = f"<small>{esc(m['note'])}</small>" if m.get("note") else ""
        return f'<div class="msg me">{esc(m["text"])}{note}</div>'
    f, d = m.get("faq"), m.get("docs")
    body = f'<b class="faq-title">📘 {esc(f["title"])}</b>' if f else ""
    body += esc(m["text"])
    if m.get("note"):
        body += f'<small style="margin-top:6px">{esc(m["note"])}</small>'
    if d:
        items = "".join(
            f'<li><b>{esc(x["title"])}</b><span>{esc(x["how"])}</span><span class="docs-links">'
            + "".join(f'<a href="{esc(l["url"])}" target="_blank" rel="noreferrer">{esc(l["label"])} 열기 ↗</a>' for l in x["links"])
            + "</span></li>" for x in d["items"])
        body += f'<ol class="docs-guide">{items}</ol><small style="margin-top:6px">{esc(d["note"])}</small>'
    if f:
        body += (f'<small class="faq-note">{esc(f["notice"])} · {esc(f["by"])} · 출처: '
                 f'<a href="{esc(f["source_url"])}" target="_blank" rel="noreferrer">{esc(f["source_label"])}</a></small>')
    return f'<div class="msg with"><img src="{moa(m.get("mood") or "base")}" alt="" /><div>{body}</div></div>'


left, right = st.columns([1, 0.34], gap="large")
with left:
    html('<div class="chat" aria-live="polite">' + "".join(msg_html(m) for m in c["msgs"]) + "</div>")
    if step != RESULT:
        if c["chips"]:
            with st.container(key="chk_chips", horizontal=True, gap="small"):
                mine = mine_at(step)
                for i, ch in enumerate(c["chips"]):
                    is_mine = ch == mine
                    st.button(f"내 답 · {ch}" if is_mine else ch, key=f"chip_{len(c['msgs'])}_{i}", on_click=on_chip, args=(ch,),
                              type="primary" if is_mine else "secondary", help=f"{who['name']}님의 답" if is_mine else None)
        if c["listOpen"]:
            with st.container(key="chk_list"):
                companies = api.companyList()
                prefs = sum(1 for x in companies if x.get("pref_of"))
                firms = len(companies) - prefs
                html(f"<b>조회 대상 기업 {fmt(firms)}곳{f' · 우선주 {fmt(prefs)}종목' if prefs else ''}</b>")
                st.selectbox("목록에서 찾기", [f"{x['name']} · {'우선주 · ' if x.get('pref_of') else ''}{x['code']}" for x in companies], index=None,
                             placeholder="기업명이나 종목코드로 찾기", key="chk_list_pick", on_change=on_list_pick, label_visibility="collapsed")
                html('<p class="small" style="margin:0">이름을 누르면 입력창에 이어서 넣어 드려요. 회사마다 이름 뒤에 주식 수를 적어 주세요(예: 삼성전자 100주, 케이티앤지 30주).</p>')
        with st.container(key="chk_tools", horizontal=True, gap="small"):
            if step in (ENTRY, 0, 2):
                st.button(f"📋 {s['company_list_chip']} 보기", key="tool_list", type="tertiary", on_click=toggle, args=("listOpen",))
            st.button(f"📷 {s['image_chip']}", key="tool_photo_h", type="tertiary", on_click=set_photo, args=("holdings",))
            st.button(f"🧾 {s['base_image_chip']}", key="tool_photo_b", type="tertiary", on_click=set_photo, args=("base",))
        if c["photo"]:
            k = c["photo"]
            g = s["image_guide"][k]  # 웹의 사진 안내 창과 같은 글을 올리는 칸 위에 보인다
            html(f'<div class="photo-guide"><h4>{"🧾" if k == "base" else "📷"} {esc(g["title"])}</h4><ul>'
                 + "".join(f"<li>{esc(line)}</li>" for line in g["lines"]) + "</ul></div>")
            st.file_uploader("🧾 " + s["base_image_chip"] if k == "base" else "📷 " + s["image_chip"], type=["png", "jpg", "jpeg", "webp"],
                             key=f"chk_photo_{k}_{c.get('photo_n', 0)}", on_change=on_image, args=(k,))
        with st.form("chk_form", border=False):
            f1, f2 = st.columns([5, 1], vertical_alignment="bottom")
            with f1:
                st.text_input("답 입력", key="chk_text", max_chars=s["max_chars"] + 20, label_visibility="collapsed",
                              placeholder="예: 배당락이란? · 삼성전자 10주" if step == ENTRY else "예: 100주 · 500만 원 · 모름", autocomplete="off")
            with f2:
                st.form_submit_button("보내기", type="primary", on_click=on_form, use_container_width=True)

with right:
    with st.container(key="chk_mine"):
        html('<h4 style="margin:0 0 10px;font:400 20px \'Do Hyeon\'">내 답</h4>')
        for i, l in enumerate(s["step_labels"][:5]):
            v = answer_text(i, ans)
            st.button(f"{l}  \n**{v if v is not None else '–'}**", key=f"mine_{i}", disabled=v is None or step == RESULT,
                      on_click=edit, args=(i,), use_container_width=True)
        html('<p class="small" style="margin:10px 0 0">답한 칸을 누르면 그 항목만 다시 물어요. 입력은 저장하지 않아요.</p>')


# ── 결과 ────────────────────────────────────────────────────────────────
def stock_lines(x: dict, t: dict) -> list[str]:
    out = [t["shares"].replace("{shares}", fmt(x["shares"]))]
    if x["special"]:
        out.append(t["special"].replace("{amount}", won(x["special"])))
    if x["held"]:
        out.append(t["held"].replace("{amount}", won(x["held"])))
    if not x["special"] and not x["held"]:
        out.append(t["general"])
    r = x["ratio_to_2025_pct"]
    if x["need_2027"] is not None and x["d2025"] is not None and r is not None:
        out.append(t["next_up"].replace("{pct}", fmt(r - 100, 1)) if r > 100 else t["next_keep"].replace("{pct}", fmt(r, 1)))
    return out


IRP_DEMO = 9_000_000
BRACKETS = [("low", "총급여 5,000만 원 이하"), ("mid", "총급여 5,000만~5,500만 원"), ("high", "총급여 5,500만 원 초과"),
            ("biz_low", "종합소득 3,800만 원 이하"), ("biz_mid", "종합소득 3,800만~4,500만 원"), ("biz_high", "종합소득 4,500만 원 초과"),
            ("", "잘 모르겠어요")]


def choose_bracket(key: str, fin: int) -> None:
    c = S()
    c.update(pick=key, isa_err="", isa=None)
    try:
        c["isa"] = api.isaIrp(key or None, fin, IRP_DEMO, 0)
    except Exception as e:  # noqa: BLE001
        c["isa_err"] = str(e)


def isa_irp_pick(fin: int) -> None:
    """점검 결과(금융소득 2천만 원 이하)에 붙는 ISA·IRP 구간 버튼 (app/web/src/components/IsaIrpPick.tsx)"""
    c = S()
    p = lambda permil: f"{fmt(permil / 10, 1)}%"  # noqa: E731
    # 영수증 사진의 ㉑ 총급여로 고른 구간을 한 번 미리 고른다(④가 '있음'이면 종합소득 기준이라 고르지 않음)
    preset = None if c["ans"].get("otherIncome") else c["ans"].get("receiptBracket")
    if preset and c.get("preset_done") != preset:
        c["preset_done"] = preset
        choose_bracket(preset, fin)
    html('<p class="ii-pick-lead">💡 금융소득이 2천만 원 이하라 분리과세로는 세금이 달라지지 않아요. 대신 ISA·IRP로는 달라질 수 있어요. <b>소득이 어느 구간인가요?</b> 근로소득만 있으면 총급여, 사업소득 등이 있으면 종합소득금액으로 골라 주세요.</p>')
    with st.container(key="chk_brackets", horizontal=True, gap="small"):
        for key, label in BRACKETS:
            st.button(label, key=f"br_{key or 'unknown'}", type="primary" if c["pick"] == key else "secondary",
                      on_click=choose_bracket, args=(key, fin))
    if preset and c["pick"] == preset:
        html('<p class="small ii-preset">🧾 원천징수영수증 ㉑ 총급여 기준으로 골랐어요. 다르면 다른 구간을 눌러 주세요.</p>')
    if c["isa_err"]:
        html(f'<p class="small" style="color:var(--no)">{esc(c["isa_err"])}</p>')
    g = c["isa"]
    if g and c["pick"] is not None:
        ch = g["chosen"]
        isa_tax = g["isa"]["low_income"] if ch and ch["isa_type"] == "서민형" else g["isa"]["general"]
        head = f"{ch['isa_type']} · {fmt(ch['isa_free'] / 10_000)}만 원까지 비과세" if ch else "· 일반형 200만 원, 서민형 400만 원까지 비과세"
        isa_now = f"ISA {ch['isa_type']}은 {won(isa_tax)}" if ch else f"ISA 일반형 {won(g['isa']['general'])} · 서민형 {won(g['isa']['low_income'])}"
        html(f"""<div class="ii-pick-out">
  <div><b>ISA {esc(head)}</b><span>예를 들어 지금 1년 이자·배당 {won(fin)}만큼을 ISA 안에서 벌고 계좌를 닫으면, 보통 계좌는 세금 {won(g['isa']['normal'])}, {esc(isa_now)}이에요. 비과세 한도는 해마다가 아니라 계좌를 닫을 때 모든 순이익에 한 번 적용돼요.</span>
    <em>3년은 꼭 채워야 해요 · 1년 2,000만 원, 모두 1억 원까지 넣을 수 있어요 · 직전 3년 안에 금융소득종합과세 대상이었다면 가입할 수 없어요</em></div>
  <div><b>IRP · 넣은 돈의 {' 또는 '.join(p(r['rate_permil']) for r in g['irp'])} 세액공제</b>
    <span>1년에 900만 원을 넣으면 연말정산 때 세금에서 최대 {' 또는 '.join(won(r['credit']) for r in g['irp'])}까지 빼 줘요(참고 계산, 확정 환급액 아님). 낼 세금보다 많이 빼 주지는 않아요.</span>
    <em>55세 이후 연금으로 받아야 해요 · 중간에 깨면 16.5%를 내요</em></div>
  <p class="small">{esc(g['notice'])}</p>
</div>""")
        st.page_link(PAGES["isa-irp"], label="제도별 비교에서 금액을 바꿔 계산해 보기 →", query_params={"b": c["pick"]} if c["pick"] else None)


def law_find() -> None:
    q = st.session_state.get("chk_lawq", "").strip()
    if q:
        try:
            S()["hits"] = api.lawSearch(q)["hits"]
        except Exception:  # noqa: BLE001
            S()["hits"] = []


def evidence_drawer() -> None:
    with st.container(key="chk_drawer"):
        h1, h2 = st.columns([5, 1], vertical_alignment="center")
        with h1:
            html('<h4 style="margin:0;font:400 22px \'Do Hyeon\'">근거 보기</h4>')
        with h2:
            st.button("×", key="drawer_x", on_click=toggle, args=("drawer",), type="tertiary")
        try:
            data = api.evidence()
        except Exception:  # noqa: BLE001
            data = []
        html('<div class="drawer" style="box-shadow:none;border:0;padding:0;position:static;max-height:none">'
             '<div class="orig">원문 그대로예요. AI가 쓴 문장이 아니에요.</div>'
             + "".join(f'<article><b>{esc(p["label"])}</b><p>{esc(p["text"])}</p></article>' for p in data) + "</div>")
        with st.form("chk_law", border=False):
            q1, q2 = st.columns([4, 1], vertical_alignment="bottom")
            with q1:
                st.text_input("관련 조문 찾기", key="chk_lawq", max_chars=s["max_chars"], placeholder="관련 조문 찾기 (예: 고배당 분리과세 신청)", label_visibility="collapsed")
            with q2:
                st.form_submit_button("찾기", on_click=law_find)
        hits = c["hits"]
        if hits is not None:
            html('<div class="drawer" style="box-shadow:none;border:0;padding:0;position:static;max-height:none">'
                 + ("".join(f'<article><b>{esc(p["label"])}</b> <span class="small">{esc(p.get("by"))}</span><p>{esc(p["text"])}</p></article>' for p in hits)
                    if hits else '<p class="small">비슷한 조문을 찾지 못했어요.</p>') + "</div>")
        html(f'<p class="small" style="margin:10px 0 0">{esc(s["law_notice"])}</p>')


r = c["result"]
if r:
    a = c["ans"]
    other = a.get("other") or {}
    fin = (a.get("interest") or 0) + (other.get("domestic") or 0) + (other.get("foreign") or 0) + r["special_total"]
    cols = st.columns([1, 0.62], gap="medium") if c["drawer"] else [st.container()]
    with cols[0]:
        with st.container(key="chk_result"):
            tax = r["tax"]
            if r["no_target"]:
                big = (f'<div class="taxbig"><span class="small" style="font-weight:800">{esc(s["special_label"])}</span><br />'
                       f'<b class="num">{esc(s["no_target"])}</b><p class="small" style="margin:6px 0 0">{esc(r["no_target"])}</p></div>')
            elif tax["difference"] is not None:
                big = ('<div class="taxbig"><span class="small" style="font-weight:800">분리과세를 신청하면 계산상 세액 차이</span><br />'
                       f'<b class="num">{won(abs(tax["difference"]))} ({esc(tax["direction"])})</b>'
                       '<p class="small" style="margin:6px 0 0">참고용 모의 계산이에요. 확정 세액이나 돌려받는 돈(환급액)이 아니에요.</p></div>')
            else:
                big = (f'<div class="taxbig"><span class="small" style="font-weight:800">{esc(s["special_label"])}</span>'
                       f'<span class="small legal"> · {esc(s["special_legal"])}</span><br /><b class="num">{won(r["special_total"])}</b><br />'
                       f'<span class="small" style="font-weight:800;display:inline-block;margin-top:10px">{esc(s["special_tax_label"])}</span><br />'
                       f'<b class="num">{won(tax["separate_tax"])}</b> <span class="small">({esc(s["special_tax_tag"])})</span>'
                       f'<p class="small" style="margin:8px 0 0">{esc(s["special_tax_note"])}</p></div>')
            rows = ""
            if tax["difference"] is not None and not r["no_target"]:
                rows = '<div class="rows">' + "".join(f'<div><span>{esc(k)}</span><span class="num">{won(v)}</span></div>' for k, v in tax["rows"]) + "</div>"
            explain = (f'<details class="explain"><summary>{esc(s["special_explain_title"])}</summary>'
                       + "".join(f'<p class="small">{esc(p)}</p>' for p in s["special_explain"]) + "</details>")
            stocks = '<div class="stocks">' + "".join(
                f'<div><img src="{moa(mood_of(x["status"]))}" alt="" />{esc(x["name"])}'
                f'<span class="badge {badge_class(x["status"])}">{esc(x["status"])}{" · " + esc(x["route"]) if x["route"] else ""}</span>'
                f'<small class="stock-plain">{"".join(f"<span>{esc(l)}</span>" for l in stock_lines(x, s["stock_text"]))}</small></div>'
                for x in r["stocks"]) + "</div>"
            html(f'<section aria-label="점검 결과"><span class="tag">점검 결과 · 판정은 실제 공시, 세액은 참고 계산</span>'
                 f'<p class="big" style="font-size:26px">{esc(r["headline"])}</p>{big}{rows}{explain}{stocks}'
                 f'<p class="small" style="margin:12px 0 0">{esc(s["condition"])} {esc(s["next_check"])}</p></section>')
            c["send"] = st.checkbox(s["send_result"], value=c["send"], key="chk_send")
            html(f'<p class="small" style="margin:4px 0 0">{esc(s["send_result_note"])}</p>')
            if tax["status"] == "차이 없음":
                isa_irp_pick(fin)
            with st.container(key="chk_outlinks", horizontal=True, gap="small"):
                go = None
                if st.button(s["result_actions"][0], key="go_sep", type="primary"):
                    go = "separate"
                if st.button(s["result_actions"][1], key="go_fil"):
                    go = "filing"
                st.button("근거 보기", key="ev_open", type="tertiary", on_click=toggle, args=("drawer",))
                st.button("처음부터 다시 점검", key="restart", type="tertiary", on_click=start)
            if go:
                # 점검 결과는 주소에 싣지 않고 화면 사이에서만 넘긴다(웹은 router state, Streamlit은 세션). 저장하지 않는다
                st.session_state["consult_state"] = {"send": c["send"], "checkup": {
                    "headline": r["headline"],
                    "diff": f"{won(abs(tax['difference']))} ({tax['direction']})" if tax["difference"] is not None else None,
                    "stocks": [f"{x['name']} {x['status']}" for x in r["stocks"]],
                }}
                st.switch_page(PAGES["consult"], query_params={"type": go})
            html(f'<p class="small" style="margin:14px 0 0">{esc(" ".join(r["notes"]))} {esc(s["result_footnote"])}</p>')
    if c["drawer"]:
        with cols[1]:
            evidence_drawer()
