"""F-06 재무 여력: 최소 필요 배당액이 회사에 얼마나 부담인지 보는 지표. 합격점은 두지 않는다 (PRD v0.2 F-06).

- 잉여현금 = 영업활동 현금흐름 − 유형자산 취득 (2025 사업연도, DART 재무 API 현금흐름표)
- 감당 배수 = 잉여현금 ÷ 최소 필요 배당액(2027 사업연도 배당 유지 조건, 2025년 기본 시나리오)
- 수익성: ROE = 지배주주 순이익 ÷ 자본총계 / 안정성: 부채비율 = 부채총계 ÷ 자본총계
- 은행·보험·증권 등 금융업은 현금흐름 구조가 달라 미적용. 최소액이 보류·충족 불가면 미표시.
"""
import re
from dataclasses import dataclass
from statistics import median

FINANCIAL = re.compile(r"은행|보험|증권|금융|신탁|캐피탈|투자업|여신")
FINANCIAL_NAME = re.compile(r"금융|은행|증권|보험|캐피탈|신한지주|BNK|DGB|JB")  # 업종이 '지주회사'로만 적힌 금융지주
NOT_APPLIED, NOT_SHOWN, SHOWN = "미적용(금융업)", "미표시(최소액 보류·충족 불가)", "표시"


@dataclass
class Capacity:
    status: str
    fcf: float | None = None
    cover: float | None = None  # 잉여현금 ÷ 최소액 (배)
    roe_pct: float | None = None
    debt_pct: float | None = None
    note: str = ""


def is_financial(industry: str | None, name: str = "") -> bool:
    return bool(industry and FINANCIAL.search(industry)) or bool(name and FINANCIAL_NAME.search(name))


def capacity(industry, ocf, capex, min_amount, ni, liabilities, equity, name: str = "") -> Capacity:
    if is_financial(industry, name):
        return Capacity(NOT_APPLIED, note=f"업종 '{industry}'")
    roe = round(ni / equity * 100, 1) if ni is not None and equity else None
    debt = round(liabilities / equity * 100, 1) if liabilities is not None and equity and equity > 0 else None
    if not min_amount:
        return Capacity(NOT_SHOWN, roe_pct=roe, debt_pct=debt)
    if ocf is None:
        return Capacity(SHOWN, roe_pct=roe, debt_pct=debt, note="현금흐름표 영업활동 현금흐름 없음")
    fcf = ocf - abs(capex or 0)
    note = "" if capex is not None else "유형자산 취득 줄 없음(0으로 봄)"
    return Capacity(SHOWN, fcf, round(fcf / min_amount, 2), roe, debt, note)


def industry_median(values: dict[str, list[float]], industry: str, overall: list[float], min_n: int = 5):
    """같은 업종 감당 배수 중앙값 (회사가 min_n곳 미만이면 전체 중앙값). → (값, 기준 글)."""
    same = values.get(industry, [])
    if len(same) >= min_n:
        return round(median(same), 2), f"같은 업종 {len(same)}곳 중앙값"
    return (round(median(overall), 2) if overall else None), f"같은 업종이 {len(same)}곳뿐이라 전체 {len(overall)}곳 중앙값"
