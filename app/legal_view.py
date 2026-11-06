"""개인정보 처리 안내(/privacy)와 이용약관 특약(/terms) (웹 app/web/src/pages/Legal.tsx).
문서 내용은 app/web/src/legal.ts를 그대로 뽑은 web_text.json에서 읽는다."""
import streamlit as st

from common import esc, html, web_text


def block(b) -> str:
    if isinstance(b, str):
        return f"<p>{esc(b)}</p>"
    if "list" in b:
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in b["list"]) + "</ul>"
    if "note" in b:
        return f'<p class="legal-note">ⓘ {esc(b["note"])}</p>'
    head = b["table"]["head"]
    rows = "".join("<tr>" + "".join(f'<td data-label="{esc(head[i])}">{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>" for r in b["table"]["rows"])
    return f'<div class="legal-table"><table><thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in head)}</tr></thead><tbody>{rows}</tbody></table></div>'


def render(kind: str) -> None:
    L = web_text()["legal"]
    doc = L["PRIVACY"] if kind == "privacy" else L["TERMS"]
    other_key, other = ("terms", L["TERMS"]) if kind == "privacy" else ("privacy", L["PRIVACY"])
    html(f"""<div class="legal"><header class="legal-head">
  <span class="bank-mark">A은행 · 모형</span>
  <h1>{esc(doc['title'])}</h1>
  <p class="small">{esc(doc['version'])} · 시행 {esc(doc['effective'])}</p>
  <p class="notice">ⓘ <span>{esc(L['LEGAL_MOCK'])}</span></p>
  <p>{esc(doc['lead'])}</p>
</header></div>""")
    st.page_link(st.session_state["_pages"][other_key], label=f"{other['short']} 보기")
    toc = "".join(f'<li><a href="#{esc(s["id"])}">{esc(s["title"])}</a></li>' for s in doc["sections"])
    body = "".join(f'<section id="{esc(s["id"])}" class="legal-sec"><h2>{esc(s["title"])}</h2>{"".join(block(b) for b in s["body"])}</section>'
                   for s in doc["sections"])
    # 웹의 [인쇄하기] 단추는 브라우저 인쇄(Ctrl/⌘+P)로 대신한다
    html(f"""<div class="legal"><div class="legal-body">
  <nav class="legal-toc" aria-label="차례"><b>차례</b><ol>{toc}</ol></nav>
  <article>{body}</article>
</div></div>""")
