"""data/sample/*.csv → 메모리 SQLite → sql/role_check.sql 실행 (DB 파일·API 키 불필요)"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
con = sqlite3.connect(":memory:")
for table, name in [("review_values", "review_values_jinyoung.csv"),
                    ("judgement", "judgement_2026.csv"),
                    ("price_coverage", "price_coverage.csv")]:
    pd.read_csv(ROOT / "data" / "sample" / name, dtype={"corp_code": str, "stock_code": str}).to_sql(table, con, index=False)

for i, q in enumerate(s for s in (ROOT / "sql" / "role_check.sql").read_text(encoding="utf-8").split(";") if "SELECT" in s):
    print(f"\n[{i + 1}]")
    print(pd.read_sql(q, con).to_string(index=False))
