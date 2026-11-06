"""전수 검산표 형식(source/scripts/export_review_workbook.py)을 스트리밍(write-only) 엑셀로 쓰기.

수십만~수백만 행도 메모리에 올리지 않고 한 행씩 쓴다. 모양은 검산표와 같다:
남색 머리 · 맨 끝 노란 검토 칸 3개(목록 고르기) · 연두색 수식 칸 · '원문 열기' 링크 · 틀 고정 · 필터,
앞에 안내 · 진행현황 · 항목_설명 시트. 링크는 엑셀 링크 수 한도(시트당 65,530개)를 피하려고 HYPERLINK 수식으로 단다.
한 시트가 MAX_ROWS를 넘으면 '이름 (2)' 시트로 이어 쓴다.
"""
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from scripts.export_review_workbook import (BOX, F, FILL, FORMULA_FILL, HEAD, NUM, REVIEW_COLS, REVIEWERS, STATES, Col)

MAX_ROWS = 1_000_000  # 엑셀 한 시트 한도 1,048,576행보다 조금 적게
CELL_MAX = 32_000  # 엑셀 한 칸 글자 한도 32,767자

_HEAD_FONT = Font(name=F, bold=True, color="FFFFFF")
_HEAD_FONT_Y = Font(name=F, bold=True, color="000000")
_BODY = Font(name=F, size=10)
_LINK = Font(name=F, size=10, color="0563C1", underline="single")
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_WRAP = Alignment(wrap_text=True, vertical="top")


def _q(s: str) -> str:
    return str(s).replace('"', '""')


class Sheet:
    """시트 하나(넘치면 여러 개)에 행을 이어 쓴다. rows의 각 행은 열 이름 → 값."""

    def __init__(self, book: "Book", name: str, desc: str, cols: list[Col], formulas: dict | None, link_text: dict):
        self.book, self.name, self.desc = book, name, desc
        self.cols = cols + REVIEW_COLS
        self.formulas = formulas or {}
        self.link_text = link_text
        self.letter = {c.name: get_column_letter(j) for j, c in enumerate(self.cols, 1)}
        self.first_yellow = len(cols) + 1
        self.parts: list[tuple[str, object, int]] = []  # (시트 이름, ws, 행 수)
        self._new_part()

    def _new_part(self):
        n = len(self.parts) + 1
        title = re.sub(r"[\[\]:*?/\\]", "_", self.name if n == 1 else f"{self.name} ({n})")  # 엑셀 시트 이름에 못 쓰는 글자
        ws = self.book.wb.create_sheet(title[:31])
        for j, c in enumerate(self.cols, 1):
            ws.column_dimensions[get_column_letter(j)].width = c.width
        ws.freeze_panes = "D2"
        head = []
        for j, c in enumerate(self.cols, 1):
            cell = WriteOnlyCell(ws, c.name)
            yellow = j >= self.first_yellow
            cell.font, cell.fill = (_HEAD_FONT_Y, FILL) if yellow else (_HEAD_FONT, HEAD)
            cell.alignment, cell.border = _CENTER, BOX
            head.append(cell)
        ws.append(head)
        self.parts.append((title[:31], ws, 0))

    def add(self, r: dict):
        title, ws, n = self.parts[-1]
        if n >= MAX_ROWS:
            self._new_part()
            title, ws, n = self.parts[-1]
        i = n + 2
        styled = self.book.styled
        out = []
        for j, c in enumerate(self.cols, 1):
            if c.kind == "formula":
                v = self.formulas[c.name](self.letter, i)
            else:
                v = r.get(c.name)
                if isinstance(v, float) and v != v:
                    v = None
                elif isinstance(v, str) and len(v) > CELL_MAX:
                    v = v[:CELL_MAX] + " …(엑셀 칸 한도로 잘림)"
            if c.kind == "link":
                if v:
                    cell = WriteOnlyCell(ws, f'=HYPERLINK("{_q(v)}","{self.link_text.get(c.name, "원문 열기")}")')
                    cell.font = _LINK
                    if styled:
                        cell.border = BOX
                    out.append(cell)
                else:
                    out.append(self._plain(ws, None, styled))
                continue
            if j >= self.first_yellow:
                cell = WriteOnlyCell(ws, v)
                cell.fill = FILL
                if styled:
                    cell.font, cell.border = _BODY, BOX
                out.append(cell)
            elif c.kind in ("num", "pct", "formula"):
                cell = WriteOnlyCell(ws, v)
                if c.kind == "num":
                    cell.number_format = NUM
                elif c.kind == "pct":
                    cell.number_format = "0.00"
                else:
                    cell.fill = FORMULA_FILL
                if styled:
                    cell.font, cell.border = _BODY, BOX
                out.append(cell)
            else:
                out.append(self._plain(ws, v, styled))
        ws.append(out)
        self.parts[-1] = (title, ws, n + 1)

    @staticmethod
    def _plain(ws, v, styled):
        if not styled:
            return v
        cell = WriteOnlyCell(ws, v)
        cell.font, cell.border = _BODY, BOX
        return cell

    def close(self) -> int:
        st, rv = self.letter["검토 상태"], self.letter["검토자"]
        last_col = get_column_letter(len(self.cols))
        for _, ws, n in self.parts:
            last = max(n + 1, 2)
            for col, options in ((st, STATES), (rv, REVIEWERS)):
                dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True, showErrorMessage=True,
                                    errorTitle="목록에서 고르기", error=", ".join(options) + " 중에서 고르세요")
                dv.add(f"{col}2:{col}{last}")
                ws.data_validations.append(dv)
            ws.auto_filter.ref = f"A1:{last_col}{n + 1}"
        return sum(n for _, _, n in self.parts)


class Book:
    """엑셀 한 권. 안내 · 진행현황 · 항목_설명을 먼저 만들고, 내용은 save()에서 채운다."""

    def __init__(self, path: Path, styled: bool = True, link_text: dict | None = None):
        self.path, self.styled = path, styled
        self.link_text = link_text or {}
        self.wb = Workbook(write_only=True)
        self.guide_ws = self.wb.create_sheet("안내")
        self.prog_ws = self.wb.create_sheet("진행현황")
        self.desc_ws = self.wb.create_sheet("항목_설명")
        self.sheets: list[Sheet] = []

    def sheet(self, name: str, desc: str, cols: list[Col], formulas: dict | None = None) -> Sheet:
        s = Sheet(self, name, desc, cols, formulas, self.link_text)
        self.sheets.append(s)
        return s

    def put(self, name: str, desc: str, cols: list[Col], rows, formulas: dict | None = None) -> int:
        s = self.sheet(name, desc, cols, formulas)
        for r in rows:
            s.add(r)
        return s.close()

    def counts(self) -> dict[str, int]:
        return {title: n for s in self.sheets for title, _, n in s.parts}

    def _guide(self, rows: list[tuple]):
        ws = self.guide_ws
        ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 22, 110
        for i, (a, b) in enumerate(rows, 1):
            ca = WriteOnlyCell(ws, a)
            ca.font = Font(name=F, bold=True, size=14 if i == 1 else 10)
            cb = WriteOnlyCell(ws, b)
            cb.font, cb.alignment = Font(name=F, size=10), _WRAP
            if a in ("고칠 칸", "작성 예시"):
                cb.fill = FILL
            ws.append([ca, cb])

    def _progress(self):
        ws = self.prog_ws
        head = ["시트", "전체 행"] + STATES + ["미검토", "진행률"] + REVIEWERS
        for j in range(1, len(head) + 1):
            ws.column_dimensions[get_column_letter(j)].width = 16 if j == 1 else 11
        ws.freeze_panes = "B2"

        def row(vals, bold=False):
            out = []
            for j, v in enumerate(vals, 1):
                c = WriteOnlyCell(ws, v)
                c.font, c.border = Font(name=F, size=10, bold=bold), BOX
                c.number_format = "0.0%" if j == 7 else NUM
                out.append(c)
            ws.append(out)

        hrow = []
        for h in head:
            c = WriteOnlyCell(ws, h)
            c.font, c.fill, c.border, c.alignment = _HEAD_FONT, HEAD, BOX, _CENTER
            hrow.append(c)
        ws.append(hrow)
        i = 2
        for s in self.sheets:
            st, rv = s.letter["검토 상태"], s.letter["검토자"]
            for title, _, n in s.parts:
                last = n + 1
                a, b = f"'{title}'!${st}$2:${st}${last}", f"'{title}'!${rv}$2:${rv}${last}"
                row([title, n] + [f'=COUNTIF({a},"{x}")' for x in STATES] +
                    [f"=B{i}-SUM(C{i}:E{i})", f"=IF(B{i}=0,0,SUM(C{i}:E{i})/B{i})"] + [f'=COUNTIF({b},"{p}")' for p in REVIEWERS])
                i += 1
        t = i
        row(["합계"] + [f"=IF(B{t}=0,0,SUM(C{t}:E{t})/B{t})" if j == 7 else f"=SUM({get_column_letter(j)}2:{get_column_letter(j)}{t - 1})"
                       for j in range(2, len(head) + 1)], bold=True)

    def _describe(self):
        ws = self.desc_ws
        head = [("시트", 16), ("열", 26), ("뜻", 60), ("원천 (파일.열)", 46), ("더한 값·계산 방법", 60)]
        for j, (_, w) in enumerate(head, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "C2"
        hrow = []
        for h, _ in head:
            c = WriteOnlyCell(ws, h)
            c.font, c.fill, c.border = _HEAD_FONT, HEAD, BOX
            hrow.append(c)
        ws.append(hrow)
        n = 1
        for s in self.sheets:
            for col in s.cols:
                out = []
                for v in (s.name, col.name, col.meaning, col.source, col.how):
                    c = WriteOnlyCell(ws, v)
                    c.font, c.border, c.alignment = _BODY, BOX, _WRAP
                    out.append(c)
                ws.append(out)
                n += 1
        ws.auto_filter.ref = f"A1:E{n}"

    def save(self, guide_rows: list[tuple]):
        self._guide(guide_rows)
        self._progress()
        self._describe()
        self.wb.calculation.fullCalcOnLoad = True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(self.path)
