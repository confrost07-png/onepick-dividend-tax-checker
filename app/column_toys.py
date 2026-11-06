"""금융 상식 칼럼의 그림 도구 (웹 app/web/src/components/columnToys.tsx).

- API 값을 쓰는 세 도구(세율 계단 = api.separate, 달리기 시합 = api.race, 점 찍어 보기 = api.spread)는
  Streamlit 위젯으로 다시 그리고, 웹과 같은 API 함수·같은 화면 계산을 쓴다.
- 나머지 예시 숫자 도구는 웹 도구 코드를 묶은 web_column_toys.js(export_column_assets.mjs)를 그대로 붙인다.
  읽는 사람이 손으로 움직이는 예시라 서버 값이 없고, 웹과 모양·동작이 같다.
"""
from __future__ import annotations

import base64
import json
import math
import random
import time
from functools import lru_cache

import streamlit as st

from common import HERE, api, esc, fixed, html, js_round, run_js, won

# Column.tsx TOYS: 글의 toy 이름 → columnToys.tsx 함수 이름
TOYS = {
    "pizza": "Pizza", "stairs": "TaxStairs", "gates": "Gates", "balance": "Balance", "wallet": "Wallet", "race": "Race",
    "lineup": "Spread", "coins": "Coins", "stockbond": "StockBond", "votes": "Votes", "taxhelper": "TaxHelper",
    "wealth": "WealthMap", "fincome": "FinIncome", "withhold": "Withhold", "kinds": "IncomeSort", "grossup": "GrossUp",
    "savings": "Savings", "fx": "Fx", "account": "Account", "basket": "Basket", "yields": "Yields",
    "divcal": "DivCalendar", "recordday": "RecordDay", "payback": "Payback", "taxflow": "TaxFlow",
    "index": "IndexMaker", "knockin": "ElsPath", "eld": "EldInterest", "etn": "EtfEtn", "meeting": "Meeting",
    "splitter": "Splitter", "merger": "Merger", "ipo": "Ipo", "delistpath": "DelistPath", "waterfall": "Waterfall",
    "capital": "Capital", "ledger": "Ledger", "disclosure": "DisclosureSort", "ratemachine": "RateMachine",
    "brakes": "Brakes", "isabox": "IsaBox", "pension": "PensionCredit", "deposit": "Deposit", "shelf": "Shelf",
}


def toy(name: str, key: str) -> None:
    if name == "stairs":
        tax_stairs(key)
    elif name == "race":
        race(key)
    elif name == "lineup":
        spread(key)
    else:
        web_toy(TOYS[name], key)


def svg_img(svg: str, alt: str = "", cls: str = "toy-svg", style: str = "") -> str:
    """st.html 정화기(DOMPurify html 설정)는 <svg>를 지운다. 그래서 같은 SVG를 그림(img) 주소로 바꿔 넣는다."""
    if "xmlns=" not in svg[:200]:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" font-family="Gothic A1, sans-serif" ', 1)
    svg = svg.replace('class="toy-svg" ', "", 1)
    b64 = base64.b64encode(svg.encode("utf-8")).decode()
    return f'<img class="{cls}" style="{style}" alt="{esc(alt)}" src="data:image/svg+xml;base64,{b64}" />'


def jsnum(v) -> str:
    """JS가 숫자를 글자로 바꿀 때와 같게 (14.0 → '14')."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _card(title: str, inner: str) -> str:
    return f'<div class="card toy"><span class="col-no">직접 해 보기 · {title}</span>{inner}</div>'


# ── 웹 도구 그대로 ──────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _toys_js() -> str:
    return (HERE / "web_column_toys.js").read_text(encoding="utf-8")


def web_toy(component: str, key: str) -> None:
    hid = f"op-toy-{key}"
    run_js(
        f"if(!window.OnePickToys){{{_toys_js()}\nwindow.OnePickToys=OnePickToys}}\n"
        f"(function(){{var h=document.getElementById({json.dumps(hid)});if(!h||h.dataset.on)return;h.dataset.on='1';"
        f"window.OnePickToys.mount(h,{json.dumps(component)});}})();",
        body=f'<div id="{hid}"></div>',
    )


# ── 세율 계단 (/api/tax/separate) ─────────────────────────────────────────────
PRESETS = [5_000_000, 20_000_000, 50_000_000, 300_000_000, 1_000_000_000]


def tax_stairs(key: str) -> None:
    ak, sk = f"{key}_amount", f"{key}_slider"
    if ak not in st.session_state:
        st.session_state[ak] = 30_000_000

    def from_slider():  # 웹과 같은 로그 눈금: 100만~10억, 10만 원 단위로 반올림
        st.session_state[ak] = js_round(10 ** st.session_state[sk] * 1_000_000 / 100_000) * 100_000

    amount = st.session_state[ak]
    st.session_state[sk] = round(math.log10(max(amount, 1_000_000) / 1_000_000), 2)
    with st.container(key=f"toybox_{key}"):
        html(f'<div class="card toy" style="margin-bottom:0;border-bottom:0;border-radius:32px 32px 0 0;padding-bottom:4px">'
             f'<span class="col-no">직접 해 보기 · 세율 계단</span>'
             f'<label class="toy-big" style="display:block">고배당기업에서 받은 배당이 <b class="num">{won(amount)}</b>이면?</label></div>')
        st.slider("받은 배당", 0.0, 3.0, step=0.01, key=sk, on_change=from_slider, label_visibility="collapsed", format=" ")
        for col, p in zip(st.columns(len(PRESETS)), PRESETS):
            if col.button(won(p), key=f"{key}_p{p}", use_container_width=True):
                st.session_state[ak] = p
                st.rerun()
        r = api.separate(amount)
        max_tax = max([s["tax"] for s in r["steps"]] + [1])
        stairs = "".join(
            f'<div class="stair {"on" if s["part"] > 0 else ""}" style="min-height:{70 + s["rate_pct"] * 6}px">'
            f'<b>{jsnum(s["rate_pct"])}%</b>'
            f'<span>{won(s["from"]) + " 초과" + (" ~ " + won(s["to"]) if s["to"] else "")}</span>'
            + (f'<em class="num">{won(s["part"])} × {jsnum(s["rate_pct"])}%<br />= {won(s["tax"])}</em>' if s["part"] > 0 else "")
            + f'<i style="height:{s["tax"] / max_tax * 100}%"></i></div>'
            for s in r["steps"])
        html(f'<div class="card toy" style="margin-top:0;border-top:0;border-radius:0 0 32px 32px;padding-top:8px">'
             f'<div class="stair-row">{stairs}</div>'
             f'<div class="taxbig" style="margin-top:16px"><span class="small" style="font-weight:800">분리과세 세액 (참고용 계산)</span><br />'
             f'<b class="num">{won(r["tax"])}</b> <span class="small">· 받은 배당의 {jsnum(r["effective_pct"])}%</span></div>'
             f'<p class="small" style="margin:0">지방소득세는 넣지 않았어요. 세율 출처: {r["source"]}. {r["notice"]}</p></div>')


# ── 달리기 시합 (/api/column/race) ───────────────────────────────────────────
def _sign1(v: float) -> str:
    return f"{'+' if v > 0 else ''}{fixed(v, 1)}%"


def _race_svg(r: dict, day: int) -> str:
    W, H, L, R, T, B = 420, 220, 40, 70, 16, 190
    allv = [v for p in r["path"] for v in (p[1], p[2])]
    lo, hi = min(allv + [0]) - 2, max(allv + [0]) + 2
    X = lambda d: L + (W - L - R) * d / 60  # noqa: E731
    Y = lambda v: B - (B - T) * (v - lo) / (hi - lo)  # noqa: E731
    shown = r["path"][: day + 1]
    _, s, m = shown[-1]
    gap = js_round((s - m) * 100) / 100
    band = " ".join([f"{X(p[0])},{Y(p[1])}" for p in shown] + [f"{X(p[0])},{Y(p[2])}" for p in reversed(shown)])
    ticks = "".join(f'<text x="{X(d)}" y="{H + 6}" text-anchor="middle" font-size="11" fill="#6B7684">{d}일</text>' for d in (0, 20, 40, 60))
    svg = (f'<svg viewBox="0 0 {W} {H + 10}" class="toy-svg" role="img" aria-label="{day}거래일째 회사 {_sign1(s)}, 시장 {_sign1(m)}">'
           f'<line x1="{L}" x2="{W - R}" y1="{Y(0)}" y2="{Y(0)}" stroke="#191F28" stroke-dasharray="3 4" />'
           f'<text x="{L - 6}" y="{Y(0) + 4}" text-anchor="end" font-size="11" fill="#6B7684">0%</text>{ticks}'
           f'<polygon points="{band}" fill="{"rgba(61,107,255,.16)" if gap >= 0 else "rgba(242,85,90,.16)"}" />'
           f'<polyline points="{" ".join(f"{X(p[0])},{Y(p[2])}" for p in shown)}" fill="none" stroke="#8B95A5" stroke-width="3" />'
           f'<polyline points="{" ".join(f"{X(p[0])},{Y(p[1])}" for p in shown)}" fill="none" stroke="#3D6BFF" stroke-width="3" />'
           f'<circle cx="{X(day)}" cy="{Y(m)}" r="9" fill="#8B95A5" /><text x="{X(day) + 13}" y="{Y(m) + 4}" font-size="12" font-weight="800" fill="#6B7684">시장 {_sign1(m)}</text>'
           f'<circle cx="{X(day)}" cy="{Y(s)}" r="9" fill="#3D6BFF" /><text x="{X(day) + 13}" y="{Y(s) + 4}" font-size="12" font-weight="800" fill="#2547D9">회사 {_sign1(s)}</text></svg>')
    svg = svg_img(svg, f"{day}거래일째 회사 {_sign1(s)}, 시장 {_sign1(m)}")
    word = ("· 올랐지만 시장보다 뒤처졌어요" if s >= 0 and gap < 0 else "· 내렸지만 시장보다는 덜 내렸어요" if s < 0 and gap >= 0
            else "· 시장보다 잘 달렸어요" if gap >= 0 else "· 시장보다 뒤처졌어요")
    result = (f'<p class="toy-result" aria-live="polite">{day}거래일째 · 초과수익률 = 회사 {_sign1(s)} − 시장 {_sign1(m)} = '
              f'<b style="color:{"var(--sea)" if gap >= 0 else "var(--no)"}">{"+" if gap > 0 else ""}{fixed(gap, 1)}%p</b> {word}</p>')
    return svg + result


def race(key: str) -> None:
    pk = f"{key}_pick"
    if pk not in st.session_state:
        st.session_state[pk] = random.randrange(10000)
    r = api.race(st.session_state[pk])
    last = len(r["path"]) - 1
    with st.container(key=f"toybox_{key}"):
        html(f'<div class="card toy" style="margin-bottom:0;border-bottom:0;border-radius:32px 32px 0 0;padding-bottom:0">'
             f'<span class="col-no">직접 해 보기 · 진짜 달리기 시합 다시 보기</span>'
             f'<p class="small" style="margin-top:0">실제로 있었던 "배당을 늘린다는 공시" {r["n_events"]}건 중 하나예요({r["year"]}년, {r["market"]}). '
             f'공시한 날부터 60거래일 동안(공시 전날 값을 0%로), 이 회사 주가와 시장지수가 얼마나 올랐는지 같이 달려요. 회사 이름은 보여 주지 않아요.</p></div>')
        box = st.empty()
        c1, c2, _ = st.columns([1.3, 1.3, 3])
        replay = c1.button("▶ 처음부터 다시", key=f"{key}_replay", use_container_width=True)
        if c2.button("🎲 다른 공시 뽑기", key=f"{key}_next", type="primary", use_container_width=True):
            st.session_state[pk] += 1 + random.randrange(50)
            st.rerun()
        html(f'<div class="card toy" style="margin-top:0;border-top:0;border-radius:0 0 32px 32px;padding-top:0">'
             f'<p class="small" style="margin:0">몇 번 뽑아 보세요. 같은 "배당을 늘린다는 공시"인데도 결과가 제각각이에요. 그래서 데이터 이야기에서는 {r["n_events"]}건을 모아 가운데 값으로 봐요. '
             f'이 그림은 배당을 빼고 주가만 본 값이라, 데이터 이야기의 숫자(날마다 차이를 더하고 배당을 넣은 값)와 조금 달라요.</p></div>')
        # 웹처럼 새 공시를 뽑았을 때와 [처음부터 다시]를 눌렀을 때 하루씩 달린다
        if replay or st.session_state.get(f"{key}_played") != st.session_state[pk]:
            st.session_state[f"{key}_played"] = st.session_state[pk]
            for d in range(last + 1):
                box.html(_race_svg(r, d))
                time.sleep(0.07)
        else:
            box.html(_race_svg(r, last))


# ── 점 찍어 보기 (/api/column/spread) ────────────────────────────────────────
def _median(v: list[float]) -> float:
    s, n = sorted(v), len(v)
    return s[(n - 1) // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _quantile(s: list[float], p: float) -> float:
    i = (len(s) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def spread(key: str) -> None:
    data = api.spread()
    K = 20
    labels = {"none": "모두 보기", "top": f"가장 많이 오른 {K}건 빼 보기", "bottom": f"가장 많이 내린 {K}건 빼 보기"}
    ck = f"{key}_cut"
    cut = st.session_state.get(ck) or "none"
    values = data["values"]
    v = values[:-K] if cut == "top" else values[K:] if cut == "bottom" else values
    mean, mid, q1, q3 = sum(v) / len(v), _median(v), _quantile(v, .25), _quantile(v, .75)
    LO, HI, BIN, W, L, R, B, DOT = -40, 80, 2, 440, 22, 22, 200, 5.2
    X = lambda x: L + (W - L - R) * (max(LO, min(HI, x)) - LO) / (HI - LO)  # noqa: E731
    stacks: dict[int, int] = {}
    vs = set(v)
    dots = []
    for x in values:
        b = math.floor((max(LO, min(HI - .01, x)) - LO) / BIN)
        k = stacks.get(b, 0)
        stacks[b] = k + 1
        dots.append((x, L + (b + .5) * (W - L - R) / ((HI - LO) / BIN), B - 4 - k * DOT, x not in vs))
    top = min(d[2] for d in dots) - 10
    sign = lambda n: f"{'+' if n > 0 else ''}{fixed(n, 2)}%p"  # noqa: E731
    circles = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{DOT / 2 - .3}" fill="{"#E5E8EE" if out else "#3D6BFF" if x >= 0 else "#F2555A"}" opacity="{1 if out else .75}" />'
        for x, cx, cy, out in dots)
    ticks = "".join(f'<text x="{X(t)}" y="{B + 16}" text-anchor="middle" font-size="11" fill="#6B7684">{"+" if t > 0 else ""}{t}%p</text>'
                    for t in (-40, -20, 0, 20, 40, 60, 80))
    svg = (f'<svg viewBox="0 {top} {W} {B - top + 26}" class="toy-svg" role="img" aria-label="평균 {sign(mean)}, 가운데 값 {sign(mid)}">'
           f'<rect x="{X(q1)}" y="{top}" width="{X(q3) - X(q1)}" height="{B - top}" fill="rgba(61,107,255,.08)" />{circles}'
           f'<line x1="{X(0)}" x2="{X(0)}" y1="{top}" y2="{B}" stroke="#191F28" stroke-width="1" stroke-dasharray="2 3" />'
           f'<line x1="{X(mean)}" x2="{X(mean)}" y1="{top}" y2="{B}" stroke="#F2555A" stroke-width="3" stroke-dasharray="6 4" />'
           f'<line x1="{X(mid)}" x2="{X(mid)}" y1="{top}" y2="{B}" stroke="#2547D9" stroke-width="3" />'
           f'<line x1="{L}" x2="{W - R}" y1="{B}" y2="{B}" stroke="#191F28" />{ticks}</svg>')
    with st.container(key=f"toybox_{key}"):
        html(_card("점 찍어 보기",
                   f'<p class="small" style="margin-top:0">점 하나가 실제 "배당을 늘린다는 공시" 한 건이에요. 공시 뒤 60거래일 동안 시장보다 얼마나 더 올랐는지(초과수익률)에 따라 줄을 세웠어요. 모두 {len(values)}건이에요.</p>'
                   f'<div class="spread-legend"><span><i class="lg-mean"></i>평균 <b>{sign(mean)}</b></span>'
                   f'<span><i class="lg-mid"></i>가운데 값 <b>{sign(mid)}</b></span>'
                   f'<span><i class="lg-iqr"></i>가운데 절반 {fixed(q1, 1)}~{fixed(q3, 1)}%p</span></div>'
                   + svg_img(svg, f"평균 {sign(mean)}, 가운데 값 {sign(mid)}")))
        st.segmented_control("빼 볼 사례", list(labels), format_func=labels.get, key=ck, default="none", label_visibility="collapsed")
        result = ("몇 건만 아주 크게 올라서, 평균이 가운데 값보다 오른쪽으로 끌려가 있어요." if cut == "none"
                  else f"{K}건만 뺐는데 평균은 {sign(mean)}로 크게 움직이고, 가운데 값은 {sign(mid)}로 조금만 움직여요.")
        html(f'<p class="toy-result" aria-live="polite">{result}</p>'
             f'<p class="small" style="margin:0 0 24px">{data["basis"]}. −40%p보다 낮거나 +80%p보다 높은 점은 양 끝에 모았어요. 데이터 이야기 6장의 가운데 값과 같은 사례예요.</p>')
