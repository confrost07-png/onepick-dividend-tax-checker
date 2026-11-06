"""API·원문 불일치 칸을 DART 원문으로 다시 확인한다.

칸마다: 원문 URL의 감사보고서를 받아 ① 감사 대상 회사 이름 ② 별도/연결 ③ 해당 사업연도 값을 읽고,
API 확정값·원문 후보 중 어느 쪽과 같은지 판정한다. 결과: dart/verify_result.csv
"""
import re
import sys

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ofs_review"  # 결과 CSV (git 제외)

from scripts.ofs_review import dartdoc as dd  # noqa: E402

SRC = str(OUT_DIR.parent / "03_별도보완" / "별도_보완결과.csv")
NUM = re.compile(r"\(?-?[\d,]{4,}\)?")
LABEL = {
    "부채총계": r"부\s*채\s*총\s*계",
    "자본총계": r"자\s*본\s*총\s*계",
    "당기순이익_전체": r"당\s*기\s*순\s*(이\s*익|손\s*실|손\s*익)",
    "배당금지급_지급기준": r"배\s*당\s*금\s*의?\s*지\s*급",
}
SECTION = {
    "부채총계": r"재\s*무\s*상\s*태\s*표",
    "자본총계": r"재\s*무\s*상\s*태\s*표",
    "당기순이익_전체": r"(포\s*괄\s*)?손\s*익\s*계\s*산\s*서",
    "배당금지급_지급기준": r"현\s*금\s*흐\s*름\s*표",
}


def norm(name: str) -> str:
    return re.sub(r"\s|주식회사|\(주\)|㈜|[:：]", "", name or "")


def official_names(corp_code: str) -> set[str]:
    """DART 기업개황의 회사이름·공시회사명."""
    import html as H
    h = dd.get(f"https://dart.fss.or.kr/dsae001/selectPopup.ax?selectKey={corp_code.zfill(8)}")
    t = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", h)))
    names = set()
    for pat in (r"회사이름 (.+?) (?:정보 더보기|rss)", r"공시회사명 (.+?) 종목코드"):
        m = re.search(pat, t)
        if m:
            names.add(norm(m.group(1)))
    return names


def to_num(tok: str) -> float:
    neg = tok.startswith("(") or tok.startswith("-")
    v = float(tok.strip("()-").replace(",", ""))
    return -v if neg else v


def doc_lines(url: str) -> list[str]:
    if "main.do" in url:
        rcp = re.search(r"rcpNo=(\d+)", url).group(1)
        out = []
        for n in dd.toc(rcp):
            if any(w in re.sub(r"\s", "", n["text"]) for w in ("감사보고서", "재무제표")):
                out += dd.section_text(n).splitlines()
        return out
    return dd.lines(url)


def entity(lines: list[str]) -> str:
    """감사 대상 회사: '○○ 주주 및 이사회 귀중' 또는 재무상태표 머리의 회사 이름."""
    for ln in lines[:600]:
        m = re.search(r"([^|]{2,40}?)\s*(?:의)?\s*주주\s*(?:및|와)\s*이사회\s*(?:귀중|귀하)", ln)
        if m:
            return m.group(1).strip(" |")
    for i, ln in enumerate(lines):
        if re.search(r"^재\s*무\s*상\s*태\s*표", ln):
            m = re.search(r"((?:주식회사|\(주\)|㈜)\s*[^|(]+?(?=\s*\||\s*\()|[^\s|]+\s*주식회사)", " ".join(lines[i:i + 6]))
            if m:
                return m.group(1)
    return ""


def unit_of(lines: list[str], start: int) -> int:
    for ln in lines[start:start + 12]:
        m = re.search(r"단위\s*[:：]?\s*(백만원|천원|원)", ln)
        if m:
            return {"원": 1, "천원": 1000, "백만원": 1_000_000}[m.group(1)]
    return 1


def read_value(lines: list[str], item: str, year: int):
    """별도(연결 아님) 재무제표에서 item의 year 값. (값, 메모)"""
    for i, ln in enumerate(lines):
        if not re.search(SECTION[item], ln) or len(ln) > 40:
            continue
        head = " ".join(lines[i:i + 10])
        consolidated = bool(re.search(r"연\s*결", ln))
        years = [int(y) for y in re.findall(r"(\d{4})\s*[년.]\s*\d{1,2}\s*[월.]\s*\d{1,2}\s*일?\s*(?:현재|까지)",
                                             head.replace("\xa0", " "))]
        if not years:
            continue
        unit = unit_of(lines, i)
        for j in range(i + 1, min(i + 600, len(lines))):
            ln2 = lines[j]
            if re.search(SECTION[item], ln2) and len(ln2) < 40 and j > i + 3:  # 바로 아래 표 제목은 같은 표
                break
            if re.search(LABEL[item], ln2):
                row = ln2  # 칸이 여러 줄로 나뉜 경우: 숫자·구분선만 있는 다음 줄들을 이어 붙인다
                for nxt in lines[j + 1:j + 8]:
                    if not re.fullmatch(r"[|\s\d,().\-]*", nxt):
                        break
                    row += " " + nxt
                nums = [to_num(t) for t in NUM.findall(row) if "," in t]
                if not nums:
                    continue
                if year not in years[:len(nums)]:
                    return None, f"표 연도 {years[:2]}에 {year} 없음"
                v = nums[years.index(year)] * unit
                col = "당기" if years.index(year) == 0 else "비교기간(재작성 가능)"
                return v, ("연결표" if consolidated else "별도표") + f" {col} 연도열 {years[:2]} 단위 {unit}"
        return None, "항목 행 못 찾음"
    return None, "표 못 찾음"


def main():
    b = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig")
    b["v"] = pd.to_numeric(b["확정값"])
    b["w"] = pd.to_numeric(b["원 단위"])
    mis = b[b["대조"].fillna("").str.startswith("불일치")].assign(묶음="불일치")
    q5 = b[b.v.notna() & b.w.notna() & (b.v != b.w) & ~b["대조"].fillna("").str.startswith("불일치")].assign(묶음="표시없는차이")
    rows = pd.concat([mis, q5])
    cache, out, names_cache = {}, [], {}
    for r in rows.itertuples():
        url = r.원문
        if url not in cache:
            try:
                L = doc_lines(url)
                cache[url] = (L, entity(L))
            except Exception as ex:  # noqa: BLE001
                cache[url] = ([], f"받기 실패: {ex}")
        L, ent = cache[url]
        if r.corp_code not in names_cache:
            names_cache[r.corp_code] = official_names(r.corp_code) | {norm(r.회사명)}
        same = bool(norm(ent)) and norm(ent) in names_cache[r.corp_code]
        val, memo = read_value(L, r.항목, int(r.사업연도)) if L else (None, "문서 없음")
        if not norm(ent):
            verdict = "확인 못 함(감사 대상 이름 없음)"
        elif not same:
            verdict = "원문 후보는 다른 회사 보고서 → API 유지"
        elif val is None:
            verdict = f"확인 못 함({memo})"
        elif abs(val - r.v) < 1:
            verdict = "원문 = API 값 → API 유지"
        elif abs(val - r.w) < 1:
            verdict = "원문 = 원문 후보 → 원문 값"
        else:
            verdict = "원문이 둘 다와 다름"
        out.append({"묶음": r.묶음, "corp_code": r.corp_code, "회사": r.회사명, "연도": r.사업연도, "항목": r.항목,
                    "API 확정값": r.v, "원문 후보": r.w, "보고서 감사 대상": ent, "같은 회사": same,
                    "다시 읽은 값": val, "메모": memo, "판정": verdict, "원문": url})
        print(len(out), r.회사명, r.사업연도, r.항목, "→", verdict, flush=True)
    pd.DataFrame(out).to_csv(str(OUT_DIR / "verify_result.csv"), index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
