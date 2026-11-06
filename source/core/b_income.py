"""배당소득 B와 판정에 쓰는 2024·2025 배당액을 정한다. DB 없이 시험할 수 있게 순수 함수로 둔다.

[PRD v0.2 5.3] B = 현금배당 − 비과세로 확인된 감액배당 + 주식배당. 감액배당 과세 여부를 확인 못 하면 판정 보류.
- B(2024): 회사가 KIND 고배당기업 공시에 적은 '2024.12.31.이 속하는 사업연도의 배당소득' (공시 사실).
- D(2025)·D(2024): 같은 공시의 '직전·전전 사업연도 이익배당금액'(원 단위). 공시가 없으면 DART 현금배당총액(백만 원).
- B(2025) = D(2025) + 2025 주식배당금총액. 공시 메모에 감액배당이 있으면 비과세 금액을 확인하기 전까지 비우고
  '감액배당 확인 필요'로 둔다 (판정 보류).
"""
from dataclasses import dataclass

MIL = 1_000_000
KIND = "KIND 고배당기업 공시"
DART_D = "DART 사업보고서 현금배당총액"
B2025_OK = "D(2025) + 주식배당 (공시 메모에 감액배당 없음)"
B2025_HOLD = "감액배당 확인 필요"


@dataclass
class BYear:
    """한 회사의 판정용 배당 숫자 (금액은 원)."""

    b2024: float | None
    b2024_source: str
    b2025: float | None
    b2025_source: str
    d2025: float | None
    d2024: float | None
    d_source: str
    d_unit: int
    reduction_unconfirmed: bool
    reduction_note: str


def has_reduction(note: str | None) -> bool:
    return bool(note) and "감액" in note


def b_year(kind: dict | None, dart_d2025, dart_d2024, stock_div_2025=None, b2024_from_source=None) -> BYear:
    """kind: raw.kind_list 한 행(없으면 None). dart_*: DART 현금배당총액(원, 백만 원 단위 값).
    stock_div_2025: 2025 주식배당금총액(원). b2024_from_source: DB가 빈 B2024를 원문 재대조에서 읽은 값."""
    b2024, b_src = None, "없음"
    if kind and kind.get("b2024_won") is not None:
        b2024, b_src = float(kind["b2024_won"]), KIND
    elif b2024_from_source is not None:
        b2024, b_src = float(b2024_from_source), f"{KIND} 원문 (DB 빈칸)"

    if kind and str(kind.get("prev_year")) == "2025" and kind.get("prev_d_won") is not None:
        d25 = float(kind["prev_d_won"])
        d24 = float(kind["prevprev_d_won"]) if kind.get("prevprev_d_won") is not None else None
        d_src, unit = KIND, 1
    else:
        d25 = float(dart_d2025) if dart_d2025 is not None else None
        d24 = float(dart_d2024) if dart_d2024 is not None else None
        d_src, unit = DART_D, MIL

    note = (kind or {}).get("reduction_note") or ""
    reduction = has_reduction(note)
    if reduction:
        b25, b25_src = None, B2025_HOLD
    elif d25 is None:
        b25, b25_src = None, "D(2025) 결측"
    else:
        b25, b25_src = d25 + float(stock_div_2025 or 0), B2025_OK
    return BYear(b2024, b_src, b25, b25_src, d25, d24, d_src, unit, reduction, note)
