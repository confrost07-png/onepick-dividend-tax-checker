"""원픽 Streamlit 화면: 웹(app/web/src, React)과 같은 화면·문구·숫자를 Streamlit으로 본뜬 것.

실행(저장소 맨 위 폴더에서): .venv/bin/streamlit run app/app.py
- 숫자는 웹이 부르는 FastAPI 함수(source/api/main.py)를 그대로 부른다. 8000 서버를 따로 띄우지 않아도 된다.
- 웹 코드·API·DB는 바꾸지 않는다. 라우트 순서와 이름은 app/web/src/App.tsx를 따른다.
"""
import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from common import api, esc, html, persona_id, set_persona, setup

st.set_page_config(page_title="원픽", page_icon=str(__import__("common").WEB / "public" / "moa" / "moa_base.webp"), layout="wide")

V = "views/"
# app/web/src/App.tsx TITLES와 주 메뉴(NavLink) 순서. 메뉴에 없는 화면은 숨김 페이지로 둔다
PAGES = {
    "home": st.Page(V + "home.py", title="홈", url_path="home", default=True),
    "check": st.Page(V + "check.py", title="내 배당 점검", url_path="check"),
    "analysis": st.Page(V + "story.py", title="데이터 이야기", url_path="analysis"),
    "column": st.Page(V + "column.py", title="금융 상식", url_path="column"),
    "wealth": st.Page(V + "wealth.py", title="자산관리", url_path="wealth"),
    "isa-irp": st.Page(V + "isa_irp.py", title="제도별 비교", url_path="isa-irp"),
    "company": st.Page(V + "company.py", title="회사 보기", url_path="company", visibility="hidden"),
    "consult": st.Page(V + "consult.py", title="세무상담 신청", url_path="consult", visibility="hidden"),
    "me": st.Page(V + "me.py", title="내 정보", url_path="me", visibility="hidden"),
    "mypage": st.Page(V + "mypage.py", title="마이페이지", url_path="mypage", visibility="hidden"),
    "privacy": st.Page(V + "legal_privacy.py", title="개인정보 처리 안내", url_path="privacy", visibility="hidden"),
    "terms": st.Page(V + "legal_terms.py", title="이용약관(특약)", url_path="terms", visibility="hidden"),
}
st.session_state["_pages"] = PAGES
page = st.navigation(list(PAGES.values()), position="top")
# 탭 제목은 app/web/src/App.tsx TITLES와 같게
TITLES = {"home": "홈", "column": "금융 상식 칼럼", "wealth": "A은행 자산관리"}
setup(TITLES.get(page.url_path, page.title))


def topbar() -> None:
    """웹 머리: 로고 · (주 메뉴는 Streamlit 위쪽 메뉴) · 회사 찾기 · 로그인 메뉴."""
    with st.container(key="topbar"):
        c1, c2, c3 = st.columns([3, 3, 1.4], vertical_alignment="center")
        with c1:
            html('<div class="op-brand"><i></i>원픽</div>')
        with c2:
            companies = api.companyList()
            label = {f"{c['name']} · {c['code']}": c["code"] for c in companies if not c.get("pref_of")}
            pick = st.selectbox("회사 찾기", list(label), index=None, placeholder="회사 찾기", label_visibility="collapsed",
                                key=f"find_{page.url_path}")
            if pick:
                st.session_state.pop(f"find_{page.url_path}", None)
                st.switch_page(PAGES["company"], query_params={"code": label[pick]})
        with c3:
            account_menu()


def account_menu() -> None:
    """웹 AccountMenu.tsx: 로그인하지 않아도 모든 화면을 쓸 수 있고, 시연용 고객으로 로그인·바꾸기·로그아웃."""
    people = api.personas()
    pid = persona_id()
    who = next((p for p in people if p["id"] == pid), None)
    with st.popover(f"{who['emoji']} {who['name']}님(가상)" if who else "로그인", use_container_width=True):
        if who:
            st.page_link(PAGES["mypage"], label="마이페이지 · 신청 내역 · 취소")
            st.page_link(PAGES["me"], label="내 정보 · 소득 · 계좌 · 점검 결과")
        st.caption("다른 가상 고객으로 바꾸기" if who else "시연용 고객으로 로그인 (가상 인물)")
        for p in people:
            if p["id"] == pid:
                continue
            if st.button(f"{p['emoji']} {p['name']} · {p['tag']}", key=f"login_{p['id']}", use_container_width=True):
                set_persona(p["id"])
                st.rerun()
        if who and st.button("로그아웃", key="logout", use_container_width=True):
            set_persona(None)
            st.rerun()


topbar()
try:
    page.run()
except StopException:  # 화면이 st.stop()으로 일찍 끝나도 아래쪽 안내는 그린다 (웹은 늘 보임)
    pass

# 웹 App.tsx 아래쪽 안내
html('<footer class="foot small">'
     "<p>종목 추천이 아니며 매수·매도 판단 근거로 제공하지 않습니다. 세액은 참고용 모의 계산이에요(확정 세액·환급액 아님). 상담 신청·예약·로그인은 시연용 모형이에요. 판정은 공식 해설 전까지 '현재 해석 기준'이에요.</p>"
     "<p>자료: OpenDART · KIND · 국가법령정보센터 (조세특례제한법 제104조의27, 시행 2026. 9. 18.)</p>"
     "</footer>")
c1, c2, c3 = st.columns([6, 2, 2])
with c1:
    st.caption("원픽은 A은행(가상) 앱의 애드온 서비스로, A은행 개인(신용)정보처리방침과 기본약관을 따릅니다")
with c2:
    st.page_link(PAGES["privacy"], label="**원픽 개인정보 처리 안내**")
with c3:
    st.page_link(PAGES["terms"], label="이용약관(특약)")
