"""OCR 사람 검토표 (output/tables/OCR_검토표_YYYYMMDD.xlsx). 쪽 그림과 OCR 글자를 나란히 보고 확인·정정한다.

실행: .venv/bin/python -m scripts.export_ocr_review [--out 파일] [--scale 1.5]
      .venv/bin/python -m scripts.export_ocr_review --sample 95 [--seed 0]   (AI 검토 쪽 사람 표본 확인표)
- 대상: raw.policy_page_ocr에서 needs_review인 쪽 (OCR만 출처인 쪽 + 신뢰도 낮은 줄이 남은 쪽 + 실패)
- 우선순위: 1 낮은 줄 남음·실패 / 2 빈 쪽 / 3 그 밖의 OCR만 출처 쪽
- 쪽 그림은 data/raw/ocr_pages/에 PNG로 만들고 표에서 상대 경로 링크로 연다 (git 제외)
- 검토자는 노란 칸(검토 상태·검토자·정정 글자·메모)만 채우고, scripts.load_ocr_review로 DB에 넣는다
- 이미 DB에 들어간 검토 결과는 노란 칸에 미리 채워 둔다 (이어서 검토)
"""
import argparse
import subprocess
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import db
from scripts.ocr_policy_docs import ROOT, TOOL

OUT_DIR = ROOT / "output" / "tables"
PAGE_DIR = ROOT / "data" / "raw" / "ocr_pages"
REVIEWERS = ["한상범", "김민지", "박예지", "조진영"]
STATES = ["확인완료", "정정함", "확인불가"]
PRIORITY = {1: "1 낮은 줄 남음", 2: "2 빈 쪽", 3: "3 OCR만 출처"}
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
F = "Arial"
HEAD, FILL = PatternFill("solid", fgColor="1F3864"), PatternFill("solid", fgColor="FFFF00")
STATE_FILL = {"확인완료": "C6EFCE", "정정함": "BDD7EE", "확인불가": "F8CBAD"}
COLS = [("우선순위", 13), ("회사명", 14), ("접수번호", 15), ("문서", 12), ("쪽", 5), ("쪽 그림", 9), ("원문", 9),
        ("글자층 글자 수", 8), ("OCR 글자 수", 8), ("낮은 줄 수", 7), ("배율", 5), ("신뢰도 낮은 줄 (먼저 볼 곳)", 30),
        ("OCR 글자", 70), ("검토 상태", 11), ("검토자", 9), ("정정 글자 (정정함일 때 쪽 전체를 고친 글자)", 50), ("메모", 24)]
YELLOW_FROM = 14
GUIDE = [
    "OCR 사람 검토표 — 글자층이 없어 OCR만 출처인 PDF 쪽과, 다시 읽어도 신뢰도 낮은 줄이 남은 쪽",
    "",
    "1. '쪽 그림'을 눌러 원본 쪽을 보고, 'OCR 글자'와 비교합니다. 노란 칸만 채웁니다.",
    "2. 검토 상태: 확인완료 = OCR 글자가 그림과 같음 (읽는 순서 차이는 괜찮음)",
    "             정정함 = 틀린 글자가 있음 → '정정 글자' 칸에 그 쪽 글자 전체를 고쳐 적음 (OCR 글자를 복사해 고치면 편함)",
    "             확인불가 = 그림이 흐리거나 잘려 사람도 읽을 수 없음 (메모에 이유)",
    "3. 빈 쪽(우선순위 2)은 그림에 정말 글자가 없으면 확인완료, 글자가 있으면 정정함으로 글자를 적습니다.",
    "4. 우선순위 1부터 보면 오류가 많은 쪽을 먼저 잡습니다. 숫자(금액·비율·연도)는 특히 꼼꼼히 봅니다.",
    "5. 다 채우면: .venv/bin/python -m scripts.load_ocr_review <이 파일> → DB 반영, 정정 글자는 검색 문단에도 들어감",
    "6. 검토자가 'Claude(AI)'인 행은 AI가 먼저 본 결과입니다 (source/scripts/ocr_ai_review.py). 사람이 확인하면 검토자를 자기 이름으로",
    "   바꿔야 DB에 사람 검토로 들어갑니다. 검토자를 그대로 두면 상태를 바꿔도 반영되지 않습니다.",
    "",
    "신뢰도: macOS Vision이 줄마다 주는 값(0.3 / 0.5 / 1.0). 0.5 미만 줄을 '낮은 줄'로 표시. 낮은 줄이 있으면 4배로 다시 읽음.",
    "만든 코드: source/scripts/export_ocr_review.py · OCR: source/scripts/ocr_policy_docs.py · 쪽 그림 폴더: data/raw/ocr_pages/",
]


def page_png(file_path: str, rcept_no: str, dcm_no: str, page: int, scale: float) -> Path:
    out = PAGE_DIR / f"{rcept_no}_{dcm_no}_{page:03d}.png"
    if not out.exists():
        PAGE_DIR.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([str(TOOL), "--render", str(ROOT / "data" / file_path), str(page), str(out), str(scale)],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"쪽 그림 실패 {file_path} {page}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return out


def sample(data: list[dict], n: int, seed: int) -> list[dict]:
    """AI가 검토한 쪽에서 n쪽을 뽑는다. (우선순위, AI 판정) 묶음마다 크기에 비례해 뽑고(최소 1쪽), 원래 순서를 유지."""
    import random
    pool = [r for r in data if r["reviewer"] == "Claude(AI)"]
    groups: dict[tuple, list[dict]] = {}
    for r in pool:
        groups.setdefault((r["review_priority"], r["review_status"]), []).append(r)
    rng = random.Random(seed)
    picked = []
    for key in sorted(groups, key=str):
        g = groups[key]
        k = min(len(g), max(1, round(n * len(g) / max(1, len(pool)))))
        picked += rng.sample(g, k)
    keep = {id(r) for r in picked}
    return [r for r in data if id(r) in keep]


def rows(conn, scale: float, n_sample: int | None = None, seed: int = 0) -> list[list]:
    data = db.fetch_dicts(conn, """
        SELECT p.*, d.file_path, f.corp_name FROM raw.policy_page_ocr p
        JOIN raw.policy_document d USING (rcept_no, dcm_no) JOIN raw.policy_filing f USING (rcept_no)
        WHERE p.needs_review ORDER BY p.review_priority, f.corp_name, p.rcept_no, p.dcm_no, p.page""")
    if n_sample:
        data = sample(data, n_sample, seed)
    out = []
    for k, r in enumerate(data, 1):
        png = page_png(r["file_path"], r["rcept_no"], r["dcm_no"], r["page"], scale)
        if k % 200 == 0:
            print(f"    쪽 그림 {k}/{len(data)}", flush=True)
        out.append([PRIORITY.get(r["review_priority"], r["review_priority"]), r["corp_name"], r["rcept_no"], r["dcm_no"],
                    r["page"], str(Path("..") / png.relative_to(ROOT / "data")), DART + r["rcept_no"],
                    r["layer_chars"], r["ocr_chars"], r["n_low_lines"], float(r["scale"]),
                    r["low_lines"] or (r["note"] if r["status"] == "실패" else None), r["text"],
                    r["review_status"], r["reviewer"], r["corrected_text"], r["review_note"]])
    return out


SAMPLE_GUIDE = [
    "",
    "[사람 표본 확인] 이 표는 AI(Claude)가 검토한 쪽 중 무작위로 뽑은 표본입니다 (--sample, 시드 고정).",
    "  AI 결과(검토 상태·정정 글자)가 미리 채워져 있습니다. 쪽 그림과 비교해",
    "  - AI 결과가 맞으면: 검토자만 자기 이름으로 바꿉니다 (상태·정정 글자는 그대로)",
    "  - 틀리면: 정정 글자를 그림대로 고치고(정정함), 검토자를 자기 이름으로 바꿉니다. 메모에 틀린 곳을 적어 주세요",
    "  검토자를 바꾼 행만 사람 검토로 들어가고, check_ocr_quality --coverage의 '사람 검토' 수가 늘어납니다.",
    "  AI의 원래 판정은 data/raw/ocr_ai/result_*.jsonl에 남아 있어, 사람 결과와 비교해 AI 정확도를 셀 수 있습니다.",
]


def write(data: list[list], out: Path, sample_mode: bool = False):
    wb = Workbook()
    g = wb.active
    g.title = "안내"
    for i, line in enumerate(GUIDE + (SAMPLE_GUIDE if sample_mode else []), 1):
        g.cell(i, 1, line).font = Font(name=F, bold=i == 1, size=12 if i == 1 else 10)
    g.column_dimensions["A"].width = 120

    ws = wb.create_sheet("검토표")
    for j, (name, width) in enumerate(COLS, 1):
        c = ws.cell(1, j, name)
        c.font = Font(name=F, bold=True, color="000000" if j >= YELLOW_FROM else "FFFFFF")
        c.fill = FILL if j >= YELLOW_FROM else HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = width
    link = Font(name=F, size=10, color="0563C1", underline="single")
    for i, r in enumerate(data, 2):
        for j, v in enumerate(r, 1):
            c = ws.cell(i, j, ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v)  # 엑셀에 못 넣는 제어 문자 제거
            c.font = Font(name=F, size=10)
            c.alignment = Alignment(wrap_text=j in (12, 13, 16), vertical="top")
            if j == 6:
                c.hyperlink, c.value, c.font = v, "그림 열기", link
            if j == 7:
                c.hyperlink, c.value, c.font = v, "원문 열기", link
            if j >= YELLOW_FROM:
                c.fill = FILL
        ws.row_dimensions[i].height = 60
    last = max(len(data) + 1, 2)
    for col, opts in ((14, STATES), (15, REVIEWERS)):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        letter = get_column_letter(col)
        dv.add(f"{letter}2:{letter}{last}")
        ws.add_data_validation(dv)
    for state, color in STATE_FILL.items():  # 검토 상태에 따라 행 왼쪽(우선순위~쪽) 색
        ws.conditional_formatting.add(f"A2:E{last}", FormulaRule(formula=[f'$N2="{state}"'],
                                                                fill=PatternFill("solid", fgColor=color)))
    ws.freeze_panes = "F2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}{last}"

    s = wb.create_sheet("진행현황")
    heads = ["구분", "쪽 수", "확인완료", "정정함", "확인불가", "남음", "진행률"]
    for j, h in enumerate(heads, 1):
        c = s.cell(1, j, h)
        c.font, c.fill = Font(name=F, bold=True, color="FFFFFF"), HEAD
    groups = [("전체", None)] + [(v, v) for v in PRIORITY.values()] + [(f"검토자 {p}", p) for p in REVIEWERS]
    rng = lambda col: f"검토표!${col}$2:${col}${last}"
    for i, (label, key) in enumerate(groups, 2):
        s.cell(i, 1, label).font = Font(name=F)
        if key is None:
            cond = ""
        elif key in REVIEWERS:
            cond = f',{rng("O")},"{key}"'
        else:
            cond = f',{rng("A")},"{key}"'
        total = f'COUNTIFS({rng("C")},"<>"{cond})' if key not in REVIEWERS else f'COUNTIFS({rng("O")},"{key}")'
        s.cell(i, 2, f"={total}")
        for j, state in enumerate(STATES, 3):
            s.cell(i, j, f'=COUNTIFS({rng("N")},"{state}"{cond})')
        s.cell(i, 6, f"=B{i}-C{i}-D{i}-E{i}")
        s.cell(i, 7, f"=IF(B{i}=0,0,(C{i}+D{i})/B{i})").number_format = "0.0%"
        for j in range(2, 7):
            s.cell(i, j).font = Font(name=F)
    s.cell(len(groups) + 3, 1, "정확도 100% 조건: '전체' 행의 남음 0 · 확인불가 0 (확인불가 쪽은 원문 화질 문제로 따로 보고)").font = \
        Font(name=F, size=9, color="555555")
    s.column_dimensions["A"].width = 20
    wb.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OCR 사람 검토표 만들기")
    ap.add_argument("--out", type=Path, default=None, help="기본: OCR_검토표_날짜.xlsx, --sample이면 OCR_사람표본_날짜.xlsx")
    ap.add_argument("--sample", type=int, default=None, help="AI가 검토한 쪽에서 이만큼 무작위로 뽑은 사람 표본 확인표")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scale", type=float, default=1.5, help="쪽 그림 확대 배율")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    with db.connect(a.url) as conn:
        data = rows(conn, a.scale, a.sample, a.seed)
    out = a.out or OUT_DIR / f"OCR_{'사람표본' if a.sample else '검토표'}_{date.today():%Y%m%d}.xlsx"
    write(data, out, sample_mode=bool(a.sample))
    print(out, f"{len(data)}쪽")
