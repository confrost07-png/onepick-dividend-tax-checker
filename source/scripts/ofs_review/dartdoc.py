"""DART 공시 원문 읽기 도우미: 접수번호 → 목차(섹션) → 섹션 글자. 받은 HTML은 cache/에 저장해 다시 받지 않는다."""
import hashlib
import html
import os
import re
import subprocess
import time

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "raw", "dart_cache")  # source/core/dart_doc.py와 같은 캐시
os.makedirs(CACHE, exist_ok=True)


def _decode(raw: bytes) -> str:
    head = raw[:3000].decode("ascii", "ignore").lower()
    enc = "cp949" if ("euc-kr" in head or "ks_c_5601" in head) else "utf-8"
    return raw.decode(enc, "replace")


def get(url: str) -> str:
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if os.path.exists(path):
        return _decode(open(path, "rb").read())
    for _ in range(3):
        r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            open(path, "wb").write(r.stdout)
            time.sleep(0.4)
            return _decode(r.stdout)
        time.sleep(2)
    raise RuntimeError(f"받지 못함: {url}")


def lines(url: str) -> list[str]:
    """문서 전체를 표 한 줄 = 한 줄 글자로 (칸은 ' | '로 구분)."""
    x = re.sub(r"\s+", " ", get(url))  # 원래 줄바꿈은 없애고
    x = re.sub(r"(?i)</t[dh]>", " | ", x)
    x = re.sub(r"(?i)</tr>|</table>|<table[^>]*>", "\x00", x)  # 표 한 줄마다 줄을 나눈다
    x = re.sub(r"(?i)(</p>|<br\s*/?>)(?![^<]*</t[dh]>)", "\x00", x)  # 표 밖 문단도 나눈다
    x = html.unescape(re.sub(r"<[^>]+>", " ", x))
    return [re.sub(r" +", " ", ln).strip() for ln in x.split("\x00") if ln.strip()]


def toc(rcp_no: str) -> list[dict]:
    s = get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}")
    pat = (r"node\d\['text'\] = \"([^\"]*)\";.*?node\d\['rcpNo'\] = \"(\d+)\";\s*node\d\['dcmNo'\] = \"(\d+)\";"
           r"\s*node\d\['eleId'\] = \"(\d+)\";\s*node\d\['offset'\] = \"(\d+)\";\s*node\d\['length'\] = \"(\d+)\";"
           r"\s*node\d\['dtd'\] = \"([^\"]+)\"")
    out = [dict(zip(["text", "rcpNo", "dcmNo", "eleId", "offset", "length", "dtd"], m)) for m in re.findall(pat, s, re.S)]
    title = re.search(r"<title>([^<]*)", s)
    for o in out:
        o["title"] = title.group(1) if title else ""
    return out


def section_text(node: dict) -> str:
    url = ("https://dart.fss.or.kr/report/viewer.do?rcpNo={rcpNo}&dcmNo={dcmNo}&eleId={eleId}"
           "&offset={offset}&length={length}&dtd={dtd}").format(**node)
    return "\n".join(lines(url))


def find(rcp_no: str, *words: str) -> list[dict]:
    nodes = toc(rcp_no)
    return [n for n in nodes if all(w in re.sub(r"\s", "", n["text"]) for w in words)]
