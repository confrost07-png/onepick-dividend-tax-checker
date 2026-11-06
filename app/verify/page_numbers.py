"""② 화면 대조: 같은 화면을 웹(8000)과 Streamlit에서 연 뒤 보이는 글자(innerText)를 저장하고, 숫자만 골라 견준다.

1) 받기 서버를 띄운다:  .venv/bin/python app/verify/page_numbers.py serve --dir <폴더> [--port 8765]
2) 브라우저에서 각 화면을 열고 콘솔에서 아래 한 줄을 실행해 글자를 보낸다(파일 이름: web_<화면>.txt / st_<화면>.txt).
     fetch('http://127.0.0.1:8765/web_home.txt',{method:'POST',body:document.querySelector('main').innerText})
3) 견준다:  .venv/bin/python app/verify/page_numbers.py compare --dir <폴더> [--out 결과.md]

숫자는 '1,234' '12.3' '−4.5' 같은 덩어리로 뽑고(쉼표 빼고 같은 값으로 셈), 한쪽에만 있는 숫자를 그 앞뒤 글자와 함께 적는다.
화면 틀(메뉴·아래쪽 안내·Streamlit 단추 글자)에서 나온 숫자도 섞이므로, 결과는 사람이 한 번 읽어 판단한다.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

NUM = re.compile(r"[−-]?\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> Counter:
    return Counter(m.group().replace(",", "").replace("−", "-") for m in NUM.finditer(text))


def context(text: str, num: str, width: int = 24) -> str:
    for m in NUM.finditer(text):
        if m.group().replace(",", "").replace("−", "-") == num:
            a, b = max(0, m.start() - width), min(len(text), m.end() + width)
            return text[a:b].replace("\n", " ")
    return ""


def compare(folder: Path) -> list[dict]:
    out = []
    for web in sorted(folder.glob("web_*.txt")):
        name = web.stem[4:]
        st_ = folder / f"st_{name}.txt"
        if not st_.exists():
            out.append({"page": name, "missing": True})
            continue
        wt, stt = web.read_text(encoding="utf-8"), st_.read_text(encoding="utf-8")
        wn, sn = numbers(wt), numbers(stt)
        only_web, only_st = wn - sn, sn - wn
        out.append({"page": name, "web": sum(wn.values()), "st": sum(sn.values()), "same": sum((wn & sn).values()),
                    "only_web": [(n, c, context(wt, n)) for n, c in sorted(only_web.items())],
                    "only_st": [(n, c, context(stt, n)) for n, c in sorted(only_st.items())]})
    return out


def report(rows: list[dict]) -> str:
    lines = ["| 화면 | 웹 숫자 | Streamlit 숫자 | 겹침 | 웹에만 | Streamlit에만 |", "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        if r.get("missing"):
            lines.append(f"| {r['page']} | – | (Streamlit 글 없음) | | | |")
            continue
        lines.append(f"| {r['page']} | {r['web']} | {r['st']} | {r['same']} | {sum(c for _, c, _ in r['only_web'])} | {sum(c for _, c, _ in r['only_st'])} |")
    for r in rows:
        if r.get("missing") or not (r["only_web"] or r["only_st"]):
            continue
        lines += ["", f"### {r['page']}"]
        lines += [f"- 웹에만 `{n}`×{c}: …{ctx}…" for n, c, ctx in r["only_web"]]
        lines += [f"- Streamlit에만 `{n}`×{c}: …{ctx}…" for n, c, ctx in r["only_st"]]
    return "\n".join(lines) + "\n"


def serve(folder: Path, port: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            name = Path(self.path).name
            if not re.fullmatch(r"(web|st)_[\w-]+\.txt", name):
                self.send_response(400); self.end_headers(); return  # noqa: E702
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            (folder / name).write_bytes(body)
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()  # noqa: E702
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    HTTPServer(("127.0.0.1", port), H).serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["serve", "compare"])
    ap.add_argument("--dir", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(Path(a.dir), a.port)
        return 0
    text = report(compare(Path(a.dir)))
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
