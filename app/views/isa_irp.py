"""ISA·IRP 안내 (웹 app/web/src/pages/IsaIrp.tsx): 금융소득 2천만 원 이하 고객에게 쓸 만한 배당 절세 계좌를 계산으로만 보여 준다.
계산은 api.isaIrp(core.isa_irp)가 한다. 상품 이름·가입 버튼은 넣지 않고, 가입 상담은 PB에게 잇는다."""
import streamlit as st

from common import api, error, esc, fmt, html, load, moa, won

PAGES = st.session_state["_pages"]
MAN = 10_000


def permil_pct(p: float) -> str:
    return f"{fmt(p / 10, 1)}%"


BRACKET_KEYS = ("low", "mid", "high", "biz_low", "biz_mid", "biz_high")
KIND_TITLE = {"wage": "근로소득만 있어요 · 총급여", "business": "사업소득 등이 있어요 · 종합소득금액"}
IRP_LINE = {"wage": "총급여 5,500만 원", "business": "종합소득금액 4,500만 원"}

pick = st.query_params.get("b")
bracket = pick if pick in BRACKET_KEYS else None

html(f"""<div class="wealth isa-irp"><header class="wealth-hero">
  <div>
    <span class="bank-mark">ISA · IRP</span>
    <h1>“그럼 소액 투자자는 쓸 게 없나요?”</h1>
    <p>금융소득이 2천만 원 이하라면 고배당 분리과세를 신청해도 세금 차이가 0원이에요. 이때는 ISA·IRP로 배당 세금이 달라질 수 있어요(계산 예시).</p>
  </div>
  <img src="{moa('curious')}" alt="" />
</header></div>""")
c1, c2, _ = st.columns([1, 1.6, 3])
c1.markdown("[내 구간 보기](#bracket)")
if c2.button("먼저 내 배당 점검하기"):
    st.switch_page(PAGES["check"])
html('<div class="wealth"><p class="notice">ⓘ <span>추천이 아니라 계산이에요. 혜택과 제약을 함께 보여 드리고, 가입 상담은 PB에게 이어 드려요.</span></p></div>')

profit = st.session_state.get("ii_profit", 300) * MAN
irp = st.session_state.get("ii_irp", 900) * MAN
pension = st.session_state.get("ii_pension", 0) * MAN
g, err = load(api.isaIrp, bracket, profit, irp, pension)
if err:
    error(err)
    st.stop()

cmp = "".join(f'<div class="ii-cmp-col" role="row"><b role="rowheader">{esc(c["name"])}</b>'
              f'<p role="cell"><span class="tag">대상</span>{esc(c["who"])}</p><p role="cell"><span class="tag">혜택</span>{esc(c["benefit"])}</p>'
              f'<p role="cell"><span class="tag">제약</span>{esc(c["limit"])}</p></div>' for c in g["compare"])
html(f"""<div class="wealth isa-irp"><section class="wealth-sec"><h2 id="cmp">세 제도는 대상이 거의 겹치지 않아요</h2>
<div class="ii-cmp" role="table" aria-label="고배당 분리과세, ISA, IRP 비교">{cmp}</div>
<p class="small">분리과세 대상(금융소득이 많은 사람)과 ISA 가입자(소액 투자자)는 대부분 겹치지 않아요. IRP 공제율은 지방소득세 포함, {esc(g['checked'])} 기준 현행 제도예요.</p>
</section></div>""")


# 금액 구간별 세율 한눈에 (웹 components/RateHeat.tsx). 숫자는 api.isaIrp의 rate_table(core.isa_irp.rate_table)
def pct(permil: int) -> str:
    return f"{permil / 10:.1f}%"


def man_eok(n: int) -> str:
    return f"{fmt(n / 1e8, 1)}억" if n >= 1e8 else f"{fmt(n / 1e4)}만"


def range_label(lo: int, hi: int | None) -> str:
    return f"{man_eok(lo)} 초과" if hi is None else f"{man_eok(hi)} 이하" if lo == 0 else f"{man_eok(lo)}~{man_eok(hi)}"


STOPS = [(0, (238, 242, 255)), (0.5, (61, 107, 255)), (1, (20, 33, 107))]  # 0% 연한 파랑 → 25% sea → 50% 짙은 남색


def heat(permil: int) -> str:
    t = min(1, permil / 500)
    i = 0 if t <= STOPS[1][0] else 1
    (a, ca), (b, cb) = STOPS[i], STOPS[i + 1]
    k = (t - a) / (b - a)
    c = ",".join(str(round(v + (w - v) * k)) for v, w in zip(ca, cb))
    return f"background:rgb({c});color:{'#fff' if t > 0.42 else 'var(--ink)'}"


def weight(permil: int) -> str:
    return "🪶" if permil < 100 else "🎒" if permil < 200 else "🧳" if permil < 300 else "🏋️" if permil < 450 else "🪨"


T = g["rate_table"]
rows, n = T["rows"], len(T["rows"])
html('<div class="wealth isa-irp"><section class="wealth-sec" id="rates"><h2>금액이 커지면 세금 가방은 얼마나 무거워질까? <span class="tag">2026년 · 지방소득세 포함</span></h2>'
     '<p class="ii-lead">같은 금액 구간에서 네 제도가 떼는 세율을 나란히 놓았어요. 색이 진할수록 무거워요. 아래 막대를 움직여 보세요.</p></section></div>')
labels = [range_label(r["lower"], r["upper"]) for r in rows]
at = labels.index(st.select_slider("금액 움직여 보기", options=labels, value=labels[4], key="rh_at"))
row = rows[at]
gap = row["basic_permil"] - row["separate_permil"]
tail = (f"두 세율 차이는 {pct(gap)}p예요. 분리과세는 요건을 채운 회사의 현금배당에만 쓸 수 있어요." if gap > 0 else
        f"이 구간은 종합소득세 세율이 더 낮아요. 그런데 금융소득이 {man_eok(T['threshold'])} 원 이하면 종합과세 없이 원천징수 {pct(T['normal_permil'])}로 끝나요.")
cells = "".join(
    f'<div class="rh-row{" on" if i == at else ""}" role="row">'
    f'<span class="rh-label" role="rowheader" style="grid-row:{i + 2}"><span aria-hidden="true">{weight(r["basic_permil"])}</span>{range_label(r["lower"], r["upper"])}</span>'
    f'<span class="rh-cell" role="cell" style="{heat(r["basic_permil"])};grid-row:{i + 2};grid-column:2;display:grid;place-items:center">{pct(r["basic_permil"])}</span>'
    f'<span class="rh-cell" role="cell" style="{heat(r["separate_permil"])};grid-row:{i + 2};grid-column:3;display:grid;place-items:center">{pct(r["separate_permil"])}</span></div>'
    for i, r in enumerate(rows))
isa, irp = T["isa"], T["irp"]
html(f"""<div class="wealth isa-irp"><div class="rh">
<div class="rh-pick"><img src="{moa('base' if gap > 0 else 'curious')}" alt="" />
<div class="rh-bubble" aria-live="polite"><b>{range_label(row['lower'], row['upper'])} 구간이라면</b>
<p>여기서 더 버는 <strong>1만 원</strong>마다 떼는 세금이 종합소득세는 <strong>{fmt(row['basic_permil'] * 10)}원</strong>, 고배당 분리과세는 <strong>{fmt(row['separate_permil'] * 10)}원</strong>이에요.</p>
<p class="small">{tail}</p></div></div>
<div class="rh-scroll"><div class="rh-grid" role="table" aria-label="금액 구간별 세율 비교 (지방소득세 포함)" style="grid-template-rows:auto repeat({n}, 52px)">
<div class="rh-head rh-corner" role="columnheader">금액 구간</div>
<div class="rh-head" role="columnheader"><b>종합소득세</b><span>과세표준 · 한계세율</span></div>
<div class="rh-head" role="columnheader"><b>고배당 분리과세</b><span>고배당기업 배당액</span></div>
<div class="rh-head" role="columnheader"><b>ISA</b><span>계좌 안 순이익</span></div>
<div class="rh-head" role="columnheader"><b>IRP 연금으로 받기</b><span>1년 사적연금 수령액</span></div>
{cells}
<div class="rh-tall" role="cell" style="{heat(isa['over_permil'])};grid-column:4;grid-row:2 / span {n}"><strong>{pct(isa['over_permil'])}</strong>
<span>순이익 {man_eok(isa['free_general'])} 원까지 0원<br />(서민형 {man_eok(isa['free_low_income'])} 원)<br />넘는 부분은 금액과 상관없이 {pct(isa['over_permil'])}</span><em>🧺 바구니 안에는 계단이 없어요</em></div>
<div class="rh-tall rh-tall--top" role="cell" style="{heat(irp['pension_permil'][1])};grid-column:5;grid-row:2"><strong>{pct(irp['pension_permil'][0])}~{pct(irp['pension_permil'][1])}</strong>
<span>1년 {man_eok(irp['separate_cap'])} 원 이하 · 나이별</span></div>
<div class="rh-tall" role="cell" style="{heat(irp['over_permil'])};grid-column:5;grid-row:3 / span {n - 1}"><strong>{pct(irp['over_permil'])}</strong>
<span>1년 {man_eok(irp['separate_cap'])} 원을 넘으면<br />{pct(irp['over_permil'])} 분리과세 또는<br />종합과세 중 골라요</span><em>⏳ 55세 전에 깨면 {pct(irp['early_permil'])}</em></div>
</div></div>
<div class="rh-legend" aria-hidden="true"><span>0%</span><i></i><span>50%</span></div>
<ul class="rh-notes small">
<li>같은 줄이라도 재는 돈이 달라요. 종합소득세는 모든 종합소득을 더해 공제한 과세표준, 고배당 분리과세는 요건을 채운 회사에서 받은 현금배당액(ETF·펀드 제외), ISA는 계좌 안 순이익, IRP는 1년 연금 수령액 기준이에요.</li>
<li>누진세율은 그 구간을 넘는 부분에만 붙어요. 금융소득이 {man_eok(T['threshold'])} 원 이하면 종합과세 없이 원천징수 {pct(T['normal_permil'])}로 끝나요.</li>
<li>세율은 모두 지방소득세를 포함했어요. 세액 계산 예시이고, 어느 쪽을 고르라는 권유가 아니에요. 근거: {esc(T['source'])}</li>
</ul></div>
<section class="wealth-sec" id="bracket"><h2>소득이 어느 구간인가요?</h2></section></div>""")

for kind in ("wage", "business"):
    html(f'<h3 class="ii-kind">{KIND_TITLE[kind]}</h3>')
    labels = {b["key"]: f"{b['label']}  \nISA {b['isa_type']} {fmt(b['isa_free'] / MAN)}만 원 · IRP 공제 {permil_pct(b['irp_permil'])}"
              for b in g["brackets"] if b.get("kind", "wage") == kind}
    if kind == "business":
        labels[""] = "잘 모르겠어요  \n두 공제율을 모두 계산해요"
    cols = st.columns(4)
    for col, (k, lab) in zip(cols, labels.items()):
        if col.button(lab, key=f"b_{k or 'none'}", type="primary" if (bracket or "") == k else "secondary", use_container_width=True):
            if k:
                st.query_params["b"] = k
            else:
                st.query_params.pop("b", None)
            st.rerun()
html('<p class="small">근로소득만 있으면 총급여(근로소득 원천징수영수증 21번 칸), 사업·임대·연금소득 등이 함께 있으면 종합소득금액(종합소득세 신고서)으로 봐요. ISA 유형은 가입 직전 해 소득, IRP 공제율은 돈을 넣는 해 소득으로 정해요. 여기서는 두 해 소득이 같은 구간이라고 보고 계산해요. 몰라도 그대로 진행할 수 있어요.</p>'
     '<div class="wealth isa-irp"><section class="wealth-sec ii-calc"><h2 id="calc">같은 돈이라도 계좌에 따라 세금이 달라요</h2></section></div>')


def man_input(label: str, key: str, default: int, hint: str | None = None) -> None:
    st.number_input(f"{label} (만 원)", min_value=0, step=10, value=default, key=key)
    if hint:
        html(f'<span class="small">{hint}</span>')


left, right = st.columns(2)
with left, st.container(border=True):
    html('<h3 style="margin:0">ISA · 이자·배당 순이익을 받으면</h3>')
    man_input("3년 동안 번 이자·배당 순이익", "ii_profit", 300)
    bars = ""
    for key, name, tax in [("normal", "일반 계좌 (15.4%)", g["isa"]["normal"]), ("general", "ISA 일반형", g["isa"]["general"]), ("low", "ISA 서민형", g["isa"]["low_income"])]:
        ch = g["chosen"]
        mine = ch and ((key == "low" and ch["isa_type"] == "서민형") or (key == "general" and ch["isa_type"] == "일반형"))
        w = max(2, tax / g["isa"]["normal"] * 100) if g["isa"]["normal"] else 2
        bars += f'<li class="{"mine" if mine else ""}"><span>{name}{"<em>내 구간</em>" if mine else ""}</span><i style="width:{w}%"></i><b>{won(tax)}</b></li>'
    html(f"""<div class="isa-irp"><ul class="ii-bars">{bars}</ul>
<p class="small">일반형은 200만 원, 서민형은 400만 원까지 세금이 없고, 넘는 부분에 9.9%를 매겨요. 계좌 안 순이익 기준이에요. 근거: {esc(g['isa']['source'])}</p>
<div class="ii-limit"><b>함께 볼 제약</b> 3년은 꼭 채워야 해요 · 1년 2,000만 원, 모두 1억 원까지 · 직전 3년 안에 금융소득종합과세 대상이었다면 가입할 수 없어요</div></div>""")
with right, st.container(border=True):
    html('<h3 style="margin:0">IRP · 1년에 넣으면</h3>')
    man_input("IRP에 넣을 돈", "ii_irp", 900)
    man_input("연금저축에 넣을 돈", "ii_pension", 0, "연금저축은 600만 원까지만 세고, 둘을 합쳐 900만 원까지 공제해요.")
    irp_line = IRP_LINE[g["chosen"].get("kind", "wage")] if g["chosen"] else "총급여 5,500만 원 · 종합소득금액 4,500만 원"
    refund = "".join(f'<li><span>{irp_line} {"이하" if r["rate_permil"] == 165 else "초과"} ({permil_pct(r["rate_permil"])})</span><b>{won(r["credit"])}</b></li>' for r in g["irp"])
    over = f'<p class="small ii-over">한도를 넘은 {won(g["irp"][0]["over"])}은 공제 셈에서 빠져요.</p>' if g["irp"][0]["over"] > 0 else ""
    html(f"""<div class="isa-irp"><ul class="ii-refund">{refund}</ul>{over}
<p class="small">연말정산 때 세금에서 빼 주는 금액(최대)이에요. 확정 환급액이 아니에요. 낼 세금(원천징수영수증 71번 결정세액)이 이보다 적으면 그만큼만 빼 줘요. 근거: {esc(g['irp'][0]['source'])}</p>
<div class="ii-limit"><b>함께 볼 제약</b> 55세 이후 연금으로 받아야 해요 · 중간에 깨면 16.5%를 내요 · 받을 때 연금소득세 3.3~5.5%</div></div>""")

E, W = g["isa_early"], g["irp_withdraw"]
item = lambda icon, title, text: f'<div class="ii-item"><span aria-hidden="true">{icon}</span><b>{esc(title)}</b><p>{esc(text)}</p></div>'  # noqa: E731
steps = "".join(f'<li><span class="flow-no">{i + 1}</span><b>{esc(s["title"])}</b><span class="small">{esc(s["text"])}</span></li>' for i, s in enumerate(W["steps"]))
tax = "".join(f'<div class="ii-item ii-tax"><b>{esc(t["case"])}</b><span class="small">{esc(t["examples"])}</span><p>{esc(t["tax"])}</p></div>' for t in W["tax"])
facts = "".join(f'<tr><th scope="row">{esc(f["item"])}</th><td>{esc(f["isa"])}</td><td>{esc(f["irp"])}</td></tr>' for f in g["facts"])
rcpt = "".join(f'<tr><th scope="row">{esc(r["no"])}번</th><td>{esc(r["item"])}</td><td>{esc(r["use"])}</td></tr>' for r in g["receipt"])
why = "".join(f'<li><b>{esc(w["law"])}</b> {esc(w["text"])}</li>' for w in g["why_not"])
html(f"""<div class="wealth isa-irp">
<p class="notice">ⓘ <span>{esc(g['notice'])}</span></p>
<section class="wealth-sec"><h2 id="early">ISA · 3년 전에 돈이 필요하면</h2>
<p class="ii-lead">{esc(E['problem'])} 계좌를 깨기 전에 이런 방법이 있어요.</p>
<div class="ii-cards">{''.join(item(w['icon'], w['title'], w['text']) for w in E['ways'])}</div>
<p class="small">근거: {esc(E['source'])}</p></section>
<section class="wealth-sec"><h2 id="withdraw">IRP · 중간에 꺼낼 수 있는 법정 사유</h2>
<p class="ii-lead">IRP는 55세 전에는 원칙적으로 꺼낼 수 없지만, 아래 사유라면 중도인출을 신청할 수 있어요.</p>
<div class="ii-cards">{''.join(item(r['icon'], r['title'], r['text']) for r in W['reasons'])}</div>
<h3 class="ii-sub">이렇게 신청해요</h3><ol class="flow">{steps}</ol>
<h3 class="ii-sub">꺼낼 때 내는 세금</h3><div class="ii-cards">{tax}</div>
<p class="small">{esc(W['note'])} 근거: {esc(W['source'])}</p></section>
<section class="wealth-sec"><h2 id="facts">자세한 숫자 <span class="tag">{esc(g['checked'])} 현행</span></h2>
<div class="ii-table-wrap"><table class="ii-table"><thead><tr><th scope="col">항목</th><th scope="col">ISA (개인종합자산관리계좌)</th><th scope="col">IRP (개인형 퇴직연금)</th></tr></thead><tbody>{facts}</tbody></table></div>
<p class="small">{esc(g['facts_note'])}</p><p class="small">출처: {esc(g['facts_source'])}</p></section>
<section class="wealth-sec"><h2 id="rcpt">원천징수영수증, 이 칸만 보면 돼요</h2>
<div class="ii-table-wrap"><table class="ii-table"><thead><tr><th scope="col">칸</th><th scope="col">항목</th><th scope="col">쓰는 곳</th></tr></thead><tbody>{rcpt}</tbody></table></div>
<p class="small">영수증 2쪽에 있어요. 출처: {esc(g['receipt_source'])}</p></section>
<section class="wealth-sec"><details class="basis ii-why"><summary id="why">왜 ‘추천’하지 않고 계산만 하나요?</summary>
<ul>{why}</ul><p class="small">그래서 원픽은 내 구간의 혜택과 제약을 함께 계산해 보여 주고, 가입 상담은 PB에게 이어요. 법률 자문이 아니에요.</p></details></section>
<section class="wealth-sec"><h2 id="next">더 알아보기</h2></section></div>""")

NEXT = [("🗂️", "PB 상담", "가입할지, 얼마나 넣을지는 PB와 함께 정해요. 상품 권유는 PB 상담에서만 해요.", "상담 신청", ("consult", {"type": "general"})),
        ("🧺", "ISA 글 읽기", "바구니 계좌가 어떻게 세금을 덜 떼는지, 조문과 함께 쉽게 풀었어요.", "금융 상식", ("column", {"id": "isa"})),
        ("🏦", "IRP 글 읽기", "넣을 때 돌려받고, 꺼낼 때 내는 세금을 순서대로 봐요.", "금융 상식", ("column", {"id": "irp"}))]
for col, (icon, name, line, cta, (to, q)) in zip(st.columns(3), NEXT):
    with col:
        html(f'<div class="svc" style="min-height:170px"><span class="svc-icon" aria-hidden="true">{icon}</span><b>{name}</b><span>{line}</span></div>')
        if st.button(cta, key=f"next_{name}", type="primary"):
            st.switch_page(PAGES[to], query_params=q)
