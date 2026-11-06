"""밸류업 계획 문단에서 약속(숫자 목표·실행 약속)을 정해진 단어 규칙으로 찾는다 (분석 설계 D1).

[프로젝트 원칙] 생성형 AI를 쓰지 않는다. 문단은 원문 글자 그대로 두고, 규칙이 읽은 종류·값만 따로 적는다.
사람이 원문을 확인하기 전의 '후보'이며, 화면 카드에는 사람이 확인한 값(core.core_policy_item)만 쓴다.

- 숫자 목표: 배당성향·주당배당금·배당 총액(core.policy_extract.read_target 재사용), ROE, 주주환원율, PBR.
  문장 조각에 목표를 뜻하는 말(목표·이상·지향·달성·까지·상향·수준·유지·확대 등)이 함께 있어야 한다.
  과거 실적을 적은 표·그림 글자는 숫자가 많고 길어서, 너무 긴 조각은 쓰지 않는다.
- 실행 약속(숫자 없음): 자사주 소각, 분기·중간배당, 분리과세 언급.
"""
import re
from dataclasses import dataclass

from core import policy_extract as pe

CUE = re.compile(r"목표|이상|지향|달성|까지|상향|수준|유지|확대|추진|Target|target", re.I)
MAX_FRAGMENT = 300
_EXTRA_SPLIT = re.compile(r"\s*[•▪■●◦]\s*|(?<=[다음함임])\.\s+")
NUMERIC = {  # 종류: (지표 글자, 값 단위, 그럴듯한 범위)
    "ROE": (r"ROE|자기자본\s*이익률", "%", (1, 50)),
    "주주환원율": (r"(?:총\s*)?주주\s*환원\s*율|주주환원\s*비율", "%", (5, 150)),
    "PBR": (r"PBR|주가\s*순자산\s*비율", "배", (0.3, 10)),
}
DIVIDEND_RANGE = {"배당성향": (5, 100), "주당배당금": (10, 1_000_000), "총액": (1, 10 ** 15)}
ACTIONS = {
    "자사주 소각": re.compile(r"(?:자사주|자기\s*주식)[^。]{0,40}소각|소각[^。]{0,20}(?:자사주|자기\s*주식)"),
    "분기·중간배당": re.compile(r"분기\s*배당|중간\s*배당|반기\s*배당"),
    "분리과세 언급": re.compile(r"분리\s*과세"),
}
KINDS = ("배당성향", "주당배당금", "총액", "ROE", "주주환원율", "PBR")


@dataclass(frozen=True)
class Promise:
    kind: str     # 배당성향 / 주당배당금 / 총액 / ROE / 주주환원율 / PBR / 자사주 소각 / 분기·중간배당 / 분리과세 언급
    value: str    # 숫자 목표면 값(%·원·배), 실행 약속이면 빈 글
    text: str     # 원문 조각(글자 그대로)


def pieces(text: str) -> list[str]:
    out = []
    for f in pe.fragments(re.sub(r"\s+", " ", text or "")):
        out += [p.strip() for p in _EXTRA_SPLIT.split(f) if len(p.strip()) >= 6]
    return out


def _in_range(v: str, rng) -> bool:
    try:
        return rng[0] <= float(v) <= rng[1]
    except ValueError:
        return False


def numeric(fragment: str) -> list[Promise]:
    if len(fragment) > MAX_FRAGMENT or not CUE.search(fragment):
        return []
    out = []
    kind, value, _ = pe.read_target(fragment)
    if kind and _in_range(value, DIVIDEND_RANGE[kind]):
        out.append(Promise(kind, value, fragment))
    t = fragment.replace(",", "")
    for kind, (metric, unit, rng) in NUMERIC.items():
        m = re.search(rf"(?:{metric})[^0-9%]{{0,25}}(\d+(?:\.\d+)?)\s*{unit}", t)
        if m and _in_range(m.group(1), rng):
            out.append(Promise(kind, m.group(1), fragment))
    return out


def find(text: str) -> list[Promise]:
    """문단 하나에서 약속 후보. 같은 (종류, 값)은 한 번만."""
    out, seen = [], set()
    for f in pieces(text):
        found = numeric(f) + [Promise(k, "", f) for k, rx in ACTIONS.items() if rx.search(f)]
        for p in found:
            if (p.kind, p.value) not in seen:
                seen.add((p.kind, p.value))
                out.append(p)
    return out


def same_value(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return a == b
