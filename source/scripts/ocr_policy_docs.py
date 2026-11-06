"""PDF 쪽을 전부 OCR로 읽어 쪽별 결과(raw.policy_page_ocr)와 검색 조각(raw.policy_chunk)에 넣는다.

실행: .venv/bin/python -m scripts.ocr_policy_docs [--limit N] [--redo] [--url ...]
      .venv/bin/python -m scripts.ocr_policy_docs --rechunk   (OCR 없이 검색 조각만 다시 만들기)
- 검색 조각은 쪽마다 한 벌: 글자층이 충분하면 글자층 + 글자층에 없는 OCR 줄만 보충, 그림 쪽은 OCR (rebuild_chunks)
OCR은 macOS 기본 Vision(한국어·영어, source/scripts/pdf_ocr.swift를 data/raw/bin/pdf_ocr로 컴파일). 쪽당 0.3초쯤.
- 글자층이 있는 쪽도 읽는다: 그래프·표 그림 속 글자는 글자층에 없기 때문 (글자층은 그대로 두고 OCR은 보충)
- 2.5배로 읽고, 신뢰도 0.5 미만 줄이 있거나 글자가 안 나오면 4배로 다시 읽어 더 나은 쪽을 고른다
- 빈 쪽·실패도 1행씩 남긴다 → 쪽 수 = 행 수로 '빠짐없이 처리'를 확인 (source/scripts/check_ocr_quality.py --coverage)
- OCR만 출처인 쪽(글자층 40자 미만)과 낮은 줄이 남은 쪽은 needs_review → source/scripts/export_ocr_review.py
- 이미 같은 판(RUN)으로 읽은 문서는 건너뛰어 중간에 멈춰도 이어서 돈다. 사람 검토 칸은 다시 읽어도 지우지 않는다
"""
import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import db
from core import policy_docs as pd_

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "data" / "raw" / "bin" / "pdf_ocr"
RUN = "v2-전쪽"
LOW = 0.5          # 이 값 미만 신뢰도 줄 = 낮은 줄 (Vision 값은 0.3 / 0.5 / 1.0 단계로 나옴, 0.3 줄은 대개 깨진 글자)
MIN_LAYER = 40     # 글자층 글자가 이보다 적으면 OCR만 출처인 쪽
SCALES = (2.5, 4.0)


@dataclass
class PageOCR:
    page: int
    lines: list[tuple[float, str]]  # (신뢰도, 글자)
    scale: float

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.lines)

    @property
    def chars(self) -> int:
        return len(squash(self.text))

    @property
    def low(self) -> list[str]:
        return [t for c, t in self.lines if c < LOW]


def squash(s: str) -> str:
    return "".join(s.split())


def parse(stdout: str, scale: float) -> dict[int, PageOCR]:
    """pdf_ocr 출력 → {쪽: PageOCR}. 덩어리 = '번호\\t줄 수\\t최저\\t평균\\t신뢰도\\x1F글자\\n…'"""
    out = {}
    for block in stdout.split("\f"):
        parts = block.split("\t", 4)
        if len(parts) < 4:
            continue
        lines = []
        for ln in (parts[4].split("\n") if len(parts) == 5 and parts[4] else []):
            conf, _, text = ln.partition("\x1f")
            if text.strip():
                lines.append((float(conf), text.strip()))
        out[int(parts[0])] = PageOCR(int(parts[0]), lines, scale)
    return out


def better(a: PageOCR, b: PageOCR) -> PageOCR:
    """낮은 줄이 적은 쪽, 같으면 글자가 많은 쪽."""
    return min((a, b), key=lambda p: (len(p.low), -p.chars))


def classify(layer_chars: int, r: PageOCR | None) -> tuple[str, bool, int | None]:
    """→ (상태, 검토 필요, 우선순위). 우선순위 1 낮은 줄 남음 / 2 빈 쪽 / 3 그 밖의 OCR만 출처 쪽."""
    if r is None:
        return "실패", True, 1
    status = "글자 있음" if r.chars else "빈 쪽"
    only_ocr = layer_chars < MIN_LAYER
    if r.low:
        return status, True, 1
    if only_ocr and not r.chars:
        return status, True, 2
    if only_ocr:
        return status, True, 3
    return status, False, None


def ocr_pages(pdf: Path, pages: list[int], scale: float = SCALES[0]) -> dict[int, PageOCR]:
    if not TOOL.exists():
        subprocess.run(["swiftc", "-O", str(ROOT / "source" / "scripts" / "pdf_ocr.swift"), "-o", str(TOOL)], check=True)
    out = {}
    for i in range(0, len(pages), 10):  # 10쪽씩
        r = subprocess.run([str(TOOL), str(pdf), ",".join(map(str, pages[i:i + 10])), str(scale)],
                           capture_output=True, timeout=900)
        if r.returncode != 0:  # 파일을 못 열면 0쪽으로 넘기지 않고 멈춘다
            raise RuntimeError(f"OCR 실패 {pdf}: {r.stderr.decode('utf-8', 'replace').strip()}")
        out.update(parse(r.stdout.decode("utf-8", "replace"), scale))
    return out


def ocr(pdf: Path, pages: list[int]) -> dict[int, str]:
    """쪽별 OCR 글자만 (source/scripts/check_ocr_quality.py에서 씀)."""
    return {n: p.text for n, p in ocr_pages(pdf, pages).items()}


def read_document(pdf: Path, n_pages: int) -> dict[int, PageOCR]:
    """전 쪽을 2.5배로 읽고, 낮은 줄이 있거나 글자가 안 나온 쪽만 4배로 다시 읽어 더 나은 결과를 고른다."""
    got = ocr_pages(pdf, list(range(1, n_pages + 1)), SCALES[0])
    again = [n for n, p in got.items() if p.low or not p.chars]
    if again:
        for n, p in ocr_pages(pdf, again, SCALES[1]).items():
            got[n] = better(got[n], p)
    return got


def rebuild_chunks(conn, rcept_no: str, dcm_no: str):
    """PDF 문서의 검색 조각을 쪽마다 한 벌로 다시 만든다 (core.policy_docs.page_chunks).

    글자층이 충분한 쪽은 글자층 + 글자층에 없는 OCR 줄만 보충('OCR 보충'), 그림 쪽은 OCR 한 벌('OCR').
    사람·AI가 정정한 쪽은 정정 글자를 OCR 대신 쓴다('OCR 정정', 'OCR 정정 보충'). OCR 원본은 raw.policy_page_ocr에 그대로.
    """
    layer_pages = conn.execute("SELECT text FROM raw.policy_document WHERE rcept_no = %s AND dcm_no = %s",
                               (rcept_no, dcm_no)).fetchone()[0].split("\n\f\n")
    ocr = {p: (text, status, fixed) for p, text, status, fixed in conn.execute("""
            SELECT page, text, review_status, corrected_text FROM raw.policy_page_ocr
            WHERE rcept_no = %s AND dcm_no = %s""", (rcept_no, dcm_no)).fetchall()}
    conn.execute("DELETE FROM raw.policy_chunk WHERE rcept_no = %s AND dcm_no = %s", (rcept_no, dcm_no))
    rows, seq = [], 0
    for page in range(1, max(len(layer_pages), max(ocr, default=0)) + 1):
        text, status, fixed = ocr.get(page, ("", None, None))
        layer = layer_pages[page - 1] if page <= len(layer_pages) else ""
        for method, c in pd_.page_chunks(layer, text, fixed if status == "정정함" and fixed else None):
            seq += 1
            rows.append((rcept_no, dcm_no, seq, page, c.replace("\x00", ""), method))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO raw.policy_chunk (rcept_no, dcm_no, seq, page, text, method) VALUES (%s,%s,%s,%s,%s,%s)", rows)
    conn.execute("""UPDATE raw.policy_document SET n_ocr_pages =
                    (SELECT count(*) FROM raw.policy_page_ocr WHERE rcept_no = %s AND dcm_no = %s AND ocr_chars > 0)
                    WHERE rcept_no = %s AND dcm_no = %s""", (rcept_no, dcm_no, rcept_no, dcm_no))


def rechunk(url: str):
    """OCR을 다시 하지 않고 PDF 문서 전부의 검색 조각만 다시 만든다 (문서 1개마다 확정)."""
    with db.connect(url) as conn:
        docs = conn.execute("SELECT rcept_no, dcm_no FROM raw.policy_document WHERE file_type = 'pdf' ORDER BY 1, 2").fetchall()
        for k, (rcept_no, dcm_no) in enumerate(docs, 1):
            with conn.transaction():
                rebuild_chunks(conn, rcept_no, dcm_no)
            if k % 50 == 0:
                print(f"    조각 다시 만들기 {k}/{len(docs)}", flush=True)
        conn.commit()
    print(f"  검색 조각 다시 만듦: PDF {len(docs)}개")


def save(conn, d: dict, got: dict[int, PageOCR], error: str | None):
    layer = d["text"].split("\n\f\n")
    rows = []
    for n in range(1, d["n_pages"] + 1):
        lc = len(squash(layer[n - 1])) if n <= len(layer) else 0
        r = got.get(n)
        status, review, prio = classify(lc, r)
        confs = [c for c, _ in r.lines] if r else []
        rows.append((d["rcept_no"], d["dcm_no"], n, RUN, status, lc, r.chars if r else 0, len(confs),
                     len(r.low) if r else 0, min(confs) if confs else None,
                     round(sum(confs) / len(confs), 3) if confs else None, r.scale if r else SCALES[0],
                     "\n".join(r.low) or None if r else None, (r.text if r else "").replace("\x00", ""),
                     error if r is None else None, review, prio))
    with conn.cursor() as cur:  # 검토 칸(reviewer 등)은 건드리지 않는다
        cur.executemany("""
            INSERT INTO raw.policy_page_ocr (rcept_no, dcm_no, page, run, status, layer_chars, ocr_chars, n_lines,
                n_low_lines, conf_min, conf_avg, scale, low_lines, text, note, needs_review, review_priority)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (rcept_no, dcm_no, page) DO UPDATE SET run = EXCLUDED.run, status = EXCLUDED.status,
                layer_chars = EXCLUDED.layer_chars, ocr_chars = EXCLUDED.ocr_chars, n_lines = EXCLUDED.n_lines,
                n_low_lines = EXCLUDED.n_low_lines, conf_min = EXCLUDED.conf_min, conf_avg = EXCLUDED.conf_avg,
                scale = EXCLUDED.scale, low_lines = EXCLUDED.low_lines, text = EXCLUDED.text, note = EXCLUDED.note,
                needs_review = EXCLUDED.needs_review, review_priority = EXCLUDED.review_priority, ocred_at = now()""", rows)
    rebuild_chunks(conn, d["rcept_no"], d["dcm_no"])


def main(url: str, limit: int | None, redo: bool):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        conn.commit()
        docs = db.fetch_dicts(conn, """SELECT rcept_no, dcm_no, file_path, n_pages, text FROM raw.policy_document
                                      WHERE file_type = 'pdf' ORDER BY rcept_no, dcm_no""")
        done = {(r[0], r[1]) for r in conn.execute("""
            SELECT d.rcept_no, d.dcm_no FROM raw.policy_document d JOIN raw.policy_page_ocr p USING (rcept_no, dcm_no)
            WHERE p.run = %s GROUP BY 1, 2, d.n_pages HAVING count(*) = d.n_pages""", (RUN,))}
        total = pages_low = 0
        todo = [d for d in docs if redo or (d["rcept_no"], d["dcm_no"]) not in done][:limit]
        print(f"  PDF {len(docs)}개 중 이번에 읽을 문서 {len(todo)}개 ({sum(d['n_pages'] for d in todo):,}쪽)", flush=True)
        for k, d in enumerate(todo, 1):
            error = None
            try:
                got = read_document(ROOT / "data" / d["file_path"], d["n_pages"])
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                got, error = {}, str(e)[:500]
            with conn.transaction():
                save(conn, d, got, error)
            conn.commit()  # 문서 1개마다 확정
            total += len(got)
            pages_low += sum(1 for p in got.values() if p.low)
            print(f"    {k}/{len(todo)} {d['rcept_no']} {d['dcm_no']}: {len(got)}/{d['n_pages']}쪽"
                  f"{' 실패: ' + error if error else ''} (누적 {total:,}, 낮은 줄 남은 쪽 {pages_low:,})", flush=True)
        print(f"  OCR 끝: {total:,}쪽")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="PDF 전 쪽 OCR")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--redo", action="store_true", help="같은 판으로 읽은 문서도 다시 읽음")
    ap.add_argument("--rechunk", action="store_true", help="OCR은 그대로 두고 검색 조각만 쪽마다 한 벌로 다시 만듦")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    rechunk(a.url) if a.rechunk else main(a.url, a.limit, a.redo)
