"""DB 빈칸을 DART 원문에서 다시 읽어 채울 값을 만든다. 원본 표는 고치지 않고 core.core_dart_fill에 따로 둔다.

칸마다 결과 상태는 셋 중 하나다.
- 채움: 원문에서 읽었고 같은 표 안의 합계로 검산이 맞음 (또는 코드로 계산한 값)
- 원문도 비어 있음 / 무배당 확인 / 계산 대상 아님 / 정책 대기: 값을 넣지 않는 것이 맞는 칸
- 확인 필요: 원문을 못 찾았거나 검산이 안 맞음 (사람이 볼 칸)
"""
import re

from core import dart_doc as dd

ENGINE = "source/core/dart_fill.py"
FILLED, NEEDS_REVIEW = "채움", "확인 필요"
NO_DIVIDEND, EMPTY_SOURCE, NOT_APPLICABLE, POLICY = "무배당 확인", "원문도 비어 있음", "계산 대상 아님", "정책 대기"
NO_REPORT = "사업보고서 없음"


def row(corp, year, item, value=None, status=NEEDS_REVIEW, *, ref="", text=None, rcept="", title="", url="",
        column="", fs_kind="", check="", note=""):
    return {"corp_code": corp, "bsns_year": int(year), "item": item, "ref": ref, "value_won": value, "value_text": text,
            "status": status, "source_rcept_no": rcept, "source_title": title, "source_url": url, "column_kind": column,
            "fs_kind": fs_kind, "check_result": check, "note": note, "engine": ENGINE}


def source_tag(title: str | None) -> str:
    """채운 값의 출처가 사업보고서가 아니면 꼬리표 글 (사업보고서면 빈 글).
    공시 제목 예: '가나다/사업보고서/2020.03.30', '가나다/연결감사보고서/2020.04.29', '감사보고서제출 첨부 연결감사보고서',
    '분기보고서 (2021.03) 첨부 사업보고서'."""
    t = re.sub(r"\s", "", title or "")
    if not t:
        return ""
    if "첨부" in t:
        filing, doc = t.split("첨부", 1)
        filing = re.sub(r"\(.*?\)", "", filing)
        return f"출처: {filing} 첨부 {doc} (첨부파일, 사업보고서 본문 아님)"
    kind = t.split("/")[1] if t.count("/") >= 2 else t
    if "사업보고서" in kind:
        return ""
    return f"출처: {kind} (사업보고서 아님)"


def norm(name: str) -> str:
    return re.sub(r"\s|주식회사|\(주\)|㈜", "", name or "").upper()


def same_company(title: str, corp_name: str) -> bool:
    """공시 제목 '회사명/보고서명/날짜'의 회사명이 우리 회사인지."""
    return norm(title.split("/")[0]) == norm(corp_name)


# --- ① 재무 (지배주주 순이익·부채·자본) ------------------------------------------------


def _financial_lines(corp, year, need, consolidated, lines, meta) -> list[dict] | None:
    """재무제표 줄에서 그 해 열을 찾아 칸을 만든다. 그 해 열이 없으면 None."""
    bs = dd.pick(dd.statements(lines, "BS"), consolidated)
    if bs is None or year not in bs.years:
        return None
    meta = dict(meta, column="당기" if bs.years[0] == year else "비교기간(재작성 가능)", fs_kind="연결" if consolidated else "별도")
    out = []
    ok, chk = dd.check_balance(bs, year)
    for item, label in (("liabilities_won", dd.L_LIAB), ("equity_won", dd.L_EQUITY)):
        if item in need:
            out.append(row(corp, year, item, bs.value(label, year), FILLED if ok else NEEDS_REVIEW, check=chk, **meta))
    if "ni_owner_won" in need:
        st = dd.pick(dd.statements(lines, "IS"), consolidated)
        ni, chk2 = dd.owner_net_income(st, year) if st else (None, "손익계산서 못 찾음")
        out.append(row(corp, year, "ni_owner_won", ni, FILLED if ni is not None else NEEDS_REVIEW, check=chk2, **meta))
    return out


def financial(corp, corp_name, year, need: list[str], consolidated: bool, rcepts: list[str]) -> list[dict]:
    """need ⊂ {ni_owner_won, liabilities_won, equity_won}. rcepts: 볼 사업보고서·감사보고서 접수번호(앞선 것 우선)."""
    fs = "연결" if consolidated else "별도"
    for rcp in rcepts:
        title, nodes = dd.filing(rcp)
        if not same_company(title, corp_name):
            continue
        chap = dd.chapter(nodes, "연결재무제표" if consolidated else "재무제표") or dd.audit_chapter(nodes, consolidated)
        if not chap:
            continue
        out = _financial_lines(corp, year, need, consolidated, dd.section_lines(chap),
                               dict(rcept=rcp, title=title, url=chap[0].url))
        if out is not None:
            return out
    return [row(corp, year, item, note=f"{fs} 재무제표에서 {year}년 열을 못 찾음 (본 공시 {', '.join(rcepts) or '없음'})")
            for item in need]


def financial_attached(corp, year, need: list[str], consolidated: bool, docs: list[tuple[str, str, str]]) -> list[dict] | None:
    """'감사보고서제출' 공시의 첨부 감사보고서(본문 목차로는 안 열리고 첨부로만 열리는 것). docs: [(주소, 공시명, 접수번호)]."""
    for url, title, rcp in docs:
        out = _financial_lines(corp, year, need, consolidated, dd.table_lines(dd.get(url)), dict(rcept=rcp, title=title, url=url))
        if out is not None:
            return out
    return None


# --- ② 배당 결정 공시 원본 찾기 ----------------------------------------------------------


def decision_fields(lines: list[str]) -> dict:
    """현금ㆍ현물배당결정 본문 → 배당구분·종류·보통주 주당배당금·배당금총액·기준일."""
    out = {}
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.split("|")]
        head = re.sub(r"^\d+\.\s*", "", cells[0])
        if head == "배당구분":
            out["div_kind"] = cells[1]
        elif head == "배당종류":
            out["div_type"] = cells[1]
        elif head.startswith("1주당 배당금") and len(cells) > 2 and "보통" in cells[1]:
            out["dps_common_won"] = dd.cell_value(cells[2])
        elif head.startswith("배당금총액"):
            out["total_won"] = dd.cell_value(cells[1])
        elif head.startswith("배당기준일"):
            out["record_date"] = cells[1]
    return out


def decision(corp, corp_name, fix_rcept: str, disclosed_on: str) -> list[dict]:
    """[첨부정정] 공시만 있고 원래 결정 공시가 DB에 없는 경우: 같은 날 '현금ㆍ현물배당결정' 원공시를 찾아 읽는다."""
    day = disclosed_on.replace("-", "")
    start = f"{int(day[:4]) - (1 if day[4:6] <= '02' else 0)}{'11' if day[4:6] <= '02' else str(int(day[4:6]) - 2).zfill(2)}01"
    found = [(r, t) for r, t in dd.search(corp, start, day)  # 정정 공시일과 그 전 두 달 사이의 원공시 (가장 가까운 것)
             if "배당결정" in t.replace(" ", "").replace("ㆍ", "").replace(",", "") and "정정" not in t]
    found = found[:1]
    if not found:
        return [row(corp, int(day[:4]), "decision.total_won", ref=fix_rcept, note=f"{disclosed_on}까지 두 달 안 원공시를 검색에서 못 찾음")]
    rcp, title = found[-1]
    f = decision_fields(dd.body_lines(rcp))
    rec = f.get("record_date", "")
    year = int(rec[:4]) if re.match(r"\d{4}-\d{2}", rec) else int(day[:4])
    if f.get("div_kind") == "결산배당" and re.match(r"\d{4}-0[1-6]", rec):  # 2024년부터 결산배당 기준일을 다음 해로 정할 수 있음
        year -= 1
    ok = f.get("total_won") is not None and bool(re.match(r"\d{4}-\d{2}-\d{2}", f.get("record_date", "")))
    meta = dict(ref=rcp, rcept=rcp, title=f"{corp_name}/{title}/{disclosed_on}", url=f"{dd.BASE}/dsaf001/main.do?rcpNo={rcp}",
                check="배당금총액과 기준일을 읽음" if ok else "본문 항목 일부 못 읽음",
                note=f"[첨부정정] {fix_rcept}의 원공시 · {f.get('div_kind', '')} {f.get('div_type', '')}")
    st = lambda v: FILLED if ok and v is not None else NEEDS_REVIEW  # noqa: E731 칸마다 따로
    return [row(corp, year, "decision.total_won", f.get("total_won"), st(f.get("total_won")), **meta),
            row(corp, year, "decision.dps_common_won", f.get("dps_common_won"), st(f.get("dps_common_won")), **meta),
            row(corp, year, "decision.record_date", None, st(f.get("record_date")), text=f.get("record_date"), **meta)]


# --- ③ 사업보고서 배당 표: 보통주 주당 현금배당금 ---------------------------------------------

_KIND = re.compile(r"보통|우선|종류|대주주|소액|의결권|결산|중간|분기|^-$")


def dividend_rows(lines: list[str], label: str = r"주당\s*현금\s*배당금") -> list[tuple[str, list]]:
    """배당 표에서 label 행과 그 아래 주식 종류별 행 [(종류, [당기, 전기, 전전기 …])]."""
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.split("|")]
        if not re.search(label, cells[0]):
            continue
        out, first = [], cells[1:]
        for cs in [first] + [[c.strip() for c in x.split("|")] for x in lines[i + 1:i + 6]]:
            if not cs or not _KIND.search(cs[0]):
                break
            vals = [dd.cell_value(c) for c in cs[1:] if c != ""]
            out.append((cs[0], [v for v in vals]))
        return out
    return []


def report_year(nodes) -> int | None:
    """사업보고서의 당기 연도 = 재무제표(없으면 연결) 재무상태표 첫 열 연도."""
    for name in ("재무제표", "연결재무제표"):
        chap = dd.chapter(nodes, name)
        if chap:
            sts = dd.statements(dd.section_lines(chap), "BS")
            if sts:
                return sts[0].years[0]
    return None


def common_dps(corp, corp_name, year, rcepts: list[str], item: str = "dps_common_won") -> dict:
    for rcp in rcepts:
        title, nodes = dd.filing(rcp)
        if not same_company(title, corp_name):
            continue
        sec = [n for n in nodes if "배당에관한사항" in n.text.replace(" ", "")]
        fy = report_year(nodes)
        if not sec or fy is None or not 0 <= fy - year <= 2:
            continue
        col = fy - year
        rows_ = dividend_rows(dd.section_lines(sec[:1]))
        meta = dict(rcept=rcp, title=title, url=sec[0].url, column="당기" if col == 0 else "비교기간(재작성 가능)")
        listed = " · ".join(f"{k} {v[col] if len(v) > col else '?'}" for k, v in rows_)
        if not rows_:
            return row(corp, year, item, note="배당 표에서 주당 현금배당금 행 못 찾음", **meta)
        at = {k: (v[col] if len(v) > col else None) for k, v in rows_}
        common = [x for k, x in at.items() if re.search(r"보통|의결권\s*있", k)]
        how = "보통주 행"
        if not common and all(re.search(r"결산|중간|분기", k) for k in at):  # 보통주를 결산·중간으로 나눠 적은 표
            common, how = [sum(x or 0 for x in at.values())], "결산·중간·분기 행 합계"
        elif not common and {k for k in at} >= {"대주주", "소액주주"}:  # 차등배당: 두 값이 같을 때만
            vals = {x for k, x in at.items() if k in ("대주주", "소액주주")}
            common, how = (list(vals), "차등배당 대주주·소액주주 같은 값") if len(vals) == 1 else ([], "")
        elif not common and rows_[0][0] in ("-", ""):  # 종류 칸이 없으면 첫 행이 보통주
            common = [at[rows_[0][0]]]
        if len(common) == 1 and common[0] is not None:
            v = common[0]
            return row(corp, year, item, v, FILLED if v else EMPTY_SOURCE, check=f"배당 표 {how} ({listed})", **meta)
        return row(corp, year, item, note=f"보통주 행이 하나로 정해지지 않음 ({listed})", **meta)
    return row(corp, year, item, note="해당 연도 배당 표가 있는 사업보고서를 못 찾음")


def dividend_total(corp, corp_name, year, rcepts: list[str]) -> dict:
    """배당 표 '현금배당금총액' 행에서 그 연도 열 값(원). '-'는 0(무배당)."""
    for rcp in rcepts:
        title, nodes = dd.filing(rcp)
        if not same_company(title, corp_name):
            continue
        sec = [n for n in nodes if "배당에관한사항" in n.text.replace(" ", "")]
        fy = report_year(nodes)
        if not sec or fy is None or not 0 <= fy - year <= 2:
            continue
        col = fy - year
        meta = dict(rcept=rcp, title=title, url=sec[0].url, column="당기" if col == 0 else "비교기간(재작성 가능)")
        for ln in dd.section_lines(sec[:1]):
            cells = [c.strip() for c in ln.split("|") if c.strip() != ""]
            if not cells or not re.search(r"현금\s*배당금\s*총액", cells[0]):
                continue
            unit = 1_000_000 if "백만" in cells[0] else 1_000 if "천원" in cells[0] else 1
            raw = cells[1:][-3:] if len(cells) > 4 else cells[1:]  # 주식 종류 칸이 있으면 뒤의 당기·전기·전전기만
            vals = [dd.cell_value(c) for c in raw]
            if len(vals) <= col or vals[col] is None:
                return row(corp, year, "d_dart_won", note=f"현금배당금총액 행에 {year}년 열 값 없음 ({' | '.join(cells)})", **meta)
            return row(corp, year, "d_dart_won", vals[col] * unit, FILLED,
                       check=f"배당 표 '{cells[0]}' {raw[col]} × {unit:,} (당기·전기·전전기 중 {col + 1}번째 열)", **meta)
        return row(corp, year, "d_dart_won", note="배당 표에서 현금배당금총액 행 못 찾음", **meta)
    return row(corp, year, "d_dart_won", note="해당 연도 배당 표가 있는 사업보고서를 못 찾음")


# --- ④ 현금흐름표 배당금 지급 -----------------------------------------------------------------


def dividends_paid(corp, corp_name, year, consolidated: bool, rcepts: list[str], prev_d=None,
                   item: str = "cf_paid_won") -> dict:
    fs = "연결" if consolidated else "별도"
    for rcp in rcepts:
        title, nodes = dd.filing(rcp)
        if not same_company(title, corp_name):
            continue
        chap = dd.chapter(nodes, "연결재무제표" if consolidated else "재무제표")
        cf = dd.pick(dd.statements(dd.section_lines(chap), "CF"), consolidated) if chap else None
        if cf is None or year not in cf.years:
            continue
        k = cf.years.index(year)
        hits = [(name, nums[k] * cf.unit) for name, nums in cf.rows
                if re.search(dd.L_DIV_PAID, name) and not re.search(dd.L_NCI, name) and len(nums) > k]
        meta = dict(rcept=rcp, title=title, url=chap[0].url, fs_kind=fs,
                    column="당기" if k == 0 else "비교기간(재작성 가능)")
        if len(hits) == 1:
            v = abs(hits[0][1])
            chk = f"현금흐름표 '{hits[0][0]}' 1줄"
            if prev_d:
                chk += f" · 전년 배당총액 대비 {v / float(prev_d) * 100:.0f}%"
            return row(corp, year, item, v, FILLED, check=chk, **meta)
        if not hits:
            return row(corp, year, item, 0.0, EMPTY_SOURCE, check="현금흐름표에 배당금 지급 줄 없음", **meta)
        return row(corp, year, item, note="배당금 지급 줄이 여러 개: " + " · ".join(f"{n} {abs(v):,.0f}" for n, v in hits), **meta)
    return row(corp, year, item, fs_kind=fs, note=f"{fs} 현금흐름표에서 {year}년 열을 못 찾음")
