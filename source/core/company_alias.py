"""자주 틀리거나 다르게 부르는 회사 이름 표 (data/processed/chat/company_alias.csv): 줄임말·영문·옛 이름·오타·자회사 → 대상 기업.

표에 걸려도 바로 바꿔 계산하지 않는다. 바꾼 글을 입력창에 넣고 "○○ 말씀인가요?"라고 되묻는다(엉뚱한 회사로 계산 방지).
"""
import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.chat_parse import topic_josa

ALIAS_CSV = Path(__file__).resolve().parents[2] / "data" / "processed" / "chat" / "company_alias.csv"


@dataclass(frozen=True)
class Alias:
    written: str  # 고객이 쓴 이름
    company: str  # 대상 기업 표준명
    kind: str  # 줄임말·영문·옛 이름·오타·자회사 …
    memo: str = ""


@lru_cache(maxsize=1)
def load(path: Path = ALIAS_CSV) -> tuple[Alias, ...]:
    with path.open(encoding="utf-8") as f:
        return tuple(Alias(r["입력"].strip(), r["대상 기업"].strip(), r["종류"].strip(), (r.get("메모") or "").strip())
                     for r in csv.DictReader(f) if r["입력"].strip())


def _pattern(written: str) -> re.Pattern:
    # 앞뒤가 다른 글자로 이어지지 않을 때만(‘삼성화재’가 ‘삼성화재해상보험’ 안에서 걸리지 않게). 띄어쓰기·대소문자는 무시
    body = r"\s*".join(re.escape(ch) for ch in written.replace(" ", ""))
    return re.compile(rf"(?<![가-힣A-Za-z]){body}(?![가-힣A-Za-z&+])", re.I)


def replace(text: str, aliases: tuple[Alias, ...] | None = None) -> tuple[str, list[Alias]]:
    """글 속의 별칭을 대상 기업 이름으로 바꾼 글과, 바꾼 별칭들. 긴 별칭부터 본다."""
    found: list[tuple[int, Alias]] = []
    original = text
    for a in sorted(aliases if aliases is not None else load(), key=lambda a: -len(a.written)):
        new, n = _pattern(a.written).subn(a.company, text)
        if n:
            text = new
            m = _pattern(a.written).search(original)
            found.append((m.start() if m else len(original), a))
    return text, [a for _, a in sorted(found, key=lambda x: x[0])]  # 되묻는 순서는 글에 적힌 순서


def ask_text(used: list[Alias]) -> str:
    """되묻는 말: "'삼전'은 '삼성전자' 말씀인가요?" (자회사·옛 이름이면 까닭을 덧붙인다)."""
    parts = []
    for a in used:
        w = f"'{a.written}'{topic_josa(a.written)}"
        if a.kind == "자회사":
            parts.append(f"{w} 따로 상장되지 않았어요. 지주회사인 '{a.company}' 말씀인가요?")
        elif a.kind == "옛 이름":
            ieyo = "이에요" if topic_josa(a.company) == "은" else "예요"  # 받침 있으면 '이에요'
            parts.append(f"{w} 지금 이름이 '{a.company}'{ieyo}. 이 회사 말씀인가요?")
        else:
            parts.append(f"{w} '{a.company}' 말씀인가요?")
    return " ".join(parts) + " 입력창에 바꿔 넣었어요. 맞으면 [보내기]를 눌러 주세요."


def lookup(name: str) -> Alias | None:
    """이름 하나가 표에 있으면 그 별칭 (사진에서 읽은 이름 맞추기)."""
    key = name.replace(" ", "").lower()
    return next((a for a in load() if a.written.replace(" ", "").lower() == key), None)
