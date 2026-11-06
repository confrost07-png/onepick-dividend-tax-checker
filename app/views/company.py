"""회사 보기 (웹 app/web/src/pages/Company.tsx, /company/:code → ?code=)
이 회사 동전이 법 토너먼트에서 지난 길과 2027년 최소 필요 배당. 회사별 공시 뒤 주가 반응은 보여 주지 않는다(팀 원칙)."""
import streamlit as st

from common import api, badge_class, error, esc, html, judge_year_html, load, loading, moa, mood_of, pct, won

MARK = {"pass": "✓", "fail": "✕", "hold": "?", "skip": "–", "goal": "★"}


def nb(s: str) -> str:
    return f'<span class="nb">{esc(s)}</span>'


def rounds(s: dict) -> list[dict]:
    first = s["reasons"][0] if s["reasons"] else ""
    r1 = "hold" if s["status"] == "판정 보류" and not first.startswith("전전") else "pass"
    r2 = "skip" if r1 != "pass" else "fail" if first.startswith("제2호") else "pass"
    r3 = "skip" if r2 != "pass" else "pass" if s["status"] == "충족" else "hold" if s["status"] == "판정 보류" else "fail"
    payout = f"적자라 배당성향 {s['deemed_payout']}%로 봐요" if s["deemed_payout"] is not None else f"배당성향 {pct(s['payout_pct'])}"
    end = "goal" if s["status"] == "충족" else "fail" if s["status"] == "미충족" else "hold"
    return [
        {"state": r1, "title": "1라운드", "text": "판정 숫자를 확인하는 중이에요" if r1 == "hold" else "판정 숫자가 다 있어요",
         "why": esc(first) if r1 == "hold" else None},
        {"state": r2, "title": "2라운드 · 제2호", "text": "배당이 2024년보다 줄었어요" if r2 == "fail" else "배당이 줄지 않았는지",
         "why": (f"배당소득 {nb(won(s['b2024']) + ' →')} {nb(won(s['b2025']) + ' (' + pct(s['b_growth_pct'], True) + ')')}"
                 if s["b2024"] is not None and s["b2025"] is not None and r2 != "skip" else None)},
        {"state": r3, "title": f"3라운드 · {'가목 언덕' if s['route'] == '가목' else '나목 계단'}" if s["route"] else "3라운드 · 제3호",
         "text": "배당성향 40% 이상" if s["route"] == "가목" else "25% 이상 + 배당 10%↑" if s["route"] == "나목" else "가목 또는 나목" if r3 == "skip" else first,
         "why": f"{nb(payout)} · {nb('이익배당 ' + pct(s['d_growth_pct'], True))}" if r3 != "skip" else None},
        {"state": end, "title": "2026 통과" if s["status"] == "충족" else "이번엔 탈락" if s["status"] == "미충족" else "판정 보류",
         "text": "2026 사업연도 배당이 분리과세 대상" if s["status"] == "충족" else first},
    ]


code = st.query_params.get("code", "")
s, err = load(api.company, code) if code else (None, "회사를 찾지 못했어요")
if err:
    error(err)
    st.stop()
if not s:
    loading()
    st.stop()

mood = mood_of(s["status"])
have = s["d2025"] or 0
need = s["need_2027"]
mx = max(have, need) if need is not None else have
more = need is not None and need > have
hello = (f"{s['name']} 동전은 세 라운드를 모두 지나 {'가목 언덕' if s['route'] == '가목' else '나목 계단'}에 올라섰어요!" if s["status"] == "충족"
         else f"{s['name']} 동전은 이번 토너먼트에서 멈췄어요. 아래에서 어느 문이었는지 보세요." if s["status"] == "미충족"
         else f"{s['name']} 동전은 대기석에 있어요. 확인이 끝나면 다시 달려요.")

html(f"""<div class="co-head">
  <h1>{esc(s['name'])}</h1><span class="small">{esc(s['code'])}</span>
  <span class="badge {badge_class(s['status'])}">{esc(s['status'])}{' · ' + esc(s['route']) if s['route'] else ''}</span>
  <span class="tag">{'판정 보류' if s['status'] == '판정 보류' else '현재 해석 기준'}</span>
</div>""")
# 웹의 [주소 복사] 단추: Streamlit에서는 주소를 그대로 보여 준다(클립보드 복사는 st.code의 복사 단추)
with st.expander("주소 복사"):
    st.code(f"/company?code={s['code']}", language=None)

def step_html(r: dict) -> str:
    why = f'<span class="why">{r["why"]}</span>' if r.get("why") else ""
    return (f'<li class="step {r["state"]}"><div class="dot" aria-hidden="true">{MARK[r["state"]]}</div>'
            f'<h4>{esc(r["title"])}</h4><p>{esc(r["text"])}</p>{why}</li>')


steps = "".join(step_html(r) for r in rounds(s))
html(f"""<section class="card" aria-label="법 토너먼트에서 지난 길">
  <div class="moa-say" style="margin-bottom:22px"><img class="moa-pop" src="{moa(mood)}" alt="" /><p>{esc(hello)}</p></div>
  <ol class="path" style="list-style:none;padding:0;margin:0">{steps}</ol>
  {judge_year_html()}
</section>""")

if need is None:
    big = '<p class="big">2027년 최소 필요 배당은 <em>계산하지 않았어요</em></p>'
else:
    msg = f"2027년엔 2025년보다 <em>{won(need - have)}</em> 더 줘야 해요" if more else "2025년만큼만 줘도 2027년 요건을 넘어요"
    big = f'<p class="big">{msg}</p>'
gauge = ""
if need is not None:
    gauge = (f'<div class="gauge" role="img" aria-label="2025 배당 {won(have)}, 2027 최소 필요 {won(need)}">'
             f'<div class="gauge__track"><div class="gauge__fill" style="width:{min(100, have / mx * 100) if mx else 0}%"></div></div>'
             f'<div class="gauge__mark" style="left:calc({min(100, need / mx * 100) if mx else 0}% - 2px)"><span>2027 최소</span></div></div>')
need_txt = f"{won(need)} ({pct(s['ratio_to_2025_pct'])})" if need is not None else (s["need_status"] or "–")
links = "".join(f'<a class="chip" href="{esc(l["url"])}" target="_blank" rel="noreferrer">{esc(l["label"])} ↗</a>' for l in s["sources"])
html(f"""<section class="card" style="margin-top:20px" aria-label="2027 사업연도 배당">
  <span class="tag">다음 판정 · 2027 사업연도 배당</span>
  {big}{gauge}
  <dl class="facts">
    <div><dt>2025 배당</dt><dd>{won(s['d2025']) if s['d2025'] is not None else '–'}</dd></div>
    <div><dt>2027 최소 필요</dt><dd>{esc(need_txt)}</dd></div>
    <div><dt>2025 배당성향</dt><dd>{pct(s['payout_pct'])}</dd></div>
  </dl>
  <p class="small" style="margin:12px 0 0">2026년 순이익이 2025년과 같다고 가정했어요. 결과는 2027년 2~3월 배당 결정 공시에서 확인할 수 있어요.</p>
  {f'<div class="outlinks">{links}</div>' if s['sources'] else ''}
</section>""")
