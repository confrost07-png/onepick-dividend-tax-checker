"""주식 총수(raw.dart_share_total) 이상치 판정 → core.core_share_check. 원본은 고치지 않고 사유와 보정 배수만 남긴다.

자본금 대조: (보통+우선·종류+기타 발행주식수) × 액면가 ÷ 자본금. 1% 안이면 정상(행을 남기지 않음).
API 1,000배 오류: 회사가 사업보고서 표 단위를 '천주'로 잘못 적어 API 값이 1,000배가 된 경우(서린바이오·조선내화·네오팜 원문 확인).
  아래 두 조건이 모두 맞을 때만 ÷1,000 보정한다.
  ① 자본금 비율이 1,000배(±0.1%)
  ② 보통주 PBR(종가 × 유통주식수 ÷ 자본총계)이 API 값으로는 100 넘고, ÷1,000 하면 100 이하
그 밖의 자본금 차이는 이익소각 등으로 생길 수 있어 값은 그대로 두고 표시만 한다.
"""
from dataclasses import dataclass
from decimal import Decimal

UNIT_1000 = "API 단위 오류(1,000배)"
CAPITAL_GAP = "자본금과 차이"
NO_COMPARE = "대조 불가"
NO_COMMON = "보통주 행 없음"
FIX, MARK = "보정", "표시만"

MATCH_TOL = Decimal("0.01")
THOUSAND_TOL = Decimal("0.001")
PBR_LIMIT = Decimal("100")
RULE = "source/core/share_check.py 2026-10-27"


@dataclass
class Facts:
    has_common: bool
    issued_all: Decimal | None  # 보통+우선·종류+기타 발행주식수 (API 값)
    floating: Decimal | None    # 보통주 유통주식수 (API 값)
    par: Decimal | None         # 주당 액면가(원)
    capital: Decimal | None     # 자본금(원)
    close: Decimal | None       # 결산 기준일 이전 마지막 종가
    equity: Decimal | None      # 자본총계(원)


@dataclass
class Finding:
    check: str
    action: str
    factor: Decimal
    reason: str
    ratio: Decimal | None = None
    pbr_api: Decimal | None = None
    pbr_fixed: Decimal | None = None


def _pbr(f: Facts, factor: Decimal) -> Decimal | None:
    if f.close is None or f.floating is None or not f.equity or f.equity <= 0:
        return None
    return (f.close * f.floating * factor / f.equity).quantize(Decimal("0.01"))


def judge(f: Facts) -> Finding | None:
    """이상치면 Finding, 자본금과 1% 안에서 맞으면 None."""
    if not f.has_common:
        return Finding(NO_COMMON, MARK, Decimal(1), "API 응답에 보통주로 묶을 행이 없음(합계만 등)")
    if not f.issued_all or not f.par or not f.capital or f.par <= 0 or f.capital <= 0:
        missing = [n for n, v in (("발행주식수", f.issued_all), ("액면가", f.par), ("자본금", f.capital)) if not v]
        return Finding(NO_COMPARE, MARK, Decimal(1), f"자본금 대조 자료 없음: {', '.join(missing) or '0 이하 값'}")
    ratio = (f.issued_all * f.par / f.capital).quantize(Decimal("0.001"))
    if abs(ratio - 1) <= MATCH_TOL:
        return None
    pbr_api, pbr_fixed = _pbr(f, Decimal(1)), _pbr(f, Decimal("0.001"))
    if (abs(ratio / 1000 - 1) <= THOUSAND_TOL and pbr_api is not None
            and pbr_api > PBR_LIMIT and pbr_fixed <= PBR_LIMIT):
        return Finding(UNIT_1000, FIX, Decimal("0.001"),
                       f"발행주식수×액면이 자본금의 {ratio:,}배, PBR {pbr_api:,} → ÷1,000 하면 {pbr_fixed}. "
                       "사업보고서 표 단위를 '천주'로 잘못 적어 API 값이 1,000배로 보임", ratio, pbr_api, pbr_fixed)
    note = "PBR로 확인 못 함" if pbr_api is None else f"PBR {pbr_api:,}"
    return Finding(CAPITAL_GAP, MARK, Decimal(1),
                   f"발행주식수×액면이 자본금의 {ratio}배({note}). 이익소각·액면 변경·자본금 자료 오류 등 원인 미확인",
                   ratio, pbr_api, pbr_fixed)
