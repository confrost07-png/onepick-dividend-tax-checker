"""금융 상식 찾기: 고객 질문과 가까운 고정 답변 하나를 그대로 돌려준다 (검색만, 생성 없음).

답 문장은 data/processed/faq/finance_faq.json에 미리 써 두고, 문항마다 예시 질문을 bge-m3로 임베딩해
data/processed/faq/embeddings.json에 둔다. 질문이 오면 질문만 임베딩해 가장 비슷한 예시 질문을 고른다.
Ollama가 없으면 글자 겹침으로 찾는다. AI는 어느 답을 보여 줄지 고르기만 하고, 문장을 쓰지 않는다.

임베딩 다시 만들기: uv run python -m core.faq_search build
"""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.law_search import _bigrams, _cosine, ollama_embed

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "faq"
FAQ_PATH = DATA_DIR / "finance_faq.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.json"

MIN_SCORE = 0.75  # 이보다 덜 비슷하면 '답을 찾지 못함' (bge-m3 기준. 상관없는 질문은 0.69 이하, '고배당 주식들을 알려줘'→주식배당 같은 엉뚱한 답은 0.73 안팎이었음)
MIN_OVERLAP = 0.5  # 글자 검색: 질문의 두 글자 묶음 중 이만큼이 예시 질문에 있어야 함

# 비교할 때 빼는 말. 어느 질문에나 붙어 글자 검색 점수만 부풀린다
_FILLER = re.compile(r"(뭐예요|뭔가요|뭐야|무엇인가요|무엇|이란|란|이에요|인가요|알려\s*줘요?|알려\s*주세요|궁금해요|뜻|\?)")


@dataclass(frozen=True)
class Faq:
    id: str
    title: str
    examples: list[str]
    answer: str
    source_label: str
    source_url: str

    def texts(self) -> list[str]:
        """임베딩·글자 검색에 쓰는 문장: 제목과 예시 질문."""
        return [self.title, *self.examples]


@dataclass(frozen=True)
class FaqHit:
    faq: Faq
    score: float
    by: str  # 'AI 검색' 또는 '글자 검색'


def _core(text: str) -> str:
    return _FILLER.sub("", text).strip()


def _overlap(query: str, text: str) -> float:
    q = _bigrams(_core(query))
    return len(q & _bigrams(_core(text))) / len(q) if q else 0.0


def load() -> tuple[list[Faq], list[list[list[float]]] | None]:
    raw = json.loads(FAQ_PATH.read_text(encoding="utf-8"))
    faqs = [Faq(**{k: item[k] for k in Faq.__dataclass_fields__}) for item in raw["items"]]
    vectors = None
    if EMBEDDINGS_PATH.exists():
        saved = json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8"))
        # 문항이나 예시 질문이 바뀌었으면 옛 임베딩은 쓰지 않는다
        if saved.get("texts") == [f.texts() for f in faqs]:
            vectors = saved["vectors"]
    return faqs, vectors


@dataclass
class FaqSearch:
    faqs: list[Faq]
    vectors: list[list[list[float]]] | None = None
    embed: Callable[[list[str]], list[list[float]]] | None = ollama_embed

    @classmethod
    def from_files(cls, embed=ollama_embed) -> "FaqSearch":
        faqs, vectors = load()
        return cls(faqs, vectors, embed)

    def search(self, query: str) -> FaqHit | None:
        """가장 가까운 문항 하나. 충분히 비슷한 것이 없으면 None."""
        query = query.strip()
        if not _core(query) or not self.faqs:
            return None
        scored = None
        if self.vectors is not None and self.embed is not None:
            try:
                qv = self.embed([query])[0]
                scored = [(max(_cosine(qv, v) for v in vs), f) for vs, f in zip(self.vectors, self.faqs)]
                by, floor = "AI 검색", MIN_SCORE
            except Exception:  # Ollama가 꺼져 있거나 응답이 이상하면 글자 검색으로 대신한다
                scored = None
        if scored is None:
            scored = [(max(_overlap(query, t) for t in f.texts()), f) for f in self.faqs]
            by, floor = "글자 검색", MIN_OVERLAP
        score, faq = max(scored, key=lambda x: x[0])
        return FaqHit(faq, round(score, 3), by) if score >= floor else None


def build() -> None:
    faqs, _ = load()
    texts = [f.texts() for f in faqs]
    flat = ollama_embed([t for ts in texts for t in ts])
    vectors, i = [], 0
    for ts in texts:
        vectors.append([[round(x, 6) for x in v] for v in flat[i:i + len(ts)]])
        i += len(ts)
    EMBEDDINGS_PATH.write_text(json.dumps({"model": "bge-m3", "texts": texts, "vectors": vectors},
                                          ensure_ascii=False), encoding="utf-8")
    print(f"{len(faqs)}개 문항, {len(flat)}개 문장 임베딩 저장: {EMBEDDINGS_PATH}")


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
    else:
        print("사용법: uv run python -m core.faq_search build")
