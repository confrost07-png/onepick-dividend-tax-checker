"""A은행 자산관리서비스 (웹 app/web/src/pages/Wealth.tsx): 서비스 소개와 PB센터 14곳 찾기. 모형 화면이다.
지점·문구는 app/web/src/bank.ts를 그대로 뽑은 web_text.json에서 읽는다."""
import streamlit as st

from common import esc, html, moa, web_text

PAGES = st.session_state["_pages"]
B = web_text()["bank"]
BANK, BRANCHES, REGIONS = B["BANK"], B["BRANCHES"], B["REGIONS"]

SERVICES = [
    {"icon": "🧾", "name": "세무상담", "line": "분리과세를 신청할지, 내 소득에서 무엇이 달라지는지 세무 전문가가 함께 봐요.", "to": ("consult", {"type": "separate"}), "cta": "세무상담 신청"},
    {"icon": "📮", "name": "금융소득 종합과세 신고대행", "line": "5월 종합소득세 확정신고를 제휴 세무법인이 대신 해요. 신고대행 수수료는 은행이 내는 것으로 가정했어요(기획안, 시연용).", "to": ("consult", {"type": "filing"}), "cta": "신고대행 신청"},
    {"icon": "🔎", "name": "원픽 배당 점검", "line": "내 종목이 내년에도 분리과세 대상인지, 신청하면 세금이 얼마나 달라지는지 미리 계산해요.", "to": ("check", {}), "cta": "점검하기"},
    {"icon": "🗂️", "name": "PB 자산관리 상담", "line": "예금·투자·은퇴 준비를 PB(프라이빗 뱅커)와 한꺼번에 살펴봐요. 상품 권유는 PB 상담에서만 해요.", "to": ("consult", {"type": "general"}), "cta": "상담 신청"},
]
FLOW = [
    {"step": "미리 보기", "who": "원픽 점검", "line": "대상 여부와 세액 차이를 계산해요"},
    {"step": "판단하기", "who": "세무상담", "line": "신청할지 세무 전문가와 정해요"},
    {"step": "신고하기", "who": "신고대행", "line": "5월 확정신고와 분리과세신청서 제출"},
]


def go(page: str, params: dict) -> None:
    st.switch_page(PAGES[page], query_params=params or None)


html(f"""<div class="wealth"><header class="wealth-hero">
  <div>
    <span class="bank-mark">{BANK}</span>
    <h1>{BANK} 자산관리서비스</h1>
    <p>배당 세금, 신고, 자산관리를 한곳에서. 원픽 점검으로 미리 보고, 필요하면 세무 전문가에게 이어 드려요.</p>
  </div>
  <img src="{moa('happy')}" alt="" />
</header></div>""")
c1, c2, _ = st.columns([1, 1, 4])
if c1.button("세무상담 신청", type="primary", use_container_width=True):
    go("consult", {"type": "separate"})
c2.markdown("[PB센터 찾기](#branches)")
html(f'<div class="wealth"><p class="notice">ⓘ <span>{esc(B["MOCK_NOTE"])}</span></p></div>')

html('<div class="wealth"><section class="wealth-sec"><h2 id="svc">이런 서비스가 있어요</h2></section></div>')
for col, s in zip(st.columns(4), SERVICES):
    with col:
        html(f'<div class="svc" style="min-height:230px"><span class="svc-icon" aria-hidden="true">{s["icon"]}</span><b>{s["name"]}</b><span>{s["line"]}</span></div>')
        if st.button(s["cta"], key=f"svc_{s['name']}", type="primary"):
            go(*s["to"])

flow = "".join(f'<li><span class="flow-no">{i + 1}</span><b>{f["who"]}</b><span class="small">{f["step"]} · {f["line"]}</span></li>' for i, f in enumerate(FLOW))
html(f"""<div class="wealth"><section class="wealth-sec" aria-labelledby="flow">
  <h2 id="flow">이렇게 이어져요</h2>
  <ol class="flow">{flow}</ol>
  <p class="small">기존 서비스는 신고 때(3단계)부터 도와줬어요. 원픽은 그 앞의 1단계를 채워요. 세법 해석과 신청 여부 판단은 세무 전문가가 해요.</p>
</section>
<section class="wealth-sec" id="branches"><h2 id="br">PB센터 찾기 <span class="tag">{len(BRANCHES)}곳</span></h2></section></div>""")

opts = ["전체", *REGIONS]
region = st.pills("지역 고르기", opts, default="전체", label_visibility="collapsed",
                  format_func=lambda r: r if r == "전체" else f"{r} {sum(b['region'] == r for b in BRANCHES)}") or "전체"
shown = BRANCHES if region == "전체" else [b for b in BRANCHES if b["region"] == region]
cols = st.columns(4)
for i, b in enumerate(shown):
    with cols[i % 4]:
        days = "".join(f'<i class="{"on" if d in b["days"] else ""}">{d}</i>' for d in ["월", "화", "수", "목", "금"])
        html(f"""<div class="branch"><div class="branch-top"><b>{BANK} PB센터 {b['name']}점</b>{'<span class="badge badge--ok">화상 가능</span>' if b['video'] else ''}</div>
<span class="small">{b['area']}</span>
<span class="branch-days" aria-label="세무 전문가 상담 요일">{days}</span>
<span class="small">세무 전문가 상담 요일 · 예약제</span></div>""")
        if st.button("이 지점에서 상담 신청", key=f"br_{b['id']}"):
            go("consult", {"type": "separate", "way": "visit", "branch": b["id"]})
