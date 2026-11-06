"""시연 10개사 기업가치 제고 계획 공시 → 배당 목표·정책 문장 검토표 (F-03·F-07, 사람이 원문 확인).

실행: .venv/bin/python -m scripts.export_policy_review [--reviewer 박예지] [--out 파일] [--all-versions]
정정된 공시는 같은 계획의 최신 판만 넣는다 (core.v_policy_filing_latest). 옛 판까지 보려면 --all-versions.
후보 문장은 두 곳에서 뽑는다.
  본문: source/core/policy_extract.py가 공시 본문(2. 주요 내용 · 6. 기타)에서 원문 글자 그대로
  첨부: raw.policy_chunk의 첨부 HTML·PDF 문단(글자층 또는 OCR) 중 배당·자사주·주주환원·투자 문단. 쪽 번호를 원문 위치에 적는다
검토자는 노란 칸(검토 상태·검토자·F-03 목표로 쓰기·목표 대상 연도·메모)만 채우고, scripts.load_policy_review로 DB에 넣는다.

--bundle: 검토표와 첨부 PDF 쪽 그림(JPEG)을 zip 하나로 묶는다. 표의 '쪽 그림' 칸은 zip 안 쪽그림/ 폴더의 상대 경로라
          압축을 푼 뒤 열어야 링크가 열린다. 쪽 그림은 data/raw/ocr_pages/에 있으면 쓰고, 없으면 pdf_ocr --render로 그린다.
"""
import argparse
import re
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from PIL import Image

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import dart_doc as dd
from core import db
from core import policy_extract as pe

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "output" / "tables"
# 원본 PDF·쪽 그림·OCR 도구는 메인 폴더 data/에 있다 (워크트리에서 실행하면 메인 폴더도 찾는다)
DATA_ROOTS = [ROOT / "data"] + ([ROOT.parents[2] / "data"] if ROOT.parent.name == "worktrees" else [])
PAGE_DIR = "쪽그림"
PAGE_SCALE, JPEG_QUALITY, MAX_WIDTH = 1.5, 80, 1600
REVIEWERS = ["박예지", "금민권", "한상범", "김민지", "조진영"]
STATES = ["확인완료", "확인불가", "정정됨(배제)"]
YEARS = ["2024", "2025", "2026", "2027"]
F = "Arial"
HEAD, FILL = PatternFill("solid", fgColor="1F3864"), PatternFill("solid", fgColor="FFFF00")
OCR_FILL = PatternFill("solid", fgColor="FCE4D6")
COLS = [("순위", 6), ("회사명", 14), ("corp_code", 10), ("공시명", 30), ("접수번호", 15), ("공시일", 11), ("순번", 6),
        ("원문 위치", 26), ("읽은 방식", 9), ("분류", 10), ("원문 문장 (글자 그대로)", 70), ("코드가 읽은 목표 종류", 12),
        ("목표 값", 10), ("분모·기준 메모", 26), ("2025 지배주주 순이익(원)", 18), ("원문", 10), ("쪽 그림", 10),
        ("검토 상태", 12), ("검토자", 10), ("F-03 목표로 쓰기", 10), ("목표 대상 연도", 10), ("메모", 30)]
NAMES = [c for c, _ in COLS]
YELLOW_FROM = NAMES.index("검토 상태") + 1
TEXT_COL, NI_COL, LINK_COL, HOW_COL, PAGE_COL = (NAMES.index(n) + 1 for n in (
    "원문 문장 (글자 그대로)", "2025 지배주주 순이익(원)", "원문", "읽은 방식", "쪽 그림"))


def category(text: str) -> str | None:
    return next((c for c, pat in pe.CATEGORIES if re.search(pat, text)), None)


def page_name(rcept_no: str, dcm_no: str, page: int) -> str:
    return f"{PAGE_DIR}/{rcept_no}_{dcm_no}_{page:03d}.jpg"


def attachment_items(conn, rcept_no: str) -> list[tuple[pe.PolicyItem, str, dict | None]]:
    """첨부 HTML·PDF 문단 중 정책 문단 → (항목, 읽은 방식, 쪽 정보). 본문(body)은 policy_extract가 따로 읽는다."""
    out = []
    for r in db.fetch_dicts(conn, """
            SELECT c.rcept_no, c.dcm_no, c.seq, c.page, c.text, c.method, d.doc_name, d.file_type, d.file_path
            FROM raw.policy_chunk c JOIN raw.policy_document d USING (rcept_no, dcm_no)
            WHERE c.rcept_no = %s AND c.dcm_no <> 'body' ORDER BY c.dcm_no, c.page NULLS FIRST, c.seq""", (rcept_no,)):
        cat = category(r["text"])
        if cat is None:
            continue
        doc = (r["doc_name"] or "").split(" · ")[-1]
        where = f"첨부 {doc}" + (f" {r['page']}쪽" if r["page"] else "")
        kind, value, note = pe.read_target(r["text"]) if cat == "배당 목표" else ("", "", "")
        page = ({"rcept_no": r["rcept_no"], "dcm_no": r["dcm_no"], "page": r["page"], "file_path": r["file_path"]}
                if r["file_type"] == "pdf" and r["page"] else None)
        out.append((pe.PolicyItem(where, cat, r["text"], kind, value, note), r["method"], page))
    return out


def rows(conn, all_versions: bool = False):
    """all_versions가 False면 정정으로 바뀐 옛 판은 빼고 같은 계획의 최신 판만 (core.v_policy_filing_latest)."""
    out = []
    filings = db.fetch_dicts(conn, """
        SELECT d.rank, d.corp_code, d.corp_name, f.rcept_no, f.report_nm, f.rcept_dt, y.ni_owner_won
        FROM core.core_demo_company d JOIN raw.dart_filing_list f USING (corp_code)
        LEFT JOIN core.v_financial_year_verified y ON y.corp_code = d.corp_code AND y.bsns_year = 2025
        LEFT JOIN core.v_policy_filing_latest v ON v.rcept_no = f.rcept_no
        WHERE f.report_nm ~ '기업가치제고계획' AND f.report_nm !~ '예고' AND (%s OR v.is_latest IS NOT FALSE)
        ORDER BY d.rank, f.rcept_no DESC""", (all_versions,))
    for f in filings:
        items = [(it, "본문", None) for it in pe.extract(dd.body_lines(f["rcept_no"]))]
        items += attachment_items(conn, f["rcept_no"])
        if not items:
            items = [(pe.PolicyItem("-", "-", "(본문·첨부에서 배당·자사주·투자 문장을 찾지 못함: 원문 확인 필요)"), "-", None)]
        for i, (it, how, page) in enumerate(items, 1):
            out.append([f["rank"], f["corp_name"], f["corp_code"], " ".join(f["report_nm"].split()), f["rcept_no"],
                        str(f["rcept_dt"]), i, it.section, how, it.category, it.text, it.target_kind, it.target_value,
                        it.basis_note, float(f["ni_owner_won"]) if f["ni_owner_won"] is not None else None,
                        f"{dd.BASE}/dsaf001/main.do?rcpNo={f['rcept_no']}", page, None, None, None, None, None])
    return out


def _find(rel: str) -> Path | None:
    return next((r / rel for r in DATA_ROOTS if (r / rel).exists()), None)


def _render_tool(tmp: Path) -> Path:
    """pdf_ocr 도구. data/raw/bin에 없으면 source/scripts/pdf_ocr.swift를 임시 폴더에 컴파일한다."""
    tool = _find("raw/bin/pdf_ocr")
    if tool:
        return tool
    tool = tmp / "pdf_ocr"
    subprocess.run(["swiftc", "-O", str(ROOT / "source" / "scripts" / "pdf_ocr.swift"), "-o", str(tool)], check=True)
    return tool


def page_jpeg(p: dict, out: Path, tmp: Path, tools: dict) -> str:
    """쪽 그림 하나를 JPEG로 만든다. 돌려주는 값: 그림을 얻은 곳(기존 그림 / 새로 그림)."""
    png = _find(f"raw/ocr_pages/{p['rcept_no']}_{p['dcm_no']}_{p['page']:03d}.png")
    how = "기존 그림"
    if png is None:
        pdf = _find(p["file_path"])
        if pdf is None:
            raise FileNotFoundError(f"원본 PDF 없음: data/{p['file_path']}")
        if "tool" not in tools:
            tools["tool"] = _render_tool(tmp)
        png = tmp / "page.png"
        r = subprocess.run([str(tools["tool"]), "--render", str(pdf), str(p["page"]), str(png), str(PAGE_SCALE)],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"쪽 그림 실패 {pdf} {p['page']}: {r.stderr.decode('utf-8', 'replace').strip()}")
        how = "새로 그림"
    with Image.open(png) as im:
        im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)))
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return how


def bundle(data: list[list], out_zip: Path, reviewer: str | None) -> dict:
    """검토표 + 쪽그림/ 을 zip 하나로. zip 안 맨 위 폴더 이름 = zip 이름."""
    top = out_zip.stem
    counts = {"기존 그림": 0, "새로 그림": 0}
    with tempfile.TemporaryDirectory() as t:
        tmp, done, tools = Path(t), {}, {}
        stage = tmp / top
        for r in data:
            p = r[PAGE_COL - 1]
            if p:
                name = page_name(p["rcept_no"], p["dcm_no"], p["page"])
                if name not in done:
                    done[name] = page_jpeg(p, stage / name, tmp, tools)
                    counts[done[name]] += 1
        write(data, stage / f"{top}.xlsx", reviewer, pages=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(tmp).as_posix())
    return counts


def _head(ws, cols, yellow_from=None):
    for j, (name, width) in enumerate(cols, 1):
        yellow = yellow_from is not None and j >= yellow_from
        c = ws.cell(1, j, name)
        c.font = Font(name=F, bold=True, color="000000" if yellow else "FFFFFF")
        c.fill = FILL if yellow else HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = width


def write_review(ws, data: list[list], reviewer: str | None, pages: bool = False):
    _head(ws, COLS, YELLOW_FROM)
    reviewer_col = NAMES.index("검토자") + 1
    for i, r in enumerate(data, 2):
        for j, v in enumerate(r, 1):
            if j == reviewer_col and reviewer:
                v = reviewer
            page, v = (v, None) if j == PAGE_COL else (None, v)
            c = ws.cell(i, j, v)
            c.font = Font(name=F, size=10)
            c.alignment = Alignment(wrap_text=j == TEXT_COL, vertical="top")
            if j == NI_COL:
                c.number_format = "#,##0"
            if j == LINK_COL and v:
                c.hyperlink, c.value = v, "원문 열기"
                c.font = Font(name=F, size=10, color="0563C1", underline="single")
            if pages and page:
                c.hyperlink = page_name(page["rcept_no"], page["dcm_no"], page["page"])
                c.value = "쪽 그림 열기"
                c.font = Font(name=F, size=10, color="0563C1", underline="single")
            if j == HOW_COL and str(v).startswith("OCR"):
                c.fill = OCR_FILL
            if j >= YELLOW_FROM:
                c.fill = FILL
    last = max(len(data) + 1, 2)
    for name, opts in (("검토 상태", STATES), ("검토자", REVIEWERS), ("F-03 목표로 쓰기", ["예", "아니오"]),
                       ("목표 대상 연도", YEARS)):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        letter = get_column_letter(NAMES.index(name) + 1)
        dv.add(f"{letter}2:{letter}{last}")
        ws.add_data_validation(dv)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def write_progress(ws, data: list[list]):
    """회사별 검토 진행. 검토표 칸을 COUNTIFS로 세므로 검토자가 채우는 대로 바뀐다."""
    cols = [("순위", 6), ("회사명", 16), ("후보 행", 9), ("확인완료", 9), ("확인불가", 9), ("정정됨(배제)", 11),
            ("미검토", 9), ("F-03 목표 '예'", 12), ("목표 대상 연도 적음", 14), ("OCR 문단", 9)]
    _head(ws, cols)
    rng = {n: f"검토표!${get_column_letter(NAMES.index(n) + 1)}$2:${get_column_letter(NAMES.index(n) + 1)}${len(data) + 1}"
           for n in ("회사명", "검토 상태", "F-03 목표로 쓰기", "목표 대상 연도", "읽은 방식")}
    companies = list(dict.fromkeys((r[0], r[1]) for r in data))
    for i, (rank, name) in enumerate(companies, 2):
        k = f'{rng["회사명"]},$B{i}'
        values = [rank, name, f"=COUNTIFS({k})"]
        values += [f'=COUNTIFS({k},{rng["검토 상태"]},"{s}")' for s in STATES]
        values += [f"=C{i}-D{i}-E{i}-F{i}", f'=COUNTIFS({k},{rng["F-03 목표로 쓰기"]},"예")',
                   f'=COUNTIFS({k},{rng["목표 대상 연도"]},"<>")', f'=COUNTIFS({k},{rng["읽은 방식"]},"OCR*")']
        for j, v in enumerate(values, 1):
            ws.cell(i, j, v).font = Font(name=F, size=10)
    t = len(companies) + 2
    ws.cell(t, 2, "합계").font = Font(name=F, bold=True)
    for j in range(3, len(cols) + 1):
        L = get_column_letter(j)
        ws.cell(t, j, f"=SUM({L}2:{L}{t - 1})").font = Font(name=F, bold=True)
    ws.freeze_panes = "C2"


def write(data: list[list], out: Path, reviewer: str | None = None, pages: bool = False):
    wb = Workbook()
    g = wb.active
    g.title = "안내"
    notes = [("먼저", "압축 파일로 받았다면 반드시 압축을 푼 뒤 이 엑셀을 여세요. '쪽 그림 열기'는 같은 폴더의 쪽그림/ 안 그림을 엽니다."),
             ("무엇", "시연 10개사(core.core_demo_company)의 기업가치 제고 계획 공시에서 코드가 뽑은 배당 목표·정책 문장 후보 (PRD v0.2 F-03·F-07)"),
             ("검토자", reviewer or "(검토자 칸에 이름을 고르세요)"),
             ("검토 방법", "'원문 열기'로 공시를 열어 문장이 원문과 같은지, 분류·목표 값이 맞는지 보고 노란 칸을 채웁니다. 첨부 PDF 행은 '쪽 그림 열기'로 그 쪽 그림을 옆에 띄워 대조하세요."),
             ("읽은 방식", "본문 = 공시 본문 표, 글자층 = 첨부 파일 글자, OCR·OCR 정정 = 이미지에서 읽은 글자(주황). OCR 행은 숫자·단위를 원문과 꼭 대조하고, 틀리면 메모에 바른 글자를 적어 주세요. 같은 쪽에 글자층과 OCR 문단이 함께 있으면 원문과 맞는 쪽만 '확인완료', 나머지는 '정정됨(배제)'."),
             ("순서", "'분류'가 배당 목표·주주환원율인 행부터 보세요(카드 ③ 비교와 이행 대조에 쓰임). 자사주·투자 계획은 카드 ⑥에 원문으로만 보입니다."),
             ("F-03 목표로 쓰기", "회사별로 2026 사업연도 배당 목표로 볼 문장 하나만 '예'. 배당성향 목표는 2025 지배주주 순이익을 분모로 환산합니다."),
             ("목표 대상 연도", "목표가 어느 사업연도 배당을 말하는지(예: '2025년 배당성향 50%' → 2025). 2025 이하를 적으면 그해 실제 배당과 대조해 카드 ③ '과거 계획 이행'에 '목표 이상/미만 배당'으로 보여 줍니다. 여러 해에 걸친 목표(예: 2024~2026 평균)는 비우고 메모에 적어 주세요."),
             ("화면 반영", "검토 상태가 '확인완료'인 행만 scripts.load_policy_review로 DB에 들어가고 챗봇 ③·⑥에 보입니다."),
             ("진행현황", "회사별 확인완료·미검토 수가 검토표를 채우는 대로 바뀝니다(엑셀에서 열면 계산)."),
             ("만든 날", f"{date.today().isoformat()} · source/scripts/export_policy_review.py")]
    for i, (a, b) in enumerate(notes, 1):
        g.cell(i, 1, a).font = Font(name=F, bold=True)
        c = g.cell(i, 2, b)
        c.font = Font(name=F)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    g.column_dimensions["A"].width, g.column_dimensions["B"].width = 16, 110
    write_review(wb.create_sheet("검토표"), data, reviewer, pages)
    write_progress(wb.create_sheet("진행현황"), data)
    wb.active = 1
    wb.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="밸류업 배당 목표·정책 검토표 만들기")
    ap.add_argument("--reviewer", choices=REVIEWERS, help="검토자 칸을 이 이름으로 미리 채움")
    ap.add_argument("--bundle", action="store_true", help="검토표와 첨부 PDF 쪽 그림을 zip 하나로 묶기")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--all-versions", action="store_true", help="정정 전 옛 판 공시도 함께 (기본: 같은 계획의 최신 판만)")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    suffix = f"{date.today():%Y%m%d}{'_' + a.reviewer if a.reviewer else ''}"
    out = a.out or OUT_DIR / (f"밸류업_정책_검토_{suffix}.zip" if a.bundle else f"밸류업_정책_검토표_{suffix}.xlsx")
    with db.connect(a.url) as conn:
        data = rows(conn, a.all_versions)
    if a.bundle:
        counts = bundle(data, out, a.reviewer)
        print(f"쪽 그림 {sum(counts.values())}장 (기존 {counts['기존 그림']} · 새로 {counts['새로 그림']}) · "
              f"{out.stat().st_size / 1e6:.1f}MB")
    else:
        write(data, out, a.reviewer)
    print(out, f"{len(data)}행 · 회사 {len({r[2] for r in data})}곳 · 목표 후보 {sum(1 for r in data if r[11])}행 · "
               f"첨부 {sum(1 for r in data if r[8] not in ('본문', '-'))}행(OCR {sum(1 for r in data if str(r[8]).startswith('OCR'))})")
