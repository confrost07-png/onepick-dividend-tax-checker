"""OpenDART 원문 XML(사업보고서 zip 안의 본문) 표 읽기.

DART 서식의 정형 표는 <TABLE-GROUP ACLASS="DIVIDEND"> 처럼 표 종류 코드가 붙어 있고, 값 칸(<TE>)에는
ACODE(항목 코드)가 붙어 있다. OpenDART 정기보고서 API도 이 칸들을 읽어 만든다.
여기서는 표 묶음마다 행렬(rowspan·colspan을 펼친 칸)을 만들어, 원문 글자를 그대로 돌려준다.
XML은 &cr; 같은 비표준 엔티티와 깨진 태그가 섞여 있어 정규식으로 읽는다.
"""
import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


def decode(raw: bytes) -> str:
    """머리에 utf-8이라 적혀 있어도 실제로는 cp949인 파일이 섞여 있다."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", "replace")


def read_report(zip_path: Path, rcept_no: str) -> str | None:
    """사업보고서 zip에서 본문 XML(감사보고서 첨부 _00760 등 제외)을 글자로. 파일이 없으면 None."""
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        main = f"{rcept_no}.xml" if f"{rcept_no}.xml" in names else names[0]
        return decode(z.read(main))


def clean(s: str) -> str:
    s = re.sub(r"&cr;", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


@dataclass
class Cell:
    text: str
    tag: str = "TD"     # TH 머리 · TD 글자 · TE 값 · TU 단위·기준일
    acode: str = ""     # 값 칸 항목 코드 (TE의 ACODE, TU의 AUNIT)
    spanned: bool = False  # 위·왼쪽 칸이 rowspan·colspan으로 덮은 자리


@dataclass
class Table:
    head: list[list[Cell]] = field(default_factory=list)
    body: list[list[Cell]] = field(default_factory=list)


@dataclass
class Group:
    aclass: str
    title: str          # 이 표 묶음 앞의 가장 가까운 목차 제목
    tables: list[Table] = field(default_factory=list)

    def unit_cells(self) -> dict[str, str]:
        """표 위 '(기준일 : …) (단위 : …)' 칸: AUNIT 코드 → 글자 (AUNITVALUE가 있으면 그 값도)."""
        out = {}
        for t in self.tables:
            for row in t.head + t.body:
                for c in row:
                    if c.tag == "TU" and not c.spanned and c.acode:
                        out.setdefault(c.acode, c.text)
        return out


_CELL = re.compile(r"<(TH|TD|TE|TU)\b([^>]*)>(.*?)</\1>", re.S)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_TITLE = re.compile(r"<TITLE[^>]*>(.*?)</TITLE>", re.S)
_GROUP = re.compile(r'<TABLE-GROUP\b([^>]*)>(.*?)</TABLE-GROUP>', re.S)
_TABLE = re.compile(r"<TABLE\b[^>]*>(.*?)</TABLE>", re.S)


def _rows(part: str, carry: dict[int, list]) -> list[list[Cell]]:
    """<TR> 묶음을 칸 행렬로. carry = 열 번호 → [남은 행 수, 칸] (rowspan이 THEAD에서 TBODY로 넘어가지는 않음)."""
    out = []
    for tr in re.findall(r"<TR\b[^>]*>(.*?)</TR>", part, re.S):
        row: list[Cell] = []
        col = 0

        def fill_carry():
            nonlocal col
            while col in carry:
                left, cell = carry[col]
                row.append(Cell(cell.text, cell.tag, cell.acode, True))
                carry[col][0] -= 1
                if carry[col][0] <= 0:
                    del carry[col]
                col += 1

        for tag, attrs, inner in _CELL.findall(tr):
            fill_carry()
            a = dict(_ATTR.findall(attrs))
            cell = Cell(clean(inner), tag, a.get("ACODE") or a.get("AUNIT") or "")
            if tag == "TU" and a.get("AUNITVALUE"):
                cell.text = f"{cell.text} [{a['AUNITVALUE']}]".strip()
            cs, rs = int(a.get("COLSPAN", 1) or 1), int(a.get("ROWSPAN", 1) or 1)
            for k in range(cs):
                c = cell if k == 0 else Cell(cell.text, cell.tag, cell.acode, True)
                row.append(c)
                if rs > 1:
                    carry[col] = [rs - 1, cell]
                col += 1
        fill_carry()
        out.append(row)
    return out


def tables_of(body: str) -> list[Table]:
    out = []
    for tb in _TABLE.findall(body):
        t = Table()
        head = re.search(r"<THEAD\b[^>]*>(.*?)</THEAD>", tb, re.S)
        rest = tb[head.end():] if head else tb
        if head:
            t.head = _rows(head.group(1), {})
        t.body = _rows(rest, {})
        out.append(t)
    return out


def groups(text: str, skip_xbrl: bool = True) -> list[Group]:
    """본문의 정형 표 묶음 전부 (순서대로). XBRL 재무제표·주석 묶음({XBRL}…)은 기본으로 뺀다 (재무 API·주석 파일과 겹침)."""
    titles = [(m.start(), clean(m.group(1))) for m in _TITLE.finditer(text)]
    out, ti, last = [], 0, ""
    for m in _GROUP.finditer(text):
        while ti < len(titles) and titles[ti][0] < m.start():
            last = titles[ti][1]
            ti += 1
        a = dict(_ATTR.findall(m.group(1)))
        aclass = a.get("ACLASS", "")
        if not aclass or (skip_xbrl and aclass.startswith("{XBRL}")):
            continue
        out.append(Group(aclass, last, tables_of(m.group(2))))
    return out


def first(gs: list[Group], aclass: str) -> Group | None:
    return next((g for g in gs if g.aclass == aclass), None)


def value_rows(g: Group) -> list[list[Cell]]:
    """값 칸(TE)이 하나라도 있는 본문 행 (기준일·단위 표 제외)."""
    return [r for t in g.tables for r in t.body if any(c.tag == "TE" for c in r)]


def header(g: Group) -> list[str]:
    """값이 있는 표의 머리 마지막 행 글자 (열 이름). 머리가 여러 행이면 위 행 글자를 앞에 붙임."""
    for t in g.tables:
        if t.head and any(any(c.tag == "TE" for c in r) for r in t.body):
            n = max(len(r) for r in t.head)
            names = []
            for j in range(n):
                parts = []
                for r in t.head:
                    if j < len(r) and r[j].text and r[j].text not in parts:
                        parts.append(r[j].text)
                names.append(" ".join(parts))
            return names
    return []


def grid(g: Group):
    """표 묶음의 모든 행: (표 번호, 행 번호, '머리'/'본문', 칸 글자들, 값 칸 코드들). 덮인 칸도 글자를 채움."""
    for ti, t in enumerate(g.tables, 1):
        n = 0
        for kind, rows in (("머리", t.head), ("본문", t.body)):
            for r in rows:
                n += 1
                yield ti, n, kind, [c.text for c in r], [c.acode for c in r if c.tag in ("TE", "TU") and not c.spanned and c.acode]


def number(s: str | None) -> float | None:
    """원문 숫자 글자 → 숫자. '-'·빈칸·글자는 None. (1,234)·△1,234는 음수."""
    t = (s or "").replace(",", "").replace(" ", "").strip()
    neg = t.startswith("(") and t.endswith(")") or t.startswith("△") or t.startswith("▲")
    t = t.strip("()△▲")
    try:
        v = float(t)
    except ValueError:
        return None
    return -abs(v) if neg else v


_OFFSET = {"당기": 0, "전기": 1, "전전기": 2}


def dividend_items(g: Group) -> list[tuple[str, str, int, str]]:
    """배당 표(DIVIDEND): (구분, 주식 종류, 열(0 당기 · 1 전기 · 2 전전기), 원문 글자). 종류 칸이 없는 행은 '-'."""
    head = header(g)
    cols = [(j, _OFFSET[h.split()[0]]) for j, h in enumerate(head) if h and h.split()[0] in _OFFSET]
    out = []
    for row in value_rows(g):
        if not cols:  # 머리가 없는 표: 끝 3칸을 당기·전기·전전기로 봄
            cols = [(len(row) - 3 + k, k) for k in range(3)]
        label = row[0].text
        # 종류 칸은 TE일 때도 TD일 때도 있음. 구분 칸이 colspan으로 덮은 자리면 종류 칸이 없는 행
        kind = "-" if len(row) < 2 or (row[1].spanned and row[1].text == label) else row[1].text
        for j, off in cols:
            if j < len(row):
                out.append((label, kind or "-", off, row[j].text))
    return out


def share_totals(g: Group) -> tuple[list[str], dict[str, dict[str, tuple[str, str]]], dict[str, str]]:
    """주식의 총수 표(TOT_STK): (주식 종류 순서, 종류 → 항목 코드 → (항목 이름, 원문 글자), 항목 이름 → 비고).
    항목 코드는 합계 열의 SUM_ 앞붙임을 뗀 것 (ISU_STK1 발행할 주식의 총수 … FLT_STK 유통주식수)."""
    head = header(g)
    kinds, data, notes = [], {}, {}
    for row in value_rows(g):
        label = next((c.text for c in reversed(row[:2]) if c.tag != "TE" and c.text), row[0].text)
        for j, c in enumerate(row):
            if c.tag != "TE" or c.spanned:
                continue
            h = head[j] if j < len(head) else f"칸{j + 1}"
            if "비고" in h:
                if c.text not in ("", "-"):
                    notes[label] = c.text
                continue
            kind = h.replace("주식의 종류", "").strip() or h
            code = c.acode[4:] if c.acode.startswith("SUM_") else c.acode
            if kind not in data:
                kinds.append(kind)
                data[kind] = {}
            data[kind].setdefault(code or label, (label, c.text))
    return kinds, data, notes


HOLDER_FIELDS = [("성명", ("성명",)), ("관계", ("관계",)), ("주식 종류", ("종류",)),
                 ("기초 주식수", ("기초", "주식수")), ("기초 지분율", ("기초", "지분율")),
                 ("기말 주식수", ("기말", "주식수")), ("기말 지분율", ("기말", "지분율")), ("비고", ("비고",))]


def holders(g: Group) -> list[dict[str, str]]:
    """최대주주 및 특수관계인 표(BSH_SPCL): 행마다 {성명, 관계, 주식 종류, 기초·기말 주식수·지분율, 비고} 원문 글자."""
    head = [re.sub(r"\s+", "", h) for h in header(g)]
    pos = {}
    for name, words in HOLDER_FIELDS:
        j = next((j for j, h in enumerate(head) if all(w in h for w in words) and j not in pos.values()), None)
        if j is not None:
            pos[name] = j
    if len(pos) < 7:  # 머리를 못 읽으면 표준 서식 순서
        pos = {name: j for j, (name, _) in enumerate(HOLDER_FIELDS)}
    return [{name: (row[j].text if j < len(row) else "") for name, j in pos.items()} for row in value_rows(g)]
