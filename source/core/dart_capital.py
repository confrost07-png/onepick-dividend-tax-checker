"""증자·감자(OpenDART 주요사항보고서 API)와 액면분할·병합(DART 원문 표) 수집·해석.

API 키는 환경변수 OPENDART_API_KEY, 없으면 저장소 위쪽 폴더의 .env에서 그 한 줄만 읽는다. 키는 캐시 파일 이름·로그·오류 문구에 넣지 않는다.
받은 응답은 data/raw/dart_api_cache/(API)·data/raw/dart_cache/(원문)에 두고 다시 받지 않는다. 오류 응답은 저장하지 않는다.
DB 없이 시험할 수 있게 해석 함수는 응답 dict·원문 줄을 받아 행 dict를 돌려준다.
"""
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_CACHE = ROOT / "data" / "raw" / "dart_api_cache"
DOC_CACHE = ROOT / "data" / "raw" / "dart_cache"
API = "https://opendart.fss.or.kr/api"
DART = "https://dart.fss.or.kr"
KEY_NAME = "OPENDART_API_KEY"

BEGIN, END = "20230101", "20261020"  # 배당 결정 공시(05)와 같은 기간
API_BEGIN = "20000101"  # 증자·감자 API는 원공시 날짜로 찾아서, 기간 전 원공시를 기간 안에 정정한 건은 넓혀야 나온다

# 보고서명 → 종류. 자회사·종속회사 공시는 그 회사 자신의 일이 아니라 뺀다.
CAPITAL_TITLES = [  # (정규식, 종류, API). 유무상을 먼저 봐야 무상증자로 잘못 잡히지 않음
    (r"유\s*무\s*상\s*증\s*자\s*결\s*정", "유무상증자", "pifricDecsn"),
    (r"유\s*상\s*증\s*자\s*결\s*정", "유상증자", "piicDecsn"),
    (r"무\s*상\s*증\s*자\s*결\s*정", "무상증자", "fricDecsn"),
    (r"감\s*자\s*결\s*정", "감자", "crDecsn"),
]
SPLIT_TITLES = [(r"주\s*식\s*분\s*할\s*결\s*정", "주식분할"), (r"주\s*식\s*병\s*합\s*결\s*정", "주식병합")]
_NOT_SELF = re.compile(r"자\s*회\s*사|종\s*속\s*회\s*사")


class StopRun(RuntimeError):
    """키 오류·하루 호출 한도 초과처럼 더 불러도 소용없는 오류. 이미 받은 응답은 캐시에 남아 다시 실행하면 이어서 받는다."""


def api_key() -> str | None:
    if os.environ.get(KEY_NAME):
        return os.environ[KEY_NAME].strip()
    for d in [ROOT, *ROOT.parents]:
        f = d / ".env"
        if f.is_file():
            for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                k, _, v = ln.partition("=")
                if k.strip() == KEY_NAME and v.strip():
                    return v.strip().strip("'\"")
    return None


# --- 받기 -----------------------------------------------------------------

STOP_STATUS = {"010": "등록되지 않은 키", "011": "사용할 수 없는 키", "012": "접근할 수 없는 IP",
               "020": "요청 제한 초과", "901": "키 기간 만료"}


def call(key: str, endpoint: str, params: dict, pause: float = 0.15) -> dict:
    """OpenDART JSON 1회. status '000'(정상)·'013'(자료 없음)만 캐시에 둔다."""
    API_CACHE.mkdir(parents=True, exist_ok=True)
    tag = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
    path = API_CACHE / (hashlib.sha1(tag.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = f"{API}/{endpoint}.json?" + urllib.parse.urlencode({"crtfc_key": key, **params})
    last = ""
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
            last = type(e).__name__  # 주소에 키가 있어 오류 문구는 남기지 않음
            time.sleep(2)
            continue
        status = data.get("status")
        if status in STOP_STATUS:
            raise StopRun(f"OpenDART {status} {STOP_STATUS[status]}")
        if status in ("000", "013"):
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            time.sleep(pause)
        return data
    return {"status": "network", "message": f"3번 받지 못함 ({last})"}


def filing_list(key: str, corp_code: str, pblntf_ty: str, begin: str = BEGIN, end: str = END) -> tuple[list[dict], str]:
    """회사의 공시 목록 전부(정정 전 원공시 포함). (행 목록, 결과 문구)."""
    rows, page = [], 1
    while True:
        d = call(key, "list", {"corp_code": corp_code, "bgn_de": begin, "end_de": end, "pblntf_ty": pblntf_ty,
                               "last_reprt_at": "N", "page_no": page, "page_count": 100})
        if d.get("status") == "013":
            return rows, "공시 없음"
        if d.get("status") != "000":
            return rows, f"실패: {d.get('status')} {d.get('message')}"
        rows += d.get("list", [])
        if page >= int(d.get("total_page") or 1):
            return rows, "성공"
        page += 1


def decision_rows(key: str, corp_code: str, endpoint: str, begin: str = API_BEGIN, end: str = END) -> tuple[list[dict], str]:
    """증자·감자 결정 응답 중 접수일이 기간(BEGIN~END) 안인 것."""
    d = call(key, endpoint, {"corp_code": corp_code, "bgn_de": begin, "end_de": end})
    if d.get("status") == "013":
        return [], "공시 없음"
    if d.get("status") != "000":
        return [], f"실패: {d.get('status')} {d.get('message')}"
    rows = [r for r in d.get("list", []) if BEGIN <= str(r.get("rcept_no", ""))[:8] <= END]
    return rows, "성공" if rows else "공시 없음"


def _decode(raw: bytes) -> str:
    head = raw[:3000].decode("ascii", "ignore").lower()
    return raw.decode("cp949" if ("euc-kr" in head or "ks_c_5601" in head) else "utf-8", "replace")


def get_page(url: str, pause: float = 0.4) -> str:
    """DART 공개 화면 1장 (키 없음). source/core/dart_doc.py와 같은 캐시 폴더·이름 규칙."""
    DOC_CACHE.mkdir(parents=True, exist_ok=True)
    path = DOC_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if path.exists():
        return _decode(path.read_bytes())
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                raw = r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(2)
            continue
        if raw:
            path.write_bytes(raw)
            time.sleep(pause)
            return _decode(raw)
    raise RuntimeError(f"원문을 받지 못함: {url}")


def table_lines(page: str) -> list[str]:
    """HTML → 줄 목록. 표는 한 행이 한 줄이고 칸은 ' | '로 나뉜다."""
    x = re.sub(r"(?is)<style.*?</style>|<script.*?</script>", " ", page)
    x = re.sub(r"\s+", " ", x)
    x = re.sub(r"(?i)</t[dh]>", " | ", x)
    x = re.sub(r"(?i)</tr>|</table>|<table[^>]*>", "\x00", x)
    x = html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ")
    return [re.sub(r" +", " ", ln).strip() for ln in x.split("\x00") if ln.strip()]


def doc_lines(rcept_no: str) -> list[str]:
    """한 장짜리 공시(분할·병합 결정 등)의 본문 줄."""
    page = get_page(f"{DART}/dsaf001/main.do?rcpNo={rcept_no}")
    m = re.search(r"viewDoc\(\"(\d+)\", \"(\d+)\", \"(\d+)\", \"(\d+)\", \"(\d+)\", \"([^\"]+)\"", page)
    if not m:
        return []
    rcp, dcm, ele, off, ln, dtd = m.groups()
    return table_lines(get_page(f"{DART}/report/viewer.do?rcpNo={rcp}&dcmNo={dcm}&eleId={ele}"
                                f"&offset={off}&length={ln}&dtd={dtd}"))


def link(rcept_no: str) -> str:
    return f"{DART}/dsaf001/main.do?rcpNo={rcept_no}"


# --- 값 정리 ---------------------------------------------------------------


def num(v) -> Decimal | None:
    """'1,000,000' → 1000000. '-'·빈칸·글자는 None. '(1,000)'은 음수."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "－", "−"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        d = Decimal(s.strip("()"))
    except InvalidOperation:
        return None
    return -d if neg else d


def text(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return None if s in ("", "-") else s


def rcept_date(rcept_no: str) -> str:
    return f"{rcept_no[:4]}-{rcept_no[4:6]}-{rcept_no[6:8]}"


def classify(report_nm: str) -> tuple[str, str] | None:
    """보고서명 → (종류, 'API 이름' 또는 'doc'). 해당 없으면 None."""
    if not report_nm or _NOT_SELF.search(report_nm):
        return None
    for pat, kind, endpoint in CAPITAL_TITLES:
        if re.search(pat, report_nm):
            return kind, endpoint
    for pat, kind in SPLIT_TITLES:
        if re.search(pat, report_nm):
            return kind, "doc"
    return None


def is_correction(report_nm: str | None) -> bool:
    return bool(report_nm) and report_nm.lstrip().startswith("[")


def _sum(vals) -> Decimal | None:
    nums = [v for v in vals if v is not None]
    return sum(nums) if nums else None


def _base(r: dict, kind: str, endpoint: str, report_nm: str | None) -> dict:
    rc = r.get("rcept_no", "")
    cols = ("shares_common shares_pref par_won before_common before_pref after_common after_pref per_share_common "
            "per_share_pref funds_won capital_before_won capital_after_won ratio_common_pct ratio_pref_pct method reason "
            "record_date listing_date board_date check_result").split()
    return {"rcept_no": rc, "kind": kind, "corp_code": r.get("corp_code"), "corp_name": r.get("corp_name"),
            "rcept_dt": rcept_date(rc), "report_nm": report_nm, "is_correction": is_correction(report_nm),
            "version": "API 최종본", **dict.fromkeys(cols), "payload": json.dumps(r, ensure_ascii=False),
            "link": link(rc), "source": endpoint}


def _paid(r: dict, p: str = "") -> dict:
    return {"shares_common": num(r.get(p + "nstk_ostk_cnt")), "shares_pref": num(r.get(p + "nstk_estk_cnt")),
            "par_won": num(r.get(p + "fv_ps")), "before_common": num(r.get(p + "bfic_tisstk_ostk")),
            "before_pref": num(r.get(p + "bfic_tisstk_estk")),
            "funds_won": _sum(num(r.get(p + k)) for k in
                              ("fdpp_fclt", "fdpp_bsninh", "fdpp_op", "fdpp_dtrp", "fdpp_ocsa", "fdpp_etc")),
            "method": text(r.get(p + "ic_mthn"))}


def _free(r: dict, p: str = "") -> dict:
    return {"shares_common": num(r.get(p + "nstk_ostk_cnt")), "shares_pref": num(r.get(p + "nstk_estk_cnt")),
            "par_won": num(r.get(p + "fv_ps")), "before_common": num(r.get(p + "bfic_tisstk_ostk")),
            "before_pref": num(r.get(p + "bfic_tisstk_estk")),
            "per_share_common": num(r.get(p + "nstk_ascnt_ps_ostk")), "per_share_pref": num(r.get(p + "nstk_ascnt_ps_estk")),
            "record_date": text(r.get(p + "nstk_asstd")), "listing_date": text(r.get(p + "nstk_lstprd")),
            "board_date": text(r.get(p + "bddd"))}


def check_reduction(before, cut, after) -> str:
    if None in (before, cut, after):
        return "검산 못 함 (빈칸)"
    return "일치" if before - cut == after else f"안 맞음 ({before:,} − {cut:,} ≠ {after:,})"


def check_reduction_row(row: dict) -> str | None:
    """보통주 감자면 보통주로, 종류주식만 감자면 종류주식으로 검산. 액면가 감액은 주식 수가 그대로여야 맞다."""
    if all(row[k] is None for k in ("shares_common", "shares_pref", "par_won")):
        return None  # 값이 모두 '-'인 응답은 capital_rows에서 따로 표시
    side = "common" if row["shares_common"] is not None or row["shares_pref"] is None else "pref"
    before, cut, after = row[f"before_{side}"], row[f"shares_{side}"], row[f"after_{side}"]
    label = "" if side == "common" else "종류주식 "
    if re.search(r"액\s*면", row["method"] or "") and before is not None and before == after:
        return f"{label}일치 (액면가 감액, 주식 수 변동 없음)"
    res = check_reduction(before, cut, after)
    return res if not label else label + res


def capital_rows(r: dict, endpoint: str, report_nm: str | None = None) -> list[dict]:
    """API 응답 1행 → raw.dart_capital_event 행 (유무상은 2행). 주식 수·액면가가 모두 '-'인 응답(철회 정정 등)은 표시한다."""
    rows = _capital_rows(r, endpoint, report_nm)
    for row in rows:
        if all(row[k] is None for k in ("shares_common", "shares_pref", "par_won")):
            row["check_result"] = "원문 주식 수·액면가가 모두 '-' (철회 등 확인 필요)"
    return rows


def _capital_rows(r: dict, endpoint: str, report_nm: str | None) -> list[dict]:
    if endpoint == "piicDecsn":
        return [{**_base(r, "유상증자", endpoint, report_nm), **_paid(r)}]
    if endpoint == "fricDecsn":
        return [{**_base(r, "무상증자", endpoint, report_nm), **_free(r)}]
    if endpoint == "pifricDecsn":
        return [{**_base(r, "유무상증자(유상)", endpoint, report_nm), **_paid(r, "piic_")},
                {**_base(r, "유무상증자(무상)", endpoint, report_nm), **_free(r, "fric_")}]
    if endpoint == "crDecsn":
        row = {**_base(r, "감자", endpoint, report_nm),
               "shares_common": num(r.get("crstk_ostk_cnt")), "shares_pref": num(r.get("crstk_estk_cnt")),
               "par_won": num(r.get("fv_ps")),
               "before_common": num(r.get("bfcr_tisstk_ostk")), "after_common": num(r.get("atcr_tisstk_ostk")),
               "before_pref": num(r.get("bfcr_tisstk_estk")), "after_pref": num(r.get("atcr_tisstk_estk")),
               "capital_before_won": num(r.get("bfcr_cpt")), "capital_after_won": num(r.get("atcr_cpt")),
               "ratio_common_pct": num(r.get("cr_rt_ostk")), "ratio_pref_pct": num(r.get("cr_rt_estk")),
               "method": text(r.get("cr_mth")), "reason": text(r.get("cr_rs")), "record_date": text(r.get("cr_std")),
               "listing_date": text(r.get("crsc_nstklstprd")), "board_date": text(r.get("bddd"))}
        row["check_result"] = check_reduction_row(row)
        return [row]
    raise ValueError(endpoint)


def versions(titles: dict[str, str], returned: set[str]) -> dict[str, tuple[str, str | None]]:
    """API는 정정 공시 묶음에서 마지막 판만 준다. 목록의 접수번호 → (판 구분, 그 묶음의 최종본 접수번호).

    묶음: 원공시(제목이 '['로 시작하지 않음)나 앞 묶음이 끝난 뒤의 공시에서 시작해, API가 준 최종본에서 끝난다.
    앞 공시와 GAP_DAYS일 넘게 떨어진 정정은 다른 일(기간 전 원공시의 정정 등)로 본다.
    첨부서류만 바꾼 정정([첨부정정]·[첨부추가])만 남은 묶음은 API가 그 앞 공시를 대신 주므로 앞 최종본을 가리킨다.
    API가 아무것도 주지 않은 묶음은 ('API 응답 없음', 묶음의 마지막 접수번호) — 마지막 판을 원문에서 읽는다.
    """
    chains, cur, prev = [], None, None
    for rc in sorted(titles):
        if cur is None or not is_correction(titles[rc]) or (prev and _days(prev, rc) > GAP_DAYS):
            cur = []
            chains.append(cur)
        cur.append(rc)
        prev = rc
        if rc in returned:
            cur = None
    out, last_final = {}, None
    for chain in chains:
        final = max((rc for rc in chain if rc in returned), default=None)
        attach_only = final is None and last_final and all(re.match(r"\[\s*첨\s*부", titles[rc]) for rc in chain)
        for rc in chain:
            out[rc] = ("API 최종본", final) if rc in returned else \
                      ("앞선 판", final) if final and rc < final else \
                      ("첨부만 정정", last_final) if attach_only else ("API 응답 없음", chain[-1])  # 원문으로 읽을 판
        last_final = final or last_final
    return out


GAP_DAYS = 120


def _days(a: str, b: str) -> int:
    """접수번호 앞 8자리(날짜) 사이 일수."""
    da, db_ = (date(int(x[:4]), int(x[4:6]), int(x[6:8])) for x in (a, b))
    return abs((db_ - da).days)


def listed_only_row(filing: dict, kind: str, version: str, final: str | None, endpoint: str) -> dict:
    """API가 주지 않은 목록 공시 1건. 값은 비우고 판 구분만 적는다."""
    row = {**_base({"rcept_no": filing["rcept_no"], "corp_code": filing["corp_code"], "corp_name": filing.get("corp_name")},
                   kind, endpoint, filing.get("report_nm")), "version": version, "payload": "{}", "source": "list.json"}
    title = filing.get("report_nm") or ""
    row["check_result"] = (f"정정 묶음의 최종본 {final}에 값이 있음" if version == "앞선 판" else
                           f"첨부서류만 정정, 본문 값은 {final}과 같음" if version == "첨부만 정정" else
                           "주요사항보고서가 아닌 공시라 API 없음 (원문 확인 필요)" if "주요사항보고서" not in title else
                           "목록에는 있으나 API 응답에 없음 (원문 확인 필요)")
    return row


# --- 유상증자 원문 읽기 (API가 주지 않은 공시) ------------------------------

_SEC = re.compile(r"^(\d+)\.\s*")
_COMMON = re.compile(r"^보\s*통\s*주")
_PREF = re.compile(r"^(기\s*타|우\s*선|종\s*류)\s*주")


def paid_fields(lines: list[str]) -> dict:
    """유상증자 결정 본문 → _paid()와 같은 열 + 일정. 정정공시는 정정 내역표 뒤 본문(마지막 '1. 신주의 종류와 수')부터."""
    out = {"shares_common": None, "shares_pref": None, "par_won": None, "before_common": None, "before_pref": None,
           "funds_won": None, "method": None, "record_date": None, "listing_date": None, "board_date": None}
    starts = [i for i, ln in enumerate(lines) if re.match(r"1\.\s*신\s*주\s*의\s*종\s*류\s*와\s*수", ln)]
    if not starts:
        return out
    sec, funds = None, []
    for ln in lines[starts[-1]:]:
        cells = _cells(ln)
        if not cells:
            continue
        m = _SEC.match(cells[0])
        if m:
            sec = int(m.group(1))
            title = _SEC.sub("", cells[0])
            rest = cells[1:]
        else:
            title, rest = "", cells
        if sec in (1, 3) and rest:  # 신주 / 증자 전 발행주식총수: '보통주식 (주) | 수', '기타주식 (주) | 수'
            col = "shares" if sec == 1 else "before"
            if _COMMON.match(rest[0]):
                out[f"{col}_common"] = num(rest[-1]) if len(rest) > 1 else None
            elif _PREF.match(rest[0]):
                out[f"{col}_pref"] = num(rest[-1]) if len(rest) > 1 else None
        elif sec == 2 and m and rest:
            out["par_won"] = num(rest[-1])
        elif sec == 4 and rest and re.search(r"\(\s*원\s*\)", rest[0]):
            funds.append(num(rest[-1]))
        elif sec == 5 and m and rest:
            out["method"] = text(rest[-1])
        elif m and rest:
            if re.search(r"신\s*주\s*배\s*정\s*기\s*준\s*일", title):
                out["record_date"] = text(rest[-1])
            elif re.search(r"상\s*장\s*예\s*정\s*일", title):
                out["listing_date"] = text(rest[-1])
            elif re.search(r"이\s*사\s*회\s*결\s*의\s*일", title):
                out["board_date"] = text(rest[-1])
        if m and re.match(r"(증\s*권\s*신\s*고\s*서|기\s*타\s*투\s*자)", title):
            break
    out["funds_won"] = _sum(funds)
    return out


def paid_doc_row(row: dict, lines: list[str] | None, error: str | None = None) -> dict:
    """'API 응답 없음' 행을 원문 값으로 채운 행. 주식 수·액면가·증자 전 주식 수를 못 읽으면 '확인 필요'."""
    if error or not lines:
        return {**row, "check_result": f"원문 못 받음{': ' + error if error else ''}"}
    f = paid_fields(lines)
    ok = (f["shares_common"] is not None or f["shares_pref"] is not None) and f["par_won"] is not None \
        and (f["before_common"] is not None)
    return {**row, **f, "version": "원문 최종본", "source": "DART 원문",
            "check_result": "원문 읽음 (API에 없는 공시)" if ok else "원문 읽었으나 빈칸 있음 (확인 필요)"}


# --- 분할·병합 원문 읽기 -----------------------------------------------------

_DATE_FIELDS = [  # (줄 첫 칸 정규식, 열)
    (r"주\s*주\s*총\s*회", "agm_date"),
    (r"효\s*력\s*발\s*생\s*일", "effective_date"),
    (r"상\s*장\s*예\s*정\s*일", "listing_date"),
    (r"이\s*사\s*회\s*결\s*의\s*일", "board_date"),
    (r"(분\s*할|병\s*합)\s*(의\s*)?목\s*적", "purpose"),
]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|") if c.strip()]


def _nums(cells: list[str]) -> list[Decimal | None]:
    return [num(c) for c in cells]


def split_fields(lines: list[str]) -> dict:
    """분할·병합 결정 본문 → 값. 정정공시는 정정 내역표 뒤의 본문(마지막 '1. 주식분할 내용')부터 읽는다."""
    out = {"par_before_won": None, "par_after_won": None, "shares_before_common": None, "shares_after_common": None,
           "shares_before_pref": None, "shares_after_pref": None, "agm_date": None, "effective_date": None,
           "halt_start": None, "halt_end": None, "listing_date": None, "board_date": None, "purpose": None}
    starts = [i for i, ln in enumerate(lines) if re.match(r"1\.\s*주\s*식\s*(분\s*할|병\s*합)\s*(의\s*)?내\s*용", ln)]
    if not starts:
        return out
    in_halt = False  # '매매거래정지기간 | 시작일 | …' 다음 줄 '종료일 | …'
    for ln in lines[starts[-1]:]:
        cells = _cells(ln)
        if not cells:
            continue
        if re.match(r"※|5\.\s*기\s*타", cells[0]):
            break
        label = " ".join(cells[:-1])
        if re.match(r"1\s*주\s*당\s*가\s*액", cells[0]):
            out["par_before_won"], out["par_after_won"] = (_nums(cells[1:3]) + [None, None])[:2]
        elif (k := next((i for i, c in enumerate(cells) if re.match(r"(보\s*통|종\s*류)\s*주\s*식", c)), None)) is not None:
            side = "common" if "보" in cells[k] else "pref"
            out[f"shares_before_{side}"], out[f"shares_after_{side}"] = (_nums(cells[k + 1:k + 3]) + [None, None])[:2]
        elif re.search(r"매\s*매\s*거\s*래\s*정\s*지", label):
            out["halt_start"] = text(cells[-1]) if re.search(r"시\s*작\s*일", label) else None
            in_halt = True
            continue
        elif in_halt and re.match(r"종\s*료\s*일", cells[0]):
            out["halt_end"] = text(cells[-1])
        else:
            for pat, col in _DATE_FIELDS:
                if len(cells) > 1 and re.search(pat, label):
                    out[col] = text(cells[-1])
                    break
        in_halt = False
    return out


def check_split(kind: str, f: dict) -> tuple[str, str]:
    """액면가 비율과 보통주 수 비율이 맞는지. (검산 결과, 상태)."""
    pb, pa, sb, sa = f["par_before_won"], f["par_after_won"], f["shares_before_common"], f["shares_after_common"]
    if None in (pb, pa, sb, sa) or not pa or not pb:
        return "검산 못 함 (빈칸)", "확인 필요"
    if kind == "주식분할":
        r = pb / pa
        ok = pb > pa and sa == sb * r
        msg = f"액면 {pb:,}→{pa:,}원 ({r:g}배 분할), 주식 {sb:,} × {r:g} = {sb * r:,}"
    else:
        r = pa / pb
        ok = pa > pb and abs(sa - sb / r) <= max(Decimal(1), sb / r * Decimal("0.001"))  # 병합은 단주 처리로 조금 다를 수 있음
        msg = f"액면 {pb:,}→{pa:,}원 ({r:g}주→1주 병합), 주식 {sb:,} ÷ {r:g} ≈ {sb / r:,.0f}"
    return (f"일치: {msg}", "읽음") if ok else (f"안 맞음: {msg}, 원문 변경 후 {sa:,}", "확인 필요")


def split_row(filing: dict, kind: str, lines: list[str] | None, error: str | None = None) -> dict:
    """공시 목록 1행 + 원문 줄 → raw.dart_split_merge 행."""
    rc = filing["rcept_no"]
    f = split_fields(lines or [])
    if error or not lines:
        check, status = f"원문 못 받음{': ' + error if error else ''}", "원문 못 받음"
    else:
        check, status = check_split(kind, f)
    return {"rcept_no": rc, "kind": kind, "corp_code": filing["corp_code"], "corp_name": filing.get("corp_name"),
            "rcept_dt": rcept_date(rc), "report_nm": filing.get("report_nm"),
            "is_correction": is_correction(filing.get("report_nm")), **f,
            "check_result": check, "status": status, "link": link(rc), "source": "DART 원문"}


def list_row(r: dict, pblntf_ty: str) -> dict:
    dt = r.get("rcept_dt") or ""
    return {"rcept_no": r["rcept_no"], "corp_code": r["corp_code"], "corp_name": r.get("corp_name"),
            "stock_code": text(r.get("stock_code")), "corp_cls": r.get("corp_cls"), "pblntf_ty": pblntf_ty,
            "report_nm": (r.get("report_nm") or "").strip(), "flr_nm": r.get("flr_nm"),
            "rcept_dt": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else None, "rm": text(r.get("rm")),
            "source": "OpenDART list.json"}
