"""홈 (웹 app/web/src/pages/Home.tsx)"""
import streamlit as st

from common import api, error, html, judge_year_html, load, loading, moa, tournament

PAGES = st.session_state["_pages"]
f, err = load(api.funnel)
met = f["ga"] + f["na"] + f["na_deficit"] if f else 0
fail = f["fail2"] + f["fail3"] if f else 0
hold = f["hold_missing"] + f["hold_zero"] if f else 0

c1, c2 = st.columns([1.25, 0.75], vertical_alignment="center")
with st.container(key="hero"):
    html(f"""<section class="hero" style="margin-top:4px">
  <div>
    <h1>내 배당, 내년에도<br />분리과세 될까요?</h1>
    <p>어려운 세법은 모아가 쉬운 말로 풀어 드려요. 회사 이름만 넣어 보세요.</p>
  </div>
  <img class="moa-float" src="{moa('base')}" alt="원픽 마스코트 모아" />
</section>""")
    # 웹: 큰 검색창 + 예시 칩(삼성전자·케이티앤지). Streamlit은 위쪽 '회사 찾기'와 같은 목록 상자를 쓴다
    q1, q2, q3, _ = st.columns([4, 1, 1, 2], vertical_alignment="center")
    with q1:
        companies = api.companyList()
        names = {f"{c['name']} · {c['code']}": c["code"] for c in companies if not c.get("pref_of")}
        pick = st.selectbox("회사 이름 입력", list(names), index=None, placeholder="회사 이름 입력", label_visibility="collapsed", key="home_find")
        if pick:
            st.session_state.pop("home_find", None)
            st.switch_page(PAGES["company"], query_params={"code": names[pick]})
    with q2:
        if st.button("삼성전자", use_container_width=True):
            st.switch_page(PAGES["company"], query_params={"code": "005930"})
    with q3:
        if st.button("케이티앤지", use_container_width=True):
            st.switch_page(PAGES["company"], query_params={"code": "033780"})

if err:
    error(f"숫자를 불러오지 못했어요: {err}")

left, right = st.columns([1.35, 0.65])
with left:
    html(f"""<section class="card home-tour" style="padding-bottom:12px"><h2>고배당 {f['total'] if f else 638}곳의 법 토너먼트</h2>
<p class="small" style="margin:0 0 14px">동전 하나가 회사 하나예요. 법이 정한 문 세 개를 지나야 분리과세 대상이 돼요.</p></section>""")
    if f:
        tournament(f, compact=True, key="home-tour")
    else:
        loading()
with right:
    stack = "".join(f'<span style="width:{n / f["total"] * 100}%"></span>' for n in (met, fail, hold)) if f else ""
    html(f"""<section class="card verdict" aria-label="2026 판정">
  <span class="tag">2026 판정 · 현재 해석 기준</span>
  <p style="margin:12px 0 0;font-weight:800">{f['total'] if f else '…'}곳 중</p>
  <b class="big-n num">{met if f else '…'}</b><span class="round" style="font-size:28px"> 곳 통과</span>
  {f'<div class="stack" aria-hidden="true">{stack}</div>' if f else ''}
  <ul class="legend">
    <li><i style="background:var(--sea)"></i>충족<em>{met if f else ''}</em></li>
    <li><i style="background:var(--no)"></i>미충족<em>{fail if f else ''}</em></li>
    <li><i style="background:#C9CFD9"></i>판정 보류<em>{hold if f else ''}</em></li>
  </ul>
  <p class="small" style="margin:14px 0 0">판정 보류는 자료를 확인하는 중이거나, 해석이 아직 정해지지 않은 회사예요.</p>
  {judge_year_html()}
</section>""")

DOORS = [
    ("check", "", "내 배당 점검하기", "보유 종목과 소득을 대화로 답하면, 분리과세를 신청했을 때 세금이 얼마나 달라지는지 계산해요.", "점검 시작 →", "base"),
    ("analysis", "", "데이터 이야기 보기", "올해 붙은 회사 절반이 다음 해엔 떨어졌어요. 숫자로 따라가 보세요.", "이야기 보기 →", "curious"),
    ("column", " door--column", "모아의 금융 상식 칼럼", "배당은 피자 나눠 먹기, 초과수익률은 달리기 시합. 어려운 금융 용어를 그림으로 만져 보며 알아봐요.", "칼럼 읽기 →", "happy"),
]
for col, (to, cls, h3, p, go, mood) in zip(st.columns(3), DOORS):
    with col:
        bg = "background:var(--coin-soft)" if to == "analysis" else ""
        html(f'<div class="door{cls}" style="{bg}"><h3>{h3}</h3><p>{p}</p><span class="go">{go}</span><img src="{moa(mood)}" alt="" /></div>')
        st.page_link(PAGES[to], label=go)
