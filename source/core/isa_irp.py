"""ISA·IRP 구간 안내와 단순 계산 (발표 자료 ISA·IRP 1~3, 부록 A~C).

금액은 원 단위 정수, 세율은 지방소득세를 넣은 천분율(15.4% → 154)로 곱한 뒤 1,000으로 나눠 버린다.
추천이 아니라 계산만 한다: 구간별 혜택과 제약을 함께 돌려주고, 상품 이름·가입 권유는 넣지 않는다.

확인 기록 (2026-11-02)
- ISA: 조세특례제한법 제91조의18 (시행 2026. 9. 18. 현행본) · 전국투자자교육협의회 ISA 안내
- IRP·연금저축: 소득세법 제59조의3 (세액공제 12%·15%, 지방소득세 포함 13.2%·16.5%)
- 일반 계좌 배당 원천징수 14% + 지방소득세 1.4% = 15.4% (소득세법 제129조 제1항 제2호)
- 개정 동향: 2026 세제개편안 '생산적금융 ISA'(연 2,000만·총 2억 원)는 국회 심의 중이라 넣지 않음
"""
from dataclasses import asdict, dataclass

from core import tax_rates

CHECKED = "2026-11-02"
NOTICE = "단순 계산 예시예요. 세율은 지방소득세를 포함했고, 실제 세액은 개인 상황에 따라 달라요. 확정 세액이나 환급액이 아니에요. 특정 상품 가입 권유가 아니에요."

NORMAL_ACCOUNT_PERMIL = 154  # 일반 계좌 배당 원천징수 15.4%
ISA_OVER_PERMIL = 99  # ISA 비과세 한도 초과분 9% 분리과세 + 지방소득세 = 9.9%
ISA_FREE_GENERAL = 2_000_000
ISA_FREE_LOW_INCOME = 4_000_000
PENSION_SAVING_CAP = 6_000_000  # 연금저축만으로 세액공제를 받을 수 있는 한도
PENSION_CREDIT_CAP = 9_000_000  # 연금저축 + IRP 합산 세액공제 한도

SRC_ISA = "조세특례제한법 제91조의18"
SRC_ISA_LIMIT = "조세특례제한법 제129조의2"  # 직전 3개 과세기간 중 금융소득종합과세 대상이면 ISA 특례 제한
SRC_IRP = "소득세법 제59조의3"
SRC_NORMAL = "소득세법 제129조 제1항 제2호 · 지방세법(지방소득세 10%)"

# 연금으로 받을 때 (구간별 세율표에만 씀)
PENSION_TAX_PERMIL = (33, 55)  # 사적연금 연금소득세 3~5%(나이별) + 지방소득세
PENSION_SEPARATE_CAP = 15_000_000  # 사적연금 연 1,500만 원 이하면 저율 분리과세로 끝남
PENSION_OVER_PERMIL = 165  # 넘으면 15% 분리과세(+지방소득세) 또는 종합과세 중 선택
EARLY_WITHDRAW_PERMIL = 165  # 중도 해지·인출 시 기타소득세 15% + 지방소득세
SRC_PENSION = "소득세법 제14조 제3항 제9호 · 제64조의4 · 제129조 제1항 제5호의2"


@dataclass(frozen=True)
class Bracket:
    key: str
    label: str  # 근로자: 총급여 구간, 사업자 등: 종합소득금액 구간
    isa_type: str
    isa_free: int
    irp_permil: int  # 연금계좌 세액공제율(지방소득세 포함)
    kind: str = "wage"  # wage: 근로소득만 있음(총급여), business: 사업소득 등이 있음(종합소득금액)


# 근로소득만 있으면 총급여, 사업소득 등이 있으면 종합소득금액으로 본다 (조특법 제91조의18 제2항 · 소득세법 제59조의3)
# 제2항 단서: 총급여 기준은 근로소득만(또는 분리과세 소득만 더) 있는 사람, 종합소득금액 기준은 총급여 5천만 원 이하인 사람에 한정
BRACKETS = [
    Bracket("low", "5,000만 원 이하", "서민형", ISA_FREE_LOW_INCOME, 165),
    Bracket("mid", "5,000만~5,500만 원", "일반형", ISA_FREE_GENERAL, 165),
    Bracket("high", "5,500만 원 초과", "일반형", ISA_FREE_GENERAL, 132),
    Bracket("biz_low", "3,800만 원 이하", "서민형", ISA_FREE_LOW_INCOME, 165, "business"),
    Bracket("biz_mid", "3,800만~4,500만 원", "일반형", ISA_FREE_GENERAL, 165, "business"),
    Bracket("biz_high", "4,500만 원 초과", "일반형", ISA_FREE_GENERAL, 132, "business"),
]
BY_KEY = {b.key: b for b in BRACKETS}


def wage_bracket(gross: int) -> str:
    """총급여(원천징수영수증 ㉑)로 근로자 구간: 5,000만 원 이하 low, 5,500만 원 이하 mid, 넘으면 high.
    (ISA 서민형: 총급여 5,000만 원 이하 · 연금계좌 16.5%: 총급여 5,500만 원 이하)"""
    return "low" if gross <= 50_000_000 else "mid" if gross <= 55_000_000 else "high"

# 세 제도 비교 (발표 ISA·IRP 1). 대상이 거의 겹치지 않는다.
COMPARE = [
    {"name": "고배당 분리과세", "who": "금융소득 2천만 원을 넘는 사람에게 실익(그 이하는 원래 14%)", "benefit": "배당을 14~30%로 따로 과세",
     "limit": "2028년 사업연도까지 한시"},
    {"name": "ISA", "who": "소액 투자자", "benefit": "순이익 200만 원 비과세(서민형 400만 원), 넘는 부분 9.9%",
     "limit": "3년 의무 · 직전 3년 안에 금융소득종합과세 대상이었으면 가입 불가"},
    {"name": "IRP", "who": "세금을 내는 근로·사업소득자", "benefit": "넣은 돈의 13.2~16.5% 세액공제",
     "limit": "55세 이후 연금으로 받기 · 중도 해지하면 16.5%"},
]

# 상세 숫자 (발표 부록 A, 2026. 11. 현행)
FACTS = [
    {"item": "납입 한도", "isa": "연 2,000만 원 · 총 1억 원 (못 채운 한도는 다음 해로 넘어감)",
     "irp": "연 1,800만 원 (연금저축과 합산)"},
    {"item": "세금 혜택", "isa": "순이익 200만 원 비과세 (서민형 400만 원), 넘는 부분 9.9% 분리과세",
     "irp": "세액공제 한도 900만 원 (연금저축 합산), 공제율 16.5% / 13.2%"},
    {"item": "구간 기준", "isa": "서민형: 총급여 5,000만 원 이하(근로소득만 있는 경우) 또는 종합소득 3,800만 원 이하(총급여 5,000만 원 이하인 경우)",
     "irp": "16.5%: 총급여 5,500만 원 이하 (종합소득 4,500만 원 이하)"},
    {"item": "제약", "isa": "의무 3년 · 직전 3개 과세기간 중 금융소득종합과세 대상이면 가입 불가",
     "irp": "55세 이후 연금 수령 시 연금소득세 3.3~5.5% · 중도 해지 시 16.5%"},
]
FACTS_NOTE = ("ISA 만기 후 60일 안에 연금계좌로 옮기면 옮긴 돈의 10%(최대 300만 원)를 세액공제 한도에 더해요. "
              "2026 세제개편안 '생산적금융 ISA'(연 2,000만·총 2억 원)는 국회 심의 중이에요.")
FACTS_SOURCE = (f"{SRC_ISA} · {SRC_ISA_LIMIT}(ISA 가입 제한) · {SRC_IRP} · 전국투자자교육협의회 ISA 안내 · 조세일보(2026. 8. 3.) 세제개편안 보도 · "
                f"확인일 {CHECKED}")

# 근로소득 원천징수영수증 2쪽 칸 (발표 부록 C, 2026. 3. 20. 개정 서식)
RECEIPT = [
    {"no": "21", "item": "총급여", "use": "ISA 서민형 · IRP 공제율 구간"},
    {"no": "47", "item": "종합소득 과세표준", "use": "분리과세 신청 전·후 세액 비교 (내 배당 점검)"},
    {"no": "71", "item": "결정세액", "use": "세액공제를 얼마까지 받을 수 있는지"},
    {"no": "57~59", "item": "연금계좌 (연금저축 · IRP)", "use": "이미 받은 연금계좌 공제"},
    {"no": "59-1", "item": "ISA 만기 시 연금계좌 납입액", "use": "ISA → 연금계좌 이전 추가 공제"},
]
RECEIPT_SOURCE = "소득세법 시행규칙 별지 제24호서식(1) 근로소득 원천징수영수증 · 2026. 3. 20. 개정 서식"

# 왜 추천하지 않고 계산만 하나 (발표 부록 B)
WHY_NOT_RECOMMEND = [
    {"law": "금융소비자보호법 제2조", "text": "특정인에게 상품 가입을 권하면 판매·중개 행위에 들어갈 수 있어요."},
    {"law": "제17조 적합성 원칙", "text": "권유하려면 고객 정보를 확인하고, 맞지 않는 상품은 권하지 않아야 해요."},
    {"law": "제19조 설명 의무", "text": "권유할 때는 혜택뿐 아니라 제약과 위험도 설명해야 해요."},
    {"law": "금융위원회 2021. 9. 7. 판단", "text": "온라인 플랫폼의 상품 비교·추천은 '중개'에 해당할 수 있어요."},
]


# 중간에 돈이 필요할 때 (팀 자료 2026-11-02). 조문 근거는 칼럼 ISA·IRP 글과 같은 조문을 쓴다.
ISA_EARLY = {
    "problem": "가입한 날부터 3년이 되기 전에 계좌를 깨면, 그동안 받은 비과세 혜택만큼 세금을 다시 걷어요. "
               "넣은 돈보다 많이 꺼내도 깬 것으로 봐요.",
    "ways": [
        {"icon": "💳", "title": "한도 안에서 대출 받기",
         "text": "계좌를 깨는 대신, 계좌에 담긴 돈을 담보로 한도 안에서 대출을 받으면 3년을 채우고 혜택을 지킬 수 있어요. "
                 "대출이 되는지, 한도와 이자는 금융회사마다 달라요."},
        {"icon": "↩️", "title": "넣은 돈 안에서만 꺼내기",
         "text": "넣은 돈(납입원금)보다 적게 꺼내면 계좌를 깬 것으로 보지 않아요."},
        {"icon": "🧾", "title": "어쩔 수 없는 사유는 빼 줘요",
         "text": "사망이나 해외 이주처럼 어쩔 수 없는 사유로 깨면 혜택을 다시 걷지 않아요."},
    ],
    "source": f"{SRC_ISA} 제3항 제4호, 제7항·제8항 · 대출 조건은 금융회사 안내",
}

IRP_WITHDRAW = {
    "reasons": [
        {"icon": "🏠", "title": "무주택자 주택 구입",
         "text": "집이 없는 가입자가 본인 이름으로 집을 살 때, 매매계약을 맺은 날부터 소유권 이전 등기 후 1개월 안에 신청할 수 있어요."},
        {"icon": "🏠", "title": "무주택자 전세금·임차보증금",
         "text": "전월세 계약을 맺은 날부터 보증금 잔금을 낸 날 뒤 1개월 안에 신청할 수 있어요. "
                 "회사 퇴직연금은 같은 회사에 다니는 동안 1번만 되지만, 개인형 IRP는 횟수 제한이 없어요."},
        {"icon": "🏥", "title": "본인·가족의 6개월 이상 요양",
         "text": "질병이나 부상으로 본인, 배우자, 부양가족이 6개월 넘게 요양해야 할 때, 요양 사유를 확인할 수 있는 날부터 "
                 "요양이 끝난 날 뒤 1개월 안에 신청할 수 있어요. 개인형 IRP는 의료비 조건이 없지만, DC형과 기업형 IRP는 "
                 "1년 임금 총액의 12.5%를 넘게 의료비를 낼 때만 돼요."},
        {"icon": "💸", "title": "개인회생·파산선고",
         "text": "신청한 날 기준 지난 5년 안에 개인회생 절차 개시 결정이나 파산선고를 받았고, 그 효력이 남아 있을 때 신청할 수 있어요."},
        {"icon": "🌊", "title": "재난 피해",
         "text": "천재지변으로 집이 부서지거나 쓸려 갔을 때, 재난으로 가족이 실종됐을 때, 본인이 15일 넘게 입원 치료를 받아야 할 때 "
                 "신청할 수 있어요. 피해를 입은 날부터 3개월 안에 신청해야 해요."},
    ],
    "steps": [
        {"title": "증빙 서류 내기", "text": "중도인출 사유를 보여 주는 서류를 회사에 내요."},
        {"title": "신청서 보내기", "text": "신청서와 증빙 서류를 퇴직연금을 맡긴 금융회사에 보내요."},
        {"title": "받기", "text": "금융회사가 굴리던 상품을 팔아 돈을 보내 줘요."},
    ],
    "tax": [
        {"case": "부득이한 사유", "examples": "6개월 이상 요양 · 개인회생 · 파산선고 · 천재지변",
         "tax": "세액공제 받은 납입금과 운용수익은 연금소득세 3.3~5.5%, 퇴직급여는 퇴직소득세의 70%"},
        {"case": "그 밖의 사유", "examples": "무주택자 주택 구입 · 전세보증금 · 부득이한 사유에 들지 않는 사회재난 피해(특별재난지역 사회재난으로 15일 이상 입원하면 부득이한 사유)",
         "tax": "세액공제 받은 납입금과 운용수익은 기타소득세 16.5%, 퇴직급여는 퇴직소득세 그대로"},
    ],
    "note": "신청 조건과 서류는 가입한 금융회사에서 마지막으로 확인해 주세요.",
    "source": "근로자퇴직급여 보장법 시행령 제14조·제18조(중도인출 사유) · 소득세법 시행령 제20조의2(부득이한 사유) · "
              "소득세법 제21조 제1항 제21호(기타소득)",
}


def permil(amount: int, rate: int) -> int:
    return amount * rate // 1000


def isa_compare(profit: int) -> dict:
    """같은 이자·배당 순이익을 일반 계좌, ISA 일반형, ISA 서민형에서 받을 때의 세금."""
    def isa(free: int) -> int:
        return permil(max(0, profit - free), ISA_OVER_PERMIL)
    return {"profit": profit, "normal": permil(profit, NORMAL_ACCOUNT_PERMIL),
            "general": isa(ISA_FREE_GENERAL), "low_income": isa(ISA_FREE_LOW_INCOME),
            "source": f"{SRC_ISA} · {SRC_NORMAL}"}


def irp_credit(irp: int, pension_saving: int, rate: int, tax_due: int | None = None) -> dict:
    """연금계좌 세액공제. 연금저축은 600만 원까지만 세고, IRP와 합쳐 900만 원까지 공제율을 곱한다.

    tax_due(원천징수영수증 71번 결정세액)를 알면 그보다 많이 돌려받을 수 없다.
    """
    counted = min(min(pension_saving, PENSION_SAVING_CAP) + irp, PENSION_CREDIT_CAP)
    credit = permil(counted, rate)
    refund = credit if tax_due is None else min(credit, tax_due)
    return {"irp": irp, "pension_saving": pension_saving, "counted": counted,
            "over": irp + pension_saving - counted, "rate_permil": rate, "credit": credit,
            "tax_due": tax_due, "refund": refund, "source": SRC_IRP}


def guide(bracket: str | None, profit: int, irp: int, pension_saving: int = 0,
          tax_due: int | None = None) -> dict:
    """ISA·IRP 화면 한 장. bracket이 None이면(총급여를 모름) 두 공제율을 모두 계산한다."""
    chosen = BY_KEY.get(bracket) if bracket else None
    rates = [chosen.irp_permil] if chosen else sorted({b.irp_permil for b in BRACKETS}, reverse=True)
    return {
        "brackets": [asdict(b) for b in BRACKETS],
        "chosen": asdict(chosen) if chosen else None,
        "isa": isa_compare(profit),
        "irp": [irp_credit(irp, pension_saving, r, tax_due) for r in rates],
        "compare": COMPARE, "facts": FACTS, "facts_note": FACTS_NOTE, "facts_source": FACTS_SOURCE,
        "receipt": RECEIPT, "receipt_source": RECEIPT_SOURCE,
        "isa_early": ISA_EARLY, "irp_withdraw": IRP_WITHDRAW,
        "why_not": WHY_NOT_RECOMMEND, "notice": NOTICE, "checked": CHECKED,
        "rate_table": rate_table(),
    }


def with_local(pct: int) -> int:
    """국세 세율(%)에 지방소득세 10%를 더한 천분율. 6% → 66(6.6%)."""
    return pct * 11


def rate_table() -> dict:
    """금액 구간별 세율 한눈에 보기. 종합소득세·분리과세 구간 경계를 합쳐 행을 만들고, 행마다 그 구간 한계세율을 넣는다.

    종합소득세는 과세표준, 고배당 분리과세는 고배당기업 배당액 기준이라 같은 금액이라도 뜻이 다르다(화면에 적음).
    """
    def rate(brackets: list[tax_rates.Bracket], lower: int) -> int:
        return max((b for b in brackets if b.lower_bound <= lower), key=lambda b: b.lower_bound).rate_pct

    bounds = sorted({b.lower_bound for b in tax_rates.BASIC} | {b.lower_bound for b in tax_rates.SEPARATE})
    rows = [{"lower": lo, "upper": hi,
             "basic_permil": with_local(rate(tax_rates.BASIC, lo)),
             "separate_permil": with_local(rate(tax_rates.SEPARATE, lo))}
            for lo, hi in zip(bounds, bounds[1:] + [None])]
    return {
        "rows": rows,
        "isa": {"over_permil": ISA_OVER_PERMIL, "free_general": ISA_FREE_GENERAL, "free_low_income": ISA_FREE_LOW_INCOME},
        "irp": {"pension_permil": list(PENSION_TAX_PERMIL), "separate_cap": PENSION_SEPARATE_CAP,
                "over_permil": PENSION_OVER_PERMIL, "early_permil": EARLY_WITHDRAW_PERMIL},
        "normal_permil": NORMAL_ACCOUNT_PERMIL,
        "threshold": tax_rates.FINANCIAL_THRESHOLD,
        "source": f"{tax_rates.BASIC[0].source} · {tax_rates.SEPARATE[0].source} · {SRC_ISA} · {SRC_PENSION} · 지방세법(지방소득세 10%)",
    }


# --- 소득 종류별 판정 (근로자는 총급여, 사업자는 종합소득금액) ---------------------------------
# ISA 서민형은 가입 직전 연도 소득, IRP 공제율은 납입 연도 소득으로 본다.
ISA_LOW_WAGE = 50_000_000  # 총급여 5,000만 원 이하 → ISA 서민형
ISA_LOW_COMPREHENSIVE = 38_000_000  # 종합소득금액 3,800만 원 이하 → ISA 서민형
IRP_HIGH_WAGE = 55_000_000  # 총급여 5,500만 원 이하 → 16.5%
IRP_HIGH_COMPREHENSIVE = 45_000_000  # 종합소득금액 4,500만 원 이하 → 16.5%


def isa_type(kind: str, last_year_income: int) -> str:
    """'wage'(총급여) 또는 'business'(종합소득금액) 기준 ISA 가입 유형."""
    cap = ISA_LOW_WAGE if kind == "wage" else ISA_LOW_COMPREHENSIVE
    return "서민형" if last_year_income <= cap else "일반형"


def irp_permil(kind: str, income: int) -> int:
    cap = IRP_HIGH_WAGE if kind == "wage" else IRP_HIGH_COMPREHENSIVE
    return 165 if income <= cap else 132


def isa_blocked_years(join_year: int, taxed_years: list[int]) -> list[int]:
    """가입 직전 3개 과세기간 중 금융소득종합과세 대상이었던 해. 하나라도 있으면 가입 제한."""
    return sorted(y for y in taxed_years if join_year - 3 <= y <= join_year - 1)


def profile(kind: str, join_year: int, last_year_income: int, this_year_income: int, taxed_years: list[int],
            isa_profit: int, irp: int, pension_saving: int = 0, what_if: list[int] | None = None) -> dict:
    """한 사람의 ISA·IRP 판정과 계산 예시. 추천이 아니라 조건과 계산만 돌려준다."""
    blocked = isa_blocked_years(join_year, taxed_years)
    typ = isa_type(kind, last_year_income)
    rate = irp_permil(kind, this_year_income)
    compare = isa_compare(isa_profit)
    return {
        "kind": kind, "basis": "총급여" if kind == "wage" else "종합소득금액",
        "isa": {"blocked_years": blocked, "can_join": not blocked, "type": typ,
                "free": ISA_FREE_LOW_INCOME if typ == "서민형" else ISA_FREE_GENERAL,
                "income_year": join_year - 1, "income": last_year_income,
                "normal_tax": compare["normal"], "isa_tax": compare["low_income" if typ == "서민형" else "general"],
                "profit": isa_profit, "source": f"{SRC_ISA} · {SRC_ISA_LIMIT}"},
        "irp": {**irp_credit(irp, pension_saving, rate), "income_year": join_year, "income": this_year_income},
        "what_if": [{"income": w, "rate_permil": irp_permil(kind, w), "credit": irp_credit(irp, pension_saving, irp_permil(kind, w))["credit"]}
                    for w in (what_if or [])],
        "notice": NOTICE, "checked": CHECKED,
    }
