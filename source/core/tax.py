"""2층 세액 비교: 2026년에 받는 배당(2027년 5월 신고분)의 분리과세 신청 전후 소득세.

예상 세액 차이 = T0 − (T1 + S(E))
  T0: 특례 미신청 시 연간 소득세
  T1: 특례 신청 시 특례배당(E)을 뺀 소득의 연간 소득세
  S(E): 특례배당 분리과세 세액
  양수면 신청 시 세액 감소, 음수면 증가. 화면에는 '계산상 세액 차이'로만 중립 표시한다.

계산 순서 [팀 해석: 조특법 제104조의27 제1~3항, 소득세법 제14조(④ 배당가산액은 2천만 원 판단에서 뺌)·제15조 제2호(배당세액공제 한도)·
  제17조·제56조·제62조, 소득세법 시행령 제116조의2(2천만 원을 채우는 순서)]
  ① 금융소득 합계로 2천만 원 초과 여부를 본다(분리과세를 신청한 특례배당은 뺀다)
  ② 2천만 원은 이자 → 배당가산 비대상 배당 → 대상 배당 순으로 채운다
  ③ 2천만 원을 넘는 배당가산 대상 배당에 10%를 더한다
  ④ 기본세율 적용, 비교과세(원천징수 방식과 비교해 큰 금액)
  ⑤ 배당세액공제 = min(배당가산액, 산출세액 − 비교산출세액)

지원 범위 밖(배당세액공제 외 세액공제, 지방소득세, 기납부세액)은 넣지 않는다.
"""
from dataclasses import dataclass, field

from core import tax_rates as r

COMPARED = "비교 계산"
NO_DIFFERENCE = "차이 없음"
SEPARATE_ONLY = "분리과세 세액만"

NOTICE = "참고용 모의 계산이며 확정 세액·환급액이 아니고, 실제 신고세액과 다를 수 있습니다."
EXCLUDED = ["배당세액공제 외 세액공제", "지방소득세", "기납부세액"]


@dataclass(frozen=True)
class TaxInput:
    """한 고객의 2026년 소득. 금액은 원 단위, 모르면 None.

    interest: 예금·채권 이자
    dividend_no_grossup: 배당가산 비대상 배당(해외주식·ETF·펀드 등)
    dividend_grossup: 배당가산 대상 일반 배당(특례 아닌 국내 주식 배당)
    special_dividend: 특례배당소득 후보 E(요건 충족 종목의 금전 배당)
    base_without_financial: 금융소득을 뺀 종합소득 과세표준(근로소득 과세표준).
                            종합소득공제가 남으면 음수로 넣는다(예: 본인 기본공제만 → −1,500,000)
    has_other_income: 사업·연금·기타소득이 있음
    """

    interest: int | None
    dividend_no_grossup: int | None
    dividend_grossup: int | None
    special_dividend: int
    base_without_financial: int | None
    has_other_income: bool = False


@dataclass
class ComprehensiveTax:
    tax: int
    financial_total: int
    comprehensive: bool  # 금융소득 종합과세 여부
    gross_up: int = 0
    calculated: int = 0  # 산출세액(비교과세 후)
    comparison: int = 0  # 비교산출세액
    dividend_credit: int = 0


@dataclass
class TaxResult:
    status: str
    separate_tax: int  # S(E)
    t0: ComprehensiveTax | None = None
    t1: ComprehensiveTax | None = None
    difference: int | None = None  # T0 − (T1 + S(E))
    reasons: list[str] = field(default_factory=list)
    notice: str = NOTICE

    @property
    def direction(self) -> str | None:
        """중립 표시용: 분리과세 신청 시 세액이 '감소' / '증가' / '변화 없음'."""
        if self.difference is None:
            return None
        if self.difference > 0:
            return "감소"
        return "증가" if self.difference < 0 else "변화 없음"


def separate_tax(e: int) -> int:
    """특례배당소득 분리과세 세액 S(E)."""
    return r.apply(r.SEPARATE, e)


def comprehensive_tax(interest: int, div_no_gu: int, div_gu: int, base_without_financial: int,
                      gross_up: bool = True) -> ComprehensiveTax:
    """금융소득과 다른 종합소득으로 연간 소득세(배당세액공제 후)를 계산한다.

    gross_up=False면 배당가산과 배당세액공제를 모두 빼고 계산한다.
    국세청 보도자료(2026.3.9) 참고 2 사례가 이 방식(세액공제 없다고 가정)이라 검산에 쓴다.
    """
    if not gross_up:
        div_no_gu, div_gu = div_no_gu + div_gu, 0
    fin = interest + div_no_gu + div_gu
    threshold = r.FINANCIAL_THRESHOLD
    withholding = lambda amount: amount * r.WITHHOLDING_RATE_PCT // 100  # noqa: E731

    if fin <= threshold:
        # 분리과세(원천징수로 끝남) + 다른 소득은 기본세율
        tax = r.apply(r.BASIC, base_without_financial) + withholding(fin)
        return ComprehensiveTax(tax, fin, comprehensive=False, calculated=tax)

    # ② 2천만 원을 이자 → 비대상 배당 → 대상 배당 순으로 채운다
    left = threshold - min(interest, threshold)
    left -= min(div_no_gu, left)
    gu_in_threshold = min(div_gu, left)
    gross_up = (div_gu - gu_in_threshold) * r.GROSS_UP_PCT // 100  # ③

    taxable = base_without_financial + fin + gross_up
    general = withholding(threshold) + r.apply(r.BASIC, taxable - threshold)  # ④ 일반산출세액
    comparison = withholding(fin) + r.apply(r.BASIC, taxable - fin - gross_up)  # 비교산출세액
    calculated = max(general, comparison)
    credit = min(gross_up, calculated - comparison)  # ⑤
    return ComprehensiveTax(calculated - credit, fin, True, gross_up, calculated, comparison, credit)


def compare(x: TaxInput) -> TaxResult:
    s = separate_tax(x.special_dividend)

    unknown = [n for n, v in [("이자", x.interest), ("다른 배당", x.dividend_no_grossup),
                              ("다른 배당", x.dividend_grossup)] if v is None]
    # 금융소득이 2천만 원 이하면 다른 소득·과세표준과 상관없이 원천징수로 끝난다 → 이것부터 본다
    if not unknown:
        fin_all = x.interest + x.dividend_no_grossup + x.dividend_grossup + x.special_dividend
        if fin_all <= r.FINANCIAL_THRESHOLD:
            return TaxResult(NO_DIFFERENCE, s, difference=0,
                             reasons=["금융소득이 2천만 원 이하라 분리과세를 신청해도 세액이 같음(14% 원천징수로 끝남)"])

    stop = []
    if x.has_other_income:
        stop.append("사업·연금·기타소득이 있어 계산 범위 밖")
    if x.base_without_financial is None:
        unknown.append("과세표준")
    if unknown:
        stop.append(f"모르는 항목: {', '.join(dict.fromkeys(unknown))}")
    if stop:
        return TaxResult(SEPARATE_ONLY, s, reasons=stop + ["분리과세 세액만 보여 주고 세무상담을 안내함"])

    t0 = comprehensive_tax(x.interest, x.dividend_no_grossup, x.dividend_grossup + x.special_dividend, x.base_without_financial)
    t1 = comprehensive_tax(x.interest, x.dividend_no_grossup, x.dividend_grossup, x.base_without_financial)
    return TaxResult(COMPARED, s, t0, t1, t0.tax - (t1.tax + s))


def compare_with_held(x: TaxInput, held_dividend: int) -> dict[str, TaxResult]:
    """판정 보류 종목의 배당을 특례에 포함한 경우와 일반 배당으로 둔 경우를 따로 계산한다."""
    include = TaxInput(x.interest, x.dividend_no_grossup, x.dividend_grossup,
                       x.special_dividend + held_dividend, x.base_without_financial, x.has_other_income)
    exclude = TaxInput(x.interest, x.dividend_no_grossup,
                       None if x.dividend_grossup is None else x.dividend_grossup + held_dividend,
                       x.special_dividend, x.base_without_financial, x.has_other_income)
    return {"포함": compare(include), "제외": compare(exclude)}


def special_dividend_amount(dps: int, shares: int) -> int:
    """특례배당소득 E = 공시 주당배당금 × 기준일 보유 수량 (금전 배당만, 주식배당 제외)."""
    return dps * shares
