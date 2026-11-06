"""원천 자료(회사 목록·배당 표 전체 항목·배당 결정 공시·KIND 고배당 공시)를 DART 원문에서 다시 읽어 칸마다 대조한다.

재무 숫자(02 재무·04·04-2)는 source/core/dart_verify.py가 맡고, 여기서는 그 밖의 원천 표를 맡는다.
결과는 core.core_source_verify 한 칸 = 한 행. 값은 글자로 두고(날짜·구분 글자 포함) 숫자면 숫자로 비교한다.
"""
import html
import re

from core import dart_doc as dd

ENGINE = "source/core/source_verify.py"
MATCH, MISMATCH, NOT_FOUND = "일치", "불일치", "원문에서 못 찾음"


def _num(s):
    if s is None:
        return None
    c = str(s).strip().replace(",", "").replace(" ", "")
    if c in ("", "-", "－"):
        return None
    neg = c.startswith("(") or c.startswith("-")
    try:
        v = float(c.strip("()-"))
    except ValueError:
        return None
    return -v if neg else v


def compare(db_value, src_value, tol: float = 0.0) -> str:
    """두 값(글자)이 같은지. 둘 다 숫자로 읽히면 숫자로, 아니면 공백을 뺀 글자로. '-'와 빈칸은 같은 것으로 본다."""
    if src_value is None:
        return NOT_FOUND
    a, b = _num(db_value), _num(src_value)
    if a is not None and b is not None:
        return MATCH if abs(a - b) <= tol else MISMATCH
    blank = lambda x: x is None or str(x).strip() in ("", "-", "－", "None")  # noqa: E731
    if blank(db_value) and blank(src_value):
        return MATCH
    norm = lambda x: re.sub(r"\s|ㆍ|·", "", str(x or ""))  # noqa: E731
    return MATCH if norm(db_value) == norm(src_value) else MISMATCH


def result(target, corp, year, key, item, db_value, src_value, rcept, note="", tol=0.0) -> dict:
    return {"target": target, "corp_code": corp, "bsns_year": year, "ref": key, "item": item,
            "db_value": None if db_value is None else str(db_value), "src_value": None if src_value is None else str(src_value),
            "result": compare(db_value, src_value, tol), "src_rcept_no": rcept, "note": note, "engine": ENGINE}


# --- 회사 개황 ---------------------------------------------------------------------------------


def company_info(corp_code: str) -> dict:
    """DART 기업개황 팝업 → 공시회사명·종목코드·법인구분·결산월·업종명."""
    h = dd.get(f"{dd.BASE}/dsae001/selectPopup.ax?selectKey={corp_code.zfill(8)}")
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    out = {}
    for key, pat in (("name", r"공시회사명 (.+?) 종목코드"), ("stock_code", r"종목코드 (\S*) 대표자명"),
                     ("market", r"법인구분 (\S+)"), ("fiscal_month", r"결산월 (\d+)월"), ("industry", r"업종명 (.+?) 설립일")):
        m = re.search(pat, t)
        if m:
            out[key] = m.group(1).strip()
    return out


MARKET = {"유가증권시장": "코스피", "코스닥시장": "코스닥", "코넥스시장": "코넥스", "기타법인": "기타"}


# --- 사업보고서 배당 표 -----------------------------------------------------------------------------

ITEMS = ["주당액면가액", "(연결)당기순이익", "(별도)당기순이익", "(연결)주당순이익", "현금배당금총액", "주식배당금총액",
         "(연결)현금배당성향", "현금배당수익률", "주식배당수익률", "주당현금배당금", "주당주식배당"]


def item_key(label: str) -> str | None:
    """'주당 현금배당금(원)' → '주당현금배당금'. 표 행 머리가 항목이 아니면 None."""
    s = re.sub(r"\s|\(백만원\)|\(원\)|\(%\)|\(주\)|\(천원\)", "", label or "")
    return next((k for k in ITEMS if s == k or s.startswith(k)), None)


_CONT = re.compile(r"^(보통|우선|종류|의결권|-$|－$|대주주|소액|\d*우선|구형|신형|전환|기타|제\d|\d종|배당주|상환|계$|중간)")


def dividend_table(lines: list[str]) -> list[tuple[str, str, list[str]]]:
    """배당 표 → [(항목, 주식 종류, [당기, 전기, 전전기] 칸 글자)]. 종류 칸이 없는 행은 종류 '-'.
    항목 머리 없이 이어지는 행(예: '우선주 | 60 | 40 | 20')은 바로 위 항목의 다른 종류."""
    out, cur, started = [], None, False
    for ln in lines:
        cells = [c.strip() for c in ln.split("|")]
        while cells and cells[-1] == "":
            cells.pop()
        if not cells:
            continue
        if re.sub(r"\s", "", cells[0]) in ("구분", "구 분") and any("당기" in c for c in cells):
            started = True
            continue
        if not started:
            continue
        k = item_key(cells[0])
        if k:
            cur = k
            rest = cells[1:]
        elif cur and len(cells) >= 2 and _CONT.match(re.sub(r"\s", "", cells[0])):
            rest = cells
        elif cur is None:
            continue  # 머리 아래 '제 66기 | 제 65기 …' 같은 줄
        else:
            break
        if len(rest) >= 4:
            kind, vals = rest[0], rest[1:4]
        elif k is None:
            kind, vals = rest[0], rest[1:4]
        else:
            kind, vals = "-", rest[:3]
        out.append((cur, kind, vals))
    return out


def stock_kind(k: str) -> str:
    k = re.sub(r"\s", "", k or "")
    if k in ("", "-"):
        return "-"
    if "우선" in k or "종류" in k or "없는" in k:
        return "우선"
    return "보통" if "보통" in k or "있는" in k else k


def dividend_section(rcp: str):
    """사업보고서 → (공시 제목, 기간 연도, 배당 표 줄)."""
    title, nodes = dd.filing(rcp)
    sec = [n for n in nodes if "배당에관한사항" in n.text.replace(" ", "")]
    if not sec:
        return title, []
    return title, dd.section_lines(sec[:1])


# --- 배당 결정 공시 -------------------------------------------------------------------------------


def decision_all(lines: list[str]) -> dict:
    """현금ㆍ현물배당결정 본문 → 칸별 글자. 같은 머리가 뒤(기타 사항 글)에 또 나오면 앞의 것."""
    out, last = {}, None
    for ln in lines:
        cells = [c.strip() for c in ln.split("|")]
        head = re.sub(r"^\d+\.\s*", "", cells[0]).replace(" ", "")
        val = cells[1] if len(cells) > 1 else ""
        if head == "배당구분":
            out.setdefault("div_kind", val)
        elif head == "배당종류":
            out.setdefault("div_type", val)
        elif head.startswith("1주당배당금"):
            last = "dps"
            if len(cells) > 2:
                out["dps_common_won" if "보통" in cells[1] else "dps_pref_won"] = cells[2]
        elif head.startswith("시가배당율") or head.startswith("시가배당률"):
            last = "yield"
            if len(cells) > 2:
                out["yield_common_pct" if "보통" in cells[1] else "yield_pref_pct"] = cells[2]
        elif head in ("종류주식", "우선주식") and last in ("dps", "yield"):
            out.setdefault("dps_pref_won" if last == "dps" else "yield_pref_pct", val)
        elif head.startswith("-차등배당"):
            out.setdefault("differential", val)
        elif head.startswith("배당금총액"):
            out.setdefault("total_won", val)
        elif head.startswith("배당기준일"):
            out.setdefault("record_date", val)
        elif head.startswith("배당금지급예정일"):
            out.setdefault("pay_date", val)
        elif head.startswith("주주총회예정일"):
            out.setdefault("agm_date", val)
        elif head.startswith("이사회결의일"):
            out.setdefault("board_date", val)
        if not head.startswith(("1주당배당금", "시가배당", "종류주식", "우선주식", "-차등배당")):
            last = None
    return out


DECISION_FIELDS = ["div_kind", "div_type", "dps_common_won", "dps_pref_won", "yield_common_pct", "yield_pref_pct",
                   "differential", "total_won", "record_date", "pay_date", "agm_date", "board_date"]


# --- KIND 고배당기업 공시 -------------------------------------------------------------------------


def kind_fields(lines: list[str]) -> dict:
    out = {}
    for ln in lines:
        cells = [c.strip() for c in ln.split("|")]
        head = cells[0].replace(" ", "")
        val = cells[1] if len(cells) > 1 else ""
        if "고배당기업여부" in head:
            out["is_high_dividend"] = val
        elif head.startswith("2024.12.31.이속하는사업연도의배당소득"):
            out["b2024_won"] = val
        elif "증가율" in head:
            out["growth_pct"] = val
        elif "배당성향" in head and head.startswith("직전사업연도"):
            out["prev_payout_pct"] = val
            m = re.search(r"\((\d{4})\)", cells[0])
            if m:
                out["prev_year"] = m.group(1)
        elif "이익배당금액" in head and head.startswith("직전사업연도"):
            out["prev_d_won"] = val
        elif "이익배당금액" in head and head.startswith("전전사업연도"):
            out["prevprev_d_won"] = val
        elif re.fullmatch(r"(\d+\.)?결정일자", head):  # 번호는 서식마다 다름 (4. / 6.)
            out["decision_date"] = val
    return out


KIND_FIELDS = ["is_high_dividend", "b2024_won", "prev_year", "prev_payout_pct", "prev_d_won", "prevprev_d_won", "growth_pct",
               "decision_date"]
