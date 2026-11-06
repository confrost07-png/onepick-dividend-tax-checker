"""F-03·F-07: 기업가치 제고 계획 공시 본문에서 배당 목표·배당 정책 문장을 뽑는다 (사람이 원문 확인하기 전 후보).

[PRD v0.2 F-07] AI(코드) 추출 후 사람이 원문을 확인하고, 확인하지 않은 항목은 화면에 보이지 않는다.
문장은 원문 글자 그대로 두고, 코드가 읽은 목표(종류·값)는 따로 적는다. 회사가 약속을 지킬지는 예측하지 않는다.
"""
import re
from dataclasses import dataclass

SECTIONS = {"2. 주요 내용": r"^2\.\s*주요\s*내용", "6. 기타 투자판단과 관련한 중요사항": r"^\d\.\s*기타\s*투자판단"}
CATEGORIES = [("배당 목표", r"배당성향|주당\s*배당금|DPS|배당금|현금배당|배당\s*총액|분기배당|배당\s*정책"),
              ("자사주", r"자사주|자기주식|소각|매입"),
              ("주주환원율", r"주주환원율|환원율|TSR"),
              ("투자 계획", r"투자|CAPEX|자본적\s*지출|M&A|설비")]
_SPLIT = re.compile(r"\s(?=-\s)|(?<=\.)\s(?=\d+\.\s)|(?=<[^>]{1,10}>)|(?=\(\d\)\s)|(?=\[[^\]]{1,12}\])|(?=※)")


@dataclass
class PolicyItem:
    section: str
    category: str
    text: str
    target_kind: str = ""   # 배당성향 / 주당배당금 / 총액
    target_value: str = ""  # % 또는 원
    basis_note: str = ""    # 분모가 세법 기준(연결 지배주주 순이익)과 다를 수 있다는 표시


def sections(lines: list[str]) -> dict[str, str]:
    out = {}
    for ln in lines:
        cells = [c.strip() for c in ln.split("|")]
        for name, pat in SECTIONS.items():
            if re.match(pat, cells[0]) and len(cells) > 1:
                out[name] = " ".join(c for c in cells[1:] if c)
    return out


def fragments(text: str) -> list[str]:
    return [f.strip(" -·") for f in _SPLIT.split(text or "") if len(f.strip(" -·")) >= 6]


def read_target(text: str) -> tuple[str, str, str]:
    """문장 → (목표 종류, 값, 분모 메모). 못 읽으면 빈 글."""
    t = text.replace(",", "")
    m = re.search(r"배당성향[^0-9%]{0,20}(\d+(?:\.\d+)?)\s*%", t)
    if m:
        note = "별도 기준으로 보임 (세법 기준은 연결 지배주주 순이익)" if "별도" in t else ""
        if "조정" in t or "일회성" in t:
            note = (note + " · " if note else "") + "회사가 조정한 순이익 기준일 수 있음"
        return "배당성향", m.group(1), note
    m = re.search(r"(?:주당\s*배당금|DPS)[^0-9]{0,20}(\d+)\s*원", t)
    if m:
        return "주당배당금", m.group(1), "유통주식 수가 있어야 총액으로 환산"
    m = re.search(r"배당(?:금)?\s*총액[^0-9]{0,15}(\d+(?:\.\d+)?)\s*(조|억)\s*원", t)
    if m:
        unit = 10 ** 12 if m.group(2) == "조" else 10 ** 8
        return "총액", str(int(float(m.group(1)) * unit)), ""
    return "", "", ""


def extract(lines: list[str]) -> list[PolicyItem]:
    out = []
    for sec, text in sections(lines).items():
        for frag in fragments(text):
            cat = next((c for c, pat in CATEGORIES if re.search(pat, frag)), None)
            if cat is None:
                continue
            kind, value, note = read_target(frag) if cat == "배당 목표" else ("", "", "")
            out.append(PolicyItem(sec, cat, frag, kind, value, note))
    return out
