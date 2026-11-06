"""데이터 이야기 분석 보고서 PDF → report/분석결과_요약보고서.pdf

실행: .venv/bin/python -m scripts.report_story_pdf [--out ...] [--html-only]
- 숫자는 화면과 같은 API 함수(source/api/main.py의 funnel·analysis·analysis_events·analysis_movement)에서 가져온다.
- 맨 앞에 '한눈에 보는 결론'(장마다 물음과 숫자로 된 답)을 둔다.
- 장마다 '목적 · 자료와 방법 · 결과 · 확인하는 법 · 한계 · 시사점'. 확인하는 법의 SQL·명령은 source/scripts/story_checks.py에 있고,
  보고서를 만들 때 모두 실제로 돌려 화면 값과 같은지 맞춰 본다. 다르면 멈춘다.
- 화면 API에 없는 숫자(2장 몰림 크기, 9장 제도 전 모습 점검)는 extra_data()에서 같은 분석 코드로 다시 계산한다.
- 화면에서 바꿔 볼 수 있는 모든 조합(공시 뒤 주가 60개, 경기 상관 432칸, 행동 분석 검정 34개)은 부록 표로 싣는다.
- 기본 위치로 만들면 app/web/public/onepick_story_report.pdf에도 복사한다(화면의 'PDF 받기' 링크).
- 회사 이름은 넣지 않는다(데이터 이야기와 같은 원칙). PDF는 macOS WebKit으로 인쇄한다(source/scripts/html_to_pdf.swift).
"""
import argparse
import shutil
import subprocess
import tempfile
from datetime import date
from html import escape
from pathlib import Path

from api import main as api
from core import bunching as bn
from core import db
from core import p1_analysis as p1
from scripts import check_did_pretrend as pretrend
from scripts import story_checks as sc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "분석결과_요약보고서.pdf"
WEB_COPY = ROOT / "app" / "web" / "public" / "onepick_story_report.pdf"  # 데이터 이야기 화면의 'PDF 받기' 링크(웹·Streamlit)
MOA = ROOT / "app" / "web" / "public" / "moa"

SEA, SEA_DEEP, WAVE, COIN, COIN_DEEP, INK, GRAY, LINE, PAPER, OK, NO = (
    "#3D6BFF", "#2547D9", "#EEF2FF", "#FFC93C", "#E0A500", "#191F28", "#6B7684", "#E5E8EE", "#F6F7F9", "#19B36B", "#F2555A")

CSS = """
@page { size: A4; margin: 12mm 12mm 14mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0 auto; max-width: 168mm; color: #191F28; font: 500 10.5pt/1.65 "Gothic A1", "Apple SD Gothic Neo", sans-serif; word-break: keep-all; }
h1, h2, h3, .round { font-family: "Do Hyeon", "Gothic A1", sans-serif; font-weight: 400; }
h1 { font-size: 30pt; line-height: 1.25; margin: 0 0 10px; }
h2 { font-size: 20pt; line-height: 1.3; margin: 0 0 8px; }
h2 em, h1 em { font-style: normal; color: #3D6BFF; }
h3 { font-size: 13.5pt; margin: 18px 0 6px; }
h4 { font-size: 10.5pt; margin: 12px 0 4px; font-weight: 800; }
p { margin: 0 0 8px; }
.page { break-before: page; page-break-before: always; }
.ch-no { display: inline-block; font: 400 11pt "Do Hyeon"; color: #fff; background: #3D6BFF; border-radius: 999px; padding: 2px 14px; margin-bottom: 8px; }
.lead { font-size: 11pt; }
.small, .muted { color: #6B7684; font-size: 8.8pt; line-height: 1.55; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; }
.cover .logo { display: flex; align-items: center; gap: 10px; font: 400 26pt "Do Hyeon"; margin-bottom: 40px; }
.cover .logo i { width: 30px; height: 30px; border-radius: 50%; background: #FFC93C; box-shadow: inset 0 -4px 0 #E0A500; display: inline-block; }
.cover img { width: 150px; margin-top: 30px; }
.box { border-radius: 16px; padding: 12px 16px; margin: 10px 0; break-inside: avoid; page-break-inside: avoid; }
.why { background: #EEF2FF; }
.basis { background: #F6F7F9; }
.check { background: #fff; border: 2px solid #E5E8EE; break-inside: auto; page-break-inside: auto; }
.basis { break-inside: auto; page-break-inside: auto; }
pre, h4 { break-inside: avoid; page-break-inside: avoid; }
.limit { background: #FFF6DB; }
.tag { display: inline-block; font: 800 8.5pt "Gothic A1"; border-radius: 999px; padding: 1px 10px; margin-bottom: 6px; }
.why .tag { background: #3D6BFF; color: #fff; }
.basis .tag { background: #191F28; color: #fff; }
.check .tag { background: #6B7684; color: #fff; }
.limit .tag { background: #E0A500; color: #fff; }
.meaning { background: #E9F8F0; }
.meaning .tag { background: #19B36B; color: #fff; }
.result-tag { display: inline-block; font: 800 8.5pt "Gothic A1"; border-radius: 999px; padding: 1px 10px; background: #FFC93C; color: #191F28; margin: 10px 0 4px; }
.box ul { margin: 0; padding-left: 18px; } .box li { margin: 2px 0; }
pre { background: #191F28; color: #E5E8EE; border-radius: 10px; padding: 10px 12px; font: 7.6pt/1.5 Menlo, monospace; white-space: pre-wrap; word-break: break-all; margin: 6px 0; }
.ok { color: #19B36B; font-weight: 800; } .no { color: #F2555A; font-weight: 800; }
table { border-collapse: collapse; width: 100%; font-size: 8.4pt; font-variant-numeric: tabular-nums; margin: 6px 0; }
th, td { border-bottom: 1px solid #E5E8EE; padding: 3px 6px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
td.l, th.l { text-align: left; }
thead th { color: #6B7684; font-weight: 800; border-bottom: 2px solid #191F28; }
tr { break-inside: avoid; page-break-inside: avoid; }
td.sig { color: #2547D9; font-weight: 800; }
.facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 8px 0; }
.facts div { background: #F6F7F9; border-radius: 14px; padding: 10px 12px; }
.facts dt { font-size: 8.4pt; color: #6B7684; } .facts dd { margin: 2px 0 0; font: 400 18pt "Do Hyeon"; color: #3D6BFF; }
.card { border: 1px solid #E5E8EE; border-radius: 16px; padding: 10px 12px; margin: 8px 0; break-inside: avoid; page-break-inside: avoid; }
.say { display: flex; gap: 10px; align-items: flex-end; margin: 8px 0; }
.say img { width: 52px; } .say p { background: #EEF2FF; border-radius: 16px 16px 16px 4px; padding: 8px 14px; font-weight: 700; margin: 0; }
svg text { font-family: "Gothic A1", sans-serif; }
.toc li { margin: 3px 0; } .toc { columns: 2; }
.grid8 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
"""


# ---------------------------------------------------------------- 작은 도구

def n(v, d=0) -> str:
    if v is None:
        return "–"
    if isinstance(v, float) and v != v:
        return "–"
    s = f"{v:,.{d}f}"
    return s.replace("-", "−")


def pv(v) -> str:
    """p값: 0.001보다 작으면 '< 0.001', 아니면 소수 셋째 자리."""
    return "–" if v is None else "< 0.001" if v < 0.001 else f"{v:.3f}"


def pp(v, d=1) -> str:
    return "–" if v is None else (("+" if v > 0 else "") + n(v, d) + "%p")


def table(head: list[str], rows: list[list], left: int = 1, sig_col: int | None = None) -> str:
    th = "".join(f"<th class='{'l' if i < left else ''}'>{escape(str(h))}</th>" for i, h in enumerate(head))
    body = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            cls = "l" if i < left else ""
            if sig_col is not None and i == sig_col and isinstance(v, (int, float)) and v == v and v < 0.05:
                cls += " sig"
            tds.append(f"<td class='{cls}'>{escape(v if isinstance(v, str) else n(v, 4) if isinstance(v, float) and abs(v) < 1 and v != 0 else n(v, 2) if isinstance(v, float) else n(v) if isinstance(v, int) else str(v))}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def box(kind: str, label: str, html: str) -> str:
    return f"<div class='box {kind}'><span class='tag'>{label}</span>{html}</div>"


def say(text: str, mood: str = "curious") -> str:
    return f"<div class='say'><img src='moa_{mood}.webp' alt=''><p>{text}</p></div>"


# ---------------------------------------------------------------- 그림 (원픽 화면 그림과 같은 색 약속: 파랑 기본, 노랑 강조)

def bars(rows: list[tuple], hi: set, unit: str = "곳", label_every: int = 5, w: int = 680, h: int = 170, marks: dict | None = None) -> str:
    top, bottom, left = 34, 24, 6
    mx = max((v for _, v in rows), default=1) or 1
    bw = (w - left * 2) / len(rows)
    out = []
    for i, (k, v) in enumerate(rows):
        x = left + i * bw
        bh = (h - top - bottom) * (v / mx)
        color = COIN if k in hi else "#C9D3FF"
        out.append(f"<rect x='{x + 1:.1f}' y='{h - bottom - bh:.1f}' width='{bw - 2:.1f}' height='{max(bh, 0.5):.1f}' rx='2' fill='{color}'/>")
        if k in hi:
            out.append(f"<text x='{x + bw / 2:.1f}' y='{h - bottom - bh - 4:.1f}' font-size='9' text-anchor='middle' font-weight='800'>{v}</text>")
        if isinstance(k, int) and k % label_every == 0:
            out.append(f"<text x='{x + bw / 2:.1f}' y='{h - 8}' font-size='9' fill='{GRAY}' text-anchor='middle'>{k}{unit}</text>")
    for k, text in (marks or {}).items():
        idx = [r[0] for r in rows].index(k)
        x = left + idx * bw
        out.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='14' y2='{h - bottom}' stroke='{INK}' stroke-dasharray='3 3'/>"
                   f"<text x='{x + 3:.1f}' y='10' font-size='9' font-weight='800'>{escape(text)}</text>")
    out.append(f"<line x1='{left}' x2='{w - left}' y1='{h - bottom}' y2='{h - bottom}' stroke='{INK}'/>")
    return f"<svg viewBox='0 0 {w} {h}' width='100%'>{''.join(out)}</svg>"


def hbars(rows: list[tuple], unit: str = "곳", w: int = 680, color: str = SEA) -> str:
    rh, lw = 22, 230
    mx = max((v for _, v in rows), default=1) or 1
    out = []
    for i, (k, v) in enumerate(rows):
        y = i * rh + 4
        bw = (w - lw - 60) * v / mx
        out.append(f"<text x='0' y='{y + 14}' font-size='10'>{escape(str(k))}</text>"
                   f"<rect x='{lw}' y='{y + 3}' width='{max(bw, 1):.1f}' height='{rh - 8}' rx='4' fill='{color}'/>"
                   f"<text x='{lw + bw + 6:.1f}' y='{y + 14}' font-size='10' font-weight='800'>{n(v)}{unit}</text>")
    return f"<svg viewBox='0 0 {w} {len(rows) * rh + 8}' width='100%'>{''.join(out)}</svg>"


def lines(rows: list[tuple], names: tuple[str, str], unit: str = "%", w: int = 680, h: int = 180, xlab=lambda y: str(y)) -> str:
    top, bottom, left, right = 16, 26, 36, 90
    vals = [v for r in rows for v in r[1:] if v is not None]
    lo, hi = min(0, min(vals)), max(vals)
    x = lambda i: left + (w - left - right) * i / max(len(rows) - 1, 1)
    y = lambda v: top + (hi - v) / (hi - lo or 1) * (h - top - bottom)
    out = [f"<line x1='{left}' x2='{w - right}' y1='{y(lo)}' y2='{y(lo)}' stroke='{INK}'/>"]
    for j, color in ((1, SEA), (2, COIN_DEEP)):
        pts = [(x(i), y(r[j])) for i, r in enumerate(rows) if r[j] is not None]
        out.append(f"<polyline fill='none' stroke='{color}' stroke-width='2.5' points='{' '.join(f'{a:.1f},{b:.1f}' for a, b in pts)}'/>")
        for (a, b), r in zip(pts, [r for r in rows if r[j] is not None]):
            out.append(f"<circle cx='{a:.1f}' cy='{b:.1f}' r='3' fill='{color}'/><text x='{a:.1f}' y='{b - 6:.1f}' font-size='8' text-anchor='middle' fill='{color}'>{n(r[j], 1)}</text>")
        lx, ly = pts[-1]
        out.append(f"<text x='{lx + 8:.1f}' y='{ly + 4:.1f}' font-size='10' font-weight='800' fill='{color}'>{escape(names[j - 1])}</text>")
    for i, r in enumerate(rows):
        out.append(f"<text x='{x(i):.1f}' y='{h - 8}' font-size='9' fill='{GRAY}' text-anchor='middle'>{escape(xlab(r[0]))}</text>")
    return f"<svg viewBox='0 0 {w} {h}' width='100%'>{''.join(out)}</svg>"


def curve(points: list[list], w: int = 330, h: int = 170, title: str = "") -> str:
    """[날, 사례, 가운데, 25%, 75%] → 가운데 값 선과 가운데 절반 띠."""
    top, bottom, left = 20, 22, 30
    lo = min(min(p[3] for p in points), 0)
    hi = max(max(p[4] for p in points), 0)
    days = points[-1][0] or 1
    x = lambda d: left + (w - left - 8) * d / days
    y = lambda v: top + (hi - v) / (hi - lo or 1) * (h - top - bottom)
    band = " ".join(f"{x(p[0]):.1f},{y(p[4]):.1f}" for p in points) + " " + " ".join(f"{x(p[0]):.1f},{y(p[3]):.1f}" for p in reversed(points))
    med = " ".join(f"{x(p[0]):.1f},{y(p[2]):.1f}" for p in points)
    end = points[-1]
    return (f"<svg viewBox='0 0 {w} {h}' width='100%'><text x='0' y='12' font-size='10' font-weight='800'>{escape(title)}</text>"
            f"<polygon points='{band}' fill='{WAVE}'/><line x1='{left}' x2='{w - 8}' y1='{y(0):.1f}' y2='{y(0):.1f}' stroke='{INK}'/>"
            f"<polyline points='{med}' fill='none' stroke='{SEA}' stroke-width='2.5'/>"
            f"<text x='{x(end[0]) - 2:.1f}' y='{y(end[2]) - 6:.1f}' font-size='10' font-weight='800' text-anchor='end' fill='{SEA_DEEP}'>{pp(end[2], 2)}</text>"
            f"<text x='{left}' y='{h - 6}' font-size='9' fill='{GRAY}'>공시 날</text><text x='{w - 8}' y='{h - 6}' font-size='9' fill='{GRAY}' text-anchor='end'>{days}거래일</text>"
            f"<text x='{left - 4}' y='{y(hi) + 4:.1f}' font-size='8' fill='{GRAY}' text-anchor='end'>{n(hi, 1)}</text>"
            f"<text x='{left - 4}' y='{y(lo) + 4:.1f}' font-size='8' fill='{GRAY}' text-anchor='end'>{n(lo, 1)}</text></svg>")


def coef_chart(rows: list[list], base: int = 2023, w: int = 680, h: int = 190) -> str:
    """[연도, 계수, 아래, 위] (%p) → 점과 95% 범위 막대. 2025는 노란 점, 기준 해는 속이 빈 점."""
    top, bottom, left = 14, 24, 46
    lo = min(0, *(r[2] for r in rows))
    hi = max(0, *(r[3] for r in rows))
    step = (w - left - 8) / len(rows)
    x = lambda i: left + step * (i + 0.5)
    y = lambda v: top + (hi - v) / (hi - lo or 1) * (h - top - bottom)
    out = [f"<line x1='{left}' x2='{w - 8}' y1='{y(0):.1f}' y2='{y(0):.1f}' stroke='{INK}'/>"]
    for v in (hi, lo):
        out.append(f"<text x='{left - 6}' y='{y(v) + 4:.1f}' font-size='9' fill='{GRAY}' text-anchor='end'>{pp(v)}</text>")
    for i, (yr, c, l, u) in enumerate(rows):
        if yr != base:
            out.append(f"<line x1='{x(i):.1f}' x2='{x(i):.1f}' y1='{y(u):.1f}' y2='{y(l):.1f}' stroke='{GRAY}' stroke-width='2'/>")
        fill = "#fff" if yr == base else COIN if yr == 2025 else SEA
        out.append(f"<circle cx='{x(i):.1f}' cy='{y(c):.1f}' r='5.5' fill='{fill}' stroke='{GRAY if yr == base else fill}' stroke-width='2'/>"
                   f"<text x='{x(i):.1f}' y='{h - 8}' font-size='9.5' text-anchor='middle' fill='{GRAY}'>{yr}</text>")
        if yr != base:
            out.append(f"<text x='{x(i) + 8:.1f}' y='{y(c) + 3:.1f}' font-size='8.5' font-weight='800'>{pp(c)}</text>")
    return f"<svg viewBox='0 0 {w} {h}' width='100%'>{''.join(out)}</svg>"


def grid3(year: int, g: list[list[int]]) -> str:
    """3장 칸 그림 한 해: 줄 = 증가율(10% 이상 / 0~10% / 감소), 칸 = 배당성향(25% 미만 / 25~40% / 40% 이상). 요건 칸은 초록 테두리."""
    cell, pad = 44, 2
    mx = max(max(r) for r in g) or 1
    ok = {(0, 1), (0, 2), (1, 2), (2, 2)}  # 나목(25%↑·10%↑)·가목(40%↑, 배당이 줄지 않을 때) — 감소 줄의 40%는 제2호로 빠질 수 있어 테두리만 옅게
    out = [f"<text x='0' y='12' font-size='11' font-weight='800'>{year}</text>"]
    for r in range(3):
        for c in range(3):
            v = g[r][c]
            x, y = c * (cell + pad), 18 + r * (cell + pad)
            stroke = f"stroke='{OK}' stroke-width='2.5'" if (r, c) in ok and r < 2 else ""
            out.append(f"<rect x='{x}' y='{y}' width='{cell}' height='{cell}' rx='6' fill='rgba(61,107,255,{0.06 + 0.5 * v / mx:.2f})' {stroke}/>"
                       f"<text x='{x + cell / 2}' y='{y + cell / 2 + 4}' font-size='11' text-anchor='middle' font-weight='800'>{v}</text>")
    return f"<svg viewBox='0 0 {3 * cell + 2 * pad} {18 + 3 * cell + 2 * pad}' width='100%'>{''.join(out)}</svg>"


# ---------------------------------------------------------------- 장 만들기

LABELS = ("목적", "자료와 방법", "확인하는 법", "한계", "시사점")  # 장마다 이 순서로 (결과는 자료와 방법 다음)


def check_html(outs: list[sc.Outcome], ch: int) -> str:
    parts = []
    for o in [o for o in outs if o.check.ch == ch]:
        mark = "<span class='ok'>✓ 화면 값과 같음</span>" if o.same else "<span class='no'>✗ 화면 값과 다름</span>"
        val = o.actual
        if isinstance(val, dict) and len(str(val)) > 260:
            val = "표 값 전부"
        parts.append(f"<h4>{escape(o.check.what)} · {mark}</h4><pre>{escape(o.check.code)}</pre>"
                     f"<p class='small'>이 보고서를 만들 때 돌린 결과: {escape(str(val))}</p>")
    return "".join(parts)


def chapter(no: int, title: str, purpose: str, method: str, result: str, limit: str, meaning: str, outs: list[sc.Outcome]) -> str:
    return (f"<section class='page'><span class='ch-no'>{no}장</span><h2>{title}</h2>"
            + box("why", "목적", purpose) + box("basis", "자료와 방법", method)
            + f"<span class='result-tag'>결과</span>{result}"
            + box("check", "확인하는 법", check_html(outs, no)) + box("limit", "한계", limit)
            + box("meaning", "시사점", meaning) + "</section>")


def extra_data(url: str | None = None) -> dict:
    """화면 API에는 없고 화면 글이 출처와 함께 적어 둔 숫자를, 같은 코드로 다시 계산한다.
    - bunching: 2장 몰림 크기 (source/scripts/analysis_bunching.py와 같은 source/core/bunching.py, 같은 시드·1,000번)
    - pretrend: 9장 제도 전 모습 점검 (source/scripts/check_did_pretrend.py compute)"""
    with db.connect(url) as conn:
        comp = p1.companies(db.fetch_dicts(conn, p1.DIV_SQL), db.fetch_dicts(conn, p1.FIN_SQL))
    pay = bn.payouts_by_year(comp, range(2018, 2026))
    bunch = {y: bn.one_sided_25(pay[y], reps=bn.BOOT_REPS) for y in pay}
    return {"bunching": bunch, "pretrend": pretrend.compute(url)}


def build(s: dict, outs: list[sc.Outcome]) -> str:
    f, a, ev, mv = s["funnel"], s["analysis"], s["events"], s["movement"]
    x = s["extra"]
    built = date.today().isoformat()
    payout, growth = dict(a["payout"]), dict(a["growth"])
    ret = a["retro"]
    before = [r[4] for r in ret if r[0] < 2024]
    r24 = next(r for r in ret if r[0] == 2024)
    mc, bh, cc, t = a["macro"], a["behavior"], a["control"], a["trust"]
    diff = [c for c in mc["corr"] if c[1] == "diff"]
    diff_sig = sorted([c for c in diff if c[5] is not None and c[5] < 0.05], key=lambda c: c[5])
    ps = sorted(c[5] for c in diff if c[5] is not None)
    bh_k = max([i + 1 for i, p in enumerate(ps) if p <= 0.05 * (i + 1) / len(ps)], default=0)
    prim = {k: [x for x in bh["fits"][k] if x["role"] == "primary"] for k in bh["fits"]}
    fit = lambda k, start: next(x for x in prim[k] if x["name"].startswith(start))
    rate_f, fx_f, own_f, close_f = fit("exposure", "금리"), fit("exposure", "환율"), fit("policy", "개인 최대주주"), fit("policy", "기준선")
    placebo = [x for x in bh["fits"]["policy"] if x["role"] == "placebo" and x["name"].startswith("개인 최대주주")]
    pl_sig = sum(1 for x in placebo if x["p_cluster"] is not None and x["p_cluster"] < 0.05)
    lag_name = dict(mc["lags"])
    dn, mn = mc["dividend_names"], mc["macro_names"]
    sim = cc["simulation"]
    sig = lambda p: p is not None and p < 0.05

    # 요약 장과 본문이 함께 쓰는 값
    passed = f["ga"] + f["na"] + f["na_deficit"]
    b25 = x["bunching"][2025]
    b_pre_sure = [y for y, r in x["bunching"].items() if y < 2025 and r.ci_low > 0]
    pt = x["pretrend"]
    pre_gap = [v for y, v in pt["gap"].items() if y <= 2024]
    grid_ok = []  # 3장: 2018~2024년 해마다 요건 칸(가목 2칸 + 나목 1칸)에 든 비율(10곳 기준)
    for y, g in mv["grid"].items():
        if 2018 <= int(y) <= 2024 and sum(map(sum, g)):
            grid_ok.append((g[0][1] + g[0][2] + g[1][2]) / sum(map(sum, g)) * 10)
    ok_lo, ok_hi = round(min(grid_ok)), round(max(grid_ok))
    drop_tens = round(sum(before) / len(before) / 10)
    min_ok = a["min_ratio"][0][1]
    min_n = sum(v for _, v in a["min_ratio"])
    reg = [r for r in ev["methods"]["regression_60"] if r["모형"].startswith("+ 규모")]
    coef = lambda name: next(r for r in reg if r["변수"] == name)
    c_yield, c_up, c_size = coef("배당수익률(%)"), coef("배당 증가(0/1)"), coef("log 시가총액(추정)")
    ht = {r["묶음"]: r for r in a["holder"]["table"]}
    h_near = next(r for k, r in ht.items() if k.startswith("기준선 근처"))
    h_far = next(r for k, r in ht.items() if k.startswith("나머지"))
    pf = mc["profit"]
    pf_up, pf_down = pf["updown_ex_last"]
    pf_r = next(r for r in pf["firm_ex_last"] if r["profit"] == "ni_change" and r["dividend"] == "dps_change")
    pf_prev = next(r for r in pf["firm_ex_last"] if r["profit"] == "ni_change_prev")
    macro_firm_max = max([abs(c[4]) for c in mc["corr"] if c[1] == "panel_ex2025" and c[4] is not None], default=0)
    inc25 = next(r for r in cc["increase"] if r[0] == 2025)
    inc_gap_max = max(abs(r[2] - r[4]) for r in cc["increase"] if r[0] < 2025 and r[2] is not None and r[4] is not None)
    sv, dv, rv = t["source_verify"], t["dart_verify"], t["review"]
    sv_rate = sv.get("일치", 0) / sum(sv.values()) * 100
    res = t.get("resolution") or {}

    cover = f"""<section class='cover'>
<div class='logo'><i></i>원픽</div>
<h1>데이터 이야기<br><em>분석 보고서</em></h1>
<p class='lead'>2026년 고배당기업 {n(f['total'])}곳과 같은 업종 상장사(대조군) {n(t['control']['companies'])}곳의 공시·재무제표·주가·경기 자료를 분석한 결과예요.
장마다 <b>목적 · 자료와 방법 · 결과 · 확인하는 법 · 한계 · 시사점</b> 순서로 썼어요. 화면에서 바꿔 볼 수 있는 모든 조합은 부록에 표로 실었어요.</p>
<p class='small'>만든 날 {built} · 숫자는 원픽 화면이 쓰는 API 함수(source/api/main.py)와 분석 코드에서 바로 가져왔어요 · 회사 이름은 넣지 않았어요 · 만든 코드 source/scripts/report_story_pdf.py</p>
<p class='small'><b>종목 추천이 아니며 매수·매도 판단 근거로 제공하지 않습니다.</b> 지난 숫자를 정리한 것이고, 한쪽이 다른 쪽의 원인이라는 뜻은 아니에요.</p>
<img src='moa_happy.webp' alt=''>
</section>"""

    summary = f"""<section class='page'><h2>한눈에 보는 <em>결론</em></h2>
<p class='lead'>장마다 무엇을 물었고, 숫자가 무엇이라고 답했는지 한 줄씩 모았어요. 자세한 근거와 한계는 각 장에 있어요.</p>
{table(['장', '물음', '숫자가 말한 답'], [
        ['1 법 토너먼트', '638곳은 법의 요건을 어디서 채우고 어디서 걸렸나?', f"요건을 모두 채운 곳 {n(passed)}곳(가목 {f['ga']} · 나목 {f['na']} · 적자라 25%로 본 나목 {f['na_deficit']}). 배당소득이 줄어 걸린 곳 {f['fail2']}곳, 자료가 모자라 보류 {f['hold_missing'] + f['hold_zero']}곳, 미달 {f['fail3']}곳."],
        ['2 기준선에 몰려요', '배당성향이 기준선 바로 위에 몰렸나?', f"2025년 배당성향 25~28%에 예상보다 약 {n(b25.excess)}곳이 더 있었어요(95% 범위 {n(b25.ci_low)}~{n(b25.ci_high)}곳). 2018~2024년에는 {'이런 몰림이 없었어요' if not b_pre_sure else '일부 해에도 몰림이 있었어요'}."],
        ['3 8년의 움직임', '지금 고배당기업은 예전에도 요건을 채웠나?', f"2018~2024년에는 해마다 10곳 중 {ok_lo if ok_lo == ok_hi else f'{ok_lo}~{ok_hi}'}곳 정도만 요건 칸에 있었어요."],
        ['4 내년엔 절반이', '요건을 채운 회사가 다음 해에도 채웠나?', f"2018~2023년에 해마다 {round(min(before))}~{round(max(before))}%가 다음 해에 빠졌어요(10곳 중 {drop_tens}곳꼴). 빠진 이유 1위는 {a['drop_reasons'][0][0]}({n(a['drop_reasons'][0][1])}건)이에요."],
        ['5 내년에 필요한 배당', '2027년 배당도 대상이 되려면 얼마를 줘야 하나?', f"계산한 {n(min_n)}곳 중 {n(min_ok)}곳({n(min_ok / min_n * 100, 1)}%)은 2025년만큼만 줘도 돼요. 남은 현금은 한가운데 회사가 최소 배당의 {a['capacity']['median']}배예요."],
        ['6 공시 뒤 주가', '배당 공시 뒤 주가가 더 오른 데는 무엇이 관련 있었나?', f"배당을 늘렸는지(p = {pv(c_up['p'])})보다 배당수익률이 높았는지(1%p당 {pp(c_yield['계수(%p)'], 2)}, p = {pv(c_yield['p'])})가 더 관련 있었어요."],
        ['7 최대주주', '기준선 근처 회사는 최대주주가 다른가?', f"최대주주가 개인인 회사가 기준선 근처 {h_near['개인 최대주주(%)']}%, 나머지 {h_far['개인 최대주주(%)']}%예요(검정하지 않은 단순 비교)."],
        ['8 경기와 배당', '경기가 좋아지면 배당도 늘었나?', f"변화끼리 본 {len(diff)}짝 중 {len(diff_sig)}짝만 함께 움직였고, 보정하면 {bh_k}짝이에요. 배당은 경기보다 회사 이익을 따라갔어요(상관 {pf_r['r']:.2f})."],
        ['9 세금 제도와 배당', '분리과세 뒤 누가 배당을 더 늘렸나?', f"개인 최대주주 회사가 2025년에 배당을 10% 이상 늘린 비율이 평소보다 {pp(own_f['coef'] * 100)} 더 올랐어요(보정 p {n(own_f['p_holm'], 3)}). 제도 전 추세를 빼도 {pp(pt['did_trend']['coef'])}로 남아요. 같은 해 상법 개정 영향과는 가를 수 없어요."],
        ['10 대조군과 비교', '배당을 덜 하는 같은 업종 회사와 무엇이 다른가?', f"2025년에 배당을 10% 넘게 늘린 비율이 고배당기업 {n(inc25[2], 1)}%, 대조군 {n(inc25[4], 1)}%였어요. 2024년까지는 차이가 가장 커도 {n(inc_gap_max, 1)}%p였어요."],
        ['11 데이터 뒷이야기', '이 숫자들을 믿어도 되나?', f"원문과 대조한 {n(sum(sv.values()))}칸 중 {n(sv_rate, 1)}%가 같았고, 다른 칸 {n(res.get('source_verify', {}).get('open', 0))}칸은 팀이 원문을 보고 모두 확인·정정했어요."],
    ], left=3)}
{say('정리하면, 기준선 바로 위에 회사가 몰렸고 2025년에 개인 최대주주 회사가 배당을 더 늘렸어요. 다만 모두 함께 나타난 모습이라, 제도 때문이라고 단정하지 않아요.')}
</section>"""

    n_same = sum(o.same for o in outs)
    howto = f"""<section class='page'><h2>이 보고서를 <em>읽는 법</em></h2>
<p class='lead'>숫자마다 어디서 왔는지 적었고, 읽는 사람이 직접 다시 셀 수 있게 만들었어요.</p>
{box('why', '목적', '<p>그 장에서 무엇을 알고 싶었는지와 그 이유예요. 고배당기업 배당소득 분리과세(조세특례제한법 제104조의27) 요건이나 투자자가 궁금해할 점과 이어져요.</p>')}
{box('basis', '자료와 방법', '<p>자료를 어디서 받았는지(OpenDART·KIND·KRX·한국은행 ECOS), DB 표 이름, 정의와 계산식, 관련 조문이에요. 표 이름은 <b>스키마.표</b> 모양이에요(예: core.core_judgement_2026).</p>')}
<span class='result-tag'>결과</span><p>원픽 화면 <b>데이터 이야기</b>와 같은 숫자와 그림이에요. 2025년은 노란색, 나머지는 파란색이에요.</p>
{box('check', '확인하는 법', f'<p>onepick DB에 그대로 돌려 볼 수 있는 SQL이나 명령이에요. 이 보고서를 만들 때 {len(outs)}개를 모두 실제로 돌렸고, <b>{n_same}개가 화면 값과 같았어요</b>. 하나라도 다르면 보고서를 만들지 않아요.</p><p class="small">DB를 받는 법은 report/실행안내/팀원_실행_안내.md에 있어요(PostgreSQL 덤프 또는 DuckDB 파일).</p>')}
{box('limit', '한계', '<p>그 분석으로 말할 수 없는 것이에요. 함께 나타난 것(상관)과 원인(인과)을 섞지 않으려고 적었어요.</p>')}
{box('meaning', '시사점', '<p>결과가 투자자나 제도를 보는 사람에게 무슨 뜻인지예요. 한계 안에서 말할 수 있는 만큼만 썼어요.</p>')}
<h3>숫자를 읽는 약속</h3>
<ul><li><b>p값</b>: 실제로는 관련이 없는데 이만큼 차이가 우연히 나올 가능성이에요. 0.05보다 작으면 '우연으로 보기 어렵다'고 써요. 차이가 있다는 뜻이지 크다는 뜻은 아니에요.</li>
<li><b>보정</b>: 여러 번 검사하면 우연히 걸리는 짝도 늘어나요. 그래서 검사한 횟수만큼 기준을 엄하게 잡은 값(BH·Holm 보정)을 함께 적어요.</li>
<li><b>가운데 값</b>: 회사들을 크기순으로 줄 세웠을 때 한가운데 회사의 값이에요(중앙값). 아주 큰 회사 하나에 흔들리지 않아요.</li>
<li><b>[팀 해석]</b>: 법이나 공식 해설에 답이 없어 팀이 정한 기준이에요.</li></ul>
<h3>차례</h3><ol class='toc'>
<li>법 토너먼트</li><li>기준선에 몰려요</li><li>8년의 움직임</li><li>내년엔 절반이</li><li>내년에 필요한 배당</li><li>공시 뒤 주가</li>
<li>최대주주</li><li>경기와 배당</li><li>세금 제도와 배당</li><li>대조군과 비교</li><li>데이터 뒷이야기</li>
<li>부록 A~F: 모든 조합 표</li></ol>
<h3>자료가 오는 길</h3>
{table(['단계', '내용', '대표 표'], [
        ['원천', 'KIND 고배당기업 목록, OpenDART 사업보고서·공시, KRX 주가, 한국은행 ECOS, 대조군 자료(4개 업종 상장사)', 'raw.kind_list · raw.dart_* · raw.krx_price_daily · raw.ecos_macro · partner.*'],
        ['검증', '원문 대조(코드 · DART 재대조), 팀 검토본 반영', 'core.core_source_verify · core.core_dart_verify · core.core_review_value'],
        ['확정 값', '검토로 확정한 값을 먼저 쓰는 보기', 'core.v_dividend_year_verified · core.v_financial_year_verified'],
        ['분석 결과', '판정·분석 스크립트가 저장한 결과', 'core.core_judgement_2026 · core.core_event_* · core.core_macro_* · core.core_behavior_*'],
        ['화면', 'API가 결과 표만 읽어 보여 줌', 'source/api/main.py → app/web/src/pages/Story.tsx']], left=3)}
</section>"""

    # 1장
    ch1 = chapter(1, "문 세 개를 <em>모두</em> 지나야 해요. 마지막 문만 <em>둘 중 하나</em>예요",
        f"<p>고배당기업 배당이 분리과세를 받으려면 회사가 법의 요건 세 가지를 모두 채워야 해요. {n(f['total'])}곳이 실제로 어느 요건에서 걸리는지 알아야, 투자자가 '내 종목이 왜 대상인지, 왜 아닌지'를 이해할 수 있어요.</p>",
        f"""<ul><li><b>조문</b>: 조세특례제한법 제104조의27 ① "다음 각 호의 요건을 <b>모두</b> 갖출 것". 제2호 = 직전 사업연도 배당소득이 2024 사업연도보다 줄지 않을 것. 제3호 = 가목(배당성향 40% 이상) <b>또는</b> 나목(배당성향 25% 이상이고 이익배당금액이 전전 사업연도보다 10% 이상 늘어남). 시행령 제104조의24 ⑤: 순이익이 0 이하면 부채가 자본총액의 2배를 넘을 때 0%, 아니면 25%로 봐요.</li>
<li><b>대상</b>: KIND 2026 고배당기업 목록 {n(f['total'])}곳(raw.kind_list).</li>
<li><b>숫자</b>: 2025 사업연도 배당·순이익·부채·자본(core.v_dividend_year_verified, core.v_financial_year_verified). 비율을 나누지 않고 원 단위 정수끼리 곱해 견줘요(100 × 배당 ≥ 40 × 순이익). 소수점 반올림 때문에 기준선에서 판정이 뒤집히지 않게 하려고요.</li>
<li><b>판정 코드</b>: source/core/judgement.py → 결과 표 core.core_judgement_2026. 조문과 코드의 대응은 report/검증/조문_코드_대응표.md.</li></ul>""",
        f"""<div class='facts'><div><dt>가목 (배당성향 40% 이상)</dt><dd>{f['ga']}곳</dd></div><div><dt>나목 (25% 이상 + 10% 증가)</dt><dd>{f['na']}곳</dd></div><div><dt>적자라 25%로 본 나목</dt><dd>{f['na_deficit']}곳</dd></div>
<div><dt>제2호 미충족 (배당소득 감소)</dt><dd>{f['fail2']}곳</dd></div><div><dt>판정 보류 (자료 결측)</dt><dd>{f['hold_missing']}곳</dd></div><div><dt>전전년 무배당이라 보류 · 미달</dt><dd>{f['hold_zero']} · {f['fail3']}곳</dd></div></div>
{hbars([('1라운드 자료 확인 → 보류', f['hold_missing']), ('2라운드 제2호 → 미충족', f['fail2']), ('3라운드 가목', f['ga']), ('3라운드 나목', f['na']), ('3라운드 나목(적자 25% 간주)', f['na_deficit']), ('3라운드 전전년 무배당 → 보류', f['hold_zero']), ('3라운드 미달', f['fail3'])])}
<p>요건을 모두 채운 곳은 <b>{n(passed)}곳</b>이에요. 가장 많이 걸린 문은 둘째 문(제2호, 배당소득이 2024년보다 줄지 않았나)으로 {f['fail2']}곳이에요.</p>""",
        "<p>'전전년에 배당하지 않았다가 배당한 경우를 10% 증가로 볼지'는 공식 해설이 없어 판정 보류로 두었어요[팀 해석]. 감액배당 금액이나 과세 여부를 확인하지 못한 회사도 보류예요. 국세청의 공식 판정이 아니라 공개 자료로 다시 계산한 결과예요.</p>",
        "<p>KIND 명단에 있다고 모두 요건을 채운 건 아니에요. 배당소득이 2024년보다 줄었는지(제2호)가 가장 큰 걸림돌이라, 투자자는 배당성향보다 먼저 '작년보다 배당이 줄지 않았나'를 봐야 해요.</p>", outs)

    # 2장
    pay_rows = [(k, payout[k]) for k in sorted(payout)]
    gro_rows = [(k, growth[k]) for k in sorted(growth)]
    bunch_rows = [[str(y), r.n, r.above_actual, n(r.above_actual - r.excess, 1), n(r.excess, 1), f"{n(r.ci_low, 1)} ~ {n(r.ci_high, 1)}", "예" if r.ci_low > 0 else "아니오"]
                  for y, r in sorted(x["bunching"].items())]
    ch2 = chapter(2, "분리과세 기준선 <em>바로 위에</em> 회사들이 몰려 있어요",
        "<p>세금 혜택이 기준선(배당성향 25%·40%, 배당 증가율 10%)을 넘느냐로 갈리면, 회사가 배당을 기준선에 맞춰 정할 수 있어요. 그렇다면 기준선 바로 위에 회사가 유난히 많아야 해요. 이렇게 기준선 근처에 회사가 몰렸는지 세어 보는 방법을 '몰림 분석'(bunching)이라고 해요.</p>",
        f"""<ul><li><b>배당성향</b> = 2025 이익배당금액(DART 현금배당총액) ÷ 2025 지배주주 순이익 × 100. 흑자이고 배당한 {a['notes']['payout_n']}곳을 셌어요. 적자 {a['notes']['deficit_n']}곳은 번 돈이 없어 배당성향을 계산할 수 없으니 그림에서 뺐어요.</li>
<li><b>증가율</b> = (2025 배당 − 2024 배당) ÷ 2024 배당 × 100. 두 해 모두 배당하고 2025 순이익을 아는 {a['notes']['growth_n']}곳.</li>
<li><b>몰림 크기</b>: 배당성향 5~75%를 1%p씩 나눠 세고, 28% 이상 구간만으로 매끈한 곡선(3차식)을 그려 '몰림이 없었다면 있었을 회사 수'를 만들었어요. 25~28%의 실제 회사 수에서 이 값을 뺀 것이 몰림 크기예요. 회사를 다시 뽑아 {n(bn.BOOT_REPS)}번 계산한 가운데 95%를 범위로 적었어요(시드 {bn.SEED}).</li>
<li><b>원천과 코드</b>: core.v_dividend_year_verified(d_dart_won), core.v_financial_year_verified(ni_owner_won). source/core/p1_analysis.py, source/core/bunching.py → report/분석/기준선_몰림_분석_결과.md(source/scripts/analysis_bunching.py).</li></ul>""",
        f"""<div class='card'><h4>2025 배당성향 1%p 구간별 회사 수 (10~59%)</h4>{bars(pay_rows, {25, 40}, '%', 5, marks={25: '25% 기준선', 40: '40% 기준선'})}
<p class='small'>24%대 <b>{payout[24]}</b>곳 · 25%대 <b>{payout[25]}</b>곳 · 26%대 {payout[26]}곳 · 39%대 {payout[39]}곳 · 40%대 {payout[40]}곳</p></div>
<p>2025년 배당성향 25%대는 <b>{payout[25]}곳</b>으로 바로 위 26%대 {payout[26]}곳보다 많아요. 몰림 크기를 계산하면 25~28%에 예상보다 <b>약 {n(b25.excess)}곳</b>이 더 있었어요(5~75% 안 {n(b25.n)}곳의 {n(b25.excess / b25.n * 100)}%쯤). 다시 뽑아 계산한 범위도 {n(b25.ci_low)}~{n(b25.ci_high)}곳으로 0보다 커서 우연으로 보기 어려워요.</p>
<h4>해마다 25~28%에 예상보다 더 있었던 회사 수</h4>
{table(['사업연도', '5~75% 회사', '25~28% 실제', '예상', '더 있었던 수', '95% 범위', '0보다 큼'], bunch_rows, left=1)}
<div class='card'><h4>2025 배당 증가율 1%p 구간별 회사 수 (−10~29%)</h4>{bars(gro_rows, {10}, '%', 5, marks={10: '10% 기준선'})}
<p class='small'>9%대 <b>{growth[9]}</b>곳 · 10%대 <b>{growth[10]}</b>곳 · 0%대가 많은 건 작년과 똑같이 배당한 회사가 많아서예요.</p></div>""",
        "<p>638곳은 모두 2026년에 고배당기업으로 공시한 회사라 2025 배당성향 25% 아래가 거의 없어요. 25% 아래가 비어 있는 건 회사가 배당을 올려서가 아니라 회사를 이렇게 골랐기 때문이에요. 40% 기준선 위아래는 남는 조건이 달라서(아래에는 10% 증가 회사만 남음) 이 표본으로는 몰림을 판단하기 어려워요. 9%대가 적은 것도 9%대 회사는 배당성향 40% 이상이어야 명단에 들 수 있어서예요. 몰림이 있다는 것까지는 말할 수 있지만, 왜 몰렸는지는 이 계산으로 알 수 없어요.</p>",
        f"<p>2018~2024년에는 없던 몰림이 2025년에만 나타났어요. 회사들이 기준선을 알고 배당을 맞췄을 수 있다는 신호예요. 투자자에게는 '기준선 바로 위 회사는 내년에 이익이 조금만 늘어도 기준 아래로 내려갈 수 있다'는 뜻이기도 해요(5장).</p>", outs)

    # 3장
    grids = "".join(f"<div class='card'>{grid3(int(y), g)}</div>" for y, g in sorted(mv["grid"].items(), key=lambda kv: int(kv[0])))
    g25 = mv["grid"][2025] if 2025 in mv["grid"] else mv["grid"]["2025"]
    ok_txt = f"{ok_lo}곳" if ok_lo == ok_hi else f"{ok_lo}~{ok_hi}곳"
    ch3 = chapter(3, "8년 동안 회사들은 <em>어느 칸</em>에 있었을까요?",
        "<p>요건은 배당성향과 배당 증가율 두 가지로 정해져요. 이 둘로 9칸을 나누고 해마다 회사가 어느 칸에 있었는지 보면, 지금 고배당기업이 예전에도 요건을 채웠는지, 2025년에 무엇이 달라졌는지 한눈에 보여요.</p>",
        f"""<ul><li>{escape(mv['basis'])}.</li>
<li><b>칸 경계</b>는 판정 코드와 같은 정수 비교예요: 배당성향 칸 = 100·배당 ≥ 40·순이익 → 40% 이상, 100·배당 ≥ 25·순이익 → 25~40%, 아니면 25% 미만 / 줄 = 10·배당 ≥ 11·전년 배당 → 10% 이상, 배당 ≥ 전년 배당 → 0~10%, 아니면 감소.</li>
<li><b>원천과 코드</b>: core.v_dividend_year_verified, core.v_financial_year_verified. source/api/data.py grid_3x3.</li></ul>""",
        f"""<p class='small'>줄: 위 = 증가율 10% 이상 · 가운데 = 0~10% · 아래 = 감소 / 칸: 왼쪽 = 배당성향 25% 미만 · 가운데 = 25~40% · 오른쪽 = 40% 이상. 초록 테두리 = 요건을 채우는 칸(감소 줄은 제2호로 빠질 수 있어 표시하지 않음).</p>
<div class='grid8'>{grids}</div>
<p>2018~2024년에는 해마다 <b>10곳 중 {ok_txt}</b> 정도만 요건 칸에 있었어요. 올해 고배당기업이라도 예전에는 아니었던 회사가 많다는 뜻이에요. 2025년에는 {n(sum(map(sum, g25)))}곳 중 25% 미만 칸이 {g25[0][0] + g25[1][0] + g25[2][0]}곳뿐이에요. 해마다 전체 표는 부록 D에 있어요.</p>""",
        "<p>'배당 감소' 줄은 배당 총액으로 셌는데, 법의 제2호는 배당소득을 봐요. 배당소득 값은 2024·2025년 것만 있어서 8년을 같은 잣대로 견주려고 배당 총액을 썼어요. 적자 회사, 전년에 배당하지 않았거나 값을 확인하지 못한 회사는 칸에 넣지 못해 1장 숫자와 달라요. 2025년은 그해 숫자로 고배당기업을 고른 표본이라 다른 해와 바로 견주지 않아요. 지금 명단에 있는 회사만 봐서 그사이 사라진 회사는 빠져 있어요(생존 편향).</p>",
        "<p>고배당기업은 한 번 뽑히면 끝이 아니라 해마다 다시 따져요. 올해 한 해 숫자만 보지 말고, 그 회사가 지난 몇 년 동안 어느 칸에 있었는지 함께 봐야 해요.</p>", outs)

    # 4장
    ch4 = chapter(4, "올해 고배당기업이어도, 다음 해엔 <em>절반</em>이 빠졌어요",
        "<p>올해 고배당기업이어도 내년에 또 대상인지는 따로 판정해요. 지금 법을 지난 해 숫자에 그대로 대어 '요건을 채운 회사가 다음 해에도 채웠나'를 보면, 이 혜택을 한 해짜리로 봐야 할지 알 수 있어요.</p>",
        """<ul><li><b>방법</b>: 지금 조문(source/core/judgement.py)을 2018~2025 사업연도 숫자에 그대로 대었어요. 지난 세금을 다시 매긴다는 뜻이 아니라 가상 계산이에요.</li>
<li><b>대신 쓴 것[팀 해석]</b>: 지난 해에는 감액배당 정보가 없어 배당소득을 이익배당금액으로 두었어요. 제2호의 기준(2024 배당소득)은 '직전 해 배당이 그 전 해보다 줄지 않았나'로 대신했어요.</li>
<li><b>원천과 코드</b>: core.v_dividend_year_verified, core.v_financial_year_verified. source/core/p1_analysis.py retro.</li></ul>""",
        f"""<div class='facts'><div><dt>2018~2023년 다음 해에 빠진 비율</dt><dd>{round(min(before))}~{round(max(before))}%</dd></div><div><dt>2024년</dt><dd style='color:{COIN_DEEP}'>{n(r24[4], 1)}%</dd></div><div><dt>빠진 이유 1위</dt><dd style='font-size:13pt'>{escape(a['drop_reasons'][0][0])}</dd></div></div>
{table(['사업연도', '요건 충족', '다음 해 판정 가능', '다음 해 빠짐', '빠진 비율(%)'], [[str(r[0]), r[1], r[2], r[3], n(r[4], 1)] for r in ret])}
<p>2018~2023년에는 해마다 <b>10곳 중 {drop_tens}곳꼴</b>이 다음 해에 빠졌어요.</p>
<h4>빠진 이유 (빠진 {n(sum(v for _, v in a['drop_reasons']))}건)</h4>{hbars([(k, v) for k, v in a['drop_reasons']], '건')}""",
        "<p>지금 명단에 남은 회사만 봐서, 그사이 사라진 회사는 빠져 있어요(생존 편향). 2024년에 빠진 비율이 뚝 떨어진 건 638곳을 2025년 숫자로 뽑았기 때문이라 다른 해와 바로 견주지 않아요.</p>",
        "<p>올해 대상이어도 '내년에도 될까?'를 미리 확인해야 해요. 빠진 이유 1위가 배당 감소였으니, 회사의 배당이 줄 조짐이 있는지가 가장 중요한 점검거리예요.</p>", outs)

    # 5장
    cap = a["capacity"]
    ch5 = chapter(5, "내년에도 넘으려면? <em>절반은 올해만큼이면 돼요</em>",
        "<p>2027년에 받는 배당도 분리과세를 받으려면 회사가 2026 사업연도 몫으로 최소 얼마를 줘야 하는지 알아야 해요. 그 금액을 2025년 배당과 견주고, 그만큼 줄 현금이 있는지도 봤어요.</p>",
        f"""<ul><li><b>최소 필요 배당</b>: 2026 순이익이 2025년과 같다고 놓고, 가목·나목·제2호를 모두 맞추는 가장 작은 2026 배당을 계산했어요(source/core/min_dividend.py → core.core_min_dividend_2027, 시나리오 '2025년 (기본)'). 계산할 수 있었던 곳 {n(min_n)}곳.</li>
<li><b>재무 여력</b> = 2025 잉여현금흐름(영업현금흐름 − 설비투자) ÷ 2027 최소 필요 배당(source/core/capacity.py → core.core_capacity_2025.cover_x). {n(cap['n'])}곳, {escape(', '.join(f'{k} {v}곳' for k, v in cap['other'].items()))}은 뺐어요.</li></ul>""",
        f"""<h4>2027 최소 필요 배당 ÷ 2025 배당</h4>{hbars([(k, v) for k, v in a['min_ratio']])}
<p>{n(min_n)}곳 중 <b>{n(min_ok)}곳({n(min_ok / min_n * 100, 1)}%)</b>은 2025년만큼만 배당해도 돼요.</p>
<h4>재무 여력 (가운데 값 {cap['median']}배)</h4>{hbars([(k, v) for k, v in cap['bins']], color=COIN_DEEP)}
<p>남은 현금이 최소 배당의 몇 배인지 보면 한가운데 회사는 <b>{cap['median']}배</b>예요. 1배보다 작으면 그해 번 현금만으로는 모자란다는 뜻이에요.</p>""",
        "<p>순이익이 그대로라는 가정이 커요. 이익이 늘면 필요한 배당도 늘어요. 재무 여력은 요건 판정과 상관없는 참고값이고, 금융업은 잉여현금흐름 개념이 맞지 않아 뺐어요.</p>",
        "<p>절반쯤은 배당을 지금만큼만 유지하면 내년에도 요건을 채워요. 나머지는 배당을 더 늘려야 하니, 남은 현금이 넉넉한지 함께 봐야 해요.</p>", outs)

    # 6장
    curves = a["event"]["curves"]
    ch6 = chapter(6, "공시 뒤, 주가는 <em>어떻게 움직였을까요?</em>",
        "<p>배당을 늘린다는 공시가 주가에 좋은 신호였는지 알면, 투자자가 공시를 보고 판단할 때 기준이 생겨요. 배당뿐 아니라 증자·감자·분할 같은 자본 변동 공시도 같은 방법으로 봤어요.</p>",
        f"""<ul><li><b>초과수익률</b> = 종목 수익률 − 시장지수 수익률(시장조정). 공시 뒤 주가 움직임에서 그날 시장 전체 움직임을 뺀 값이에요. 기준 화면: {escape(a['event']['basis'])}.</li>
<li><b>사건</b>: 배당 결정 공시(raw.dividend_decision)와 자본 변동 공시(raw.dart_capital_event, raw.dart_split_merge), 2025년까지. 주가 raw.krx_price_daily, 지수 raw.krx_market_index.</li>
<li><b>우연인지</b>: Kolari–Pynnönen 보정 BMP 검정 → 모든 조건에 걸쳐 Benjamini–Hochberg 보정 q. 팀이 미리 정한 주 분석은 시장모형 기준이에요. source/core/event_study.py, source/scripts/event_methods.py → data/processed/analysis/event_methods.json, report/분석/이벤트스터디_방법별_결과.md.</li>
<li><b>요인 비교</b>: 시장모형 60거래일 회귀에 배당 증가·배당수익률·회사 규모·연도를 함께 넣었어요({n(ev['methods']['n_regression_60'])}건, 공시일로 묶은 표준오차).</li></ul>""",
        f"""<div class='grid8' style='grid-template-columns: 1fr 1fr'>{''.join(f"<div class='card'>{curve(v, title=f'{k} ({n(v[0][1])}건)')}</div>" for k, v in curves.items())}</div>
<p class='small'>굵은 선 = 가운데 값, 옅은 띠 = 가운데 절반(25~75%). 모든 조건 {len(ev['summary'])}개의 결과는 부록 A에 있어요.</p>
<h4>여러 요인을 함께 넣은 회귀 (60거래일)</h4>
{table(['변수', '계수(%p)', '표준오차', 'p'], [[r['변수'], r['계수(%p)'], r['군집 표준오차'], r['p']] for r in reg], sig_col=3)}
<p>배당을 늘렸다는 사실만으로는 차이가 뚜렷하지 않았어요(p = {pv(c_up['p'])}). 대신 <b>배당수익률(주가 대비 배당)이 1%p 높으면</b> 공시 뒤 60거래일 초과수익률이 {pp(c_yield['계수(%p)'], 2)} 높았어요(p = {pv(c_yield['p'])}). 회사 규모(시가총액 로그)가 1 클수록은 {pp(c_size['계수(%p)'], 2)}(p = {pv(c_size['p'])})였어요.</p>""",
        "<p>이 계산은 '공시가 없었다면 주가가 평소처럼 시장을 따라 움직였을 것'이라고 놓고 해요. 같은 때 다른 공시(실적 등)가 섞일 수 있고, 인과관계가 아니에요. 사례 10건 미만인 조건은 표시하지 않았어요. 주가·지수는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가예요. 주 분석 조건에서는 시장모형과 시장조정 두 방법 모두 q가 0.05보다 작아 결론이 같아요.</p>",
        "<p>'배당을 늘린다'는 소식 자체보다 '주가에 비해 배당이 얼마나 많은가'가 공시 뒤 주가와 더 관련 있었어요. 함께 나타났다는 뜻이지, 배당수익률 때문에 주가가 올랐다는 뜻은 아니에요.</p>", outs)

    # 7장
    kinds = a["holder"]["notes"]["kinds"]
    ch7 = chapter(7, "기준선 근처 회사는 <em>개인 최대주주</em>가 조금 더 많아요",
        "<p>분리과세 혜택은 배당을 받는 개인에게 가요. 최대주주가 개인이면 지분이 많은 만큼 배당도 많이 받으니, 배당을 기준선에 맞출 이유가 더 커요. 그런 회사가 정말 기준선 근처에 많은지 견줘 봤어요.</p>",
        f"""<ul><li><b>원천</b>: 2025 사업보고서 최대주주 현황(OpenDART hyslrSttus) → raw.dart_major_holder → core.core_major_holder.</li>
<li><b>지분율</b> = 최대주주와 가족·계열사(특수관계인)의 보통주 기말 지분율 합계('계' 행 우선). <b>개인/법인</b>은 이름·관계 칸의 글자 규칙으로만 나눠요(source/core/major_holder.py). 2025: 개인 {kinds.get('개인')} · 법인 {kinds.get('법인')} · 판단 불가 {kinds.get('판단 불가')}곳.</li>
<li><b>기준선 근처</b> = 2025 배당성향이 25%·40%에서, 또는 증가율이 10%에서 위아래 {a['holder']['near_pp']}%p 안(source/core/holder_analysis.py).</li></ul>""",
        table(['묶음', '회사 수', '지분율 가운데 값(%)', '가운데 절반(%)', '개인 최대주주(%)'],
              [[r['묶음'], r['회사 수'], r['중앙값'], f"{r['1사분위']}~{r['3사분위']}", r['개인 최대주주(%)']] for r in a["holder"]["table"]])
        + f"<p>최대주주가 개인인 회사는 기준선 근처가 <b>{h_near['개인 최대주주(%)']}%</b>, 나머지가 <b>{h_far['개인 최대주주(%)']}%</b>예요. 지분율 가운데 값은 {h_near['중앙값']}%와 {h_far['중앙값']}%로 비슷해요.</p>",
        "<p>두 비율이 몇 %p 다른지만 본 단순 비교이고, 그 차이가 우연인지 검정하지 않았어요. 개인/법인 구분은 이름 규칙이라 5자 이상 이름이나 외국인은 '판단 불가'가 돼요. 지분율에는 계열 법인 몫도 섞여 있어요. 한 회사가 여러 기준선 근처에 함께 들어갈 수 있어요.</p>",
        "<p>기준선 근처에 개인 최대주주 회사가 조금 더 많은 건 '세금을 아끼는 사람이 배당을 정한다'는 생각과 어긋나지 않아요. 다만 이 장만으로는 그렇다고 말할 수 없어서, 9장에서 업종 전체로 다시 봤어요.</p>", outs)

    # 8장
    yc = mc["year_cols"]
    yname = {"payer_share": "배당 회사 비율(%)", "dps_up_share": "DPS 올린 회사(%)", "yield_median": "시가배당률 중앙값(%)", "base_rate": "기준금리(%)",
             "ktb3y": "국고채 3년(%)", "usdkrw": "원/달러", "gdp_growth": "GDP 성장률(%)", "cpi_growth": "물가상승률(%)", "unemployment": "실업률(%)",
             "current_account_chg": "경상수지 증감(백만$)"}
    terc = {r[0]: r for r in bh["series"]["exposure"]["tercile_up"]}
    tcut = {r[0]: r for r in bh["series"]["exposure"]["tercile_cut"]}
    ch8 = chapter(8, "경기가 좋아지면 배당도 늘었을까요? <em>뚜렷하지 않았어요</em>",
        "<p>'경기가 좋으면 배당도 늘겠지'라는 생각이 맞는지 알고 싶었어요. 맞다면 투자자는 경기 전망으로 배당을 짐작할 수 있어요. 먼저 해마다 견줬고, 해가 9개뿐이라는 한계를 넘으려고 회사마다 금리·환율 영향을 얼마나 크게 받는지(노출도)로 다시 봤어요. 경기 대신 회사 자기 이익과도 견줬어요.</p>",
        f"""<ul><li><b>경기</b>: 한국은행 ECOS(raw.ecos_macro) 기준금리·국고채 3년·원/달러·실질 GDP·물가·실업률·고용률·경상수지를 달력 연도로 모았어요. 경기를 본 시점 3가지: {escape(' / '.join(lag_name.values()))}.</li>
<li><b>배당</b>: core.v_dividend_year_verified(검토 확정 값 우선), 시가배당률 raw.dart_dividend_item. 배당 지표 {len(dn)}개.</li>
<li><b>상관</b>: 두 값이 얼마나 함께 움직이는지를 −1~1로 나타낸 값이에요. Spearman 순위 상관을 쓰고, p값은 연도를 섞는 순열검정으로 구했어요. source/core/macro_dividend.py → core.core_macro_dividend_corr, report/분석/배당_거시지표_상관_결과.md.</li>
<li><b>회사 이익과 배당</b>: 회사·연도마다 순이익 증감과 주당배당금 증감의 상관({pf['years'][0]}~{pf['years'][1] - 1}년, {pf['years'][1]}년 뺌). source/scripts/analyze_profit_dividend.py → data/processed/analysis/profit_dividend.json.</li>
<li><b>노출도 분석</b>: 회사×연도 자료(우리 638사 + 대조군, partner.v_panel). 금리 노출 = 전년 말 차입금 ÷ 자산, 환율 노출 = 전년 외화환산 이익·손실·해외사업장 환산차이 절댓값 ÷ 자산(partner.fs_line). 그해 모든 회사가 함께 겪은 일, 회사마다 원래 배당하던 습관, 이익 변화(Lintner 통제)를 뺀 회귀예요. 연도 섞기 순열 2,000번, Holm 보정. source/core/exposure_dividend.py → core.core_behavior_fit, report/분석/배당_노출도_분석_결과.md.</li></ul>""",
        f"""<div class='facts'><div><dt>변화끼리 본 짝 중 p &lt; 0.05</dt><dd>{len(diff_sig)} / {len(diff)}</dd><dt>아무 관계가 없어도 우연히 나올 만한 수 {n(len(diff) * 0.05, 1)}</dt></div>
<div><dt>검사 횟수만큼 보정(BH)하면</dt><dd>{bh_k}짝</dd></div><div><dt>노출도 주 검정 2개 보정 p</dt><dd>{n(rate_f['p_holm'], 2)} · {n(fx_f['p_holm'], 2)}</dd></div></div>
<p>경기와 배당을 짝지어 본 {len(diff)}쌍 중 함께 움직인 것처럼 보인 짝은 <b>{len(diff_sig)}쌍</b>뿐이었어요. 아무 관계가 없어도 {len(diff)}쌍을 보면 {round(len(diff) * 0.05)}쌍쯤은 우연히 이렇게 나와요.</p>
<h4>회사마다 보면, 배당은 그 회사의 이익을 따라 움직였어요</h4>
<div class='facts' style='grid-template-columns: 1fr 1fr'><div><dt>{escape(pf_up[0])}</dt><dd>{n(pf_up[2], 1)}%</dd><dt>가 주당배당금을 올렸어요 · 줄인 회사 {n(pf_up[3], 1)}% · 회사·연도 {n(pf_up[1])}개</dt></div>
<div><dt>{escape(pf_down[0])}</dt><dd>{n(pf_down[2], 1)}%</dd><dt>가 주당배당금을 올렸어요 · 줄인 회사 {n(pf_down[3], 1)}% · 회사·연도 {n(pf_down[1])}개</dt></div></div>
<p>순이익 증감과 주당배당금 증감의 상관은 <b>{pf_r['r']:.2f}</b>로, 경기 지표와 견준 값(가장 커도 {macro_firm_max:.2f})보다 훨씬 컸어요. 1년 전 이익 변화와는 거의 관계가 없었어요(상관 {pf_prev['r']:.2f}). {pf['years'][1]}년을 넣어도 상관 {pf['firm'][0]['r']:.2f}로 결론이 같아요.</p>
<h4>연도별 배당·경기 값 (core.core_macro_dividend_year)</h4>
{table(['사업연도', *[yname.get(c, c) for c in yc]], [[str(r[0]), *[n(v, 1) if v is not None and abs(v) < 1000 else n(v) for v in r[1:]]] for r in mc['years']])}
<h4>변화끼리 p &lt; 0.05였던 {len(diff_sig)}짝</h4>
{table(['시점', '배당 지표', '경기 지표', '상관', 'p'], [[lag_name[c[0]].split(' (')[0], dn.get(c[2], c[2]), mn.get(c[3], c[3]), c[4], c[5]] for c in diff_sig], left=3)}
<h4>회사마다 금리·환율 영향 크기로 본 주 검정 (배당 방향 점수: 줄임 −1 · 그대로 0 · 올림 +1)</h4>
{table(['검정', '계수', '95% 범위', '순열 p', 'Holm 보정 p', '회사'], [[x['name'], x['coef'], f"{n(x['low'], 3)} ~ {n(x['high'], 3)}", x['p_perm'], x['p_holm'], x['n_firms']] for x in (rate_f, fx_f)], sig_col=4)}
<p>금리·환율 영향을 크게 받는 회사도 배당을 {'다르게 정했어요' if sig(rate_f['p_holm']) or sig(fx_f['p_holm']) else '다르게 정하지 않았어요'}(보정 p {n(rate_f['p_holm'], 2)} · {n(fx_f['p_holm'], 2)}).</p>
<h4>영향을 크게 받는 3분의 1과 적게 받는 3분의 1의 단순 비율</h4>
{table(['경기', '회사', '올린 비율(%)', '줄인 비율(%)', '회사·연도'], [[k.split('|')[0] + ' ' + k.split('|')[1], k.split('|')[2], n(terc[k][2], 1), n(tcut[k][2], 1), terc[k][5]] for k in sorted(terc)], left=2)}""",
        "<p>사업연도가 2017~2025 9개뿐이라 한 해(2020 코로나, 2025)가 결과를 크게 흔들어요. 상관 분석은 638곳 명단으로만 봐서 사라진 회사는 빠져 있어요. 배당총액은 가장 큰 1곳의 몫이 커서 그 1곳을 뺀 값도 봤어요. 노출도는 계정 이름으로 모은 대략적인 값이고, 수출 비중은 자료가 없어 쓰지 못했어요. '관계가 없다'고 증명한 게 아니라 '이 자료로는 우연과 구별되는 관계를 찾지 못했다'는 뜻이에요. 이익과 배당도 함께 움직였다는 뜻이지, 이익이 배당을 정했다고 단정하지 않아요.</p>",
        "<p>경기 전망만으로 배당을 짐작하기는 어려웠어요. 배당은 경기보다 그해 그 회사가 번 돈을 더 따라갔으니, 투자자는 경기 뉴스보다 회사 실적을 먼저 봐야 해요.</p>", outs)

    # 9장
    es_h = [[r[1], r[2] * 100, r[3] * 100, r[4] * 100] for r in bh["series"]["policy"]["es_holder"]]
    es_c = [[r[1], r[2] * 100, r[3] * 100, r[4] * 100] for r in bh["series"]["policy"]["es_close"]]
    rate_h = bh["series"]["policy"]["rate_holder"]
    yrs = sorted({r[1] for r in rate_h})
    rh = lambda y, lab: next((r for r in rate_h if r[1] == y and r[0] == lab), None)
    es25 = next(r[1] for r in es_h if r[0] == 2025)
    owner_pre = [rh(y, '개인 최대주주 회사')[2] for y in yrs if y < 2025]
    ch9 = chapter(9, "배당소득 분리과세 뒤, 누가 배당을 더 늘렸을까요? <em>세금을 가장 많이 아끼는 회사</em>",
        "<p>8장에서 경기는 배당을 움직이지 못했어요. 그럼 세금 제도는 어땠을까요? 분리과세는 2025 사업연도 숫자로 요건을 따져서 <b>2025년 배당이 회사들이 제도를 알고 정한 첫 배당</b>이에요. 같은 해 경기는 모든 회사가 함께 겪으니, 혜택을 크게 받는 무리와 나머지를 견주면 경기 몫을 빼고 제도 쪽 몫을 볼 수 있어요. 이렇게 '평소 차이'와 '제도 뒤 차이'를 다시 빼서 보는 방법을 이중차분이라고 해요.</p>",
        f"""<ul><li><b>제도 일정</b>: 2024-07-25 정부안의 주주환원 촉진세제 → 2024-12-10 국회 의결에서 빠짐(국회예산정책처). 2025-07-31 세제개편안에 고배당기업 분리과세 → 2025-12-02 국회 통과(14·20·25·30%) → 2026-01-01 시행(2028년까지).</li>
<li><b>회사 범위</b>: 제조·도소매·건설·부동산임대 상장사 전체(우리 435곳 + 대조군, partner.company). 우리 고배당기업은 2025 배당 결과로 뽑혀서 따로 떼지 않고 한 표본으로만 봐요.</li>
<li><b>개인 최대주주 회사</b> = 2024 사업연도 최대주주가 개인이고 최대주주와 특수관계인 보통주 지분이 30% 이상(partner.major_holder, source/core/major_holder.py 규칙). 최대주주가 지주회사 같은 법인이면 배당이 그 법인을 먼저 거쳐 개인 최대주주 혜택이 줄어서 '나머지'에 넣었어요.</li>
<li><b>기준선 거리</b> = 해마다 전년 숫자로 '올해 요건을 맞추려면 배당을 몇 % 늘려야 하나'(순이익 그대로 가정). 50% 이하면 가까움.</li>
<li><b>결과 값</b> = 배당총액을 10% 이상 늘렸나. 회사·연도 효과, Lintner 통제, 금리·환율 노출 × 경기, 밸류업 공시(partner.filing, 2025-07-31 전)를 넣은 회귀예요. 무리 섞기 순열 1,000번, 미리 정한 주 검정 2개에 Holm 보정. source/core/policy_did.py → core.core_behavior_fit·series, report/분석/배당_제도효과_분석_결과.md.</li>
<li><b>제도 전 모습 점검</b>: 같은 자료·같은 모형으로 제도 전 계수와 추세를 다시 계산했어요(source/scripts/check_did_pretrend.py compute, 회사·연도 {n(pt['n'])}개, 회사 {n(pt['firms'])}곳).</li></ul>""",
        f"""<div class='facts' style='grid-template-columns: 1fr 1fr'><div><dt>개인 최대주주 회사 ({n(own_f['n_treated'])}곳)</dt><dd>{pp(own_f['coef'] * 100)}</dd><dt>보정 p {n(own_f['p_holm'], 3)} · {'우연으로 보기 어려워요' if sig(own_f['p_holm']) else '우연과 구별되지 않아요'}</dt></div>
<div><dt>기준선 가까이 있던 회사 ({n(close_f['n_treated'])}곳)</dt><dd>{pp(close_f['coef'] * 100)}</dd><dt>보정 p {n(close_f['p_holm'], 3)} · {'우연으로 보기 어려워요' if sig(close_f['p_holm']) else '우연과 구별되지 않아요'}</dt></div></div>
<p>개인 최대주주 회사는 2025년에 배당을 10% 이상 늘린 비율이 평소보다 <b>{pp(own_f['coef'] * 100)}</b> 더 올랐어요. 기준선 가까이 있던 회사는 뚜렷한 차이가 없었어요.</p>
<div class='card'><h4>개인 최대주주 회사 − 나머지, 해마다 (2023 = 0, 세로 막대 = 95% 범위)</h4>{coef_chart(es_h)}</div>
<p>2025년 값은 {pp(es25)}로 가장 커요. 제도가 다른 해에 생겼다고 치고 같은 계산을 하면 {pp(min(x['coef'] for x in placebo) * 100)} ~ {pp(max(x['coef'] for x in placebo) * 100)}가 나와요. 다만 가짜 해 {len(placebo)}번 중 {pl_sig}번은 우연으로 보기 어려운 값(p &lt; 0.05)이 나왔어요. 해마다 이 정도는 흔들릴 수 있다는 뜻이라 2025년 결과도 조심해서 읽어야 해요.</p>
<h4>제도 전 모습 점검 (평행추세)</h4>
<ul><li>단순 비율 차이(개인 최대주주 회사 − 나머지)는 2018~2024년에 {pp(min(pre_gap))} ~ {pp(max(pre_gap))}였고{'(해마다 개인 최대주주 회사가 낮았어요)' if max(pre_gap) < 0 else ''}, 2025년에는 {pp(pt['gap'][2025])}였어요.</li>
<li>제도 전 여섯 해 계수가 모두 0이라는 가정을 한꺼번에 검정하면 p = {pv(pt['wald_p'])}예요.</li>
<li>제도 전에 개인 최대주주 회사 쪽이 다른 속도로 움직인 흔적도 뚜렷하지 않았어요(해마다 {pp(pt['slope'])}, p = {pv(pt['slope_p'])}).</li>
<li>이 기울기를 빼고 다시 계산해도 2025년 차이는 <b>{pp(pt['did_trend']['coef'])}</b>(p = {pv(pt['did_trend']['p'])})로 남아요. 기울기를 빼지 않으면 {pp(pt['did_plain']['coef'])}로 위 카드와 같아요.</li></ul>
<h4>배당을 10% 이상 늘린 회사 비율 (단순 비율)</h4>
{table(['사업연도', '개인 최대주주 회사(%)', '다른 상장사(%)', '차이'], [[str(y), n(rh(y, '개인 최대주주 회사')[2], 1), n(rh(y, '나머지 회사')[2], 1), pp(rh(y, '개인 최대주주 회사')[2] - rh(y, '나머지 회사')[2])] for y in yrs])}
<h4>기준선 가까움 − 멂, 해마다</h4>
{table(['사업연도', '계수(%p)', '95% 범위(%p)'], [[str(r[0]), n(r[1], 1), f"{n(r[2], 1)} ~ {n(r[3], 1)}"] for r in es_c])}""",
        f"""<p><b>같은 해 상법 개정과 가를 수 없어요.</b> 2025년에 이사가 주주 전체의 이익을 살피도록 상법도 바뀌어서, 개인 최대주주가 직접 지배하는 회사일수록 이 압력도 컸을 수 있어요. 밸류업 정책, 주가 상승, 실적 변화도 같은 해에 있었어요. 이익 변화와 2025-07-31 전 밸류업 공시는 맞춰 놓았지만, 그 뒤 공시나 상법 압력은 빼지 못했어요.</p>
<p>'다른 상장사'에는 최대주주가 법인인 회사, 개인이지만 지분이 30%보다 적은 회사가 섞여 있고, 그 회사의 개인 주주도 분리과세 혜택을 받아요. 그래서 이 값은 제도 전체의 효과가 아니라 '개인 최대주주 회사가 더 움직인 몫'에 가까워요. 제도 뒤 연도가 2025 하나뿐이고, 4개 업종 상장사만 봤어요. 지분 30%에는 계열 법인 몫도 섞여 있어요. 제도 전 흔적이 뚜렷하지 않다는 것이 평행추세가 맞다는 증명은 아니고, 2020년처럼 한 해에 크게 흔들린 적도 있어요. 배당을 몇 원 더 줬는지는 이 결과로 알 수 없어요.</p>""",
        f"<p>분리과세로 세금을 가장 많이 아끼는 사람은 배당을 많이 받는 개인 최대주주예요. 개인 최대주주 회사는 제도 전 해마다 평균 {n(sum(owner_pre) / len(owner_pre), 1)}%가 배당을 10% 이상 늘렸으니 {pp(own_f['coef'] * 100)}는 작지 않은 차이예요(개인 최대주주 회사 {n(own_f['n_treated'])}곳으로 치면 약 {round(own_f['coef'] * own_f['n_treated'])}곳). 이 결과는 '2025년에 개인 최대주주 회사가 배당을 늘린 비율이 평소보다 더 올랐다'는 데까지만 말해요. 제도 때문이라고 단정하지 않아요.</p>", outs)

    # 10장
    trend = cc["trend"]
    inc = cc["increase"]
    car = cc["car"]
    ch10 = chapter(10, "배당을 덜 하는 회사들과 견줘 보면, <em>차이가 또렷해요</em>",
        "<p>고배당기업만 보면 '원래 그런 회사인지, 제도 때문인지' 알 수 없어요. 같은 업종에서 고배당기업이 아닌 상장사(대조군)와 같은 방법으로 견줘야 무엇이 다른지 보여요.</p>",
        f"""<ul><li><b>대조군</b>: 제조·도소매·건설·부동산임대 코스피·코스닥 상장사 {n(sim['control_n'])}곳(4조 협조 자료, partner.*). 우리와 겹치는 435곳은 우리가 확인한 값만 써요. 무배당은 배당 표에 '-'로 적힌 해를 0으로 셌어요.</li>
<li><b>요건 시뮬레이션</b>: 판정 코드(source/core/judgement.py)에 배당소득 대신 현금배당총액을 넣었어요. 이 방법은 고배당기업에서 실제 판정과 {n(sim['approx_agree'])}/{n(sim['approx_n'])}곳({n(sim['approx_agree'] / sim['approx_n'] * 100, 1)}%) 같았어요.</li>
<li><b>리츠 제외</b>: 조세특례제한법 제104조의27 ①1호 단서 → 시행령 제104조의24 ② → 법인세법 제51조의2 ①4호(위탁관리·기업구조조정 부동산투자회사). 회사 종류는 각 사업보고서로 확인했어요.</li>
<li><b>원천과 코드</b>: partner.v_panel, partner.krx_price_daily, partner.analysis_result. source/scripts/analyze_panel.py → report/분석/대조군_비교분석_20261102.md.</li></ul>""",
        f"""<h4>2025 업종별 가운데 값</h4>
{table(['업종', '무리', '회사', '배당한 비율(%)', '배당성향(%)', 'ROE(%)', '부채비율(%)', '자본(억 원)'], [[r[0], r[1].replace('우리 638사', '고배당기업'), r[2], r[3], r[4], r[5], r[6], r[7]] for r in cc['industry_2025']], left=2)}
<div class='card'><h4>배당한 회사 비율(%)</h4>{lines([(r[0], r[1], r[3]) for r in trend], ('고배당기업', '대조군'))}</div>
<div class='card'><h4>배당을 10% 넘게 늘린 회사 비율(%)</h4>{lines([(r[0], r[2], r[4]) for r in inc], ('고배당기업', '대조군'), xlab=lambda y: f"{str(y - 1)[2:]}→{str(y)[2:]}")}</div>
<p>2024년까지는 해마다 두 무리 차이가 가장 커도 {n(inc_gap_max, 1)}%p였는데, 2025년에는 고배당기업 <b>{n(inc25[2], 1)}%</b>, 대조군 <b>{n(inc25[4], 1)}%</b>로 벌어졌어요.</p>
<div class='facts' style='grid-template-columns: repeat(4, 1fr)'><div><dt>대조군 상장사</dt><dd>{n(sim['control_n'])}곳</dd></div><div><dt>배당 숫자로 요건 맞춤</dt><dd>{sim['met']}곳</dd></div><div><dt>법으로 빠지는 리츠</dt><dd>{sim['reit_excluded']}곳</dd></div><div><dt>될 수 있는 곳</dt><dd>{sim['eligible']}곳</dd></div></div>
{table(['업종', '요건 맞춤', '미충족', '보류', '리츠 제외'], [list(r) for r in sim['by_industry']])}
<h4>배당 결정 공시 뒤 시장 대비 초과수익률 (평균, %p)</h4>
{table(['창(거래일)', '공시', '무리', '건수', '평균', '가운데', 'p'], [[r[0], r[1], r[2].replace('우리 638사', '고배당기업'), r[3], r[4], r[5], r[6]] for r in car], left=0, sig_col=6)}""",
        "<p>가장 중요한 한계: 고배당기업은 2025년 숫자로 뽑혀서 '나중에 잘된 회사'가 들어 있어요. 그래서 두 무리의 차이를 배당의 효과로 읽으면 안 돼요(9장에서 업종 전체를 한 표본으로 따로 봤어요). 이 장의 가운데 값과 비율은 단순 비교이고, 우연인지 검정한 것은 주가 반응 표뿐이에요. 그 표의 p는 한 무리의 평균이 0과 다른지 본 t검정이고, 두 무리 사이의 차이를 검정한 것은 아니에요. 대조군은 사람 검토를 거치지 않았어요. 주가 반응은 1~4월 첫 배당 결정 공시만 봐서 6장과 방법이 달라요.</p>",
        f"<p>같은 업종 상장사 {n(sim['control_n'])}곳에 고배당 요건을 그대로 대어 보면 {sim['eligible']}곳만 남아요. 고배당기업은 같은 업종 안에서도 드문 회사이고, 2025년에 배당을 늘린 모습도 대조군과 뚜렷이 달랐어요.</p>", outs)

    # 11장
    ch11 = chapter(11, "이 숫자들, <em>믿어도 될까요?</em>",
        "<p>모든 분석은 공시 숫자를 옮겨 적은 데서 시작해요. 옮겨 적은 숫자가 원문과 같은지, 다르면 어떻게 처리했는지를 보여 줘야 앞 장들의 결과를 믿을 수 있어요.</p>",
        f"""<ul><li><b>코드 원문 대조</b>(core.core_source_verify): DB 숫자를 사업보고서·공시 원문에서 다시 찾아 비교했어요. <b>DART 재대조</b>(core.core_dart_verify): OpenDART 원문 문서로 한 번 더 비교했어요.</li>
<li><b>팀 검토</b>(core.core_review_value): 팀이 원문을 보고 확인·정정한 값이에요. 검토본 {escape(res.get('review_file', ''))}. 달랐던 칸의 처리는 source/scripts/verify_resolution.py → data/processed/analysis/verify_resolution.json.</li>
<li><b>밸류업 공시</b> raw.policy_filing·policy_document·policy_page_ocr, <b>주가</b> raw.krx_price_daily, <b>대조군</b> partner.company·financial_year·krx_price_daily.</li></ul>""",
        f"""<div class='facts'><div><dt>원문과 대조한 숫자 칸</dt><dd>{n(sum(sv.values()))}</dd><dt>일치 {n(sv.get('일치', 0))} ({n(sv_rate, 1)}%)</dt></div>
<div><dt>DART 원문 재대조</dt><dd>{n(sum(dv.values()))}</dd><dt>일치 {n(dv.get('일치', 0) + dv.get('일치(단위 반올림)', 0))}</dt></div>
<div><dt>팀이 원문 보고 검토한 값</dt><dd>{n(sum(rv.values()))}</dd><dt>확인완료 {n(rv.get('확인완료', 0))}</dt></div>
<div><dt>밸류업 공시 · 원본 파일 · OCR 쪽</dt><dd style='font-size:13pt'>{n(t['policy_filings'])} · {n(t['policy_documents'])} · {n(t['ocr_pages'])}</dd></div>
<div><dt>주가 줄 (고배당기업)</dt><dd>{n(t['price_rows'])}</dd></div><div><dt>공시 뒤 주가 계산 사례</dt><dd>{n(t['event_cases'])}</dd></div></div>
{table(['대조', '결과', '칸 수'], [['코드 원문 대조', k, v] for k, v in sv.items()] + [['DART 재대조', k, v] for k, v in dv.items()] + [['팀 검토', k, v] for k, v in rv.items()], left=2)}
<h4>달랐던 칸은 어떻게 됐나</h4>
{table(['대조', '처리', '칸 수'], [['코드 원문 대조', k, v] for k, v in res.get('source_verify', {}).get('detail', {}).items()] + [['DART 재대조', k, v] for k, v in res.get('dart_verify', {}).get('detail', {}).items()], left=2)}""",
        "<p>'확인불가'는 아직 못 푼 칸이 아니라 원문에 값이 없다는 확인이에요. 주가·지수는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가예요. 대조군 자료는 사람 검토를 거치지 않았어요.</p>",
        "<p>고배당기업 숫자는 공시 원문까지 거슬러 올라가 확인할 수 있어요. 원문과 다른 칸은 두 값을 나란히 남기고 팀이 다시 확인했으니, 앞 장의 숫자를 다시 셀 때도 같은 값이 나와요.</p>", outs)

    # 부록
    tests = {(x['공시 종류'], x['기준일'], x['창'], x['수익률']): x for x in ev['methods']['tests'] if x['모형'] == '시장조정'}
    ev_rows = []
    for x in sorted(ev["summary"], key=lambda x: (x["kind"], x["window"], x["basis"], x["ret"], x["sample"])):
        tq = tests.get((x["kind"], x["basis"], x["window"], x["ret"])) if x["sample"] == "자본 변동 겹침 제외" else None
        ev_rows.append([x["kind"], x["basis"], x["ret"], x["sample"], x["window"], x["n"], x["median"], f"{n(x['p25'], 2)} ~ {n(x['p75'], 2)}",
                        tq["KP p BH 보정 q"] if tq and tq.get("KP p BH 보정 q") is not None else "–"])
    appA = (f"<section class='page'><span class='ch-no'>부록 A</span><h2>6장 공시 뒤 주가: <em>모든 조건 {len(ev_rows)}개</em></h2>"
            "<p class='small'>화면에서 고를 수 있는 공시 종류 × 기준일 × 수익률 × 표본 × 창의 모든 조합이에요. 가운데 값·범위는 시장조정 초과수익률(%p), q는 시장조정 KP 보정 BMP 검정을 모든 조건에 걸쳐 BH 보정한 값이에요(검정은 '자본 변동 겹침 제외' 표본으로만). 진한 파랑 = q &lt; 0.05. 출처 core.core_event_summary(period = '2025년까지'), data/processed/analysis/event_methods.json.</p>"
            + table(["공시 종류", "기준일", "수익률", "표본", "창", "사례", "가운데(%p)", "가운데 절반(%p)", "q"], ev_rows, left=4, sig_col=8)
            + "<h3>방법별 검정 전체 (시장모형·시장조정)</h3><p class='small'>공시일 군집 t, KP 보정 BMP, 일반화 부호, 윌콕슨 p와 BH 보정 q. 출처 data/processed/analysis/event_methods.json(source/scripts/event_methods.py).</p>"
            + table(["공시 종류", "기준일", "창", "모형", "수익률", "사례", "평균", "군집 t p", "KP p", "부호 p", "윌콕슨 p", "q"],
                    [[x['공시 종류'], x['기준일'], x['창'], x['모형'], x['수익률'], x['사례'], x['평균(%p)'], x['공시일 군집 t p'], x['KP 보정 BMP p'], x['일반화 부호 p'], x['윌콕슨 p'], x['KP p BH 보정 q']]
                     for x in sorted(ev['methods']['tests'], key=lambda x: (x['공시 종류'], x['기준일'], x['창'], x['모형'], x['수익률']))], left=2, sig_col=11)
            + "</section>")

    kind_name = {"level": "그 해 값끼리", "diff": "전년 대비 변화끼리", "panel": "회사마다", "panel_ex2025": "회사마다 (2025 빼고)"}
    parts = []
    for lag, _ in mc["lags"]:
        for kind in ("level", "diff", "panel", "panel_ex2025"):
            rows = [c for c in mc["corr"] if c[0] == lag and c[1] == kind]
            if not rows:
                continue
            parts.append(f"<h3>{escape(lag_name[lag])} · {kind_name[kind]} ({len(rows)}칸)</h3>"
                         + table(["배당 지표", "경기 지표", "상관", "p", "연도 수", "회사·연도"],
                                 [[dn.get(c[2], c[2]), mn.get(c[3], c[3]), c[4], c[5], int(c[6]) if c[6] is not None else "–", int(c[7]) if c[7] is not None else "–"] for c in rows], left=2, sig_col=3))
    appB = (f"<section class='page'><span class='ch-no'>부록 B</span><h2>8장 경기와 배당: <em>상관 {len(mc['corr'])}칸 전부</em></h2>"
            f"<p class='small'>시차 3 × 보는 법 4 × 배당 지표 × 경기 지표. Spearman 순위 상관과 순열검정 p(진한 파랑 = p &lt; 0.05, 보정 전). '회사마다'는 회사·연도 행으로 셌고 연도 단위로 섞었어요. 출처 core.core_macro_dividend_corr(계산일 {mc['built_at']}).</p>"
            + "".join(parts) + "</section>")

    role_name = {"primary": "주 검정", "robust": "보조", "placebo": "위약·가짜 제도 해"}
    beh = []
    for k, title in (("exposure", "금리·환율 노출도 (8장)"), ("policy", "분리과세 이중차분 (9장)")):
        rows = sorted(bh["fits"][k], key=lambda x: (["primary", "robust", "placebo"].index(x["role"]), x["name"]))
        beh.append(f"<h3>{title}</h3>" + table(["역할", "검정", "계수", "95% 범위", "회사 묶음 p", "순열 p", "Holm p", "회사·연도", "회사"],
                   [[role_name[x['role']], x['name'], x['coef'], f"{n(x['low'], 3)} ~ {n(x['high'], 3)}", x['p_cluster'], x['p_perm'] if x['p_perm'] is not None else "–",
                     x['p_holm'] if x['p_holm'] is not None else "–", x['n'], x['n_firms']] for x in rows], left=2, sig_col=6))
    appC = (f"<section class='page'><span class='ch-no'>부록 C</span><h2>8·9장 회사 행동 분석: <em>검정 {sum(len(v) for v in bh['fits'].values())}개 전부</em></h2>"
            "<p class='small'>노출도 계수는 배당 방향 점수(−1/0/+1) 단위, 제도 계수는 '배당 10% 이상 증가' 비율(0~1, ×100 = %p). 주판단은 순열 p와 Holm 보정 p(진한 파랑 = Holm p &lt; 0.05). 출처 core.core_behavior_fit.</p>"
            + "".join(beh) + "</section>")

    grid_rows = []
    for y, g in sorted(mv["grid"].items(), key=lambda kv: int(kv[0])):
        for i, lab in enumerate(["증가 10% 이상", "증가 0~10%", "감소"]):
            grid_rows.append([str(y), lab, *g[i]])
    appD = ("<section class='page'><span class='ch-no'>부록 D</span><h2>2·3장 <em>구간별 회사 수 전부</em></h2>"
            "<h3>2025 배당성향 1%p 구간 (흑자)</h3>" + table(["구간(%)", "회사 수"] * 2, [[*pay_rows[i], *pay_rows[i + 25]] for i in range(25)], left=0)
            + "<h3>2025 배당 증가율 1%p 구간</h3>" + table(["구간(%)", "회사 수"] * 2, [[*gro_rows[i], *gro_rows[i + 20]] for i in range(20)], left=0)
            + "<h3>3장 해마다 9칸</h3>" + table(["사업연도", "증가율 줄", "배당성향 25% 미만", "25~40%", "40% 이상"], grid_rows, left=2)
            + "</section>")

    appE = ("<section class='page'><span class='ch-no'>부록 E</span><h2>10장 대조군 비교 <em>표 전부</em></h2>"
            + "<h3>해마다 배당한 회사 비율·배당성향 가운데 값</h3>" + table(["연도", "고배당기업 배당한 비율", "고배당기업 배당성향", "대조군 배당한 비율", "대조군 배당성향"], [[str(r[0]), *r[1:]] for r in cc["trend"]], left=0)
            + "<h3>배당을 10% 넘게 늘린 회사</h3>" + table(["연도", "고배당기업 회사", "고배당기업 %", "대조군 회사", "대조군 %"], [[str(r[0]), *r[1:]] for r in cc["increase"]], left=0)
            + "<h3>해마다 시장 대비 수익률</h3><p class='small'>해마다 말 종가 기준 1년 수익률(%)의 가운데 값. '초과'는 종목 수익률 − 소속 시장지수 수익률. 출처 source/scripts/analyze_panel.py returns 표.</p>"
            + table(["연도", "고배당기업 회사", "수익률", "초과", "대조군 회사", "수익률", "초과", "코스피", "코스닥"], [[str(r[0]), *r[1:]] for r in cc["returns"]], left=0)
            + "<h3>업종별 최대주주 지분</h3>" + table(["업종", "무리", "회사", "가운데(%)", "가운데 절반(%)", "개인 최대주주(%)"],
                [[h['industry'], h['group'].replace('우리 638사', '고배당기업'), h['n'], h['median'], f"{h['p25']}~{h['p75']}", h['person_pct']] for h in cc['holder']], left=2)
            + "</section>")

    checks_all = "".join(f"<h4>{o.check.ch}장 · {escape(o.check.what)} · {'<span class=ok>✓ 같음</span>' if o.same else '<span class=no>✗ 다름</span>'}</h4>" for o in outs)
    appF = ("<section class='page'><span class='ch-no'>부록 F</span><h2>다시 계산하는 <em>명령</em></h2>"
            "<p>DB를 받은 뒤(report/실행안내/팀원_실행_안내.md) 아래 순서로 돌리면 이 보고서의 숫자를 처음부터 다시 만들 수 있어요.</p>"
            "<pre>.venv/bin/python -m scripts.build_core             # 확정 표 (core.core_dividend_year 등)\n"
            ".venv/bin/python -m scripts.build_judgement        # 1장 판정 (core.core_judgement_2026)\n"
            ".venv/bin/python -m scripts.build_capacity         # 5장 재무 여력 (core.core_capacity_2025)\n"
            ".venv/bin/python -m scripts.build_events           # 6장 공시 뒤 주가 (core.core_event_*)\n"
            ".venv/bin/python -m scripts.event_methods          # 6장 방법별 검정 (data/processed/analysis/event_methods.json)\n"
            ".venv/bin/python -m scripts.analyze_macro_dividend # 8장 경기 상관 (core.core_macro_dividend_*)\n"
            ".venv/bin/python -m scripts.analyze_exposure_dividend  # 8장 노출도 (core.core_behavior_*)\n"
            ".venv/bin/python -m scripts.analyze_policy_did     # 9장 제도 효과 (core.core_behavior_*)\n"
            ".venv/bin/python -m scripts.analyze_panel          # 10장 대조군 (partner.analysis_result)\n"
            ".venv/bin/python -m scripts.report_story_pdf       # 이 보고서</pre>"
            "<h3>이번에 돌린 확인</h3>" + checks_all + "</section>")
    return f"<html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Do+Hyeon&family=Gothic+A1:wght@400;500;700;800&display=swap' rel='stylesheet'><style>{CSS}</style></head><body>" \
        + cover + summary + howto + ch1 + ch2 + ch3 + ch4 + ch5 + ch6 + ch7 + ch8 + ch9 + ch10 + ch11 + appA + appB + appC + appD + appE + appF + "</body></html>"


def screen_data(url: str | None = None) -> dict:
    return {"funnel": api.funnel(), "analysis": api.analysis(), "events": api.analysis_events(), "movement": api.analysis_movement(),
            "extra": extra_data(url)}


def main(url: str, out: Path, html_only: bool) -> None:
    s = screen_data(url)
    outs = sc.run(s, url)
    bad = [o for o in outs if not o.same]
    if bad:
        raise SystemExit("화면 값과 다른 확인이 있어 멈춰요: " + "; ".join(f"{o.check.ch}장 {o.check.what}" for o in bad))
    html = build(s, outs)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        for img in MOA.glob("*.webp"):
            shutil.copy(img, Path(tmp) / img.name)
        if html_only:
            dst = out.with_suffix(".html")
            shutil.copy(page, dst)
            for img in MOA.glob("*.webp"):
                shutil.copy(img, dst.parent / img.name)
            print(dst)
            return
        r = subprocess.run(["swift", str(ROOT / "source" / "scripts" / "html_to_pdf.swift"), str(page), str(out)], capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise SystemExit(f"PDF 만들기 실패: {r.stderr[-500:]}")
    if out == OUT:
        shutil.copy(out, WEB_COPY)
    print(out, f"확인 {len(outs)}개 모두 화면 값과 같음")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="데이터 이야기 분석 보고서 PDF")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--html-only", action="store_true", help="PDF 대신 HTML만 (미리 보기용)")
    a = ap.parse_args()
    main(a.url, a.out, a.html_only)
