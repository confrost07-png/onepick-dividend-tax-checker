"""내 정보 (웹 app/web/src/pages/Me.tsx): 로그인했다고 가정한 시연용 고객의 개인 페이지 (source/core/personas.py, api.persona).
금융소득 합계·점검 결과·ISA·IRP 판정은 서버가 코드로 계산한 값을 그대로 보여 준다."""
import math

import streamlit as st

from common import api, error, esc, fmt, html, load, persona_id

PAGES = st.session_state["_pages"]
KIND = {"interest": "이자", "stock": "보유 주식 배당", "fund": "ETF 분배금"}


def exact(n: float) -> str:
    return f"{fmt(n)}원"


def pct(p: float) -> str:
    return f"{fmt(p / 10, 1)}%"


pid = persona_id()
if not pid:
    html('<div class="me"><h1>내 정보</h1><p>로그인하면 내 소득·계좌와 점검 결과, ISA·IRP 조건을 한곳에서 볼 수 있어요. 위쪽 메뉴의 [로그인]에서 시연용 고객을 골라 주세요.</p>'
         '<p class="small">로그인하지 않아도 내 배당 점검과 다른 화면은 모두 쓸 수 있어요.</p></div>')
    st.page_link(PAGES["check"], label="내 배당 점검")
    st.stop()

p, err = load(api.persona, pid)
if err:
    error(err)
    st.stop()

c, ii = p["checkup"], p["isa_irp"]
html(f"""<div class="me"><header class="me-hero card">
  <span class="me-face" aria-hidden>{p['emoji']}</span>
  <div>
    <p class="small me-login">A은행 앱 로그인 상태로 가정 · 가상 인물</p>
    <h1>{esc(p['name'])}님 <span class="small">만 {p['age']}세</span></h1>
    <p class="me-job">{esc(p['job'])} · {esc(p['home'])}</p>
    <blockquote>“{esc(p['quote'])}”</blockquote>
    <p class="small">관심사: {esc(p['goal'])}</p>
  </div>
</header></div>""")

facts = ""
if not c["no_target"] and c["tax"]["difference"] is not None:
    facts = '<dl class="facts">' + "".join(f"<div><dt>{esc(l)}</dt><dd>{exact(v)}</dd></div>" for l, v in c["tax"]["rows"]) + \
            f'<div class="me-diff"><dt>신청 전후 계산상 세액 차이</dt><dd>{exact(c["tax"]["difference"])} {esc(c["tax"]["direction"])}</dd></div></dl>'
answers = "".join(f"<li>{esc(a) if a is not None else '묻지 않음 (④에 다른 소득 있음)'}</li>" for a in p["answers"])
html(f"""<div class="me"><section class="me-sec"><h2 id="me-check">내 배당 점검</h2>
<div class="card me-check">
  <p class="me-headline">{esc(c['headline'])}</p>{facts}
  <p class="small">{esc(c['tax']['notice'])} 지방소득세·배당세액공제 외 세액공제·이미 낸 세금은 빼고 계산했어요. 환급액이 아니에요.</p>
  <div class="me-answers"><b>점검에 넣을 답</b><ol>{answers}</ol>
  <p class="small">아래 버튼을 누르면 챗봇에 이 답을 차례로 넣어 보여 드려요. 마지막 확인([맞아요])은 직접 눌러 주세요. 점검 화면에 그냥 들어가면 단계마다 '내 답' 버튼으로만 보여 드려요.</p></div>
</div></section></div>""")
if st.button("이 답으로 점검 챗봇 돌려 보기", type="primary"):
    st.switch_page(PAGES["check"], query_params={"auto": "1"})

rows = "".join(f'<tr><th>{esc(n)}<span class="small">{KIND[k]} · {esc(b)}</span></th><td>{exact(v)}</td></tr>' for n, b, v, k in p["financial"])
html(f"""<div class="me"><section class="me-sec"><h2 id="me-fin">1년 금융소득 (세전)</h2>
<div class="card"><table class="me-table"><tbody>{rows}</tbody><tfoot><tr><th>합계</th><td>{exact(p['financial_total'])}</td></tr></tfoot></table>
<p class="small">모두 15.4%가 원천징수됐다고 보면 실제로 들어온 돈은 {exact(p['withheld_after'])}(월평균 약 {exact(math.floor(p['withheld_after'] / 12 / 1_000 + 0.5) * 1_000)})이에요.
최종 세후소득이나 매달 고정으로 받는 돈은 아니에요.</p></div></section></div>""")

isa = ii["isa"]
if isa["can_join"]:
    isa_body = (f'<p><b class="badge badge--ok">가입 가능 · {esc(isa["type"])}</b></p>'
                f'<p>{isa["income_year"]}년 {esc(ii["basis"])} {exact(isa["income"])} 기준으로 {esc(isa["type"])}이에요. 계좌를 닫을 때 순이익 {exact(isa["free"])}까지 세금이 없어요(매년 한도가 아니에요).</p>'
                f'<p class="small">예시: 3년 넘게 유지해 이자·배당 순이익 {exact(isa["profit"])}이 생기면 일반 계좌 세금 {exact(isa["normal_tax"])}, ISA {exact(isa["isa_tax"])}. 수익 예측이 아니에요.</p>')
else:
    isa_body = (f'<p><b class="badge badge--no">가입 제한</b></p>'
                f'<p>{"·".join(str(y) for y in isa["blocked_years"])}년에 금융소득종합과세 대상이었어요. 가입 직전 3년 안에 이력이 있으면 가입할 수 없어요.</p>')
irp = ii["irp"]
what_if = ""
if ii["what_if"]:
    what_if = (f'<table class="me-table me-table--small"><thead><tr><th>올해 {esc(ii["basis"])}이 확정되면</th><td>공제율 · 공제</td></tr></thead><tbody>'
               + "".join(f'<tr><th>{exact(w["income"])}</th><td>{pct(w["rate_permil"])} · {exact(w["credit"])}</td></tr>' for w in ii["what_if"]) + "</tbody></table>")
html(f"""<div class="me"><section class="me-sec"><h2 id="me-isa">ISA · IRP — 내 조건 ({esc(ii['basis'])} 기준)</h2>
<div class="me-two">
  <div class="card"><h3>ISA</h3>{isa_body}<p class="small">근거: {esc(isa['source'])}</p></div>
  <div class="card"><h3>IRP</h3><p><b class="badge badge--ok">공제율 {pct(irp['rate_permil'])}</b></p>
    <p>{irp['income_year']}년 {esc(ii['basis'])} {exact(irp['income'])} 기준이에요. 본인 납입 {exact(irp['irp'])}이면 계산상 공제는 {exact(irp['credit'])}이에요.</p>{what_if}
    <p class="small">확정 환급액이 아니에요. 그해 낼 세금보다 많이 돌려받지 못해요. 근거: {esc(irp['source'])}</p></div>
</div>
<p class="small">{esc(p['isa_irp_note'])} {esc(ii['notice'])}</p></section></div>""")
st.page_link(PAGES["isa-irp"], label="제도별 비교에서 더 보기 →")

inc = "".join(f"<tr><th>{esc(k)}</th><td>{exact(v) if v else '없음'}</td></tr>" for k, v in p["income"])
acc = "".join(f'<tr><th>{esc(k)}</th><td class="me-left">{esc(v)}</td></tr>' for k, v in p["accounts"])
tips = "".join(f"<li>{esc(t)}</li>" for t in p["pitfalls"])
html(f"""<div class="me"><section class="me-sec"><h2 id="me-acc">소득과 계좌</h2>
<div class="me-two">
  <div class="card"><h3>소득</h3><table class="me-table"><tbody>{inc}</tbody></table><p class="small">{esc(p['income_note'])}</p></div>
  <div class="card"><h3>계좌·제도 가입 상태</h3><table class="me-table"><tbody>{acc}</tbody></table></div>
</div></section>
<section class="me-sec"><h2 id="me-tip">놓치기 쉬운 점</h2><ul class="card me-tips">{tips}</ul><p class="small">다음 점검: {esc(p['next'])}</p></section>
<p class="small">자료: {esc(p['source'])}. 주당배당금과 판정은 원픽 DB(KIND·OpenDART) 기준이에요.</p></div>""")
