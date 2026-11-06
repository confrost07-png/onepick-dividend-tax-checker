"""판정·세액을 엔진 코드와 따로 조문 그대로 다시 계산해, DB 판정·세액 엔진 결과와 맞춰 본다 (최종 점검 2026-11-04).

실행: PYTHONPATH=source .venv/bin/python -m scripts.check_rules_independent
- 판정: core.core_judgement_2026의 입력값(B·D·NI·부채·자본)에 조특법 제104조의27 ①2·3호와
  시행령 제104조의24⑤(적자면 배당성향 25% 간주, 부채가 자본총액의 2배 초과면 0%)를 직접 적용해 저장된 판정과 비교.
  보류(자료 결측·전전 무배당)는 팀 해석이라 비교하지 않고 이유별로 센다.
- KIND 일치: 같은 입력으로 낸 배당성향(적자는 간주값)이 raw.kind_list 공시 배당성향과 1%p 이내인 회사 수.
- 세액: 소득세법 제55조·제62조·제56조, 시행령 제116조의2, 조특법 제104조의27②를 정수 계산으로 옮긴 식과
  core.tax.compare를 김춘배 페르소나·국세청 보도자료(2026.3.9) 사례 2건에서 비교.
결과 기록: report/검증/최종_점검_결과_20261104.md
"""
from collections import Counter
from decimal import Decimal

from core import db
from core import tax as engine_tax

BASIC = [(14_000_000, 6, 0), (50_000_000, 15, 1_260_000), (88_000_000, 24, 5_760_000), (150_000_000, 35, 15_440_000),
         (300_000_000, 38, 19_940_000), (500_000_000, 40, 25_940_000), (1_000_000_000, 42, 35_940_000),
         (None, 45, 65_940_000)]  # 소득세법 제55조① (상한, 세율 %, 누진공제)
SEPARATE = [(20_000_000, 14), (300_000_000, 20), (5_000_000_000, 25), (None, 30)]  # 조특법 제104조의27②


def basic_tax(base: int) -> int:
    for top, rate, ded in BASIC:
        if top is None or base <= top:
            return base * rate // 100 - ded


def separate_tax(e: int) -> int:
    tax, low = 0, 0
    for top, rate in SEPARATE:
        if e > low:
            tax += ((e if top is None else min(e, top)) - low) * rate // 100
        low = top or low
    return tax


def financial_tax(interest: int, plain: int, grossup: int, other_base: int, gross_up: bool = True) -> int:
    """금융소득 종합과세 소득세. 2천만 원은 이자 → 가산 비대상 배당 → 가산 대상 배당 순으로 채운다."""
    fin = interest + plain + grossup
    if fin <= 20_000_000:
        return fin * 14 // 100 + basic_tax(other_base)
    gu = max(0, grossup - max(0, 20_000_000 - interest - plain)) // 10 if gross_up else 0
    general = 2_800_000 + basic_tax(other_base + fin - 20_000_000 + gu)
    floor = fin * 14 // 100 + basic_tax(other_base)
    return max(general, floor) - (min(gu, general - floor) if general > floor else 0)


def statute_compare(interest: int, plain: int, special: int, other_grossup: int, base: int, gross_up: bool = True):
    t0 = financial_tax(interest, plain, special + other_grossup, base, gross_up)
    t1 = financial_tax(interest, plain, other_grossup, base, gross_up) + separate_tax(special)
    return t0, t1


def check_judgement(conn) -> None:
    rows = db.fetch_dicts(conn, """SELECT j.*, k.prev_payout_pct FROM core.core_judgement_2026 j
                                   JOIN raw.kind_list k USING (corp_code)""")
    diff, kinds, holds, kind_ok, kind_all, kind_n = [], Counter(), Counter(), 0, 0, 0
    for r in rows:
        b, b24, d, dpp, ni = r["b_prev_won"], r["b_2024_won"], r["d_prev_won"], r["d_prevprev_won"], r["ni_prev_won"]
        liab, eq = r["liabilities_won"], r["equity_won"]
        payout = None
        if ni is not None and ni > 0 and d is not None:
            payout = d * 100 / ni
        elif ni is not None and ni <= 0 and liab is not None and eq is not None and eq > 0:
            payout = Decimal(0 if liab > 2 * eq else 25)  # 시행령 제104조의24⑤
        if r["prev_payout_pct"] is not None:
            kind_n += 1
            # 발표 숫자(602/637)는 판정 표에 저장된 간주값을 쓴다: 적자이면서 보류인 회사는 간주값이 없어 '다름'으로 센다
            shown = payout if ni is not None and ni > 0 else r["deemed_payout_pct"]
            kind_ok += shown is not None and abs(shown - r["prev_payout_pct"]) <= 1
            kind_all += payout is not None and abs(payout - r["prev_payout_pct"]) <= 1
        if r["status"] == "판정 보류":
            holds[(r["reasons"] or "").split(":")[0]] += 1
            continue
        rule2 = b is not None and b24 is not None and b >= b24  # ①2호: 직전 배당소득이 2024 사업연도보다 줄지 않음
        ga = payout is not None and ni > 0 and payout >= 40
        na = payout is not None and payout >= 25 and dpp is not None and dpp > 0 and d >= dpp * Decimal("1.1")
        mine = "충족" if rule2 and (ga or na) else "미충족"
        kinds["흑자" if ni > 0 else "적자"] += 1
        if mine != r["status"]:
            diff.append((r["corp_code"], mine, r["status"], r["reasons"]))
    print(f"판정: 638곳 중 판정 {sum(kinds.values())}곳({dict(kinds)}) 조문 재계산과 다른 곳 {len(diff)}곳 {diff[:5]}")
    print(f"      보류 {sum(holds.values())}곳 {dict(holds)}")
    print(f"KIND 배당성향 1%p 이내: {kind_ok}/{kind_n} = {kind_ok / kind_n * 100:.1f}% "
          f"(적자·보류 회사에도 간주값을 붙이면 {kind_all}/{kind_n} = {kind_all / kind_n * 100:.1f}%)")


def engine(interest: int, plain: int, special: int, other: int, base: int, gross_up: bool) -> tuple[int, int]:
    """같은 입력을 세액 엔진(core.tax)으로 계산한 신청 전·후 세액."""
    t0 = engine_tax.comprehensive_tax(interest, plain, special + other, base, gross_up=gross_up).tax
    t1 = engine_tax.comprehensive_tax(interest, plain, other, base, gross_up=gross_up).tax + engine_tax.separate_tax(special)
    return t0, t1


def check_tax() -> None:
    cases = [  # (이름, 이자, 가산 비대상 배당, 특례배당, 그 밖의 가산 대상 배당, 금융소득 뺀 과세표준, 배당가산)
        ("김춘배", 6_000_000, 3_000_000, 24_620_000, 0, 80_000_000, True),
        ("국세청 사례 1", 0, 0, 30_000_000, 30_000_000, 70_000_000, False),  # 보도자료는 배당가산을 넣지 않음
        ("국세청 사례 2", 0, 0, 30_000_000, 30_000_000, 10_000_000, False),
    ]
    for name, interest, plain, special, other, base, gu in cases:
        mine = statute_compare(interest, plain, special, other, base, gu)
        eng = engine(interest, plain, special, other, base, gu)
        print(f"세액 {name}: 조문 식 {mine[0]:,} → {mine[1]:,} (차이 {mine[0] - mine[1]:,}) · 엔진 {eng[0]:,} → {eng[1]:,} "
              f"{'같음' if mine == eng else '다름'}")
    for e in (20_000_000, 300_000_000, 5_000_000_000):
        print(f"분리과세 S({e:,}): 조문 식 {separate_tax(e):,} · 엔진 {engine_tax.separate_tax(e):,}")


if __name__ == "__main__":
    with db.connect() as conn:
        check_judgement(conn)
    check_tax()
