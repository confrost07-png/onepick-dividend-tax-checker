"""밸류업 약속 비교: 회사의 배당 목표를 2026 사업연도 배당총액으로 환산해 최소 필요 배당액과 비교한다.

[팀 해석] 결과는 '최소액 이상 / 최소액 미만 / 비교 불가' 세 가지로만 표시한다.
          회사가 약속을 지킬지는 예측하지 않는다.
[팀 해석] 배당성향 목표는 회사가 쓴 분모로 환산하고, 세법 기준(지배주주 순이익)과 다르면 표시한다.
[팀 해석] 주당배당금 목표는 유통주식수(발행주식 − 자기주식)를 곱한다.
"""
from dataclasses import dataclass, field
from fractions import Fraction

from core.min_dividend import COMPUTED, MinResult

AT_LEAST = "최소액 이상"
BELOW = "최소액 미만"
NOT_COMPARABLE = "비교 불가"
UNVERIFIED_IMPLEMENTATION = "이행 내역 미확인"
MET = "목표 이상 배당"
SHORT = "목표 미만 배당"


@dataclass(frozen=True)
class DividendTarget:
    """기업가치 제고 계획에서 원문 대조를 마친 배당 목표 하나.

    kind: "배당성향" / "주당배당금" / "총액"
    value: 배당성향이면 % (예: "35" 또는 "37.5"), 주당배당금·총액이면 원
    denominator: 배당성향 목표의 분모로 회사가 쓴 이익 금액(원)
    denominator_is_tax_basis: 분모가 세법 기준(연결 지배주주 순이익)과 같은지
    source: 원문 위치(공시 접수번호·쪽)
    """

    kind: str
    value: str | int
    denominator: int | None = None
    denominator_is_tax_basis: bool = True
    issued_shares: int | None = None
    treasury_shares: int | None = None
    source: str = ""


@dataclass
class ValueupComparison:
    status: str
    target_amount: int | None = None  # 원 단위 내림(표시용)
    notes: list[str] = field(default_factory=list)
    implementation: str = UNVERIFIED_IMPLEMENTATION
    source: str = ""


def target_amount(t: DividendTarget) -> Fraction | None:
    """목표를 2026 사업연도 배당총액(원)으로 환산한다. 환산할 수 없으면 None."""
    if t.kind == "총액":
        return Fraction(int(t.value))
    if t.kind == "주당배당금":
        if t.issued_shares is None or t.treasury_shares is None:
            return None
        return Fraction(int(t.value)) * (t.issued_shares - t.treasury_shares)
    if t.kind == "배당성향":
        if t.denominator is None:
            return None
        return Fraction(str(t.value)) / 100 * t.denominator
    raise ValueError(f"알 수 없는 목표 종류: {t.kind}")


@dataclass(frozen=True)
class PastTarget:
    """이미 끝난 사업연도(year)를 대상으로 한 과거 계획의 배당 목표. 검토자가 원문과 대조한 것만."""

    year: int
    kind: str  # 배당성향 / 주당배당금 / 총액
    value: str | int
    basis_note: str = ""
    source: str = ""


def _fmt(kind: str, v: Fraction) -> str:
    if kind == "배당성향":
        return f"{float(v):.1f}%"
    return f"{int(v):,}원"


def implementation(t: PastTarget, d_won, ni_won, dps_won) -> str | None:
    """과거 목표와 그해 실제 배당을 같은 단위로 대조한다. 실제 숫자가 없으면 None ('이행 내역 미확인' 유지).

    [팀 해석] 배당성향 = 그해 D ÷ 지배주주 순이익(세법 기준). 회사 분모가 다르면 그 사실을 함께 적는다.
              주당배당금 = 사업보고서 보통주 주당 현금배당금, 총액 = 그해 D. 목표와 같으면 '목표 이상'.
    """
    target = Fraction(str(t.value))
    if t.kind == "배당성향":
        if d_won is None or ni_won is None or Fraction(str(ni_won)) <= 0:
            return None
        actual = Fraction(str(d_won)) * 100 / Fraction(str(ni_won))
    elif t.kind == "주당배당금":
        if dps_won is None:
            return None
        actual = Fraction(str(dps_won))
    elif t.kind == "총액":
        if d_won is None:
            return None
        actual = Fraction(str(d_won))
    else:
        raise ValueError(f"알 수 없는 목표 종류: {t.kind}")
    text = (f"{t.year} 사업연도 {t.kind} 목표 {_fmt(t.kind, target)} → 실제 {_fmt(t.kind, actual)} "
            f"({MET if actual >= target else SHORT})")
    if t.kind == "배당성향" and t.basis_note:
        text += " · 회사 분모와 세법 기준(지배주주 순이익)이 다를 수 있음"
    return text


def compare(target: DividendTarget | None, minimum: MinResult, implementation: str | None = None) -> ValueupComparison:
    if target is None:
        return ValueupComparison(NOT_COMPARABLE, notes=["원문 대조를 마친 배당 목표가 없음"],
                                 implementation=implementation or UNVERIFIED_IMPLEMENTATION)

    amount = target_amount(target)
    result = ValueupComparison(NOT_COMPARABLE, source=target.source)
    if implementation:
        result.implementation = implementation
    if target.kind == "배당성향" and not target.denominator_is_tax_basis:
        result.notes.append("회사 배당성향의 분모가 세법 기준(지배주주 순이익)과 다름")
    if amount is None:
        result.notes.append("목표를 금액으로 환산할 자료가 없음")
        return result
    result.target_amount = int(amount)  # 내림
    if minimum.status != COMPUTED:
        result.notes.append(f"최소 필요 배당액이 '{minimum.status}'라 비교할 수 없음")
        return result
    result.status = AT_LEAST if amount >= minimum.amount else BELOW
    return result
