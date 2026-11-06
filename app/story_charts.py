"""데이터 이야기 그림: 웹 app/web/src/components/charts.tsx·charts2.tsx·control.tsx·macro.tsx를 Python으로 옮긴 것.

웹과 같은 SVG(같은 viewBox·좌표 계산·class 이름)를 문자열로 만든다. 색은 app/web/src/index.css가 class로 입힌다.
웹에서 마우스를 올리면 아래에 뜨던 설명은 SVG <title>(브라우저 말풍선)로 보여 준다.
st.html은 SVG를 지우므로 그림은 md()(st.markdown, HTML 허용)로 그린다.
"""
from __future__ import annotations

import math
import time
from decimal import Decimal

import streamlit as st

from common import esc, fixed, fmt, js_round


# ── 공용 ──────────────────────────────────────────────────────────────────
def md(body: str) -> None:
    """HTML(SVG 포함)을 그린다. 줄바꿈을 없애 마크다운 문법(들여쓰기·빈 줄)이 끼어들지 않게 한다."""
    st.markdown(" ".join(body.split("\n")), unsafe_allow_html=True)


def jsn(v) -> str:
    """JS String(number)와 같은 글자 (12.0 → '12', 1e-05 → '0.00001')."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if float(v).is_integer():
        return str(int(v))
    r = repr(float(v))
    if "e" in r and 1e-7 <= abs(v) < 1e21:
        r = format(Decimal(r), "f")
    return r


def n(v: float) -> str:
    """SVG 좌표 숫자"""
    return jsn(round(v, 3))


def tip_box(text: str) -> str:
    return f'<p class="chart-tip" aria-live="polite">{esc(text)}</p>'


def title(text: str) -> str:
    return f"<title>{esc(text)}</title>"


# ── charts.tsx ────────────────────────────────────────────────────────────
def retro_chart(rows) -> str:
    W, B, top, L = 640, 250, 40, 30
    bw = (W - L - 20) / len(rows)
    y50 = B - (B - top) * .5
    out = [f'<svg class="chart" viewBox="0 0 {W} 300" role="img" aria-label="다음 해 탈락률 막대 그래프">',
           f'<line x1="{L}" x2="{W - 10}" y1="{B}" y2="{B}" class="axis" />',
           f'<line x1="{L}" x2="{W - 10}" y1="{n(y50)}" y2="{n(y50)}" class="guide" />',
           f'<text x="{W - 10}" y="{n(y50 - 6)}" class="tick" text-anchor="end">50%</text>']
    for i, (year, met, _, fail, rate) in enumerate(rows):
        h, x, w = (B - top) * rate / 100, L + i * bw + bw * .18, bw * .64
        t = f"{year}년 요건을 넘은 {met}곳 중 {fail}곳이 다음 해에 떨어졌어요 ({jsn(rate)}%)"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}'
                   f'<rect class="hit" x="{n(x - 6)}" y="{top}" width="{n(w + 12)}" height="{B - top}" />'
                   f'<rect x="{n(x)}" y="{n(B - h)}" width="{n(w)}" height="{n(h)}" rx="10" class="{"bar-coin" if year == 2024 else "bar-sea"}" />'
                   f'<text x="{n(x + w / 2)}" y="{n(B - h - 10)}" class="val" text-anchor="middle">{fixed(rate, 1)}%</text>'
                   f'<text x="{n(x + w / 2)}" y="{B + 22}" class="tick" text-anchor="middle">{year}→{year + 1}</text>'
                   f'<text x="{n(x + w / 2)}" y="{B + 40}" class="tick soft" text-anchor="middle">{fail}/{met}곳</text></g>')
    out.append("</svg>")
    return "".join(out) + tip_box("막대에 마우스를 올리면 자세한 숫자가 나와요")


EASY = {
    '제2호 미충족': '배당이 전년보다 줄었어요 (제2호)',
    '배당성향 25% 미만': '번 돈의 25%도 배당하지 않았어요',
    '배당성향 25~40%이지만 이익배당금액 10% 증가 미달': '25~40%인데 배당을 10% 이상 늘리지 않았어요',
    '적자로 배당성향 25% 간주, 이익배당금액 10% 증가 미달': '적자라 25%로 보는데, 배당을 10% 이상 늘리지 않았어요',
    '적자이고 부채가 자본총액의 2배 초과': '적자이고 빚이 자본의 2배를 넘었어요',
}


def reasons_chart(rows) -> str:
    W, rowh = 1000, 46
    total = sum(r[1] for r in rows)
    mx = max(r[1] for r in rows)
    out = [f'<svg class="chart" viewBox="0 0 {W} {rowh * len(rows) + 10}" role="img" aria-label="다음 해 탈락 이유">']
    for i, (label, k) in enumerate(rows):
        y, w = i * rowh + 6, max((W - 140) * k / mx, 6)
        out.append(f'<g><text x="0" y="{y + 12}" class="lab">{esc(EASY.get(label, label))}</text>'
                   f'<rect x="0" y="{y + 18}" width="{n(w)}" height="16" rx="8" class="{"bar-no" if i == 0 else "bar-gray"}" />'
                   f'<text x="{n(w + 10)}" y="{y + 31}" class="val">{k}건 · {js_round(k / total * 100)}%</text></g>')
    out.append("</svg>")
    return "".join(out)


def payout_chart(rows) -> str:
    W, B, top, L = 900, 270, 50, 10
    mx = max(r[1] for r in rows)
    bw = (W - L - 10) / len(rows)
    out = [f'<svg class="chart" viewBox="0 0 {W} 320" role="img" aria-label="2025 배당성향 분포">']
    for v, k in rows:
        x, h = L + (v - 10) * bw + 1.5, (B - top) * k / mx
        t = f"배당성향 {v}%대: {k}곳"
        cls = "bar-coin" if v == 25 else "bar-sea" if v >= 25 else "bar-gray"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect class="hit" x="{n(x)}" y="{top}" width="{n(bw - 3)}" height="{B - top}" />'
                   + (f'<rect x="{n(x)}" y="{n(B - h)}" width="{n(bw - 3)}" height="{n(h)}" rx="4" class="{cls}" />' if k > 0 else "")
                   + (f'<text x="{n(x + bw / 2)}" y="{B + 20}" class="tick" text-anchor="middle">{v}%</text>' if v % 5 == 0 else "")
                   + "</g>")
    for v in (25, 40):
        x = L + (v - 10) * bw
        out.append(f'<g pointer-events="none"><line x1="{n(x)}" x2="{n(x)}" y1="{top - 20}" y2="{B}" class="thr" />'
                   f'<rect x="{n(x - 38)}" y="{top - 42}" width="76" height="24" rx="12" class="pill" />'
                   f'<text x="{n(x)}" y="{top - 25}" class="pill-t" text-anchor="middle">{v}% 기준선</text></g>')
    out.append(f'<line x1="{L}" x2="{W - 10}" y1="{B}" y2="{B}" class="axis" /></svg>')
    return "".join(out) + tip_box("막대에 마우스를 올리면 그 구간의 회사 수가 나와요")


RUNWAY = [("seg-ok", "올해만큼이면 충분"), ("seg-coin", "10% 안쪽 더"), ("seg-warn", "10~25% 더"),
          ("seg-warn2", "25~50% 더"), ("seg-no", "1.5배 넘게")]


def runway_chart(rows) -> str:
    W = 900
    total = sum(r[1] for r in rows)
    rest = sum(r[1] for r in rows[2:])
    x = 0.0
    out = [f'<svg class="chart" viewBox="0 0 {W} 150" role="img" aria-label="2027년 최소 필요 배당 ÷ 2025년 배당">']
    for i, (label, k) in enumerate(rows):
        w, x0 = W * k / total, x
        x += w
        lx = x0 + (16 if w > 60 else w / 2)
        t = f"{label}: {k}곳 ({js_round(k / total * 100)}%)"
        cls = RUNWAY[i][0] if i < len(RUNWAY) else ""
        g = f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect x="{n(x0)}" y="20" width="{n(max(w - 3, 2))}" height="56" rx="14" class="{cls}" />'
        if w > 60:
            g += f'<text x="{n(x0 + 16)}" y="56" class="seg-n">{k}곳</text>'
        if i < 2:
            g += (f'<text x="{n(lx)}" y="104" class="lab">{RUNWAY[i][1]}</text>'
                  f'<text x="{n(lx)}" y="124" class="tick">{js_round(k / total * 100)}%</text>')
        out.append(g + "</g>")
    detail = " · ".join(f"{RUNWAY[i + 2][1]} {k}" for i, (_, k) in enumerate(rows[2:]))
    out.append(f'<text x="{W}" y="104" class="lab" text-anchor="end">25% 넘게 더 줘야 하는 회사 {rest}곳</text>'
               f'<text x="{W}" y="124" class="tick" text-anchor="end">{detail}</text></svg>')
    return "".join(out) + tip_box("칸에 마우스를 올리면 구간 이름과 회사 수가 나와요")


# ── charts2.tsx ───────────────────────────────────────────────────────────
def growth_chart(rows) -> str:
    W, B, top, L = 900, 270, 50, 10
    mx = max(r[1] for r in rows)
    lo = rows[0][0]
    bw = (W - L - 10) / len(rows)
    capped = min(mx, 40)
    out = [f'<svg class="chart" viewBox="0 0 {W} 320" role="img" aria-label="2025 이익배당금액 증가율 분포">']
    for v, k in rows:
        x, h = L + (v - lo) * bw + 1.5, (B - top) * min(k, capped) / capped
        t = f"증가율 {v}%대: {k}곳{' (막대 위를 잘랐어요)' if k > capped else ''}"
        cls = "bar-coin" if v == 10 else "bar-sea" if v >= 10 else "bar-gray"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect class="hit" x="{n(x)}" y="{top}" width="{n(bw - 3)}" height="{B - top}" />'
                   + (f'<rect x="{n(x)}" y="{n(B - h)}" width="{n(bw - 3)}" height="{n(h)}" rx="4" class="{cls}" />' if k > 0 else "")
                   + (f'<text x="{n(x + bw / 2)}" y="{top - 6}" class="val" text-anchor="middle">{k}↑</text>' if k > capped else "")
                   + (f'<text x="{n(x + bw / 2)}" y="{B + 20}" class="tick" text-anchor="middle">{v}%</text>' if v % 5 == 0 else "")
                   + "</g>")
    tx = L + (10 - lo) * bw
    out.append(f'<g pointer-events="none"><line x1="{n(tx)}" x2="{n(tx)}" y1="{top - 20}" y2="{B}" class="thr" />'
               f'<rect x="{n(tx - 38)}" y="{top - 42}" width="76" height="24" rx="12" class="pill" />'
               f'<text x="{n(tx)}" y="{top - 25}" class="pill-t" text-anchor="middle">10% 기준선</text></g>'
               f'<line x1="{L}" x2="{W - 10}" y1="{B}" y2="{B}" class="axis" /></svg>')
    return "".join(out) + tip_box("막대에 마우스를 올리면 그 구간의 회사 수가 나와요")


GRID_ROWS = ['배당 10% 이상 증가', '0~10% 증가', '배당 감소']
GRID_COLS = [('배당성향', '25% 미만'), ('25~40%', '(나목 땅)'), ('40% 이상', '(가목 땅)')]
GRID_OK = [(0, 1), (0, 2), (1, 2)]


def _grid_total(g) -> int:
    return sum(sum(r) for r in g)


def _grid_ok_pct(g) -> float:
    return sum(g[r][c] for r, c in GRID_OK) / max(1, _grid_total(g)) * 100


def _grid_html(grid: dict, y: int) -> str:
    years = sorted(int(k) for k in grid)
    last = years[-1]
    g = grid[str(y)]
    tot, mx = _grid_total(g), max(1, *[v for r in g for v in r])
    parts = [f'<div class="g3"><div class="g3-top"><b class="g3-year">{y}</b>'
             f'<span class="small">사업연도 · {fmt(tot)}곳 · 요건 칸 {fixed(_grid_ok_pct(g), 1)}%</span></div>']
    if y == last:
        parts.append(f'<p class="g3-warn">{y}년은 이 해 숫자로 고배당기업을 골랐기 때문에, 다른 해와 바로 비교하면 안 돼요.</p>')
    parts.append(f'<div class="g3-grid" role="table" aria-label="{y}년 배당성향과 배당 증가율로 나눈 회사 수"><div></div>')
    parts += [f'<div class="g3-h" role="columnheader">{a}<br />{b}</div>' for a, b in GRID_COLS]
    for i, row in enumerate(g):
        parts.append(f'<div class="g3-r" role="rowheader">{GRID_ROWS[i]}</div>')
        for j, v in enumerate(row):
            p, ok = v / max(1, tot) * 100, (i, j) in GRID_OK
            parts.append(f'<div role="cell" class="g3-c{" ok" if ok else ""}" style="background: rgba(61,107,255,{fixed(0.05 + 0.45 * v / mx, 2)})">'
                         + ('<span class="g3-tag">충족</span>' if ok else "")
                         + f'<div class="g3-n">{fmt(v)}곳</div><div class="g3-p">{fixed(p, 1)}%</div>'
                         f'<div class="g3-bt"><div style="width: {fixed(p, 1)}%"></div></div></div>')
    parts.append('</div><div class="g3-legend"><span><i class="g3-sw ok"></i>요건을 채우는 칸</span>'
                 '<span><i class="g3-sw"></i>색이 진할수록 회사가 많음</span><span>연도 아래 %는 요건 칸 비율</span></div></div>')
    return "".join(parts)


@st.fragment
def grid_chart(grid: dict) -> None:
    """3장 칸 그림. 웹의 연도 단추는 선택 단추로, ▶ 재생은 해마다 1.2초씩 넘기는 단추로."""
    years = sorted(int(k) for k in grid)
    key = "g3_year"
    if key not in st.session_state:
        st.session_state[key] = years[-1]
    c1, c2 = st.columns([6, 1], vertical_alignment="center")
    with c1:
        st.segmented_control("연도 고르기", years, key=key, label_visibility="collapsed",
                             format_func=lambda v: f"{v} · {fixed(_grid_ok_pct(grid[str(v)]), 0)}%")
    with c2:
        play = st.button("▶ 재생", key="g3_play", use_container_width=True)
    box = st.empty()
    if play:
        for y in years:
            with box.container():
                md(_grid_html(grid, y))
            time.sleep(1.2)
        st.session_state[key] = years[-1]
        return
    y = st.session_state.get(key) or years[-1]
    with box.container():
        md(_grid_html(grid, y))


def holder_chart(h) -> str:
    rows = [r for r in h["table"] if r["표시"]]
    W, rowh, L, R, lo, hi = 900, 58, 230, 170, 20, 70
    X = lambda v: L + (W - L - R) * (v - lo) / (hi - lo)  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {W} {rowh * len(rows) + 40}" role="img" aria-label="최대주주 지분율 비교">']
    for v in (20, 30, 40, 50, 60, 70):
        out.append(f'<g><line x1="{n(X(v))}" x2="{n(X(v))}" y1="10" y2="{rowh * len(rows)}" class="guide" />'
                   f'<text x="{n(X(v))}" y="{rowh * len(rows) + 22}" class="tick" text-anchor="middle">{v}%</text></g>')
    out.append(f'<text x="{W - R + 20}" y="18" class="tick">개인 최대주주</text>')
    for i, r in enumerate(rows):
        y, far = i * rowh + 34, r["묶음"].startswith("나머지")
        out.append(f'<g><text x="0" y="{y + 5}" class="lab">{esc(r["묶음"])}</text>'
                   f'<text x="0" y="{y + 23}" class="tick">{jsn(r["회사 수"])}곳</text>'
                   f'<rect x="{n(X(r["1사분위"]))}" y="{y - 7}" width="{n(X(r["3사분위"]) - X(r["1사분위"]))}" height="14" rx="7" class="{"bar-gray" if far else "bar-coin"}" opacity="0.7" />'
                   f'<circle cx="{n(X(r["중앙값"]))}" cy="{y}" r="8" class="{"dot-gray" if far else "dot-sea"}" />'
                   f'<text x="{n(X(r["중앙값"]))}" y="{y - 14}" class="val" text-anchor="middle">{jsn(r["중앙값"])}%</text>'
                   f'<text x="{W - R + 20}" y="{y + 6}" class="{"end-gray" if far else "end-sea"}">{jsn(r["개인 최대주주(%)"])}%</text></g>')
    out.append("</svg>")
    return "".join(out)


def capacity_chart(c) -> str:
    W = 900
    total = sum(b[1] for b in c["bins"])
    cls = ["seg-no", "seg-warn", "seg-coin", "seg-ok"]
    x = 0.0
    out = [f'<svg class="chart" viewBox="0 0 {W} 200" role="img" aria-label="재무 여력 분포">']
    for i, (name, k) in enumerate(c["bins"]):
        w, x0 = W * k / total, x
        x += w
        out.append(f'<g><rect x="{n(x0)}" y="10" width="{n(max(w - 3, 2))}" height="56" rx="14" class="{cls[i]}" />'
                   + (f'<text x="{n(x0 + 16)}" y="46" class="seg-n">{k}곳</text>' if w > 70 else "")
                   + f'<text x="{n(x0 + 4)}" y="92" class="lab">{esc(name)}</text>'
                   f'<text x="{n(x0 + 4)}" y="112" class="tick">{js_round(k / total * 100)}%</text></g>')
    short = c["bins"][0][1]
    w_short = W * short / total
    for name, x0, x1, k, color in (("배당하기 어려워요", 0, w_short - 3, short, "var(--no)"),
                                   ("배당하기 충분해요", w_short, W - 3, total - short, "var(--sea)")):
        out.append(f'<g><path d="M{n(x0 + 1)},150 V136 H{n(x1 - 1)} V150" fill="none" stroke="{color}" stroke-width="2.5" />'
                   f'<text x="{n((x0 + x1) / 2)}" y="162" class="lab" text-anchor="middle" style="fill: {color}">{name}</text>'
                   f'<text x="{n((x0 + x1) / 2)}" y="184" class="tick" text-anchor="middle">{k}곳 · {js_round(k / total * 100)}%</text></g>')
    out.append("</svg>")
    return "".join(out)


KIND_ORDER = ['주당배당금 증가', '주당배당금 유지·감소', '무상증자', '유상증자(제3자배정)', '유상증자(주주배정)', '감자(자기주식 소각)', '주식분할']


def one_curve(curve, days: int) -> str:
    W, L, R, top, B = 720, 50, 20, 20, 300
    vals = [v for d in curve for v in d[2:]]
    lo, hi = min(*vals, -1) - 1, max(*vals, 1) + 1
    X = lambda d: L + (W - L - R) * d / days  # noqa: E731
    Y = lambda v: B - (B - top) * (v - lo) / (hi - lo)  # noqa: E731
    step = 10 if hi - lo > 40 else 5
    ticks, v = [], math.ceil(lo / step) * step
    while v <= hi:
        ticks.append(v)
        v += step
    last = curve[-1]
    out = [f'<svg class="chart" viewBox="0 0 {W} 340" role="img" aria-label="공시 뒤 {days}거래일 초과수익률 곡선">']
    for v in ticks:
        lab = f"{'+' if v > 0 else ''}{v}%p" if v else "0"
        out.append(f'<g><line x1="{L}" x2="{W - R}" y1="{n(Y(v))}" y2="{n(Y(v))}" class="{"axis" if v == 0 else "guide"}" />'
                   f'<text x="{L - 8}" y="{n(Y(v) + 4)}" class="tick" text-anchor="end">{lab}</text></g>')
    for d in (0, days / 2, days):
        out.append(f'<text x="{n(X(d))}" y="{B + 24}" class="tick" text-anchor="middle">{jsn(d)}일</text>')
    band = " ".join(f"{n(X(p[0]))},{n(Y(p[3]))}" for p in curve) + " " + " ".join(f"{n(X(p[0]))},{n(Y(p[4]))}" for p in reversed(curve))
    out.append(f'<polygon class="band-sea" points="{band}" />'
               f'<polyline class="line-sea" points="{" ".join(f"{n(X(p[0]))},{n(Y(p[2]))}" for p in curve)}" />'
               f'<circle cx="{n(X(last[0]))}" cy="{n(Y(last[2]))}" r="6" class="dot-sea" /></svg>')
    return "".join(out)


def event_explorer(ev) -> None:
    """6장 공시 뒤 주가 탐색. 웹의 칩 단추를 Streamlit 선택 단추로 바꿨다(고를 수 없는 값은 빼고 보여 준다)."""
    summary = ev["summary"]
    kinds = [k for k in KIND_ORDER if any(s["kind"] == k for s in summary)]
    ss = st.session_state
    ss.setdefault("ev_kind", kinds[0])
    ss.setdefault("ev_win", 60)
    ss.setdefault("ev_basis", "공시일")
    ss.setdefault("ev_ret", "배당 포함")
    ss.setdefault("ev_sample", "자본 변동 겹침 제외")

    def pick_of():
        kind, win, basis, ret, sample = ss.ev_kind, ss.ev_win, ss.ev_basis, ss.ev_ret, ss.ev_sample
        score = lambda x: (8 if x["window"] == win else 0) + (4 if x["sample"] == sample else 0) + (2 if x["basis"] == basis else 0) + (1 if x["ret"] == ret else 0)  # noqa: E731
        c = [x for x in summary if x["kind"] == kind]
        return sorted(c, key=score, reverse=True)[0] if c else None  # 파이썬 정렬은 JS처럼 안정 정렬

    def has(k, w, b, r, s):
        return any(x["kind"] == k and x["window"] == w and x["basis"] == b and x["ret"] == r and x["sample"] == s for x in summary)

    with st.container(border=True):
        pick = pick_of()
        rows = [
            ("① 어떤 공시", "어떤 소식이 나온 뒤를 볼까요", "ev_kind", kinds, lambda v: True, str),
            ("② 얼마 동안", "기준일부터 며칠 뒤까지", "ev_win", [20, 60], lambda w: any(x["kind"] == ss.ev_kind and x["window"] == w for x in summary), lambda w: f"{w}거래일"),
            ("③ 언제부터", "0일로 잡는 날", "ev_basis", ["공시일", "주주총회 결의일", "배당락일"], lambda b: any(x["kind"] == ss.ev_kind and x["basis"] == b for x in summary), str),
            ("④ 무엇을 셀지", "배당금도 수익에 넣을까요", "ev_ret", ["배당 포함", "주가만"], lambda r: any(x["kind"] == ss.ev_kind and x["ret"] == r for x in summary), str),
            ("⑤ 어떤 사례", "증자·감자가 같은 기간에 겹친 회사", "ev_sample", ["자본 변동 겹침 제외", "전체"], lambda s: bool(pick) and has(ss.ev_kind, pick["window"], pick["basis"], pick["ret"], s), str),
        ]
        for title_, sub, key, opts, ok, ff in rows:
            c1, c2 = st.columns([1, 4], vertical_alignment="center")
            with c1:
                md(f'<div class="ev-q"><b>{title_}</b><span>{sub}</span></div>')
            with c2:
                avail = [o for o in opts if ok(o)]
                # 웹은 실제로 보이는 조건(pick)을 켜진 칩으로 보여 준다
                shown = pick and {"ev_kind": pick["kind"], "ev_win": pick["window"], "ev_basis": pick["basis"],
                                  "ev_ret": pick["ret"], "ev_sample": pick["sample"]}[key]
                val = st.segmented_control(title_, avail, default=shown if shown in avail else None, format_func=ff,
                                           key=f"{key}_w", label_visibility="collapsed")
                if val is not None and val != ss[key]:
                    ss[key] = val
                    st.rerun()
        pick = pick_of()
        if pick:
            samp = "증자·감자가 <b>겹친 사례도 모두 넣고</b>" if pick["sample"] == "전체" else "증자·감자가 <b>겹친 사례는 빼고</b>"
            md(f'<p class="ev-now">지금 보는 것: <b>{esc(pick["kind"])}</b> 공시 뒤 · <b>{esc(pick["basis"])}</b>부터 <b>{pick["window"]}거래일</b> · '
               f'<b>{"배당 포함" if pick["ret"] == "배당 포함" else "주가만"}</b> 수익률 · {samp}</p>')

    key = "|".join([pick["kind"], pick["basis"], pick["ret"], pick["sample"], str(pick["window"])]) if pick else ""
    curve = ev["curves"].get(key)
    test = None
    if pick and pick["sample"] == "자본 변동 겹침 제외" and ev.get("methods"):
        test = next((t for t in ev["methods"]["tests"] if t.get("공시 종류") == pick["kind"] and t.get("기준일") == pick["basis"]
                     and t.get("창") == pick["window"] and t.get("모형") == "시장조정" and t.get("수익률") == pick["ret"]), None)
    q = test.get("KP p BH 보정 q") if test else None
    body = f'<div class="card">{one_curve(curve, pick["window"]) if curve else "<p class=small>사례가 10건 미만이라 곡선을 표시하지 않아요.</p>"}</div>'
    side = ""
    if pick:
        med = pick["median"]
        mean = f" · 평균 {'+' if test['평균(%p)'] > 0 else ''}{jsn(test['평균(%p)'])}%p, {jsn(test['사례'])}건" if test else ""
        if q is None:
            q1 = "검정 안 함"
            q2 = "검정은 '자본 변동 겹침 제외' 표본으로만 했어요" if pick["sample"] == "전체" else "사례가 적어 검정하지 않았어요"
        else:
            q1 = "우연이라 보기 어려워요" if q < 0.05 else "우연일 수도 있어요"
            q2 = f"q {'< 0.0001' if q < 0.0001 else '= ' + fixed(q, 4)} (0.05보다 {'작음' if q < 0.05 else '큼'})"
        side = (f'<div class="ch-side"><div class="stat"><b class="num" style="color: {"var(--sea)" if med >= 0 else "var(--no)"}">{"+" if med > 0 else ""}{fixed(med, 2)}%p</b>'
                f'<span>{pick["window"]}거래일 가운데 값 · {pick["n"]}건<br />가운데 절반: {jsn(pick["p25"])}~{jsn(pick["p75"])}%p</span></div>'
                f'<div class="stat"><span>평균이 0과 다른 게 우연일 가능성{esc(mean)}</span>'
                f'<b style="font-size: 28px; margin-top: 4px">{q1}</b><span>{esc(q2)}</span></div></div>')
    md(f'<div class="ch-body">{body}{side}</div>')


# ── control.tsx ───────────────────────────────────────────────────────────
def two_lines(rows, unit: str, label: str, x_label=None) -> str:
    W, H, top, bottom, L, R = 640, 280, 30, 40, 34, 90
    vals = [v for r in rows for v in (r[1], r[2]) if v is not None]
    hi, lo = max(100, *vals), 0
    x = lambda i: L + i * (W - L - R) / max(len(rows) - 1, 1)  # noqa: E731
    y = lambda v: top + (hi - v) / (hi - lo) * (H - top - bottom)  # noqa: E731

    def path(k):
        return " ".join("" if r[k] is None else f"{'L' if i and rows[i - 1][k] is not None else 'M'}{n(x(i))},{n(y(r[k]))}" for i, r in enumerate(rows))

    show = lambda v: "–" if v is None else f"{fixed(v, 1)}{unit}"  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">']
    for g in (0, 50, 100):
        out.append(f'<g><line x1="{L}" x2="{W - R}" y1="{n(y(g))}" y2="{n(y(g))}" class="guide" /><text x="{L - 6}" y="{n(y(g) + 4)}" class="tick" text-anchor="end">{g}</text></g>')
    out.append(f'<path d="{path(2)}" class="line-gray" /><path d="{path(1)}" class="line-sea" />')
    for i, r in enumerate(rows):
        xl = x_label(r[0]) if x_label else str(r[0])
        t = f"{xl}: 고배당기업(같은 4개 업종) {show(r[1])} · 대조군 {show(r[2])}"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect class="hit" x="{n(x(i) - 18)}" y="{top}" width="36" height="{H - top - bottom}" />'
                   + (f'<circle cx="{n(x(i))}" cy="{n(y(r[2]))}" r="6" class="dot-gray" />' if r[2] is not None else "")
                   + (f'<circle cx="{n(x(i))}" cy="{n(y(r[1]))}" r="6" class="dot-sea" />' if r[1] is not None else "")
                   + f'<text x="{n(x(i))}" y="{H - 14}" class="tick" text-anchor="middle">{x_label(r[0]) if x_label else str(r[0])[2:]}</text></g>')
    last = rows[-1]
    if last[1] is not None:
        out.append(f'<text x="{W - R + 12}" y="{n(y(last[1]) + 8)}" class="end-sea">{fixed(last[1], 0)}{unit}</text>')
    if last[2] is not None:
        out.append(f'<text x="{W - R + 12}" y="{n(y(last[2]) + 8)}" class="end-gray">{fixed(last[2], 0)}{unit}</text>')
    out.append("</svg>")
    return "".join(out) + tip_box("점에 마우스를 올리면 두 집단 값이 나와요 · 파랑 = 고배당기업(같은 4개 업종), 회색 = 대조군")


def pair_bars(rows, label: str) -> str:
    W, H, top, bottom, L = 640, 260, 28, 40, 10
    hi = max(10, *[v for r in rows for v in (r[1], r[2])])
    y = lambda v: top + (hi - v) / hi * (H - top - bottom)  # noqa: E731
    gw = (W - L * 2) / len(rows)
    bw = min(46, gw / 2 - 10)
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">']
    for i, (name, a, b) in enumerate(rows):
        cx = L + gw * i + gw / 2
        t = f"{name}: 고배당기업(같은 4개 업종) {fixed(a, 1)}% · 대조군 {fixed(b, 1)}%"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect class="hit" x="{n(cx - gw / 2)}" y="{top}" width="{n(gw)}" height="{H - top - bottom}" />'
                   f'<rect x="{n(cx - bw - 3)}" y="{n(y(a))}" width="{n(bw)}" height="{n(y(0) - y(a))}" rx="4" class="bar-sea" />'
                   f'<rect x="{n(cx + 3)}" y="{n(y(b))}" width="{n(bw)}" height="{n(y(0) - y(b))}" rx="4" class="bar-gray" />'
                   f'<text x="{n(cx - bw / 2 - 3)}" y="{n(y(a) - 6)}" class="soft" text-anchor="middle">{fixed(a, 0)}</text>'
                   f'<text x="{n(cx + bw / 2 + 3)}" y="{n(y(b) - 6)}" class="soft" text-anchor="middle">{fixed(b, 0)}</text>'
                   f'<text x="{n(cx)}" y="{H - 14}" class="tick" text-anchor="middle">{esc(name)}</text></g>')
    out.append(f'<line x1="{L}" x2="{W - L}" y1="{n(y(0))}" y2="{n(y(0))}" class="axis" /></svg>')
    return "".join(out) + tip_box("막대에 마우스를 올리면 두 집단 비율이 나와요 · 파랑 = 고배당기업(같은 4개 업종), 회색 = 대조군")


# ── macro.tsx ─────────────────────────────────────────────────────────────
def r2(v) -> str:
    return "–" if v is None else fixed(v, 2).replace("-", "−")


VIEWS = [("level", "그 해 값끼리"), ("diff", "전년 대비 변화끼리"), ("panel", "회사마다"), ("panel_ex2025", "회사마다 (2025 빼고)")]


def corr_explorer(m) -> None:
    """8장 상관표. 웹의 시점·보는 법 칩을 선택 단추로 바꿨다."""
    with st.container(border=True):
        lags = dict(m["lags"])
        lag = st.segmented_control("거시 값을 붙인 시점", list(lags), default=m["lags"][0][0], format_func=lambda k: lags[k],
                                   key="corr_lag", label_visibility="collapsed") or m["lags"][0][0]
        views = dict(VIEWS)
        view = st.segmented_control("보는 법", list(views), default="diff", format_func=lambda k: views[k],
                                    key="corr_view", label_visibility="collapsed") or "diff"
        rows = [c for c in m["corr"] if c[0] == lag and c[1] == view]
        macros = list(dict.fromkeys(c[3] for c in rows))
        divs = list(dict.fromkeys(c[2] for c in rows))
        cell = {(c[2], c[3]): c for c in rows}
        sig_n = sum(1 for c in rows if c[5] is not None and c[5] < 0.05)
        head = "".join(f"<th>{esc(m['macro_names'].get(k, k))}</th>" for k in macros)
        body = []
        for d in divs:
            tds = []
            for k in macros:
                c = cell.get((d, k))
                r, p = (c[4], c[5]) if c else (None, None)
                on = p is not None and p < 0.05
                cls = f' class="{"sig-up" if r > 0 else "sig-down"}"' if on else ""
                tds.append(f'<td{cls} title="{"" if p is None else "p = " + fixed(p, 3)}">{r2(r)}{"*" if on else ""}</td>')
            body.append(f"<tr><th>{esc(m['dividend_names'].get(d, d))}</th>{''.join(tds)}</tr>")
        extra = f" 아무 관계가 없어도 {fixed(len(rows) * 0.05, 1)}칸쯤은 우연히 나와요." if view not in ("panel", "panel_ex2025") else ""
        md(f'<div class="corr-table"><table><thead><tr><th>배당 \\ 거시</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
           f'<p class="small" style="margin: 10px 0 0">이 조합에서 우연이 아닐 수 있는 칸(p &lt; 0.05, *)은 <b>{sig_n}</b>개 / {len(rows)}칸이에요.'
           f'{extra} 칸에 마우스를 올리면 p값이 보여요.</p>')


LAG_WORD = {"same": "같은 해", "prev": "1년 전", "decision": "결의 시점(이듬해 1~3월)"}
PANEL_YEAR = {"dps_up": ("dps_up_share", "주당배당금을 올린 회사 비율"), "dps_growth": ("dps_growth_median", "주당배당금 증가율 중앙값")}


def macro_name(m, k: str) -> str:
    base = m["macro_names"].get(k, k)
    return f"{base} 증감" if k.endswith("_chg") else base


def scatter(pts, x_name: str, y_name: str, label: str) -> str:
    W, H, L, R, T, B = 320, 240, 14, 14, 30, 40
    if not pts:
        return f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}"></svg>'
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]

    def pad(lo, hi):
        s = (hi - lo) or 1
        return lo - s * 0.08, hi + s * 0.08

    x0, x1 = pad(min(xs), max(xs))
    y0, y1 = pad(min(ys), max(ys))
    sx = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)  # noqa: E731
    sy = lambda v: T + (y1 - v) / (y1 - y0) * (H - T - B)  # noqa: E731
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((v - mx) ** 2 for v in xs)
    slope = sum((p[1] - mx) * (p[2] - my) for p in pts) / sxx if sxx else 0
    fy = lambda v: my + slope * (v - mx)  # noqa: E731
    fa, fb = sorted([mx + (y0 - my) / slope, mx + (y1 - my) / slope]) if slope else (x0, x1)
    lx0, lx1 = max(x0, fa), min(x1, fb)
    f = lambda v: fmt(v, 2)  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">',
           f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" class="axis" />',
           f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" class="axis" />']
    if lx0 < lx1:
        out.append(f'<line x1="{n(sx(lx0))}" x2="{n(sx(lx1))}" y1="{n(sy(fy(lx0)))}" y2="{n(sy(fy(lx1)))}" class="fit" />')
    for yr, px, py in pts:
        t = f"{yr}: {x_name} {f(px)} · {y_name} {f(py)}"
        out.append(f'<g class="dot" aria-label="{esc(t)}">{title(t)}<circle cx="{n(sx(px))}" cy="{n(sy(py))}" r="14" fill="transparent" />'
                   f'<circle cx="{n(sx(px))}" cy="{n(sy(py))}" r="6" class="{"bar-coin" if yr == 2025 else "bar-sea"}" />'
                   f'<text x="{n(sx(px))}" y="{n(sy(py) - 10)}" class="soft" text-anchor="middle">{str(yr)[2:]}</text></g>')
    out.append(f'<text x="{W - R}" y="{H - 12}" class="tick" text-anchor="end">{esc(x_name)} →</text>'
               f'<text x="{L}" y="4" class="tick" dominant-baseline="hanging">↑ {esc(y_name)}</text></svg>')
    return "".join(out) + tip_box("점에 마우스를 올리면 그 해 값이 나와요")


def series_pts(m, y_key: str, x_key: str, diff: bool, drop2025: bool = False):
    ys, xs = m["series"].get(y_key) or {}, m["series"].get(x_key) or {}
    years = sorted(int(k) for k in ys)

    def val(s, yr):
        v = s.get(str(yr))
        if v is None:
            return None
        if not diff:
            return v
        p = s.get(str(yr - 1))
        return None if p is None else v - p

    out = []
    for yr in years:
        x, y = val(xs, yr), val(ys, yr)
        if x is None or y is None or (drop2025 and yr == 2025):
            continue
        out.append((yr, x, y))
    return out


def _sig(c) -> bool:
    return c[5] is not None and c[5] < 0.05


def _xkey(lag: str, macro: str) -> str:
    return macro if lag == "same" else f"{macro}@{lag}"


def sig_scatters(m, kind: str) -> str:
    """p < 0.05로 뚜렷했던 짝 산점도. kind: diff 변화끼리, panel 회사마다, level 그 해 값끼리"""
    cards = []
    if kind == "panel":
        keys = list(dict.fromkeys(f"{c[0]}|{c[2]}|{c[3]}" for c in m["corr"] if c[1] in ("panel", "panel_ex2025") and _sig(c)))
        for k in keys:
            lag, dv, mv = k.split("|")
            al = next((c for c in m["corr"] if c[0] == lag and c[1] == "panel" and c[2] == dv and c[3] == mv), None)
            ex = next((c for c in m["corr"] if c[0] == lag and c[1] == "panel_ex2025" and c[2] == dv and c[3] == mv), None)
            y_key, y_name = PANEL_YEAR[dv]
            x_name = f"{LAG_WORD[lag]} {macro_name(m, mv)}"

            def show(c):
                if not c:
                    return "–"
                cls = f' class="{"sig-up" if c[4] > 0 else "sig-down"}"' if _sig(c) else ""
                return f"<b{cls}>{r2(c[4])}{'' if _sig(c) else ' (뚜렷하지 않음)'}</b>"

            cards.append(f'<div class="card scatter"><h4>{esc(y_name)} ↔ {esc(x_name)}</h4>'
                         f'<p class="small">회사마다 본 상관 {show(al)} · 2025 빼면 {show(ex)} <span>({fmt((al[7] if al else 0) or 0)}개 회사·연도)</span></p>'
                         + scatter(series_pts(m, y_key, _xkey(lag, mv), False), x_name, y_name, f"{y_name}과 {x_name}, 해마다") + "</div>")
    else:
        rows = sorted([c for c in m["corr"] if c[1] == kind and _sig(c)], key=lambda c: -abs(c[4]))
        for c in rows:
            lag, _, dv, mv, rv, p = c[:6]
            x_name = f"{LAG_WORD[lag]} {macro_name(m, mv)}{' 변화' if kind == 'diff' else ''}"
            y_name = f"{m['dividend_names'].get(dv, dv)}{' 변화' if kind == 'diff' else ''}"
            cards.append(f'<div class="card scatter"><h4>{esc(y_name)} ↔ {esc(x_name)}</h4>'
                         f'<p class="small">상관 <b class="{"sig-up" if rv > 0 else "sig-down"}">{r2(rv)}</b> · p = {fixed(p, 3)} · {jsn(c[6])}개 해</p>'
                         + scatter(series_pts(m, dv, _xkey(lag, mv), kind == "diff"), x_name, y_name, f"{y_name}과 {x_name}") + "</div>")
    return f'<div class="scatter-grid">{"".join(cards)}</div>'


def bh_count(ps, alpha: float = 0.05) -> int:
    """Benjamini–Hochberg: 보정 뒤 q < alpha로 남는 개수 (macro.tsx bhCount)"""
    s = sorted(ps)
    k = 0
    for i, p in enumerate(s):
        if p <= alpha * (i + 1) / len(s):
            k = i + 1
    return k


def coef_chart(rows, base: int, label: str) -> str:
    W, H, top, bottom, L, R = 440, 230, 16, 30, 40, 8
    lo, hi = min(0, *[r[2] for r in rows]), max(0, *[r[3] for r in rows])
    span = (hi - lo) or 1
    y = lambda v: top + (hi - v) / span * (H - top - bottom)  # noqa: E731
    step = (W - L - R) / len(rows)
    x = lambda i: L + step * (i + 0.5)  # noqa: E731
    pp = lambda v: f"{'+' if v > 0 else ''}{fixed(v, 1)}%p".replace("-", "−")  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">']
    for v in (hi, 0, lo):
        out.append(f'<text x="{L - 6}" y="{n(y(v) + 4)}" class="soft" text-anchor="end">{"0" if v == 0 else pp(v)}</text>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{n(y(0))}" y2="{n(y(0))}" class="axis" />')
    for i, (yr, c, lo_, hi_) in enumerate(rows):
        t = f"{yr}: 기준 해 (0)" if yr == base else f"{yr}: {pp(c)} (95% 범위 {pp(lo_)} ~ {pp(hi_)})"
        cls = "dot-base" if yr == base else "bar-coin" if yr == 2025 else "bar-sea"
        out.append(f'<g class="bar" aria-label="{esc(t)}">{title(t)}<rect class="hit" x="{n(x(i) - step / 2)}" y="{top}" width="{n(step)}" height="{H - top - bottom}" />'
                   + (f'<line x1="{n(x(i))}" x2="{n(x(i))}" y1="{n(y(hi_))}" y2="{n(y(lo_))}" class="ci" />' if yr != base else "")
                   + f'<circle cx="{n(x(i))}" cy="{n(y(c))}" r="6" class="{cls}" />'
                   f'<text x="{n(x(i))}" y="{H - 10}" class="tick" text-anchor="middle">{str(yr)[2:]}</text></g>')
    out.append("</svg>")
    return "".join(out) + tip_box("점에 마우스를 올리면 값이 나와요")
