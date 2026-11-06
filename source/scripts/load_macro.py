"""ECOS 거시지표 CSV(data/raw/macro/) → onepick DB raw.ecos_macro.

실행: .venv/bin/python -m scripts.load_macro [--dir 폴더] [--url ...]
먼저 scripts.collect_macro로 CSV를 받아 둔다. 다시 돌리면 표를 비우고 새로 채운다.
"""
import argparse
import csv
from pathlib import Path

from core import db
from core import macro as m


def load_macro(url: str, folder: Path) -> int:
    rows = []
    for s in m.SERIES:
        path = folder / f"{s.name}.csv"
        if not path.exists():
            raise SystemExit(f"{path} 없음: 먼저 scripts.collect_macro 실행")
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows += m.db_rows(list(csv.DictReader(f)), path.name)
    with db.connect(url) as conn:
        db.apply_schema(conn)
        n = db.replace_rows(conn, "raw.ecos_macro", rows)
    print(f"  raw.ecos_macro: {n:,}행")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ECOS 거시지표 CSV를 onepick DB에 적재")
    ap.add_argument("--dir", type=Path, default=m.OUT_DIR, help="collect_macro 저장 폴더")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    load_macro(args.url, args.dir)
