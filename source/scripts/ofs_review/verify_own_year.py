"""1차 판정에서 결론이 안 난 칸을 '그 연도 자기 사업보고서'의 별도 재무제표로 다시 확인한다.

대상: 비교기간 값으로만 원문과 맞은 칸, 원문이 둘 다와 다른 칸, 감사 대상 이름을 못 읽은 칸, 사명이 달라 보이는 칸.
사업보고서 접수번호는 별도_보완결과.csv의 배당 표 행(같은 회사·같은 연도)에서 가져온다.
결과: dart/verify_own_year.csv
"""
import re
import sys

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ofs_review"  # 결과 CSV (git 제외)

from scripts.ofs_review import dartdoc as dd  # noqa: E402
from scripts.ofs_review import verify_mismatch as vm  # noqa: E402

b = pd.read_csv(vm.SRC, dtype=str, encoding="utf-8-sig")
annual = (b[(b["출처"] == "배당 표") & b["접수번호"].notna()]
          .groupby(["corp_code", "사업연도"])["접수번호"].first().to_dict())
r = pd.read_csv(str(OUT_DIR / "verify_result.csv"), dtype={"corp_code": str, "연도": str})
r["corp_code"] = r["corp_code"].str.zfill(8)
need = r[r["메모"].str.contains("비교기간", na=False) | r["판정"].str.contains("둘 다|확인 못", na=False)
         | r["보고서 감사 대상"].fillna("").str.contains("만호제강|위너스$")]

out = []
for x in need.itertuples():
    rcp = annual.get((x.corp_code, x.연도))
    val, memo, title = None, "사업보고서 접수번호 없음", ""
    if rcp:
        allnodes = dd.toc(rcp)
        start = next((i for i, n in enumerate(allnodes) if re.fullmatch(r"\d+\.\s*재무제표", n["text"].strip())), None)
        nodes = []
        if start is not None:  # '4. 재무제표'와 그 아래 4-1, 4-2 … (다음 큰 목차 전까지)
            nodes = [allnodes[start]]
            for n in allnodes[start + 1:]:
                if re.match(r"\d+\.\s", n["text"].strip()):
                    break
                nodes.append(n)
        title = allnodes[0]["title"] if allnodes else ""
        text = "\n".join(dd.section_text(n) for n in nodes)
        val, memo = (vm.read_value(text.splitlines(), x.항목, int(x.연도)) if nodes else (None, "별도 재무제표 목차 없음"))
    if val is None:
        own = f"확인 못 함({memo})"
    elif abs(val - x._6) < 1:
        own = "자기 연도 사업보고서 = API 값"
    elif abs(val - x._7) < 1:
        own = "자기 연도 사업보고서 = 원문 후보"
    else:
        own = "자기 연도 사업보고서가 둘 다와 다름"
    out.append({**x._asdict(), "사업보고서": title, "사업보고서 값": val, "사업보고서 메모": memo, "2차 판정": own})
    print(x.회사, x.연도, x.항목, "→", own, flush=True)
pd.DataFrame(out).drop(columns=["Index"]).to_csv(str(OUT_DIR / "verify_own_year.csv"), index=False, encoding="utf-8-sig")
