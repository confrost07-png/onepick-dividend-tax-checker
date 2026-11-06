"""세무상담·신고대행 신청 (웹 app/web/src/pages/Consult.tsx): 종류 → 방법 → 지점 → 날짜·시간 → 점검 결과 보내기 → 확인 → 완료(모형).
개인정보를 받지 않고, 신청 내용을 어디에도 보내지 않는다. 점검 화면이 넘긴 결과는 st.session_state["consult_state"]."""
from datetime import date, datetime

import streamlit as st

from bank_util import add_app, date_text, day_name, is_taken, mock_number, next_business_days
from common import api, esc, html, moa, persona_id, web_text

PAGES = st.session_state["_pages"]
B = web_text()["bank"]
BANK, BRANCHES, REGIONS, TYPES, WAYS, SLOTS = B["BANK"], B["BRANCHES"], B["REGIONS"], B["CONSULT_TYPES"], B["WAYS"], B["SLOTS"]
STEPS = ["상담 종류", "상담 방법", "지점", "날짜·시간", "점검 결과", "확인"]

S = st.session_state
qp = st.query_params
sig = (qp.get("type"), qp.get("way"), qp.get("branch"))
if S.get("cs_sig") != sig:  # 새로 들어오면 주소의 type·way·branch로 시작 (웹 useSearchParams)
    t, w, b = sig
    S.update(cs_sig=sig, cs_type=t, cs_way=w, cs_branch=b, cs_region="전체", cs_date=None, cs_slot=None,
             cs_send=bool((S.get("consult_state") or {}).get("send")), cs_agree=False, cs_done=None, cs_saved=False,
             cs_step=(3 if w == "phone" or b else 2) if (t and w) else 1 if t else 0)

checkup = (S.get("consult_state") or {}).get("checkup")
who = persona_id()
me = next((p for p in api.personas() if p["id"] == who), None)
br = next((b for b in BRANCHES if b["id"] == S.cs_branch), None)
way = S.cs_way
where = f"{BANK} 세무상담센터(전화)" if way == "phone" else f"{BANK} PB센터 {br['name']}점{'(화상)' if way == 'video' else ''}" if br else "–"
type_name = next((t["name"] for t in TYPES if t["id"] == S.cs_type), None)
way_name = next((w["name"] for w in WAYS if w["id"] == way), None)
d_sel = date.fromisoformat(S.cs_date) if S.cs_date else None


def go(n: int) -> None:
    S.cs_step = n
    st.rerun()


if S.cs_done:
    send, saved = S.cs_send, S.cs_saved
    html(f"""<div class="consult"><div class="card done-card">
  <img src="{moa('happy')}" alt="" />
  <span class="tag">모형 예약</span>
  <h1>모형 예약을 마쳤어요</h1>
  <dl class="facts" style="grid-template-columns:1fr 1fr">
    <div><dt>예약 번호(모형)</dt><dd>{S.cs_done}</dd></div>
    <div><dt>상담</dt><dd>{esc(type_name)}</dd></div>
    <div><dt>곳</dt><dd>{esc(where)}</dd></div>
    <div><dt>때</dt><dd>{date_text(d_sel) if d_sel else ''} {S.cs_slot}</dd></div>
  </dl>
  <p>{'점검 결과를 함께 보내는 것으로 표시했어요(모형).' if send else '점검 결과는 보내지 않고 예약만 했어요.'} 실제 서비스라면 {BANK} 앱 알림과 문자로 확정 안내가 가요.</p>
  {(f'<p>{"<b>마이페이지</b>에서 신청 내역을 확인하고 취소할 수 있어요." if saved else "이 브라우저에 신청 내역을 남기지 못했어요(저장소를 쓸 수 없음)."}</p>') if me
   else '<p class="small">로그인하지 않고 신청해서 내역이 남지 않아요. 위쪽 메뉴에서 로그인하고 신청하면 마이페이지에서 확인·취소할 수 있어요.</p>'}
  <p class="small">{esc(B['SAVED_NOTE'] if me and saved else B['MOCK_NOTE'])}</p>
</div></div>""")
    c = st.columns(4)
    if me and saved and c[0].button("마이페이지에서 보기", type="primary"):
        st.switch_page(PAGES["mypage"])
    if c[1].button("자산관리서비스로"):
        st.switch_page(PAGES["wealth"])
    if c[2].button("점검으로 돌아가기"):
        st.switch_page(PAGES["check"])
    st.stop()

step = S.cs_step
steps = "".join(f'<li class="{"done" if i < step else "now" if i == step else ""}"><button disabled><span>{i + 1}</span>{s}</button></li>' for i, s in enumerate(STEPS))
html(f"""<div class="consult"><header class="check-head">
  <span class="bank-mark">{BANK}</span>
  <h1>세무상담 신청</h1>
  <p class="small" style="margin:0">{esc(B['MOCK_NOTE'])}</p>
</header>
<ol class="consult-steps" aria-label="신청 단계">{steps}</ol></div>""")


def pick(items, current, key, on_pick, cols=1, label=lambda x: x["name"], sub=lambda x: x["line"]):
    grid = st.columns(cols)
    for i, it in enumerate(items):
        with grid[i % cols]:
            on = current == it["id"]
            if st.button(f"{'✓ ' if on else ''}**{label(it)}**  \n{sub(it)}", key=f"{key}_{it['id']}", type="primary" if on else "secondary", use_container_width=True):
                on_pick(it)
                st.rerun()


with st.container(border=True):
    if step == 0:
        html('<div class="consult-card"><h2>어떤 상담이 필요하세요?</h2></div>')
        pick(TYPES, S.cs_type, "type", lambda t: S.update(cs_type=t["id"]))
    elif step == 1:
        html('<div class="consult-card"><h2>어떻게 상담할까요?</h2></div>')

        def set_way(w):
            S.cs_way = w["id"]
            if w["id"] == "video" and br and not br["video"]:
                S.cs_branch = None
        pick(WAYS, way, "way", set_way, cols=3)
    elif step == 2:
        html('<div class="consult-card"><h2>어느 PB센터에서 할까요?</h2></div>')
        if way == "video":
            html('<p class="small">화상 상담이 되는 지점만 보여 드려요.</p>')
        S.cs_region = st.pills("지역 고르기", ["전체", *REGIONS], default=S.cs_region, label_visibility="collapsed", key="cs_region_pick") or "전체"
        shown = [b for b in BRANCHES if (way != "video" or b["video"]) and (S.cs_region == "전체" or b["region"] == S.cs_region)]
        pick(shown, S.cs_branch, "branch", lambda b: S.update(cs_branch=b["id"], cs_date=None, cs_slot=None), cols=4,
             label=lambda b: f"{b['name']}점", sub=lambda b: f"{b['area']}  \n세무 상담 {'·'.join(b['days'])}")
        if not shown:
            html('<p class="small">이 지역에는 화상 상담 지점이 없어요. 다른 지역을 골라 주세요.</p>')
    elif step == 3:
        html('<div class="consult-card"><h2>언제가 좋으세요?</h2></div>')
        lead = "평일 아무 날이나 고를 수 있어요." if way == "phone" else f"{br['name'] if br else ''}점은 {'·'.join(br['days']) if br else ''}요일에 세무 전문가가 있어요."
        html(f'<p class="small">{lead} 회색 시간은 이미 찼어요(모형).</p>')
        days = next_business_days(10)
        row = st.columns(5)
        for i, d in enumerate(days):
            ok = way == "phone" or not br or day_name(d) in br["days"]
            on = d_sel == d
            if row[i % 5].button(f"{d.day} {day_name(d)}", key=f"d_{d}", disabled=not ok, type="primary" if on else "secondary", use_container_width=True):
                S.update(cs_date=d.isoformat(), cs_slot=None)
                st.rerun()
        if d_sel:
            srow = st.columns(len(SLOTS))
            for i, s in enumerate(SLOTS):
                taken = is_taken(S.cs_branch or "phone", d_sel, s)
                if srow[i].button(s, key=f"s_{s}", disabled=taken, type="primary" if S.cs_slot == s else "secondary", use_container_width=True):
                    S.cs_slot = s
                    st.rerun()
    elif step == 4:
        html('<div class="consult-card"><h2>점검 결과를 함께 보낼까요?</h2></div>')
        if checkup:
            html(f"""<div class="send-box">
<p class="small" style="margin-top:0">실제 서비스라면 세무 전문가가 상담 전에 미리 봐요(시연판은 보내지 않아요). 보내지 않아도 상담은 똑같이 받을 수 있어요.</p>
<div class="send-preview"><b>보낼 내용</b><p>{esc(checkup['headline'])}</p>{f"<p>계산상 세액 차이(참고용 모의 계산): {esc(checkup['diff'])}</p>" if checkup.get('diff') else ''}
<p class="small">종목별 판정·최소 필요 배당액·세액 계산 근거. 이름·주민등록번호·계좌번호는 보내지 않아요.</p></div></div>""")
            S.cs_send = st.checkbox("점검 결과 함께 보내기", value=S.cs_send)
            if not S.cs_send:
                S.cs_agree = False
            else:
                html(f"""<div class="consent"><b>개인정보 제3자 제공 동의 (모형)</b><ul>
<li>받는 곳: {BANK} 제휴 세무법인</li><li>보내는 것: 위 점검 결과</li><li>쓰는 곳: 이번 세무상담 준비</li><li>보관 기간: 상담이 끝나면 지워요</li></ul>
<p class="small" style="margin:0 0 8px">동의하지 않아도 상담은 똑같이 받을 수 있어요.</p></div>""")
                st.page_link(PAGES["privacy"], label="개인정보 처리 안내 제4조 보기")
                S.cs_agree = st.checkbox("위 내용에 동의해요(모형)", value=S.cs_agree)
        else:
            html("<p>지금은 보낼 점검 결과가 없어요. 결과 없이도 상담을 신청할 수 있어요.</p>")
            st.page_link(PAGES["check"], label="먼저 점검하기")
    else:
        contact = f"{me['name']}님 {BANK} 로그인 정보로 연결(모형)" if me else f"{BANK} 로그인 정보로 연결(모형)"
        html(f"""<div class="consult-card"><h2>이대로 신청할까요?</h2>
<dl class="facts" style="grid-template-columns:1fr 1fr">
  <div><dt>상담</dt><dd>{esc(type_name)}</dd></div>
  <div><dt>방법</dt><dd>{esc(way_name)}</dd></div>
  <div><dt>곳</dt><dd>{esc(where)}</dd></div>
  <div><dt>때</dt><dd>{date_text(d_sel) if d_sel else ''} {S.cs_slot or ''}</dd></div>
  <div><dt>점검 결과</dt><dd>{'함께 보내기로 표시(모형)' if S.cs_send else '보내지 않아요'}</dd></div>
  <div><dt>연락받을 곳</dt><dd>{esc(contact)}</dd></div>
</dl>
<p class="small">이름과 연락처는 묻지 않아요. 실제 서비스에서는 {BANK} 앱에 로그인한 정보로 이어져요. 신청하면 A은행 기본약관·개인(신용)정보처리방침과 원픽 이용약관(특약)·개인정보 처리 안내에 따라 처리해요.</p></div>""")

    can_next = [bool(S.cs_type), bool(way), way == "phone" or bool(br), bool(d_sel and S.cs_slot), not S.cs_send or S.cs_agree, True][step]
    n1, _, n2 = st.columns([1, 4, 1.4])
    if step > 0 and n1.button("이전", use_container_width=True):
        go(1 if way == "phone" and step == 3 else step - 1)
    if step < 5:
        if n2.button("다음", type="primary", disabled=not can_next, use_container_width=True):
            go(3 if way == "phone" and step == 1 else step + 1)
    elif n2.button("신청하기(모형)", type="primary", use_container_width=True):
        no = mock_number()
        if who and S.cs_type and way and d_sel and S.cs_slot:
            S.cs_saved = add_app(who, {"no": no, "type": S.cs_type, "typeName": type_name or "", "way": way, "wayName": way_name or "",
                                       "where": where, "date": d_sel.isoformat(), "slot": S.cs_slot, "send": S.cs_send,
                                       "createdAt": datetime.now().isoformat(), "status": "신청"})
        S.cs_done = no
        st.rerun()
