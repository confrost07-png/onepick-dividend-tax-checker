"""밸류업 계획 약속 분류(D1): 638사 문단에서 약속 후보를 찾아 report/분석/밸류업_약속_분류_결과.md와 검토표를 만든다.

실행: .venv/bin/python -m scripts.analysis_policy_promise [--url ...] [--sample 60]
문단: raw.policy_chunk(첨부·본문 글자층·OCR), 공시는 정정된 계획의 최신 판만(core.v_policy_filing_latest).
정확도: 사람이 원문을 확인한 시연 10사(core.core_policy_item)와 대조한다.
검토표: output/tables/밸류업_약속_자동추출_검토표_<날짜>.xlsx (전체 후보 + 사람 확인용 무작위 표본).
"""
import argparse
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill

from core import db
from core import policy_promise as pp

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "분석" / "밸류업_약속_분류_결과.md"
SEED = 20261029
ACTIONS = tuple(pp.ACTIONS)
EARLY, LATE = "2025년까지 첫 공시", "2026년 첫 공시"
CHUNK_SQL = """SELECT l.corp_code, l.corp_name, l.rcept_no, l.rcept_dt, l.report_nm, c.page, c.seq, c.method, c.text
               FROM core.v_policy_filing_latest l JOIN raw.policy_chunk c ON c.rcept_no = l.rcept_no
               WHERE l.is_latest ORDER BY l.corp_code, l.rcept_dt, c.seq"""
FIRST_SQL = """SELECT corp_code, min(rcept_dt) AS first_dt FROM raw.policy_filing
               WHERE report_nm NOT LIKE '%%예고%%' GROUP BY corp_code"""
HUMAN_SQL = """SELECT corp_code, target_kind, target_value, use_as_target FROM core.core_policy_item
               WHERE target_kind IS NOT NULL AND target_value IS NOT NULL"""


def validation(found: dict, human: list[dict]) -> str:
    """사람이 확인한 목표 값을 규칙이 찾았나(찾아냄), 규칙이 낸 배당 값 중 사람 목록에 있는 비율(맞음)."""
    firms = sorted({h["corp_code"] for h in human})
    lines = ["| 회사(가린 이름) | 사람이 F-03 목표로 쓴 값 | 규칙이 찾았나 | 규칙이 낸 배당 목표 후보 수 | 그중 사람 목록에 있는 값 |",
             "|---|---|---|---|---|"]
    hit = total = cand = good = 0
    for i, corp in enumerate(firms, 1):
        mine = [p for p in found.get(corp, []) if p["kind"] in ("배당성향", "주당배당금")]
        targets = [h for h in human if h["corp_code"] == corp and h["use_as_target"]]
        listed = [h for h in human if h["corp_code"] == corp]
        ok = [any(p["kind"] == t["target_kind"] and pp.same_value(p["value"], str(t["target_value"])) for p in mine) for t in targets]
        hit += sum(ok)
        total += len(targets)
        in_list = sum(1 for p in mine if any(p["kind"] == h["target_kind"] and pp.same_value(p["value"], str(h["target_value"])) for h in listed))
        cand += len(mine)
        good += in_list
        tv = ", ".join(f"{t['target_kind']} {t['target_value']}" for t in targets) or "-"
        lines.append(f"| 회사 {i} | {tv} | {'예' if all(ok) and ok else '아니오' if targets else '-'} | {len(mine)} | {in_list} |")
    lines.append(f"| **합계** | {total}개 | **{hit}/{total} 찾음** | {cand} | **{good}/{cand}** |")
    return "\n".join(lines), hit, total, good, cand


def _cell(v):
    """엑셀에 넣을 수 없는 제어 문자(OCR 글자에 섞임)는 지운다. 원문 조각의 나머지 글자는 그대로."""
    return ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v


def write_review(rows: list[dict], sample_n: int) -> Path:
    path = ROOT / "output" / "tables" / f"밸류업_약속_자동추출_검토표_{date.today():%Y%m%d}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "전체 후보"
    head = ["회사코드", "회사명", "접수번호", "공시일", "보고서명", "쪽", "문단 순서", "글자 읽은 방법", "약속 종류", "값", "원문 조각"]
    ws.append(head)
    for r in rows:
        ws.append([_cell(v) for v in (r["corp_code"], r["corp_name"], r["rcept_no"], r["rcept_dt"], r["report_nm"], r["page"],
                                      r["seq"], r["method"], r["kind"], r["value"], r["text"])])
    sample = random.Random(SEED).sample([r for r in rows if r["value"]], min(sample_n, sum(1 for r in rows if r["value"])))
    ws2 = wb.create_sheet("사람 확인 표본")
    ws2.append(head + ["목표가 맞나(맞음/아님/모름)", "검토자", "메모"])
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for r in sample:
        ws2.append([_cell(v) for v in (r["corp_code"], r["corp_name"], r["rcept_no"], r["rcept_dt"], r["report_nm"], r["page"],
                                       r["seq"], r["method"], r["kind"], r["value"], r["text"], "", "", "")])
        for col in (12, 13, 14):
            ws2.cell(ws2.max_row, col).fill = yellow
    for sheet in (ws, ws2):
        for c in sheet[1]:
            c.font = Font(bold=True)
        sheet.column_dimensions["K"].width = 90
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main(url: str | None, sample_n: int):
    with db.connect(url) as conn:
        chunks = db.fetch_dicts(conn, CHUNK_SQL)
        first = {r["corp_code"]: r["first_dt"] for r in db.fetch_dicts(conn, FIRST_SQL)}
        human = db.fetch_dicts(conn, HUMAN_SQL)
        n_firms = db.fetch_dicts(conn, "SELECT count(*) AS n FROM core.core_company")[0]["n"]
    rows = []
    for c in chunks:
        for p in pp.find(c["text"]):
            rows.append({**{k: c[k] for k in ("corp_code", "corp_name", "rcept_no", "rcept_dt", "report_nm", "page", "seq", "method")},
                         "kind": p.kind, "value": p.value, "text": p.text})
    by_firm = defaultdict(list)
    for r in rows:
        by_firm[r["corp_code"]].append(r)
    timing = {c: EARLY if d.year < 2026 else LATE for c, d in first.items()}
    n_group = Counter(timing.values())
    chunk_firms = len({c["corp_code"] for c in chunks})

    def firms_with(kind, numeric=True, group=None):
        return sum(1 for corp, ps in by_firm.items() if (group is None or timing.get(corp) == group)
                   and any(p["kind"] == kind and (bool(p["value"]) == numeric) for p in ps))

    count_lines = [f"| 약속 종류 | 638사 중 회사 수 | {EARLY} ({n_group[EARLY]}사) | {LATE} ({n_group[LATE]}사) |", "|---|---|---|---|"]
    for k in pp.KINDS:
        a, e, l = firms_with(k), firms_with(k, group=EARLY), firms_with(k, group=LATE)
        count_lines.append(f"| {k} 숫자 목표 | {a} ({a * 100 / n_firms:.0f}%) | {e * 100 / n_group[EARLY]:.0f}% | {l * 100 / n_group[LATE]:.0f}% |")
    for k in ACTIONS:
        a, e, l = firms_with(k, False), firms_with(k, False, EARLY), firms_with(k, False, LATE)
        count_lines.append(f"| {k} | {a} ({a * 100 / n_firms:.0f}%) | {e * 100 / n_group[EARLY]:.0f}% | {l * 100 / n_group[LATE]:.0f}% |")

    payout_vals = Counter()
    for corp, ps in by_firm.items():
        for v in {float(p["value"]) for p in ps if p["kind"] == "배당성향"}:
            payout_vals[v] += 1
    top_payout = "\n".join(f"| {v:g}% | {n} |" for v, n in payout_vals.most_common(8))
    roe_vals = sorted(v for ps in by_firm.values() for v in {float(p["value"]) for p in ps if p["kind"] == "ROE"})
    roe_median = roe_vals[len(roe_vals) // 2] if roe_vals else float("nan")

    val_table, hit, total, good, cand = validation(by_firm, human)
    review = write_review(rows, sample_n)
    only25 = sum(1 for ps in by_firm.values()
                 if {float(p["value"]) for p in ps if p["kind"] == "배당성향"} == {25.0})

    text = f"""# 밸류업 계획 약속 분류 — 638사는 무엇을 약속했나

- 만든 날: {date.today().isoformat()} · 코드: `source/scripts/analysis_policy_promise.py`, `source/core/policy_promise.py`(배당 값 읽기는 `source/core/policy_extract.py` 재사용) · 설계: `report/설계/데이터_분석_설계.md` D1
- 문단: `raw.policy_chunk` {len(chunks):,}개(정정된 계획은 최신 판만, `core.v_policy_filing_latest`), 문단이 있는 회사 {chunk_firms}사
- 방법: **생성형 AI 없이 정해진 단어 규칙**으로 찾는다. 숫자 목표는 지표(배당성향·ROE 등)와 숫자, 그리고 목표를 뜻하는 말(목표·이상·지향·달성·까지·유지·확대 등)이 같은 문장 조각에 있을 때만 센다. 300자가 넘는 조각(주로 표·그림 글자)은 쓰지 않는다
- 무리: 밸류업 계획 첫 공시일(`raw.policy_filing`, 예고 제외). A2와 같다

## 한 줄 결과

{{summary}}

## 1. 사람이 확인한 회사와 대조 — 규칙을 얼마나 믿을 수 있나

시연 10사는 사람이 원문을 보고 배당 목표를 확인했다(`core.core_policy_item`). 그중 목표 값이 적힌 {len({h['corp_code'] for h in human})}사(항목 {len(human)}개)와 대조했다. 회사 이름은 가렸다. **대조한 회사가 적어서 정확도는 대략적인 값**이다.

{val_table}

- '규칙이 찾았나': 사람이 F-03 목표로 쓰기로 한 값을 규칙도 찾았는지.
- '그중 사람 목록에 있는 값': 규칙이 낸 배당성향·주당배당금 후보 중, 사람이 목표 문장으로 뽑은 값과 같은 것. 사람은 모든 문단을 보지는 않았으므로, 목록에 없다고 다 틀린 것은 아니다.

## 2. 약속 종류별 회사 수

한 회사의 최신 계획 문서 전체에서 한 번이라도 나오면 센 것이다. 숫자 목표는 목표를 뜻하는 말과 함께 나온 것만.

{chr(10).join(count_lines)}

## 3. 배당성향 목표로 많이 나온 값

| 배당성향 값 | 회사 수 |
|---|---|
{top_payout}

- 배당성향 후보가 **25% 하나뿐인 회사: {only25}사**. 고배당기업 요건(25%)을 그대로 목표로 적은 경우가 많다는 뜻이다.
- ROE 숫자 목표 값의 중앙값: {roe_median:g}% (회사마다 서로 다른 값만 센 {len(roe_vals)}개 값).

## 4. 읽을 때 주의

- **규칙이 찾은 것은 '후보'다.** 과거 실적("2024년 배당성향 35%")을 목표로 잘못 읽거나, 표·그림 글자 속 목표를 놓칠 수 있다. 1절의 대조가 그 정도를 보여 준다. 화면 카드에는 사람이 확인한 값만 쓴다(F-07 원칙).
- 고배당기업 표시를 위한 재공시에는 법 조문을 옮긴 문장("배당성향 25% 이상 및 … 10% 이상 증가")이 들어 있어, 이것도 배당성향 25% 후보로 잡힌다.
- 사람 확인용 무작위 표본 {min(sample_n, sum(1 for r in rows if r['value']))}개를 검토표로 내보냈다: `{review.relative_to(ROOT)}`('사람 확인 표본' 시트의 노란 칸). 확인 결과로 규칙의 정확도를 638사 전체 기준으로 다시 잰다.
"""
    summary = (f"638사 중 {firms_with('배당성향')}사가 배당성향 숫자 목표를, {firms_with('ROE')}사가 ROE 목표를, "
               f"{firms_with('자사주 소각', False)}사가 자사주 소각을 언급했다. 사람이 확인한 {len({h['corp_code'] for h in human})}사 기준으로 규칙은 "
               f"F-03 목표 값 {total}개 중 {hit}개를 찾았고, 규칙이 낸 배당 후보 {cand}개 중 {good}개가 사람이 뽑은 값과 같았다. "
               f"**일찍 공시한 회사는 ROE 목표 {firms_with('ROE', group=EARLY) * 100 / n_group[EARLY]:.0f}%, 자사주 소각 "
               f"{firms_with('자사주 소각', False, EARLY) * 100 / n_group[EARLY]:.0f}%인데, 2026년에 처음 공시한 회사는 "
               f"{firms_with('ROE', group=LATE) * 100 / n_group[LATE]:.0f}%, {firms_with('자사주 소각', False, LATE) * 100 / n_group[LATE]:.0f}%뿐이다.** "
               f"2026년에 들어온 회사의 계획에는 숫자 목표나 자사주 소각 약속이 드물다.")
    text = text.replace("{summary}", summary)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"검토표: {review}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--sample", type=int, default=60)
    a = ap.parse_args()
    main(a.url, a.sample)
