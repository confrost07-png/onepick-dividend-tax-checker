"""최소 필요 배당액: 2027 사업연도 배당도 고배당기업 요건을 채우려면
회사가 2026 사업연도 몫으로 최소 얼마를 배당해야 하는지 계산한다.

[조문] 요건은 core.judgement와 같다(2027 판정은 2026 숫자로 함).
[팀 해석] B2026 = D2026(전부 과세되는 현금 이익배당)일 때만 산출한다.
[팀 해석] 2026년 부채·자본은 2025년 말 상태가 유지된다고 가정한다.
[팀 해석] 순이익 시나리오는 최근 3년(2023~2025) 최저·2025년·최고값이고 기본은 2025년이다.

  흑자:              max(B2024, min(0.40×NI, max(0.25×NI, 1.10×D2025)))
  흑자·D2025 = 0:    max(B2024, 0.40×NI)   (가목 기준으로 보수적 표시)
  적자·부채 ≤ 2배:   max(B2024, 1.10×D2025)
  적자·부채 > 2배:   충족 불가
  최소액은 원 단위 올림.
"""
from dataclasses import dataclass, field

from core.judgement import JudgeInput, MET, judge

COMPUTED = "산출"
IMPOSSIBLE = "충족 불가"
HOLD = "판정 보류"

ASSUMPTIONS = [
    "2026 사업연도 배당이 전부 과세되는 현금 이익배당이라고 가정(B2026 = D2026)",
    "2026년 부채·자본은 2025년 말 상태가 유지된다고 가정",
    "순이익 가정에 따른 값이며 실제 배당 계획이나 배당가능액이 아님",
]
CHECK_SCHEDULE = "실제 배당액은 2027년 2~3월 배당 결정 공시에서 확인할 수 있습니다."


def _ceil_ratio(amount: int, num: int, den: int) -> int:
    """amount × num / den 을 원 단위로 올림한다(정수 연산)."""
    return -(-amount * num // den)


@dataclass(frozen=True)
class MinInput:
    b2024: int | None
    d2025: int | None
    ni2026: int | None
    liabilities: int | None = None
    equity: int | None = None
    b_equals_d: bool = True  # 주식배당·비과세 감액배당이 섞이면 False


@dataclass
class MinResult:
    status: str
    amount: int | None = None
    basis: str = ""
    reasons: list[str] = field(default_factory=list)


def min_required(x: MinInput) -> MinResult:
    missing = [n for n, v in [("B(2024)", x.b2024), ("D(2025)", x.d2025), ("NI(2026 가정)", x.ni2026)] if v is None]
    if missing:
        return MinResult(HOLD, reasons=[f"자료 결측: {', '.join(missing)}"])
    if not x.b_equals_d:
        return MinResult(HOLD, reasons=["배당소득(B)과 이익배당금액(D)이 달라 따로 계산이 필요함"])

    if x.ni2026 > 0:
        cap40 = _ceil_ratio(x.ni2026, 40, 100)
        if x.d2025 == 0:
            return MinResult(COMPUTED, max(x.b2024, cap40), "가목 기준(2025 무배당이라 보수적으로 표시)")
        floor25 = _ceil_ratio(x.ni2026, 25, 100)
        grow10 = _ceil_ratio(x.d2025, 110, 100)
        amount = max(x.b2024, min(cap40, max(floor25, grow10)))
        basis = "가목(배당성향 40%)" if amount == cap40 and cap40 < max(floor25, grow10) else "나목(25% 이상·10% 증가)"
        if amount == x.b2024 and x.b2024 > min(cap40, max(floor25, grow10)):
            basis = "제2호(2024 배당소득 이상)"
        return MinResult(COMPUTED, amount, basis)

    if x.liabilities is None or x.equity is None:
        return MinResult(HOLD, reasons=["적자 가정인데 부채·자본총계 결측"])
    if x.equity <= 0:
        return MinResult(HOLD, reasons=["적자이면서 자본잠식: 부채 기준 해석 미확인"])
    if x.liabilities > 2 * x.equity:
        return MinResult(IMPOSSIBLE, reasons=["적자이고 부채가 자본총액의 2배 초과: 배당성향 0% 간주"])
    if x.d2025 == 0:
        return MinResult(HOLD, reasons=["적자 가정이고 2025 무배당: 0에서의 증가를 '10% 증가'로 볼지 미확인"])
    return MinResult(COMPUTED, max(x.b2024, _ceil_ratio(x.d2025, 110, 100)), "적자 25% 간주, 나목 10% 증가")


def passes_2027(dividend_2026: int, x: MinInput) -> bool:
    """2026 몫 배당을 dividend_2026(= B2026 = D2026)으로 했을 때 2027 판정이 충족인지."""
    j = judge(JudgeInput(
        b_prev=dividend_2026, b_2024=x.b2024, d_prev=dividend_2026, d_prevprev=x.d2025,
        ni_prev=x.ni2026, liabilities=x.liabilities, equity=x.equity,
    ))
    return j.status == MET


@dataclass
class Scenario:
    label: str
    ni2026: int
    result: MinResult
    ratio_to_2025_pct: float | None = None  # 최소액 ÷ D2025 × 100 (표시용)
    additional_needed: int | None = None  # 이미 결의한 2026 배당을 뺀 금액
    pass_if_same_as_2025: bool | None = None


def scenarios(b2024, d2025, ni_history: dict[int, int], liabilities=None, equity=None,
              declared_2026: int = 0, b_equals_d: bool = True) -> list[Scenario]:
    """순이익 시나리오(최근 3년 최저·2025년·최고)별 최소 필요 배당액.

    ni_history: {2023: NI, 2024: NI, 2025: NI}. 값이 같은 시나리오는 하나로 합친다.
    declared_2026: 이미 결의한 2026 사업연도 중간·분기배당 합계(같은 집계 범위)
    """
    values = [v for v in ni_history.values() if v is not None]
    if 2025 not in ni_history or ni_history[2025] is None or not values:
        return []
    candidates = [("최근 3년 최저", min(values)), ("2025년 (기본)", ni_history[2025]), ("최근 3년 최고", max(values))]

    out: list[Scenario] = []
    seen: set[int] = set()
    for label, ni in candidates:
        if ni in seen:
            continue
        seen.add(ni)
        x = MinInput(b2024, d2025, ni, liabilities, equity, b_equals_d)
        r = min_required(x)
        s = Scenario(label, ni, r)
        if r.status == COMPUTED:
            if d2025:
                s.ratio_to_2025_pct = round(r.amount * 100 / d2025, 1)
            s.additional_needed = max(0, r.amount - declared_2026)
            if d2025 is not None:
                s.pass_if_same_as_2025 = passes_2027(d2025, x)
        out.append(s)
    return out


def level(result: MinResult, d2025: int | None) -> str:
    """고객 요약의 '최소 필요 배당액 수준': 유지로 충분 / 늘려야 함 / 어려움 / 판정 보류."""
    if result.status == IMPOSSIBLE:
        return "어려움"
    if result.status != COMPUTED or d2025 is None:
        return HOLD
    return "유지로 충분" if result.amount <= d2025 else "늘려야 함"
