"""데이터 이야기 (/analysis, 웹 app/web/src/pages/Story.tsx). 회사 이름 없이 집계만. 보유 종목·점검·거래 화면과 잇지 않는다.

문구는 Story.tsx 그대로, 숫자는 api.analysis()/funnel()/events()/movement() 값과 Story.tsx와 같은 계산식으로만 쓴다.
"""
import math
from pathlib import Path

import streamlit as st

from common import api, esc, fixed, fmt, js_round, judge_year_html, load, moa, tournament
from story_charts import (bh_count, capacity_chart, coef_chart, corr_explorer, event_explorer, grid_chart, growth_chart,
                          holder_chart, jsn, md, pair_bars, payout_chart, reasons_chart, retro_chart, runway_chart,
                          sig_scatters, two_lines)

LAG_PLAIN = ['같은 해', '1년 전', '배당을 정하는 결의 시점(이듬해 1~3월)']  # 8장 경기 시점 쉬운 이름 (macro.lags 순서)
CHAPTERS = ['법 토너먼트', '기준선에 몰려요', '8년의 움직임', '내년엔 절반이', '내년에 필요한 배당', '공시 뒤 주가', '최대주주', '경기와 배당', '세금 제도와 배당', '대조군과 비교', '데이터 뒷이야기']
DATA_CH = CHAPTERS.index('데이터 뒷이야기') + 1  # 보유 자료를 보여 주는 장
REPORT_PDF = Path(__file__).resolve().parents[2] / "app" / "web" / "public" / "onepick_story_report.pdf"


def ch(body: str, cid: str | None = None) -> None:
    """장 하나의 글 묶음. 위젯이 끼어드는 장은 여러 묶음으로 나눠 그리고, 첫 묶음에만 id를 단다."""
    md(f'<div class="chapter" id="{cid}">{body}</div>' if cid else f'<div class="chapter" style="margin-top: 0">{body}</div>')


def say(text: str, mood: str = "curious", style: str = "") -> str:
    return f'<div class="moa-say" style="{style}"><img src="{moa(mood)}" alt="" /><p>{text}</p></div>'


def basis(summary: str, inner: str) -> str:
    return f'<details class="basis"><summary>{summary}</summary>{inner}</details>'


funnel, e1 = load(api.funnel)
a, e2 = load(api.analysis)
ev, e3 = load(api.events)
mv, e4 = load(api.movement)
f = funnel
error = e2 or e1 or e3 or e4

# ── Story.tsx 위쪽 계산 (같은 식) ───────────────────────────────────────────
before24 = [r[4] for r in a["retro"] if r[0] < 2024] if a else []
r24 = next((r for r in a["retro"] if r[0] == 2024), None) if a else None
r18 = a["retro"][0] if a else None
dropTens = js_round(sum(before24) / len(before24) / 10) if before24 else 0
okShare = []
if mv:
    for y, g in mv["grid"].items():
        if 2018 <= int(y) <= 2024:
            tot = sum(sum(r) for r in g)
            okShare.append((g[0][1] + g[0][2] + g[1][2]) / tot * 10 if tot else 0)
okTens = ""
if okShare:
    okLo, okHi = js_round(min(okShare)), js_round(max(okShare))
    okTens = f"{okLo}곳" if okLo == okHi else f"{okLo}~{okHi}곳"
reasonTotal = sum(x[1] for x in a["drop_reasons"]) if a else 0


def pay(v):
    return next((r[1] for r in a["payout"] if r[0] == v), 0)


def grow(v):
    return next((r[1] for r in a["growth"] if r[0] == v), 0)


minTotal = sum(x[1] for x in a["min_ratio"]) if a else 0
reg = [r for r in ev["methods"]["regression_60"] if r["모형"].startswith("+ 규모")] if ev and ev.get("methods") else None


def coef(name):
    return next((r for r in reg if r["변수"] == name), None) if reg else None


t = a["trust"] if a else None
sv = sum(t["source_verify"].values()) if t else 0
rv = sum(t["review"].values()) if t else 0
holderNear = next((r for r in a["holder"]["table"] if r["묶음"].startswith("기준선 근처")), None) if a and a.get("holder") else None
holderFar = next((r for r in a["holder"]["table"] if r["묶음"].startswith("나머지")), None) if a and a.get("holder") else None
mc = a.get("macro") if a else None


def sigCount(lag, kind):
    rows = [c for c in (mc["corr"] if mc else []) if c[0] == lag and c[1] == kind]
    return [len([c for c in rows if c[5] is not None and c[5] < 0.05]), len(rows)]


def sigAll(kind):
    k = n = 0
    for lag, _ in (mc["lags"] if mc else []):
        x = sigCount(lag, kind)
        k, n = k + x[0], n + x[1]
    return k, n


diffK, diffN = sigAll("diff")
levelK, levelN = sigAll("level")
diffRows = [c for c in (mc["corr"] if mc else []) if c[1] == "diff"]
diffMacros = list(dict.fromkeys(mc["macro_names"].get(c[3], c[3]) for c in diffRows)) if mc else []
diffDivs = list(dict.fromkeys(mc["dividend_names"].get(c[2], c[2]) for c in diffRows)) if mc else []
pf = mc.get("profit") if mc else None
pfUp, pfDown = (pf["updown_ex_last"][0], pf["updown_ex_last"][1]) if pf else (None, None)
pfR = next((r for r in pf["firm_ex_last"] if r["profit"] == "ni_change" and r["dividend"] == "dps_change"), None) if pf else None
macroFirmMax = max([0] + [abs(c[4]) for c in (mc["corr"] if mc else []) if c[1] == "panel_ex2025" and c[4] is not None])
diffBh = bh_count([c[5] for c in (mc["corr"] if mc else []) if c[1] == "diff" and c[5] is not None])
bh = a.get("behavior") if a else None


def prim(key):
    return [x for x in ((bh or {}).get("fits", {}).get(key) or []) if x["role"] == "primary"]


def fitOf(key, start):
    return next((x for x in prim(key) if x["name"].startswith(start)), None)


expRate, expFx = fitOf("exposure", "금리"), fitOf("exposure", "환율")
polHolder, polClose = fitOf("policy", "개인 최대주주"), fitOf("policy", "기준선")
placebo = [x for x in ((bh or {}).get("fits", {}).get("policy") or []) if x["role"] == "placebo" and x["name"].startswith("개인 최대주주")]


def sigP(x):
    return bool(x) and x.get("p_holm") is not None and x["p_holm"] < 0.05


def pp(v, d=1):
    return "–" if v is None else f"{'+' if v > 0 else ''}{fixed(v * 100, d)}%p".replace("-", "−", 1)


def p3(v):
    return "–" if v is None else "< 0.001" if v < 0.001 else fixed(v, 3)


_pol = ((bh or {}).get("series") or {}).get("policy") or {}
esHolder = [[r[1], (r[2] or 0) * 100, (r[3] or 0) * 100, (r[4] or 0) * 100] for r in (_pol.get("es_holder") or [])]


def rateHolder(yr, label):
    return next((r for r in (_pol.get("rate_holder") or []) if r[1] == yr and r[0] == label), None)


rateYears = sorted(set(r[1] for r in (_pol.get("rate_holder") or [])))


def rateGap(yr):
    h, o = (rateHolder(yr, "개인 최대주주 회사") or [None] * 3)[2], (rateHolder(yr, "나머지 회사") or [None] * 3)[2]
    return h - o if h is not None and o is not None else None


preLower = all((rateGap(y) or 0) < 0 for y in rateYears if y < 2025)
gap25 = rateGap(2025)
es25 = next((r[1] for r in esHolder if r[0] == 2025), None)
plLo = min(x["coef"] or 0 for x in placebo) if placebo else None
plHi = max(x["coef"] or 0 for x in placebo) if placebo else None
# 9장 방법과 한계: 제도 전(2018~2024) 모습과 크기 (평행추세 점검 숫자는 source/scripts/check_did_pretrend.py 2026-11-03 계산)
plSig = sum(1 for x in placebo if x.get("p_cluster") is not None and x["p_cluster"] < 0.05)


def sp(v):
    return f"{'+' if v > 0 else ''}{fixed(v, 1)}%p".replace("-", "−", 1)


preGaps = [g for g in (rateGap(y) for y in rateYears if y < 2025) if g is not None]
preOwner = [v for v in ((rateHolder(y, "개인 최대주주 회사") or [None] * 3)[2] for y in rateYears if y < 2025) if v is not None]
esPre = [r[1] for r in esHolder if r[0] < 2025 and r[0] != 2023]


def tercile(series, label):
    r = next((r for r in ((((bh or {}).get("series") or {}).get("exposure") or {}).get(series) or []) if r[0] == label), None)
    return r[2] if r else None


up25 = ((mc["series"].get("dps_up_share") or {}).get("2025")) if mc else None
cc = a.get("control") if a else None


def ind25(industry, group):
    return next((r for r in cc["industry_2025"] if r[0] == industry and r[1] == group), None) if cc else None


def pc(v):
    return "–" if v is None else f"{fixed(v, 1)}%"


def car(w, kind, group):
    return next((r for r in cc["car"] if r[0] == w and r[1] == kind and r[2] == group), None) if cc else None


ourN = sum(r[2] for r in cc["sample"] if r[0] == "우리 638사" and r[1]) if cc else 0
ourAll = sum(r[2] for r in cc["sample"] if r[0] == "우리 638사") if cc else 0
ourByInd = " · ".join(f"{r[1]} {r[2]}곳" for r in cc["sample"] if r[0] == "우리 638사" and r[1]) if cc else ""
sim = cc.get("simulation") if cc else None
inc25 = next((r for r in cc["increase"] if r[0] == 2025), None) if cc else None
incBefore = [v for r in cc["increase"] if r[0] < 2025 for v in (r[2], r[4]) if v is not None] if cc else []
incGapMax = max([0] + [abs(r[2] - r[4]) for r in cc["increase"] if r[0] < 2025 and r[2] is not None and r[4] is not None]) if cc else 0
ct = t.get("control") if t else None


def hAll(g):
    return next((h for h in (cc.get("holder") or []) if h["industry"] == "4개 업종 합계" and h["group"] == g), None) if cc else None


hOurs, hCtrl = hAll("우리 638사"), hAll("대조군")
hGaps = []
for i in ("제조업", "도소매업", "건설업"):
    o = next((h for h in ((cc or {}).get("holder") or []) if h["industry"] == i and h["group"] == "우리 638사"), None)
    c = next((h for h in ((cc or {}).get("holder") or []) if h["industry"] == i and h["group"] == "대조군"), None)
    if o and c:
        hGaps.append(o["median"] - c["median"])


def binShare(h):
    return [k / h["n"] * 100 for _, k in h["bins"]] if h else []


res = t.get("resolution") if t else None

# ── 머리 ─────────────────────────────────────────────────────────────────
md(f'''<div class="story-head"><div>
<h1>고배당 분리과세,<br />숫자로 따라가 볼까요?</h1>
<p>2026년 고배당기업 {f["total"] if f else 638}곳의 공시, 재무제표, 주가를 살펴봤어요. 회사 이름은 빼고 전체를 모은 숫자만 보여 드려요.<br />모두 팀이 보유한 자료로 분석했어요. 어떤 자료를 얼마나 모았는지는 <a href="#ch{DATA_CH}">{DATA_CH}장</a>에 있어요.<br />장마다 목적·방법·결과·한계·시사점을 정리한 분석 보고서(PDF)도 받아 볼 수 있어요.</p>
</div><div class="moa-say"><p>어려운 말은 제가<br />쉽게 바꿔 드릴게요!</p><img src="{moa("happy")}" alt="" /></div></div>
<nav class="chapters" aria-label="장 목차">{"".join(f'<a href="#ch{i + 1}">{i + 1} {c}</a>' for i, c in enumerate(CHAPTERS))}</nav>
<div class="notice">ⓘ <span><b>종목 추천이 아니며 매수·매도 판단 근거로 제공하지 않습니다.</b> 지난 숫자를 정리한 것이고, 한쪽이 다른 쪽의 원인이라는 뜻은 아니에요.</span></div>''')
if REPORT_PDF.exists():  # 웹의 '분석 보고서(PDF)' 링크와 같은 파일 (source/scripts/report_story_pdf.py가 만듦)
    st.download_button("분석 보고서(PDF) 받기", REPORT_PDF.read_bytes(), file_name="데이터이야기_분석보고서.pdf", mime="application/pdf")
if error:
    md(f'<p class="error">분석 결과를 불러오지 못했어요: {esc(error)}</p>')

# ── 1장 ──────────────────────────────────────────────────────────────────
ch('<div class="ch-no">1장</div><h2>문 세 개를 <em>모두</em> 지나야 해요. 마지막 문만 <em>둘 중 하나</em>예요</h2>'
   '<p class="lead">고배당기업이 되려면 법(조세특례제한법 제104조의27 ①)이 정한 요건 세 가지를 모두 채워야 해요. 이걸 문 세 개로 그렸어요. 단, 셋째 문(제3호)은 가목과 나목 중 하나만 채우면 돼요. 동전 하나가 회사 하나예요.</p>', "ch1")
if f:
    tournament(f, autoplay="visible", key="story-tour")
    ch(judge_year_html())
    ch(basis("근거와 숫자 보기", f'<p>각 문에서 몇 곳이 멈췄는지예요. 1라운드 자료 확인 → 판정 보류 <b>{f["hold_missing"]}</b>곳 · 2라운드 제2호(배당소득이 2024년보다 줄지 않았나) → 미충족 <b>{f["fail2"]}</b>곳 · 3라운드 제3호 → 가목 <b>{f["ga"]}</b>곳, 나목 <b>{f["na"]}</b>곳 + 적자라 배당성향 25%로 본 나목 <b>{f["na_deficit"]}</b>곳, 전전년 무배당이라 보류 <b>{f["hold_zero"]}</b>곳, 미달 <b>{f["fail3"]}</b>곳. 출처 core.core_judgement_2026.</p>'))
else:
    md('<div class="loading">불러오는 중…</div>')

if a:
    notes = a["notes"]
    # ── 2장 ──
    ch(f'''<div class="ch-no">2장</div>
<h2>분리과세 기준선 <em>바로 위에</em> 회사들이 몰려 있어요</h2>
<p class="lead">배당성향은 회사가 번 돈 중 얼마를 배당으로 나눠 줬는지를 나타낸 비율이에요. 고배당기업이 되려면 배당성향이 40% 이상이거나, 25% 이상이면서 배당을 전년보다 10% 이상 늘려야 해요. 고배당기업 명단 안에서 셌기 때문에 25%보다 낮은 회사는 원래 거의 없어요. 그래서 기준 위끼리 견줘 보면, 2025년 배당성향 25%대는 <b>{pay(25)}</b>곳으로 바로 위 26%대 <b>{pay(26)}</b>곳보다 많아요. 기준 바로 위에 회사가 몰려 있어요. 회사들이 기준에 맞춰 배당을 정했을 수도 있지만, 이 숫자만으로 그렇다고 단정할 수는 없어요.</p>
<div class="card">{payout_chart(a["payout"])}<p class="small" style="margin: 4px 0 0">이익을 낸 회사 {jsn(notes["payout_n"])}곳만 셌어요. 손해를 보고도 배당한 회사 {jsn(notes["deficit_n"])}곳은 뺐어요. 번 돈이 없으면 '번 돈 중 얼마를 배당했나'를 계산할 수 없어서예요. 몰림이 우연인지는 따로 계산했어요. 28% 위 회사 수로 '몰림이 없었다면 있었을 곳 수'를 그려 보면 2025년 25~28%에는 예상보다 약 69곳(5~75% 안 449곳의 15%쯤)이 더 있었어요. 회사를 1,000번 다시 뽑아 계산해도 가운데 95%가 45~93곳으로 0보다 커서 우연으로 보기 어렵고, 2018~2024년에는 이런 몰림이 없었어요. 다만 왜 몰렸는지는 이 계산으로 알 수 없어요. 출처 source/scripts/analysis_bunching.py → report/분석/기준선_몰림_분석_결과.md.</p></div>
<h3>배당 증가율도 <em style="color: var(--sea)">10% 바로 위</em>에 모여요</h3>
<p class="lead">배당 증가율은 배당을 전년보다 몇 % 늘렸는지예요. 나목은 배당을 10% 이상 늘려야 해요. 9%대는 <b>{grow(9)}</b>곳인데 10%대는 <b>{grow(10)}</b>곳이에요. 다만 9%대 회사는 배당성향이 40% 이상이어야 명단에 들 수 있어서 원래 적게 잡혀요. 그러니 이 차이를 모두 기준에 맞춘 결과로 볼 수는 없어요.</p>
<div class="card">{growth_chart(a["growth"])}<p class="small" style="margin: 4px 0 0">2024년과 2025년에 모두 배당했고 순이익 자료가 있는 {jsn(notes["growth_n"])}곳을 셌어요. 그림을 보기 좋게 하려고 배당을 10% 넘게 줄였거나 30% 넘게 늘린 회사는 뺐어요. 0%대가 많은 건 작년과 똑같이 배당한 회사가 많아서예요.</p></div>''', "ch2")

    # ── 3장 ──
    ch3 = ('<div class="ch-no">3장</div><h2>8년 동안 회사들은 <em>어느 칸</em>에 있었을까요?</h2>'
           '<p class="lead">가로는 배당성향, 세로는 배당 증가율이에요. 이 둘로 9칸을 나눴고, 초록 테두리 칸에 있으면 요건을 채운 거예요. 연도를 바꾸거나 재생 버튼을 눌러 해마다 몇 곳이 어느 칸에 있었는지 보세요.</p>')
    if okTens:
        ch3 += f'<p class="lead">고배당기업은 한 번 뽑히면 끝이 아니라 해마다 다시 따져요. 지금 고배당기업 명단에 있는 회사 가운데 그해 흑자였고 전년에도 배당한 회사만 칸 그림에 넣어 지난 8년을 보니, 2018~2024년에는 해마다 10곳 중 {okTens} 정도만 요건을 채웠어요. 올해 고배당기업이라도 예전에는 아니었던 회사가 많다는 뜻이에요. 그러니 올해 한 해만 보지 말고 해마다 배당이 어떻게 바뀌는지 함께 봐야 해요.</p>'
    ch(ch3, "ch3")
    if mv:
        import streamlit as st
        with st.container(border=True):
            grid_chart(mv["grid"])
        dc = mv.get("decrease_check")
        dc_t = f" 두 값이 모두 있는 {dc['year']}년으로 견주면, 칸 그림 {dc['n']}곳 중 배당소득 값도 있는 {dc['both']}곳에서 '감소'인지가 갈리는 회사는 {dc['differ']}곳이에요(배당소득 값이 없는 {dc['n'] - dc['both']}곳은 견주지 못했어요)." if dc else ""
        g25 = mv["grid"].get("2025")
        g25n = fmt(sum(sum(r) for r in g25)) if g25 else "–"
        met_t = f" {fmt(f['ga'] + f['na'] + f['na_deficit'])}곳" if f else ""
        nad_t = f"{f['na_deficit']}곳" if f else "일부"
        ch(basis("근거", f'''<p>칸을 나눈 방법과 자료예요. {esc(mv["basis"])}. 칸 경계는 판정 엔진과 같은 정수 비교예요(배당성향 25%·40%, 증가율 10%, 감소 여부). '배당 감소' 줄은 배당 총액 기준이고, 법의 제2호는 배당소득 기준이라 다를 수 있어요.{dc_t} 마지막 해는 그해 숫자로 고배당기업을 고른 표본이라 다른 해와 바로 비교하지 않아요. 출처 core.v_dividend_year_verified, core.v_financial_year_verified.</p>
<p><b>1장과 숫자가 다른 이유</b> · 1장은 올해 판정이고, 이 그림은 8년을 같은 잣대로 견주려고 만든 그림이에요. 그래서 세 가지가 달라요.</p>
<ul>
<li><b>세는 회사가 달라요.</b> 2025년 칸에 있는 회사를 모두 더한 {g25n}곳은 요건을 채운 회사 수가 아니라 그림에 들어간 회사 전체예요. 적자 회사, 전년에 배당하지 않았거나 값을 확인하지 못한 회사는 배당성향이나 증가율을 계산할 수 없어서 빠졌어요.</li>
<li><b>적자 회사는 법이 따로 봐 줘요.</b> 법은 적자 회사의 배당성향을 25%로 쳐 주지만, 이 그림에서는 계산할 수 없어 뺐어요. 1장에서 요건을 채운{met_t} 중 {nad_t}이 이런 회사예요.</li>
<li><b>'배당 감소' 줄의 잣대가 달라요.</b> 법(제2호)은 배당소득이 줄었는지를 보는데, 배당소득 값은 2024·2025년 것만 있어요. 8년을 같은 잣대로 견주려고 이 그림은 배당 총액으로 셌어요. 배당성향과 증가율로 칸을 나누는 계산은 판정과 같아요.</li>
</ul>'''))
    else:
        md('<div class="loading">불러오는 중…</div>')

    # ── 4장 ──
    lead4 = '<p class="lead">고배당기업은 해마다 새로 따져요. 그래서 어느 해에 요건을 채운 회사가 다음 해에도 채웠는지 따라가 봤어요. 지금 법을 지난 해 숫자에 그대로 대어 본 거예요.'
    if r18:
        lead4 += f' 예를 들어 {r18[0]}년에 요건을 채운 회사는 <b>{r18[1]}곳</b>이었는데, 이 중 <b>{r18[3]}곳</b>은 {r18[0] + 1}년에 채우지 못했어요. 2년 연속 채운 곳은 {r18[1] - r18[3]}곳뿐이에요.'
    lead4 += f' {r24[0] - 1 if r24 else 2023}년까지 보면 해마다 <b>10곳 중 {dropTens}곳꼴</b>이 다음 해에 빠졌어요. 그래서 올해 대상이어도 "내년에도 될까?"를 미리 확인해야 해요.</p>'
    side = f'<div class="stat"><b>{js_round(min(before24))}~{js_round(max(before24))}%</b><span>2018~2023년에 다음 해 빠진 비율<br />10곳 중 {dropTens}곳꼴</span></div>'
    if r24:
        side += f'<div class="stat"><b style="color: var(--coin-deep)">{fixed(r24[4], 1)}%</b><span>2024년만 뚝 떨어졌어요<br />2025년 숫자로 뽑힌 명단을 보고 있어서, 2025년에는 거의 다 요건을 채울 수밖에 없어요</span></div>'
    ch(f'''<div class="ch-no">4장</div>
<h2>올해 고배당기업이어도, 다음 해엔 <em class="no">절반</em>이 빠졌어요</h2>{lead4}
<div class="ch-body"><div class="card">{retro_chart(a["retro"])}<p class="small" style="margin: 4px 0 0">막대 높이 = 그해 요건을 채운 회사 중 다음 해에 못 채운 비율 · 막대 아래 숫자 = 못 채운 곳 / 그해 채운 곳 · 다음 해에 새로 채운 회사는 세지 않았어요</p></div>
<div class="ch-side">{side}</div></div>
<h3>빠진 이유 1위는 <em>"배당이 줄어서"</em>예요</h3>
<div class="card">{reasons_chart(a["drop_reasons"])}</div>
{basis("근거와 한계", f"<p>빠진 {reasonTotal}건을 기준으로 셌어요. 지금 법을 지난 해에 대어 본 가상 결과이고, 지난 세금을 다시 매긴다는 뜻은 아니에요. 지난 해에는 '2024년보다 줄지 않았나'를 볼 수 없어서 '직전 해 배당이 그 전 해보다 줄지 않았나'로 대신했어요(팀 해석). 지금 명단에 남은 회사만 봤기 때문에, 그사이 사라진 회사는 빠져 있어요(생존 편향). 출처 source/core/p1_analysis.py.</p>")}''', "ch4")

    # ── 5장 ──
    cap = a["capacity"]
    others = " · ".join(f"{k} {jsn(v)}곳" for k, v in cap["other"].items())
    ch(f'''<div class="ch-no">5장</div>
<h2>내년에도 넘으려면? <em>절반은 올해만큼이면 돼요</em></h2>
<p class="lead">2027년에 받는 배당도 분리과세 대상이 되려면, 회사가 2026년 몫으로 배당을 최소 얼마나 줘야 할까요? 그 최소 금액을 계산해서 2025년 배당과 견줘 봤어요. 2026년 순이익은 2025년과 같다고 놓고 계산했어요.</p>
<div class="card">{runway_chart(a["min_ratio"])}</div>
<h3>그만큼 줄 <em style="color: var(--sea)">돈은 있을까요?</em></h3>
<p class="lead">2025년에 회사가 사업과 투자를 하고 남은 현금(잉여현금흐름)이 위에서 계산한 최소 배당의 몇 배인지 봤어요. 1배보다 작으면 그해 번 현금만으로는 모자란다는 뜻이에요. 회사들을 줄 세웠을 때 한가운데 회사는 <b>{jsn(cap["median"])}배</b>예요.</p>
<div class="card">{capacity_chart(cap)}</div>
{basis("근거", f"<p>최소 배당을 계산할 수 있었던 회사는 {minTotal}곳이에요(core.core_min_dividend_2027 '2025년 (기본)'). 남은 현금 비교 {jsn(cap['n'])}곳(core.core_capacity_2025.cover_x), {others}은 뺐어요. 남은 현금 비교는 요건 판정과 상관없는 참고값이에요.</p>")}''', "ch5")

    # ── 6장 ──
    ch('<div class="ch-no">6장</div><h2>공시 뒤, 주가는 어떻게 움직였을까요?</h2>'
       '<p class="lead">회사가 배당 같은 공시를 낸 뒤 주가가 시장 평균보다 얼마나 더 올랐는지(초과수익률) 봤어요. 공시 종류와 조건을 직접 골라 보세요. 굵은 선은 한가운데 회사의 값이고, 옅은 띠는 가운데 절반 회사(25~75%)가 들어 있는 범위예요. 증자·감자·분할은 공시 날짜와 주가만으로 계산했어요.</p>', "ch6")
    if ev:
        event_explorer(ev)
    else:
        md('<div class="loading">불러오는 중…</div>')
    ch6 = ""
    if reg and coef("배당수익률(%)"):
        facts = ""
        for nm in ("배당수익률(%)", "배당 증가(0/1)", "log 시가총액(추정)"):
            r = coef(nm)
            label = "배당수익률이 1%p 높으면" if nm == "배당수익률(%)" else "배당을 늘렸다는 사실만으로는" if nm == "배당 증가(0/1)" else "회사가 클수록"
            facts += (f'<div><dt>{label}</dt><dd>{"+" if r["계수(%p)"] > 0 else ""}{jsn(r["계수(%p)"])}%p {"· 뚜렷함" if r["p"] < 0.05 else "· 뚜렷하지 않음"}</dd>'
                      f'<span class="pill {"pill--sea" if r["p"] < 0.05 else "pill--gray"}">{"우연으로 보기 어려워요" if r["p"] < 0.05 else "우연일 수도 있어요"}</span></div>')
        n_reg = jsn(ev["methods"]["n_regression_60"])
        q6 = say(f"그럼 주가가 더 오른 데는 무엇이 관련 있었을까요? 여러 요인을 한꺼번에 넣고 공시 뒤 60거래일을 비교해 봤어요({n_reg}건).", style="margin-bottom: 14px")
        ch6 += (f'<div class="card" style="margin-top: 20px">{q6}'
                f'<div class="facts" style="grid-template-columns: repeat(3, 1fr)">{facts}</div>'
                '<p style="margin: 14px 0 0">배당을 늘렸는지보다 <b>배당수익률(주가 대비 배당)이 높았는지</b>가 공시 뒤 주가와 더 관련 있었어요. 함께 나타났다는 뜻이지, 배당수익률 때문에 주가가 올랐다는 뜻은 아니에요.</p></div>')
    ps = f"(배당수익률 p = {jsn(coef('배당수익률(%)')['p'])}, 배당 증가 p = {jsn(coef('배당 증가(0/1)')['p'])}, 회사 규모 p = {jsn(coef('log 시가총액(추정)')['p'])})" if reg and coef("배당수익률(%)") else ""
    ch6 += basis("방법과 한계", f"<p>쉽게 말해, 공시 뒤 주가 움직임에서 그날 시장 전체 움직임을 뺀 값이에요. 자세한 방법: 곡선과 가운데 값은 시장조정 초과수익률(종목 수익률 − 시장지수 수익률)이에요. '우연일 가능성'은 같은 조건의 시장조정 사례로 Kolari–Pynnönen 보정 BMP 검정을 한 결과예요(팀이 미리 정한 주 분석은 시장모형 기준이에요. 주 분석 조건에서는 두 방법 모두 q가 0.05보다 작아 결론이 같아요). 요인 비교는 시장모형 60거래일 회귀예요. '뚜렷함·우연으로 보기 어려워요'는 p값이 0.05보다 작다는 뜻이에요. 실제로는 관련이 없는데 이 정도 차이가 우연히 나올 가능성이 5% 미만이라는 뜻이고, 0.05 이상이면 '우연일 수도 있어요'로 표시해요. '우연으로 보기 어려워요'는 차이가 있다는 뜻이지 크다는 뜻은 아니에요. 얼마나 큰지는 %p 숫자로 따로 봐야 해요{ps}. q는 모든 조건에 걸쳐 Benjamini–Hochberg로 보정한 값이에요. 사례 10건 미만은 표시하지 않아요. 이 계산은 '공시가 없었다면 주가가 평소처럼 시장을 따라 움직였을 것'이라고 놓고 해요. 같은 때 다른 사건이 섞일 수 있고 인과관계가 아니에요. 주가·지수는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가예요. 출처 core.core_event_curve, source/scripts/event_methods.py → report/분석/이벤트스터디_방법별_결과.md.</p>")
    ch(ch6)

    # ── 7장 ──
    if a.get("holder"):
        h = a["holder"]
        kinds = h["notes"]["kinds"]
        ch(f'''<div class="ch-no">7장</div>
<h2>기준선 근처 회사는 <em>개인 최대주주</em>가 조금 더 많아요</h2>
<p class="lead">최대주주가 개인이면 지분이 많은 만큼 배당도 많이 받아요. 회사가 고배당 요건을 채우면 그 사람도 분리과세로 세금을 줄일 수 있어요. 그래서 개인 최대주주는 배당을 늘리고 싶어 할 수 있어요. 정말 그런 회사가 기준선 근처에 많은지 살펴봤어요.</p>
<p class="lead">배당성향 25%·40%, 증가율 10% 기준선에서 위아래 {jsn(h["near_pp"])}%p 안에 있는 회사를 '기준선 근처'로 묶어 나머지와 견줬어요. 최대주주가 개인인 회사는 기준선 근처가 <b>{jsn(holderNear["개인 최대주주(%)"]) if holderNear else ""}%</b>, 나머지가 <b>{jsn(holderFar["개인 최대주주(%)"]) if holderFar else ""}%</b>예요.</p>
<div class="card">{holder_chart(h)}<p class="small" style="margin: 6px 0 0">점 = 최대주주와 가족·계열사(특수관계인)가 가진 보통주 지분율의 한가운데 값 · 막대 = 가운데 절반 회사의 범위 · 오른쪽 = 최대주주가 개인인 회사 비율. 한 회사가 여러 기준선 근처에 함께 들어갈 수 있어요.</p></div>
{basis("근거와 한계", f"<p>2025 사업보고서 최대주주 현황(OpenDART) {jsn(h['notes']['n_holder'])}곳 중 지분율이 있는 {jsn(h['notes']['n_pct'])}곳 · 최대주주 개인 {jsn(kinds.get('개인'))} · 법인 {jsn(kinds.get('법인'))} · 판단 불가 {jsn(kinds.get('판단 불가'))}. 두 비율이 몇 %p 다른지만 본 단순 비교이고, 그 차이가 우연인지 검정하지는 않았어요. 함께 나타난 경향일 뿐, 최대주주 때문이라고 단정하지 않아요. 출처 core.core_major_holder, source/core/holder_analysis.py.</p>")}''', "ch7")

    # ── 8장 ──
    if mc:
        sets = ""
        for ttl, items in (("경기 지표", diffMacros), ("배당 지표", diffDivs), ("경기를 본 시점", LAG_PLAIN[:len(mc["lags"])])):
            unit = "가지" if ttl == "경기를 본 시점" else "개"
            chips = "".join(f'<span class="chip chip--line">{esc(x)}</span>' for x in items)
            sets += f'<div class="macro-set"><b>{ttl} <em>{len(items)}{unit}</em></b><div class="chips">{chips}</div></div>'
        ch(f'''<div class="ch-no">8장</div>
<h2>경기가 좋아지면 배당도 늘었을까요? <em>뚜렷하지 않았어요</em></h2>
<p class="lead">경기가 좋아진 해에 배당도 늘었을까요? 아래 경기 지표와 배당 지표를 하나씩 짝지어, 전년보다 늘거나 준 정도가 함께 움직였는지 봤어요. 자료는 2017~2025년 9년치예요. 전년과의 차이는 앞 해가 있어야 셀 수 있어서 실제로는 2018~2025년 8개 해를 봤어요.</p>
<div class="card macro-sets">{sets}</div>
{say("<b>상관계수가 뭐예요?</b> 두 값이 얼마나 함께 움직이는지를 −1에서 1 사이 숫자로 나타낸 거예요. 1에 가까우면 하나가 오를 때 다른 하나도 올랐고, −1에 가까우면 하나가 오를 때 다른 하나는 내렸어요. 0에 가까우면 서로 상관없이 움직였어요. 함께 움직였다고 해서 하나가 다른 하나의 원인이라는 뜻은 아니에요.", style="margin: 16px 0")}
<p class="lead" style="color: var(--ink)"><b>{len(diffMacros)} × {len(diffDivs)} × {len(mc["lags"])} = {diffN}쌍</b> 중에서 함께 움직인 것처럼 보인 짝은 <b style="color: var(--sea)">{diffK}쌍</b>뿐이었어요. 아무 관계가 없어도 {diffN}쌍을 보면 {js_round(diffN * 0.05)}쌍쯤은 우연히 이렇게 나와요. 그래서 <b>경기만 보고 배당을 짐작하기는 어려웠어요.</b></p>''', "ch8")
        body8 = ""
        if pf and pfUp and pfDown and pfR:
            facts = "".join(f'<div><dt>{esc(k)}</dt><dd>{jsn(up)}%가 배당을 올렸어요</dd><dt>줄인 회사 {jsn(cut)}% · 회사·연도 {fmt(nn)}개</dt></div>' for k, nn, up, cut in (pfUp, pfDown))
            body8 += f'''<h3>회사마다 보면, 배당은 <em style="color: var(--sea)">그 회사의 이익</em>을 따라 움직였어요</h3>
<p class="lead">이번에는 경기 대신 회사마다 자기 이익이 늘었는지와 배당이 늘었는지를 짝지어 봤어요({pf["years"][0]}~{pf["years"][1] - 1}년). 그해 이익이 늘어난 회사는 <b>{jsn(pfUp[2])}%</b>가 1주당 배당을 올렸는데, 이익이 줄어든 회사는 <b>{jsn(pfDown[2])}%</b>만 올렸어요. 상관계수는 <b>{fixed(pfR["r"], 2)}</b>로, 경기 지표와 견준 값(가장 커도 {fixed(macroFirmMax, 2)})보다 훨씬 컸어요. 배당은 경기보다 그 회사가 번 돈을 더 따라갔어요.</p>
<div class="facts facts--big" style="grid-template-columns: repeat(2, 1fr)">{facts}</div>
<p class="small">{pf["years"][1]}년은 그해 숫자로 고배당기업을 뽑았기 때문에 뺐어요(넣어도 상관계수 {fixed(pf["firm"][0]["r"], 2)}로 결론은 같아요). 1년 전 이익 변화와는 거의 관계가 없었어요(상관계수 {fixed(pf["firm_ex_last"][3]["r"], 2)}). 배당은 <b>그해</b> 이익을 따라간 거예요. 함께 움직였다는 뜻이지, 이익이 배당을 정했다고 단정하는 건 아니에요.</p>'''
        body8 += f'''<h3>함께 움직인 것처럼 보인 {diffK}짝 <small style="color: var(--gray); font-size: 0.62em">우연일 수 있어요</small></h3>
<p class="small">점 하나가 한 해예요(2018~2025년, 8개). 노란 점이 2025년이에요. "실업률이 오른 해에 배당총액도 늘었다"처럼 상식과 반대인 짝도 있어요. 여기 실린 짝은 아무 관계가 없는데도 이만큼 함께 움직일 가능성이 5%보다 작은 짝(p &lt; 0.05)이에요. 여러 번 검사하면 우연히 걸리는 짝도 늘어나서, 기준을 더 엄하게 잡으면(BH 보정) {str(diffBh) + "쌍만 남아요" if diffBh else "하나도 남지 않아요"}.</p>
{sig_scatters(mc, "diff")}
<h3>회사마다 보면: 작년 경상수지가 많이 늘었을 때 <em style="color: var(--sea)">올해 배당을 올린 회사가 조금 많았어요</em></h3>
<p class="small">계산은 회사와 연도 하나하나(수천 개)로 했고, 그림은 보기 쉽게 해마다 모은 값(배당 올린 회사 비율, 증가율 한가운데 값)으로 그렸어요. 상관은 0.2보다 작아 약한 편이고, 2025년(배당 올린 회사 {fixed(up25, 1) if up25 is not None else ""}%)을 빼면 더 작아져요.</p>
{sig_scatters(mc, "panel")}
{basis(f"전년과의 차이가 아니라 그해 값끼리 견준 결과 보기 ({levelN}짝 중 {levelK}짝이 뚜렷)", '<p class="small">두 값이 해마다 꾸준히 오르기만 해도 상관이 크게 나와요. 그래서 이 짝들은 관계가 있다는 근거로 보기 어려워요.</p>' + sig_scatters(mc, "level"))}
<h3>전체 표에서 <em style="color: var(--sea)">시점과 보는 법</em>을 바꿔 보세요</h3>
<p class="lead">칸 안의 숫자가 상관계수예요. 진한 칸은 우연으로 보기 어려운 짝(p &lt; 0.05)이에요. 위 버튼으로 경기를 본 시점과 비교 방법을 바꿔 볼 수 있어요.</p>'''
        ch(body8)
        corr_explorer(mc)
        body8b = ""
        if expRate and expFx:
            facts = ""
            for label, dfn, x, unit in (("금리가 오를 때, 빚이 많은 회사는", "빚 비율 = 전년 말 차입금·사채 ÷ 자산총계", expRate, "기준금리 1%p"),
                                        ("원/달러가 오를 때, 외화로 된 자산이나 빚이 많은 회사는", "외화 비율 = 전년 외화환산이익·손실과 해외사업장 환산차이(절댓값) ÷ 자산총계", expFx, "원/달러 1%")):
                dd = ("배당을 더 올렸어요" if x["coef"] > 0 else "배당을 덜 올렸어요") if sigP(x) else "다르지 않았어요"
                facts += (f'<div><dt>{label}<br /><small>{dfn}. 같은 해 회사들을 이 비율로 줄 세워, 가장 낮은 회사와 가장 높은 회사의 차이를 봤어요</small></dt><dd>{dd}</dd>'
                          f'<dt>{unit}당 배당 방향 점수 {"+" if x["coef"] > 0 else ""}{fixed(x["coef"], 3).replace("-", "−", 1)} · 보정 p {p3(x["p_holm"])} · {fmt(x["n_firms"])}곳</dt></div>')
            trs = ""
            for m_ in ("기준금리", "원/달러"):
                for w in ("오른 해", "내린 해"):
                    for b in ("크게 받는 회사(위 1/3)", "적게 받는 회사(아래 1/3)"):
                        k = f"{m_}|{w}|{b}"
                        trs += f'<tr><th>{m_} {w}</th><td style="text-align: left">{b}</td><td>{pc(tercile("tercile_up", k))}</td><td>{pc(tercile("tercile_cut", k))}</td></tr>'
            body8b += f'''<h3>회사마다 받는 크기로 봐도 <em style="color: var(--sea)">{"차이가 있었어요" if sigP(expRate) or sigP(expFx) else "달라지지 않았어요"}</em></h3>
<p class="lead">해마다 견주면 9개 해뿐이라 판단할 자료가 적어요. 그래서 이번에는 같은 해 회사끼리 견줬어요. 금리가 오르면 빚이 많은 회사가, 환율이 오르면 외화 자산이나 외화 빚이 많은 회사가 더 큰 영향을 받아요. 그렇다면 <b>영향을 크게 받은 회사</b>는 배당을 다르게 정했을까요? 공정하게 견주려고 그해 모든 회사가 함께 겪은 일, 회사마다 원래 배당하던 습관, 이익 변화 같은 다른 이유는 빼고 봤어요.</p>
<div class="facts" style="grid-template-columns: repeat(2, 1fr)">{facts}</div>
{basis("영향을 크게 받는 회사와 적게 받는 회사를 단순히 견준 표 보기", f'<div class="corr-table"><table><thead><tr><th>경기</th><th>회사</th><th>올린 비율</th><th>줄인 비율</th></tr></thead><tbody>{trs}</tbody></table></div><p class="small">위 1/3·아래 1/3 = 같은 해 회사들을 금리는 빚 비율, 원/달러는 외화 비율로 줄 세웠을 때 위쪽·아래쪽 3분의 1이에요. 그해 분위기·회사 성향을 빼지 않은 단순 비율이에요. 배당 방향 점수는 줄임 −1 · 그대로 0 · 올림 +1이고, 노출도가 가장 적은 회사에서 가장 큰 회사로 갈 때의 차이예요. 2,000번 연도를 섞어 본 순열검정과 Holm 보정으로 판단했어요. 출처 partner.fs_line(차입금·외화환산 계정), partner.v_panel, core.core_behavior_fit(계산일 {esc(bh["built_at"]) if bh else ""}) → report/분석/배당_노출도_분석_결과.md.</p>')}'''
        pf_t = (f" 이익과 배당은 회사·연도마다 지배주주 순이익 증감과 보통주 주당배당금 증감을 짝지은 Spearman 상관이에요. p값은 같은 해 안에서만 이익 값을 {fmt(pf['n_perm'])}번 섞은 순열검정이라, 그해 모두가 함께 겪은 분위기는 빼고 회사끼리의 차이만 봐요(네 가지 짝 중 1년 전 이익을 뺀 셋은 p &lt; 0.001). 해마다 모은 값 {pf['year_agg']['n']}개끼리 보면 상관계수 {fixed(pf['year_agg']['r'], 2)}(p = {fixed(pf['year_agg']['p'], 2)})로 관계가 보이지 않아요. 그래서 '회사마다 보면'이라고 적었어요. 출처 core.v_financial_year_verified, core.v_dividend_year_verified → source/scripts/analyze_profit_dividend.py(계산일 {esc(pf['built'])}).") if pf else ""
        body8b += basis("방법과 한계", f"<p>쉽게 말해, 9개 해뿐인 짧은 자료라 한두 해가 결과를 크게 흔들 수 있어요. 자세한 방법: Spearman 순위 상관이에요. p값은 순열검정(값을 섞어 같은 크기 상관이 우연히 나오는 비율)이고, '회사마다'는 회사들이 같은 해 경기 값을 함께 받으므로 연도 단위로 섞었어요. p값이 작으면 '우연으로 보기 어렵다'는 뜻일 뿐, 관계가 세다는 뜻은 아니에요. 회사·연도가 수천 개면 아주 약한 상관도 p가 작게 나와서, 얼마나 센지는 상관계수(−1~1) 크기로 따로 봐요. 사업연도가 2017~2025 9개뿐이라 한 해(2020 코로나, 2025)가 결과를 크게 흔들어요. 지금 638곳 명단으로만 봐서, 그 뒤 상장한 회사는 앞 연도 값이 없고 사라진 회사는 빠져 있어요. 배당총액은 해마다 배당이 가장 큰 1곳의 몫이 커서, 그 1곳을 뺀 값도 따로 봤어요.{pf_t} 상관관계이고 인과가 아니에요. 출처 raw.ecos_macro(한국은행 ECOS), core.v_dividend_year_verified, core.core_macro_dividend_corr(계산일 {esc(mc['built_at'])}) → report/분석/배당_거시지표_상관_결과.md.</p>")
        ch(body8b)

    # ── 9장 ──
    if bh and polHolder and polClose:
        es25_t = f"{'+' if es25 > 0 else ''}{fixed(es25, 1)}%p".replace("-", "−", 1) if es25 is not None else "–"
        dt_lead = ("개인 최대주주 회사는 2024년까지 배당을 10% 이상 늘린 비율이 다른 상장사보다 낮았는데, 2025년에는 오히려 더 높아져서"
                   if preLower and gap25 is not None and gap25 > 0 else "2025년에 배당을 10% 이상 늘린 비율이")
        pre_t = (f"<p><b>제도 전 모습(평행추세 점검)</b> · 단순 비율로 보면 개인 최대주주 회사와 다른 상장사의 차이는 2018~2024년에 {sp(min(preGaps))}~{sp(max(preGaps))}였고{'(해마다 개인 최대주주 회사가 낮았어요)' if preLower else ''}, 2025년에는 {sp(gap25) if gap25 is not None else '–'}였어요. 늘 일정하게 낮았던 몫은 회사 차이를 빼면서 함께 빠져요. 해마다 본 계수는 제도 전에 {sp(min(esPre))}~{sp(max(esPre))}로 오르내렸지만, 여섯 해가 모두 0이라는 가정을 한꺼번에 검정하면 p = 0.13이에요. 제도 전에 두 무리가 서로 다른 속도로 움직인 흔적도 뚜렷하지 않았어요(개인 최대주주 회사 쪽이 해마다 +0.6%p, p = 0.37). 이 기울기를 빼고 다시 계산해도 2025년 차이는 +9.0%p(p = 0.02)로 남아요. 다만 흔적이 뚜렷하지 않다는 것이 평행추세가 맞다는 증명은 아니고, 2020년처럼 한 해에 크게 흔들린 적도 있어요. 출처 source/scripts/check_did_pretrend.py(2026-11-03 계산, 같은 자료·같은 모형).</p>"
                 if preGaps and esPre else "")
        trs = ""
        for yr in rateYears:
            hh = (rateHolder(yr, "개인 최대주주 회사") or [None] * 3)[2]
            oo = (rateHolder(yr, "나머지 회사") or [None] * 3)[2]
            diff = f"{'+' if hh - oo > 0 else ''}{fixed(hh - oo, 1)}%p".replace("-", "−", 1) if hh is not None and oo is not None else "–"
            trs += f"<tr><th>{yr}</th><td>{pc(hh)}</td><td>{pc(oo)}</td><td>{diff}</td></tr>"
        ch(f'''<div class="ch-no">9장</div>
<h2>배당소득 분리과세 뒤, 누가 배당을 더 늘렸을까요? <em>{"세금을 가장 많이 아끼는 회사" if sigP(polHolder) else "뚜렷하지 않았어요"}</em></h2>
<p class="lead">고배당기업 배당소득 분리과세는 2025년 7월에 발표되고 12월에 국회를 통과했어요. 요건을 2025년 숫자로 따지기 때문에 <b>2025년 배당은 회사들이 이 제도를 알고 정한 첫 배당</b>이에요. 그래서 제조·도소매·건설·부동산임대 상장사 전체에서, 2025년에만 유독 배당을 더 늘린 무리가 있었는지 봤어요. 그해 경기처럼 모든 회사가 함께 겪은 일은 빼고 봤어요.</p>
<div class="facts facts--big" style="grid-template-columns: repeat(2, 1fr)">
<div><dt>개인 최대주주 회사<br /><small>최대주주가 회사가 아닌 개인이고, 최대주주와 가족·계열사 등 특수관계인 지분 합계 30% 이상</small></dt><dd>{pp(polHolder["coef"])}</dd>
<dt>{dt_lead} 평소와 비교하면 {pp(polHolder["coef"])} 더 {"늘었어요" if (polHolder["coef"] or 0) >= 0 else "줄었어요"}.<br /><small>보정 p {p3(polHolder["p_holm"])} · {fmt(polHolder["n_treated"] or 0)}곳</small></dt></div>
<div><dt>기준선 가까이 있던 회사<br /><small>순이익이 전년과 같다고 할 때, 배당을 전년보다 50% 이하만 늘려도 요건(배당성향 40%, 또는 25% 이상이면서 배당 10% 증가)을 맞추는 회사</small></dt><dd>{pp(polClose["coef"])}</dd><dt>{"우연이라 보기 어려워요" if sigP(polClose) else "우연과 구별되지 않아요"} · 보정 p {p3(polClose["p_holm"])} · {fmt(polClose["n_treated"] or 0)}곳</dt></div>
</div>
{say("분리과세로 세금을 가장 많이 아끼는 사람은 배당을 많이 받는 개인 최대주주예요. " + ("실제로 배당을 정하는 개인 최대주주가 배당도 직접 받는 회사는 2025년에 배당을 늘린 비율이 다른 회사보다 더 크게 올랐어요." if sigP(polHolder) else "그런데 개인 최대주주 회사도 2025년에 뚜렷하게 달라지지는 않았어요.") + " 다만 같은 해에 바뀐 상법의 영향과 나눠 보기는 어려워요. 그래서 제도 효과라고 단정하지 않아요.", style="margin: 14px 0")}
<h3>해마다 견줘 보면 <em style="color: var(--sea)">{"2025년에 가장 크게 튀어요" if sigP(polHolder) else "해마다 비슷해요"}</em></h3>
<div class="card">{coef_chart(esHolder, 2023, "개인 최대주주 회사와 다른 상장사의 배당 10% 이상 증가 비율 차이, 해마다")}</div>
<p class="lead">점 하나는 그해 '배당을 10% 이상 늘린 회사 비율'이 개인 최대주주 회사와 다른 상장사 사이에 얼마나 차이 났는지예요. 2023년을 0으로 놓고 다른 해가 그보다 얼마나 높고 낮은지 그렸어요. 2018~2024년에는 위아래로 오르내렸는데, 제도를 알고 배당을 정한 2025년(노란 점)에는 <b>{es25_t}</b>로 크게 올라갔어요. 제도가 다른 해에 생겼다고 치고 똑같이 계산해 보면 {pp(plLo)} ~ {pp(plHi)}가 나와요. 2025년 값이 그 어느 해보다 커요. 다만 가짜 해 {len(placebo)}번 중 {plSig}번은 우연으로 보기 어려운 값(p &lt; 0.05)이 나왔어요. 해마다 이 정도는 흔들릴 수 있다는 뜻이라, 2025년 결과도 조심해서 읽어야 해요.</p>
<p class="small">최대주주가 지주회사 같은 법인이면 배당이 그 법인을 먼저 거쳐서 개인 최대주주의 세금 혜택이 줄어요. 그래서 이런 회사는 '다른 상장사' 쪽에 넣었어요. 이익 변화, 금리·환율 영향, 밸류업 공시 여부는 똑같이 맞춰 놓고 견줬어요. 세로 막대는 값이 있을 법한 범위(95%)예요. 위 카드의 {pp(polHolder["coef"])}는 2025년을 그 전 모든 해와 비교한 값이고, 이 그래프의 {es25_t}는 2025년을 2023년과 비교한 값이라 숫자가 달라요.</p>
{basis("배당을 10% 이상 늘린 회사 비율 (단순 비율) 보기", f'<div class="corr-table"><table><thead><tr><th>사업연도</th><th>개인 최대주주 회사</th><th>다른 상장사</th><th>차이</th></tr></thead><tbody>{trs}</tbody></table></div>')}
<p class="small"><b>같은 해 상법 개정의 영향과 나눠 보기 어려워요.</b> 2025년에는 이사가 주주 전체의 이익을 살피도록 상법도 바뀌었어요. 개인 최대주주가 직접 지배하는 회사일수록 이 압력을 더 크게 받았을 수 있어서, 이 차이에는 세금이 아닌 상법 몫도 섞였을 수 있어요.</p>
{basis("방법과 한계", f"<p>쉽게 말해, 개인 최대주주 회사와 다른 회사의 차이가 2025년에만 평소보다 얼마나 커졌는지 본 거예요(이중차분). 회사와 연도의 차이를 빼고, '개인 최대주주 회사 × 2025년' 계수를 봤어요. 우연인지는 회사들의 무리 구분을 1,000번 섞어 본 순열검정으로 보고, 미리 정한 두 검정(개인 최대주주 회사·기준선 거리)에 Holm 보정을 했어요. 개인 최대주주 회사는 2024 사업연도 최대주주가 사람(개인)이고 최대주주+특수관계인 보통주 지분이 30% 이상인 회사예요. 이 30%에는 계열 법인 몫도 섞여 있어요. 기준선 거리는 전년 숫자로 '올해 요건을 맞추려면 배당을 몇 % 늘려야 하나'를 재서 50% 이하면 가까움으로 봤어요. 제도 일정: 2024-07 정부안의 주주환원 촉진세제가 2024-12 국회에서 빠졌고, 2025-07-31 분리과세 발표, 2025-12-02 국회 통과(최고 30%), 2026-01-01 시행(국회예산정책처, 뉴시스·연합뉴스 보도). 제도 뒤 연도가 2025 하나뿐이고, 4개 업종 상장사만 봤어요. 우리 고배당기업은 2025년 배당 결과로 뽑혀서 대조군과 나눠 보지 않고 한 표본으로만 봤어요. 상관관계를 넘어 인과로 읽으려면 '제도가 없었다면 두 무리가 2025년에도 같은 차이로 움직였을 것'(평행추세)이라는 가정이 필요해요.</p>{pre_t}<p><b>비교 대상이 알맞은가</b> · '다른 상장사'에는 최대주주가 법인인 회사, 개인이지만 지분이 30%보다 적은 회사가 섞여 있어요. 개인 최대주주 회사와 규모·지배 구조·배당 습관이 다를 수 있어요. 또 다른 상장사의 개인 주주도 분리과세 혜택을 받아요. 그래서 이 값은 제도 전체의 효과가 아니라 '개인 최대주주 회사가 더 움직인 몫'에 가까워요.</p><p><b>같은 때 생긴 다른 일</b> · 2025년에는 상법 개정, 밸류업(기업가치 제고) 정책, 주가 상승, 회사 실적 변화가 함께 있었어요. 이익 변화와 2025-07-31 전 밸류업 공시는 맞춰 놓았지만, 그 뒤 공시나 상법 압력처럼 개인 최대주주 회사에 더 몰렸을 수 있는 일은 빼지 못했어요.</p><p><b>얼마나 큰 차이인가</b> · {pp(polHolder['coef'])}는 '배당을 10% 이상 늘린 회사 비율'의 차이예요. 개인 최대주주 회사는 제도 전 해마다 평균 {fixed(sum(preOwner) / len(preOwner), 1) if preOwner else '–'}%가 배당을 10% 이상 늘렸으니 작지 않은 차이예요. 개인 최대주주 회사 {fmt(polHolder['n_treated'] or 0)}곳으로 치면 약 {js_round((polHolder['coef'] or 0) * (polHolder['n_treated'] or 0))}곳이 평소보다 더 배당을 10% 이상 늘린 셈이에요. 다만 배당을 몇 원 더 줬는지는 이 결과로 알 수 없어요.</p><p><b>그래서</b> 이 결과는 '2025년에 개인 최대주주 회사가 배당을 늘린 비율이 평소보다 더 올랐다'는 데까지만 말해요. 제도 때문이라고 단정하지 않아요. 출처 partner.v_panel, partner.major_holder, partner.filing, partner.fs_line, core.core_behavior_fit·core_behavior_series(계산일 {esc(bh['built_at'])}) → report/분석/배당_제도효과_분석_결과.md.</p>")}''', "ch9")

    # ── 10장 ──
    if cc and sim:
        facts1 = "".join(f'<div><dt>{nm}</dt><dd>{pc((ind25("제조업", "우리 638사") or [None] * 8)[k])}</dd><dt>대조군 {pc((ind25("제조업", "대조군") or [None] * 8)[k])}</dt></div>'
                         for nm, k in (("배당성향", 4), ("ROE (번 돈 ÷ 자본)", 5), ("부채비율 (빚 ÷ 자본)", 6), ("배당한 회사 비율", 3)))
        reit_say = say('리츠(부동산투자회사)는 배당을 많이 해도 처음부터 대상이 아니에요. 법(조세특례제한법 제104조의27 ①1호 단서)이 "투자회사 및 그와 유사한 법인"을 빼는데, 시행령 제104조의24 ②와 법인세법 제51조의2 ①4호가 여기에 위탁관리·기업구조조정 리츠가 들어간다고 정해요. 고배당기업 638곳에 리츠가 하나도 없는 이유예요.', style="margin: 14px 0")
        body10 = f'''<div class="ch-no">10장</div>
<h2>배당을 덜 하는 회사들과 견줘 보면, <em>차이가 또렷해요</em></h2>
<p class="lead">고배당기업만 보면 무엇이 특별한지 알기 어려워요. 그래서 같은 업종(제조·도소매·건설·부동산임대) 상장사 <b>{fmt(sim["control_n"])}</b>곳을 비교 대상(대조군)으로 삼아, 고배당기업 638곳 중 같은 업종 <b>{ourN}</b>곳과 견줘 봤어요. 아래는 2025년 제조업 회사들의 한가운데 값이에요.</p>
<p class="small" style="margin-top: -8px">두 집단은 업종이 겹쳐요. 고배당기업 {ourAll}곳 중 <b>{ourN}곳</b>이 대조군과 같은 업종이에요({esc(ourByInd)}). 이 회사들은 대조군 자료에도 들어 있어서, 겹치는 곳은 우리가 확인한 값을 썼어요. 나머지 {ourAll - ourN}곳은 금융·IT·지주회사처럼 4개 업종 밖이라 비교에서 뺐어요.</p>
<div class="facts facts--big" style="grid-template-columns: repeat(4, 1fr)">{facts1}</div>
<h3>배당하는 회사 비율, <em style="color: var(--sea)">대조군은 해마다 줄었어요</em></h3>
<div class="card">{two_lines([[r[0], r[1], r[3]] for r in cc["trend"]], "%", "해마다 배당한 회사 비율: 고배당기업(같은 4개 업종)과 대조군")}</div>
<h3>배당을 10% 이상 늘린 회사, <em style="color: var(--sea)">2025년에만 크게 벌어졌어요</em></h3>
<p class="lead">2024년까지는 해마다 두 집단 차이가 가장 커도 <b>{fixed(incGapMax, 1)}%p</b>였어요(두 집단 모두 {js_round(min(incBefore))}~{js_round(max(incBefore))}% 사이). 그런데 2025년에는 고배당기업 <b>{pc(inc25[2] if inc25 else None)}</b>, 대조군 <b>{pc(inc25[4] if inc25 else None)}</b>로 벌어졌어요. 회사들이 제도에 맞추려고 배당을 늘린 건지, 고배당기업을 애초에 2025년 숫자로 뽑아서 그런 건지는 이 비교만으로 알 수 없어요. 그래서 9장에서 업종 전체를 한데 놓고 따로 살펴봤어요.</p>
<div class="card">{two_lines([[r[0], r[2], r[4]] for r in cc["increase"]], "%", "배당을 10% 이상 늘린 회사 비율", lambda y: f"{str(y - 1)[2:]}→{str(y)[2:]}")}</div>
<h3>대조군 회사에 고배당 요건을 그대로 적용해 보면 <em style="color: var(--sea)">{sim["eligible"]}곳</em>만 남아요</h3>
<div class="facts facts--big" style="grid-template-columns: repeat(4, 1fr)">
<div><dt>대조군 상장사</dt><dd>{fmt(sim["control_n"])}곳</dd><dt>코스피·코스닥만{" (모은 대조군 " + fmt(ct["companies"]) + "곳 중 코넥스·비상장·상장폐지 회사를 뺌)" if ct else ""}</dt></div>
<div><dt>배당 숫자로 요건을 맞춤</dt><dd>{sim["met"]}곳</dd><dt>배당성향·증가율 기준</dt></div>
<div><dt>법으로 빠지는 리츠</dt><dd>{sim["reit_excluded"]}곳</dd><dt>위탁관리·기업구조조정 리츠</dt></div>
<div><dt>고배당기업이 될 수 있는 곳</dt><dd>{sim["eligible"]}곳</dd><dt>대조군 중 {fixed(sim["eligible"] / sim["control_n"] * 100, 1)}%</dt></div>
</div>
{reit_say}'''
        if hOurs and hCtrl:
            so, sc = binShare(hOurs), binShare(hCtrl)
            body10 += f'''<h3>최대주주 지분도 <em style="color: var(--sea)">고배당기업 쪽이 더 많아요</em></h3>
<p class="lead">2025년 사업보고서에서 최대주주와 가족·계열사(특수관계인)가 가진 보통주 지분율을 더해 봤어요. 한가운데 회사 기준으로 고배당기업은 <b>{jsn(hOurs["median"])}%</b>, 대조군은 <b>{jsn(hCtrl["median"])}%</b>예요. 지분이 많을수록 배당으로 받는 돈도 커서 배당을 늘릴 이유가 더 있다고 볼 수 있어요. 다만 이 자료만으로는 지분이 많아서 배당을 많이 한 건지 알 수 없어요.</p>
<div class="facts facts--big" style="grid-template-columns: repeat(4, 1fr)">
<div><dt>지분율 가운데 값</dt><dd>{jsn(hOurs["median"])}%</dd><dt>대조군 {jsn(hCtrl["median"])}%</dt></div>
<div><dt>가운데 절반 범위</dt><dd>{jsn(hOurs["p25"])}~{jsn(hOurs["p75"])}%</dd><dt>대조군 {jsn(hCtrl["p25"])}~{jsn(hCtrl["p75"])}%</dt></div>
<div><dt>지분 50% 이상인 회사</dt><dd>{fixed(so[-1], 1) if so else ""}%</dd><dt>대조군 {fixed(sc[-1], 1) if sc else ""}%</dt></div>
<div><dt>최대주주가 개인인 회사</dt><dd>{jsn(hOurs["person_pct"])}%</dd><dt>대조군 {jsn(hCtrl["person_pct"])}%</dt></div>
</div>
<div class="card">{pair_bars([[nm, so[i], sc[i]] for i, (nm, _) in enumerate(hOurs["bins"])], "최대주주+특수관계인 지분율 구간별 회사 비율: 고배당기업(같은 4개 업종)과 대조군")}</div>
<p class="small">같은 업종끼리 봤어요(고배당기업 {fmt(hOurs["n"])}곳 · 대조군 {fmt(hCtrl["n"])}곳). 업종마다 봐도 제조·도소매·건설 모두 고배당기업 쪽 가운데 값이 {fixed(min(hGaps), 1)}~{fixed(max(hGaps), 1)}%p 높아요. 두 집단 모두 같은 규칙(source/core/major_holder.py)으로 셌어요. 겹치는 435곳은 대조군 원문으로도 세어 봤는데 우리 값과 모두 같았어요. 개인인지 법인인지는 이름으로 나눠서, 가리지 못한 '판단 불가'도 섞여 있어요.</p>'''

        def cell(r):
            if not r or r[4] is None:
                return "–"
            return f"평균 {'+' if r[4] > 0 else ''}{fixed(r[4], 2).replace('-', '−', 1)}%p ({fmt(r[3])}건{', 뚜렷함' if r[6] is not None and r[6] < 0.05 else ', 뚜렷하지 않음'})"

        trs = "".join(f'<tr><td>배당을 {"늘린다" if k == "증가" else "유지·줄인다"}는 공시</td><td>{cell(car(60, k, "우리 638사"))}</td><td>{cell(car(60, k, "대조군"))}</td></tr>' for k in ("유지·감소", "증가"))
        body10 += f'''<h3>"배당을 유지하거나 줄인다"는 공시 뒤, <em style="color: var(--sea)">대조군 주가가 더 약하게 움직였어요</em>(두 무리 차이는 검정하지 않음)</h3>
<div class="legal-table"><table><thead><tr><th>공시 뒤 60거래일 동안 시장 평균보다 더 오른 정도</th><th>고배당기업(같은 4개 업종)</th><th>대조군</th></tr></thead><tbody>{trs}</tbody></table></div>
{basis("방법과 한계", f"<p>가장 중요한 한계: 고배당기업은 2025년 숫자로 뽑혀서 잘된 회사가 많이 들어 있어요. 그래서 두 집단의 차이를 배당 때문이라고 읽으면 안 돼요. 자세한 방법: 대조군 데이터는 OpenDART·사업보고서 원문에서 모은 자료예요. 고배당기업 638곳과 겹치는 회사는 우리 값만 쓰고, 둘 다 코스피·코스닥 상장사만 봤어요(대조군의 코넥스·비상장·상장폐지 회사는 뺌). 무배당은 배당 표에 '-'로 적힌 해를 0으로 셌어요. 요건 시뮬레이션은 판정 엔진(source/core/judgement.py)에 배당소득 대신 현금배당총액을 넣었고, 이 방법은 고배당기업 638곳에서 실제 판정과 {fixed(sim['approx_agree'] / sim['approx_n'] * 100, 1)}% 같았어요. 리츠 종류는 각 회사 사업보고서로 확인했어요. 주가 반응은 1~4월 첫 배당 결정 공시(2023~2026년 6월)부터 60거래일 시장조정 초과수익률이고, 늘림·유지는 연간 보통주 주당배당금으로 나눴어요(6장과 방법이 달라요). 고배당기업 638곳은 2025년 숫자로 뽑혀서 '나중에 잘된 회사'가 들어 있을 수 있어요. 그래서 차이를 배당의 효과로 읽으면 안 돼요. 이 장의 한가운데 값과 비율은 몇 %p 다른지만 본 단순 비교이고, 우연인지 검정한 것은 주가 반응 표뿐이에요. 그 표의 '뚜렷함'은 한 집단의 평균이 0과 다른지 본 t검정(p &lt; 0.05)이고, 두 집단 사이의 차이를 검정한 것은 아니에요. 대조군은 사람 검토를 거치지 않았어요. 출처 partner.v_panel, partner.krx_price_daily(네이버 금융 수정주가, KRX 주가와 표본 대조), partner.analysis_result(계산일 {esc(cc['built_at'])}) → report/분석/대조군_비교분석_20261102.md.</p>")}'''
        ch(body10, "ch10")

    # ── 11장 ──
    if t:
        body11 = ('<div class="ch-no">11장</div><h2>이 숫자들, <em>믿어도 될까요?</em></h2>'
                  "<p class=\"lead\">고배당기업 숫자는 공시 원문까지 거슬러 올라가 확인할 수 있어요. 대조군 자료는 사람 검토를 거치지 않았고, 주가·지수는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가예요. 원문과 다른 칸은 두 값을 나란히 남겨 팀이 다시 확인했고, 원문에서 값을 찾지 못한 칸도 따로 셌어요. 아래 카드에 그 결과가 있어요.</p>")
        tt = t.get("totals")
        if tt:
            body11 += f'''<h3>팀이 모은 데이터를 <em style="color: var(--sea)">모두 합치면</em></h3>
<div class="facts facts--big facts--wide" style="margin-bottom: 10px">
<div><dt>수집한 원천 자료 전체</dt><dd>{fmt(tt["source_rows"])}행</dd><dt>공시·재무·주가·지분·경기 자료, 우선주 목록·배당금, 대조군 자료(표 {jsn(tt["source_tables"])}개)를 모두 더한 값</dt></div>
<div><dt>이 자료로 계산한 분석 결과</dt><dd>{fmt(tt["result_rows"])}행</dd><dt>판정·검증·분석 결과 표 {jsn(tt["result_tables"])}개 (원래 자료와 겹치게 세지 않음)</dt></div>
</div>
<div class="facts facts--big" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 14px">
<div><dt>회사</dt><dd>{fmt(tt["companies"])}곳</dd><dt>고배당기업 {fmt(t["companies"])} + 대조군 {fmt(ct["companies"] if ct else 0)}</dt></div>
<div><dt>회사·연도 재무</dt><dd>{fmt(tt["fin_rows"])}행</dd><dt>사업보고서 원문 기준</dt></div>
<div><dt>하루하루 주가</dt><dd>{fmt(tt["price_rows"])}줄</dd><dt>상장사 {fmt(tt["price_companies"])}곳 · 2018년부터</dt></div>
<div><dt>최대주주·특수관계인 지분</dt><dd>{fmt(tt["holder_rows"])}줄</dd><dt>사업보고서 최대주주 현황</dt></div>
</div>
<h3>그 안을 나눠 보면</h3>'''
        svd, dvd, rvw = t["source_verify"], t["dart_verify"], t["review"]
        if res:
            s1 = f"달랐던 {fmt(res['source_verify']['open'])}칸은 {'모두' if res['source_verify']['settled'] == res['source_verify']['open'] else fmt(res['source_verify']['settled']) + '칸'} 팀이 원문 보고 확인·정정"
            d1 = (f"일치 {fmt(dvd.get('일치', 0) + dvd.get('일치(단위 반올림)', 0))} · 다르거나 못 읽은 {fmt(res['dart_verify']['open'])}칸"
                  f"{'도 모두' if res['dart_verify']['settled'] == res['dart_verify']['open'] else ' 중 ' + fmt(res['dart_verify']['settled']) + '칸'} 팀 검토·원문 대조로 확인·정정")
        else:
            s1 = f"불일치 {fmt(svd.get('불일치', 0))} · 못 찾음 {fmt(svd.get('원문에서 못 찾음', 0))}"
            d1 = " · ".join(f"{k} {fmt(v)}" for k, v in dvd.items())

        def pair(lbl_a, va, lbl_b, vb, unit):
            return f'<dd class="dd-pair"><span><small>{lbl_a}</small>{fmt(va)}{unit}</span><span><small>{lbl_b}</small>{fmt(vb)}{unit}</span></dd>'

        def dd(v, unit):
            return f"<dd>{fmt(v)}{unit}</dd>"

        cells = [
            f'<div><dt>원문과 대조한 숫자 칸</dt><dd>{fmt(sv)}칸</dd><dt>일치 {fmt(svd.get("일치", 0))} ({fixed(svd.get("일치", 0) / sv * 100, 1)}%) · {s1}</dt></div>',
            f'<div><dt>팀이 원문을 보고 검토한 값</dt><dd>{fmt(rv)}개</dd><dt>확인완료 {fmt(rvw.get("확인완료", 0))} · 정정 {fmt(rvw.get("정정됨(배제)", 0))} · 원문 대조로 고침 {fmt(rvw.get("원문 대조", 0))} · 원문에 없음 {fmt(rvw.get("확인불가", 0))}</dt></div>',
            f'<div><dt>DART 공시 원문 재대조</dt><dd>{fmt(sum(dvd.values()))}칸</dd><dt>{d1}</dt></div>',
            f'<div><dt>밸류업(기업가치 제고) 공시</dt><dd>{fmt(t["policy_filings"])}건</dd><dt>원본 파일 {fmt(t["policy_documents"])}개 · 전 쪽 글자 인식(OCR) {fmt(t["ocr_pages"])}쪽</dt></div>',
            f'<div><dt>판정한 회사{"와 대조군" if ct else ""}</dt>{pair("고배당기업", t["companies"], "대조군", ct["companies"], "곳") if ct else dd(t["companies"], "곳")}'
            f'<dt>KIND 고배당기업 목록 전체{" · 대조군은 같은 4개 업종, 재무 " + fmt(ct["fin_rows"]) + "행에 원문 링크를 모두 달아 둠" if ct else ""}</dt></div>',
            f'<div><dt>주가 데이터</dt>{pair("고배당기업", t["price_rows"], "대조군", ct["price_rows"], "줄") if ct else dd(t["price_rows"], "줄")}'
            f'<dt>공시 뒤 주가 반응 계산 사례 {fmt(t["event_cases"])}건{" · 대조군 상장사 " + fmt(ct["price_companies"]) + "곳, 우리 KRX 주가와 표본 8곳 모든 날 같음" if ct else ""}</dt></div>',
            f'<div><dt>최대주주·특수관계인 지분</dt>{pair("고배당기업", t["holder"]["rows"], "대조군", ct["holder_rows"], "줄") if ct else dd(t["holder"]["rows"], "줄")}'
            f'<dt>2025 사업보고서 {fmt(t["holder"]["companies"])}곳 · 지분율 확인 {fmt(t["holder"]["pct"])}곳{" · 대조군 " + fmt(ct["holder_companies"]) + "곳, 2017~2025 원문에서 값을 읽은 줄만" if ct else ""}</dt></div>',
        ]
        if ct:
            cause = f"{fmt(ct['overlap_diff'] - ct['overlap_unexplained'])}칸 확인" if ct["overlap_unexplained"] else "모두 확인"
            cells.append(f'<div><dt>겹친 {fmt(ct["overlap"])}곳으로 다시 맞춰 봄</dt><dd>{fmt(ct["overlap_diff"])}칸</dd><dt>다른 칸 원인 {cause} · 우리 값 {fmt(ct["corrected"])}칸을 원문으로 정정</dt></div>')
        body11 += f'<div class="facts facts--big facts--4">{"".join(cells)}</div>'
        body11 += basis("근거", "<p>위 숫자는 모두 데이터베이스에서 바로 센 값이에요: core.core_source_verify, core.core_review_value, core.core_dart_verify (달랐던 칸의 처리는 팀 전수 검산표 검토본의 행별 검토 상태와 원문 대조 파일로 셈: source/scripts/verify_resolution.py → data/processed/analysis/verify_resolution.json), raw.policy_filing·policy_document·policy_page_ocr, raw.krx_price_daily, core.core_event_car. 대조군은 partner.company·financial_year·krx_price_daily와 겹침 원인표(data/partner/…/겹침_차이_원인_*.csv)·원문 대조 파일(data/processed/review/원문대조_*.csv). 주가·지수는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가예요.</p>")
        ch(body11, "ch11")

if not a and not error:
    md('<div class="loading">분석 결과를 불러오는 중…</div>')
_ = math  # (math는 그림 모듈과 같은 반올림 확인용으로 남겨 둠)
