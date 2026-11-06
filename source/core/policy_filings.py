"""4층 배당 정책 상세(P1): 자사주 매입·소각, 투자·인수 공시 → raw.dart_policy_filing 행.

OpenDART 주요사항보고서 API(자기주식 취득·처분, 취득 신탁 체결·해지, 타법인 주식 양수, 영업양수, 유형자산 양수)의
값을 받은 글자 그대로 둔다. 숫자·날짜로 읽는 일은 core.v_policy_filing 뷰가 한다. 점수·평가는 붙이지 않는다.
API가 없는 주식소각결정·타법인주식취득결정(거래소 공시)·신규시설투자·유형자산취득결정은 raw.dart_filing_list의
제목·접수번호로만 보완하고 금액은 비워 둔다(원문 링크로 확인). 자회사·종속회사의 주요경영사항 공시는 넣지 않는다.
API 키는 core.share_total.api_key()로 읽고, 캐시 파일 이름·DB·출력에 남기지 않는다.
"""
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.share_total import RETRY_WAITS, ROOT

API = "https://opendart.fss.or.kr/api/{api}.json"
CACHE = ROOT / "data" / "raw" / "dart_api_cache"
FILING_LIST = "filing_list"  # API가 아니라 raw.dart_filing_list 제목으로 보완한 행의 api 값


@dataclass(frozen=True)
class Spec:
    """API 하나의 원문 칸 이름. 앞의 이름이 비어 있으면(‘-’) 뒤의 이름을 쓴다."""
    kind: str
    date: tuple[str, ...]
    amount: str | None = None
    amount_etc: str | None = None
    shares: str | None = None
    shares_etc: str | None = None
    purpose: str | None = None
    target: str | None = None
    period_bgn: str | None = None
    period_end: str | None = None


SPECS = {
    "tsstkAqDecsn": Spec("자기주식 취득", ("aq_dd",), "aqpln_prc_ostk", "aqpln_prc_estk", "aqpln_stk_ostk",
                         "aqpln_stk_estk", "aq_pp", "aq_mth", "aqexpd_bgd", "aqexpd_edd"),
    "tsstkDpDecsn": Spec("자기주식 처분", ("dp_dd",), "dppln_prc_ostk", "dppln_prc_estk", "dppln_stk_ostk",
                         "dppln_stk_estk", "dp_pp", None, "dpprpd_bgd", "dpprpd_edd"),
    "tsstkAqTrctrCnsDecsn": Spec("자기주식 취득 신탁 체결", ("bddd", "ctr_cns_prd"), "ctr_prc", None, None, None,
                                 "ctr_pp", "ctr_cns_int", "ctr_pd_bgd", "ctr_pd_edd"),
    "tsstkAqTrctrCcDecsn": Spec("자기주식 취득 신탁 해지", ("bddd", "cc_prd"), "ctr_prc_bfcc", None, None, None,
                                "cc_pp", "cc_int", "ctr_pd_bfcc_bgd", "ctr_pd_bfcc_edd"),
    "otcprStkInvscrInhDecsn": Spec("타법인 주식 양수", ("bddd",), "inhdtl_inhprc", None, "inhdtl_stkcnt", None,
                                   "inh_pp", "iscmp_cmpnm", None, "inh_prd"),
    "bsnInhDecsn": Spec("영업양수", ("bddd",), "inh_prc", None, None, None, "inh_pp", "inh_bsn", None, "inh_prd"),
    "tgastInhDecsn": Spec("유형자산 양수", ("bddd", "inh_prd_ctr_cnsd"), "inhdtl_inhprc", None, None, None,
                          "inh_pp", "ast_nm", None, "inh_prd_inh_std"),
}

# API가 없는 공시: 제목에 이 말이 있으면 종류를 붙여 보완한다 (앞에서부터 먼저 맞는 것)
TITLE_KINDS = (("주식소각결정", "주식 소각"), ("타법인주식및출자증권취득결정", "타법인 주식 취득"),
               ("신규시설투자", "신규 시설투자"), ("유형자산취득결정", "유형자산 취득"))
NOT_OWN = ("자회사의", "종속회사의")  # 자회사·종속회사의 주요경영사항: 이 회사의 현금 사용이 아님

COLS = ["api", "rcept_no", "corp_code", "corp_name", "kind", "report_nm", "decision_date_raw", "amount_raw",
        "amount_etc_raw", "shares_raw", "shares_etc_raw", "purpose_raw", "target_raw", "period_bgn_raw",
        "period_end_raw", "source", "item"]


def _get(item: dict, name: str | None) -> str | None:
    """원문 칸 값. 없거나 '-'·빈칸이면 None (값은 고치지 않는다)."""
    if not name:
        return None
    v = item.get(name)
    if v is None or str(v).strip() in {"", "-"}:
        return None
    return str(v).strip()


def rows_from_response(api: str, payload: dict, titles: dict[str, str] | None = None) -> list[dict]:
    """API 응답 → 행. titles는 {접수번호: 공시 제목}(raw.dart_filing_list)으로, 있으면 report_nm에 넣는다."""
    spec, titles = SPECS[api], titles or {}
    if payload.get("status") != "000":
        return []
    out = []
    for it in payload.get("list") or []:
        out.append({
            "api": api, "rcept_no": it.get("rcept_no"), "corp_code": it.get("corp_code"), "corp_name": it.get("corp_name"),
            "kind": spec.kind, "report_nm": titles.get(it.get("rcept_no")),
            "decision_date_raw": next((v for v in (_get(it, n) for n in spec.date) if v), None),
            "amount_raw": _get(it, spec.amount), "amount_etc_raw": _get(it, spec.amount_etc),
            "shares_raw": _get(it, spec.shares), "shares_etc_raw": _get(it, spec.shares_etc),
            "purpose_raw": _get(it, spec.purpose), "target_raw": _get(it, spec.target),
            "period_bgn_raw": _get(it, spec.period_bgn), "period_end_raw": _get(it, spec.period_end),
            "source": f"OpenDART {api}", "item": json.dumps(it, ensure_ascii=False),
        })
    return out


def title_kind(report_nm: str | None) -> str | None:
    s = report_nm or ""
    if any(w in s for w in NOT_OWN):
        return None
    return next((kind for word, kind in TITLE_KINDS if word in s), None)


def rows_from_filing_list(filings: list[dict], have: set[str]) -> list[dict]:
    """API로 받지 못한 공시를 제목·접수번호로만 보완한다. have: 이미 API로 받은 접수번호."""
    out = []
    for f in filings:
        kind = title_kind(f.get("report_nm"))
        if kind is None or f["rcept_no"] in have:
            continue
        out.append({c: None for c in COLS} | {
            "api": FILING_LIST, "rcept_no": f["rcept_no"], "corp_code": f["corp_code"], "corp_name": f.get("corp_name"),
            "kind": kind, "report_nm": f.get("report_nm"), "source": "raw.dart_filing_list (제목만, 금액은 원문 확인)"})
    return out


def cache_path(api: str, corp_code: str, bgn_de: str, end_de: str) -> Path:
    return CACHE / api / f"{corp_code}_{bgn_de}_{end_de}.json"


def fetch(key: str, api: str, corp_code: str, bgn_de: str, end_de: str, pause: float = 0.6) -> dict:
    """한 회사·한 API 응답. 정상(000)·데이터 없음(013) 응답만 캐시에 두고 다시 받지 않는다."""
    path = cache_path(api, corp_code, bgn_de, end_de)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    query = urllib.parse.urlencode({"crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de})
    for wait in RETRY_WAITS + (None,):
        try:
            with urllib.request.urlopen(f"{API.format(api=api)}?{query}", timeout=60) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except (OSError, ValueError):
            if wait is None:
                raise RuntimeError(f"응답을 받지 못함: {api} {corp_code}") from None  # 키가 든 주소는 오류에 남기지 않음
            time.sleep(wait)
    if payload.get("status") in {"000", "013"}:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    time.sleep(pause)
    return payload
