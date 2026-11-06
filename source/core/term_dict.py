"""금융 용어 사전 찾기: 금융위원회 금융용어사전 + 원픽 보충 용어 (챗봇 용어 질문).

- data/processed/term/fsc_glossary.json: 금융위원회 누리집 '금융용어설명' 원문 그대로 (source/scripts/collect_fsc_glossary.py)
- data/processed/term/onepick_terms.json: 흔히 묻지만 위 사전·칼럼 사전에 없는 용어. 공공기관 자료를 열어 확인하고 원픽이 쉬운 말로 쓴 풀이,
  용어마다 확인한 출처 주소가 있다.
- 답을 만들지 않는다. 용어 이름(또는 별칭)이 글자로 정확히 맞을 때만 그 항목을 그대로 돌려준다.
  화면은 먼저 칼럼 용어 사전(app/web/src/column.ts)·금융 상식 고정 답변에서 찾고, 없을 때 이 사전을 쓴다.
"""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "term"
FSC = DIR / "fsc_glossary.json"
ONEPICK = DIR / "onepick_terms.json"
MAX_QUERY = 30
# 금융위 누리집 원문이 깨진 항목은 쓰지 않는다 (용어 쪽 번호 → 까닭)
SKIP_FSC = {"1925": "BaaS: 누리집 원문이 문장 중간부터 시작함(여는 괄호 없이 닫는 괄호만 있음)"}

# '배당락이란?', 'PER 뜻', 'ETF가 뭐야', '블록딜이 뭔가요' → 용어만
_ASK_TAIL = re.compile(
    r"\s*(?:이란|란|이라는\s*건|라는\s*건|이\s*뭐|가\s*뭐|은\s*뭐|는\s*뭐|뭐|의\s*뜻|뜻|에\s*대해|이\s*무엇|가\s*무엇|무엇|설명|알려)"
    r".*$")
_NOISE = re.compile(r"[\s·ㆍ,\-–—_/'\"‘’“”「」『』.?？!]")


def term_of(text: str) -> str:
    """질문 문장에서 용어 부분만. 못 떼면 문장 그대로(앞뒤 공백·물음표 정리)."""
    t = text.strip().strip("?？!. ~")
    return _ASK_TAIL.sub("", t).strip() or t


def key(s: str) -> str:
    return _NOISE.sub("", s).lower()


def keys_of(term: str, aliases: list[str] = ()) -> set[str]:
    """'IPO(기업공개, Initial Public Offering)' → {'ipo기업공개initialpublicoffering', 'ipo', '기업공개', 'initialpublicoffering'}."""
    out = {key(term), key(re.sub(r"\(.*?\)", "", term))}
    for inside in re.findall(r"\((.*?)\)", term):
        out |= {key(p) for p in re.split(r"[,，]", inside)}
    out |= {key(a) for a in aliases}
    return {k for k in out if k}


@dataclass(frozen=True)
class Entry:
    term: str
    definition: str
    source_name: str
    source_url: str
    kind: str  # 'fsc' 금융위원회 원문 / 'onepick' 원픽 보충
    aliases: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def index() -> dict[str, Entry]:
    """열쇠(정리한 용어·별칭) → 항목. 원픽 보충을 먼저 넣어 같은 열쇠면 쉬운 말 풀이를 쓴다. 금융위 사전의 중복 용어는 처음 것만."""
    idx: dict[str, Entry] = {}
    if ONEPICK.exists():
        for t in json.loads(ONEPICK.read_text(encoding="utf-8"))["terms"]:
            e = Entry(t["term"], t["definition"], t["source_name"], t["source_url"], "onepick", tuple(t.get("aliases", [])))
            for k in keys_of(t["term"], t.get("aliases", [])):
                idx.setdefault(k, e)
    if FSC.exists():
        data = json.loads(FSC.read_text(encoding="utf-8"))
        name = data["source"]["name"]
        for t in data["terms"]:
            if t["id"] in SKIP_FSC:
                continue
            e = Entry(t["term"], t["definition"], name, t["url"], "fsc")
            for k in keys_of(t["term"]):
                idx.setdefault(k, e)
    return idx


def find(text: str) -> Entry | None:
    """용어 질문이면 사전 항목, 아니면 None. 숫자가 섞이거나 긴 문장은 용어 질문으로 보지 않는다."""
    t = term_of(text)
    if not t or len(t) > MAX_QUERY or any(ch.isdigit() for ch in t):
        return None
    return index().get(key(t))


def counts() -> dict[str, int]:
    """사전별 항목 수(같은 항목이 별칭으로 여러 번 들어가도 한 번)."""
    seen = {id(e): e.kind for e in index().values()}
    return {k: list(seen.values()).count(k) for k in ("fsc", "onepick")}


def entries() -> list[Entry]:
    """사전 항목 전체(별칭으로 겹쳐 들어간 것은 한 번). 원픽 보충 먼저, 그다음 금융위원회 사전."""
    seen: dict[int, Entry] = {}
    for e in index().values():
        seen.setdefault(id(e), e)
    return sorted(seen.values(), key=lambda e: (e.kind != "onepick", e.term))
