"""OpenDART 수집과 결측 보완.

화면(DART 뷰어)에는 보이는데 API가 빈 값을 주는 흔한 원인과 이 모듈의 대응:
- status 013(데이터 없음)·020(한도 초과)을 빈 표로 처리 → 상태를 나눠 기록, 020은 LimitReached로 멈춤
- 연결재무제표(CFS)가 없는 회사 → 별도(OFS)로 다시 요청하고 어느 쪽인지 남김(계정마다 허용한 쪽만)
- 계정 이름이 회사마다 다름('당기순이익(손실)', '분기순이익') → account_id 먼저, 다음에 정리한 이름으로 찾음
- 그해 보고서에 값이 없음 → 다음 해 사업보고서의 전기 값으로 찾고 '재작성됐을 수 있음'을 남김
- '-'·'△'·쉼표 → 숫자 변환에서 결측과 음수를 구분
- 정정공시 → 공시 검색은 최종본만(last_reprt_at=Y)
- API 범위 밖(배당 결정 공시 숫자 등) → 공시 원문(document.xml) 표에서 찾고 '원문에서 찾음'으로 표시
- 감사보고서 기준 재무 값 → 감사보고서·연결감사보고서 원문의 재무제표 표를 읽음(audit_account)

끝까지 못 찾으면 0으로 채우지 않고 '확인 불가'와 DART 뷰어 링크를 남긴다.
"""
import html
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from core.sources.base import (
    API_ERROR,
    FROM_ORIGINAL,
    NO_DATA,
    OK,
    UNVERIFIED,
    Client,
    Fetched,
    LimitReached,
    Source,
    public_params,
    secret,
    squash,
    strip_brackets,
    to_number,
    unit_from_label,
)

BASE = "https://opendart.fss.or.kr/api"
KEY_NAME = "DART_API_KEY"

REPORT_CODES = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}
FS_NAMES = {"CFS": "연결", "OFS": "별도"}

STATUS_MESSAGES = {
    "000": "정상",
    "010": "등록되지 않은 키",
    "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP",
    "013": "조회된 데이터 없음",
    "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(하루 20,000건)",
    "021": "조회 가능한 회사 개수 초과(최대 100건)",
    "100": "필드의 부적절한 값",
    "101": "부적절한 접근",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
    "901": "사용자 계정의 개인정보 보유기간 만료",
}
KEY_ERRORS = {"010", "011", "012", "901"}  # 키를 고치기 전에는 어떤 요청도 성공하지 않음


class DartKeyError(Exception):
    """키·IP 문제. 비밀키를 다시 입력해야 한다(base.forget_secret 후 다시 실행)."""


def viewer_url(rcept_no: str) -> str:
    """사람이 원문을 확인할 DART 뷰어 주소."""
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


@dataclass(frozen=True)
class Account:
    """찾을 계정.

    ids: 표준 계정코드(account_id). 감사보고서 원문에는 없어 이름으로만 찾는다.
    names: 계정 이름 후보. 비교할 때 양쪽 모두 strip_brackets로 공백·괄호 덧말을 지운다.
    statements: sj_div (BS 재무상태표, IS 손익계산서, CIS 포괄손익계산서, CF 현금흐름표)
    fs_only: 이 재무제표에서만 받는다. 다른 쪽을 요청하면 대체하지 않고 '확인 불가'
    absolute: 음수로 오는 값을 절댓값으로 저장한다
    """

    ids: tuple[str, ...]
    names: tuple[str, ...]
    statements: tuple[str, ...]
    fs_only: tuple[str, ...] = ("CFS", "OFS")
    absolute: bool = False


# 재무회계 팀원 검토(2026-10-22) 반영. 자동 대체는 하지 않는다.
ACCOUNTS = {
    # 배당성향 분모(NI). 연결 작성 회사는 CFS에서만 가져옴
    # "지배기업소유주지분" 단독 이름은 CIS 총포괄이익 귀속 행과 겹쳐서 제외
    "지배주주순이익": Account(
        ids=("ifrs-full_ProfitLossAttributableToOwnersOfParent",),
        names=("지배기업소유주지분순이익", "지배기업소유주지분당기순이익",
               "지배기업의소유주에게귀속되는당기순이익", "지배기업소유주에게귀속되는당기순이익",
               "지배기업의소유주에게귀속되는당기순이익(손실)", "지배기업소유주에게귀속되는당기순이익(손실)",
               "지배주주지분순이익", "지배주주순이익"),
        statements=("IS", "CIS"),
        fs_only=("CFS",),
    ),
    # CFS: 비지배지분 포함 연결 전체 순이익 / OFS: 별도 순이익(연결 미작성 회사의 NI)
    # 배당 표(DIVIDEND_ITEMS)의 "당기순이익"과는 다른 값
    "당기순이익_전체": Account(
        ids=("ifrs-full_ProfitLoss",),
        names=("당기순이익", "당기순이익(손실)", "당기순손익", "당기순손실", "연결당기순이익",
               "분기순이익", "반기순이익"),
        statements=("IS", "CIS"),
    ),
    "부채총계": Account(
        ids=("ifrs-full_Liabilities",),
        names=("부채총계",),
        statements=("BS",),
    ),
    # 비지배지분 포함. 2배 기준의 '자본총액'이 이 값인지 지배주주자본인지는 시행규칙 원문 확인 필요
    "자본총계": Account(
        ids=("ifrs-full_Equity",),
        names=("자본총계",),
        statements=("BS",),
    ),
    # CFS에만 있음. OFS에서 없을 때 자본총계로 대체하지 않음
    "지배주주자본": Account(
        ids=("ifrs-full_EquityAttributableToOwnersOfParent",),
        names=("지배기업소유주지분", "지배기업의소유주지분", "지배기업의소유주에게귀속되는자본"),
        statements=("BS",),
        fs_only=("CFS",),
    ),
    # 지급 기준(그해 실제 나간 돈). D(이익배당금액, 결의 기준)와 다름. 자동 대체 금지
    # OFS 현금흐름표에서만 가져옴. 음수로 오므로 저장할 때 절댓값으로 맞춤
    "배당금지급_지급기준": Account(
        ids=("ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
             "ifrs-full_DividendsPaidClassifiedAsOperatingActivities",
             "ifrs-full_DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities",
             "ifrs-full_DividendsPaid"),
        names=("배당금의지급", "배당금지급", "현금배당금의지급", "배당금지급액"),
        statements=("CF",),
        fs_only=("OFS",),
        absolute=True,
    ),
}

# 배당에 관한 사항(alotMatter)의 se 항목. strip_brackets로 정리한 이름과 같은지 본다.
DIVIDEND_ITEMS = ("현금배당금총액", "주당현금배당금", "현금배당성향", "현금배당수익률", "당기순이익",
                  "주당순이익", "주식배당금총액", "주당주식배당", "주당액면가액")

PERIODS = {"thstrm": "당기", "frmtrm": "전기", "lwfr": "전전기"}
CORP_CLS = {"Y": "유가", "K": "코스닥", "N": "코넥스", "E": "기타"}  # 기업개황 법인구분
AUDIT_REPORTS = {"CFS": ("F002", "연결감사보고서"), "OFS": ("F001", "감사보고서")}  # (공시 상세유형, 보고서 이름)
NO_ROW = "행 없음"  # pick_dividend 안에서만 쓰는 상태: 다음 보고서로 넘어가 찾는다


def _fiscal_year(value) -> str:
    return str(int(value))


class Dart:
    """OpenDART 요청 묶음. key를 주지 않으면 비밀 입력(base.secret)으로 받는다."""

    def __init__(self, key: str | None = None, client: Client | None = None):
        self._key = key
        self.client = client or Client()
        self._audit_cache: dict = {}  # (corp_code, 사업연도, fs) → 읽은 감사보고서 재무제표

    @property
    def key(self) -> str:
        if not self._key:
            self._key = secret(KEY_NAME, "OpenDART 인증키 입력(화면에 보이지 않음): ")
        return self._key

    # --- 요청 공통 ---

    def call(self, endpoint: str, params: dict) -> tuple[str, str, dict]:
        """JSON API 한 번. (status, message, 본문)을 돌려준다. 키 문제·한도 초과는 예외로 멈춘다."""
        url = f"{BASE}/{endpoint}"
        full = {"crtfc_key": self.key, **params}
        raw = self.client.get(url, full, keep=lambda b: _json_status(b) == "000",
                              remember=lambda b: _json_status(b) in ("000", "013"))
        body = json.loads(raw)
        status = str(body.get("status", ""))
        message = body.get("message") or STATUS_MESSAGES.get(status, "")
        if status in KEY_ERRORS:
            raise DartKeyError(f"{status} {STATUS_MESSAGES.get(status, message)}")
        if status == "020":
            raise LimitReached(f"OpenDART {STATUS_MESSAGES['020']}")
        return status, message, body

    def _rows(self, endpoint: str, params: dict) -> tuple[pd.DataFrame | None, str, str]:
        """list 응답을 표로. 실패하면 (None, 상태, 사유)."""
        status, message, body = self.call(endpoint, params)
        label = f"{endpoint} {' '.join(str(v) for v in params.values())}"
        if status == "000":
            return pd.DataFrame(body.get("list", [])), OK, f"{label}: 정상"
        if status == "013":
            return None, NO_DATA, f"{label}: 013 데이터 없음"
        return None, API_ERROR, f"{label}: {status} {message}"

    # --- 고유번호 ---

    def corp_codes(self) -> pd.DataFrame:
        """전체 회사 고유번호표(corp_code, corp_name, stock_code, modify_date). 상장사만 stock_code가 있다."""
        url = f"{BASE}/corpCode.xml"
        raw = self.client.get(url, {"crtfc_key": self.key}, keep=lambda b: b[:2] == b"PK")
        if raw[:2] != b"PK":
            status = _xml_status(raw)
            if status in KEY_ERRORS:
                raise DartKeyError(f"{status} {STATUS_MESSAGES.get(status, '')}")
            if status == "020":
                raise LimitReached(f"OpenDART {STATUS_MESSAGES['020']}")
            raise ValueError(f"고유번호 파일을 받지 못함: {status} {STATUS_MESSAGES.get(status, '')}")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            root = ET.fromstring(z.read(z.namelist()[0]))
        rows = [{c.tag: (c.text or "").strip() for c in item} for item in root.iter("list")]
        return pd.DataFrame(rows, columns=["corp_code", "corp_name", "stock_code", "modify_date"])

    # --- 재무제표 ---

    def statement(self, corp_code: str, year, reprt_code: str = "11011",
                  fs_divs: tuple[str, ...] = ("CFS", "OFS")) -> Fetched:
        """전체 재무제표(fnlttSinglAcntAll). 연결이 없으면 별도로 다시 요청한다. value는 표, fs_div 열 포함."""
        attempts: list[str] = []
        worst = NO_DATA
        for fs in fs_divs:
            params = {"corp_code": corp_code, "bsns_year": _fiscal_year(year), "reprt_code": reprt_code, "fs_div": fs}
            df, status, note = self._rows("fnlttSinglAcntAll.json", params)
            attempts.append(f"{FS_NAMES[fs]} {note.split(': ', 1)[1]}")
            if df is not None and not df.empty:
                df["fs_div"] = fs
                rcept = str(df["rcept_no"].iloc[0]) if "rcept_no" in df else None
                return Fetched(df, OK, Source("fnlttSinglAcntAll", public_params(params), rcept), attempts)
            if status == API_ERROR:
                worst = API_ERROR
        return Fetched(None, worst, None, attempts)

    def account(self, corp_code: str, year, item: str, reprt_code: str = "11011",
                field: str = "thstrm_amount", fs_divs: tuple[str, ...] = ("CFS", "OFS")) -> Fetched:
        """계정 값 하나(원 단위). 찾는 순서:

        1) 그해 전체 재무제표(fs_divs 순서, 기본 연결→별도)에서 account_id, 다음에 이름으로
        2) 그해 주요계정(fnlttSinglAcnt)에서 이름으로
        3) 다음 해 사업보고서의 전기 값(frmtrm_amount). 재작성됐을 수 있어 메모를 남긴다
        계정마다 허용한 재무제표(Account.fs_only)만 본다. 다른 계정 값으로 대체하지 않는다.
        분기 손익의 누적 값이 필요하면 field='thstrm_add_amount'.
        fs_divs=("CFS",)나 ("OFS",)로 한쪽만 주면 다른 쪽으로 넘어가지 않는다(2~4단계도 같은 쪽만 본다).
        """
        spec = ACCOUNTS[item]
        allowed = tuple(fs for fs in fs_divs if fs in spec.fs_only)
        if not allowed:
            wanted = "·".join(FS_NAMES[f] for f in fs_divs)
            only = "·".join(FS_NAMES[f] for f in spec.fs_only)
            return Fetched(None, UNVERIFIED, Source("fnlttSinglAcntAll", note=f"{item}은 {only}재무제표에서만 받음({wanted} 요청)"),
                           [f"{item}: {wanted}재무제표 대상 아님"])
        fs_divs = allowed
        attempts: list[str] = []

        st = self.statement(corp_code, year, reprt_code, fs_divs)
        attempts += st.attempts
        if st.found:
            fs = st.value["fs_div"].iloc[0]
            hit = find_account(st.value, spec, field)
            if hit:
                value, how = hit
                attempts.append(f"{item}: {how}")
                src = Source("fnlttSinglAcntAll", st.source.params, st.source.rcept_no, note=f"{FS_NAMES[fs]} · {how}")
                return _number_result(value, src, attempts, spec.absolute)
            attempts.append(f"{item}: 전체 재무제표에 계정 없음")

        main = self._main_accounts(corp_code, year, reprt_code, spec, field, attempts, fs_divs)
        if main:
            return main

        if reprt_code == "11011" and field == "thstrm_amount":
            nxt = self.statement(corp_code, int(year) + 1, "11011", fs_divs)
            attempts += [f"다음 해 {a}" for a in nxt.attempts]
            if nxt.found:
                hit = find_account(nxt.value, spec, "frmtrm_amount")
                if hit:
                    value, how = hit
                    attempts.append(f"{item}: 다음 해 전기 값 {how}")
                    src = Source("fnlttSinglAcntAll", nxt.source.params, nxt.source.rcept_no,
                                 note=f"{int(year) + 1} 사업보고서의 전기 값(재작성됐을 수 있음)")
                    return _number_result(value, src, attempts, spec.absolute)

        rcept = st.source.rcept_no if st.source else None
        status = API_ERROR if st.status == API_ERROR else UNVERIFIED
        note = f"원문 확인: {viewer_url(rcept)}" if rcept else "사업보고서 원문 확인"
        return Fetched(None, status, Source("fnlttSinglAcntAll", {"corp_code": corp_code, "bsns_year": str(year)}, rcept, note=note), attempts)

    def _main_accounts(self, corp_code, year, reprt_code, spec: Account, field, attempts,
                       fs_divs: tuple[str, ...] = ("CFS", "OFS")) -> Fetched | None:
        params = {"corp_code": corp_code, "bsns_year": _fiscal_year(year), "reprt_code": reprt_code}
        df, _, note = self._rows("fnlttSinglAcnt.json", params)
        attempts.append(f"주요계정 {note.split(': ', 1)[1]}")
        if df is None or df.empty:
            return None
        if "fs_div" not in df:
            attempts.append("주요계정: 연결·별도 구분 열 없음")
            return None
        parts = [(FS_NAMES[fs], df[df["fs_div"] == fs]) for fs in fs_divs]
        for fs_name, part in parts:
            hit = find_account(part, spec, field, use_ids=False)
            if hit:
                value, how = hit
                attempts.append(f"주요계정 {fs_name} {how}")
                rcept = str(part["rcept_no"].iloc[0]) if "rcept_no" in part else None
                return _number_result(value, Source("fnlttSinglAcnt", params, rcept, note=f"{fs_name} · {how}"), attempts,
                                      spec.absolute)
        return None

    # --- 배당에 관한 사항 ---

    def dividends(self, corp_code: str, year, reprt_code: str = "11011") -> Fetched:
        """배당에 관한 사항(alotMatter) 표 그대로."""
        params = {"corp_code": corp_code, "bsns_year": _fiscal_year(year), "reprt_code": reprt_code}
        df, status, note = self._rows("alotMatter.json", params)
        rcept = str(df["rcept_no"].iloc[0]) if df is not None and "rcept_no" in df and not df.empty else None
        return Fetched(df, status, Source("alotMatter", params, rcept), [note])

    def dividend_item(self, corp_code: str, year, item: str, stock_knd: str = "보통주",
                      basis: str = "연결", strict_basis: bool = True) -> Fetched:
        """배당 항목 값 하나. 단위는 항목 이름에서 읽는다(현금배당금총액은 백만 원).

        찾는 순서: 그해 사업보고서 당기 → 다음 해 전기 → 다다음 해 전전기.
        행은 있는데 값이 '-'이면 '데이터 없음'(무배당일 수 있어 배당 결정 공시로 확인), 행이 없으면 '확인 불가'.
        """
        if item not in DIVIDEND_ITEMS:
            raise ValueError(f"알 수 없는 배당 항목: {item}")
        attempts: list[str] = []
        saw_dash = False
        last_source = None
        for offset, period in ((0, "thstrm"), (1, "frmtrm"), (2, "lwfr")):
            got = self.dividends(corp_code, int(year) + offset)
            attempts += got.attempts
            if got.status == API_ERROR:
                return Fetched(None, API_ERROR, got.source, attempts)
            if not got.found or got.value.empty:
                continue
            last_source = got.source
            pick = pick_dividend(got.value, item, period, stock_knd, basis, strict_basis)
            attempts.append(f"{int(year) + offset} 보고서 {PERIODS[period]}: {pick['how']}")
            if pick["status"] == OK:
                note = pick["note"]
                if offset:
                    note = f"{int(year) + offset} 사업보고서의 {PERIODS[period]} 값" + (f" · {note}" if note else "")
                src = Source("alotMatter", got.source.params, got.source.rcept_no, note=note)
                return Fetched(pick["value"], OK, src, attempts, unit=pick["unit"])
            if pick["status"] == UNVERIFIED:
                return Fetched(None, UNVERIFIED, Source("alotMatter", got.source.params, got.source.rcept_no,
                                                        note=pick["note"]), attempts)
            saw_dash = saw_dash or pick["status"] == NO_DATA
        if saw_dash:
            note = "보고서에 '-'로 표시: 무배당일 수 있음. 배당 결정 공시로 확인"
            return Fetched(None, NO_DATA, _with_note(last_source, note), attempts)
        return Fetched(None, UNVERIFIED, _with_note(last_source, "배당 항목 행을 찾지 못함: 사업보고서 원문 확인"), attempts)

    # --- 공시 검색·원문 ---

    def disclosures(self, bgn_de, end_de, corp_code: str | None = None, keywords: tuple[str, ...] = (),
                    pblntf_ty: str | None = None, final_only: bool = True,
                    pblntf_detail_ty: str | None = None) -> Fetched:
        """공시 목록(list.json). 모든 쪽을 넘겨 받고 report_nm에 keywords가 하나라도 들어간 것만 남긴다.

        final_only=True면 정정 전 공시를 빼고 최종본만 받는다(last_reprt_at=Y).
        회사를 정하지 않으면 OpenDART가 3개월까지만 받아 주므로 기간을 3개월씩 나눠 요청한다.
        pblntf_ty: A 정기공시, B 주요사항보고, F 외부감사관련, I 거래소공시(배당 결정·기업가치 제고 계획) 등.
        pblntf_detail_ty: F001 감사보고서, F002 연결감사보고서 등.
        """
        frames, attempts = [], []
        chunks = [(_ymd(bgn_de), _ymd(end_de))] if corp_code else _quarters(_ymd(bgn_de), _ymd(end_de))
        for start, end in chunks:
            page = 1
            while True:
                params = {"bgn_de": start, "end_de": end, "page_no": page, "page_count": 100,
                          "last_reprt_at": "Y" if final_only else "N"}
                if corp_code:
                    params["corp_code"] = corp_code
                if pblntf_ty:
                    params["pblntf_ty"] = pblntf_ty
                if pblntf_detail_ty:
                    params["pblntf_detail_ty"] = pblntf_detail_ty
                status, message, body = self.call("list.json", params)
                if status == "013":
                    attempts.append(f"{start}~{end}: 013 데이터 없음")
                    break
                if status != "000":
                    attempts.append(f"{start}~{end} {page}쪽: {status} {message}")
                    return Fetched(None, API_ERROR, Source("list", public_params(params)), attempts)
                frames.append(pd.DataFrame(body.get("list", [])))
                total = int(body.get("total_page", 1) or 1)
                if page >= total:
                    attempts.append(f"{start}~{end}: {body.get('total_count', '')}건")
                    break
                page += 1
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["rcept_no", "report_nm"])
        if keywords and not df.empty:
            keys = [squash(k) for k in keywords]
            df = df[df["report_nm"].map(lambda n: any(k in squash(n) for k in keys))]
        df = df.reset_index(drop=True)
        if not df.empty:
            df["정정"] = df["report_nm"].map(lambda n: "정정" in str(n))
            df["원문"] = df["rcept_no"].map(viewer_url)
        status = OK if not df.empty else NO_DATA
        return Fetched(df, status, Source("list", {"bgn_de": bgn_de, "end_de": end_de, "corp_code": corp_code}), attempts)

    def document(self, rcept_no: str) -> Fetched:
        """공시 원문(document.xml). value는 {파일 이름: 본문}."""
        params = {"rcept_no": rcept_no}
        raw = self.client.get(f"{BASE}/document.xml", {"crtfc_key": self.key, **params},
                              keep=lambda b: b[:2] == b"PK")
        src = Source("document", params, rcept_no, viewer_url(rcept_no))
        if raw[:2] != b"PK":
            status = _xml_status(raw) or _json_status(raw)
            if status in KEY_ERRORS:
                raise DartKeyError(f"{status} {STATUS_MESSAGES.get(status, '')}")
            if status == "020":
                raise LimitReached(f"OpenDART {STATUS_MESSAGES['020']}")
            kind = NO_DATA if status in ("013", "014") else API_ERROR
            note = f"{status} {STATUS_MESSAGES.get(status, '')}: 뷰어에서 직접 확인"
            return Fetched(None, kind, _with_note(src, note), [f"document {rcept_no}: {note}"])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            files = {name: _decode(z.read(name)) for name in z.namelist()}
        return Fetched(files, OK, src, [f"document {rcept_no}: 파일 {len(files)}개"])

    def from_original(self, rcept_no: str, label: str, as_text: bool = False) -> Fetched:
        """공시 원문 표에서 label 행의 값을 찾는다. 찾으면 '원문에서 찾음'(사람이 한 번 더 확인)."""
        doc = self.document(rcept_no)
        if not doc.found:
            return doc
        found = find_in_tables(doc.value, label, as_text=as_text)
        found.source = Source("document", {"rcept_no": rcept_no}, rcept_no, viewer_url(rcept_no), found.source.note)
        found.attempts = doc.attempts + found.attempts
        return found

    def dividend_decision(self, rcept_no: str) -> dict[str, Fetched]:
        """배당 결정 공시(현금ㆍ현물배당결정) 원문의 주요 숫자. 금액은 원 단위."""
        doc = self.document(rcept_no)
        labels = {"1주당배당금": ("1주당배당금", False), "배당금총액": ("배당금총액", False),
                  "시가배당율": ("시가배당율", False), "배당기준일": ("배당기준일", True)}
        out = {}
        for name, (label, as_text) in labels.items():
            if not doc.found:
                out[name] = doc
                continue
            f = find_in_tables(doc.value, label, as_text=as_text)
            f.source = Source("document", {"rcept_no": rcept_no}, rcept_no, viewer_url(rcept_no), f.source.note)
            out[name] = f
        return out

    # --- 감사보고서 원문 재무제표 ---

    def audit_report(self, corp_code: str, year, fs: str = "CFS") -> Fetched:
        """그 사업연도의 감사보고서(OFS) 또는 연결감사보고서(CFS) 공시 한 건. value는 list.json 행."""
        detail, name = AUDIT_REPORTS[fs]
        y = int(year)
        found = self.disclosures(f"{y}0101", f"{y + 1}1231", corp_code=corp_code,
                                 pblntf_ty="F", pblntf_detail_ty=detail)
        attempts = [f"{name} 검색 {a}" for a in found.attempts]
        if found.status == API_ERROR:
            return Fetched(None, API_ERROR, found.source, attempts)
        df = found.value if found.found else pd.DataFrame(columns=["report_nm", "rcept_no"])
        if not df.empty:
            plain = df["report_nm"].map(strip_brackets)
            same_kind = plain.str.startswith(name) if fs == "CFS" else plain.str.startswith(name) & ~plain.str.startswith("연결")
            df = df[same_kind & df["report_nm"].map(lambda n: f"({y}." in squash(n))]
        if df.empty:
            note = f"{y} 사업연도 {name} 없음" + (" (연결 미작성 회사일 수 있음)" if fs == "CFS" else "")
            return Fetched(None, NO_DATA, Source("list", {"corp_code": corp_code, "year": y}, note=note), attempts + [note])
        row = df.sort_values("rcept_no").iloc[-1]
        attempts.append(f"{name} {row['rcept_no']} ({row['report_nm']})")
        return Fetched(row, OK, Source("list", {"corp_code": corp_code, "year": y}, row["rcept_no"], viewer_url(row["rcept_no"])),
                       attempts)

    def audit_statement(self, corp_code: str, year, fs: str = "CFS") -> Fetched:
        """감사보고서 원문의 재무제표 표를 읽어 sj_div·account_nm·thstrm_amount·frmtrm_amount(원 단위) 표로."""
        key = (corp_code, int(year), fs)
        if key in self._audit_cache:
            return self._audit_cache[key]
        rep = self.audit_report(corp_code, year, fs)
        if not rep.found:
            result = rep
        else:
            rcept = rep.value["rcept_no"]
            doc = self.document(rcept)
            attempts = rep.attempts + doc.attempts
            src = Source("감사보고서", {"corp_code": corp_code, "year": int(year), "fs": fs}, rcept, viewer_url(rcept))
            if not doc.found:
                result = Fetched(None, doc.status, _with_note(src, doc.source.note if doc.source else ""), attempts)
            else:
                df = parse_financial_statements(doc.value)
                if df.empty:
                    result = Fetched(None, UNVERIFIED, _with_note(src, "원문에서 재무제표 표를 읽지 못함"), attempts)
                else:
                    kinds = ", ".join(sorted(df["sj_div"].unique()))
                    result = Fetched(df, FROM_ORIGINAL, src, attempts + [f"원문 재무제표 {kinds} {len(df)}행"])
        self._audit_cache[key] = result
        return result

    def audit_account(self, corp_code: str, year, item: str, fs: str = "CFS") -> Fetched:
        """감사보고서 원문 기준 계정 값(원 단위). 상태는 '원문에서 찾음'.

        찾는 순서: 그해 감사보고서 당기 칸 → 다음 해 감사보고서 전기 칸(재작성됐을 수 있음).
        감사보고서에는 account_id가 없어 이름으로만 찾는다. 계정마다 허용한 재무제표(fs_only)만 본다.
        """
        spec = ACCOUNTS[item]
        if fs not in spec.fs_only:
            only = "·".join(FS_NAMES[f] for f in spec.fs_only)
            return Fetched(None, UNVERIFIED, Source("감사보고서", note=f"{item}은 {only}재무제표에서만 받음"),
                           [f"{item}: {FS_NAMES[fs]} 대상 아님"])
        attempts: list[str] = []
        last_src = None
        for offset, column, label in ((0, "thstrm_amount", "당기"), (1, "frmtrm_amount", "전기")):
            st = self.audit_statement(corp_code, int(year) + offset, fs)
            attempts += [f"{int(year) + offset} {a}" for a in st.attempts]
            if st.status == API_ERROR:
                return Fetched(None, API_ERROR, st.source, attempts)
            if not st.found:
                last_src = last_src or st.source
                continue
            last_src = st.source
            df = st.value[st.value[column].notna()]
            unknown_unit = df[df["unit"].isna()]
            hit = find_account(df[df["unit"].notna()], spec, column, use_ids=False)
            if hit:
                value, how = hit
                row, table_unit = _source_row(df, spec, column, value)
                note = f"{FS_NAMES[fs]} {AUDIT_REPORTS[fs][1]} {label} 칸 · {how}" + (f" · {row}" if row else "")
                if offset:
                    note += f" · {int(year) + 1} 감사보고서의 전기 값(재작성됐을 수 있음)"
                params = {**st.source.params, "표 단위": table_unit}
                got = _number_result(value, Source("감사보고서", params, st.source.rcept_no, st.source.url, note),
                                     attempts + [f"{item}: {label} {how}"], spec.absolute)
                if got.status == OK:
                    got.status = FROM_ORIGINAL
                return got
            if find_account(unknown_unit, spec, column, use_ids=False):
                return Fetched(None, UNVERIFIED, _with_note(st.source, "표 단위(원·천원·백만원)를 찾지 못함: 원문 확인"),
                               attempts)
            attempts.append(f"{item}: {int(year) + offset} 감사보고서 {label} 칸에 계정 없음")
        return Fetched(None, UNVERIFIED, _with_note(last_src, f"감사보고서에서 '{item}' 값을 찾지 못함: 원문 확인"), attempts)

    # --- 기업개황 ---

    def company(self, corp_code: str) -> Fetched:
        """기업개황(company.json): 정식 회사명·종목코드·법인구분(시장)·업종코드·결산월. value는 dict."""
        params = {"corp_code": corp_code}
        status, message, body = self.call("company.json", params)
        if status != "000":
            kind = NO_DATA if status == "013" else API_ERROR
            return Fetched(None, kind, Source("company", params), [f"company {corp_code}: {status} {message}"])
        keys = ("corp_name", "stock_name", "stock_code", "corp_cls", "induty_code", "acc_mt")
        value = {k: str(body.get(k, "") or "").strip() for k in keys}
        value["시장"] = CORP_CLS.get(value["corp_cls"], value["corp_cls"])
        return Fetched(value, OK, Source("company", params), [f"company {corp_code}: 정상"])

    # --- 주식 총수·최대주주 ---

    def share_counts(self, corp_code: str, year, reprt_code: str = "11011", kind: str = "보통주") -> dict[str, Fetched]:
        """주식의 총수 현황(stockTotqySttus): 발행주식총수·자기주식수·유통주식수.

        유통주식수가 비어 있고 발행·자기주식이 있으면 발행 − 자기로 계산하고 메모를 남긴다.
        """
        params = {"corp_code": corp_code, "bsns_year": _fiscal_year(year), "reprt_code": reprt_code}
        df, status, note = self._rows("stockTotqySttus.json", params)
        fields = {"발행주식총수": "istc_totqy", "자기주식수": "tesstk_co", "유통주식수": "distb_stock_co"}
        if df is None or df.empty:
            return {k: Fetched(None, status, Source("stockTotqySttus", params), [note]) for k in fields}
        row = df[df["se"].map(lambda s: squash(s).startswith(squash(kind)[:2]))]
        rcept = str(df["rcept_no"].iloc[0]) if "rcept_no" in df else None
        src = Source("stockTotqySttus", params, rcept)
        if row.empty:
            return {k: Fetched(None, UNVERIFIED, _with_note(src, f"'{kind}' 행 없음"), [note]) for k in fields}
        r = row.iloc[0]
        out = {k: _number_result(r.get(col), src, [note]) for k, col in fields.items()}
        issued, treasury = out["발행주식총수"].value, out["자기주식수"].value
        if out["유통주식수"].value is None and issued is not None and treasury is not None:
            out["유통주식수"] = Fetched(issued - treasury, OK, _with_note(src, "발행주식총수 − 자기주식수로 계산"), [note])
        return out

    def largest_holder_stake(self, corp_code: str, year, reprt_code: str = "11011", stock_knd: str = "보통주") -> Fetched:
        """최대주주 및 특수관계인 기말 지분율 합계(%). '계' 행이 있으면 그 값, 없으면 개별 행을 더한다."""
        params = {"corp_code": corp_code, "bsns_year": _fiscal_year(year), "reprt_code": reprt_code}
        df, status, note = self._rows("hyslrSttus.json", params)
        if df is None or df.empty:
            return Fetched(None, status, Source("hyslrSttus", params), [note])
        rcept = str(df["rcept_no"].iloc[0]) if "rcept_no" in df else None
        src = Source("hyslrSttus", params, rcept)
        knd = df["stock_knd"].map(squash) if "stock_knd" in df else pd.Series("", index=df.index)
        part = df[knd.str.startswith(squash(stock_knd)[:2]) | knd.isin(["", "-"])]
        total = part[part["nm"].map(lambda n: squash(n) in ("계", "합계"))]
        if not total.empty:
            return _number_result(total["trmend_posesn_stock_qota_rt"].iloc[0], _with_note(src, "'계' 행"), [note])
        values = [to_number(v) for v in part["trmend_posesn_stock_qota_rt"]]
        values = [v for v in values if v is not None]
        if not values:
            return Fetched(None, UNVERIFIED, _with_note(src, "지분율 값 없음"), [note])
        return Fetched(round(sum(values), 2), OK, _with_note(src, f"개별 {len(values)}행 합계"), [note])


# --- 표에서 값 고르기 (요청 없이 쓰는 순수 함수) ---


def find_account(df: pd.DataFrame, spec: Account, field: str = "thstrm_amount",
                 use_ids: bool = True) -> tuple[int | float | None, str] | None:
    """재무제표 표에서 계정 값을 찾는다. (값, 찾은 방법) 또는 None.

    값이 '-'인 행은 찾은 것으로 보지 않는다. 후보 값이 서로 다르면 None을 돌려 사람이 보게 한다.
    """
    if df is None or df.empty or field not in df:
        return None
    rows = df[df["sj_div"].isin(spec.statements)] if "sj_div" in df else df
    tries = []
    if use_ids and "account_id" in rows:
        tries.append(("account_id 일치", rows[rows["account_id"].isin(spec.ids)]))
    names = rows["account_nm"].map(strip_brackets) if "account_nm" in rows else pd.Series(dtype=str)
    tries.append(("계정 이름 일치", rows[names.isin({strip_brackets(n) for n in spec.names})]))
    for how, hit in tries:
        values = [to_number(v) for v in hit[field]]
        values = sorted({v for v in values if v is not None})
        if len(values) == 1:
            return values[0], how
        if len(values) > 1:
            return None
    return None


def pick_dividend(df: pd.DataFrame, item: str, period: str = "thstrm", stock_knd: str = "보통주",
                  basis: str = "연결", strict_basis: bool = True) -> dict:
    """alotMatter 표에서 항목 하나. {'status', 'value', 'unit', 'how', 'note'}.

    status: OK · NO_DATA(행은 있으나 값이 '-') · UNVERIFIED(값이 여러 개) · NO_ROW(행 자체가 없음)

    - se 이름은 '(연결)당기순이익(백만원)'처럼 기준·단위가 붙어 있어 괄호를 떼고 비교한다.
    - 연결/별도 표시가 있는 항목은 basis 쪽만 본다. 없으면 '행 없음'(다른 쪽으로 대체하지 않음).
      strict_basis=False면 다른 쪽 값을 쓰고 메모한다(비교용으로만).
    - 주식 종류가 적힌 행은 stock_knd(보통주)만 본다.
    """
    se = df["se"].astype(str)
    rows = df[se.map(strip_brackets) == squash(item)]
    if rows.empty:
        return {"status": NO_ROW, "value": None, "unit": 1, "how": "행 없음", "note": ""}
    if "stock_knd" in rows:
        knd = rows["stock_knd"].map(squash)
        typed = knd.str.startswith(squash(stock_knd)[:2])
        if typed.any():
            rows = rows[typed]
        elif not knd.isin(["", "-", "nan", "None"]).all():
            return {"status": NO_ROW, "value": None, "unit": 1, "how": f"{stock_knd} 행 없음", "note": ""}
    note = ""
    marks = rows["se"].map(lambda s: "연결" if "(연결)" in squash(s) else "별도" if "(별도)" in squash(s) else "")
    if marks.isin(["연결", "별도"]).any():
        if (marks == basis).any():
            rows = rows[marks == basis]
        elif strict_basis:
            return {"status": NO_ROW, "value": None, "unit": 1, "how": f"({basis}) 행 없음", "note": ""}
        else:
            other = "별도" if basis == "연결" else "연결"
            rows = rows[marks == other]
            note = f"{basis} 값이 없어 {other} 값을 씀"
    raw_values = list(rows[period]) if period in rows else []
    values = sorted({v for v in (to_number(x) for x in raw_values) if v is not None})
    unit = unit_from_label(rows["se"].iloc[0])
    if len(values) == 1:
        return {"status": OK, "value": values[0], "unit": unit, "how": f"'{rows['se'].iloc[0]}' 행", "note": note}
    if len(values) > 1:
        return {"status": UNVERIFIED, "value": None, "unit": unit, "how": f"값 여러 개 {values}",
                "note": f"같은 항목 값이 여러 개 {values}: 원문 확인"}
    return {"status": NO_DATA, "value": None, "unit": unit, "how": f"값이 비어 있음 {raw_values}", "note": note}


def find_in_tables(files: dict[str, str], label: str, as_text: bool = False) -> Fetched:
    """원문 표에서 첫 칸(또는 앞 칸)에 label이 들어간 행을 찾아, 그 뒤 첫 숫자(as_text면 첫 글자 칸)를 꺼낸다.

    DART 원문 XML의 TABLE/TR/TD·TE·TU와 HTML의 table/tr/td·th를 모두 읽는다.
    후보가 하나로 정해지면 '원문에서 찾음', 여러 개거나 없으면 '확인 불가'.
    """
    key = strip_brackets(label)
    candidates = []
    for name, text in files.items():
        for cells in table_rows(text):
            for i, cell in enumerate(cells[:-1]):
                if key and key in strip_brackets(cell):
                    rest = [c for c in cells[i + 1:] if c]
                    if as_text:
                        value = next((c for c in rest if c not in ("-",)), None)
                    else:
                        value = next((v for v in (to_number(c) for c in rest) if v is not None), None)
                    if value is not None:
                        candidates.append((value, unit_from_label(cell), name, " | ".join(cells)))
                    break
    distinct = sorted({(c[0], c[1]) for c in candidates}, key=str)
    if len(distinct) == 1:
        value, unit, name, row = candidates[0]
        return Fetched(value, FROM_ORIGINAL, Source("document", note=f"{name}: {row}"),
                       [f"원문 표 '{label}' 행"], unit=unit)
    if distinct:
        rows = "; ".join(c[3] for c in candidates[:5])
        return Fetched(None, UNVERIFIED, Source("document", note=f"후보 여러 개: {rows}"),
                       [f"원문 표 '{label}' 후보 {len(distinct)}개"])
    return Fetched(None, UNVERIFIED, Source("document", note=f"원문 표에 '{label}' 행 없음"),
                   [f"원문 표 '{label}' 행 없음"])


def parse_financial_statements(files: dict[str, str]) -> pd.DataFrame:
    """감사보고서 원문에서 재무제표 표를 읽는다. 금액은 원 단위로 바꾼다(단위를 못 찾으면 unit이 비어 있음).

    - 표 앞 글자(또는 표 첫 행)에 재무제표 제목이 하나만 있으면 그 표부터 그 재무제표로 본다.
      감사의견 문단처럼 제목이 여러 개 나열된 글은 무시한다. '주석'이 나오면 재무제표 구간이 끝난다.
    - '(단위 : 원)' · 천원 · 백만원을 읽어 곱한다.
    - 머리 행의 둘째 칸이 '주석'이면 각 행의 둘째 칸(주석 번호)을 뺀다.
    - 남은 금액 칸을 반으로 나눠 앞쪽을 당기, 뒤쪽을 전기로 보고 각 쪽의 마지막 숫자를 쓴다
      (한 기간에 '내역·합계' 두 칸을 쓰는 표도 읽힘). 칸 수가 홀수면 당기·전기를 정할 수 없어 비워 둔다.
    """
    rows = []
    for name, text in files.items():
        current, unit, prev_end = None, None, 0
        for m in re.finditer(r"<table\b.*?</table>", text, flags=re.S | re.I):
            # 표 앞 글자를 문단 단위로 나눠 표에 가까운 문단부터 본다
            pieces = [squash(html.unescape(x)) for x in re.split(r"<[^>]+>", text[prev_end:m.start()])]
            pieces = [x for x in pieces if x][::-1]
            prev_end = m.end()
            cells_rows = table_rows(m.group(0))
            head = squash(" ".join(cells_rows[0])) if cells_rows else ""
            title = next((t for t in map(_statement_title, pieces) if t), None)
            if not title and len(cells_rows) <= 3:
                title = _statement_title(head)
            if title:
                current, unit = title, None
            elif current and any(x.startswith("주석") and len(x) <= 15 or "재무제표에대한주석" in x for x in pieces):
                current = None
            found_unit = next((u for u in map(_unit_in, pieces) if u), None) or _unit_in(
                " ".join(squash(" ".join(r)) for r in cells_rows[:3]))
            if found_unit:
                unit = found_unit
            if not current:
                continue
            header = next((r for r in cells_rows if any(k in squash(c) for c in r for k in ("당기", "(당)", "당)"))), None)
            drop_note = bool(header and len(header) > 1 and "주석" in squash(header[1]))
            for cells in cells_rows:
                if cells is header or not cells[0] or _statement_title(squash(cells[0])) or _unit_in(squash(cells[0])):
                    continue
                amounts = cells[2:] if drop_note and len(cells) > 2 else cells[1:]
                if not any(to_number(c) is not None for c in amounts):
                    continue
                if len(amounts) == 1:
                    cur, prev = to_number(amounts[0]), None
                elif len(amounts) % 2 == 0:
                    half = len(amounts) // 2
                    cur = next((v for v in reversed([to_number(c) for c in amounts[:half]]) if v is not None), None)
                    prev = next((v for v in reversed([to_number(c) for c in amounts[half:]]) if v is not None), None)
                else:
                    cur = prev = None
                rows.append({
                    "sj_div": current, "account_nm": cells[0],
                    "thstrm_amount": None if cur is None or unit is None else cur * unit,
                    "frmtrm_amount": None if prev is None or unit is None else prev * unit,
                    "unit": unit, "file": name, "row": " | ".join(cells),
                })
    return pd.DataFrame(rows, columns=["sj_div", "account_nm", "thstrm_amount", "frmtrm_amount", "unit", "file", "row"])


_TITLES = (("포괄손익계산서", "CIS"), ("손익계산서", "IS"), ("재무상태표", "BS"), ("대차대조표", "BS"),
           ("현금흐름표", "CF"), ("자본변동표", "SCE"))


def _statement_title(text: str) -> str | None:
    """글 속 재무제표 제목 하나 → sj_div. 제목이 없거나 여러 종류가 나열돼 있으면 None."""
    found = set()
    rest = text
    for title, code in _TITLES:
        if title in rest:
            found.add(code)
            rest = rest.replace(title, "")
    return found.pop() if len(found) == 1 else None


def _unit_in(text: str) -> int | None:
    m = re.search(r"단위[:：]?(백만원|천원|원)", squash(text))
    return {"원": 1, "천원": 1_000, "백만원": 1_000_000}[m.group(1)] if m else None


def _source_row(df: pd.DataFrame, spec: Account, column: str, value) -> tuple[str, int]:
    """찾은 값의 원문 행과 표 단위."""
    names = {strip_brackets(n) for n in spec.names}
    hit = df[df["sj_div"].isin(spec.statements) & df["account_nm"].map(strip_brackets).isin(names)]
    hit = hit[hit[column].map(to_number) == value]
    if hit.empty:
        return "", 1
    return f"{hit['file'].iloc[0]}: {hit['row'].iloc[0]}", int(hit["unit"].iloc[0])


MATCH = "일치"
MISMATCH = "불일치"


def cross_check(audit: Fetched, api: Fetched) -> str:
    """감사보고서 값과 사업보고서 API 값 대조. 감사보고서 표가 천원·백만원 단위면 그 단위 안의 차이는 일치로 본다."""
    if audit.value is None:
        return "감사보고서 값 없음"
    if api.value is None:
        return "API 값 없음"
    tolerance = (audit.source.params.get("표 단위", 1) if audit.source else 1) - 1
    gap = abs(audit.value - api.value)
    return MATCH if gap <= tolerance else f"{MISMATCH}(차이 {gap:,}원)"


def table_rows(markup: str) -> list[list[str]]:
    """표 행마다 칸 글자 목록. 태그는 지우고 공백은 하나로 줄인다."""
    rows = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", markup, flags=re.S | re.I):
        cells = re.findall(r"<t[dheu]\b[^>]*>(.*?)</t[dheu]>", tr, flags=re.S | re.I)
        cleaned = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in cells]
        if any(cleaned):
            rows.append(cleaned)
    return rows


def match_stock_codes(corp_df: pd.DataFrame, stock_codes) -> pd.DataFrame:
    """종목코드 → 고유번호. 앞자리 0이 빠진 코드도 6자리로 맞춘다. 없거나 여러 개면 '확인 불가'."""
    listed = corp_df[corp_df["stock_code"].astype(str).str.strip() != ""].copy()
    listed["stock_code"] = listed["stock_code"].astype(str).str.strip().str.zfill(6)
    rows = []
    for code in stock_codes:
        norm = re.sub(r"\D", "", str(code)).zfill(6)
        hit = listed[listed["stock_code"] == norm]
        if len(hit) == 1:
            rows.append({"stock_code": norm, "corp_code": hit["corp_code"].iloc[0], "corp_name": hit["corp_name"].iloc[0],
                         "상태": OK, "메모": ""})
        else:
            memo = "고유번호표에 없음(상장폐지·코드 변경 확인)" if hit.empty else f"후보 {len(hit)}개"
            rows.append({"stock_code": norm, "corp_code": None, "corp_name": None, "상태": UNVERIFIED, "메모": memo})
    return pd.DataFrame(rows, columns=["stock_code", "corp_code", "corp_name", "상태", "메모"])


# --- 내부 도우미 ---


def _number_result(raw, src: Source, attempts: list[str], absolute: bool = False) -> Fetched:
    value = to_number(raw)
    if value is None:
        return Fetched(None, NO_DATA, _with_note(src, f"값이 비어 있음({raw!r})"), attempts)
    if absolute and value < 0:
        return Fetched(-value, OK, _with_note(src, "음수로 와서 절댓값으로 저장"), attempts)
    return Fetched(value, OK, src, attempts)


def _with_note(src: Source | None, note: str) -> Source | None:
    if src is None:
        return Source("", note=note)
    joined = f"{src.note} · {note}" if src.note else note
    return Source(src.api, src.params, src.rcept_no, src.url, joined)


def _json_status(raw: bytes) -> str | None:
    try:
        return str(json.loads(raw).get("status"))
    except (ValueError, AttributeError):
        return None


def _xml_status(raw: bytes) -> str | None:
    m = re.search(rb"<status>\s*(\d+)\s*</status>", raw)
    return m.group(1).decode() if m else None


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _ymd(value) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y%m%d")
    return re.sub(r"\D", "", str(value))


def _quarters(start: str, end: str) -> list[tuple[str, str]]:
    """YYYYMMDD 기간을 3개월 이하 조각으로 나눈다."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    while s <= e:
        stop = min(s + pd.DateOffset(months=3) - pd.Timedelta(days=1), e)
        out.append((s.strftime("%Y%m%d"), stop.strftime("%Y%m%d")))
        s = stop + pd.Timedelta(days=1)
    return out
