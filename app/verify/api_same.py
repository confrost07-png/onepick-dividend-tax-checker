"""① 데이터 대조: 웹 화면이 8000 서버에서 받는 JSON과 Streamlit 화면이 받는 값(common.api)이 같은지 본다.

실행(저장소 맨 위): .venv/bin/python app/verify/api_same.py [--base http://127.0.0.1:8000] [--out 결과.json]
- 웹 app/web/src/api.ts가 부르는 주소마다 HTTP로 받고, Streamlit은 같은 FastAPI 함수를 바로 불러 받는다.
- 두 값을 JSON으로 펼쳐 칸 하나하나(숫자 포함) 견준다. 다르면 경로와 두 값을 적는다.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402  (streamlit 캐시는 화면 밖에서도 그냥 함수처럼 돈다)
from common import api  # noqa: E402

COMPANIES = ["005930", "033780"]  # 홈 예시 칩 두 곳 + 아래에서 목록 앞쪽 몇 곳을 더 본다


def http(base: str, path: str, body: dict | None = None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def flat(x, path="") -> dict:
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            out.update(flat(v, f"{path}.{k}"))
        return out or {path: {}}
    if isinstance(x, list):
        out = {}
        for i, v in enumerate(x):
            out.update(flat(v, f"{path}[{i}]"))
        return out or {path: []}
    return {path: x}


def compare(web, st_) -> list[tuple[str, object, object]]:
    a, b = flat(web), flat(st_)
    return [(k, a.get(k, "∅"), b.get(k, "∅")) for k in sorted(set(a) | set(b)) if a.get(k, "∅") != b.get(k, "∅")]


def cases(base: str):
    """(이름, 웹 HTTP 호출, Streamlit 호출). 이름은 웹 api.ts 함수 이름을 따른다."""
    q = urllib.parse.quote
    lst = api.companyList()
    codes = COMPANIES + [c["code"] for c in lst[:: max(1, len(lst) // 6)]][:6]
    out = [
        ("funnel", lambda: http(base, "/api/judgement/funnel"), api.funnel),
        ("analysis", lambda: http(base, "/api/analysis"), api.analysis),
        ("events", lambda: http(base, "/api/analysis/events"), api.events),
        ("movement", lambda: http(base, "/api/analysis/movement"), api.movement),
        ("script", lambda: http(base, "/api/chat/script"), api.script),
        ("companyList", lambda: http(base, "/api/companies/list"), api.companyList),
        ("personas", lambda: http(base, "/api/personas"), api.personas),
        ("evidence", lambda: http(base, "/api/law/evidence"), api.evidence),
        ("lawPassages", lambda: http(base, "/api/law/passages"), api.lawPassages),
        ("spread", lambda: http(base, "/api/column/spread"), api.spread),
        ("race(0)", lambda: http(base, "/api/column/race?pick=0"), lambda: api.race(0)),
        ("separate(30000000)", lambda: http(base, "/api/tax/separate?amount=30000000"), lambda: api.separate(30_000_000)),
        ("search(삼성)", lambda: http(base, "/api/companies?q=" + q("삼성")), lambda: api.search("삼성")),
        ("isaIrp(기본)", lambda: http(base, "/api/isa-irp?profit=3000000&irp=9000000&pension_saving=0"), lambda: api.isaIrp(None, 3_000_000, 9_000_000, 0)),
        ("isaIrp(low)", lambda: http(base, "/api/isa-irp?bracket=low&profit=3000000&irp=9000000&pension_saving=0"), lambda: api.isaIrp("low", 3_000_000, 9_000_000, 0)),
        ("parse(holdings)", lambda: http(base, "/api/chat/parse", {"kind": "holdings", "text": "삼성전자 100주", "dividend_type": None}),
         lambda: api.parse("holdings", "삼성전자 100주")),
        ("checkup(예시)", lambda: http(base, "/api/checkup", CHECKUP), lambda: api.checkup(CHECKUP)),
    ]
    out += [(f"company({c})", (lambda c=c: http(base, "/api/companies/" + c)), (lambda c=c: api.company(c))) for c in dict.fromkeys(codes)]
    out += [(f"persona({p['id']})", (lambda p=p: http(base, "/api/personas/" + q(p["id"]))), (lambda p=p: api.persona(p["id"]))) for p in api.personas()]
    return out


CHECKUP = {"holdings": [{"company": "삼성전자", "shares": 2000}, {"company": "케이티앤지", "shares": 3000}],
           "interest": 6_000_000, "other_domestic": 3_000_000, "other_foreign": None, "base": 80_000_000, "has_other_income": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows, bad = [], 0
    for name, web, st_ in cases(a.base):
        w, s = web(), st_()
        diff = compare(w, s)
        n = len(flat(w))
        bad += bool(diff)
        rows.append({"api": name, "fields": n, "same": not diff, "diff": [list(map(str, d)) for d in diff[:10]]})
        print(f"{'같음' if not diff else '다름'}  {name}  칸 {n:,}개" + (f"  다른 칸 {len(diff)}개: {diff[:3]}" if diff else ""))
    print(f"\n{len(rows)}개 API 중 {len(rows) - bad}개 같음, {bad}개 다름")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
