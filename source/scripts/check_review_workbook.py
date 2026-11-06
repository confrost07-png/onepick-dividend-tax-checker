"""전수 검산표 엑셀의 '수식' 칸을 파이썬으로 똑같이 계산해 결과별 행 수를 센다 (LibreOffice 없이 수식 결과 확인용).

실행: .venv/bin/python -m scripts.check_review_workbook [엑셀 경로]
수식이 가리키는 열을 이름으로 찾아 같은 규칙으로 계산한다. 결과는 검산표를 열었을 때 엑셀이 보여 줄 값과 같아야 한다.
"""
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.export_review_workbook import EXPORT_DIR, TOL


def isnum(v) -> bool:
    return isinstance(v, (int, float)) and not pd.isna(v) and not isinstance(v, bool)


def same(a, b, tol=TOL) -> bool:
    return (not isnum(a) and not isnum(b) and (a is None or pd.isna(a)) and (b is None or pd.isna(b))) or \
        (isnum(a) and isnum(b) and abs(a - b) < tol)


def total(parts, whole, extra=None):
    def f(r):
        vals = [r[p] for p in parts] + [r[whole]]
        if not all(isnum(v) for v in vals):
            return "빈칸"
        base = sum(r[p] for p in parts)
        add = r[extra] if extra and isnum(r[extra]) else 0
        return "일치" if abs(base - r[whole]) <= 1 or (extra and abs(base + add - r[whole]) <= 1) else "불일치"
    return f


def ratio(p, t, n, tol=0.5, blank="성향 빈칸"):
    def f(r):
        if not isnum(r[n]) or r[n] <= 0 or not isnum(r[t]):
            return "계산 대상 아님"
        if not isnum(r[p]):
            return blank
        return "일치" if abs(r[p] - r[t] / r[n] * 100) <= tol else "불일치"
    return f


def fin(r):
    items = ["지배주주 순이익", "부채총계", "자본총계"]
    if not any(isnum(r[f"{i} 원문 읽은 값(원)"]) for i in items):
        return "원문 값 없음"
    return "같음" if all(same(r[f"{i} 분석 값(원)"], r[f"{i} 원문 읽은 값(원)"]) for i in items) else "다름"


def div(r):
    d, s = r["D 분석 값(원)"], r["배당 결정 공시 합계(원)"]
    if not isnum(d) or not isnum(s):
        return "비교 불가"
    return "±1% 이내" if abs(d - s) <= max(TOL, d * 0.01) else "다름"


def cf(r):
    if not isnum(r["원문 읽은 값(원)"]):
        return "원문 값 없음"
    return "같음" if same(r["분석 값(원)"], r["원문 읽은 값(원)"]) else "다름"


def api_match(r):
    a, b = r["부채 원문 읽은 값(원)"], r["자본 원문 읽은 값(원)"]
    if not isnum(a) and not isnum(b):
        return "원문 값 없음"
    return "같음" if same(r["부채총계(원)"], a, 1000) and same(r["자본총계(원)"], b, 1000) else "다름"


def cash(r):
    b, d, fx, e = (r[c] for c in ("기초 현금(원)", "현금 순증감(원)", "환율변동효과(원)", "기말 현금(원)"))
    if not (isnum(b) and isnum(d) and isnum(e)):
        return "빈칸"
    return "일치" if abs(b + d - e) <= 1 or abs(b + d + (fx if isnum(fx) else 0) - e) <= 1 else "불일치"


def decision(r):
    a, b = r["배당기준일"], r["배당금지급 예정일"]
    if not a or not b or pd.isna(a) or pd.isna(b):
        return "날짜 빈칸"
    return "순서 맞음" if str(a) <= str(b) else "순서 이상"


def kind(r):
    g, a, b = r["증가율(%)"], r["직전 배당총액 D(원)"], r["전전 배당총액 D(원)"]
    if not (isnum(g) and isnum(a) and isnum(b)) or b == 0:
        return "계산 불가"
    return "일치" if abs(g - (a / b - 1) * 100) <= 0.5 else "불일치"


def company(r):
    code, m, dec = r["종목코드"], r["결산월"], r["12월 결산"]
    return "정상" if isinstance(code, str) and len(code) == 6 and (m == 12) == bool(dec) else "확인"


def min_div(r):
    ni = r["가정한 2026 순이익(원)"]
    ys = [r[f"{y} 순이익(원)"] for y in (2023, 2024, 2025)]
    if not isnum(ni):
        return "빈칸"
    vals = [v for v in ys if isnum(v)]
    want = (min(vals) if r["시나리오"] == "최근 3년 최저" else max(vals) if r["시나리오"] == "최근 3년 최고" else ys[2]) if vals else None
    return "일치" if isnum(want) and abs(ni - want) <= 1 else "불일치"


def cf_accounts(df: pd.DataFrame) -> pd.Series:
    inc = df[df["판정"] == "포함"].copy()
    inc["abs"] = inc["당기 금액(원)"].abs()
    sums = inc.groupby(["corp_code", "사업연도", "재무제표"])["abs"].sum()
    out = []
    for r in df.to_dict("records"):
        t = r["04 합계 DB(원)"]
        if not isnum(t):
            out.append("04 합계 없음")
            continue
        s = sums.get((r["corp_code"], r["사업연도"], r["재무제표"]), 0.0)
        out.append("같음" if abs(s - t) < TOL else "다름")
    return pd.Series(out, index=df.index)


RULES = {
    "00_회사목록": {"수식 검산": company},
    "02_재무": {"수식 검산": fin},
    "02_배당표": {"수식 검산": div},
    "02_배당표_전체항목": {"수식: 배당성향": ratio("(연결)현금배당성향(%)", "현금배당금총액(백만원)", "(연결)당기순이익(백만원)")},
    "04_배당금지급": {"수식 검산": cf},
    "04-2_재무API": {"수식: 자산 합": total(["유동자산(원)", "비유동자산(원)"], "자산총계(원)", "매각예정자산(원)"),
                    "수식: 부채 합": total(["유동부채(원)", "비유동부채(원)"], "부채총계(원)", "매각예정부채(원)"),
                    "수식: 지배+비지배": total(["지배기업 소유주지분(원)", "비지배지분(원)"], "자본총계(원)"),
                    "수식: 부채+자본=자산": total(["부채총계(원)", "자본총계(원)"], "자산총계(원)"),
                    "수식: 현금 흐름": cash, "수식: DB=원문": api_match},
    "05_배당결정공시": {"수식 검산": decision},
    "03_별도보완": {"수식: 배당성향": ratio("현금배당성향(%)", "현금배당금총액(원)", "당기순이익(원)")},
    "09_KIND고배당": {"수식: 증가율": kind},
    "2027_최소배당액": {"수식 검산": min_div},
}


def main(path: Path):
    for sheet, rules in RULES.items():
        df = pd.read_excel(path, sheet_name=sheet, dtype={"corp_code": str, "종목코드": str})
        df = df.astype(object).where(df.notna(), None)
        for col, fn in rules.items():
            res = Counter(df.apply(fn, axis=1))
            print(f"  {sheet} · {col}: " + " · ".join(f"{k} {v:,}" for k, v in res.most_common()))
    df = pd.read_excel(path, sheet_name="04-1_배당계정별", dtype={"corp_code": str})
    print("  04-1_배당계정별 · 수식: 포함 계정 합: " + " · ".join(f"{k} {v:,}" for k, v in Counter(cf_accounts(df)).most_common()))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else EXPORT_DIR / f"원픽_전수검산표_{date.today():%Y%m%d}.xlsx")
