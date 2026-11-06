"""1차(원문 URL 문서)·2차(자기 연도 사업보고서) 확인을 합쳐 칸마다 최종 판정. 결과: dart/final_verdict.csv

- 배당금지급은 현금흐름표에 (괄호)=음수로 적혀 있어 절댓값으로 비교한다.
- 천원·백만원 단위 표의 반올림은 같은 값으로 본다 (차이가 더 거친 쪽 단위 이하).
- 기준값: 그 연도 사업보고서 별도 재무제표 > 원문 문서의 당기 열. 원문 문서가 다른 회사 것이면 원문 후보는 버린다.
"""
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ofs_review"  # 결과 CSV (git 제외)

r = pd.read_csv(str(OUT_DIR / "verify_result.csv"), dtype={"corp_code": str, "연도": str})
o = pd.read_csv(str(OUT_DIR / "verify_own_year.csv"), dtype={"corp_code": str, "연도": str})
key = ["corp_code", "연도", "항목", "묶음"]
r["corp_code"] = r["corp_code"].str.zfill(8)
o["corp_code"] = o["corp_code"].str.zfill(8)
m = r.merge(o[key + ["사업보고서", "사업보고서 값"]], on=key, how="left")


def grain(v):
    return 1_000_000 if v % 1_000_000 == 0 else 1_000 if v % 1_000 == 0 else 1


def same(a, b):
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(abs(a) - abs(b)) <= max(grain(abs(a)), grain(abs(b))) if a * b >= 0 or abs(a) == abs(b) \
        else abs(abs(a) - abs(b)) <= max(grain(abs(a)), grain(abs(b)))


def final(x):
    api, cand = x["API 확정값"], x["원문 후보"]
    pay = x["항목"] == "배당금지급_지급기준"
    a, c = (abs(api), abs(cand)) if pay else (api, cand)
    other = "다른 회사" in str(x["판정"])
    if pd.notna(x["사업보고서 값"]):
        ref, src = x["사업보고서 값"], "그 연도 사업보고서 별도 재무제표"
    elif not other and pd.notna(x["다시 읽은 값"]) and "당기" in str(x["메모"]):
        ref, src = x["다시 읽은 값"], "원문 문서 당기 열"
    else:
        ref, src = None, ""
    if ref is not None and pay:
        ref = abs(ref)
    if same(a, c):
        better = "원문 후보" if grain(abs(c)) < grain(abs(a)) else "API 값"
        return "같은 값(단위 반올림 차이)", f"{better}이 더 자세함", better
    if ref is None:
        if other:
            return "API 값 유지", f"원문 후보는 '{x['보고서 감사 대상']}' 감사보고서에서 읽은 값", "API 값"
        return "직접 확인 필요", str(x["판정"]), ""
    if same(ref, a):
        why = f"{src} = API" + (f" · 원문 후보는 '{x['보고서 감사 대상']}' 감사보고서 값" if other else "")
        return "API 값 유지", why, "API 값"
    if same(ref, c):
        return "원문 후보로 교체", f"{src} = 원문 후보", "원문 후보"
    return "직접 확인 필요", f"{src} 값이 API·원문 후보 둘 다와 다름", ""


m[["최종", "근거", "쓸 값"]] = m.apply(lambda x: pd.Series(final(x)), axis=1)
m.to_csv(str(OUT_DIR / "final_verdict.csv"), index=False, encoding="utf-8-sig")
print(pd.crosstab(m["최종"], m["묶음"], margins=True).to_string())
