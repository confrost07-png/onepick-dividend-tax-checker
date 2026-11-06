"""배당·주주환원 정책 문서(기업가치 제고 계획·기업지배구조보고서·주주환원 공정공시)를 문서째 받아 글자와 문단으로 나눈다.

DART 공시 1건 = 본문 1개 + 첨부서류 0~n개. 첨부(기타공시첨부서류·기타공개첨부서류)에 실제 계획서·보고서가
들어 있는 경우가 많아 둘 다 받는다. 원본 HTML은 그대로 파일로 두고(해시 기록), DB에는 글자와 문단을 넣는다.
문단은 원문 글자 그대로이며 요약·생성하지 않는다 (검색만, report/검증/조문_코드_대응표.md 원칙).
"""
import hashlib
import html
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import dart_doc as dd

KINDS = [("기업가치 제고 계획", r"기업가치"), ("기업지배구조보고서", r"지배구조보고서"),
         ("주주환원·배당정책 공정공시", r"주주환원|배당정책|주주가치")]
FILTER = "|".join(p for _, p in KINDS)
CHUNK = 600  # 문단을 이어 붙일 최대 글자 수
PDF_TOOL = Path(__file__).resolve().parents[2] / "data" / "raw" / "bin" / "pdf_text"  # swiftc source/scripts/pdf_text.swift


def doc_kind(report_nm: str) -> str:
    return next((k for k, p in KINDS if re.search(p, report_nm or "")), "기타")


@dataclass
class Document:
    dcm_no: str      # 'body', 첨부 dcmNo, 첨부 PDF는 'dcmNo-n'
    name: str
    url: str
    raw: bytes
    file_type: str = "html"


def pdf_pages(raw: bytes) -> list[str]:
    """PDF → 쪽별 글자 (macOS PDFKit, source/scripts/pdf_text.swift를 컴파일한 도구)."""
    if not PDF_TOOL.exists():
        subprocess.run(["swiftc", "-O", str(PDF_TOOL.parents[3] / "source" / "scripts" / "pdf_text.swift"), "-o", str(PDF_TOOL)], check=True)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(raw)
        f.flush()
        r = subprocess.run([str(PDF_TOOL), f.name], capture_output=True)
    if r.returncode != 0:
        return []
    return r.stdout.decode("utf-8", "replace").split("\f")


def text_of(d: Document) -> tuple[str, list[tuple[int | None, str]]]:
    """문서 → (전체 글자, [(쪽, 문단)]). PDF는 쪽마다 따로 자른다."""
    if d.file_type == "pdf":
        pages = [re.sub(r"[ \t]+", " ", p).strip() for p in pdf_pages(d.raw)]
        parts = [(i, c) for i, p in enumerate(pages, 1) for c in chunks(p)]
        return "\n\f\n".join(pages), parts
    text = html_to_text(d.raw.decode("utf-8", "replace"))
    return text, [(None, c) for c in chunks(text)]


def html_to_text(page: str) -> str:
    """HTML → 글자. 표 칸은 ' | ', 줄·문단·표 행은 줄바꿈. style·script는 버린다."""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|li|table|title)>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", " | ", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    lines = [re.sub(r"[ \t ]+", " ", ln).strip(" |") for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def chunks(text: str, size: int = CHUNK) -> list[str]:
    """줄을 순서대로 이어 size 글자 안쪽 문단으로. 한 줄이 size보다 길면 그 줄 하나가 한 문단."""
    out, cur = [], ""
    for ln in text.splitlines():
        if cur and len(cur) + 1 + len(ln) > size:
            out.append(cur)
            cur = ln
        else:
            cur = f"{cur}\n{ln}" if cur else ln
    if cur:
        out.append(cur)
    return out


def documents(rcept_no: str) -> list[Document]:
    """공시 본문(목차가 있으면 목차 순서대로 이어 붙임)과 첨부서류들."""
    out = []
    title, nodes = dd.filing(rcept_no)
    if nodes:
        pages = [dd.get(n.url) for n in nodes]
        out.append(Document("body", title, nodes[0].url, "\n".join(pages).encode("utf-8")))
    else:
        page = dd.get(f"{dd.BASE}/dsaf001/main.do?rcpNo={rcept_no}")
        m = re.search(r'viewDoc\("(\d+)", "(\d+)", "(\d+)", "(\d+)", "(\d+)", "([^"]+)"', page)
        if m:
            url = dd.Node("", *m.groups()).url
            out.append(Document("body", title, url, dd.get(url).encode("utf-8")))
    main = dd.get(f"{dd.BASE}/dsaf001/main.do?rcpNo={rcept_no}")
    seen = set()
    for m in re.finditer(r'<option[^>]*value="rcpNo=(\d+)&amp;dcmNo=(\d+)"[^>]*>(.*?)</option>', main, re.S):
        rcp, dcm = m.group(1), m.group(2)
        if (rcp, dcm) in seen:
            continue
        seen.add((rcp, dcm))
        name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))).strip()
        name = re.sub(r"^\d{4}\.\d{2}\.\d{2}\s*", "", name)
        url = f"{dd.BASE}/report/viewer.do?rcpNo={rcp}&dcmNo={dcm}&eleId=0&offset=0&length=0&dtd=HTML"
        page = dd.get(url)
        files = re.findall(r'href="(/report/download\.do\?[^"]+)"', page)
        if not files:  # 첨부가 HTML로 들어 있는 경우
            out.append(Document(dcm, name, url, page.encode("utf-8")))
        for k, href in enumerate(files, 1):  # 첨부가 PDF 파일인 경우: 파일을 받음
            link = dd.BASE + html.unescape(href)
            fname = re.sub(r"\+", " ", re.search(r"flNm=([^&]+)", html.unescape(href)).group(1)) if "flNm=" in href else name
            from urllib.parse import unquote
            out.append(Document(f"{dcm}-{k}", f"{name} · {unquote(fname)}", link, dd.get_bytes(link),
                                "pdf" if link.lower().endswith(".pdf") or ".pdf" in unquote(href).lower() else "file"))
    return out


def save_original(root: Path, rcept_no: str, d: Document) -> tuple[str, str]:
    """원본을 root/접수번호/문서.html로 저장 → (상대 경로, sha256)."""
    folder = root / rcept_no
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{d.dcm_no}.{'pdf' if d.file_type == 'pdf' else 'html'}"
    path.write_bytes(d.raw)
    return str(path.relative_to(root.parent.parent)), hashlib.sha256(d.raw).hexdigest()


# --- 검색 조각: 쪽마다 한 벌 ----------------------------------------------------------
# PDF 쪽은 글자층과 OCR이 함께 있다. 검색 조각은 쪽마다 한 벌만 둔다:
#   글자층이 MIN_LAYER자 이상이면 글자층 + OCR에서 글자층에 없는 줄만(그래프 값·그림 속 글자) 보충,
#   그보다 짧으면(그림 쪽) OCR 정정본, 없으면 OCR 전체. OCR 원본은 raw.policy_page_ocr에 그대로 남는다.
MIN_LAYER = 40
SAME_BIGRAMS = 0.7  # 숫자 없는 줄: 두 글자 묶음이 이 비율 이상 글자층에 있으면 같은 줄(OCR 오타)로 본다. 한 글자 오타가 묶음 두 개를 깨므로 글자 단위 약 85% 유사에 해당


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def supplement_lines(layer: str, ocr: str) -> list[str]:
    """OCR 줄 중 글자층에 없는 줄만 (순서 유지, 같은 줄 반복은 한 번).

    - 2글자 미만 줄은 뺀다
    - 공백을 빼고 글자층에 그대로 들어 있으면 이미 있는 줄
    - 숫자가 든 줄은 그대로 들어 있을 때만 이미 있는 줄로 본다 (그래프 값을 잘못 버리지 않게)
    - 숫자 없는 줄은 두 글자 묶음의 SAME_BIGRAMS(0.7) 이상이 글자층에 있으면 OCR 오타로 보고 뺀다
    """
    flat = _squash(layer)
    grams = _bigrams(flat)
    out, seen = [], set()
    for line in ocr.splitlines():
        s = _squash(line)
        if len(s) < 2 or s in seen or s in flat:
            continue
        if not re.search(r"\d", s):
            g = _bigrams(s)
            if g and len(g & grams) / len(g) >= SAME_BIGRAMS:
                continue
        seen.add(s)
        out.append(line.strip())
    return out


def page_chunks(layer: str, ocr: str, corrected: str | None) -> list[tuple[str, str]]:
    """PDF 한 쪽의 검색 조각 [(method, 문단)]. 쪽마다 한 벌 (위 설명)."""
    layer = re.sub(r"[ \t]+", " ", layer or "").strip()
    source, tag = (corrected, "OCR 정정") if corrected else (ocr or "", "OCR")
    if len(_squash(layer)) >= MIN_LAYER:
        extra = supplement_lines(layer, source)
        return [("글자층", c) for c in chunks(layer)] + [(f"{tag} 보충", c) for c in chunks("\n".join(extra))]
    if _squash(source):
        return [(tag, c) for c in chunks(source)]
    return [("글자층", c) for c in chunks(layer)]  # OCR도 비면 짧은 글자층이라도 남긴다


# --- 정정 공시 연결 -----------------------------------------------------------------
_ROOT = re.compile(r'alertInvestNotice\("(\d{14})",\s*"\d*",\s*"(\d{14})"')


def root_rcept_no(main_page: str, rcept_no: str) -> str | None:
    """DART 공시 화면(dsaf001/main.do)에서 최초 접수번호를 읽는다. 일반 공시는 자기 번호, 정정 공시는 처음 낸 공시 번호.

    화면 스크립트의 alertInvestNotice(접수번호, 문서번호, 최초 접수번호, …) 세 번째 값. 못 찾으면 None.
    """
    m = _ROOT.search(main_page or "")
    return m.group(2) if m and m.group(1) == rcept_no else None


def latest_versions(filings: list[tuple[str, str | None]]) -> dict[str, str]:
    """[(접수번호, 최초 접수번호)] → {접수번호: 같은 묶음의 최신 접수번호}. 최초 번호를 모르면 자기 묶음."""
    latest: dict[str, str] = {}
    for rcept, root in filings:
        key = root or rcept
        latest[key] = max(latest.get(key, rcept), rcept)
    return {rcept: latest[root or rcept] for rcept, root in filings}
