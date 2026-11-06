"""1층 요건 판정: 고배당기업 요건(조세특례제한법 제104조의27 제1항) 충족 여부.

[조문] 제2호: 직전 사업연도 배당소득(B)이 2024 사업연도 배당소득보다 줄지 않을 것
[조문] 제3호 가목: 직전 사업연도 배당성향 40% 이상
[조문] 제3호 나목: 직전 사업연도 배당성향 25% 이상이고 이익배당금액(D)이 전전 대비 10% 이상 증가
[조문] 시행령 제104조의24 제5항: 순이익이 0 이하면 부채 > 자본총액×2일 때 0%, 아니면 25%로 간주
[팀 해석] 판정 연도 연결(2026 사업연도 배당은 2025 숫자로 판정), 판정 보류 사유

비율은 나누지 않고 원 단위 정수끼리 곱해 비교한다(경계값 오차 방지).
"""
from dataclasses import dataclass, field, replace

MET = "충족"
NOT_MET = "미충족"
HOLD = "판정 보류"

ARTICLES = [
    "조세특례제한법 제104조의27 제1항",
    "조세특례제한법 시행령 제104조의24",
    "조세특례제한법 시행규칙 제47조의3",
]


@dataclass(frozen=True)
class JudgeInput:
    """한 회사의 판정에 쓰는 숫자. 금액은 모두 원 단위, 모르면 None.

    b_prev: 직전 사업연도 배당소득 B
    b_2024: 2024 사업연도 배당소득 B (제2호 기준선)
    d_prev: 직전 사업연도 이익배당금액 D
    d_prevprev: 전전 사업연도 이익배당금액 D
    ni_prev: 직전 사업연도 지배주주 순이익 NI
    liabilities, equity: 직전 사업연도 말 연결 부채총계·자본총계 (적자일 때만 씀)
    reduction_unconfirmed: 감액배당 금액이나 과세 여부를 확인하지 못함
    d_unit, ni_unit: 원천 값의 단위(원). DART 현금배당총액·02 순이익은 백만 원 단위라 1_000_000.
                     단위 오차 안에서 결과가 바뀔 수 있으면 원 단위 원값으로 재확인하라고 표시한다.
    """

    b_prev: int | None
    b_2024: int | None
    d_prev: int | None
    d_prevprev: int | None
    ni_prev: int | None
    liabilities: int | None = None
    equity: int | None = None
    reduction_unconfirmed: bool = False
    d_unit: int = 1
    ni_unit: int = 1


RECHECK_NOTE = "경계 근처: 백만 원 단위 값이라 배당 결정 공시 합계 등 원 단위 원값으로 재확인 필요"


@dataclass
class Judgement:
    status: str
    route: str | None = None  # "가목" / "나목"
    deemed_payout: int | None = None  # 적자로 간주한 배당성향(%): 25 / 0. 실제 배당성향이면 None
    reasons: list[str] = field(default_factory=list)
    articles: list[str] = field(default_factory=lambda: list(ARTICLES))
    needs_recheck: bool = False

    @property
    def tag(self) -> str:
        """화면 꼬리표. 계산 결과는 공식 해설 전까지 '현재 해석 기준'이다."""
        return HOLD if self.status == HOLD else "현재 해석 기준"


def _grew_10pct(d_prev: int, d_prevprev: int) -> bool:
    return 10 * d_prev >= 11 * d_prevprev


def judge(x: JudgeInput) -> Judgement:
    """직전·전전 사업연도 숫자로 다음 배당의 고배당기업 요건을 판정한다.

    D·NI가 단위(d_unit, ni_unit)로 반올림된 값이면, 각 값을 ±단위만큼 흔들어
    결과(충족 여부·가목/나목)가 달라지는지 보고 달라지면 needs_recheck를 켠다.
    """
    result = _judge_exact(x)
    if (x.d_unit > 1 or x.ni_unit > 1) and result.status != HOLD:
        outcomes = set()
        for dd in (-x.d_unit, x.d_unit):
            for dpp in (-x.d_unit, x.d_unit):
                for dn in (-x.ni_unit, x.ni_unit):
                    shaken = replace(
                        x, d_prev=x.d_prev + dd, d_prevprev=max(0, x.d_prevprev + dpp) if x.d_prevprev else 0,
                        ni_prev=x.ni_prev + dn, d_unit=1, ni_unit=1,
                    )
                    r = _judge_exact(shaken)
                    outcomes.add((r.status, r.route))
        if len(outcomes | {(result.status, result.route)}) > 1:
            result.needs_recheck = True
            result.reasons.append(RECHECK_NOTE)
    return result


def _judge_exact(x: JudgeInput) -> Judgement:
    missing = [name for name, v in [
        ("B(직전)", x.b_prev), ("B(2024)", x.b_2024), ("D(직전)", x.d_prev),
        ("D(전전)", x.d_prevprev), ("NI(직전)", x.ni_prev),
    ] if v is None]
    if missing:
        return Judgement(HOLD, reasons=[f"자료 결측: {', '.join(missing)}"])
    if x.reduction_unconfirmed:
        return Judgement(HOLD, reasons=["감액배당 금액 또는 과세 여부를 확인하지 못함"])

    if x.b_prev < x.b_2024:
        return Judgement(NOT_MET, reasons=["제2호 미충족: 배당소득이 2024 사업연도보다 줄어듦"])

    if x.ni_prev <= 0:
        return _judge_deficit(x)

    if 100 * x.d_prev >= 40 * x.ni_prev:
        return Judgement(MET, route="가목", reasons=["배당성향 40% 이상"])
    if 100 * x.d_prev < 25 * x.ni_prev:
        return Judgement(NOT_MET, reasons=["배당성향 25% 미만"])
    if x.d_prevprev == 0:
        return Judgement(HOLD, reasons=["전전 사업연도 무배당: 0에서의 증가를 '10% 증가'로 볼지 미확인"])
    if _grew_10pct(x.d_prev, x.d_prevprev):
        return Judgement(MET, route="나목", reasons=["배당성향 25% 이상, 이익배당금액 10% 이상 증가"])
    return Judgement(NOT_MET, reasons=["배당성향 25~40%이지만 이익배당금액 10% 증가 미달"])


def _judge_deficit(x: JudgeInput) -> Judgement:
    """순이익 0 이하: 시행령 제104조의24 제5항 간주 규정을 먼저 적용한다."""
    if x.liabilities is None or x.equity is None:
        return Judgement(HOLD, reasons=["적자 회사인데 부채·자본총계 결측"])
    if x.equity <= 0:
        return Judgement(HOLD, reasons=["적자이면서 자본잠식: 부채 기준 해석 미확인"])
    # [팀 해석] 정확히 2배는 '초과'가 아니다
    if x.liabilities > 2 * x.equity:
        return Judgement(NOT_MET, deemed_payout=0, reasons=["적자이고 부채가 자본총액의 2배 초과: 배당성향 0% 간주"])
    # 25% 간주 → 가목(40%)은 불가, 나목의 10% 증가만 확인
    if x.d_prevprev == 0 and x.d_prev == 0:
        # [팀 해석, 2026-10-26 팀 확정 대응표] 직전·전전 모두 무배당이면 증가 없음
        return Judgement(NOT_MET, deemed_payout=25, reasons=["적자로 배당성향 25% 간주, 직전·전전 모두 무배당이라 증가 없음"])
    if x.d_prevprev == 0:
        return Judgement(HOLD, deemed_payout=25, reasons=["전전 사업연도 무배당: 0에서의 증가를 '10% 증가'로 볼지 미확인"])
    if _grew_10pct(x.d_prev, x.d_prevprev):
        return Judgement(MET, route="나목", deemed_payout=25, reasons=["적자로 배당성향 25% 간주, 이익배당금액 10% 이상 증가"])
    return Judgement(NOT_MET, deemed_payout=25, reasons=["적자로 배당성향 25% 간주, 이익배당금액 10% 증가 미달"])


def judge_2026(b2025, b2024, d2025, d2024, ni2025, liabilities=None, equity=None, reduction_unconfirmed=False,
               d_unit=1, ni_unit=1) -> Judgement:
    """2026 사업연도 배당 판정 [팀 해석: 2025 사업연도 숫자로 판정]."""
    return judge(JudgeInput(b2025, b2024, d2025, d2024, ni2025, liabilities, equity, reduction_unconfirmed, d_unit, ni_unit))
