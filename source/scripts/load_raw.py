"""원천 엑셀(01·04·04-1·04-2·05·09) → onepick DB의 raw 스키마, 세율표 → ref.tax_rate.

실행: .venv/bin/python -m scripts.load_raw [--source 원천폴더] [--url postgresql://localhost/onepick]
DB가 없으면 만들고 source/db/schema.sql을 적용한다. raw·ref 표는 매번 비우고 다시 채운다(원천에서 다시 만들 수 있음).
"""
import argparse
import warnings
from pathlib import Path

from core import db, tax_rates
from core.raw_tables import DEFAULT_SOURCE_DIR, RAW_BUILDERS, read_source


def tax_rate_rows() -> list[dict]:
    return [{
        "rule": b.rule, "lower_bound": b.lower_bound, "base_tax": b.base_tax, "rate_pct": b.rate_pct,
        "valid_from": b.valid_from, "source": b.source, "status": b.status,
    } for b in tax_rates.SEPARATE + tax_rates.BASIC]


def load_raw(url: str, source_dir: Path) -> dict[str, int]:
    warnings.filterwarnings("ignore", module="openpyxl")
    db.create_database(url)
    counts = {}
    with db.connect(url) as conn:
        db.apply_schema(conn)
        for table, (key, build) in RAW_BUILDERS.items():
            counts[table] = db.replace_rows(conn, table, build(read_source(key, source_dir)))
            print(f"  {table}: {counts[table]:,}행")
        counts["ref.tax_rate"] = db.replace_rows(conn, "ref.tax_rate", tax_rate_rows())
        print(f"  ref.tax_rate: {counts['ref.tax_rate']}행")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="원천 엑셀을 onepick DB의 raw 스키마에 적재")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DIR, help="01~09 엑셀이 있는 폴더")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    print(f"원천: {args.source}")
    load_raw(args.url, args.source)
