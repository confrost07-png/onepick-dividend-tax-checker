"""4조참치 협조 데이터 전부 → 우리 전수 검산표 형식 엑셀 (대조군 또는 겹치는 회사).

실행: .venv/bin/python -m scripts.export_partner_workbook [--src 원본 폴더] [--out-dir 폴더] [--url postgresql://localhost/onepick]
--group 대조군(기본): 4조 4개 업종 회사 중 우리 638사(core.core_company)에 없는 회사. --group 겹침: 우리 638사와 겹치는 회사
(분석에는 우리 값이 더 정확하므로 우리 값을 쓰고, 겹침 파일은 4조 자료 참고·대조용). 사업연도 2017~2025. 형식은 source/scripts/export_review_workbook.py와 같다
(맨 끝 노란 칸만 검토자가 채움, 연두색은 엑셀 수식, 열 설명은 '항목_설명'). 행이 많아 source/scripts/stream_book.py로 쓴다.
만드는 파일 (같은 폴더, 받은 파일 링크는 그 폴더의 원본/ 기준)
- 검산표: 회사·사업보고서·재무·배당 표·배당금 지급·배당 결정 공시·주식 총수·최대주주·4조 위험 사건·감사의견·주석 목록
- 재무제표전체: OpenDART 재무제표 모든 줄 · 공시목록: 정기·주요사항·거래소 공시 전부
- 사업보고서표_N: 사업보고서 원문 XML의 DART 정형 표(TABLE-GROUP) 전부, 표 종류마다 시트 하나 (source/core/dart_xml.py)

값이 없을 때는 두 가지로 나눈다.
- 원문에 없음: 그 해 사업보고서가 없거나, 받아 둔 원문에 그 항목 글자가 아예 없음
- 실재하지만 불러올 수 없음: DART에 원문은 있으나 이 자료로 꺼내지 못함 (원문 못 받음 · API 표에 없음 · 본문 미수집)
"""
import argparse
import collections
import csv
import json
import os
import re
import zipfile
from datetime import date
from pathlib import Path

from core import dart_xml as dx
from core import db
from core.share_total import share_class
from scripts import stream_book as sb
from scripts.export_review_workbook import DIV_ITEMS, Col, link, stock_kind

ROOT = Path(__file__).resolve().parents[2]
PARTNER = ROOT / "data" / "partner" / "4조참치_20261030"
SRC = PARTNER / "원본"
YEARS = range(2017, 2026)
INDUSTRIES = {"real_estate_rental": "부동산임대업", "construction": "건설업",
              "wholesale_retail": "도소매업", "manufacturing": "제조업"}
MARKET = {"Y": "유가증권", "K": "코스닥", "N": "코넥스", "E": "기타(비상장·상장폐지)"}
COMPANY_VIEW = "https://dart.fss.or.kr/dsae001/selectPopup.ax?selectKey="
COMPANY_FIELDS = [  # (기업개황 키, 열 이름, 너비, 뜻)
    ("corp_name", "정식 회사명", 18, "기업개황의 정식 이름"), ("corp_name_eng", "영문 회사명", 18, "영문 이름"),
    ("ceo_nm", "대표자", 12, "대표자 이름"), ("jurir_no", "법인등록번호", 14, "법인등록번호"),
    ("bizr_no", "사업자등록번호", 12, "사업자등록번호"), ("adres", "주소", 30, "본점 주소"),
    ("hm_url", "홈페이지", 18, "홈페이지 주소"), ("ir_url", "IR 홈페이지", 14, "IR 홈페이지 주소"),
    ("phn_no", "전화번호", 13, "대표 전화"), ("fax_no", "팩스번호", 13, "팩스"),
    ("induty_code", "업종코드(기업개황)", 9, "OpenDART 기업개황 업종코드"), ("est_dt", "설립일", 9, "설립일 (YYYYMMDD)")]

HAS = "값 있음"
NO_SOURCE = "원문에 없음"
CANNOT = "실재하지만 불러올 수 없음"
GOT = "받음"

# (열 이름, 연결 표준계정, 별도 표준계정, 계정명에 들어가는 글자, 원문에서 찾을 글자)
FIN_ITEMS = [
    ("지배주주 순이익", ("ifrs-full_ProfitLossAttributableToOwnersOfParent",), ("ifrs-full_ProfitLoss",),
     ("지배기업소유주", "지배기업의소유주", "지배회사소유주", "지배기업소유지분", "지배주주지분", "지배기업지분"),
     ("당기순이익", "당기순손익", "당기순손실")),
    ("부채총계", ("ifrs-full_Liabilities",), ("ifrs-full_Liabilities",), ("부채총계",), ("부채총계",)),
    ("자본총계", ("ifrs-full_Equity",), ("ifrs-full_Equity",), ("자본총계",), ("자본총계",)),
    ("자산총계", ("ifrs-full_Assets",), ("ifrs-full_Assets",), ("자산총계",), ("자산총계",)),
]
OFS_NI_NAMES = ("당기순이익", "당기순손익", "당기순이익(손실)", "당기순손실")
DIV_ID = "ifrs-full_DividendsPaidClassifiedAsFinancingActivities"
DIV_WORDS = ("배당금지급", "배당금의지급", "배당금지급액")  # 원문에서 찾을 글자 (띄어쓰기 지운 뒤)
# 원문 표에서 '배당금(의) 지급' 바로 뒤에 금액이 붙은 줄 (현금흐름표·자본변동표). 글자만 있고 금액이 없으면 회계정책 문장 등
DIV_AMOUNT = re.compile(r"배당금의?지급(?:액)?[^0-9가-힣]{0,12}\(?-?\d{1,3}(?:,\d{3})+")
SHEET_OF = {"IS": "손익", "CIS": "손익", "BS": "재무상태", "CF": "현금흐름"}
COLUMN = {"thstrm_amount": "당기", "frmtrm_amount": "전기", "bfefrmtrm_amount": "전전기"}


# --- 읽기 -------------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def amount(v) -> float | None:
    s = str(v or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def decode_xml(raw: bytes) -> str:
    """DART 원문 XML. 머리에 utf-8이라 적혀 있어도 실제로는 cp949인 파일이 섞여 있다."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", "replace")


def document_text(zip_path: Path, rcept_no: str) -> str | None:
    """받아 둔 사업보고서 zip의 본문 XML(감사보고서 첨부 제외)을 태그·띄어쓰기 없이. 파일이 없으면 None."""
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        main = f"{rcept_no}.xml" if f"{rcept_no}.xml" in names else names[0]
        return squash(re.sub(r"<[^>]+>", " ", decode_xml(z.read(main))))


def fs_lines(fnltt_dir: Path, year: int) -> tuple[str, list[dict]]:
    """그 사업연도 사업보고서 재무제표: 연결이 있으면 연결, 없으면 별도 (4조 수집 규칙과 같음)."""
    for fs in ("CFS", "OFS"):
        p = fnltt_dir / f"{year}_11011_{fs}.json"
        if p.exists():
            lines = json.loads(p.read_text(encoding="utf-8")).get("list") or []
            if lines:
                return fs, lines
    return "", []


def account_id(x: dict) -> str:
    """옛 IFRS 분류체계 코드(ifrs_…)를 지금 코드(ifrs-full_…)로 맞춘다."""
    a = x.get("account_id") or ""
    return "ifrs-full_" + a[5:] if a.startswith("ifrs_") else a


def find_line(lines: list[dict], ids, names, sheets, skip=()) -> dict | None:
    """표준계정 코드로 먼저 찾고, 없으면 계정명 글자로 찾는다 (띄어쓰기 무시). skip 글자가 든 계정명은 뺀다."""
    in_sheet = [x for x in lines if x.get("sj_div") in sheets
                and not any(w in squash(x.get("account_nm", "")) for w in skip)]
    return (next((x for x in in_sheet if account_id(x) in ids), None)
            or next((x for x in in_sheet if any(w in squash(x.get("account_nm", "")) for w in names)
                     and "ComprehensiveIncome" not in account_id(x)), None))


SKIP = {"부채총계": ("자본",), "자본총계": ("부채",), "자산총계": ("부채", "자본")}  # '부채와자본총계' 같은 합계 줄을 피함


NI_SKIP = ("계속", "중단")  # 계속·중단영업으로 나눈 줄은 당기순이익 전체가 아님 ('지배기업 소유주(계속)' 같은 이름 포함)


def fin_item_line(lines: list[dict], fs: str, item: tuple) -> dict | None:
    """별도만 있는 회사는 지배주주 구분이 없으므로 당기순이익을 쓴다."""
    label, cfs_ids, ofs_ids, names, _ = item
    if label != "지배주주 순이익":
        return find_line(lines, cfs_ids, names, ("BS",), SKIP[label])
    if fs == "OFS":
        return find_line(lines, ofs_ids, OFS_NI_NAMES, ("IS", "CIS"), NI_SKIP)
    return find_line(lines, cfs_ids, names, ("IS", "CIS"), NI_SKIP)


def owner_profit(lines: list[dict], col: str) -> tuple[float, str] | None:
    """연결 지배주주 순이익 고르기. (값, 사유) · 못 고르면 None.
    회사가 표준 코드를 잘못 붙이는 일이 많다: 총포괄손익의 '지배기업 소유주지분'에 당기순이익 코드를 붙이거나,
    두 귀속 줄을 같은 이름으로 적거나, 계속영업 몫만 적는다. 그래서 순서대로 본다.
    1) 지배 + 비지배 = 당기순이익 검산이 맞는 줄  2) 표 안 위치가 당기순이익 귀속 쪽인 줄 (바로 앞 합계 줄이 당기순이익)
    3) 당기순이익 − 비지배  4) 지배·비지배 줄이 모두 없으면 당기순이익 전체"""
    inc = [x for x in lines if x.get("sj_div") in ("IS", "CIS") and amount(x.get(col)) is not None]
    if any(x.get("currency") == "KRW" for x in inc):  # 두산밥캣처럼 원화·달러 표를 함께 내는 회사: 원화 줄만
        inc = [x for x in inc if x.get("currency") in ("KRW", None, "")]
    nm = lambda x: squash(x.get("account_nm", ""))  # noqa: E731
    order = lambda x: int(x["ord"]) if str(x.get("ord", "")).isdigit() else 0  # noqa: E731
    total_line = find_line(inc, ("ifrs-full_ProfitLoss",), OFS_NI_NAMES, ("IS", "CIS"), NI_SKIP + ("지배",))
    if total_line is None:
        return None
    tv = amount(total_line.get(col))
    comp_lines = [x for x in inc if account_id(x) == "ifrs-full_ComprehensiveIncome"]
    plain = lambda x: not any(w in nm(x) for w in NI_SKIP + ("포괄",)) and "ComprehensiveIncome" not in account_id(x)  # noqa: E731
    cands = [x for x in inc if plain(x) and "비지배" not in nm(x)
             and (account_id(x) == "ifrs-full_ProfitLossAttributableToOwnersOfParent" or "지배" in nm(x))]
    ncis = [x for x in inc if plain(x) and (account_id(x) == "ifrs-full_ProfitLossAttributableToNoncontrollingInterests" or "비지배" in nm(x))]
    for x in cands:
        for n in [amount(y.get(col)) for y in ncis] or [0]:
            if abs(amount(x.get(col)) + n - tv) < 1:
                return amount(x.get(col)), f"{x['account_nm']} (지배 + 비지배 = 당기순이익 검산 맞음)"

    def profit_side(x):
        """바로 앞 합계 줄(당기순이익·총포괄손익 중 표에서 더 가까이 앞선 것)이 당기순이익이면 참."""
        before = [y for y in [total_line] + comp_lines if order(y) < order(x)]
        return bool(before) and max(before, key=order) is total_line

    comp_vals = {amount(y.get(col)) for y in comp_lines} - {tv}
    as_comp = lambda x: any(abs(amount(x.get(col)) - v) < 1 for v in comp_vals)  # noqa: E731  값이 총포괄손익과 같음 = 코드 잘못 붙임
    owner_id = "ifrs-full_ProfitLossAttributableToOwnersOfParent"
    side = [x for x in cands if (profit_side(x) or account_id(x) == owner_id) and not as_comp(x)]
    if side:
        x = next((y for y in side if account_id(y) == owner_id), side[0])
        return amount(x.get(col)), f"{x['account_nm']} (원문 그대로, 지배 + 비지배 = 당기순이익 검산 안 맞음 — 원문 확인 필요)"
    tagged = next((x for x in ncis if account_id(x) == "ifrs-full_ProfitLossAttributableToNoncontrollingInterests"), None)
    if tagged is not None and tv and abs(tv - amount(tagged.get(col))) >= 1:
        n = amount(tagged.get(col))
        return tv - n, f"당기순이익 '{total_line['account_nm']}' {tv:,.0f} − 비지배 '{tagged['account_nm']}' {n:,.0f} (지배 줄이 없거나 총포괄손익 쪽에만 있음)"
    if not ncis and cands:
        return tv, (f"지배 줄이 총포괄손익 쪽에만 있고 비지배 줄이 없어 당기순이익 전체 '{total_line['account_nm']}' {tv:,.0f}")
    return None


def split_profit(lines: list[dict], fs: str, col: str) -> tuple[float, str] | None:
    """지배 귀속 당기순이익 줄이 계속·중단영업으로 나뉘어 있을 때 (값, 사유).
    연결은 당기순이익 − 비지배지분 몫을 먼저 쓰고, 없으면 계속영업 + 중단영업을 더한다."""
    owner = fs == "CFS"
    if owner:
        total = find_line(lines, ("ifrs-full_ProfitLoss",), OFS_NI_NAMES, ("IS", "CIS"), NI_SKIP + ("지배",))
        nci = next((x for x in lines if x.get("sj_div") in ("IS", "CIS")
                    and account_id(x) == "ifrs-full_ProfitLossAttributableToNoncontrollingInterests"
                    and not any(w in squash(x.get("account_nm", "")) for w in NI_SKIP)), None)
        tv, nv = (amount(total.get(col)) if total else None), (amount(nci.get(col)) if nci else None)
        if tv is not None and nv is not None and tv and abs(tv - nv) < 1:
            return None  # 비지배 줄이 당기순이익 전체와 같음: 회사가 지배 줄에 비지배 코드를 붙였을 수 있어 빼지 않음
        if tv is not None and nv is not None:
            return tv - nv, f"당기순이익 '{total['account_nm']}' {tv:,.0f} − 비지배 '{nci['account_nm']}' {nv:,.0f} (지배 몫 줄이 없거나 계속·중단으로 나뉨)"
    ids = (("ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
            "ifrs-full_IncomeFromDiscontinuedOperationsAttributableToOwnersOfParent") if owner else
           ("ifrs-full_ProfitLossFromContinuingOperations", "ifrs-full_ProfitLossFromDiscontinuedOperations"))
    found = []
    for code, word in zip(ids, NI_SKIP):
        x = next((x for x in lines if x.get("sj_div") in ("IS", "CIS") and account_id(x) == code), None)
        if x is None:
            x = next((x for x in lines if x.get("sj_div") in ("IS", "CIS") and word in squash(x.get("account_nm", ""))
                      and ("지배" in squash(x.get("account_nm", ""))) == owner and "비지배" not in squash(x.get("account_nm", ""))
                      and "주당" not in x.get("account_nm", "")), None)
        found.append(x)
    cont, disc = found
    cv = amount(cont.get(col)) if cont else None
    if cv is None:
        return None
    dv = amount(disc.get(col)) if disc else None
    why = f"계속영업 '{cont['account_nm']}' {cv:,.0f}" + (f" + 중단영업 '{disc['account_nm']}' {dv:,.0f}" if dv is not None else " (중단영업 줄 없음)")
    return cv + (dv or 0), why + " — 당기순이익 줄이 없어 더함"


def profit_total(lines: list[dict]) -> float | None:
    """연결 손익계산서의 당기순이익 (지배 구분 줄이 없을 때 사유에 참고로 적음)."""
    x = find_line(lines, ("ifrs-full_ProfitLoss",), OFS_NI_NAMES, ("IS", "CIS"))
    return amount(x.get("thstrm_amount")) if x else None


def dividend_lines(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    """현금흐름표에서 회사가 주주에게 낸 배당(포함)과 비지배지분 배당(따로)."""
    paid, nci = [], []
    for x in lines:
        if x.get("sj_div") != "CF":
            continue
        nm = squash(x.get("account_nm", ""))
        if account_id(x) != DIV_ID and not ("배당" in nm and "지급" in nm):
            continue
        if any(w in nm for w in ("수취", "수입", "받은", "수령", "미지급")):  # 미지급배당금 증감은 지급이 아님
            continue
        (nci if "비지배" in nm else paid).append(x)
    return paid, nci


# --- 상태 -------------------------------------------------------------------------------


def missing_status(report: dict | None, api_has: bool, text: str | None, words, what: str,
                   amount_re: re.Pattern | None = None) -> tuple[str, str]:
    """값을 못 찾았을 때 (상태, 사유). report = 그 결산기 사업보고서(manifest 1행), text = 받은 원문(태그·띄어쓰기 없음).
    amount_re가 있으면 글자 뒤에 금액이 붙은 줄이 있어야 '실재'로 본다."""
    if report is None:
        return NO_SOURCE, "공시목록에 그 해 사업보고서 없음"
    if text is None:
        return CANNOT, f"사업보고서 원문을 못 받음 (DART 응답 {report.get('last_api_status') or '?'})"
    if not any(w in text for w in words):
        return NO_SOURCE, f"받은 원문에 '{words[0]}' 글자 없음"
    if amount_re is not None and not amount_re.search(text):
        return NO_SOURCE, f"받은 원문에 '{words[0]}' 글자는 있으나 금액이 붙은 줄 없음"
    where = "API에 그 해 재무제표 없음" if not api_has else f"API 재무제표에 {what} 계정 없음"
    found = "금액이 붙은 줄 있음" if amount_re is not None else "글자 있음"
    return CANNOT, f"{where}, 원문에는 '{words[0]}' {found} — 원문 확인 필요"


# --- 4조 자료 모으기 -------------------------------------------------------------------------


class Partner:
    """4조 원본 폴더에서 대상 회사(exclude를 뺀 회사)와 회사별 사업보고서·재무제표 위치를 한 번에 읽어 둔다."""

    def __init__(self, src: Path, exclude: set[str]):
        self.src = src
        cls = {r["corp_code"]: r for r in read_csv(src / "common" / "industry_classification.csv")}
        status = {r["corp_code"]: r for r in read_csv(src / "common" / "company_status.csv")}
        self.companies = []  # (업종 폴더, companies.csv 행)
        for folder in INDUSTRIES:
            for r in read_csv(src / folder / "lists" / "companies.csv"):
                if r["corp_code"] not in exclude:
                    self.companies.append((folder, r | {"_cls": cls.get(r["corp_code"], {}), "_status": status.get(r["corp_code"], {})}))
        self.companies.sort(key=lambda t: (t[1]["corp_name"], t[1]["corp_code"]))
        self.folder = {r["corp_code"]: f for f, r in self.companies}
        self.name = {r["corp_code"]: r["corp_name"] for _, r in self.companies}
        self.manifest = {}  # corp → [manifest 행]
        for folder in INDUSTRIES:
            for m in read_csv(src / folder / "verify" / "report_manifest.csv"):
                if m["corp_code"] in self.folder:
                    self.manifest.setdefault(m["corp_code"], []).append(m)
        self._text = {}

    def report(self, corp: str, year: int) -> dict | None:
        """그 결산기 사업보고서: 받은 최신 전체본 > 받은 최신본 > 못 받은 최신본."""
        rows = [m for m in self.manifest.get(corp, []) if m["period"][:4] == str(year)]
        if not rows:
            return None
        got = [m for m in rows if m["status"] == "수집완료"]
        latest = [m for m in got if m["is_latest_full"] == "Y"]
        return (latest or sorted(got, key=lambda m: m["rcept_no"]) or sorted(rows, key=lambda m: m["rcept_no"]))[-1]

    def zip_path(self, corp: str, rcept: str) -> Path:
        return self.src / self.folder[corp] / "raw" / "documents" / corp / f"{rcept}.zip"

    def local_link(self, corp: str, rcept: str) -> str | None:
        p = self.zip_path(corp, rcept)
        return p.relative_to(self.src.parent).as_posix() if rcept and p.exists() else None

    def text(self, corp: str, report: dict | None) -> str | None:
        """받은 원문 글자 (최근 64건만 기억: 회사·연도 순으로 돌므로 충분하고, 원문 1만여 건을 다 들고 있지 않음)."""
        if report is None or report["status"] != "수집완료":
            return None
        key = report["rcept_no"]
        if key not in self._text:
            if len(self._text) >= 64:
                self._text.pop(next(iter(self._text)))
            self._text[key] = document_text(self.zip_path(corp, key), key)
        return self._text[key]

    def latest_reports(self):
        """대상 회사·사업연도별 결산기 최신 사업보고서 (manifest 1행). 못 받은 것도 포함."""
        for folder, c in self.companies:
            for year in YEARS:
                rep = self.report(c["corp_code"], year)
                if rep is not None:
                    yield folder, c["corp_code"], year, rep

    def company_info(self, corp: str) -> dict:
        p = self.src / "common" / "company" / f"{corp}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def fnltt(self, corp: str) -> Path:
        return self.src / self.folder[corp] / "raw" / "fnltt" / corp

    def year_lines(self, corp: str, year: int) -> tuple[str, list[dict], str, str]:
        """(연결/별도, 재무제표 줄, 읽을 금액 열, 그 줄을 준 접수번호). 그 해 재무제표가 API에 없으면 다음 해·다다음 해 보고서의 비교기간 열."""
        d = self.fnltt(corp)
        for later, col in ((0, "thstrm_amount"), (1, "frmtrm_amount"), (2, "bfefrmtrm_amount")):
            fs, lines = fs_lines(d, year + later)
            if lines:
                return fs, lines, col, lines[0].get("rcept_no", "")
        return "", [], "thstrm_amount", ""


# --- 시트 ------------------------------------------------------------------------------


def base_cols(src_note: str) -> list[Col]:
    return [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", src_note),
            Col("사업연도", 8, "결산기 연도 (3월 결산이면 그 해 3월에 끝나는 회계연도)", "4조 fnltt 파일 이름 · report_manifest.period"),
            Col("4조 업종", 10, "4조가 배정한 업종", "4조 common/industry_classification.csv industry")]


def link_cols() -> list[Col]:
    return [Col("원천 열", 8, "값을 읽은 보고서 표의 열 (당기 / 다음 해 보고서의 전기 / 다다음 해 보고서의 전전기)", "4조 fnltt JSON 금액 열"),
            Col("접수번호", 15, "값을 준 사업보고서 접수번호", "4조 fnltt JSON rcept_no"),
            Col("원문", 10, "누르면 값을 준 사업보고서가 DART에서 열림", "접수번호로 만든 DART 주소", "", "link"),
            Col("사업보고서", 10, "누르면 그 사업연도 사업보고서(결산기 최신 전체본)가 DART에서 열림", "4조 verify/report_manifest.csv", "", "link"),
            Col("받은 파일", 10, "누르면 4조가 받아 둔 그 사업연도 사업보고서 원문 zip이 열림 (엑셀 파일 옆 원본/ 폴더 기준)",
                "4조 raw/documents/{corp_code}/{접수번호}.zip", "", "link")]


def status_note(label: str) -> str:
    return (f"{label} 값이 있는지: {HAS} · {NO_SOURCE}(그 해 사업보고서 없음, 받은 원문에 글자 없음) · "
            f"{CANNOT}(원문 못 받음, API 표에 없는데 원문에 글자 있음)")


def sheet_company(p: Partner):
    cols = [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호 (8자리)", "4조 lists/companies.csv corp_code"),
            Col("종목코드", 9, "KRX 보통주 종목코드 (6자리)", "4조 lists/companies.csv stock_code"),
            Col("시장", 12, "유가증권 · 코스닥 · 코넥스 · 기타(비상장·상장폐지)", "4조 companies.csv corp_cls (OpenDART 기업개황)"),
            Col("지금 상장", 7, "4조 확인 시점 상장 여부 (Y/N)", "4조 common/company_status.csv listed_now"),
            Col("상장폐지일", 11, "상장폐지된 날 (KIND)", "4조 common/company_status.csv delist_date"),
            Col("상장폐지 사유", 24, "KIND 상장폐지 사유", "4조 common/company_status.csv delist_reason"),
            Col("결산월", 6, "회계연도 끝나는 달", "4조 companies.csv acc_mt", "", "num"),
            Col("4조 업종", 10, "4조가 배정한 업종", "4조 industry_classification.csv industry"),
            Col("KSIC 코드", 8, "한국표준산업분류 코드", "4조 industry_classification.csv ksic_code"),
            Col("KSIC 이름", 22, "한국표준산업분류 이름", "4조 industry_classification.csv ksic_name"),
            Col("분류 방법", 12, "4조가 업종을 정한 방법 (KSIC자동 · 수동 등)", "4조 industry_classification.csv method"),
            Col("분류 사유", 26, "수동 배정 등의 근거", "4조 industry_classification.csv reason"),
            Col("사업보고서 결산기 수", 9, f"{YEARS.start}~{YEARS.stop - 1} 사업보고서가 있는 결산기 수", "4조 report_manifest.csv period", "", "num")]
    cols += [Col(name, w, meaning, f"4조 common/company/{{corp_code}}.json {key} (OpenDART 기업개황)")
             for key, name, w, meaning in COMPANY_FIELDS]
    cols += [
            Col("수식 검산", 12, "종목코드가 6자리이고 결산월이 1~12인지", "엑셀 수식", "", "formula"),
            Col("원문", 10, "누르면 DART 회사 개황이 열림", "dart.fss.or.kr/dsae001/selectPopup.ax?selectKey=corp_code", "", "link")]
    rows = []
    for folder, r in p.companies:
        st = r["_status"]
        periods = {m["period"] for m in p.manifest.get(r["corp_code"], []) if int(m["period"][:4]) in YEARS}
        rows.append({"회사명": r["corp_name"], "corp_code": r["corp_code"], "종목코드": r["stock_code"],
                     "시장": MARKET.get(r["corp_cls"], r["corp_cls"]), "지금 상장": st.get("listed_now", ""),
                     "상장폐지일": st.get("delist_date", ""), "상장폐지 사유": st.get("delist_reason", ""),
                     "결산월": amount(r["acc_mt"]), "4조 업종": INDUSTRIES[folder],
                     "KSIC 코드": r["ksic_code"], "KSIC 이름": r["ksic_name"], "분류 방법": r["method"], "분류 사유": r["reason"],
                     "사업보고서 결산기 수": len(periods), "원문": COMPANY_VIEW + r["corp_code"]}
                    | {name: p.company_info(r["corp_code"]).get(key, "") for key, name, _, _ in COMPANY_FIELDS})

    def check(L, i):
        return f'=IF(AND(LEN({L["종목코드"]}{i})=6,{L["결산월"]}{i}>=1,{L["결산월"]}{i}<=12),"정상","확인 필요")'

    return cols, rows, {"수식 검산": check}


def sheet_reports(p: Partner):
    cols = [Col("회사명", 16, "회사 이름", "4조 report_manifest.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", "4조 report_manifest.csv corp_code"),
            Col("결산기", 8, "보고서 기간 (YYYY.MM)", "4조 report_manifest.csv period"),
            Col("보고서명", 30, "공시 제목 (정정이면 [기재정정] 등)", "4조 report_manifest.csv report_nm"),
            Col("접수번호", 15, "DART 접수번호", "4조 report_manifest.csv rcept_no"),
            Col("접수일", 10, "공시 접수일", "4조 report_manifest.csv rcept_dt"),
            Col("버전", 9, "최초 · 기재정정 · 첨부정정 · 첨부추가", "4조 report_manifest.csv version"),
            Col("최초본", 6, "그 결산기 최초 보고서인지 (Y)", "4조 report_manifest.csv is_first"),
            Col("결산기 최신 전체본", 8, "그 결산기의 가장 최근 전체 보고서인지 (Y). 분석에는 이것만 쓰면 됨", "4조 report_manifest.csv is_latest_full"),
            Col("원문 상태", 18, f"{GOT} · {CANNOT}", "4조 report_manifest.csv status"),
            Col("사유", 28, "못 받은 이유", "4조 report_manifest.csv last_api_status",
                "014 = DART가 원문 파일을 주지 않음 (대부분 첨부서류만 고친 [첨부정정])"),
            Col("주석 섹션 수", 7, "4조가 원문에서 뽑은 재무제표 주석 섹션 수", "4조 report_manifest.csv notes_sections", "", "num"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
            Col("받은 파일", 10, "누르면 4조가 받아 둔 원문 zip이 열림", "4조 raw/documents/{corp_code}/{접수번호}.zip", "", "link")]
    rows = []
    for corp, ms in p.manifest.items():
        for m in ms:
            if int(m["period"][:4]) not in YEARS:
                continue
            got = m["status"] == "수집완료"
            reason = "" if got else (f"DART 응답 {m['last_api_status']}" +
                                     (" (원문 파일 미제공)" if m["last_api_status"] == "014" else "") + (f" · {m['zip_error']}" if m["zip_error"] else ""))
            rows.append({"회사명": p.name[corp], "corp_code": corp, "결산기": m["period"], "보고서명": m["report_nm"],
                         "접수번호": m["rcept_no"], "접수일": m["rcept_dt"], "버전": m["version"], "최초본": m["is_first"],
                         "결산기 최신 전체본": m["is_latest_full"], "원문 상태": GOT if got else CANNOT, "사유": reason,
                         "주석 섹션 수": amount(m["notes_sections"]), "원문": link(m["rcept_no"]),
                         "받은 파일": p.local_link(corp, m["rcept_no"]) if got else None})
    rows.sort(key=lambda r: (r["회사명"], r["corp_code"], r["결산기"], r["접수번호"]))
    return cols, rows, {}


def _year_row(p: Partner, folder: str, corp: str, year: int) -> tuple[dict, dict | None, str, list, str, str]:
    report = p.report(corp, year)
    fs, lines, col, rcept = p.year_lines(corp, year)
    own = report["rcept_no"] if report else ""
    r = {"회사명": p.name[corp], "corp_code": corp, "사업연도": year, "4조 업종": INDUSTRIES[folder],
         "재무 기준": {"CFS": "연결", "OFS": "별도"}.get(fs, ""),
         "원천 열": COLUMN[col] if lines else "", "접수번호": rcept, "원문": link(rcept),
         "사업보고서": link(own), "받은 파일": p.local_link(corp, own) if report and report["status"] == "수집완료" else None}
    return r, report, fs, lines, col, own


def sheet_fin(p: Partner):
    cols = base_cols("4조 fnltt 폴더 이름") + [
        Col("재무 기준", 8, "연결 또는 별도. 연결재무제표가 있으면 연결 (4조 수집 규칙)", "4조 fnltt 파일 이름의 CFS/OFS")]
    for label, *_ in FIN_ITEMS:
        meaning = ("지배기업 소유주 귀속 당기순이익 (별도만 있는 회사는 당기순이익)" if label == "지배주주 순이익" else label)
        cols += [Col(f"{label}(원)", 17, meaning, "4조 fnltt JSON (OpenDART 단일회사 전체 재무제표) 금액",
                     "표준계정 코드로 먼저 찾고, 없으면 계정명 글자로 찾음", "num"),
                 Col(f"{label} 상태", 14, status_note(label), "코드 판단 (source/scripts/export_partner_workbook.py missing_status)"),
                 Col(f"{label} 사유", 30, "상태의 근거", "코드 판단")]
    cols += [Col("수식 검산", 12, "부채총계 + 자본총계 = 자산총계", "엑셀 수식", "차이 1원 이하면 '일치', 하나라도 비면 '값 빈칸'", "formula")]
    cols += link_cols()
    rows = []
    for folder, c in p.companies:
        corp = c["corp_code"]
        for year in YEARS:
            r, report, fs, lines, col, _ = _year_row(p, folder, corp, year)
            for item in FIN_ITEMS:
                label, words = item[0], item[4]
                x = fin_item_line(lines, fs, item) if lines else None
                v = amount(x.get(col)) if x else None
                if label == "지배주주 순이익" and fs == "CFS" and lines:
                    owner = owner_profit(lines, col)
                    if owner is not None:
                        v, x = owner[0], {"sj_div": "CIS", "account_nm": owner[1]}
                split = split_profit(lines, fs, col) if label == "지배주주 순이익" and v is None and lines else None
                if v is not None:
                    st, why = HAS, f"{SHEET_OF.get(x['sj_div'], x['sj_div'])} '{x['account_nm']}'"
                elif split is not None:
                    v, (st, why) = split[0], (HAS, split[1])
                elif x is not None:
                    st, why = NO_SOURCE, f"계정 '{x['account_nm']}'은 있으나 그 해 금액이 비어 있음('-')"
                else:
                    st, why = missing_status(report, bool(lines), p.text(corp, report), words, label)
                    if label == "지배주주 순이익" and fs == "CFS" and st == CANNOT:
                        total = profit_total(lines) if col == "thstrm_amount" else None
                        why = "연결 손익계산서에 지배·비지배 구분 줄 없음" + (f" (당기순이익 {total:,.0f}원)" if total is not None else "")
                r |= {f"{label}(원)": v, f"{label} 상태": st, f"{label} 사유": why}
            rows.append(r)

    def check(L, i):
        a, d, e = (f"{L[k + '(원)']}{i}" for k in ("자산총계", "부채총계", "자본총계"))
        return f'=IF(COUNT({a},{d},{e})<3,"값 빈칸",IF(ABS({d}+{e}-{a})<=1,"일치","불일치"))'

    return cols, rows, {"수식 검산": check}


def sheet_cf(p: Partner):
    cols = base_cols("4조 fnltt 폴더 이름") + [
        Col("재무 기준", 8, "연결(CFS) 또는 별도(OFS) 현금흐름표", "4조 fnltt 파일 이름의 CFS/OFS"),
        Col("배당금 지급(원)", 17, "현금흐름표 배당금 지급 (지배회사가 주주에게 낸 현금, 양수로 적음)", "4조 fnltt JSON 현금흐름표",
            "계정 코드가 배당금 지급이거나 계정명에 '배당'과 '지급'이 함께 있는 줄의 금액 절댓값 합. 받은 배당(수취·수입)과 비지배지분 배당은 뺌", "num"),
        Col("배당금 지급 상태", 14, status_note("배당금 지급") + ". 원문에 '배당금 지급' 글자만 있고 바로 뒤에 금액이 붙은 줄이 없으면 "
            f"'{NO_SOURCE}'. 배당을 안 한 해는 보통 '{NO_SOURCE}'", "코드 판단", "source/scripts/export_partner_workbook.py DIV_AMOUNT"),
        Col("배당금 지급 사유", 30, "상태의 근거", "코드 판단"),
        Col("더한 계정", 30, "합계에 넣은 현금흐름표 계정 이름들", "4조 fnltt JSON account_nm"),
        Col("계정 수", 6, "더한 계정 수", "코드 셈", "", "num"),
        Col("비지배지분 배당(원)", 15, "따로 뺀 비지배지분 배당금 지급 (참고)", "4조 fnltt JSON 현금흐름표", "계정명에 '비지배'가 있는 배당 지급 줄 절댓값 합", "num"),
        Col("수식 검산", 12, "배당금 지급이 0 이상인지 (양수로 적었는지)", "엑셀 수식", "비면 '값 빈칸'", "formula")]
    cols += link_cols()
    rows = []
    for folder, c in p.companies:
        corp = c["corp_code"]
        for year in YEARS:
            r, report, fs, lines, col, _ = _year_row(p, folder, corp, year)
            paid, nci = dividend_lines(lines)
            vals = [amount(x.get(col)) for x in paid]
            vals = [abs(v) for v in vals if v is not None]
            nci_vals = [abs(v) for v in (amount(x.get(col)) for x in nci) if v is not None]
            if vals:
                st, why, v = HAS, "", sum(vals)
            elif paid:
                v, st, why = None, NO_SOURCE, f"계정 '{paid[0]['account_nm']}'은 있으나 그 해 금액이 비어 있음('-')"
            else:
                v = None
                st, why = missing_status(report, bool(lines), p.text(corp, report), DIV_WORDS, "배당금 지급", DIV_AMOUNT)
            r |= {"배당금 지급(원)": v, "배당금 지급 상태": st, "배당금 지급 사유": why,
                  "더한 계정": " / ".join(x["account_nm"] for x in paid) if vals else "", "계정 수": len(vals) if vals else None,
                  "비지배지분 배당(원)": sum(nci_vals) if nci_vals else None}
            rows.append(r)

    def check(L, i):
        v = f"{L['배당금 지급(원)']}{i}"
        return f'=IF(ISBLANK({v}),"값 빈칸",IF({v}>=0,"정상","음수"))'

    return cols, rows, {"수식 검산": check}


def sheet_decision(p: Partner):
    cols = [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", "4조 raw/events/filings/{corp_code}_I.json"),
            Col("접수번호", 15, "배당 결정 공시 접수번호", "4조 공시목록 I(거래소공시) rcept_no"),
            Col("공시일", 11, "공시 접수일 (YYYY-MM-DD)", "4조 공시목록 rcept_dt"),
            Col("공시명", 34, "보고서명 (정정이면 [기재정정] 등)", "4조 공시목록 report_nm", "제목에 '배당결정'(띄어쓰기 무시)이 있는 공시"),
            Col("정정 여부", 7, "제목이 [ ]로 시작하는 정정·추가 공시인지", "공시명"),
            Col("제출인", 14, "공시 제출인", "4조 공시목록 flr_nm"),
            Col("배당금총액 상태", 16, f"배당금총액·주당배당금 등 본문 값: {CANNOT} (4조가 공시 본문을 받지 않음)", "코드 판단"),
            Col("사유", 28, "상태의 근거", "코드 판단"),
            Col("원문", 10, "누르면 DART 공시 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]
    rows = []
    for folder, c in p.companies:
        corp = c["corp_code"]
        path = p.src / folder / "raw" / "events" / "filings" / f"{corp}_I.json"
        if not path.exists():
            continue
        seen = set()
        for pg in json.loads(path.read_text(encoding="utf-8")).get("pages", []):
            for x in pg.get("list") or []:
                nm, dt = x.get("report_nm", ""), x.get("rcept_dt", "")
                if "배당결정" not in squash(nm) or dt[:4] < str(YEARS.start) or x["rcept_no"] in seen:
                    continue
                seen.add(x["rcept_no"])
                rows.append({"회사명": p.name[corp], "corp_code": corp, "접수번호": x["rcept_no"],
                             "공시일": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}", "공시명": nm, "정정 여부": "Y" if nm.startswith("[") else "",
                             "제출인": x.get("flr_nm", ""), "배당금총액 상태": CANNOT,
                             "사유": "4조는 공시 목록(제목·날짜)만 받음. 금액은 원문을 열어 확인", "원문": link(x["rcept_no"])})
    rows.sort(key=lambda r: (r["회사명"], r["corp_code"], r["접수번호"]))
    return cols, rows, {}


# --- 2단계: 사업보고서 원문 XML의 정형 표 ------------------------------------------------------------

SHARE_ITEMS = [("ISU_STK1", "Ⅰ. 발행할 주식의 총수"), ("ISU_STK2", "Ⅱ. 현재까지 발행한 주식의 총수"),
               ("TOT_RST", "Ⅲ. 현재까지 감소한 주식의 총수"), ("RDC_CNT", "1. 감자"), ("DST_CNT", "2. 이익소각"),
               ("RFD_CNT", "3. 상환주식의 상환"), ("ETC_CNT", "4. 기타"), ("ISU_STK3", "Ⅳ. 발행주식의 총수"),
               ("TRS_STK", "Ⅴ. 자기주식수"), ("FLT_STK", "Ⅵ. 유통주식수"), ("TRS_RT", "Ⅶ. 자기주식 보유비율")]
SHARE_ALIAS = {"RST": "TOT_RST", "TRS_STK_RT": "TRS_RT"}  # 합계 열·옛 서식의 다른 코드
TABLE_WORDS = {"DIVIDEND": ("현금배당금총액",), "TOT_STK": ("발행주식의총수", "주식의총수"), "BSH_SPCL": ("최대주주",)}
GENERIC_BUDGET = 1_200_000  # 사업보고서표 엑셀 한 권에 넣을 행 수 (대략)


def _num(s):
    return dx.number(s)


def unit_factor(text: str | None) -> int:
    """원문 '(단위 : 천주)' 같은 글자 → 주식수에 곱할 값."""
    t = re.sub(r"\s+", "", text or "")
    return 1_000_000 if "백만주" in t else 1_000 if "천주" in t else 1


def won_written(d_mil, dps, floating) -> bool:
    """배당 표 '현금배당금총액(백만원)' 칸에 회사가 원 단위로 적었는지: 백만 원으로 읽은 D가 보통주 DPS × 유통주식수의 약 100만 배."""
    if not (d_mil and dps and floating):
        return False
    ratio = d_mil * 1_000_000 / (dps * floating)
    return 950_000 < ratio < 1_050_000


class Extract:
    """대상 회사 결산기 최신 사업보고서 원문을 한 번씩 열어, 배당·주식 총수·최대주주 표를 모으고
    모든 정형 표(102종 안팎)는 바로 사업보고서표 엑셀에 쓴다."""

    def __init__(self, p: Partner):
        self.p = p
        self.div = {}        # (corp, 보고서 연도, 열) → {"_rcept", 항목 열 이름 → 원문 글자, "_extra": [..]}
        self.div_status = {}  # (corp, 보고서 연도) → (상태, 사유) 표가 없을 때
        self.div_long = []   # 배당 표 1칸: (corp, 사업연도, 접수번호, 열, 구분, 종류, 원문 글자)
        self.share = []      # 행 dict
        self.holder = []
        self.title = {}      # aclass → Counter(제목)
        self.n_reports = {}  # aclass → 표가 있는 보고서 수
        self.n_rows = {}

    def _missing(self, report, text, aclass) -> tuple[str, str]:
        if text is None:
            return CANNOT, f"사업보고서 원문을 못 받음 (DART 응답 {report.get('last_api_status') or '?'})"
        flat = squash(dx.clean(text))
        if any(w in flat for w in TABLE_WORDS[aclass]):
            return CANNOT, f"원문에 글자는 있으나 정형 표({aclass})가 아님 — 원문 확인 필요"
        return NO_SOURCE, f"받은 원문에 정형 표({aclass})도 '{TABLE_WORDS[aclass][0]}' 글자도 없음"

    def run(self, generic: "GenericBooks | None" = None):
        want = {(squash(item), kind): name for item, kind, name, _ in DIV_ITEMS}
        for folder, corp, year, rep in self.p.latest_reports():
            got = rep["status"] == "수집완료"
            text = dx.read_report(self.p.zip_path(corp, rep["rcept_no"]), rep["rcept_no"]) if got else None
            gs = dx.groups(text) if text else []
            base = {"회사명": self.p.name[corp], "corp_code": corp, "사업연도": year, "결산기": rep["period"],
                    "접수번호": rep["rcept_no"], "원문": link(rep["rcept_no"]),
                    "받은 파일": self.p.local_link(corp, rep["rcept_no"]) if got else None}
            for g in gs:
                self.title.setdefault(g.aclass, collections.Counter())[g.title] += 1
                self.n_reports[g.aclass] = self.n_reports.get(g.aclass, 0) + 1
                if generic is not None:
                    self.n_rows[g.aclass] = self.n_rows.get(g.aclass, 0) + generic.write(g, base)
            # 배당 표
            g = dx.first(gs, "DIVIDEND")
            if g is None:
                self.div_status[(corp, year)] = self._missing(rep, text, "DIVIDEND")
            else:
                for label, kind, off, raw in dx.dividend_items(g):
                    self.div_long.append((corp, year - off, rep["rcept_no"], ("당기", "전기", "전전기")[off], label, kind, raw))
                    d = self.div.setdefault((corp, year, off), {"_rcept": rep["rcept_no"], "_extra": [], "_folder": folder})
                    col = want.get((squash(label), stock_kind(kind)))
                    if col and col not in d:
                        d[col] = raw
                    elif raw not in ("", "-"):
                        d["_extra"].append(f"{label}({kind})={raw}")
            # 주식 총수
            g = dx.first(gs, "TOT_STK")
            if g is None:
                st, why = self._missing(rep, text, "TOT_STK")
                self.share.append(base | {"상태": st, "사유": why})
            else:
                kinds, data, notes = dx.share_totals(g)
                units = " ".join(g.unit_cells().values())
                for kind in kinds:
                    r = base | {"기준일·단위": units, "주식 종류": kind, "상태": HAS, "사유": "",
                                "비고": " / ".join(f"{k}: {v}" for k, v in notes.items())}
                    extra = []
                    for code, (label, raw) in data[kind].items():
                        code = SHARE_ALIAS.get(code, code)
                        name = dict(SHARE_ITEMS).get(code)
                        if name and name not in r:
                            r[name] = _num(raw)
                        elif raw not in ("", "-"):
                            extra.append(f"{label}[{code}]={raw}")
                    r["그 밖의 칸"] = " / ".join(extra)
                    self.share.append(r)
            # 최대주주
            g = dx.first(gs, "BSH_SPCL")
            if g is None:
                st, why = self._missing(rep, text, "BSH_SPCL")
                self.holder.append(base | {"상태": st, "사유": why})
            else:
                units = " ".join(g.unit_cells().values())
                for n, h in enumerate(dx.holders(g), 1):
                    self.holder.append(base | {"기준일·단위": units, "행 번호": n, "성명": h.get("성명", ""), "관계": h.get("관계", ""),
                                               "주식 종류": h.get("주식 종류", ""), "기초 주식수": _num(h.get("기초 주식수")),
                                               "기초 지분율(%)": _num(h.get("기초 지분율")), "기말 주식수": _num(h.get("기말 주식수")),
                                               "기말 지분율(%)": _num(h.get("기말 지분율")), "비고": h.get("비고", ""),
                                               "합계 행": "Y" if squash(h.get("성명", "")) in ("계", "합계", "소계") else "",
                                               "상태": HAS, "사유": ""})


def report_cols() -> list[Col]:
    return [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", "4조 report_manifest.csv corp_code"),
            Col("사업연도", 8, "보고서 결산기 연도", "4조 report_manifest.csv period"),
            Col("결산기", 8, "보고서 기간 (YYYY.MM)", "4조 report_manifest.csv period")]


def report_links() -> list[Col]:
    return [Col("접수번호", 15, "표를 읽은 사업보고서 (결산기 최신 전체본)", "4조 report_manifest.csv rcept_no"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
            Col("받은 파일", 10, "누르면 4조가 받아 둔 원문 zip이 열림 (엑셀 옆 원본/ 폴더 기준)", "4조 raw/documents/{corp_code}/{접수번호}.zip", "", "link")]


def sheet_div_items(p: Partner, ex: Extract):
    cols = [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", "4조 report_manifest.csv corp_code"),
            Col("사업연도", 8, "배당 표의 그 열이 가리키는 사업연도", "보고서 결산기 연도 − 열(당기 0 · 전기 1 · 전전기 2)"),
            Col("보고서 접수번호", 15, "배당 표를 읽은 사업보고서 (한 보고서가 당기·전기·전전기 3개 연도를 줌)", "4조 report_manifest.csv rcept_no"),
            Col("보고서 열", 8, "그 보고서 배당 표의 당기·전기·전전기 중 어느 열인지", "원문 표 머리")]
    cols += [Col(name, 13, meaning, f"사업보고서 원문 XML 배당 표(DIVIDEND) '{item}' 행, 주식 종류 {kind}",
                 "원문 표 값 그대로 (단위도 원문 그대로). '-'는 빈칸으로 둠", "pct" if "%" in name else "num")
             for item, kind, name, meaning in DIV_ITEMS]
    cols += [Col("그 밖의 항목", 30, "위 열에 없는 행·주식 종류의 값 (항목(종류)=값). '-'는 뺌", "사업보고서 원문 XML 배당 표"),
             Col("수식: 배당성향", 11, "(연결)현금배당성향이 현금배당금총액 ÷ (연결)당기순이익 × 100 과 같은지", "엑셀 수식",
                 "|성향 − 총액÷순이익×100| ≤ 0.5 이면 '일치'. 순이익이 0 이하이거나 빈칸이면 '계산 대상 아님'", "formula"),
             Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
             Col("받은 파일", 10, "누르면 4조가 받아 둔 원문 zip이 열림", "4조 raw/documents/{corp_code}/{접수번호}.zip", "", "link")]
    rows = []
    for (corp, year, off), d in ex.div.items():
        r = {"회사명": p.name[corp], "corp_code": corp, "사업연도": year - off, "보고서 접수번호": d["_rcept"],
             "보고서 열": ("당기", "전기", "전전기")[off], "그 밖의 항목": " / ".join(d["_extra"]),
             "원문": link(d["_rcept"]), "받은 파일": p.local_link(corp, d["_rcept"])}
        for _, _, name, _ in DIV_ITEMS:
            r[name] = _num(d.get(name))
        rows.append(r)
    rows.sort(key=lambda r: (r["회사명"], r["corp_code"], r["사업연도"], r["보고서 접수번호"]))

    def check(L, i):
        pp, t, n = (f"{L[c]}{i}" for c in ("(연결)현금배당성향(%)", "현금배당금총액(백만원)", "(연결)당기순이익(백만원)"))
        return (f'=IF(OR(NOT(ISNUMBER({n})),{n}<=0,NOT(ISNUMBER({t}))),"계산 대상 아님",'
                f'IF(NOT(ISNUMBER({pp})),"성향 빈칸",IF(ABS({pp}-{t}/{n}*100)<=0.5,"일치","불일치")))')

    return cols, rows, {"수식: 배당성향": check}


def sheet_div(p: Partner, ex: Extract):
    cols = base_cols("4조 lists/companies.csv corp_code") + [
        Col("현금배당총액 D(원)", 17, "사업보고서 '배당에 관한 사항' 표의 현금배당금총액 (보통+우선, 중간·분기 포함 1년 합계)",
            "사업보고서 원문 XML 배당 표(DIVIDEND) '현금배당금총액(백만원)'", "원문 백만 원 값 × 1,000,000", "num"),
        Col("D 원문 값(백만원)", 13, "원문 표에 적힌 그대로", "사업보고서 원문 XML 배당 표", "", "num"),
        Col("D 상태", 14, status_note("현금배당총액") + ". 원문 값이 '-'이면 원문에 없음(배당 없음)", "코드 판단"),
        Col("D 사유", 30, "상태의 근거", "코드 판단"),
        Col("보통주 주당배당금(원)", 13, "배당 표 '주당 현금배당금' 중 보통주 행", "사업보고서 원문 XML 배당 표", "", "num"),
        Col("보통주 DPS 상태", 14, status_note("보통주 주당배당금"), "코드 판단"),
        Col("보통주 DPS 사유", 30, "상태의 근거", "코드 판단"),
        Col("수식 검산", 12, "현금배당총액이 있으면 보통주 주당배당금도 있는지", "엑셀 수식", "D가 있는데 DPS가 비면 'DPS 빈칸'", "formula")]
    cols += link_cols()
    floating = {}  # 접수번호 → 보통주 유통주식수 (주 단위) — D 단위 잘못 적힘을 가려내는 데 씀
    for s in ex.share:
        v = s.get("Ⅵ. 유통주식수")
        if s.get("상태") == HAS and v and share_class(s.get("주식 종류")) == "보통":
            v *= unit_factor(s.get("기준일·단위"))
            floating[s["접수번호"]] = max(v, floating.get(s["접수번호"], 0))
    rows = []
    for folder, c in p.companies:
        corp = c["corp_code"]
        for year in YEARS:
            report = p.report(corp, year)
            own = report["rcept_no"] if report else ""
            r = {"회사명": p.name[corp], "corp_code": corp, "사업연도": year, "4조 업종": INDUSTRIES[folder],
                 "사업보고서": link(own), "받은 파일": p.local_link(corp, own) if report and report["status"] == "수집완료" else None}
            hit = next(((off, ex.div[(corp, year + off, off)]) for off in (0, 1, 2) if (corp, year + off, off) in ex.div), None)
            if hit:
                off, d = hit
                r |= {"원천 열": ("당기", "전기", "전전기")[off], "접수번호": d["_rcept"], "원문": link(d["_rcept"])}
            for raw_name, out, ost, owhy, scale in (("현금배당금총액(백만원)", "현금배당총액 D(원)", "D 상태", "D 사유", 1_000_000),
                                                    ("주당 현금배당금 보통(원)", "보통주 주당배당금(원)", "보통주 DPS 상태", "보통주 DPS 사유", 1)):
                raw = hit[1].get(raw_name) if hit else None
                v = _num(raw)
                if out.startswith("현금"):
                    r["D 원문 값(백만원)"] = v
                if v is not None:
                    r[out], r[ost], r[owhy] = v * scale, HAS, ""
                elif hit and raw is not None:
                    r[ost], r[owhy] = NO_SOURCE, f"원문 배당 표 값 '{raw}' (배당 없음)"
                elif hit:
                    r[ost], r[owhy] = NO_SOURCE, "원문 배당 표에 그 행이 없음"
                elif report is None:
                    r[ost], r[owhy] = NO_SOURCE, "공시목록에 그 해 사업보고서 없음"
                else:
                    r[ost], r[owhy] = ex.div_status.get((corp, year), (CANNOT, "원문을 열지 못함"))
            if hit and won_written(r.get("D 원문 값(백만원)"), r.get("보통주 주당배당금(원)"), floating.get(hit[1]["_rcept"])):
                r["현금배당총액 D(원)"] = r["D 원문 값(백만원)"]
                r["D 사유"] = "원문 백만원 칸에 원 단위로 적힘 (D ÷ (보통주 DPS × 유통주식수) ≈ 1,000,000) → 원으로 읽음"
            rows.append(r)

    def check(L, i):
        d, s = f"{L['현금배당총액 D(원)']}{i}", f"{L['보통주 주당배당금(원)']}{i}"
        return f'=IF(AND(ISNUMBER({d}),NOT(ISNUMBER({s}))),"DPS 빈칸","정상")'

    return cols, rows, {"수식 검산": check}


def sheet_share(p: Partner, ex: Extract):
    cols = report_cols() + [Col("기준일·단위", 20, "표 위 기준일과 단위 (원문 그대로, [ ] 안은 서식 값)", "원문 XML TU 칸"),
                            Col("주식 종류", 10, "표의 열: 보통주 · 우선주 · 합계 등 (원문 그대로)", "원문 표 머리")]
    cols += [Col(name, 15, name, f"사업보고서 원문 XML 주식의 총수 표(TOT_STK) 항목 코드 {code}", "원문 값 그대로 ('-'는 빈칸)",
                 "pct" if code == "TRS_RT" else "num") for code, name in SHARE_ITEMS]
    cols += [Col("그 밖의 칸", 26, "위 열에 없는 항목 코드의 값 (항목[코드]=값)", "원문 XML"),
             Col("비고", 26, "표의 비고 칸 (항목: 내용)", "원문 XML"),
             Col("상태", 14, f"{HAS} · {NO_SOURCE}(원문에 표도 글자도 없음) · {CANNOT}(원문 못 받음 · 정형 표가 아님)", "코드 판단"),
             Col("사유", 28, "상태의 근거", "코드 판단"),
             Col("수식 검산", 13, "Ⅱ − Ⅲ = Ⅳ 이고 Ⅳ − Ⅴ = Ⅵ 인지", "엑셀 수식", "둘 다 맞으면 '일치', 칸이 비면 '값 빈칸'", "formula")]
    cols += report_links()

    def check(L, i):
        a, b, c4, c5, c6 = (f"{L[n]}{i}" for n in ("Ⅱ. 현재까지 발행한 주식의 총수", "Ⅲ. 현재까지 감소한 주식의 총수",
                                                   "Ⅳ. 발행주식의 총수", "Ⅴ. 자기주식수", "Ⅵ. 유통주식수"))
        return (f'=IF(COUNT({a},{b},{c4},{c5},{c6})<5,"값 빈칸",'
                f'IF(AND(ABS({a}-{b}-{c4})<1,ABS({c4}-{c5}-{c6})<1),"일치","불일치"))')

    rows = sorted(ex.share, key=lambda r: (r["회사명"], r["corp_code"], r["사업연도"]))
    return cols, rows, {"수식 검산": check}


def sheet_holder(p: Partner, ex: Extract):
    cols = report_cols() + [
        Col("기준일·단위", 20, "표 위 기준일과 단위 (원문 그대로)", "원문 XML TU 칸"),
        Col("행 번호", 6, "표 안 순서", "원문 표", "", "num"),
        Col("성명", 18, "최대주주·특수관계인 이름 ('계'는 합계 행)", "원문 XML 최대주주 표(BSH_SPCL) 성명"),
        Col("관계", 14, "최대주주 본인 · 특수관계인 등", "원문 XML 관계"),
        Col("주식 종류", 10, "보통주 · 우선주 등", "원문 XML 주식의 종류"),
        Col("기초 주식수", 14, "기초 소유 주식수", "원문 XML", "", "num"),
        Col("기초 지분율(%)", 9, "기초 지분율", "원문 XML", "", "pct"),
        Col("기말 주식수", 14, "기말 소유 주식수", "원문 XML", "", "num"),
        Col("기말 지분율(%)", 9, "기말 지분율", "원문 XML", "", "pct"),
        Col("비고", 22, "비고 (변동 사유 등)", "원문 XML"),
        Col("합계 행", 6, "성명이 '계'·'합계'인 행이면 Y", "코드 판단"),
        Col("상태", 14, f"{HAS} · {NO_SOURCE} · {CANNOT}", "코드 판단"),
        Col("사유", 28, "상태의 근거", "코드 판단"),
        Col("수식 검산", 12, "기말 지분율이 0~100 사이인지", "엑셀 수식", "비면 '값 빈칸'", "formula")]
    cols += report_links()

    def check(L, i):
        v = f"{L['기말 지분율(%)']}{i}"
        return f'=IF(NOT(ISNUMBER({v})),"값 빈칸",IF(AND({v}>=0,{v}<=100),"정상","확인 필요"))'

    rows = sorted(ex.holder, key=lambda r: (r["회사명"], r["corp_code"], r["사업연도"], r.get("행 번호") or 0))
    return cols, rows, {"수식 검산": check}


# --- 4조가 만든 표 (위험 사건·감사의견) · 주석 목록 ------------------------------------------------------

COLNAME = {  # 4조 CSV 열 → 한국어 열 이름
    "industry": "4조 업종", "corp_code": "corp_code", "corp_name": "회사명", "event_type": "사건 종류", "severity": "심각도(4조 잠정)",
    "use": "쓰임", "is_first_of_type": "유형별 최초", "event_date": "사건일", "date_basis": "날짜 근거", "fiscal_period": "결산기",
    "rcept_no": "접수번호", "rcept_dt": "접수일", "source": "출처", "title": "제목", "verified": "원문 대조(4조)", "detail": "내용",
    "call_year": "조회 연도", "fiscal_year": "사업연도", "row_label": "기수", "auditor": "감사인", "opinion_raw": "감사의견 원문",
    "opinion": "감사의견", "going_concern": "계속기업 불확실성", "notes": "특기사항", "period": "결산기", "version": "버전",
    "is_first": "최초본", "is_latest_full": "결산기 최신 전체본", "fs": "재무제표", "status": "읽은 상태",
    "opinion_attach": "감사의견(첨부)", "opinion_body": "감사의견(본문)", "gc_attach": "계속기업(첨부)", "gc_body": "계속기업(본문)",
    "mismatch": "첨부·본문 다름", "att_file": "첨부 파일", "opinion_evidence": "감사의견 근거 문장", "gc_evidence": "계속기업 근거 문장",
    "body_row": "본문 표 행", "note": "메모", "pblntf_ty": "공시 유형", "report_nm": "공시명", "flr_nm": "제출인", "category": "분류",
    "matched": "걸린 글자", "corp_cls_name": "법인 구분", "first_period": "첫 결산기", "last_period": "마지막 결산기",
}


def csv_sheet(p: Partner, file: str, meaning: str):
    """4조 {업종}/events/{file}.csv 를 대상 회사만 그대로 옮긴다 (열 순서 원본대로, 회사명·corp_code를 앞으로)."""
    ctrl = set(p.folder)
    rows, head = [], []
    for folder in INDUSTRIES:
        path = p.src / folder / "events" / f"{file}.csv"
        if not path.exists():
            continue
        for m in read_csv(path):
            if m["corp_code"] not in ctrl:
                continue
            head = head or list(m)
            r = {COLNAME.get(k, k): v for k, v in m.items()}
            if m.get("rcept_no"):
                r["원문"] = link(m["rcept_no"])
            rows.append(r)
    order = ["corp_name", "corp_code"] + [k for k in head if k not in ("corp_name", "corp_code")]
    cols = [Col(COLNAME.get(k, k), 16 if k in ("corp_name", "detail", "title", "opinion_evidence", "gc_evidence") else 11,
                f"{meaning}: {COLNAME.get(k, k)}", f"4조 {{업종}}/events/{file}.csv {k}") for k in order]
    cols.append(Col("원문", 10, "접수번호가 있으면 DART 원문", "접수번호로 만든 DART 주소", "", "link"))
    rows.sort(key=lambda r: (r.get("회사명", ""), r.get("corp_code", "")))
    return cols, rows, {}


def sheet_notes(p: Partner):
    cols = [Col("회사명", 16, "회사 이름", "4조 verify/notes_index.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", "4조 verify/notes_index.csv corp_code"),
            Col("결산기", 8, "보고서 기간", "4조 notes_index.csv period"),
            Col("접수번호", 15, "주석을 뽑은 사업보고서", "4조 notes_index.csv rcept_no"),
            Col("버전", 9, "최초 · 기재정정 등", "4조 notes_index.csv version"),
            Col("최초본", 6, "그 결산기 최초 보고서인지", "4조 notes_index.csv is_first"),
            Col("결산기 최신 전체본", 8, "분석에는 Y만 쓰면 됨", "4조 notes_index.csv is_latest_full"),
            Col("주석 위치", 14, "사업보고서 본문 · 감사보고서(_00760) · 연결감사보고서(_00761) 첨부", "4조 notes_index.csv source_file",
                "본문 주석만 쓰면 됨 (감사보고서 주석과 내용이 겹침)"),
            Col("재무제표", 8, "CFS 연결 · OFS 별도", "4조 notes_index.csv fs_div"),
            Col("제목", 22, "주석 제목", "4조 notes_index.csv title"),
            Col("뽑은 방법", 9, "4조가 주석을 자른 방법", "4조 notes_index.csv method"),
            Col("글자 수", 9, "주석 글자 수", "4조 notes_index.csv chars", "", "num"),
            Col("상태", 8, "4조 추출 상태 (OK 등)", "4조 notes_index.csv status"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
            Col("주석 파일", 10, "누르면 4조가 뽑은 주석 글자 파일(.txt)이 열림", "4조 raw/notes/{corp_code}/…txt", "", "link"),
            Col("주석 XML", 10, "같은 주석의 원문 XML 조각", "4조 raw/notes/{corp_code}/…xml", "", "link")]
    rows = []
    for folder in INDUSTRIES:
        path = p.src / folder / "verify" / "notes_index.csv"
        for m in read_csv(path) if path.exists() else []:
            corp = m["corp_code"]
            if corp not in p.folder or int(m["period"][:4]) not in YEARS:
                continue
            sf = m["source_file"]
            where = "감사보고서" if "_00760" in sf else "연결감사보고서" if "_00761" in sf else "사업보고서 본문"
            rel = m["file"].replace("\\", "/")
            txt = p.src / folder / "raw" / rel
            xml = txt.with_suffix(".xml")
            rows.append({"회사명": p.name[corp], "corp_code": corp, "결산기": m["period"], "접수번호": m["rcept_no"],
                         "버전": m["version"], "최초본": m["is_first"], "결산기 최신 전체본": m["is_latest_full"], "주석 위치": where,
                         "재무제표": m["fs_div"], "제목": m["title"], "뽑은 방법": m["method"], "글자 수": amount(m["chars"]),
                         "상태": m["status"], "원문": link(m["rcept_no"]),
                         "주석 파일": txt.relative_to(p.src.parent).as_posix() if txt.exists() else None,
                         "주석 XML": xml.relative_to(p.src.parent).as_posix() if xml.exists() else None})
    rows.sort(key=lambda r: (r["회사명"], r["corp_code"], r["결산기"], r["접수번호"], r["주석 위치"], r["재무제표"]))
    return cols, rows, {}


# --- 큰 표: 재무제표 전체 · 공시 목록 · 사업보고서 정형 표 ----------------------------------------------------

FS_SHEETS = [("03-1_재무상태표", ("BS",)), ("03-2_손익계산서", ("IS", "CIS")), ("03-3_현금흐름표", ("CF",)), ("03-4_자본변동표", ("SCE",))]


def fs_cols() -> list[Col]:
    src = "4조 fnltt/{corp_code}/{연도}_11011_{CFS|OFS}.json (OpenDART 단일회사 전체 재무제표)"
    cols = [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", src),
            Col("사업연도", 8, "이 재무제표를 낸 사업보고서의 사업연도", src + " 파일 이름"),
            Col("재무제표", 8, "연결 · 별도", src + " 파일 이름"),
            Col("표 이름", 14, "재무상태표 · 손익계산서 · 포괄손익계산서 · 현금흐름표 · 자본변동표", src + " sj_nm"),
            Col("순서", 6, "표 안 계정 순서", src + " ord", "", "num"),
            Col("계정명", 30, "회사가 적은 계정 이름", src + " account_nm"),
            Col("표준계정코드", 30, "XBRL 표준계정 코드 (미사용이면 회사 자체 계정)", src + " account_id"),
            Col("계정 상세", 24, "자본변동표의 자본 구성요소 등", src + " account_detail")]
    for key, label in (("thstrm", "당기"), ("frmtrm", "전기"), ("bfefrmtrm", "전전기")):
        cols += [Col(f"{label} 이름", 10, f"{label} 기수 표기", src + f" {key}_nm"),
                 Col(f"{label} 금액(원)", 17, f"{label} 금액 (원문 그대로)", src + f" {key}_amount", "", "num")]
    cols += [Col("당기 누적 금액(원)", 15, "손익계산서 누적 금액 (있을 때만)", src + " thstrm_add_amount", "", "num"),
             Col("통화", 6, "통화", src + " currency"),
             Col("접수번호", 15, "이 재무제표를 낸 사업보고서", src + " rcept_no"),
             Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
             Col("받은 파일", 10, "4조가 받아 둔 그 사업보고서 원문 zip", "4조 raw/documents", "", "link")]
    return cols


def fs_rows(p: Partner, sheets: dict):
    """sheets: 시트 이름 → stream_book.Sheet. 회사·연도·연결/별도 파일 순서로 모든 줄을 쓴다."""
    which = {sj: name for name, sjs in FS_SHEETS for sj in sjs}
    for folder, c in p.companies:
        corp = c["corp_code"]
        d = p.fnltt(corp)
        if not d.exists():
            continue
        for f in sorted(os.listdir(d)):
            year, fs = int(f[:4]), f.split("_")[-1][:3]
            if year not in YEARS:
                continue
            lines = json.loads((d / f).read_text(encoding="utf-8")).get("list") or []
            for x in lines:
                name = which.get(x.get("sj_div"))
                if not name:
                    continue
                rc = x.get("rcept_no", "")
                sheets[name].add({"회사명": p.name[corp], "corp_code": corp, "사업연도": year, "재무제표": {"CFS": "연결", "OFS": "별도"}.get(fs, fs),
                                  "표 이름": x.get("sj_nm", ""), "순서": amount(x.get("ord")), "계정명": x.get("account_nm", ""),
                                  "표준계정코드": x.get("account_id", ""), "계정 상세": x.get("account_detail", ""),
                                  "당기 이름": x.get("thstrm_nm", ""), "당기 금액(원)": amount(x.get("thstrm_amount")),
                                  "전기 이름": x.get("frmtrm_nm", ""), "전기 금액(원)": amount(x.get("frmtrm_amount")),
                                  "전전기 이름": x.get("bfefrmtrm_nm", ""), "전전기 금액(원)": amount(x.get("bfefrmtrm_amount")),
                                  "당기 누적 금액(원)": amount(x.get("thstrm_add_amount")), "통화": x.get("currency", ""),
                                  "접수번호": rc, "원문": link(rc), "받은 파일": p.local_link(corp, rc)})


FILING_SHEETS = [("10-1_정기공시", "A", "raw/filings/{corp}.json", "정기공시(사업·반기·분기보고서) 목록"),
                 ("10-2_주요사항보고", "B", "raw/events/filings/{corp}_B.json", "주요사항보고서 목록"),
                 ("10-3_거래소공시", "I", "raw/events/filings/{corp}_I.json", "거래소 공시 목록")]


def filing_cols(src: str) -> list[Col]:
    return [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
            Col("corp_code", 10, "DART 고유번호", f"4조 {src} corp_code"),
            Col("접수번호", 15, "DART 접수번호", f"4조 {src} rcept_no"),
            Col("접수일", 11, "공시 접수일 (YYYY-MM-DD)", f"4조 {src} rcept_dt"),
            Col("공시명", 40, "보고서 이름 (정정이면 [기재정정] 등)", f"4조 {src} report_nm"),
            Col("제출인", 16, "공시 제출인", f"4조 {src} flr_nm"),
            Col("비고", 8, "DART 비고 기호 (유: 유가증권 · 코: 코스닥 · 정: 정정 등)", f"4조 {src} rm"),
            Col("법인 구분", 7, "Y 유가 · K 코스닥 · N 코넥스 · E 기타", f"4조 {src} corp_cls"),
            Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link")]


def filing_rows(p: Partner, path_tpl: str):
    for folder, c in p.companies:
        corp = c["corp_code"]
        path = p.src / folder / path_tpl.format(corp=corp)
        if not path.exists():
            continue
        seen = set()
        out = []
        for pg in json.loads(path.read_text(encoding="utf-8")).get("pages", []):
            for x in pg.get("list") or []:
                if x["rcept_no"] in seen:
                    continue
                seen.add(x["rcept_no"])
                dt = x.get("rcept_dt", "")
                out.append({"회사명": p.name[corp], "corp_code": corp, "접수번호": x["rcept_no"],
                            "접수일": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt, "공시명": x.get("report_nm", ""),
                            "제출인": x.get("flr_nm", ""), "비고": x.get("rm", ""), "법인 구분": x.get("corp_cls", ""),
                            "원문": link(x["rcept_no"])})
        yield from sorted(out, key=lambda r: r["접수번호"])


class GenericBooks:
    """사업보고서 정형 표(표 종류 코드마다 시트 1개)를 여러 권에 나눠 쓴다. 권 나누기는 표본으로 잰 행 수 기준."""

    def __init__(self, out_dir: Path, stamp: str, estimate: dict[str, int], ncols: dict[str, int], group: str = "대조군"):
        self.out_dir, self.stamp, self.group = out_dir, stamp, group
        self.ncols = {k: min(max(v, 4), 40) for k, v in ncols.items()}
        self.books: list[sb.Book] = []
        self.where: dict[str, sb.Sheet] = {}
        self.plan: dict[str, int] = {}  # aclass → 권 번호
        n, used = 1, 0
        for a, rows in estimate.items():  # 원문에 처음 나오는 순서
            if used and used + rows > GENERIC_BUDGET:
                n, used = n + 1, 0
            self.plan[a], used = n, used + rows
        self.n_books = max(self.plan.values(), default=1)

    def _book(self, k: int) -> sb.Book:
        while len(self.books) < k:
            i = len(self.books) + 1
            b = sb.Book(self.out_dir / f"4조참치_{self.group}_사업보고서표_{i}_{self.stamp}.xlsx", styled=False, link_text=LINK_TEXT)
            b.index = b.sheet("표_목록", "이 권에 든 정형 표 종류 목록", INDEX_COLS)
            self.books.append(b)
        return self.books[k - 1]

    def _sheet(self, g: dx.Group) -> sb.Sheet:
        a = g.aclass
        if a not in self.where:
            n = self.ncols.get(a, 12)
            cols = [Col("회사명", 16, "회사 이름", "4조 lists/companies.csv corp_name"),
                    Col("corp_code", 10, "DART 고유번호", "4조 report_manifest.csv"),
                    Col("사업연도", 8, "보고서 결산기 연도", "4조 report_manifest.csv period"),
                    Col("결산기", 8, "보고서 기간", "4조 report_manifest.csv period"),
                    Col("접수번호", 15, "표를 읽은 사업보고서 (결산기 최신 전체본)", "4조 report_manifest.csv rcept_no"),
                    Col("표 제목", 24, "이 표 앞 가장 가까운 목차 제목", "원문 XML TITLE"),
                    Col("표 번호", 5, "이 표 묶음 안 표 순서 (보통 1 = 기준일·단위 표)", "원문 XML TABLE 순서", "", "num"),
                    Col("행 번호", 5, "표 안 행 순서 (머리 행 포함)", "원문 XML TR 순서", "", "num"),
                    Col("행 종류", 6, "머리(열 이름) · 본문", "원문 XML THEAD/TBODY")]
            cols += [Col(f"칸{j}", 14, f"{j}번째 칸 글자 (원문 그대로, rowspan·colspan은 펼쳐 같은 글자를 채움)", "원문 XML TH/TD/TE/TU")
                     for j in range(1, n + 1)]
            cols += [Col("넘친 칸", 20, f"{n}칸을 넘는 칸 (| 로 이음)", "원문 XML"),
                     Col("값 칸 코드", 24, "이 행 값 칸(TE)·단위 칸(TU)의 서식 코드 (ACODE·AUNIT, | 로 이음)", "원문 XML ACODE"),
                     Col("원문", 10, "누르면 DART 원문이 열림", "접수번호로 만든 DART 주소", "", "link"),
                     Col("받은 파일", 10, "4조가 받아 둔 원문 zip", "4조 raw/documents", "", "link")]
            book = self._book(self.plan.get(a, self.n_books))
            self.where[a] = book.sheet(a[:31], f"사업보고서 정형 표 {a}", cols)
        return self.where[a]

    def write(self, g: dx.Group, base: dict) -> int:
        s = self._sheet(g)
        n = self.ncols.get(g.aclass, 12)
        k = 0
        for ti, ri, kind, texts, codes in dx.grid(g):
            r = {kk: base[kk] for kk in ("회사명", "corp_code", "사업연도", "결산기", "접수번호", "원문", "받은 파일")}
            r |= {"표 제목": g.title, "표 번호": ti, "행 번호": ri, "행 종류": kind,
                  "넘친 칸": " | ".join(texts[n:]), "값 칸 코드": " | ".join(codes)}
            r |= {f"칸{j}": t for j, t in enumerate(texts[:n], 1)}
            s.add(r)
            k += 1
        return k

    def save(self, ex: "Extract", target: str):
        for b in self.books:
            pass
        for a, s in self.where.items():
            s.close()
        for i, b in enumerate(self.books, 1):
            mine = [a for a, s in self.where.items() if s.book is b]
            for a in mine:
                b.index.add({"표 코드": a, "표 제목(가장 흔한 것)": ex.title[a].most_common(1)[0][0] if ex.title.get(a) else "",
                             "표가 있는 보고서 수": ex.n_reports.get(a, 0), "행 수": ex.n_rows.get(a, 0),
                             "시트": ", ".join(t for t, _, _ in self.where[a].parts)})
            b.index.close()
            b.save(generic_guide(b, i, self.n_books, target, self.group))


INDEX_COLS = [Col("표 코드", 16, "DART 서식의 표 종류 코드 (TABLE-GROUP ACLASS)", "원문 XML"),
              Col("표 제목(가장 흔한 것)", 34, "이 표 앞 목차 제목 중 가장 많이 나온 것", "원문 XML TITLE"),
              Col("표가 있는 보고서 수", 10, "이 표가 있는 사업보고서 수", "코드 셈", "", "num"),
              Col("행 수", 10, "이 표 시트의 행 수 (머리 행 포함)", "코드 셈", "", "num"),
              Col("시트", 16, "이 표를 담은 시트 이름", "")]


def sample_plan(p: Partner, n: int = 300) -> tuple[dict[str, int], dict[str, int]]:
    """정형 표 종류별 예상 행 수와 최대 칸 수 (보고서 n건 표본 × 전체 보고서 수). 순서는 원문에 처음 나오는 순서."""
    reps = [(corp, rep) for _, corp, _, rep in p.latest_reports() if rep["status"] == "수집완료"]
    if not reps:
        return {}, {}
    step = max(len(reps) // n, 1)
    smp = reps[::step][:n]
    rows, ncols = {}, {}
    for corp, rep in smp:
        text = dx.read_report(p.zip_path(corp, rep["rcept_no"]), rep["rcept_no"])
        for g in dx.groups(text or ""):
            for _, _, _, texts, _ in dx.grid(g):
                rows[g.aclass] = rows.get(g.aclass, 0) + 1
                ncols[g.aclass] = max(ncols.get(g.aclass, 0), len(texts))
    scale = len(reps) / len(smp)
    return {a: int(v * scale * 1.2) for a, v in rows.items()}, ncols


# --- 안내 · 엑셀 쓰기 -----------------------------------------------------------------------

LINK_TEXT = {"사업보고서": "사업보고서 열기", "받은 파일": "받은 파일 열기", "주석 파일": "주석 파일 열기", "주석 XML": "XML 열기"}

STATUS_TEXT = (f"{HAS} = 4조 자료에서 값을 읽음 · {NO_SOURCE} = 그 해 사업보고서가 없거나, 원문에 그 항목이 없음(글자 없음 · 값 '-' · 계정은 있으나 금액 빈칸) · "
               f"{CANNOT} = DART에 원문은 있지만 이 자료로 꺼내지 못함 (원문 못 받음 · API 표에는 없는데 원문에 있음 · 정형 표가 아님 · 공시 본문 미수집). "
               "'사유' 칸에 근거를 적었습니다.")


GROUPS = {"대조군": "4조 4개 업종 수집 대상 중 우리 638사에 없는 {n:,}사 (겹치는 {m:,}사는 우리 값이 더 정확해서 뺌, 겹침 파일에 따로 있음)",
          "겹침": "4조 4개 업종 수집 대상 중 우리 638사와 겹치는 {n:,}사. 이 회사들은 우리 값이 더 정확하므로 분석에는 우리 값을 쓰고, "
                "이 파일은 4조 자료 참고·대조용"}


def common_guide(title: str, what: str, counts: dict, target: str) -> list[tuple]:
    rows = [(title, None), (None, None),
            ("만든 날", f"{date.today().isoformat()} (4조참치 원본 폴더에서 내보냄, source/scripts/export_partner_workbook.py)"),
            ("받은 자료", "4조참치 '재무나침반 데이터' (2026-10-30 받음). 설명은 data/partner/4조참치_20261030/README.md"),
            ("대상", f"{target}. 사업연도 {YEARS.start}~{YEARS.stop - 1}"),
            ("이 파일", what), ("항목 뜻", "열마다 뜻·원천·계산 방법은 '항목_설명' 시트에 있습니다."), (None, None)]
    rows += [(n, f"{v:,}행") for n, v in counts.items()]
    rows += [(None, None),
             ("상태 뜻", STATUS_TEXT),
             ("링크", "원문 = 값을 준 공시(DART) · 사업보고서 = 그 사업연도 사업보고서(DART) · 받은 파일 = 4조가 받아 둔 원문 zip "
                    "(이 엑셀 옆 원본/ 폴더 기준이라 파일을 옮기면 열리지 않음)"),
             ("검산 방법", "1) '원문 열기'·'받은 파일 열기'로 원문을 엽니다. 2) 숫자·글자를 원문과 비교합니다. "
                        "3) 노란 칸 '검토 상태'에서 확인완료 / 확인불가 / 정정됨(배제) 중 하나를 고르고, 검토자와 메모를 적습니다."),
             ("고칠 칸", "노란색 칸(검토 상태·검토자·메모)만 적어 주세요. 다른 칸은 4조 자료·원문 값이라 고치지 않습니다."),
             ("수식 칸", "연두색 '수식' 칸은 엑셀 수식입니다. '불일치'·'확인 필요'인 행부터 보면 빠릅니다."),
             ("금액 단위", "재무제표는 원(OpenDART 원 단위). 원문 표는 원문에 적힌 단위 그대로(배당 표는 백만 원·원·%, 주식은 주)."),
             (None, None),
             ("작성 예시", f"검토 상태: 확인완료 · 검토자: 한상범 · 메모: 배당금 지급 {CANNOT} → 원문 현금흐름표에 '배당금의 지급' 1,200,000,000 있음")]
    return rows


def generic_guide(b: sb.Book, i: int, n: int, target: str, group: str) -> list[tuple]:
    return common_guide(f"4조참치 {group} 사업보고서 정형 표 ({i}/{n})",
                        "사업보고서(결산기 최신 전체본) 원문 XML의 DART 정형 표(TABLE-GROUP)를 표 종류마다 시트 하나로 모두 옮김. "
                        "1행 = 원문 표 1행 (머리 행 포함). XBRL 재무제표·주석 표는 '재무제표전체' 파일과 주석 파일에 있어서 뺌. "
                        "표 종류 목록은 '표_목록' 시트", b.counts(), target)


MAIN_SHEETS = [("00_회사목록", "회사 목록과 기업개황 (대상은 안내 시트)"),
               ("01_사업보고서목록", f"{YEARS.start}~{YEARS.stop - 1} 사업보고서 1건(최초·정정 모든 버전)당 1행과 원문을 받았는지"),
               ("02_재무", "회사·사업연도별 지배주주 순이익·부채총계·자본총계·자산총계 (OpenDART 재무제표)"),
               ("02_배당표", "회사·사업연도별 현금배당총액 D·보통주 주당배당금 (사업보고서 원문 배당 표)"),
               ("02_배당표_전체항목", "사업보고서 배당 표의 모든 항목 (보고서·연도 열별 1행, 원문 단위 그대로)"),
               ("04_배당금지급", "회사·사업연도별 현금흐름표 배당금 지급"),
               ("05_배당결정공시", f"배당 결정 공시 1건당 1행 ({YEARS.start}-01 이후 접수분, 제목·날짜만)"),
               ("06_주식총수", "사업보고서 '주식의 총수' 표 (보고서·주식 종류별 1행)"),
               ("07_최대주주", "사업보고서 '최대주주 및 특수관계인의 주식소유 현황' 표 (주주 1명·주식 종류별 1행)"),
               ("08_위험사건", "4조가 모은 상환·연체 위험 사건 후보 (risk_events.csv)"),
               ("08-1_감사의견원문", "4조가 사업보고서 원문에서 읽은 감사의견·계속기업 불확실성 (audit_from_documents.csv)"),
               ("08-2_감사의견API", "OpenDART 감사의견 API 값 (audit_api.csv)"),
               ("08-3_공시사건후보", "공시 제목으로 걸러 낸 사건 후보 (filing_event_candidates.csv)"),
               ("08-4_사건조회범위", "회사별 위험 사건 API 조회 범위·상태 (events_coverage.csv)"),
               ("09_주석목록", "4조가 뽑은 재무제표 주석 파일 목록 (verify/notes_index.csv)")]


def build(src: Path, ours: set[str], out_dir: Path, stamp: str | None = None, sample: int = 300,
          group: str = "대조군") -> dict[str, dict[str, int]]:
    """group 대조군: 우리 회사(ours)를 뺀 4조 회사 · 겹침: 우리 회사와 겹치는 4조 회사만."""
    stamp = stamp or f"{date.today():%Y%m%d}"
    theirs = {r["corp_code"] for f in INDUSTRIES for r in read_csv(src / f / "lists" / "companies.csv")}
    overlap = theirs & ours
    p = Partner(src, ours if group == "대조군" else theirs - overlap)
    n = len(p.companies)
    target = GROUPS[group].format(n=n, m=len(overlap))
    result = {}

    # 1) 사업보고서 정형 표 (원문을 한 번 열면서 배당·주식 총수·최대주주도 모음)
    estimate, ncols = sample_plan(p, sample)
    generic = GenericBooks(out_dir, stamp, estimate, ncols, group)
    ex = Extract(p)
    ex.run(generic)
    generic.save(ex, target)
    for b in generic.books:
        result[b.path.name] = b.counts()

    # 2) 검산표 (본 파일)
    main = sb.Book(out_dir / f"4조참치_{group}_검산표_{stamp}.xlsx", styled=True, link_text=LINK_TEXT)
    makers = {"00_회사목록": lambda: sheet_company(p), "01_사업보고서목록": lambda: sheet_reports(p),
              "02_재무": lambda: sheet_fin(p), "02_배당표": lambda: sheet_div(p, ex), "02_배당표_전체항목": lambda: sheet_div_items(p, ex),
              "04_배당금지급": lambda: sheet_cf(p), "05_배당결정공시": lambda: sheet_decision(p),
              "06_주식총수": lambda: sheet_share(p, ex), "07_최대주주": lambda: sheet_holder(p, ex),
              "08_위험사건": lambda: csv_sheet(p, "risk_events", "위험 사건 후보"),
              "08-1_감사의견원문": lambda: csv_sheet(p, "audit_from_documents", "원문 감사의견"),
              "08-2_감사의견API": lambda: csv_sheet(p, "audit_api", "감사의견 API"),
              "08-3_공시사건후보": lambda: csv_sheet(p, "filing_event_candidates", "공시 사건 후보"),
              "08-4_사건조회범위": lambda: csv_sheet(p, "events_coverage", "사건 조회 범위"),
              "09_주석목록": lambda: sheet_notes(p)}
    for name, desc in MAIN_SHEETS:
        cols, rows, formulas = makers[name]()
        main.put(name, desc, cols, rows, formulas)
    main.save(common_guide(f"4조참치 {group} 검산표", "회사·사업보고서·재무·배당·주식 총수·최대주주·위험 사건·주석 목록. "
                           "재무제표 모든 줄은 '재무제표전체', 공시 목록은 '공시목록', 사업보고서 정형 표 전부는 '사업보고서표_N' 파일",
                           main.counts(), target))
    result[main.path.name] = main.counts()

    # 3) 재무제표 전체
    fsb = sb.Book(out_dir / f"4조참치_{group}_재무제표전체_{stamp}.xlsx", styled=False, link_text=LINK_TEXT)
    sheets = {name: fsb.sheet(name, f"OpenDART 재무제표 {name[5:]} 모든 줄 (4조 fnltt, {YEARS.start}~{YEARS.stop - 1} 사업보고서)", fs_cols())
              for name, _ in FS_SHEETS}
    fs_rows(p, sheets)
    for s in sheets.values():
        s.close()
    fsb.save(common_guide(f"4조참치 {group} 재무제표 전체", "4조가 받은 OpenDART 단일회사 전체 재무제표의 모든 계정 줄 (당기·전기·전전기 금액 그대로)",
                          fsb.counts(), target))
    result[fsb.path.name] = fsb.counts()

    # 4) 공시 목록
    fb = sb.Book(out_dir / f"4조참치_{group}_공시목록_{stamp}.xlsx", styled=False, link_text=LINK_TEXT)
    for name, _, tpl, desc in FILING_SHEETS:
        fb.put(name, desc + " (4조 수집분 전부, 2015-01 이후)", filing_cols(tpl), filing_rows(p, tpl))
    fb.save(common_guide(f"4조참치 {group} 공시 목록", "4조가 받은 OpenDART 공시 목록 전부 (정기공시 · 주요사항보고 · 거래소공시)", fb.counts(), target))
    result[fb.path.name] = fb.counts()
    return result


def our_companies(url: str) -> set[str]:
    with db.connect(url) as conn:
        return {r["corp_code"] for r in db.fetch_dicts(conn, "SELECT corp_code FROM core.core_company")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="4조참치 자료 전부를 우리 전수 검산표 형식 엑셀로 내보냄")
    ap.add_argument("--src", type=Path, default=SRC, help="4조 원본 폴더")
    ap.add_argument("--out-dir", type=Path, default=PARTNER, help="엑셀을 둘 폴더 (받은 파일 링크가 이 폴더의 원본/ 기준)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소 (뺄 우리 회사 목록)")
    ap.add_argument("--stamp", help="파일 이름 끝 (기본: 오늘 YYYYMMDD)")
    ap.add_argument("--group", choices=sorted(GROUPS), default="대조군", help="대조군: 우리 638사 밖 · 겹침: 우리 638사와 겹치는 회사")
    args = ap.parse_args()
    for f, counts in build(args.src, our_companies(args.url), args.out_dir, args.stamp, group=args.group).items():
        print(f, " · ".join(f"{k} {v:,}행" for k, v in counts.items()))
