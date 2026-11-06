"""Q8: 감사보고서 당기순이익_전체와 배당 표 당기순이익이 1% 넘게 다른 칸을 그 연도 사업보고서 별도 손익계산서로 확인. 결과: dart/verify_ni.csv"""
import re
import sys

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ofs_review"  # 결과 CSV (git 제외)

from scripts.ofs_review import dartdoc as dd  # noqa: E402
from scripts.ofs_review import verify_mismatch as vm  # noqa: E402

b = pd.read_csv(vm.SRC, dtype=str, encoding="utf-8-sig")
b["v"] = pd.to_numeric(b["확정값"])
p = b.pivot_table(index=["corp_code", "회사명", "사업연도"], columns="항목", values="v", aggfunc="first").reset_index()
both = p.dropna(subset=["당기순이익_전체", "당기순이익"])
big = both[(both["당기순이익_전체"] - both["당기순이익"]).abs() > both["당기순이익"].abs() * 0.01]
annual = (b[(b["출처"] == "배당 표") & b["접수번호"].notna()].groupby(["corp_code", "사업연도"])["접수번호"].first().to_dict())


def grain(v):
    return 1_000_000 if v % 1_000_000 == 0 else 1_000 if v % 1_000 == 0 else 1


def same(a, c):
    return abs(a - c) <= max(grain(abs(a)), grain(abs(c)))


out = []
for x in big.itertuples():
    rcp = annual.get((x.corp_code, x.사업연도))
    val, memo = None, "사업보고서 접수번호 없음"
    if rcp:
        nodes = dd.toc(rcp)
        s = next((i for i, n in enumerate(nodes) if re.fullmatch(r"\d+\.\s*재무제표", n["text"].strip())), None)
        sec = []
        if s is not None:
            sec = [nodes[s]]
            for n in nodes[s + 1:]:
                if re.match(r"\d+\.\s", n["text"].strip()):
                    break
                sec.append(n)
        val, memo = vm.read_value("\n".join(dd.section_text(n) for n in sec).splitlines(), "당기순이익_전체",
                                  int(x.사업연도)) if sec else (None, "재무제표 목차 없음")
    audit, divt = x.당기순이익_전체, x.당기순이익
    if val is None:
        v = f"확인 못 함({memo})"
    elif same(val, audit) and same(val, divt):
        v = "둘 다 맞음(반올림)"
    elif same(val, audit):
        v = "감사보고서 값이 맞음 → 배당 표 값 오류"
    elif same(val, divt):
        v = "배당 표 값이 맞음 → 감사보고서 값 확인"
    else:
        v = "사업보고서가 둘 다와 다름"
    out.append({"회사": x.회사명, "연도": x.사업연도, "감사보고서": audit, "배당 표": divt, "사업보고서 별도 손익": val,
                "메모": memo, "판정": v})
    print(x.회사명, x.사업연도, "→", v, flush=True)
pd.DataFrame(out).to_csv(str(OUT_DIR / "verify_ni.csv"), index=False, encoding="utf-8-sig")
