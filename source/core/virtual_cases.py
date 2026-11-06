"""시연용 가상 회사·가상 고객. 실제 회사·개인 정보가 아니며 모든 화면에 '가상 사례'를 표시한다.

금액은 원 단위. 실제 데이터가 들어오면 core 테이블(core_dividend_year 등)에서 같은 모양으로 채운다.
"""
from dataclasses import dataclass, field

from core.valueup import DividendTarget

EOK = 100_000_000  # 억 원


@dataclass(frozen=True)
class VirtualCompany:
    name: str
    kind_2025: bool  # 2025 사업연도 배당이 KIND 고배당기업 공시상 '해당'인지 (공시 사실)
    b2024: int | None
    b2025: int | None
    d2024: int
    d2025: int
    ni_history: dict  # {사업연도: 지배주주 순이익}
    liabilities_2025: int
    equity_2025: int
    issued_shares: int
    treasury_shares: int
    dps_2025_final: int  # 2025 결산 주당배당금 (2026년 봄 수령)
    dps_2026_interim: int  # 이미 결의한 2026 중간·분기 주당배당금 (2026년 수령)
    reduction_unconfirmed: bool = False
    target: DividendTarget | None = None
    implementation: str | None = None
    sources: list[str] = field(default_factory=list)

    @property
    def outstanding_shares(self) -> int:
        return self.issued_shares - self.treasury_shares

    @property
    def declared_2026(self) -> int:
        """이미 결의한 2026 사업연도 중간·분기배당 총액 (추가 필요액에서 뺌)."""
        return self.dps_2026_interim * self.outstanding_shares


COMPANIES = {
    "C사": VirtualCompany(
        name="C사", kind_2025=True,
        b2024=400 * EOK, b2025=460 * EOK, d2024=400 * EOK, d2025=460 * EOK,
        ni_history={2023: 1_100 * EOK, 2024: 1_650 * EOK, 2025: 1_500 * EOK},
        liabilities_2025=8_000 * EOK, equity_2025=12_000 * EOK,
        issued_shares=10_000_000, treasury_shares=200_000,
        dps_2025_final=4_700, dps_2026_interim=1_000,
        target=DividendTarget("배당성향", "35", denominator=1_500 * EOK, source="기업가치 제고 계획(가상) p.12"),
        sources=["DART 접수번호: 가상 회사라 없음", "KIND 원문: 가상 회사라 없음", "조세특례제한법 제104조의27"],
    ),
    "E사": VirtualCompany(
        name="E사", kind_2025=True,
        b2024=150 * EOK, b2025=160 * EOK, d2024=150 * EOK, d2025=160 * EOK,
        ni_history={2023: 500 * EOK, 2024: 480 * EOK, 2025: 520 * EOK},
        liabilities_2025=3_000 * EOK, equity_2025=4_000 * EOK,
        issued_shares=8_000_000, treasury_shares=0,
        dps_2025_final=2_000, dps_2026_interim=500,
        reduction_unconfirmed=True,
        sources=["DART 접수번호: 가상 회사라 없음"],
    ),
}

# 입력 문장에 쓰일 이름 → 표준 회사명
KNOWN_NAMES = {name: name for name in COMPANIES}


@dataclass(frozen=True)
class VirtualCustomer:
    """기획안 '가상 고객 5건'. base_without_financial은 금융소득을 뺀 종합소득 과세표준(공제가 남으면 음수)."""

    label: str
    holdings: dict  # {회사명: 주식 수}
    interest: int
    other_dividend: int  # 배당가산 대상 국내 주식 배당(특례 아님)
    foreign_dividend: int  # 배당가산 비대상(해외주식·ETF·펀드)
    base_without_financial: int
    has_other_income: bool = False


CUSTOMERS = [
    VirtualCustomer("① 금융소득 2천만 원 이하", {"C사": 300}, 5_000_000, 0, 0, 40_000_000),
    VirtualCustomer("② 특례를 빼면 2천만 원 이하", {"C사": 3_000}, 10_000_000, 0, 0, 80_000_000),
    VirtualCustomer("③ 특례를 빼도 2천만 원 초과", {"C사": 6_000}, 15_000_000, 10_000_000, 0, 120_000_000),
    VirtualCustomer("④ 다른 소득이 거의 없음", {"C사": 15_000}, 0, 0, 0, -1_500_000),
    VirtualCustomer("⑤ 판정 보류 종목 포함", {"C사": 3_000, "E사": 1_200}, 5_000_000, 0, 0, 60_000_000),
]
