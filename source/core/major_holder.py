"""최대주주 현황(OpenDART hyslrSttus): 응답 → raw.dart_major_holder 행, 회사별 보통주 지분율 합계·최대주주 종류.

[팀 해석 · 기획안 추가 분석 '최대주주 지분 비교']
- 지분율 = 최대주주 + 특수관계인의 보통주 기말 지분율 합계. 회사가 적은 '계' 행(보통주)을 먼저 쓰고,
  없으면 보통주 행의 기말 지분율을 더한다. 우선주·종류주식 행은 넣지 않는다(주식 종류 분류는 core.share_total.share_class).
- 최대주주 = 관계 칸이 LARGEST_RELATE에 맞는 보통주 행 가운데 기말 주식수가 가장 많은 행.
  맞는 행이 없으면 보통주 기말 지분율이 가장 큰 행으로 보고 rule에 적는다.
- 개인/법인은 이름·관계 칸 글자 규칙(CORP_WORDS·CORP_RELATE·한글 섞임·한글 2~4자 이름)으로만 나눈다. 맞지 않으면 '판단 불가'.
- 지분에 점수를 붙이지 않는다. 이름은 raw에만 두고 core·화면에는 남기지 않는다.
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from core import share_total as st

API = "https://opendart.fss.or.kr/api/hyslrSttus.json"
CACHE = st.ROOT / "data" / "raw" / "dart_api_cache" / "hyslrSttus"
TOTAL_NAMES = {"계", "합계", "총계", "소계"}
PERSON, CORP, UNKNOWN = "개인", "법인", "판단 불가"

# 관계 칸(공백 제거)이 이 이름이면 최대주주 본인 행
LARGEST_RELATE = {"최대주주", "최대주주본인", "본인", "最大株主", "本人", "최대주주(본인)", "최대주주인본인",
                  "최대주주법인", "최대주주(법인)", "최대주주(개인)", "최대주주개인"}
# 관계 칸에 이 말이 있으면 법인
CORP_RELATE = ("계열회사", "계열사", "관계회사", "법인", "재단")
# 이름(공백 제거, 소문자)에 이 말이 있으면 법인
CORP_WORDS = ("㈜", "(주)", "주식회사", "(유)", "유한회사", "(재)", "재단", "법인", "회사", "홀딩스", "지주", "은행", "보험",
              "증권", "자산운용", "투자", "캐피탈", "펀드", "조합", "공사", "공단", "협회", "연금", "정부", "기획재정부", "장학",
              "학교", "학원", "교회", "전자", "산업", "건설", "화학", "제약", "물산", "상사", "통신", "에너지", "그룹",
              "글로벌", "코리아", "인터내셔널", "테크", "시스템", "네트웍스", "케미칼", "제철", "철강", "중공업", "식품",
              "제당", "제지", "해운", "항공", "자동차", "바이오", "인베스트", "벤처", "생명", "화재", "카드", "신탁",
              "개발", "실업", "기업", "농협", "중앙회", "연맹", "엔터프라이즈", "inc", "ltd", "llc", "corp", "co.", "limited", "holdings",
              "fund", "trust", "investment", "l.p", "pte", "gmbh", "s.a", "b.v", "bank", "capital", "partners")
PERSON_NAME = re.compile(r"^[가-힣]{2,4}$")  # 괄호 안 설명을 뺀 한글 2~4자 (5자 이상은 회사명·외국 이름일 수 있어 판단 불가)
MIXED_NAME = re.compile(r"[가-힣].*[a-z0-9&]|[a-z0-9&].*[가-힣]")  # 한글과 영문·숫자가 섞인 이름(예: 삼성SDI)은 회사명

RULE = ("보통주 '계' 행 우선, 없으면 보통주 행 합 · 최대주주 = 관계 칸(최대주주/본인) 행 · "
        "개인/법인 = 이름·관계 글자 규칙 (source/core/major_holder.py)")


def _squash(s: str | None) -> str:
    return "".join((s or "").split())


def is_total(nm: str | None) -> bool:
    return _squash(nm) in TOTAL_NAMES


def is_largest(relate: str | None) -> bool:
    return _squash(relate) in LARGEST_RELATE


def holder_kind(nm: str | None, relate: str | None = None) -> str:
    name = _squash(nm).lower()
    if not name:
        return UNKNOWN
    if any(w in name for w in CORP_WORDS) or any(w in _squash(relate) for w in CORP_RELATE):
        return CORP
    bare = re.sub(r"\(.*?\)", "", name)
    if MIXED_NAME.search(bare):
        return CORP
    return PERSON if PERSON_NAME.match(bare) else UNKNOWN


def rows_from_response(corp_code: str, bsns_year: int, reprt_code: str, payload: dict) -> list[dict]:
    base = {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code,
            "api_status": payload.get("status"), "api_message": payload.get("message")}
    items = payload.get("list") or []
    empty = dict.fromkeys(["rcept_no", "stlm_dt", "relate", "stock_knd", "share_class", "bsis_shares", "bsis_pct",
                           "trmend_shares", "trmend_pct", "bsis_shares_raw", "bsis_pct_raw", "trmend_shares_raw",
                           "trmend_pct_raw", "rm"])
    if payload.get("status") != "000" or not items:
        return [{**base, **empty, "seq": 1, "nm": st.NO_ROW}]
    out = []
    for i, it in enumerate(items, 1):
        out.append({**base, "seq": i, "rcept_no": it.get("rcept_no"), "stlm_dt": it.get("stlm_dt"),
                    "nm": it.get("nm"), "relate": it.get("relate"), "stock_knd": it.get("stock_knd"),
                    "share_class": st.share_class(it.get("stock_knd")),
                    "bsis_shares": st.number(it.get("bsis_posesn_stock_co")),
                    "bsis_pct": st.number(it.get("bsis_posesn_stock_qota_rt")),
                    "trmend_shares": st.number(it.get("trmend_posesn_stock_co")),
                    "trmend_pct": st.number(it.get("trmend_posesn_stock_qota_rt")),
                    "bsis_shares_raw": it.get("bsis_posesn_stock_co"), "bsis_pct_raw": it.get("bsis_posesn_stock_qota_rt"),
                    "trmend_shares_raw": it.get("trmend_posesn_stock_co"),
                    "trmend_pct_raw": it.get("trmend_posesn_stock_qota_rt"), "rm": it.get("rm")})
    return out


@dataclass(frozen=True)
class Holding:
    pct_common: Decimal | None  # 최대주주+특수관계인 보통주 기말 지분율(%)
    pct_source: str             # '계' 행 / 행 합계 / 자료 없음
    largest_kind: str | None    # 개인 / 법인 / 판단 불가
    largest_rule: str | None    # 관계 칸 / 지분 가장 큰 행
    n_rows: int                 # 보통주 행 수('계' 제외)


def summarize(rows: list[dict]) -> Holding:
    """한 회사·한 보고서의 raw 행 → 지분율 합계와 최대주주 종류."""
    common = [r for r in rows if r.get("share_class") == st.COMMON]
    totals = [r for r in common if is_total(r.get("nm")) and r.get("trmend_pct") is not None]
    people = [r for r in common if not is_total(r.get("nm"))]
    if totals:
        pct, source = totals[0]["trmend_pct"], "'계' 행"
    elif any(r.get("trmend_pct") is not None for r in people):
        pct, source = sum((r["trmend_pct"] for r in people if r.get("trmend_pct") is not None), Decimal(0)), "행 합계"
    else:
        pct, source = None, "자료 없음"
    largest, rule = [r for r in people if is_largest(r.get("relate"))], "관계 칸"
    key = "trmend_shares"
    if not largest:
        largest, rule, key = people, "지분 가장 큰 행", "trmend_pct"
    if not largest:
        return Holding(pct, source, None, None, 0)
    top = max(largest, key=lambda r: r.get(key) if r.get(key) is not None else Decimal(-1))
    return Holding(pct, source, holder_kind(top.get("nm"), top.get("relate")), rule, len(people))
