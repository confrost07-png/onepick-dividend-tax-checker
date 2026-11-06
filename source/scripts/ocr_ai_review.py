"""OCR 검토 대상 쪽을 Claude(AI)가 쪽 그림과 대조해 검토하는 절차 (사람 검토 전 단계).

실행:
  .venv/bin/python -m scripts.ocr_ai_review batches [--size 40]     # 검토 대상 → 묶음 JSON (data/raw/ocr_ai/batch_NNN.json)
  .venv/bin/python -m scripts.ocr_ai_review record NNN < 결과.json  # 한 쪽 검토 결과를 묶음 결과 파일에 추가 (검사 후)
  .venv/bin/python -m scripts.ocr_ai_review status                  # 묶음별 진행
  .venv/bin/python -m scripts.ocr_ai_review load                    # 결과 → raw.policy_page_ocr (검토자 'Claude(AI)')

한 쪽 결과 JSON: {"key": "접수번호/문서/쪽", "status": "확인완료|정정함|확인불가",
                  "edits": [{"from": "OCR에 있는 틀린 글자", "to": "그림에 찍힌 글자"}, ...],
                  "add": ["OCR이 빠뜨린 줄", ...], "note": "메모"}
- 정정 글자 = OCR 글자에 edits를 차례로 적용(각 from의 첫 위치)하고 add를 끝에 붙인 것. 맞게 읽은 줄은 그대로 남는다
- from이 OCR 글자에 없으면 기록하지 않고 알려 준다 (잘못된 정정 방지)
- 사람이 이미 검토한 쪽(검토자가 Claude(AI)가 아님)은 load가 덮어쓰지 않는다
"""
import argparse
import json
import sys
from pathlib import Path

from core import db
from scripts.ocr_policy_docs import ROOT, rebuild_chunks

DIR = ROOT / "data" / "raw" / "ocr_ai"
PAGE_DIR = ROOT / "data" / "raw" / "ocr_pages"
AI = "Claude(AI)"
STATES = ("확인완료", "정정함", "확인불가")


def key(r) -> str:
    return f"{r['rcept_no']}/{r['dcm_no']}/{r['page']}"


def apply(text: str, edits: list[dict], add: list[str]) -> str:
    for e in edits:
        text = text.replace(e["from"], e["to"], 1)
    return "\n".join([text] + [a for a in add if a.strip()]).strip()


def check(page: dict, res: dict) -> list[str]:
    """결과 한 건을 검사 → 문제 목록 (비면 통과)."""
    errs = []
    if res.get("status") not in STATES:
        errs.append(f"status는 {STATES} 중 하나")
    edits, add = res.get("edits") or [], res.get("add") or []
    text = page["text"]
    for e in edits:
        if not isinstance(e, dict) or not e.get("from") or "to" not in e:
            errs.append(f"edits 항목 형식: {e}")
        elif e["from"] not in text:
            errs.append(f"from이 OCR 글자에 없음: {e['from']!r}")
        else:
            text = text.replace(e["from"], e["to"], 1)
    if res.get("status") == "정정함" and not edits and not add:
        errs.append("정정함이면 edits나 add가 있어야 함")
    if res.get("status") != "정정함" and (edits or add):
        errs.append("edits·add가 있으면 status는 정정함")
    return errs


def batches(size: int):
    DIR.mkdir(parents=True, exist_ok=True)
    with db.connect(db.database_url()) as conn:
        pages = db.fetch_dicts(conn, """
            SELECT p.rcept_no, p.dcm_no, p.page, p.review_priority, p.layer_chars, p.low_lines, p.text, f.corp_name
            FROM raw.policy_page_ocr p JOIN raw.policy_filing f USING (rcept_no)
            WHERE p.needs_review AND (p.reviewer IS NULL OR p.reviewer = %s)
            ORDER BY p.review_priority, p.rcept_no, p.dcm_no, p.page""", (AI,))
    for n, i in enumerate(range(0, len(pages), size), 1):
        items = [{"key": key(p), "corp_name": p["corp_name"], "priority": p["review_priority"],
                  "image": str(PAGE_DIR / f"{p['rcept_no']}_{p['dcm_no']}_{p['page']:03d}.png"),
                  "low_lines": p["low_lines"], "ocr_text": p["text"]} for p in pages[i:i + size]]
        (DIR / f"batch_{n:03d}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"검토 대상 {len(pages)}쪽 → 묶음 {-(-len(pages) // size)}개 ({DIR})")


def results(n: int) -> dict[str, dict]:
    path = DIR / f"result_{n:03d}.jsonl"
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["key"]] = r  # 같은 쪽을 다시 기록하면 마지막 것
    return out


def record(n: int, raw: str):
    batch = {p["key"]: {"text": p["ocr_text"]} for p in json.loads((DIR / f"batch_{n:03d}.json").read_text(encoding="utf-8"))}
    items = json.loads(raw)
    items = items if isinstance(items, list) else [items]
    ok = 0
    with open(DIR / f"result_{n:03d}.jsonl", "a", encoding="utf-8") as f:
        for res in items:
            if res.get("key") not in batch:
                print(f"거절 {res.get('key')}: 이 묶음에 없는 쪽")
                continue
            errs = check(batch[res["key"]], res)
            if errs:
                print(f"거절 {res['key']}: " + "; ".join(errs))
                continue
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            ok += 1
    done = len(results(n))
    print(f"기록 {ok}건 · 묶음 {n:03d} 진행 {done}/{len(batch)}")


def status():
    total = done = 0
    for b in sorted(DIR.glob("batch_*.json")):
        n = int(b.stem.split("_")[1])
        size = len(json.loads(b.read_text(encoding="utf-8")))
        got = results(n)
        total, done = total + size, done + len(got)
        counts = {s: sum(1 for r in got.values() if r["status"] == s) for s in STATES}
        print(f"  {n:03d}: {len(got)}/{size} " + " ".join(f"{s} {c}" for s, c in counts.items()))
    print(f"전체 {done}/{total}")


def load():
    with db.connect(db.database_url()) as conn:
        pages = {key(r): r for r in db.fetch_dicts(conn, "SELECT rcept_no, dcm_no, page, text, reviewer FROM raw.policy_page_ocr")}
        n, skipped, docs = 0, 0, set()
        for b in sorted(DIR.glob("batch_*.json")):
            for k, res in results(int(b.stem.split("_")[1])).items():
                p = pages[k]
                if p["reviewer"] not in (None, AI):  # 사람이 검토한 쪽은 그대로 둔다
                    skipped += 1
                    continue
                edits, add = res.get("edits") or [], res.get("add") or []
                fixed = apply(p["text"], edits, add) if res["status"] == "정정함" else None
                change = "; ".join(f"{e['from']}→{e['to']}" for e in edits) + ("; 추가 " + " / ".join(add) if add else "")
                note = " · ".join(x for x in (res.get("note"), f"AI 정정: {change}" if change else None) if x) or None
                conn.execute("""UPDATE raw.policy_page_ocr SET review_status = %s, reviewer = %s, corrected_text = %s,
                                review_note = %s, reviewed_at = now()
                                WHERE rcept_no = %s AND dcm_no = %s AND page = %s""",
                             (res["status"], AI, fixed, note, p["rcept_no"], p["dcm_no"], p["page"]))
                docs.add((p["rcept_no"], p["dcm_no"]))
                n += 1
        for rcept_no, dcm_no in sorted(docs):
            rebuild_chunks(conn, rcept_no, dcm_no)
        conn.commit()
    print(f"AI 검토 반영 {n}쪽 (사람 검토가 있어 건너뜀 {skipped}쪽), 문단 다시 만든 문서 {len(docs)}개")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OCR AI 검토 절차")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("batches").add_argument("--size", type=int, default=40)
    sub.add_parser("record").add_argument("n", type=int)
    sub.add_parser("status")
    sub.add_parser("load")
    a = ap.parse_args()
    if a.cmd == "batches":
        batches(a.size)
    elif a.cmd == "record":
        record(a.n, sys.stdin.read())
    elif a.cmd == "status":
        status()
    else:
        load()
