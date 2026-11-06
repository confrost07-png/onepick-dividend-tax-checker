"""금융위원회 금융용어사전(누리집 '금융용어설명')을 data/processed/term/fsc_glossary.json으로 받는다.

실행: .venv/bin/python -m scripts.collect_fsc_glossary
- 출처: https://www.fsc.go.kr/in090301 (목록 쪽 curPage=1..N, 용어 쪽 /in090301/view?dicId=…)
- 이용 조건: 공공데이터포털 '금융위원회_금융용어사전'(data.go.kr/data/15160317) 이용허락범위 제한 없음. 화면에는 출처를 붙인다.
- 용어 이름(subject)과 설명(cont) 글자만 원문 그대로 저장한다(HTML 태그·공백만 정리). 사전에 없는 뜻을 AI가 만들지 않도록
  챗봇 용어 풀이의 근거로만 쓴다(source/core/term_explain.py).
"""
import html
import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://www.fsc.go.kr/in090301"
OUT = Path(__file__).resolve().parents[2] / "data" / "processed" / "term" / "fsc_glossary.json"
SOURCE = {"name": "금융위원회 금융용어사전", "url": BASE, "license": "공공데이터포털 이용허락범위 제한 없음 (data.go.kr/data/15160317)"}
DELAY_SEC = 0.3

_ID = re.compile(r"view\?dicId=(\d+)")
_SUBJECT = re.compile(r'<div class="subject">(.*?)</div>', re.S)
_CONT = re.compile(r'<div class="cont">(.*?)</div>\s*<div class="btn-board"', re.S)
_PAGE = re.compile(r"curPage=(\d+)")


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "onepick-glossary/1.0 (education project)"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (금융위원회 누리집만)
        return resp.read().decode("utf-8", "replace")


def text_of(fragment: str) -> str:
    """HTML 조각 → 글자. 문단·줄바꿈은 줄로, 나머지 태그는 지우고 공백을 정리한다."""
    t = re.sub(r"<\s*(br|/p|/li|/div)[^>]*>", "\n", fragment, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def term_page(dic_id: str) -> dict | None:
    page = get(f"{BASE}/view?dicId={dic_id}")
    s, c = _SUBJECT.search(page), _CONT.search(page)
    if not s or not c:
        return None
    return {"id": dic_id, "term": text_of(s.group(1)), "definition": text_of(c.group(1)), "url": f"{BASE}/view?dicId={dic_id}"}


def main() -> None:
    first = get(f"{BASE}?curPage=1")
    pages = max(int(p) for p in _PAGE.findall(first))  # 쪽 넘김의 '맨 끝' 링크가 마지막 쪽
    ids: list[str] = []
    for p in range(1, pages + 1):
        page = first if p == 1 else get(f"{BASE}?curPage={p}")
        ids += [i for i in _ID.findall(page) if i not in ids]
        time.sleep(DELAY_SEC)
    terms, missing = [], []
    for i in ids:
        t = term_page(i)
        (terms.append(t) if t and t["term"] and t["definition"] else missing.append(i))
        time.sleep(DELAY_SEC)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": {**SOURCE, "fetched": date.today().isoformat()}, "terms": terms},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"목록 {pages}쪽 · 용어 {len(ids)}개 중 저장 {len(terms)}개 · 글을 못 읽은 쪽 {len(missing)}개 {missing[:10]} → {OUT}")


if __name__ == "__main__":
    main()
