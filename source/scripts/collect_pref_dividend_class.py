"""배당 결정 공시의 '종류주식에 대한 배당 관련 사항' 표 → raw.dividend_decision_class (우선주 종목별 1주당 배당금).

실행: .venv/bin/python -m scripts.collect_pref_dividend_class [--url ...]
- raw.dividend_decision(원천 엑셀 05)은 공시의 '3. 1주당 배당금 - 종류주식' 한 칸만 담아, 우선주가 여러 종목이면 종목별 금액을 모른다.
  공시 본문 아래 표에는 종목마다 1주당 배당금이 있다(예: 두산우 4,050원 · 두산2우B 4,000원).
- 대상: 상장 우선주(raw.krx_pref_stock '상장 중')가 있는 회사의 2025·2026 사업연도 현금배당 결정 공시.
- 원문은 DART 웹 문서(source/core/dart_doc.py, 받은 문서는 data/raw/dart_cache에 둠)를 읽는다. 조회는 DB 연결을 닫은 채로 한다.
- 정정 공시는 정정 전·후 비교표가 위에 있어, 맨 아래 【종류주식에 대한 배당 관련 사항】 표(5칸: 종류주식명·구분·1주당 배당금·시가배당률·총액)만 읽는다.
"""
import argparse
import re

from core import db
from core import dart_doc as dd

HEAD = re.compile(r"종류주식에 대한 배당 관련 사항")
_VIEW = re.compile(r'viewDoc\("(\d+)", "(\d+)", "(\d*)", "(\d*)", "(\d*)", "([^"]*)"')


def number(s: str):
    t = s.replace(",", "").strip()
    return float(t) if re.fullmatch(r"\d+(\.\d+)?", t) else None


def doc_lines(rcept_no: str) -> list[str]:
    page = dd.get(f"{dd.BASE}/dsaf001/main.do?rcpNo={rcept_no}")
    m = _VIEW.search(page)
    if not m:
        return []
    url = (f"{dd.BASE}/report/viewer.do?rcpNo={m.group(1)}&dcmNo={m.group(2)}&eleId={m.group(3)}"
           f"&offset={m.group(4)}&length={m.group(5)}&dtd={m.group(6)}")
    return [re.sub(r"\s+", " ", ln).strip() for ln in dd.table_lines(dd.get(url))]


def class_rows(lines: list[str]) -> list[dict]:
    """맨 아래 【종류주식에 대한 배당 관련 사항】 표의 행 → [{class_name, class_kind, dps_won, total_won}]."""
    starts = [i for i, ln in enumerate(lines) if HEAD.search(ln) and ln.startswith(("【", "["))]
    starts = [i for i in starts if lines[i].startswith("【")] or starts
    if not starts:
        return []
    out = []
    for ln in lines[starts[-1] + 1:]:
        cells = [c.strip() for c in ln.split("|") if c.strip() != ""]
        if len(cells) < 3 or cells[0] in ("종류주식명",):
            if out:
                break
            continue
        dps = number(cells[2])
        if dps is None:
            if out:
                break
            continue
        out.append({"class_name": cells[0], "class_kind": cells[1], "dps_won": dps,
                    "total_won": number(cells[4]) if len(cells) > 4 else None})
    return out


def main(url: str) -> None:
    with db.connect(url) as conn:
        targets = db.fetch_dicts(conn, """
            SELECT DISTINCT d.rcept_no, d.corp_code FROM raw.dividend_decision d
            WHERE d.parse_status = '정상' AND d.div_type LIKE '현금%%' AND d.attributed_year IN (2025, 2026)
              AND EXISTS (SELECT 1 FROM raw.krx_pref_stock p WHERE p.corp_code = d.corp_code AND p.status = '상장 중')
            ORDER BY d.rcept_no""")
    rows, empty = [], []
    for t in targets:  # DB 연결 밖에서 원문 조회
        got = class_rows(doc_lines(t["rcept_no"]))
        if not got:
            empty.append(t["rcept_no"])
        rows += [{"rcept_no": t["rcept_no"], "corp_code": t["corp_code"], **r} for r in got]
    with db.connect(url) as conn:
        db.apply_schema(conn)
        n = db.replace_rows(conn, "raw.dividend_decision_class", rows)
    print(f"공시 {len(targets)}건 중 종류주식 표 있음 {len(targets) - len(empty)}건 · raw.dividend_decision_class {n}행 · 표 없음 {len(empty)}건")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="배당 결정 공시의 우선주 종목별 1주당 배당금")
    ap.add_argument("--url", default=db.database_url())
    main(ap.parse_args().url)
