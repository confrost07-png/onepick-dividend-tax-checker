"""원문 대조 결과(final_verdict.csv·verify_ni.csv) → report/검증/별도재무제표_원문대조_결과.csv (팀 공유용 칸별 결과).

실행: .venv/bin/python -m scripts.ofs_review.export_result_csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "raw" / "ofs_review"
OUT = ROOT / "report" / "검증" / "별도재무제표_원문대조_결과.csv"

v = pd.read_csv(OUT_DIR / "final_verdict.csv", dtype={"연도": str, "corp_code": str})
n = pd.read_csv(OUT_DIR / "verify_ni.csv", dtype={"연도": str})
a = pd.DataFrame({"질문": v["묶음"].map({"불일치": "Q2", "표시없는차이": "Q5"}), "corp_code": v["corp_code"].str.zfill(8),
                  "회사": v["회사"], "연도": v["연도"], "항목": v["항목"], "API 확정값": v["API 확정값"], "원문 후보": v["원문 후보"],
                  "원문 문서 감사 대상": v["보고서 감사 대상"], "원문 문서에서 다시 읽은 값": v["다시 읽은 값"],
                  "그 연도 사업보고서 값": v["사업보고서 값"], "최종 판정": v["최종"], "쓸 값": v["쓸 값"], "근거": v["근거"], "원문": v["원문"]})
b = pd.DataFrame({"질문": "Q8", "회사": n["회사"], "연도": n["연도"], "항목": "당기순이익(감사보고서 vs 배당 표)",
                  "API 확정값": n["감사보고서"], "원문 후보": n["배당 표"], "그 연도 사업보고서 값": n["사업보고서 별도 손익"],
                  "최종 판정": n["판정"], "근거": n["메모"]})
pd.concat([a, b]).to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"  {OUT.name}: {len(a) + len(b)}행")
