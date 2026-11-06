"""관련 조문 찾기: 고객 질문과 가까운 조문 문단을 원문 그대로 돌려준다 (검색만, 생성 없음).

원문은 국가법령정보센터에서 받아 data/processed/law/articles.json에 항(①②…) 단위로 저장하고,
Ollama bge-m3(MIT 라이선스)로 미리 임베딩해 data/processed/law/embeddings.json에 둔다.
질문이 오면 질문만 임베딩해 코사인 유사도로 고른다. Ollama가 없으면 글자 겹침으로 찾는다.
AI는 어느 문단을 보여 줄지 고르기만 하고, 문장을 쓰지 않는다.

원문 다시 받기: uv run python -m core.law_search build
"""
import json
import math
import os
import re
import sys
import warnings
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "law"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.json"

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
TIMEOUT_SECONDS = 10
MIN_SCORE = 0.45  # 이보다 덜 비슷하면 '관련 조문을 찾지 못함'으로 본다 (bge-m3 기준, 시연 문장으로 정함)

_BASE = "https://www.law.go.kr"
# (법령명, 국가법령정보센터 조문 페이지 경로, 쓸 항·호 — 빈 튜플이면 전부)
# 항만 적으면("③") 그 항 전체, 호까지 적으면("③6") 그 항의 첫 문장과 그 호(딸린 목 포함)만 남긴다.
SOURCES = [
    ("조세특례제한법", "/법령/조세특례제한법/제104조의27", ()),
    ("조세특례제한법 시행령", "/법령/조세특례제한법시행령/제104조의24", ()),
    ("조세특례제한법 시행규칙", "/법령/조세특례제한법시행규칙/제47조의3", ()),
    # 배당소득의 범위 중 특례와 관련된 항만: ④ 주식대여 배당 상당액(시행령 제104조의24①이 인용), ⑥ 감액배당
    ("소득세법 시행령", "/법령/소득세법시행령/제26조의3", ("④", "⑥")),
    # ISA와 함께 쓸 때 근거: ISA 비과세·9% 분리과세, 금융소득 2천만 원 이하 분리과세(③5·6호), 배당 원천징수 14%(①2호)
    ("조세특례제한법", "/법령/조세특례제한법/제91조의18", ()),
    ("소득세법", "/법령/소득세법/제14조", ("③5", "③6")),
    ("소득세법", "/법령/소득세법/제129조", ("①2",)),
    # 직전 3년 중 금융소득종합과세 대상이면 ISA 등 저축 특례를 받지 못함 (source/core/isa_irp.py가 근거로 씀)
    ("조세특례제한법", "/법령/조세특례제한법/제129조의2", ("①",)),
    # 고배당 특례배당소득의 개인지방소득세 = 국세 세율의 100분의 10
    ("지방세특례제한법", "/법령/지방세특례제한법/제167조의6", ()),
]
# 원문에 없는 흔한 이름. 임베딩용 글에만 붙이고 화면 원문에는 넣지 않는다.
ALIASES = {
    "제91조의18": "ISA 개인종합자산관리계좌",
    "제129조의2": "ISA 개인종합자산관리계좌 가입 제한",
    "제14조": "금융소득 종합과세",
}
NEAR_TOP = 0.15  # 1등보다 이만큼 넘게 덜 비슷한 문단은 함께 보여 주지 않는다

_PARAGRAPH = re.compile(r"^[①-⑳]")
_ITEM = re.compile(r"^(\d+(?:의\d+)?)\. ")  # 호: "6. …", "5의2. …"
_HISTORY = re.compile(r"\s*<(?:개정|신설)[^>]*>")  # 문장 끝의 <개정 2010. 12. 27., …> 연혁 표시
_KEEP = re.compile(r"^([①-⑳]?)(\d+(?:의\d+)?)?$")  # SOURCES의 쓸 항·호: "③", "③6", "①2"


@dataclass(frozen=True)
class Passage:
    law: str
    article: str  # 예: 제104조의27(고배당기업 주식 배당소득에 대한 과세특례)
    paragraph: str  # 예: ①, 없으면 ""
    text: str  # 원문 그대로
    url: str
    effective: str  # 예: 2026. 9. 18.
    item: str = ""  # 호만 골라 담았을 때 호 번호 (예: 6), 아니면 ""

    @property
    def label(self) -> str:
        return f"{self.law} {self.article.split('(')[0]}{self.paragraph}{self.item + '호' if self.item else ''}"

    @property
    def embed_text(self) -> str:
        """임베딩·글자 검색에 쓰는 글: 라벨 + 조문 제목 + 별칭 + 원문(<개정 …> 연혁은 뺌). 화면에는 text만 보인다."""
        no = self.article.split("(")[0]
        title = self.article[len(no):].strip("()")
        body = _HISTORY.sub("", self.text)
        return " ".join(x for x in (self.label, title, ALIASES.get(no, ""), body) if x)


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float
    by: str  # "AI 검색" / "글자 검색"


# --- 원문 받기 ---

class _LawconParser(HTMLParser):
    """조문 본문(div.lawcon)의 <p> 단락을 글자로 모은다. 세율표 같은 그림은 alt 글자를 쓴다."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # lawcon 안에서의 div 깊이
        self.lines: list[str] = []
        self.buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            if self.depth:
                self.depth += 1
            elif "lawcon" in (a.get("class") or "").split():
                self.depth = 1
        if not self.depth:
            return
        if tag == "p":
            self.buf = []
        elif tag == "img" and self.buf is not None and a.get("alt"):
            self.buf.append("\n" + _clean_formula(a["alt"]))
        elif tag == "br" and self.buf is not None:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag == "p" and self.buf is not None:
            line = "".join(self.buf)
            parts = (re.sub(r"[ \t]+", " ", s).strip() for s in line.split("\n"))
            line = "\n".join(s for s in parts if s)  # 수식 그림 앞에 생기던 빈 줄도 없앤다
            if line:
                self.lines.append(line)
            self.buf = None
        elif tag == "div" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.buf is not None and not data.strip().startswith("javascript"):
            self.buf.append(data)


_LATEX = {"\\left(": "(", "\\right)": ")", "\\left[": "[", "\\right]": "]", "\\left\\{": "{", "\\right\\}": "}",
          "\\times": "×", "\\div": "÷", "\\cdot": "·", "\\leq": "≤", "\\geq": "≥",
          "\\%": "%", "\\,": " ", "\\ ": " "}


def _clean_formula(alt: str) -> str:
    """세율표 그림 설명의 수식 표시(@@LATEX@@, \\times 등)만 걷어 낸다. 숫자와 글자는 그대로 둔다."""
    s = re.sub(r"[@＠]{2}/?LATEX[@＠]{2}", "", alt)
    for k, v in _LATEX.items():
        s = s.replace(k, v)
    if "\\" in s:
        raise ValueError(f"정리하지 못한 수식 표시가 남음: {s[:80]}")
    return s


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_article(html: str, law: str, url: str) -> list[Passage]:
    """조문 페이지 HTML → 항 단위 Passage 목록. 호·목은 속한 항에 붙인다."""
    p = _LawconParser()
    p.feed(html)
    if not p.lines:
        return []
    first = p.lines[0]
    m = re.match(r"(제\d+조(?:의\d+)?\([^)]*\))\s*(.*)", first, re.S)
    if not m:
        return []
    title, rest = m.group(1), m.group(2)
    eff = re.search(r"\[시행 ([\d. ]+?)\]", html)
    effective = eff.group(1).strip() if eff else ""

    chunks: list[list[str]] = []
    for line in ([rest] if rest else []) + p.lines[1:]:
        # [본조신설 …] 같은 연혁 표시, [시행일: 2027. 1. 1.] 제14조제3항제8호다목(…) 같은 시행일 안내
        if line.startswith("[") and (line.endswith("]") or line.startswith("[시행일")):
            continue
        if _PARAGRAPH.match(line) or not chunks:
            chunks.append([line])
        else:
            chunks[-1].append(line)
    out = []
    for c in chunks:
        text = "\n".join(c)
        para = text[0] if _PARAGRAPH.match(text) else ""
        out.append(Passage(law, title, para, text, url, effective))
    return out


def split_items(p: Passage) -> dict[str, Passage]:
    """항 하나를 호 단위로 나눈다. 각 조각 = 항의 첫 문장(호 앞부분) + 그 호와 딸린 목. 원문 줄은 고치지 않는다."""
    lines = p.text.split("\n")
    head, items, cur = [], {}, None
    for line in lines:
        m = _ITEM.match(line)
        if m:
            cur = m.group(1)
            items[cur] = [line]
        elif cur is None:
            head.append(line)
        else:
            items[cur].append(line)
    return {no: Passage(p.law, p.article, p.paragraph, "\n".join(head + body), p.url, p.effective, no)
            for no, body in items.items()}


def select(passages: list[Passage], keep: tuple[str, ...], where: str) -> list[Passage]:
    """keep에 적은 항·호를 골라낸다. 하나라도 없으면 멈춘다 (조문 개정으로 번호가 바뀐 것을 놓치지 않게)."""
    if not keep:
        return passages
    by_para = {p.paragraph: p for p in passages}
    out = []
    for k in keep:
        m = _KEEP.match(k)
        if not m or not k:
            raise ValueError(f"{where}: 쓸 항·호 표시를 알 수 없음: {k!r}")
        para, item = m.group(1), m.group(2)
        if para not in by_para:
            raise RuntimeError(f"{where}: {para or '본문'}을 찾지 못함")
        if not item:
            out.append(by_para[para])
            continue
        items = split_items(by_para[para])
        if item not in items:
            raise RuntimeError(f"{where}: {para}{item}호를 찾지 못함")
        out.append(items[item])
    return out


def fetch_articles() -> list[Passage]:
    passages = []
    for law, path, keep in SOURCES:
        outer = _get(_BASE + urllib.parse.quote(path))
        src = re.search(r'src="(/LSW//lsSideInfoP\.do[^"]*)"', outer)
        if not src:
            raise RuntimeError(f"{law} 조문 페이지 주소를 찾지 못함")
        url = _BASE + unescape(src.group(1))
        found = parse_article(_get(url), law, url)
        if not found:
            raise RuntimeError(f"{law} 조문 본문을 읽지 못함")
        passages.extend(select(found, keep, f"{law} {path.rsplit('/', 1)[-1]}"))
    labels = [p.label for p in passages]
    dup = {x for x in labels if labels.count(x) > 1}
    if dup:
        raise RuntimeError(f"같은 라벨이 두 번 나옴: {sorted(dup)}")
    return passages


# --- 임베딩 ---

def ollama_embed(texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
        return json.loads(r.read())["embeddings"]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


OVERLAP_LEN = 400  # 글자 검색: 이보다 긴 문단은 길이만큼 점수를 깎는다 (긴 문단이 낱말을 많이 품어 늘 이기지 않게)


def _overlap(query: str, text: str) -> float:
    q = _bigrams(query)
    if not q:
        return 0.0
    n = len(re.sub(r"\s+", "", text))
    return len(q & _bigrams(text)) / len(q) * min(1.0, math.sqrt(OVERLAP_LEN / n)) if n else 0.0


# --- 저장·불러오기 ---

def save(passages: list[Passage], vectors: list[list[float]]) -> None:
    """두 파일을 임시 파일에 다 쓴 뒤 한꺼번에 바꿔 넣는다. 중간에 멈춰도 짝이 어긋난 파일이 남지 않게."""
    if len(vectors) != len(passages):
        raise ValueError("문단 수와 벡터 수가 다름")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"fetched": date.today().isoformat(), "source": "국가법령정보센터 (law.go.kr)",
            "note": "법령은 저작권법 제7조 제1호에 따라 저작권 보호 대상이 아님"}
    rows = [{k: v for k, v in p.__dict__.items() if k != "item" or v} for p in passages]
    files = {
        ARTICLES_PATH: json.dumps({**meta, "passages": rows}, ensure_ascii=False, indent=1),
        EMBEDDINGS_PATH: json.dumps({"model": EMBED_MODEL, "labels": [p.label for p in passages],
                                     "vectors": [[round(x, 6) for x in v] for v in vectors]}, ensure_ascii=False),
    }
    tmps = {}
    try:
        for path, body in files.items():
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(body, encoding="utf-8")
            tmps[path] = tmp
        for path, tmp in tmps.items():
            os.replace(tmp, path)
    finally:
        for tmp in tmps.values():
            tmp.unlink(missing_ok=True)


def load() -> tuple[list[Passage], list[list[float]] | None]:
    """원문과 벡터를 불러온다. 벡터 짝(개수·라벨)이 맞지 않으면 경고하고 벡터를 쓰지 않는다(글자 검색)."""
    passages = [Passage(**p) for p in json.loads(ARTICLES_PATH.read_text(encoding="utf-8"))["passages"]]
    vectors = None
    if EMBEDDINGS_PATH.exists():
        emb = json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8"))
        vectors = emb["vectors"]
        labels = emb.get("labels")
        if len(vectors) != len(passages) or (labels is not None and labels != [p.label for p in passages]):
            warnings.warn("data/processed/law/embeddings.json이 articles.json과 짝이 맞지 않아 글자 검색만 씀. "
                          "uv run python -m core.law_search build로 다시 만들어 주세요.", stacklevel=2)
            vectors = None
    return passages, vectors


# --- 검색 ---

@dataclass
class LawSearch:
    passages: list[Passage]
    vectors: list[list[float]] | None = None
    embed: Callable[[list[str]], list[list[float]]] | None = ollama_embed

    @classmethod
    def from_files(cls, embed=ollama_embed) -> "LawSearch":
        passages, vectors = load()
        return cls(passages, vectors, embed)

    def search(self, query: str, top_k: int = 3) -> list[Hit]:
        """질문과 가까운 문단을 원문 그대로 돌려준다. 충분히 비슷한 것이 없으면 빈 목록."""
        query = query.strip()
        if not query or not self.passages:
            return []
        if self.vectors is not None and self.embed is not None:
            try:
                qv = self.embed([query])[0]
                scored = [(_cosine(qv, v), p) for v, p in zip(self.vectors, self.passages)]
                by, floor = "AI 검색", MIN_SCORE
            except Exception:  # Ollama가 꺼져 있거나 응답이 이상하면 글자 검색으로 대신한다
                scored = None
        else:
            scored = None
        if scored is None:
            scored = [(_overlap(query, p.embed_text), p) for p in self.passages]
            by, floor = "글자 검색", 0.2
        scored.sort(key=lambda x: x[0], reverse=True)
        cut = max(floor, scored[0][0] - NEAR_TOP)
        return [Hit(p, round(s, 3), by) for s, p in scored[:top_k] if s >= cut]


def diff(old: list[Passage], new: list[Passage]) -> dict[str, list[str]]:
    """이전 원문과 새 원문을 라벨로 맞춰 본다: 원문이 바뀐 것, 새로 들어온 것, 빠진 것."""
    o, n = {p.label: p.text for p in old}, {p.label: p.text for p in new}
    return {"바뀜": [k for k in n if k in o and o[k] != n[k]],
            "추가": [k for k in n if k not in o],
            "빠짐": [k for k in o if k not in n]}


def build() -> None:
    passages = fetch_articles()
    for p in passages:
        if "\\" in p.text or "@@" in p.text or "＠＠" in p.text:
            raise RuntimeError(f"{p.label}: 수식 표시가 원문에 남음")
    old = load()[0] if ARTICLES_PATH.exists() else []
    vectors = ollama_embed([p.embed_text for p in passages])
    for kind, labels in diff(old, passages).items():
        print(f"{kind} {len(labels)}개" + (": " + ", ".join(labels) if labels else ""))
    save(passages, vectors)
    print(f"{len(passages)}개 문단 저장: {ARTICLES_PATH}")


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
    else:
        print("사용법: uv run python -m core.law_search build")
