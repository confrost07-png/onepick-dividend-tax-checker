"""DART 공시 원문 읽기: 받기(캐시) → 목차 → 표를 줄로 → 재무제표 한 장 읽기 → 검산.

원문은 dart.fss.or.kr 공개 화면을 그대로 받는다(API 키 없음). 받은 파일은 data/raw/dart_cache/에 두고 다시 받지 않는다.
숫자를 읽은 뒤에는 같은 표 안의 합계로 검산해, 맞는 줄을 읽었는지 확인한다 (check_* 함수).
"""
import hashlib
import html
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

CACHE = Path(__file__).resolve().parents[2] / "data" / "raw" / "dart_cache"
BASE = "https://dart.fss.or.kr"

# --- 받기 -----------------------------------------------------------------


def _decode(raw: bytes) -> str:
    head = raw[:3000].decode("ascii", "ignore").lower()
    return raw.decode("cp949" if ("euc-kr" in head or "ks_c_5601" in head) else "utf-8", "replace")


RETRY_WAITS = (2, 30, 120, 300, 600)  # DART가 요청을 잠시 거절하면(빈 응답) 점점 길게 쉬었다 다시 받음


def get(url: str, pause: float = 0.6) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if path.exists():
        return _decode(path.read_bytes())
    if os.environ.get("DART_OFFLINE"):  # 받아 둔 원문만 쓰기 (DART가 막혔을 때)
        raise RuntimeError(f"캐시에 없음: {url}")
    for wait in RETRY_WAITS + (None,):
        r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            path.write_bytes(r.stdout)
            time.sleep(pause)
            return _decode(r.stdout)
        if wait is None:
            break
        time.sleep(wait)
    raise RuntimeError(f"원문을 받지 못함: {url}")


def get_bytes(url: str, pause: float = 0.6) -> bytes:
    """파일(PDF 등)을 바이트로 받는다. get과 같은 캐시·재시도."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if path.exists():
        return path.read_bytes()
    if os.environ.get("DART_OFFLINE"):
        raise RuntimeError(f"캐시에 없음: {url}")
    for wait in RETRY_WAITS + (None,):
        r = subprocess.run(["curl", "-s", "-L", "-m", "120", "-A", "Mozilla/5.0", url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            path.write_bytes(r.stdout)
            time.sleep(pause)
            return r.stdout
        if wait is None:
            break
        time.sleep(wait)
    raise RuntimeError(f"파일을 받지 못함: {url}")


def table_lines(page: str) -> list[str]:
    """HTML → 줄 목록. 표는 한 행이 한 줄이고 칸은 ' | '로 나뉜다."""
    x = re.sub(r"\s+", " ", page)
    x = re.sub(r"(?i)</t[dh]>", " | ", x)
    x = re.sub(r"(?i)</tr>|</table>|<table[^>]*>", "\x00", x)
    x = html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ")
    return [re.sub(r" +", " ", ln).strip() for ln in x.split("\x00") if ln.strip()]


@dataclass
class Node:
    text: str
    rcp_no: str
    dcm_no: str
    ele_id: str
    offset: str
    length: str
    dtd: str

    @property
    def url(self) -> str:
        return (f"{BASE}/report/viewer.do?rcpNo={self.rcp_no}&dcmNo={self.dcm_no}&eleId={self.ele_id}"
                f"&offset={self.offset}&length={self.length}&dtd={self.dtd}")


_NODE = re.compile(
    r"node\d\['text'\] = \"([^\"]*)\";.*?node\d\['rcpNo'\] = \"(\d+)\";\s*node\d\['dcmNo'\] = \"(\d+)\";"
    r"\s*node\d\['eleId'\] = \"(\d+)\";\s*node\d\['offset'\] = \"(\d+)\";\s*node\d\['length'\] = \"(\d+)\";"
    r"\s*node\d\['dtd'\] = \"([^\"]+)\"", re.S)


def filing(rcp_no: str) -> tuple[str, list[Node]]:
    """공시 제목(회사/보고서명/날짜)과 목차."""
    page = get(f"{BASE}/dsaf001/main.do?rcpNo={rcp_no}")
    title = re.search(r"<title>([^<]*)", page)
    return (title.group(1).strip() if title else ""), [Node(*m) for m in _NODE.findall(page)]


def section_lines(nodes: list[Node]) -> list[str]:
    out = []
    for n in nodes:
        out += table_lines(get(n.url))
    return out


def chapter_lines(nodes: list[Node], name: str) -> list[str]:
    """'4. 재무제표' 같은 목차 한 장의 줄. 위 목차 한 장에 4-1·4-2 … 내용이 다 들어 있어 한 번만 받는다."""
    ch = chapter(nodes, name)
    if not ch:
        return []
    lines = table_lines(get(ch[0].url))
    if len(ch) > 1 and not any(re.search(_HEAD["BS"], ln) for ln in lines):  # 위 목차에 내용이 없는 공시는 아래 목차를 읽음
        lines = section_lines(ch)
    return lines


def annual_reports(corp_code: str, start: str = "20180101", end: str = "20261231") -> list[tuple[str, str, str]]:
    """회사의 사업보고서 목록 [(접수번호, 보고서명, 기간 'YYYY.MM')]. 정정 포함, 최신순."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = f"annual:{corp_code}:{start}:{end}"
    path = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".bin")
    if not path.exists() and os.environ.get("DART_OFFLINE"):
        raise RuntimeError(f"캐시에 없음: {key}")
    if not path.exists():
        r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-X", "POST",
                            f"{BASE}/dsab007/detailSearch.ax", "-d",
                            f"textCrpCik={corp_code}&startDate={start}&endDate={end}&maxResults=100&currentPage=1"
                            "&maxLinks=10&sort=date&series=desc&publicType=A001"], capture_output=True)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(f"사업보고서 검색 실패: {corp_code}")
        path.write_bytes(r.stdout)
        time.sleep(0.4)
    s = _decode(path.read_bytes())
    out = []
    for m in re.finditer(r"rcpNo=(\d+)[^>]*>(.*?)</a>", s, re.S):
        title = html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(2))).strip()
        period = re.search(r"\((\d{4}\.\d{2})\)", title)
        if "사업보고서" in title and period:
            out.append((m.group(1), title, period.group(1)))
    return out


def audit_reports(corp_code: str, start: str = "20170101", end: str = "20261231") -> list[tuple[str, str, str, bool]]:
    """회사의 감사보고서·연결감사보고서 목록 [(접수번호, 보고서명, 기간 'YYYY.MM', 연결 여부)]. 최신순.
    상장 전처럼 사업보고서가 없는 해에도 외부감사 대상이면 감사보고서가 있다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    for code, consolidated in (("F002", True), ("F001", False)):
        key = f"audit:{code}:{corp_code}:{start}:{end}"
        path = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".bin")
        if not path.exists() and os.environ.get("DART_OFFLINE"):
            raise RuntimeError(f"캐시에 없음: {key}")
        if not path.exists():
            r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-X", "POST",
                                f"{BASE}/dsab007/detailSearch.ax", "-d",
                                f"textCrpCik={corp_code}&startDate={start}&endDate={end}&maxResults=100&currentPage=1"
                                f"&maxLinks=10&sort=date&series=desc&publicType={code}"], capture_output=True)
            if r.returncode != 0 or not r.stdout:
                raise RuntimeError(f"감사보고서 검색 실패: {corp_code}")
            path.write_bytes(r.stdout)
            time.sleep(0.6)
        s = _decode(path.read_bytes())
        for m in re.finditer(r"rcpNo=(\d+)[^>]*>(.*?)</a>", s, re.S):
            title = html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(2))).strip()
            period = re.search(r"\((\d{4}\.\d{2})\)", title)
            if "감사보고서" in title and period:
                out.append((m.group(1), title, period.group(1), consolidated))
    return out


def attachments(corp_code: str, start: str, end: str, filing_words: tuple[str, ...], attach_words: tuple[str, ...]
                ) -> list[tuple[str, str, str, bool]]:
    """start~end 공시 중 제목에 filing_words가 든 공시의 첨부파일 가운데 이름에 attach_words가 든 문서.
    → [(본문 주소, '공시명 첨부 문서명', 첨부 접수번호, 연결 여부)].
    본문 목차로는 안 열리고 첨부로만 열리는 문서(감사보고서제출 → 감사보고서, 분기·반기보고서 → 사업보고서)를 찾는다."""
    out, seen = [], set()
    for rcp, title in search(corp_code, start, end):
        if not any(w in title.replace(" ", "") for w in filing_words):
            continue
        page = get(f"{BASE}/dsaf001/main.do?rcpNo={rcp}")
        for m in re.finditer(r'<option[^>]*value="rcpNo=(\d+)&amp;dcmNo=(\d+)"[^>]*>(.*?)</option>', page, re.S):
            name = re.sub(r"\s|&nbsp;|[\d.]", "", html.unescape(m.group(3)))
            if (m.group(1), m.group(2)) in seen or not any(w in name for w in attach_words):
                continue
            seen.add((m.group(1), m.group(2)))
            url = f"{BASE}/report/viewer.do?rcpNo={m.group(1)}&dcmNo={m.group(2)}&eleId=0&offset=0&length=0&dtd=HTML"
            out.append((url, f"{title} 첨부 {name}", m.group(1), name.startswith("연결")))
    return out


def audit_attachments(corp_code: str, year: int) -> list[tuple[str, str, str, bool]]:
    """year 사업연도 감사보고서: '감사보고서제출' 공시(다음 해 1~6월)의 첨부 감사보고서·연결감사보고서."""
    return attachments(corp_code, f"{year + 1}0101", f"{year + 1}0630", ("감사보고서제출",), ("감사보고서",))


def report_attachments(corp_code: str, year: int) -> list[tuple[str, str, str, bool]]:
    """year 사업연도 재무가 든 문서: 다음 해 분기·반기보고서에 첨부된 사업보고서·감사보고서."""
    return attachments(corp_code, f"{year + 1}0101", f"{year + 1}1231", ("분기보고서", "반기보고서"), ("사업보고서", "감사보고서"))


def audit_chapter(nodes: list[Node], consolidated: bool) -> list[Node]:
    """감사보고서 목차의 '(첨부)재무제표' 또는 '(첨부)연결재무제표' (사업보고서처럼 번호 붙은 장이 없음)."""
    for n in nodes:
        t = re.sub(r"\s", "", n.text)
        if "재무제표" in t and "주석" not in t and "감사" not in t and ("연결" in t) == consolidated:
            return [n]
    return []


def chapter(nodes: list[Node], name: str) -> list[Node]:
    """'4. 재무제표'처럼 번호 붙은 목차와 그 아래 4-1, 4-2 … (다음 번호 목차 전까지)."""
    start = next((i for i, n in enumerate(nodes) if re.fullmatch(rf"\d+\.\s*{name}", n.text.strip())), None)
    if start is None:
        return []
    out = [nodes[start]]
    for n in nodes[start + 1:]:
        if re.match(r"\d+\.\s", n.text.strip()):
            break
        out.append(n)
    return out


# --- 표 읽기 ---------------------------------------------------------------

_HEAD = {
    "BS": r"재\s*무\s*상\s*태\s*표",
    "IS": r"(포\s*괄\s*)?손\s*익\s*계\s*산\s*서",
    "CF": r"현\s*금\s*흐\s*름\s*표",
}
_DATE = re.compile(r"(\d{4})\s*[년.]\s*\d{1,2}\s*[월.]\s*\d{1,2}\s*일?\s*(?:현재|까지)")
_UNIT = re.compile(r"단위\s*[:：]?\s*([^)|]*)")
_NUM = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})+\)?$|^\(?-?\d+\)?$")
_NOTE = re.compile(r"^\(?주\s*[\d,\s]+\)?$|^\d{1,2}(?:\s*,\s*\d{1,2})*$")


def cell_value(cell: str, notes: bool = False):
    """칸 글자 → 숫자. '-'는 0, 빈칸은 None. notes=True(재무제표)면 1~2자리 주석 번호도 None."""
    c = cell.strip().replace(" ", "")
    if c in ("-", "－", "0"):
        return 0.0
    if not c or not _NUM.match(c) or (notes and _NOTE.match(c)):
        return None
    neg = c.startswith("(") or c.startswith("-")
    return -float(c.strip("()-").replace(",", "")) if neg else float(c.strip("()").replace(",", ""))


@dataclass
class Statement:
    kind: str
    consolidated: bool
    years: list[int]
    unit: int
    entity: str
    rows: list[tuple[str, list[float]]] = field(default_factory=list)
    currency: str = "KRW"

    def value(self, label: str, year: int, before: str | None = None):
        """label(정규식)과 맞는 첫 행의 year 열 값(원 단위). before가 있으면 그 행보다 앞에서만 찾는다."""
        if year not in self.years:
            return None
        for name, nums in self.rows:
            if before and re.search(before, name):
                return None
            if re.search(label, name) and len(nums) > self.years.index(year):
                return nums[self.years.index(year)] * self.unit
        return None


def statements(lines: list[str], kind: str) -> list[Statement]:
    """lines 안의 kind 표(BS·IS·CF)를 모두 읽는다. 연결·별도는 제목으로 구분한다."""
    out = []
    starts = [i for i, ln in enumerate(lines) if re.fullmatch(rf"[\d\-.\s]*(연\s*결\s*)?{_HEAD[kind]}[\s|]*", ln)]
    for k, i in enumerate(starts):
        if k + 1 < len(starts) and starts[k + 1] - i <= 3:  # '4-1. 재무상태표' 바로 아래 같은 표 제목
            continue
        head = " ".join(lines[i:i + 10])
        years = [int(y) for y in _DATE.findall(head)]
        if not years:
            continue
        unit, currency = unit_of(head)
        ent = re.search(r"\|?\s*((?:주식회사|\(주\)|㈜)\s*[^|(]+?|[^|]+?\s*주식회사)\s*\|", head)
        st = Statement(kind, bool(re.search(r"연\s*결", lines[i])), years, unit,
                       ent.group(1).strip() if ent else "", currency=currency)
        for ln in lines[i + 1:i + 700]:
            if re.fullmatch(rf"[\d\-.\s]*(연\s*결\s*)?({_HEAD['BS']}|{_HEAD['IS']}|{_HEAD['CF']}|자\s*본\s*변\s*동\s*표)[\s|]*", ln):
                break
            cells = [c for c in ln.split("|")]
            label = cells[0].strip()
            if not label or re.match(r"^제\s*\d+", label):
                continue
            nums = [v for v in (cell_value(c, notes=True) for c in cells[1:]) if v is not None]
            if nums:
                st.rows.append((label, nums))
        out.append(st)
    return out


def unit_of(head: str) -> tuple[int, str]:
    """표 머리 '(단위 : 백만원)' → (원 단위 배수, 통화). '(단위 : 천, USD)'처럼 외화면 통화가 USD."""
    m = _UNIT.search(head)
    t = m.group(1) if m else "원"
    currency = "USD" if re.search(r"USD|달러|\$", t) else "EUR" if re.search(r"EUR|유로", t) else \
        "JPY" if re.search(r"JPY|엔", t) else "CNY" if re.search(r"CNY|위안", t) else "KRW"
    scale = 1_000_000 if "백만" in t else 1_000 if "천" in t else 1
    return scale, currency


def pick(sts: list[Statement], consolidated: bool) -> Statement | None:
    """연결/별도가 맞는 표. 원화 표가 있으면 원화 표를 먼저 (USD 기준 재무정보를 함께 싣는 회사)."""
    same = [s for s in sts if s.consolidated == consolidated]
    return next((s for s in same if s.currency == "KRW"), same[0] if same else None)


def net_income_total(st: Statement, year: int) -> float | None:
    """당기순이익 전체(지배+비지배). 계속·중단영업, 법인세차감전, 지배·비지배 귀속 행은 뺀다."""
    if year not in st.years:
        return None
    k = st.years.index(year)
    for name, nums in st.rows:
        if (re.search(L_NI, name) and not re.search(r"계\s*속|중\s*단|차\s*감\s*전|법\s*인\s*세", name)
                and not re.search(L_OWNER, name) and not re.search(L_NCI, name) and len(nums) > k):
            return nums[k] * st.unit
    return None


# --- 검산 -----------------------------------------------------------------

_P = r"^[^가-힣]*"  # 앞의 번호·기호(Ⅱ., 1., (1) 등)는 건너뜀
L_ASSETS = _P + r"(자\s*산\s*총\s*계|총\s*자\s*산)"
L_LIAB = _P + r"(부\s*채\s*총\s*계|총\s*부\s*채)"
L_EQUITY = _P + r"(자\s*본\s*총\s*계|총\s*자\s*본)"
L_LIAB_EQ = _P + r"(부\s*채\s*(와|및)\s*자\s*본\s*총\s*계|자\s*본\s*(과|및)\s*부\s*채\s*총\s*계)"
L_NI = r"(당\s*기|분\s*기|반\s*기)\s*(의\s*)?순\s*(이\s*익|손\s*실|손\s*익)"  # 사업보고서에 '분기순이익'으로 잘못 적힌 경우도
L_OWNER = r"^(?!.*비\s*지\s*배).*지\s*배\s*(기\s*업|회\s*사|주\s*주)?.*(소\s*유\s*주|지\s*분|순\s*(이\s*익|손\s*익|손\s*실))"
L_NCI = r"비\s*지\s*배"
L_DIV_PAID = r"^(?!.*(수\s*령|수\s*취|종\s*속)).*배\s*당\s*(금\s*)?의?\s*지\s*급"


def near(a, b, unit: int = 1) -> bool:
    return a is not None and b is not None and abs(a - b) <= unit


def check_balance(bs: Statement, year: int) -> tuple[bool, str]:
    """부채총계 + 자본총계 = 부채와자본총계 (= 자산총계)."""
    liab, eq = bs.value(L_LIAB, year), bs.value(L_EQUITY, year)
    total = bs.value(L_LIAB_EQ, year) or bs.value(L_ASSETS, year)
    ok = liab is not None and eq is not None and near(liab + eq, total, bs.unit)
    return ok, f"부채 {liab:,.0f} + 자본 {eq:,.0f} = {total:,.0f}" if ok else f"검산 안 맞음 (부채 {liab}, 자본 {eq}, 합계 {total})"


def owner_net_income(st: Statement, year: int) -> tuple[float | None, str]:
    """연결: 당기순이익 중 지배기업 소유주 몫. 표 순서에 기대지 않고, 지배 행과 바로 뒤 비지배 행의 합이
    당기순이익과 같은 쌍을 고른다 (총포괄손익 귀속 쌍은 합이 총포괄손익이라 걸러진다)."""
    if year not in st.years:
        return None, "당기순이익 행 없음"
    k = st.years.index(year)
    val = lambda nums: nums[k] * st.unit if len(nums) > k else None  # noqa: E731
    nis = [val(n) for name, n in st.rows  # 계속·중단영업, 법인세차감전 행은 당기순이익이 아님
           if re.search(L_NI, name) and not re.search(r"계\s*속|중\s*단|차\s*감\s*전|법\s*인\s*세", name)
           and not re.search(L_OWNER, name) and not re.search(L_NCI, name) and val(n) is not None]
    ni = nis[0] if nis else None
    if not st.consolidated:
        return ni, "별도 당기순이익"
    if ni is None:
        return None, "당기순이익 행 없음"
    if not any(re.search(L_OWNER, nm) or re.search(L_NCI, nm) for nm, _ in st.rows):
        return ni, f"귀속(지배·비지배) 행 없는 표 → 당기순이익 {ni:,.0f} 전체를 지배주주 몫으로 봄"
    tried = []
    for i, (name, nums) in enumerate(st.rows):
        if not re.search(L_OWNER, name) or val(nums) is None:
            continue
        owner = val(nums)
        nxt = None
        for nm2, n2 in st.rows[i + 1:i + 6]:  # 다음 지배 행 전까지에서 비지배 행
            if re.search(L_OWNER, nm2):
                break
            if re.search(L_NCI, nm2) and val(n2) is not None:
                nxt = val(n2)
                break
        hit = next((x for x in nis if near(owner + (nxt or 0), x, st.unit)), None)
        if hit is not None:
            return owner, (f"지배 {owner:,.0f} + 비지배 {nxt:,.0f} = 당기순이익 {hit:,.0f}" if nxt is not None
                           else f"지배 {owner:,.0f} = 당기순이익 {hit:,.0f} (비지배 행 없음)")
        tried.append(f"{owner:,.0f}+{nxt:,.0f}" if nxt is not None else f"{owner:,.0f}")
    if not tried:
        return None, "지배기업 소유주 행 없음"
    return None, f"당기순이익 {ni:,.0f}과 합이 맞는 지배·비지배 쌍 없음 (본 쌍: {', '.join(tried)})"


# --- 공시 검색 ---------------------------------------------------------------


def search(corp_code: str, start: str, end: str) -> list[tuple[str, str]]:
    """회사 corp_code의 start~end(YYYYMMDD) 공시 목록 [(접수번호, 보고서명)]. 최신순."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = f"search:{corp_code}:{start}:{end}"
    path = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".bin")
    if not path.exists() and os.environ.get("DART_OFFLINE"):
        raise RuntimeError(f"캐시에 없음: {key}")
    if not path.exists():
        r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-X", "POST",
                            f"{BASE}/dsab007/detailSearch.ax", "-d",
                            f"textCrpCik={corp_code}&startDate={start}&endDate={end}&maxResults=100"
                            "&currentPage=1&maxLinks=10&sort=date&series=desc"], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"검색 실패: {key}")
        path.write_bytes(r.stdout)
        time.sleep(0.4)
    s = _decode(path.read_bytes())
    return [(m.group(1), html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(2))).strip())
            for m in re.finditer(r"rcpNo=(\d+)[^>]*>(.*?)</a>", s, re.S)]


def body_lines(rcp_no: str) -> list[str]:
    """목차 없는 한 장짜리 공시(배당 결정 등)의 본문 줄."""
    page = get(f"{BASE}/dsaf001/main.do?rcpNo={rcp_no}")
    m = re.search(r"viewDoc\(\"(\d+)\", \"(\d+)\", \"(\d+)\", \"(\d+)\", \"(\d+)\", \"([^\"]+)\"", page)
    if not m:
        return []
    return table_lines(get(Node("", *m.groups()).url))
