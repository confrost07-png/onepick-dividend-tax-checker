"""OCR 정확도 점검: 글자층이 있는 PDF 쪽을 일부러 OCR해 글자층(정답)과 비교한다.

실행: .venv/bin/python -m scripts.check_ocr_quality [--n 20] [--seed 0]   (정확도 표본)
      .venv/bin/python -m scripts.check_ocr_quality --coverage            (빠짐없이 처리했는지·검토 진행)
그림 쪽은 정답이 없어 오류율을 잴 수 없으므로, 같은 양식의 글자층 쪽으로 대신 잰다.
- 단어 재현율 = 정답 쪽 단어(2글자 이상) 중 OCR 글자에도 그대로 있는 비율. 슬라이드는 상자 읽는 순서가
  글자층과 OCR이 달라 순서를 따지는 글자 오류율(CER)은 실제보다 크게 나오므로 참고로만 둔다
- 숫자 일치율 = 정답 쪽의 숫자 덩어리(쉼표 포함) 중 OCR 글자에도 그대로 있는 비율
"""
import argparse
import difflib
import random
import re
from pathlib import Path

from core import db
from scripts.ocr_policy_docs import ROOT, RUN, ocr


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def cer(truth: str, got: str) -> float:
    a, b = squash(truth), squash(got)
    if not a:
        return 0.0
    m = sum(x.size for x in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return 1 - m / max(len(a), len(b))


def word_recall(truth: str, got: str) -> tuple[int, int]:
    words = [w for w in re.findall(r"[가-힣A-Za-z0-9]+", truth) if len(w) >= 2]
    flat = squash(got)
    return sum(1 for w in words if w in flat), len(words)


def numbers(s: str) -> list[str]:
    return re.findall(r"\d[\d,.]*\d|\d", s)


def main(url: str, n: int, seed: int):
    with db.connect(url) as conn:
        docs = db.fetch_dicts(conn, "SELECT rcept_no, dcm_no, file_path, text FROM raw.policy_document WHERE file_type = 'pdf' ORDER BY rcept_no, dcm_no")
    pages = [(d, i, t) for d in docs for i, t in enumerate(d["text"].split("\n\f\n"), 1) if len(squash(t)) >= 200]
    random.Random(seed).shuffle(pages)
    rows = []
    for d, i, truth in pages[:n]:
        got = ocr(ROOT / "data" / d["file_path"], [i]).get(i, "")
        nums = numbers(truth)
        hit = sum(1 for x in nums if x in got)
        wh, wn = word_recall(truth, got)
        rows.append((d["rcept_no"], d["dcm_no"], i, len(squash(truth)), cer(truth, got), hit, len(nums), wh, wn))
    print(f"{'접수번호':<15}{'문서':<12}{'쪽':>4}{'정답 글자':>9}{'단어 재현':>12}{'숫자 일치':>12}{'CER(순서)':>10}")
    for r in rows:
        print(f"{r[0]:<15}{r[1]:<12}{r[2]:>4}{r[3]:>9}{r[7]:>7}/{r[8]:<4}{r[5]:>7}/{r[6]:<4}{r[4]:>10.1%}")
    wh, wn = sum(r[7] for r in rows), sum(r[8] for r in rows)
    print(f"\n쪽 {len(rows)}개 · 단어 재현 {wh}/{wn} ({wh / max(1, wn):.1%}) · "
          f"쪽별 단어 재현 최저 {min(r[7] / max(1, r[8]) for r in rows):.1%} · "
          f"숫자 일치 {sum(r[5] for r in rows)}/{sum(r[6] for r in rows)} "
          f"({sum(r[5] for r in rows) / max(1, sum(r[6] for r in rows)):.1%}) · 참고 CER(순서 포함) 중앙값 "
          f"{sorted(r[4] for r in rows)[len(rows) // 2]:.1%}")


def coverage(url: str) -> bool:
    """PDF 쪽 수 = 쪽별 OCR 행 수인지, 상태별·검토별 쪽 수, 검색 조각이 쪽마다 한 벌인지. 모두 맞으면 True."""
    with db.connect(url) as conn:
        q = lambda s, *p: conn.execute(s, p).fetchone()
        pages, docs = q("SELECT sum(n_pages), count(*) FROM raw.policy_document WHERE file_type = 'pdf'")
        rows, this_run = q("SELECT count(*), count(*) FILTER (WHERE run = %s) FROM raw.policy_page_ocr", RUN)
        missing = q("""SELECT count(*) FROM raw.policy_document d, generate_series(1, d.n_pages) g(page)
                       WHERE d.file_type = 'pdf' AND NOT EXISTS (SELECT 1 FROM raw.policy_page_ocr p
                       WHERE p.rcept_no = d.rcept_no AND p.dcm_no = d.dcm_no AND p.page = g.page AND p.run = %s)""", RUN)[0]
        status = conn.execute("SELECT status, count(*) FROM raw.policy_page_ocr GROUP BY 1 ORDER BY 1").fetchall()
        doubled = q("""SELECT count(*) FROM (SELECT rcept_no, dcm_no, page FROM raw.policy_chunk WHERE page IS NOT NULL
                       GROUP BY 1, 2, 3 HAVING bool_or(method = '글자층') AND bool_or(method IN ('OCR', 'OCR 정정'))) x""")[0]
        no_chunk = q("""SELECT count(*) FROM raw.policy_page_ocr p WHERE (p.ocr_chars > 0 OR p.layer_chars > 0)
                        AND NOT EXISTS (SELECT 1 FROM raw.policy_chunk c
                                        WHERE c.rcept_no = p.rcept_no AND c.dcm_no = p.dcm_no AND c.page = p.page)""")[0]
        review = conn.execute("""SELECT review_priority, count(*), count(*) FILTER (WHERE review_status = '확인완료'),
                                        count(*) FILTER (WHERE review_status = '정정함'),
                                        count(*) FILTER (WHERE review_status = '확인불가'),
                                        count(*) FILTER (WHERE reviewer = 'Claude(AI)')
                                 FROM raw.policy_page_ocr WHERE needs_review GROUP BY 1 ORDER BY 1""").fetchall()
    print(f"PDF {docs}개 · {pages:,}쪽 · 쪽별 OCR 행 {rows:,} (이번 판 {RUN} {this_run:,}) · 처리 안 된 쪽 {missing:,}")
    print("상태: " + " · ".join(f"{s} {n:,}" for s, n in status))
    print("검토 (우선순위 / 대상 / 확인완료 / 정정함 / 확인불가 / 남음 / 그중 AI 검토 · 사람 검토)")
    for p, n, ok, fix, bad, ai in review:
        print(f"  {p}  {n:>6,}  {ok:>6,}  {fix:>6,}  {bad:>6,}  {n - ok - fix - bad:>6,}  AI {ai:,} · 사람 {ok + fix + bad - ai:,}")
    print(f"검색 조각: 글자층과 OCR 전체가 겹친 쪽 {doubled:,} · 글자가 있는데 조각이 없는 쪽 {no_chunk:,}")
    fail = dict(status).get("실패", 0)
    left = sum(n - ok - fix - bad for _, n, ok, fix, bad, _ in review)
    bad = sum(r[4] for r in review)
    print(f"빠짐없이 처리: {'예' if missing == 0 and fail == 0 else '아니오'} (미처리 {missing:,}, 실패 {fail:,})")
    ai = sum(r[5] for r in review)
    print(f"정확도 확인: {'완료' if left == 0 and bad == 0 else '진행 중'} (검토 남음 {left:,}, 확인불가 {bad:,}, "
          f"AI만 검토한 쪽 {ai:,} → 사람 표본 확인 권장)")
    return missing == 0 and fail == 0 and doubled == 0 and no_chunk == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OCR 정확도 점검 (글자층 쪽과 비교)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--coverage", action="store_true", help="빠짐없이 처리했는지와 검토 진행만 본다")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    if a.coverage:
        raise SystemExit(0 if coverage(a.url) else 1)
    main(a.url, a.n, a.seed)
