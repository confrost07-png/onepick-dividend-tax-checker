"""챗봇 점검: 고객의 보유 종목·소득 답변을 받아 판정·최소액·밸류업·세액 엔진을 한 번에 돌린다.

화면은 이 결과를 그리기만 한다. 고객 입력은 저장하지 않고 이 함수 호출 안에서만 쓴다.

특례배당소득 E(2026년 수령분) [팀 해석]
  - 2025 결산배당(2026년 봄 수령): KIND 공시상 해당이면 특례, 아니면 일반 배당
  - 2026 중간·분기배당(결의된 건): 2026 사업연도 판정이 충족이면 특례, 보류면 포함·제외 두 경우, 미충족이면 일반 배당
"""
from dataclasses import dataclass, field

from core import tax
from core.judgement import HOLD, MET, NOT_MET, Judgement, judge_2026
from core.min_dividend import Scenario, level, scenarios
from core.valueup import ValueupComparison, compare
from core.virtual_cases import COMPANIES, VirtualCompany


@dataclass
class StockCheck:
    company: VirtualCompany
    shares: int
    judgement: Judgement
    scenarios: list[Scenario]
    valueup: ValueupComparison
    special: int  # 특례배당소득 E 기여분
    held: int  # 판정 보류로 포함·제외를 나눠 볼 금액
    general: int  # 일반 배당(배당가산 대상)으로 넘어간 금액

    @property
    def base_scenario(self) -> Scenario | None:
        """2025년(기본) 시나리오. 2025 순이익이 최저·최고와 같으면 그 이름으로 합쳐져 있으므로 순이익으로 찾는다."""
        ni = self.company.ni_history.get(2025)
        return next((s for s in self.scenarios if s.label.startswith("2025")),
                    next((s for s in self.scenarios if s.ni2026 == ni), None))

    @property
    def payout_2025_pct(self) -> float | None:
        ni = self.company.ni_history.get(2025)
        return round(self.company.d2025 * 100 / ni, 1) if ni and ni > 0 else None

    @property
    def growth_2025_pct(self) -> float | None:
        d24 = self.company.d2024
        return round((self.company.d2025 - d24) * 100 / d24, 1) if d24 else None


@dataclass
class Checkup:
    stocks: list[StockCheck]
    tax: tax.TaxResult  # 판정 보류 종목이 있으면 '제외' 경우
    tax_with_held: tax.TaxResult | None = None  # 판정 보류 종목을 특례에 포함한 경우
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out = {MET: 0, HOLD: 0, NOT_MET: 0}
        for s in self.stocks:
            out[s.judgement.status] += 1
        return out

    @property
    def special_total(self) -> int:
        return sum(s.special for s in self.stocks)

    @property
    def level(self) -> tuple[str, str]:
        """(수준, 기준 회사). 판정 보류가 아닌 첫 종목 기준."""
        for s in self.stocks:
            base = s.base_scenario
            if base is not None and s.judgement.status != HOLD:
                return level(base.result, s.company.d2025), s.company.name
        return HOLD, ""


def check_stock(company: VirtualCompany, shares: int) -> StockCheck:
    c = company
    j = judge_2026(c.b2025, c.b2024, c.d2025, c.d2024, c.ni_history.get(2025),
                   c.liabilities_2025, c.equity_2025, c.reduction_unconfirmed)
    # 감액배당을 확인하지 못하면 B와 D가 같다고 볼 수 없어 최소액도 보류한다
    rows = scenarios(c.b2024, c.d2025, c.ni_history, c.liabilities_2025, c.equity_2025, c.declared_2026,
                     b_equals_d=not c.reduction_unconfirmed)
    base = next((s for s in rows if s.label.startswith("2025")), next((s for s in rows if s.ni2026 == c.ni_history.get(2025)), None))
    minimum = base.result if base else None
    vu = compare(c.target, minimum, c.implementation) if minimum else compare(None, None, c.implementation)

    # 주당배당금은 원 미만이 있을 수 있다(예: 한국금융지주 우선주 8,751.5원). 받을 금액에서 원 미만은 버린다
    final = int(c.dps_2025_final * shares)
    interim = int(c.dps_2026_interim * shares)
    special = final if c.kind_2025 else 0
    general = 0 if c.kind_2025 else final
    held = 0
    if j.status == MET:
        special += interim
    elif j.status == HOLD:
        held = interim
    else:
        general += interim
    return StockCheck(c, shares, j, rows, vu, special, held, general)


def run_checkup(holdings: dict[str, int], interest, other_dividend, foreign_dividend,
                base_without_financial, has_other_income: bool = False, companies: dict | None = None) -> Checkup:
    """holdings: {회사명: 주식 수}. 금액은 원 단위, 모르면 None. companies: {회사명: 회사}(없으면 가상 회사)."""
    book = companies if companies is not None else COMPANIES
    stocks = [check_stock(book[name], shares) for name, shares in holdings.items()]
    general = sum(s.general for s in stocks)
    held = sum(s.held for s in stocks)
    gu = None if other_dividend is None else other_dividend + general
    x = tax.TaxInput(interest, foreign_dividend, gu, sum(s.special for s in stocks),
                     base_without_financial, has_other_income)
    unknown = [n for n, v in [("이자", interest), ("다른 배당", other_dividend),
                              ("해외·펀드 배당", foreign_dividend), ("과세표준", base_without_financial)] if v is None]
    if held:
        both = tax.compare_with_held(x, held)
        return Checkup(stocks, both["제외"], both["포함"], unknown)
    return Checkup(stocks, tax.compare(x), None, unknown)
