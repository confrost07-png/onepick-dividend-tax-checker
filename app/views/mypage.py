"""마이페이지 (웹 app/web/src/pages/MyPage.tsx): 로그인한 시연용 고객의 자산관리서비스 신청 내역과 취소(모형).
웹은 내역을 브라우저에, Streamlit은 이 세션에만 둔다(bank_util)."""
from datetime import date, datetime

import streamlit as st

from bank_util import cancel_app, date_text, is_past, list_apps
from common import api, esc, html, persona_id, web_text

PAGES = st.session_state["_pages"]
B = web_text()["bank"]
BANK = B["BANK"]


def when(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{date_text(d.date())} {d.hour:02d}:{d.minute:02d}"


def card(a: dict) -> str:
    cls, txt = ("badge--no", "취소함") if a["status"] == "취소" else ("badge--hold", "지난 예약") if is_past(a) else ("badge--ok", "모형 신청")
    return f"""<div class="card my-app" style="margin-bottom:10px"><div class="my-app-head"><b>{esc(a['typeName'])}</b> <span class="badge {cls}">{txt}</span></div>
<dl class="facts" style="grid-template-columns:1fr 1fr;margin-top:10px">
<div><dt>때</dt><dd>{date_text(date.fromisoformat(a['date'][:10]))} {a['slot']}</dd></div>
<div><dt>곳</dt><dd>{esc(a['where'])} · {esc(a['wayName'])}</dd></div>
<div><dt>점검 결과</dt><dd>{'함께 보냄(동의함)' if a['send'] else '보내지 않음'}</dd></div>
<div><dt>예약 번호(모형)</dt><dd>{a['no']}</dd></div></dl>
<p class="small">신청 {when(a['createdAt'])}{f" · 취소 {when(a['canceledAt'])}" if a.get('canceledAt') else ''}</p></div>"""


pid = persona_id()
if not pid:
    html('<div class="me"><h1>마이페이지</h1><p>로그인하면 자산관리서비스 신청 내역을 보고 취소할 수 있어요. 위쪽 메뉴의 [로그인]에서 시연용 고객을 골라 주세요.</p>'
         '<p class="small">로그인하지 않아도 자산관리서비스 신청과 다른 화면은 모두 쓸 수 있어요. 다만 신청 내역은 남지 않아요.</p></div>')
    st.page_link(PAGES["wealth"], label="자산관리서비스")
    st.stop()

who = next((p for p in api.personas() if p["id"] == pid), None)
name = f"{who['emoji']} {who['name']}님" if who else ""
html(f'<div class="me"><header class="my-head"><h1>마이페이지</h1><p class="small">{name} · {BANK} 로그인 상태로 가정 · 가상 인물</p></header></div>')
st.page_link(PAGES["me"], label="내 정보 보기")
if st.session_state.get("my_msg"):
    html(f'<p class="notice" role="status">✓ <span>{esc(st.session_state["my_msg"])}</span></p>')

apps = list_apps(pid)
live = [a for a in apps if a["status"] == "신청" and not is_past(a)]
old = [a for a in apps if a not in live]
html(f'<div class="me"><section class="me-sec"><h2 id="my-live">신청 내역 <span class="small">{len(live)}건</span></h2></section></div>')
if live:
    for a in live:
        html(card(a))
        with st.popover("신청 취소"):  # 웹의 window.confirm 대신
            st.write(f"{date_text(date.fromisoformat(a['date'][:10]))} {a['slot']} {a['typeName']} 신청을 취소할까요?")
            if st.button("취소할게요", key=f"cancel_{a['no']}"):
                cancel_app(pid, a["no"])
                st.session_state["my_msg"] = f"{a['typeName']} 신청을 취소했어요(모형). 실제 서비스라면 {BANK} 앱 알림으로 취소 확인이 가요."
                st.rerun()
else:
    with st.container(border=True):
        st.write("예정된 신청이 없어요.")
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("자산관리서비스 보기", type="primary"):
            st.switch_page(PAGES["wealth"])
        if c2.button("세무상담 신청"):
            st.switch_page(PAGES["consult"], query_params={"type": "separate"})
if old:
    html(f'<div class="me"><section class="me-sec"><h2 id="my-old">지난·취소한 신청 <span class="small">{len(old)}건</span></h2>{"".join(card(a) for a in old)}</section></div>')
html(f'<p class="small">{esc(B["SAVED_NOTE"])}</p>')
